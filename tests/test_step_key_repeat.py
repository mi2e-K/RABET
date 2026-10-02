"""Stepping backward: keyframe landings and key-repeat.

- The demuxer can land on a keyframe whose picture comes after the seek
  target (MPEG-4 Part 2 with B-frames, in MP4 or AVI). A step back then
  stopped at every keyframe; the seek now backs off and decodes again.
- A backward step is a seek, which on long-GOP video takes hundreds of
  milliseconds while key-repeat arrives every ~30 ms. Since 1.3.4 those
  requests were dropped, so holding Left rewound only a few dozen frames. They
  are now folded into one step that runs when the current one lands, and
  releasing the arrow key drops what is still pending.
"""

from __future__ import annotations

import logging
import types

import av
import numpy as np
import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from controllers.video_controller import VideoController
from models.video_model import _VideoDecodeWorker
from views.main_window import MainWindow


class _FakeModel:
    def __init__(self, fps):
        self.fps = fps
        self.calls = []

    def get_frame_rate(self):
        return self.fps

    def get_position(self):
        return 0

    def step_backward(self, time_ms):
        self.calls.append(("back", time_ms))

    def step_forward(self, time_ms):
        self.calls.append(("forward", time_ms))

    def step_backward_frames(self, frames):
        self.calls.append(("back frames", frames))

    def step_forward_frames(self, frames):
        self.calls.append(("forward frames", frames))


class _FakeTimer:
    def start(self, _ms):
        pass


def _controller(fps=30.0):
    vc = VideoController.__new__(VideoController)
    vc.logger = logging.getLogger("test.step_key_repeat")
    vc._video_model = _FakeModel(fps)
    # window() -> None: no annotation controller to notify.
    vc._view = types.SimpleNamespace(set_position=lambda _p: None, window=lambda: None)
    vc._stepping_in_progress = False
    vc._pending_step_frames = 0.0
    vc._video_initializing = False
    vc._frame_duration_ms = int(1000 / fps)
    vc._step_complete_timer = _FakeTimer()
    return vc


def test_requests_during_a_step_run_as_one_step_when_it_lands():
    vc = _controller()
    vc.handle_step_backward(100)        # starts at once
    for _ in range(5):                   # key-repeat while that seek runs
        assert vc.handle_step_backward(100) is True
    assert vc._video_model.calls == [("back", 100)]

    vc._on_step_finished(9900)
    assert vc._video_model.calls[-1] == ("back frames", 15)  # 5 x 100 ms at 30 fps
    assert vc._stepping_in_progress is True

    vc._on_step_finished(9400)
    assert len(vc._video_model.calls) == 2   # nothing left once it lands
    assert vc._stepping_in_progress is False


def test_frame_steps_count_one_frame_each_at_any_frame_rate():
    vc = _controller(fps=60.0)
    vc.handle_step_backward(17)
    for _ in range(4):
        vc.handle_step_backward(17)
    vc._on_step_finished(1000)
    # 4 x 17 ms would read as "one frame" (<= 50 ms) if passed on as ms.
    assert vc._video_model.calls[-1] == ("back frames", 4)


def test_the_other_direction_replaces_what_was_pending():
    vc = _controller()
    vc.handle_step_backward(100)
    vc.handle_step_backward(100)
    vc.handle_step_backward(100)
    vc.handle_step_forward(33)
    vc._on_step_finished(1000)
    assert vc._video_model.calls[-1] == ("forward frames", 1)


def test_cancelled_requests_do_not_run():
    vc = _controller()
    vc.handle_step_backward(100)
    vc.handle_step_backward(100)
    vc.cancel_pending_steps()
    vc._on_step_finished(1000)
    assert vc._video_model.calls == [("back", 100)]
    assert vc._stepping_in_progress is False


def _key(kind, key, auto_repeat):
    return QKeyEvent(kind, key, Qt.KeyboardModifier.NoModifier, "", auto_repeat)


def test_releasing_a_held_arrow_key_cancels_pending_steps(qt_app):
    win = MainWindow()
    try:
        cancels = []
        win.video_controller = types.SimpleNamespace(cancel_pending_steps=lambda: cancels.append(1))
        press, release = QEvent.Type.KeyPress, QEvent.Type.KeyRelease

        # Held: auto-repeat presses, then the real release.
        win.keyPressEvent(_key(press, Qt.Key.Key_Left, False))
        win.keyPressEvent(_key(press, Qt.Key.Key_Left, True))
        win.keyReleaseEvent(_key(release, Qt.Key.Key_Left, True))   # repeat pair: still held
        win.keyPressEvent(_key(press, Qt.Key.Key_Left, True))
        assert cancels == []
        win.keyReleaseEvent(_key(release, Qt.Key.Key_Left, False))
        assert cancels == [1]

        # Tapped: a request that arrived during a slow step still runs.
        win.keyPressEvent(_key(press, Qt.Key.Key_Right, False))
        win.keyReleaseEvent(_key(release, Qt.Key.Key_Right, False))
        assert cancels == [1]
    finally:
        win.set_close_guard(lambda: True)
        win.deleteLater()


FPS = 10


def _mpeg4_clip(path, fps=FPS):
    """MPEG-4 Part 2 with B-frames: its keyframes index the reordered time."""
    with av.open(str(path), "w") as out:
        stream = out.add_stream("mpeg4", rate=fps)
        stream.width, stream.height, stream.pix_fmt = 64, 48, "yuv420p"
        stream.codec_context.gop_size = 12
        stream.codec_context.options = {"bf": "2"}
        for index in range(40):
            image = np.full((48, 64, 3), (index * 6) % 256, dtype=np.uint8)
            for packet in stream.encode(av.VideoFrame.from_ndarray(image, format="rgb24")):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    return str(path)


@pytest.fixture
def clip(tmp_path):
    return _mpeg4_clip(tmp_path / "clip.mp4")


# 30 fps AVI has a 1/30 s time base: whole-ms positions of frames such as
# 298 (9933 ms) used to truncate to the previous frame, so steps skipped one.
@pytest.mark.parametrize("suffix, fps", [(".mp4", 10), (".avi", 10), (".avi", 30)])
def test_stepping_back_one_frame_at_a_time_visits_every_frame(qt_app, tmp_path, suffix, fps):
    worker = _VideoDecodeWorker()
    try:
        assert worker.load_video(_mpeg4_clip(tmp_path / f"clip{suffix}", fps=fps))
        worker.seek(round(30 * 1000 / fps))
        frames = [round(worker.get_position() * fps / 1000)]
        for _ in range(40):
            worker.step_backward(0)        # one frame
            frames.append(round(worker.get_position() * fps / 1000))
        end = frames[-1]
        assert end <= 1                    # the first frame (an AVI starts at 1)
        walked = frames[: frames.index(end) + 1]
        assert walked == list(range(30, end - 1, -1))   # every frame, one at a time
    finally:
        worker.close()


def test_worker_steps_an_exact_number_of_frames(qt_app, clip):
    worker = _VideoDecodeWorker()
    try:
        assert worker.load_video(clip)
        landed = []
        worker.step_finished.connect(landed.append)
        frame_ms = 1000 // FPS

        worker.seek(30 * frame_ms)
        worker.step_backward_frames(17)      # crosses keyframes at 24 and 12
        assert worker.get_position() == 13 * frame_ms
        worker.step_forward_frames(5)
        assert worker.get_position() == 18 * frame_ms
        assert landed == [13 * frame_ms, 18 * frame_ms]
    finally:
        worker.close()
