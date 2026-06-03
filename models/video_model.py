# models/video_model.py - PyAV (FFmpeg) backed video model.
#
# Rewritten for RABET 1.3.1 to retire the python-vlc dependency.
#
# Background:
#     Earlier RABET releases used libVLC (via python-vlc) as a full
#     playback engine — it owned the decoder, the cache, the video output
#     surface, and the per-frame display buffer. While paused, the libVLC
#     vout layer could keep showing a frame that did not match the
#     internal position state. Specifically: after a seek, the user had to
#     press the arrow key three or four times before the on-screen frame
#     updated, because the vout buffer was holding stale pre-seek frames
#     and there is no libvlc-level API to flush it. We tried every
#     documented workaround (set_pause toggle, next_frame, file-caching=20,
#     play/pause pulse with various durations) and confirmed the limit is
#     in libvlc itself rather than how we use it.
#
#     1.3.1 replaces VLC with PyAV. PyAV exposes FFmpeg's demuxer/decoder
#     directly: we ask it for one frame at a time and render it ourselves
#     onto a QLabel via QImage. There is no asynchronous vout buffer
#     between "decoded frame" and "on-screen pixels", so a seek + decode
#     deterministically lands on the requested frame. Audio playback is
#     dropped entirely (not needed for annotation work).
#
# Architecture summary:
#     - ``av.open`` returns an InputContainer that we keep open for the
#       lifetime of the loaded video.
#     - One ``av.VideoStream`` is selected; we set ``thread_type="AUTO"``
#       so FFmpeg internally parallelises decoding when codecs allow it.
#     - Playback is driven by ``_playback_timer`` (a QTimer in
#       PreciseTimer mode). Each tick demuxes one frame, converts it to
#       ``QImage`` and emits :pyattr:`frame_ready`. The view connects
#       ``frame_ready`` to its display slot — that's the entire render
#       path, no native window handle plumbing.
#     - ``seek`` calls ``container.seek(pts, backward=True,
#       any_frame=False)`` so we land on or before the nearest keyframe,
#       then drains frames until ``frame.pts >= target_pts``. This is the
#       canonical PyAV "frame-accurate seek" pattern.
#     - ``step_forward`` just decodes one more frame. ``step_backward`` is
#       a seek (PyAV has no native reverse step).
#
# Compatibility notes for callers:
#     - The public Signal contract is unchanged (``playback_state_changed``,
#       ``position_changed``, ``duration_changed``, ``video_loaded``,
#       ``error_occurred``), plus the new ``frame_ready(QImage)``.
#     - Method names ``load_video``/``play``/``pause``/``stop``/``seek``/
#       ``seek_with_retry``/``step_forward``/``step_backward``/
#       ``get_position``/``get_duration``/``is_playing``/
#       ``get_frame_rate``/``set_playback_rate``/``toggle_play`` are
#       preserved. ``seek_with_retry`` is now just an alias for ``seek``
#       since PyAV's seek is deterministic.
#     - The legacy attributes ``_video_path``, ``_duration``,
#       ``_last_seek_position``, ``_frame_duration_ms`` are still present
#       so ``annotation_controller`` and ``video_controller`` keep working
#       without code changes.
#     - Removed APIs (callers in this repo were already updated): the
#       VLC-specific ``set_window_handle``, ``set_hwnd``/``set_xwindow``/
#       ``set_nsobject``, ``set_volume``/``set_muted``/``get_volume``/
#       ``is_muted``, ``refresh_frame``, ``pulse_frame_for_refresh``,
#       ``_force_refresh_frame``, and the legacy ``media_player`` attribute.

from __future__ import annotations

import logging
import threading
import time
from fractions import Fraction
from pathlib import Path
from typing import Optional

import av
import av.error
import numpy as np
from PySide6.QtCore import (
    Q_ARG,
    Q_RETURN_ARG,
    QMetaObject,
    QObject,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QImage


class _VideoDecodeWorker(QObject):
    """
    PyAV-backed decode worker. Runs on its own QThread; every av/container
    interaction (open, decode, seek, the playback QTimer) happens here. The
    UI-facing ``VideoModel`` facade (bottom of this file) owns the thread,
    queues commands to these slots, and relays the signals below.

    This was the public playback model until decode moved off the UI thread
    (A-1); the signal/method contract is preserved by the facade.

    Signals:
        playback_state_changed (bool): True=playing, False=paused.
        position_changed (int): current playback position in milliseconds.
        duration_changed (int): video duration in milliseconds (emitted
            once per ``load_video``).
        video_loaded (str): path of the newly loaded video.
        error_occurred (str): human-readable error message.
        frame_ready (QImage): a newly decoded frame ready to display. The
            view should connect this to its display slot.
    """

    # ---- Public signals (API contract) ----
    playback_state_changed = Signal(bool)
    position_changed = Signal(int)
    duration_changed = Signal(int)
    video_loaded = Signal(str)
    error_occurred = Signal(str)
    frame_ready = Signal(QImage)

    # Emitted (only on change) when the playback tick detects it is, or is
    # no longer, falling behind real time under CPU load. True = under load
    # (render cheaply); False = keeping up (render at full quality). The
    # view connects this to switch its scaling between Fast and Smooth.
    render_load_changed = Signal(bool)

    # Worker -> facade: stream frame rate + per-frame duration (ms), emitted
    # once per load so the facade can cache them for get_frame_rate() and the
    # _frame_duration_ms attribute (read by annotation_controller).
    frame_rate_changed = Signal(float, int)

    # Reasonable defaults for codecs that don't report a frame rate.
    _DEFAULT_FRAME_RATE = 30.0
    _DEFAULT_FRAME_DURATION_MS = 33

    # ----- Load-detection tuning (Change B) -----
    # A tick is "late" when the wall-clock gap since the previous tick
    # exceeds ``interval * _LATE_GAP_FACTOR + _LATE_GAP_FLOOR_MS``. The
    # factor tolerates ordinary timer jitter; the floor keeps very short
    # intervals (high playback rates) from tripping on sub-millisecond
    # noise. Hysteresis: engage "under load" only after this many
    # consecutive late ticks, and clear it only after this many consecutive
    # on-time ticks — prevents quality flicker on transient spikes.
    _LATE_GAP_FACTOR = 1.5
    _LATE_GAP_FLOOR_MS = 5.0
    _LOAD_ENGAGE_LATE_FRAMES = 4
    _LOAD_CLEAR_ONTIME_FRAMES = 12

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing VideoModel (PyAV backend)")

        # ----- PyAV state -----
        self._container: Optional[av.container.InputContainer] = None
        self._stream: Optional[av.video.stream.VideoStream] = None

        # Stream metadata cached at load time so we don't pay PyAV's
        # attribute lookup cost on every tick.
        self._time_base: Fraction = Fraction(1, 1)
        self._stream_start_pts: int = 0
        self._frame_rate: float = self._DEFAULT_FRAME_RATE
        # ``_frame_duration_ms`` is read directly by annotation_controller
        # (see annotation_controller.py:79, models/annotation_model.py:133).
        # Keep the attribute name stable.
        self._frame_duration_ms: int = self._DEFAULT_FRAME_DURATION_MS

        # ----- Legacy-public state (read by controllers; kept stable) -----
        self._video_path: Optional[str] = None
        self._duration: int = 0          # ms, kept for video_controller
        self._last_seek_position: int = 0
        self._is_playing: bool = False
        # ``_operation_in_progress`` is retained for binary compatibility
        # with any caller that might still inspect it. Under PyAV the
        # whole decode path runs synchronously on the main thread, so we
        # never set this to True; the attribute simply lets ``hasattr``
        # checks downstream stay happy.
        self._operation_in_progress: bool = False

        # ----- Playback state -----
        self._current_pts: int = 0
        self._current_ms: int = 0
        self._playback_rate: float = 1.0
        self._last_emitted_position: int = -1

        # Cache the most recent QImage so a resize / re-paint can reuse it
        # without re-decoding.
        self._last_frame_image: Optional[QImage] = None

        # ----- Display-size / load-adaptation state (Changes A & B) -----
        # Retain the most recent *decoded* frame (not just its QImage) so a
        # resize-while-paused can re-run libswscale at the new target size
        # and stay crisp instead of upscaling a small bitmap.
        self._last_decoded_frame: Optional[av.VideoFrame] = None
        # Target display size in *logical* pixels (the size of the view's
        # video label). 0 means "unset" → fall back to full-res convert.
        self._target_display_w: int = 0
        self._target_display_h: int = 0
        # Load state + tick-timing bookkeeping (see _update_load_state).
        self._under_load: bool = False
        self._last_tick_monotonic: Optional[float] = None
        self._late_tick_count: int = 0
        self._ontime_tick_count: int = 0
        # libswscale interpolation modes. Resolved once here; if the
        # installed PyAV doesn't expose the enum (older builds) we degrade
        # gracefully to "no interpolation argument".
        try:
            from av.video.reformatter import Interpolation as _Interp
            self._interp_normal = _Interp.BILINEAR
            self._interp_fast = _Interp.FAST_BILINEAR
        except Exception:
            self._interp_normal = None
            self._interp_fast = None
        self._interp_supported = self._interp_normal is not None

        # Guard against re-entrant decode calls. Decoding happens on the
        # main thread today, but a future move to a worker thread should
        # not break correctness.
        self._decode_lock = threading.Lock()

        # ----- QTimers (created here, parented to self for cleanup) -----
        self._playback_timer = QTimer(self)
        self._playback_timer.timeout.connect(self._on_playback_tick)
        self._playback_timer.setTimerType(Qt.TimerType.PreciseTimer)

        # Seek coalescing (PR-V3): the facade publishes the latest drag target
        # to _pending_seek_ms and pings _drain_seek; intermediate targets are
        # superseded so a fast slider drag doesn't decode every waypoint.
        self._pending_seek_ms: Optional[int] = None
        self._last_drained_seek: Optional[int] = None

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _ms_to_pts(self, ms: int) -> int:
        """Convert a millisecond timestamp to PTS in the stream's time base.

        Uses Fraction arithmetic to avoid float rounding errors that
        would otherwise accumulate over long videos.
        """
        if self._time_base == 0:
            return 0
        # ms -> seconds (as Fraction) -> stream PTS
        pts = int(Fraction(ms, 1000) / self._time_base)
        return pts + self._stream_start_pts

    def _pts_to_ms(self, pts: int) -> int:
        """Inverse of :meth:`_ms_to_pts`."""
        if pts is None:
            return 0
        delta = pts - self._stream_start_pts
        return int(Fraction(delta) * self._time_base * 1000)

    def _playback_target_size(self, frame: av.VideoFrame) -> Optional[tuple]:
        """Compute the aspect-ratio-fit target size for ``frame``.

        Returns ``(width, height)`` to which the frame should be downscaled
        so it fits inside the current display label, or ``None`` when no
        target is set or fitting would *upscale* the frame. We never upscale
        here: enlarging is cheap for Qt and keeping the full-res image lets a
        later resize stay crisp.
        """
        tw = self._target_display_w
        th = self._target_display_h
        if tw <= 0 or th <= 0:
            return None
        src_w = int(frame.width)
        src_h = int(frame.height)
        if src_w <= 0 or src_h <= 0:
            return None
        # Aspect-ratio-fit (letterbox) inside the label, matching Qt's
        # KeepAspectRatio used by the view's full-res path.
        scale = min(tw / src_w, th / src_h)
        if scale >= 1.0:
            return None  # Would upscale → keep full resolution.
        out_w = max(1, int(round(src_w * scale)))
        out_h = max(1, int(round(src_h * scale)))
        if out_w >= src_w or out_h >= src_h:
            return None
        return (out_w, out_h)

    def _reformat_to_rgb(self, frame: av.VideoFrame, target: Optional[tuple]):
        """Fused YUV→RGB convert (+ optional downscale) via libswscale.

        Returns a numpy ``rgb24`` array, or ``None`` if reformat fails (the
        caller then falls back to the plain full-res convert path).
        """
        try:
            kwargs = dict(format="rgb24")
            if target is not None:
                kwargs["width"] = target[0]
                kwargs["height"] = target[1]
            if self._interp_supported:
                # Cheaper scaler while under load; crisp bilinear otherwise.
                kwargs["interpolation"] = (
                    self._interp_fast if self._under_load else self._interp_normal
                )
            try:
                rgb_frame = frame.reformat(**kwargs)
            except TypeError:
                # Older PyAV without the ``interpolation`` kwarg.
                self._interp_supported = False
                kwargs.pop("interpolation", None)
                rgb_frame = frame.reformat(**kwargs)
            return rgb_frame.to_ndarray()
        except Exception as exc:
            self.logger.debug("reformat-to-size failed (%s); full-res fallback", exc)
            return None

    def _frame_to_qimage(self, frame: av.VideoFrame, for_playback: bool = False) -> QImage:
        """Convert a PyAV VideoFrame to a self-contained QImage.

        When ``for_playback`` is True and a display target size is set that
        is *smaller* than the frame, libswscale fuses the YUV→RGB convert
        and the downscale into a single pass (Change A) — far cheaper than
        converting at full resolution and then letting Qt rescale, which is
        the dominant per-frame cost on 4K. Under detected load the cheaper
        FAST_BILINEAR scaler is used (Change B). Otherwise we fall back to a
        full-resolution convert and let the view scale (keeps paused/seeked
        stills crisp and lets resize re-render from full res).

        Implementation notes:
            - ``to_ndarray`` can return a numpy array whose underlying
              buffer is not C-contiguous (PyAV 17+ in particular sometimes
              hands back a view into a SwsContext output buffer with extra
              alignment padding). QImage rejects non-contiguous buffers with
              ``BufferError``, so we force contiguity explicitly.
            - We pass the array's actual row stride (``strides[0]``) rather
              than ``3 * width`` to be defensive against any future
              libswscale change that pads each row.
            - The ``.copy()`` at the end is mandatory: without it the QImage
              shares the numpy buffer, but ``frame`` is about to be GC'd or
              recycled by the next decode call, which would leave the QImage
              pointing at freed memory.
        """
        arr = None
        if for_playback:
            target = self._playback_target_size(frame)
            if target is not None:
                arr = self._reformat_to_rgb(frame, target)
        if arr is None:
            # Full-resolution convert (load/first-frame/paused/seek paths,
            # or fallback when reformat-to-size is unavailable).
            arr = frame.to_ndarray(format="rgb24")
        if not arr.flags["C_CONTIGUOUS"]:
            arr = np.ascontiguousarray(arr)
        height, width, _ = arr.shape
        bytes_per_line = arr.strides[0]
        qimg = QImage(
            arr.data, width, height, bytes_per_line,
            QImage.Format.Format_RGB888,
        )
        return qimg.copy()  # Detach from numpy buffer; see docstring.

    def _populate_stream_metadata(self) -> None:
        """Cache frame rate / duration / time base from the loaded stream."""
        assert self._stream is not None

        # Frame rate: ``average_rate`` is most reliable; fall back to
        # ``base_rate`` and finally to a 30fps default.
        rate = self._stream.average_rate or self._stream.base_rate
        if rate and float(rate) > 0:
            self._frame_rate = float(rate)
        else:
            self._frame_rate = self._DEFAULT_FRAME_RATE
        self._frame_duration_ms = max(1, int(round(1000.0 / self._frame_rate)))

        # Time base (Fraction). Keep as Fraction so PTS conversion stays
        # exact.
        self._time_base = (
            self._stream.time_base if self._stream.time_base is not None
            else Fraction(1, 1)
        )

        self._stream_start_pts = self._stream.start_time or 0

        # Duration: prefer the stream's own duration; otherwise the
        # container's (which is in AV_TIME_BASE = microseconds).
        if self._stream.duration is not None:
            self._duration = int(
                Fraction(self._stream.duration) * self._time_base * 1000
            )
        elif self._container is not None and self._container.duration is not None:
            self._duration = int(self._container.duration / 1000)  # us -> ms
        else:
            self._duration = 0

        self.logger.debug(
            "Stream metadata: %.3f fps (%d ms/frame), time_base=%s, "
            "start_pts=%d, duration=%d ms",
            self._frame_rate, self._frame_duration_ms, self._time_base,
            self._stream_start_pts, self._duration,
        )
        self.frame_rate_changed.emit(self._frame_rate, self._frame_duration_ms)

    def _close_container(self) -> None:
        """Tear down the current PyAV container if any.

        Idempotent — safe to call from ``load_video`` (before opening a
        new file), from ``stop``, and from ``__del__``. Releasing the
        container is what frees the FFmpeg codec context and any
        internally-held memory.
        """
        if self._playback_timer.isActive():
            self._playback_timer.stop()
        self._is_playing = False

        if self._container is not None:
            try:
                self._container.close()
            except Exception:
                # Closing twice or after partial open can raise; nothing
                # we can do, just keep going.
                pass
            self._container = None
        self._stream = None
        self._last_frame_image = None
        self._last_decoded_frame = None
        self._current_pts = 0
        self._current_ms = 0
        self._last_emitted_position = -1
        # Reset load-detection state so a freshly loaded video starts
        # optimistic (full quality) rather than inheriting the prior file's
        # under-load flag.
        self._under_load = False
        self._last_tick_monotonic = None
        self._late_tick_count = 0
        self._ontime_tick_count = 0
        self._pending_seek_ms = None
        self._last_drained_seek = None

    def _decode_next_frame(self) -> Optional[av.VideoFrame]:
        """Pull the next decoded video frame from the demuxer.

        Returns ``None`` at EOF or when no container is loaded.
        """
        if self._stream is None or self._container is None:
            return None
        with self._decode_lock:
            try:
                for packet in self._container.demux(self._stream):
                    for frame in packet.decode():
                        if frame is None:
                            continue
                        return frame
            except av.error.EOFError:
                return None
            except Exception as exc:
                self.logger.error(
                    "Decode error: %s", exc, exc_info=True
                )
                return None
        return None

    def _update_current_position(self, frame: av.VideoFrame) -> None:
        """Refresh internal position state from ``frame.pts`` and emit."""
        if frame.pts is None:
            return
        self._current_pts = frame.pts
        new_ms = self._pts_to_ms(frame.pts)
        if new_ms != self._current_ms or new_ms != self._last_emitted_position:
            self._current_ms = new_ms
            self._last_emitted_position = new_ms
            self.position_changed.emit(new_ms)

    def _emit_frame(self, frame: av.VideoFrame, for_playback: bool = False) -> None:
        """Helper: convert to QImage, cache, and emit ``frame_ready``.

        ``for_playback`` enables the decode-to-display-size fast path
        (Change A). The decoded frame is retained so a resize-while-paused
        can re-render it at full quality for the new target size.
        """
        self._last_decoded_frame = frame
        qimg = self._frame_to_qimage(frame, for_playback=for_playback)
        self._last_frame_image = qimg
        self.frame_ready.emit(qimg)

    # ------------------------------------------------------------------ #
    # Loading / teardown
    # ------------------------------------------------------------------ #

    @Slot(str, result=bool)
    def load_video(self, video_path: str) -> bool:
        """Open a video file and decode the first frame.

        Args:
            video_path: filesystem path of the video to open.

        Returns:
            True on success, False otherwise (an ``error_occurred`` signal
            is emitted on failure).
        """
        if not video_path or not Path(video_path).exists():
            msg = f"Video file not found: {video_path}"
            self.logger.error(msg)
            self.error_occurred.emit(msg)
            return False

        # Always close the previous container BEFORE opening a new one,
        # otherwise FFmpeg's codec context (which can be tens of MB for
        # high-resolution H.264) leaks until we exit the app.
        self._close_container()

        try:
            self.logger.info("Opening video with PyAV: %s", video_path)
            self._container = av.open(video_path, mode="r")
            if not self._container.streams.video:
                msg = "File contains no video stream"
                self.logger.error(msg)
                self.error_occurred.emit(msg)
                self._close_container()
                return False

            self._stream = self._container.streams.video[0]
            # ``AUTO`` lets FFmpeg pick between FRAME and SLICE threading
            # based on the codec. H.264/H.265 typically use FRAME and
            # parallelise well across cores.
            self._stream.thread_type = "AUTO"

            self._populate_stream_metadata()

            # Decode the first frame so the user sees something the moment
            # the file is loaded (otherwise the QLabel stays black).
            first_frame = self._decode_next_frame()
            if first_frame is not None:
                self._update_current_position(first_frame)
                self._emit_frame(first_frame)
            else:
                self.logger.warning(
                    "Loaded %s but produced no first frame", video_path
                )

            # Reset bookkeeping; emit the public signals last so consumers
            # see a fully-initialised model.
            self._video_path = video_path
            self._last_seek_position = self._current_ms
            self.duration_changed.emit(self._duration)
            self.video_loaded.emit(video_path)
            return True

        except (av.error.FFmpegError, OSError) as exc:
            msg = f"Failed to open video with PyAV: {exc}"
            self.logger.error(msg, exc_info=True)
            self.error_occurred.emit(msg)
            self._close_container()
            return False

    @Slot()
    def close(self) -> None:
        """Public teardown — called by callers that need explicit shutdown."""
        self._close_container()

    def __del__(self):
        try:
            self._close_container()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Playback control
    # ------------------------------------------------------------------ #

    @Slot()
    def play(self) -> None:
        if self._container is None or self._is_playing:
            return
        self.logger.debug("Play command received")
        self._is_playing = True
        # Start optimistic: reset the tick-timing baseline and counters so a
        # fresh play() re-evaluates load from scratch. If we were flagged
        # under load from a previous run, clear it and tell the view to go
        # back to full quality; sustained lag will re-engage it.
        self._last_tick_monotonic = None
        self._late_tick_count = 0
        self._ontime_tick_count = 0
        if self._under_load:
            self._under_load = False
            self.render_load_changed.emit(False)
        interval = max(1, int(self._frame_duration_ms / max(0.01, self._playback_rate)))
        self._playback_timer.start(interval)
        self.playback_state_changed.emit(True)

    @Slot()
    def pause(self) -> None:
        if not self._is_playing:
            return
        self.logger.debug("Pause command received")
        self._is_playing = False
        self._playback_timer.stop()
        self.playback_state_changed.emit(False)
        # Re-render the frozen frame at full resolution. During playback the
        # emitted QImage may have been downscaled-to-fit (Change A) and/or
        # rendered with the cheaper scaler (Change B); the still frame the
        # user now examines should always be crisp. Cheap: one extra convert
        # of the already-decoded frame, only on the pause transition.
        if self._last_decoded_frame is not None and (
            self._target_display_w > 0 or self._under_load
        ):
            try:
                self._emit_frame(self._last_decoded_frame, for_playback=False)
            except Exception as exc:
                self.logger.debug("Full-res re-render on pause failed: %s", exc)

    @Slot()
    def stop(self) -> None:
        """Stop playback (does NOT close the container)."""
        self.logger.debug("Stop command received")
        was_playing = self._is_playing
        self._is_playing = False
        if self._playback_timer.isActive():
            self._playback_timer.stop()
        # Reset playhead to the start; this mirrors VLC's old ``stop``.
        if self._container is not None:
            self.seek(0)
        if was_playing:
            self.playback_state_changed.emit(False)

    @Slot()
    def toggle_play(self) -> None:
        if self._is_playing:
            self.pause()
        else:
            self.play()

    def is_playing(self) -> bool:
        return self._is_playing

    def _on_playback_tick(self) -> None:
        """QTimer callback: decode and display one frame, advance state."""
        if self._container is None:
            self.pause()
            return
        tick_t0 = time.monotonic()
        # Cheap load detection: measure how late this tick fired relative to
        # the timer interval. Must run before the decode work so the gap we
        # measure is the *inter-tick* gap, capturing both OS starvation
        # (timer firing late) and our own per-frame slowness from last tick.
        self._update_load_state()
        try:
            frame = self._decode_next_frame()
            if frame is None:
                # EOF
                self.logger.debug("Reached end of stream")
                self.pause()
                return
            self._update_current_position(frame)
            self._emit_frame(frame, for_playback=True)
            self._log_decode_timing("tick", tick_t0, level=logging.DEBUG)
        except Exception as exc:
            self.logger.error("Playback tick failed: %s", exc, exc_info=True)
            self.pause()

    def _update_load_state(self) -> None:
        """Detect sustained playback lag and toggle ``_under_load``.

        Compares the wall-clock gap since the previous tick against the
        timer interval. A handful of consecutive late ticks engages
        "under load" (cheaper rendering); a longer run of on-time ticks
        clears it. Hysteresis (the asymmetric thresholds) avoids quality
        flicker on transient spikes. Cost is a couple of ``monotonic()``
        reads and integer compares per frame — negligible against the
        multi-millisecond decode/convert that follows.
        """
        now = time.monotonic()
        last = self._last_tick_monotonic
        self._last_tick_monotonic = now
        if last is None:
            # First tick after play()/rate change — no baseline to compare.
            return
        interval_ms = self._playback_timer.interval() or self._frame_duration_ms
        gap_ms = (now - last) * 1000.0
        late = gap_ms > interval_ms * self._LATE_GAP_FACTOR + self._LATE_GAP_FLOOR_MS
        if late:
            self._late_tick_count += 1
            self._ontime_tick_count = 0
        else:
            self._ontime_tick_count += 1
            self._late_tick_count = 0

        if not self._under_load and self._late_tick_count >= self._LOAD_ENGAGE_LATE_FRAMES:
            self._under_load = True
            self._late_tick_count = 0
            self.logger.debug("Playback under load: switching to fast rendering")
            self.render_load_changed.emit(True)
        elif self._under_load and self._ontime_tick_count >= self._LOAD_CLEAR_ONTIME_FRAMES:
            self._under_load = False
            self._ontime_tick_count = 0
            self.logger.debug("Playback caught up: restoring full-quality rendering")
            self.render_load_changed.emit(False)

    def _log_decode_timing(self, op: str, t0: float, level: int = logging.INFO) -> None:
        """Measure how long an av decode op blocked its thread (PR-V1).

        Under the current main-thread backend this is time the UI is blocked;
        after the worker move the same work should run off the UI thread. Logs
        the elapsed ms and the executing thread name so before/after compares.
        """
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        self.logger.log(
            level,
            "[video-timing] %s decode=%.1fms thread=%s",
            op, elapsed_ms, threading.current_thread().name,
        )

    # ------------------------------------------------------------------ #
    # Seek / step
    # ------------------------------------------------------------------ #

    @Slot()
    def _drain_seek(self) -> None:
        """Coalesced seek entry point (PR-V3).

        Reads the latest target the facade published to ``_pending_seek_ms`` and
        seeks to it, skipping a target already served. Rapid drag pings collapse
        to the newest position instead of decoding every waypoint.
        """
        ms = self._pending_seek_ms
        if ms is None or ms == self._last_drained_seek:
            return
        self._last_drained_seek = ms
        self.seek(ms)

    @Slot(int)
    def seek(self, position_ms: int) -> bool:
        """Frame-accurate seek to ``position_ms``.

        Picks the decoded frame whose PTS is *closest* to ``target_pts``.
        Using "first frame >= target_pts" (the obvious choice) systematically
        overshoots by one frame whenever ``target_pts`` falls between two
        frames, which broke ``step_backward`` — e.g. on a 29.97fps stream,
        stepping back by one ``_frame_duration_ms`` (33 ms) from ms=1001
        landed back on the same frame because the first frame >= 968 ms
        was ms=1001 itself.

        Closest-frame selection works for both directions:
            - Forward seek lands on the frame closest to the request.
            - Backward step deterministically returns the previous frame.

        Resumes playback only if it was playing before the seek.
        """
        if self._container is None or self._stream is None or self._duration <= 0:
            return False

        seek_t0 = time.monotonic()
        was_playing = self._is_playing
        if was_playing:
            self.pause()

        position_ms = max(0, min(int(position_ms), self._duration))
        self._last_seek_position = position_ms
        target_pts = self._ms_to_pts(position_ms)

        with self._decode_lock:
            try:
                # ``backward=True`` lands us on the nearest keyframe <=
                # target_pts; ``any_frame=False`` ensures we don't end up
                # on a non-decodable frame.
                self._container.seek(
                    target_pts,
                    stream=self._stream,
                    any_frame=False,
                    backward=True,
                )
            except av.error.FFmpegError as exc:
                self.logger.error(
                    "Container seek to %d ms failed: %s", position_ms, exc
                )
                if was_playing:
                    self.play()
                return False

            # Walk frames forward from the keyframe. Track:
            #   - last_before: the most recent frame whose pts < target_pts
            #   - first_at_or_after: the first frame whose pts >= target_pts
            # then pick whichever is closer to target_pts.
            last_before: Optional[av.VideoFrame] = None
            first_at_or_after: Optional[av.VideoFrame] = None
            try:
                done = False
                for packet in self._container.demux(self._stream):
                    for frame in packet.decode():
                        if frame is None or frame.pts is None:
                            continue
                        if frame.pts < target_pts:
                            last_before = frame
                        else:
                            first_at_or_after = frame
                            done = True
                            break
                    if done:
                        break
            except av.error.EOFError:
                pass
            except Exception as exc:
                self.logger.error(
                    "Seek-drain decode failed: %s", exc, exc_info=True
                )

            chosen: Optional[av.VideoFrame]
            if first_at_or_after is None and last_before is None:
                chosen = None
            elif first_at_or_after is None:
                chosen = last_before
            elif last_before is None:
                chosen = first_at_or_after
            else:
                # Tie-break toward first_at_or_after when both are equally
                # close: this matches the prior "first frame >= target"
                # semantics for the common forward-seek case while still
                # giving step_backward the previous frame whenever the
                # caller is asking for a strictly earlier ms.
                forward_dist = first_at_or_after.pts - target_pts
                backward_dist = target_pts - last_before.pts
                if forward_dist <= backward_dist:
                    chosen = first_at_or_after
                else:
                    chosen = last_before

            if chosen is None:
                self.logger.warning(
                    "Seek to %d ms produced no frame", position_ms
                )
                if was_playing:
                    self.play()
                return False

            self._update_current_position(chosen)
            self._emit_frame(chosen)
            self._log_decode_timing("seek", seek_t0)

        if was_playing:
            self.play()
        return True

    @Slot(int)
    def seek_with_retry(self, position_ms: int, retries: int = 3) -> bool:
        """Compatibility wrapper.

        Under the old VLC backend this called ``seek`` then re-checked the
        position via ``_check_seek_result``, retrying up to ``retries``
        times if VLC undershot. PyAV's seek is deterministic — once
        :meth:`seek` returns success, the displayed frame matches the
        requested PTS — so the retry logic is unnecessary. The signature
        is kept so video_controller doesn't need to change.
        """
        _ = retries
        return self.seek(position_ms)

    @Slot(int)
    def step_forward(self, time_ms: Optional[int] = None) -> bool:
        """Decode one or more frames forward without resuming playback.

        Args:
            time_ms: amount to step forward in ms. Values <= 50 are
                treated as a single-frame step (matches the legacy
                "small value => frame step" heuristic used by
                video_controller). Larger values move
                ``round(time_ms / frame_duration_ms)`` frames forward.
        """
        if self._container is None or self._stream is None:
            return False

        if self._is_playing:
            self.pause()

        if time_ms is None or time_ms <= 50:
            frames_to_advance = 1
        else:
            frames_to_advance = max(
                1, int(round(time_ms / max(1, self._frame_duration_ms)))
            )

        last_frame: Optional[av.VideoFrame] = None
        for _ in range(frames_to_advance):
            frame = self._decode_next_frame()
            if frame is None:
                break
            last_frame = frame

        if last_frame is None:
            return False
        self._update_current_position(last_frame)
        self._emit_frame(last_frame)
        return True

    @Slot(int)
    def step_backward(self, time_ms: Optional[int] = None) -> bool:
        """Step backward by seeking to (current - step_ms).

        PyAV has no native "step back" so we seek + decode. Because
        :meth:`seek` is frame-accurate, the result is deterministic.
        """
        if self._container is None:
            return False
        if self._is_playing:
            self.pause()

        if time_ms is None or time_ms <= 50:
            step_ms = self._frame_duration_ms
        else:
            step_ms = max(self._frame_duration_ms, int(time_ms))

        target_ms = max(0, self._current_ms - step_ms)
        return self.seek(target_ms)

    # ------------------------------------------------------------------ #
    # State queries
    # ------------------------------------------------------------------ #

    def get_position(self) -> int:
        """Current playback position in milliseconds."""
        return self._current_ms

    def get_duration(self) -> int:
        return self._duration

    def get_frame_rate(self) -> float:
        return self._frame_rate

    @Slot(float)
    def set_playback_rate(self, rate: float) -> None:
        """Change the playback rate (0.25 .. 4.0 is sensible).

        Implementation: scale the playback timer's interval; the decoder
        itself always runs at native speed because that's what FFmpeg
        does. A faster rate means we tick more often and consume frames
        more quickly; a slower rate means we tick less often.
        """
        try:
            rate = float(rate)
        except (TypeError, ValueError):
            self.logger.warning("Invalid playback rate ignored: %r", rate)
            return
        rate = max(0.01, min(rate, 16.0))
        self._playback_rate = rate
        if self._is_playing:
            interval = max(1, int(self._frame_duration_ms / self._playback_rate))
            self._playback_timer.setInterval(interval)
            # The interval just changed; drop the timing baseline so the
            # next tick's gap isn't measured against the old interval and
            # mis-flagged as "late".
            self._last_tick_monotonic = None
        self.logger.debug("Playback rate set to %.3fx", rate)

    @Slot(int, int)
    def set_target_display_size(self, width: int, height: int) -> None:
        """Tell the model the size (logical px) of the view's video pane.

        The view emits this (throttled) from its resize/show events. When
        set, the playback path downscales frames to fit this size in a
        single libswscale pass (Change A) instead of converting at full
        resolution and letting Qt rescale. Logical (not device) pixels are
        used deliberately so output quality matches the previous behaviour
        on high-DPI displays.

        This is a pure setter: it only affects subsequently decoded
        *playback* frames. Resize-while-paused stays crisp without any
        re-decode here, because every paused emit path (load / pause / seek
        / step / stop) emits the frame at full resolution, and the view
        re-scales that cached full-res image itself on resize.
        """
        w = max(0, int(width))
        h = max(0, int(height))
        if w == self._target_display_w and h == self._target_display_h:
            return
        self._target_display_w = w
        self._target_display_h = h

    # ------------------------------------------------------------------ #
    # Compatibility no-ops
    # ------------------------------------------------------------------ #
    #
    # These methods existed under the VLC backend and are still referenced
    # from a couple of corners of the codebase. We expose harmless no-ops
    # so the migration can be staged: callers that should drop the calls
    # are updated in Phase 5, but until then nothing breaks.

    def set_window_handle(self, handle) -> bool:
        """No-op under PyAV — rendering goes through ``frame_ready``."""
        _ = handle
        return True

    def refresh_frame(self) -> None:
        """No-op under PyAV — there is no separate display buffer to poke."""
        return None

    def pulse_frame_for_refresh(self) -> None:
        """No-op under PyAV — see :meth:`refresh_frame`."""
        return None


class VideoModel(QObject):
    """UI-thread facade over :class:`_VideoDecodeWorker`.

    The worker runs all PyAV/decode work on its own QThread (A-1). This facade
    preserves the original signal / method / attribute contract: it queues
    commands to the worker, relays the worker's signals, and caches state so the
    synchronous ``get_*`` reads and the ``_frame_duration_ms`` attribute stay on
    the UI thread (it never reads worker state across the thread boundary).
    """

    playback_state_changed = Signal(bool)
    position_changed = Signal(int)
    duration_changed = Signal(int)
    video_loaded = Signal(str)
    error_occurred = Signal(str)
    frame_ready = Signal(QImage)
    render_load_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)

        # UI-side cached state (the synchronous reads below return these).
        self._video_path: Optional[str] = None
        self._duration: int = 0
        self._current_ms: int = 0
        self._is_playing: bool = False
        self._frame_rate: float = _VideoDecodeWorker._DEFAULT_FRAME_RATE
        self._frame_duration_ms: int = _VideoDecodeWorker._DEFAULT_FRAME_DURATION_MS
        self._last_seek_position: int = 0
        self._operation_in_progress: bool = False

        # Worker on its own thread.
        self._thread = QThread()
        self._thread.setObjectName("VideoDecodeWorker")
        self._worker = _VideoDecodeWorker()
        self._worker.moveToThread(self._thread)
        self._thread.start()

        # Relay worker signals (queued across the thread boundary).
        self._worker.frame_ready.connect(self.frame_ready)
        self._worker.render_load_changed.connect(self.render_load_changed)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.playback_state_changed.connect(self._on_worker_state)
        self._worker.position_changed.connect(self._on_worker_position)
        self._worker.duration_changed.connect(self._on_worker_duration)
        self._worker.video_loaded.connect(self._on_worker_loaded)
        self._worker.frame_rate_changed.connect(self._on_worker_frame_rate)

    # ----- relay slots (run on the UI thread: refresh cache + re-emit) -----
    @Slot(bool)
    def _on_worker_state(self, playing: bool) -> None:
        self._is_playing = playing
        self.playback_state_changed.emit(playing)

    @Slot(int)
    def _on_worker_position(self, ms: int) -> None:
        self._current_ms = ms
        self.position_changed.emit(ms)

    @Slot(int)
    def _on_worker_duration(self, ms: int) -> None:
        self._duration = ms
        self.duration_changed.emit(ms)

    @Slot(str)
    def _on_worker_loaded(self, path: str) -> None:
        self._video_path = path
        self.video_loaded.emit(path)

    @Slot(float, int)
    def _on_worker_frame_rate(self, rate: float, frame_duration_ms: int) -> None:
        self._frame_rate = rate
        self._frame_duration_ms = frame_duration_ms

    # ----- commands queued to the worker (non-blocking) -----
    def play(self) -> None:
        QMetaObject.invokeMethod(self._worker, "play", Qt.QueuedConnection)

    def pause(self) -> None:
        QMetaObject.invokeMethod(self._worker, "pause", Qt.QueuedConnection)

    def stop(self) -> None:
        QMetaObject.invokeMethod(self._worker, "stop", Qt.QueuedConnection)

    def toggle_play(self) -> None:
        QMetaObject.invokeMethod(self._worker, "toggle_play", Qt.QueuedConnection)

    def seek(self, position_ms: int) -> bool:
        ms = int(position_ms)
        self._last_seek_position = ms
        # Coalesce rapid seeks (slider drag): publish the latest target and ping
        # the worker to drain it; intermediate targets are superseded (PR-V3).
        self._worker._pending_seek_ms = ms
        QMetaObject.invokeMethod(self._worker, "_drain_seek", Qt.QueuedConnection)
        return True

    def seek_with_retry(self, position_ms: int, retries: int = 3) -> bool:
        return self.seek(position_ms)

    def step_forward(self, time_ms: Optional[int] = None) -> None:
        QMetaObject.invokeMethod(
            self._worker, "step_forward", Qt.QueuedConnection,
            Q_ARG(int, int(time_ms) if time_ms is not None else 0),
        )

    def step_backward(self, time_ms: Optional[int] = None) -> None:
        QMetaObject.invokeMethod(
            self._worker, "step_backward", Qt.QueuedConnection,
            Q_ARG(int, int(time_ms) if time_ms is not None else 0),
        )

    def set_playback_rate(self, rate: float) -> None:
        QMetaObject.invokeMethod(
            self._worker, "set_playback_rate", Qt.QueuedConnection,
            Q_ARG(float, float(rate)),
        )

    def set_target_display_size(self, width: int, height: int) -> None:
        QMetaObject.invokeMethod(
            self._worker, "set_target_display_size", Qt.QueuedConnection,
            Q_ARG(int, int(width)), Q_ARG(int, int(height)),
        )

    # ----- load / teardown -----
    def load_video(self, video_path: str) -> bool:
        """Synchronous: ThreadedVideoLoader expects a bool. Blocks the caller
        until the worker has opened the file and decoded the first frame (same
        blocking characteristic as before; the win is in playback/seek)."""
        self._last_seek_position = 0
        ok = QMetaObject.invokeMethod(
            self._worker, "load_video", Qt.BlockingQueuedConnection,
            Q_RETURN_ARG(bool), Q_ARG(str, str(video_path)),
        )
        return bool(ok)

    def close(self) -> None:
        """Close the current video (container). The worker thread stays alive so
        a subsequent load_video reuses it. Use shutdown() to stop the thread."""
        if self._thread.isRunning():
            QMetaObject.invokeMethod(
                self._worker, "close", Qt.BlockingQueuedConnection
            )

    def shutdown(self) -> None:
        """Stop the worker thread. Call on application teardown."""
        if self._thread.isRunning():
            QMetaObject.invokeMethod(
                self._worker, "close", Qt.BlockingQueuedConnection
            )
            self._thread.quit()
            self._thread.wait(3000)

    def __del__(self):
        try:
            self.shutdown()
        except Exception:
            pass

    # ----- synchronous state reads (UI-side cache) -----
    def is_playing(self) -> bool:
        return self._is_playing

    def get_position(self) -> int:
        return self._current_ms

    def get_duration(self) -> int:
        return self._duration

    def get_frame_rate(self) -> float:
        return self._frame_rate

    # ----- compatibility no-ops (mirror the worker) -----
    def set_window_handle(self, handle) -> bool:
        _ = handle
        return True

    def refresh_frame(self) -> None:
        return None

    def pulse_frame_for_refresh(self) -> None:
        return None
