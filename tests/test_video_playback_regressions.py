"""Regressions around loading and playing videos.

- every decoded frame is reachable, including the ones released by the
  decoder flush at the end of the stream;
- a seek that picks the earlier of two candidate frames does not make the next
  step skip a frame;
- opening a file while another one plays reports the stop, so the UI side is
  not left "playing" with a stopped worker (play/pause stuck);
- a failed open publishes that no video is loaded;
- a session whose end falls on the last frame completes at end of stream;
- a project video that fails to load gives the previous annotation routing
  back;
- a bare click on the position slider handle does not seek.
"""

from __future__ import annotations

import logging
import os
import time
import types

import av
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from controllers.annotation_controller import AnnotationController
from controllers.project_controller import ProjectController
from models.video_model import VideoModel, _VideoDecodeWorker
from views.video_player_view import VideoPlayerView

FPS = 10
FRAMES = 30
FRAME_MS = 1000 // FPS


def _make_video(path, frames=FRAMES, fps=FPS):
    """Write a small MPEG-4 clip with B-frames, so the decoder holds frames back."""
    with av.open(str(path), "w") as out:
        stream = out.add_stream("mpeg4", rate=fps)
        stream.width, stream.height, stream.pix_fmt = 64, 48, "yuv420p"
        stream.codec_context.options = {"bf": "2"}
        for index in range(frames):
            image = np.full((48, 64, 3), (index * 8) % 256, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(image, format="rgb24")
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    return str(path)


@pytest.fixture
def clip(tmp_path):
    return _make_video(tmp_path / "clip.mp4")


def _pump(ms):
    app = QApplication.instance()
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


# -------------------------------------------------------------------- #
# Decode worker
# -------------------------------------------------------------------- #


def test_every_frame_is_reachable_including_the_decoder_flush(qt_app, clip):
    worker = _VideoDecodeWorker()
    try:
        assert worker.load_video(clip)
        reached = 1  # load_video already decoded the first frame
        while worker._decode_next_frame() is not None:
            reached += 1
        assert reached == FRAMES
    finally:
        worker._close_container()


class _FakePacket:
    def __init__(self, frames):
        self._frames = frames

    def decode(self):
        return list(self._frames)


def test_frames_decoded_together_are_handed_out_in_order(qt_app):
    worker = _VideoDecodeWorker()
    packets = iter([_FakePacket(["f1", "f2", "f3"]), _FakePacket([]), _FakePacket(["f4"])])
    worker._stream = object()
    worker._container = types.SimpleNamespace(demux=lambda _stream: packets)
    try:
        assert [worker._decode_next_frame() for _ in range(5)] == [
            "f1", "f2", "f3", "f4", None,
        ]
    finally:
        worker._container = None
        worker._stream = None


def test_step_after_seek_that_picked_the_earlier_frame_does_not_skip(qt_app, clip):
    worker = _VideoDecodeWorker()
    try:
        assert worker.load_video(clip)
        # 30 ms past frame 12: frame 12 is closer and wins, while frame 13 was
        # already decoded to find the boundary.
        assert worker.seek(12 * FRAME_MS + 30)
        assert worker.get_position() == 12 * FRAME_MS
        assert worker._do_step_forward()
        assert worker.get_position() == 13 * FRAME_MS
    finally:
        worker._close_container()


def test_opening_a_file_while_playing_reports_the_stop(qt_app, clip, tmp_path):
    other = _make_video(tmp_path / "other.mp4")
    worker = _VideoDecodeWorker()
    states = []
    worker.playback_state_changed.connect(states.append)
    try:
        assert worker.load_video(clip)
        worker.play()
        assert states == [True]
        assert worker.load_video(other)
        assert states == [True, False]
    finally:
        worker._close_container()


def test_failed_open_publishes_that_nothing_is_loaded(qt_app, clip, tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"\0" * 4096)
    worker = _VideoDecodeWorker()
    seen = []
    worker.duration_changed.connect(lambda ms: seen.append(("duration", ms)))
    worker.position_changed.connect(lambda ms: seen.append(("position", ms)))
    worker.video_unloaded.connect(lambda: seen.append(("unloaded",)))
    try:
        assert worker.load_video(clip)
        seen.clear()
        logging.disable(logging.CRITICAL)
        try:
            assert worker.load_video(str(broken)) is False
        finally:
            logging.disable(logging.NOTSET)
        assert ("duration", 0) in seen
        assert ("position", 0) in seen
        assert ("unloaded",) in seen
        assert worker._video_path is None
        assert worker.get_duration() == 0
    finally:
        worker._close_container()


def test_end_of_stream_is_announced_after_the_last_frame(qt_app, clip):
    worker = _VideoDecodeWorker()
    ended = []
    worker.end_of_stream.connect(lambda: ended.append(True))
    try:
        assert worker.load_video(clip)
        worker.play()
        worker._playback_timer.stop()  # drive the ticks by hand
        while worker.is_playing():
            worker._on_playback_tick()
        assert ended == [True]
        assert worker.get_position() == (FRAMES - 1) * FRAME_MS
    finally:
        worker._close_container()


# -------------------------------------------------------------------- #
# Facade (worker on its own thread)
# -------------------------------------------------------------------- #


def test_facade_is_not_left_playing_after_opening_another_file(qt_app, clip, tmp_path):
    other = _make_video(tmp_path / "other.mp4")
    vm = VideoModel()
    try:
        assert vm.load_video(clip)
        vm.play()
        _pump(300)
        assert vm.is_playing()
        assert vm.load_video(other)
        _pump(200)
        # Previously stayed True: every toggle then sent pause() to a worker
        # that had already stopped, and playback could not be restarted.
        assert vm.is_playing() is False
    finally:
        vm.shutdown()


def test_facade_drops_the_old_video_after_a_failed_open(qt_app, clip, tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"\0" * 4096)
    vm = VideoModel()
    try:
        assert vm.load_video(clip)
        _pump(100)
        assert vm.get_duration() > 0
        logging.disable(logging.CRITICAL)
        try:
            assert vm.load_video(str(broken)) is False
            _pump(200)
        finally:
            logging.disable(logging.NOTSET)
        assert vm.get_duration() == 0
        assert vm._video_path is None
    finally:
        vm.shutdown()


# -------------------------------------------------------------------- #
# Timed session ending on the last frame
# -------------------------------------------------------------------- #


def _recording_controller(position, *, start=0, duration_s=3, frame_ms=33):
    ctrl = AnnotationController.__new__(AnnotationController)
    ctrl.logger = logging.getLogger("test.annotation_controller")
    ctrl._is_recording = True
    ctrl._recording_start_position = start
    ctrl._recording_duration = duration_s
    ctrl._frame_duration_ms = frame_ms
    ctrl._video_model = types.SimpleNamespace(get_position=lambda: position)
    completed = []
    ctrl._complete_recording = lambda: completed.append(True)
    return ctrl, completed


def test_session_ending_with_the_video_completes_at_end_of_stream():
    # 3 s session from 0 on a 3 s video: the last frame starts at ~2967 ms,
    # so the exact end position (3000 ms) is never reached.
    ctrl, completed = _recording_controller(position=2966)
    ctrl._on_end_of_stream()
    assert completed == [True]


def test_session_with_time_left_keeps_waiting_at_end_of_stream():
    # The video ends two seconds before the session: wait for Stop as before.
    ctrl, completed = _recording_controller(position=1000)
    ctrl._on_end_of_stream()
    assert completed == []


# -------------------------------------------------------------------- #
# Project annotation routing when the video fails to load
# -------------------------------------------------------------------- #


def _annotate_setup(load_ok):
    annotation = AnnotationController.__new__(AnnotationController)
    annotation.logger = logging.getLogger("test.annotation_controller")
    annotation._project_mode = True
    annotation._project_model = "project-model"
    annotation._current_video_id = "videos/a.mp4"
    annotation._auto_export_path = os.path.join("/p", "annotations", "a_annotations.csv")

    ctrl = ProjectController.__new__(ProjectController)
    ctrl.logger = logging.getLogger("test.project_controller")
    ctrl._annotation_controller = annotation
    ctrl._context_before_annotate = None
    ctrl._model = types.SimpleNamespace(
        is_project_open=lambda: True,
        get_project_path=lambda: "/p",
        get_annotation_relative_path_for_video=lambda _ref: os.path.join(
            "annotations", "b_annotations.csv"
        ),
        is_modified=lambda: False,
    )
    ctrl._video_controller = types.SimpleNamespace(
        load_video=lambda _path, preserve_project_context=False: load_ok
    )
    ctrl._view = types.SimpleNamespace(window=lambda: types.SimpleNamespace())
    return ctrl, annotation


def _routing(annotation):
    return (
        annotation._project_mode,
        annotation._project_model,
        annotation._current_video_id,
        annotation._auto_export_path,
    )


def test_failed_project_load_restores_the_previous_routing(monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    ctrl, annotation = _annotate_setup(load_ok=False)
    before = _routing(annotation)

    ctrl.annotate_video("/p/videos/b.mp4", "videos/b.mp4")

    assert _routing(annotation) == before


def test_project_load_failing_later_restores_the_previous_routing():
    ctrl, annotation = _annotate_setup(load_ok=True)
    before = _routing(annotation)

    ctrl.annotate_video("/p/videos/b.mp4", "videos/b.mp4")
    assert annotation._current_video_id == "videos/b.mp4"

    ctrl._on_video_load_finished("/p/videos/b.mp4", False)
    assert _routing(annotation) == before


def test_successful_project_load_keeps_the_new_routing():
    ctrl, annotation = _annotate_setup(load_ok=True)

    ctrl.annotate_video("/p/videos/b.mp4", "videos/b.mp4")
    ctrl._on_video_load_finished("/p/videos/b.mp4", True)

    assert annotation._current_video_id == "videos/b.mp4"
    assert annotation._auto_export_path == os.path.join("/p", "annotations", "b_annotations.csv")
    assert ctrl._context_before_annotate is None


# -------------------------------------------------------------------- #
# Position slider
# -------------------------------------------------------------------- #


def test_bare_click_on_the_slider_handle_does_not_seek(qt_app):
    view = VideoPlayerView()
    try:
        view.set_duration(300_000)
        view.set_position(101_966)  # slider sits on 339 -> 101 700 ms
        seeks = []
        view.seek_requested.connect(seeks.append)

        view.on_position_pressed()
        view.on_position_released()
        assert seeks == []

        view.on_position_pressed()
        view.position_slider.setValue(400)
        view.on_position_moved(400)
        view.on_position_released()
        assert seeks and seeks[-1] == 120_000
    finally:
        view.deleteLater()
