"""A-1: VideoModel facade over the decode worker thread.

These tests exercise the facade wiring without real decoding: the worker's
signals are emitted directly and we assert the facade relays them and refreshes
its UI-side cache, and that the worker thread is started/stopped correctly.
"""

from __future__ import annotations

import logging
import time

from models.video_model import VideoModel, _VideoDecodeWorker


def test_facade_starts_worker_on_its_own_thread(qt_app):
    vm = VideoModel()
    try:
        assert isinstance(vm._worker, _VideoDecodeWorker)
        assert vm._thread.isRunning()
        # The worker's thread affinity is the worker thread, not the UI thread.
        assert vm._worker.thread() is vm._thread
    finally:
        vm.shutdown()


def test_facade_relays_signals_and_caches_state(qt_app):
    vm = VideoModel()
    try:
        seen = {}
        vm.duration_changed.connect(lambda v: seen.__setitem__("dur", v))
        vm.position_changed.connect(lambda v: seen.__setitem__("pos", v))
        vm.playback_state_changed.connect(lambda v: seen.__setitem__("play", v))
        vm.video_loaded.connect(lambda v: seen.__setitem__("path", v))

        vm._worker.duration_changed.emit(5000)
        vm._worker.position_changed.emit(1200)
        vm._worker.playback_state_changed.emit(True)
        vm._worker.video_loaded.emit("clip.mp4")
        vm._worker.frame_rate_changed.emit(29.97, 33)
        qt_app.processEvents()

        # Synchronous reads come from the refreshed cache.
        assert vm.get_duration() == 5000
        assert vm.get_position() == 1200
        assert vm.is_playing() is True
        assert vm.get_frame_rate() == 29.97
        assert vm._frame_duration_ms == 33
        assert vm._video_path == "clip.mp4"
        # And the facade re-emits to its own listeners.
        assert seen == {"dur": 5000, "pos": 1200, "play": True, "path": "clip.mp4"}
    finally:
        vm.shutdown()


def test_seek_caches_last_position_without_blocking(qt_app):
    vm = VideoModel()
    try:
        assert vm.seek(7480) is True
        assert vm._last_seek_position == 7480
    finally:
        vm.shutdown()


def test_close_keeps_thread_alive(qt_app):
    vm = VideoModel()
    try:
        vm.close()
        qt_app.processEvents()
        # close() only tears down the container; the worker thread stays up so
        # a subsequent load_video reuses it.
        assert vm._thread.isRunning()
    finally:
        vm.shutdown()


def test_shutdown_stops_thread(qt_app):
    vm = VideoModel()
    assert vm._thread.isRunning()
    vm.shutdown()
    assert not vm._thread.isRunning()


def test_load_video_returns_bool_via_blocking_invoke(qt_app, tmp_path):
    vm = VideoModel()
    try:
        # A nonexistent file makes the worker return False, but the point is
        # that the BlockingQueued invoke with result=bool resolves at all: the
        # worker's @Slot must declare result=bool, otherwise this raises
        # "QMetaMethod invocation failed" (the bug seen on first device test).
        result = vm.load_video(str(tmp_path / "nope.mp4"))
        assert result is False
    finally:
        vm.shutdown()


def test_drain_seek_coalesces_to_latest(qt_app):
    # Worker-level: rapid pings collapse to the newest pending target, and a
    # target already served is skipped (PR-V3 seek coalescing).
    worker = _VideoDecodeWorker()
    served = []
    worker.seek = lambda ms: served.append(ms) or True
    worker._pending_seek_ms = 30
    worker._drain_seek()          # serves 30
    worker._drain_seek()          # same target -> skipped
    worker._pending_seek_ms = 50
    worker._drain_seek()          # serves 50
    assert served == [30, 50]


def test_decode_timing_logs_are_opt_in(monkeypatch, caplog, qt_app):
    monkeypatch.delenv("RABET_VIDEO_TIMING", raising=False)
    worker = _VideoDecodeWorker()
    with caplog.at_level(logging.INFO):
        worker._log_decode_timing("seek", time.monotonic())
    assert "[video-timing]" not in caplog.text

    caplog.clear()
    monkeypatch.setenv("RABET_VIDEO_TIMING", "1")
    worker = _VideoDecodeWorker()
    with caplog.at_level(logging.INFO):
        worker._log_decode_timing("seek", time.monotonic())
    assert "[video-timing] seek" in caplog.text


def test_facade_seek_publishes_latest_target(qt_app):
    vm = VideoModel()
    try:
        vm.seek(7480)
        # The facade publishes to the worker's pending slot (drained later) and
        # caches the position for synchronous reads.
        assert vm._worker._pending_seek_ms == 7480
        assert vm._last_seek_position == 7480
    finally:
        vm.shutdown()


def test_step_always_emits_step_finished(qt_app):
    # step_finished must fire on every step (the worker emits it in a finally),
    # even with no container loaded, so the controller's step never gets stuck
    # waiting for a completion that never comes (A-1, Codex Medium).
    vm = VideoModel()
    try:
        seen = []
        vm.step_finished.connect(lambda pos: seen.append(pos))
        vm._worker.step_forward(0)
        vm._worker.step_backward(0)
        assert len(seen) == 2
    finally:
        vm.shutdown()
