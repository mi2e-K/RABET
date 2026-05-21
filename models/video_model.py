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
from fractions import Fraction
from pathlib import Path
from typing import Optional

import av
import av.error
import numpy as np
from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QImage


class VideoModel(QObject):
    """
    PyAV-backed playback model.

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

    # Reasonable defaults for codecs that don't report a frame rate.
    _DEFAULT_FRAME_RATE = 30.0
    _DEFAULT_FRAME_DURATION_MS = 33

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

        # Guard against re-entrant decode calls. Decoding happens on the
        # main thread today, but a future move to a worker thread should
        # not break correctness.
        self._decode_lock = threading.Lock()

        # ----- QTimers (created here, parented to self for cleanup) -----
        self._playback_timer = QTimer(self)
        self._playback_timer.timeout.connect(self._on_playback_tick)
        self._playback_timer.setTimerType(Qt.TimerType.PreciseTimer)

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

    def _frame_to_qimage(self, frame: av.VideoFrame) -> QImage:
        """Convert a PyAV VideoFrame to a self-contained QImage.

        Implementation notes:
            - ``frame.to_ndarray(format="rgb24")`` can return a numpy
              array whose underlying buffer is not C-contiguous (PyAV
              17+ in particular sometimes hands back a view into a
              SwsContext output buffer with extra alignment padding).
              QImage rejects non-contiguous buffers with ``BufferError``,
              so we force contiguity explicitly.
            - We pass the array's actual row stride (``strides[0]``)
              rather than ``3 * width`` to be defensive against any
              future libswscale change that pads each row.
            - The ``.copy()`` at the end is mandatory: without it the
              QImage shares the numpy buffer, but ``frame`` is about to
              be GC'd or recycled by the next decode call, which would
              leave the QImage pointing at freed memory.
        """
        # H264/H265 streams decode to YUV; ``rgb24`` triggers libswscale
        # conversion which is acceptably fast for 1080p on modern CPUs.
        # For 4K we may want to push this onto a worker thread later.
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
        self._current_pts = 0
        self._current_ms = 0
        self._last_emitted_position = -1

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

    def _emit_frame(self, frame: av.VideoFrame) -> None:
        """Helper: convert to QImage, cache, and emit ``frame_ready``."""
        qimg = self._frame_to_qimage(frame)
        self._last_frame_image = qimg
        self.frame_ready.emit(qimg)

    # ------------------------------------------------------------------ #
    # Loading / teardown
    # ------------------------------------------------------------------ #

    @Slot(str)
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
        try:
            frame = self._decode_next_frame()
            if frame is None:
                # EOF
                self.logger.debug("Reached end of stream")
                self.pause()
                return
            self._update_current_position(frame)
            self._emit_frame(frame)
        except Exception as exc:
            self.logger.error("Playback tick failed: %s", exc, exc_info=True)
            self.pause()

    # ------------------------------------------------------------------ #
    # Seek / step
    # ------------------------------------------------------------------ #

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

        if was_playing:
            self.play()
        return True

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
        self.logger.debug("Playback rate set to %.3fx", rate)

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
