"""The timeline Update Rate skips whole frames.

With an Update Rate above 1 the canvas was scrolled on every position but
repainted only on some: what was already drawn (REC start, markers, finished
events) moved on while the playhead and the event being recorded waited for
the next repaint. The rate was also counted twice per position, so a rate of
2 never repainted. Now the canvas is repainted and scrolled together, once
every Update Rate positions, and a position that is not followed by another
(a seek or frame step while paused) is still shown.
"""

from __future__ import annotations

import logging

from PySide6.QtTest import QTest

from controllers.annotation_controller import AnnotationController
from views.timeline_view import TimelineView


def _timeline(rate):
    view = TimelineView()
    view.resize(800, 120)
    view.show()
    QTest.qWait(10)
    view.set_duration(300_000)
    view.update_freq_spin.setValue(rate)
    repaints = []
    view.timeline_canvas.update = lambda *args: repaints.append(view._current_position)
    return view, repaints


def _scroll(view):
    return view.timeline_area.horizontalScrollBar().value()


def test_repaint_and_scroll_happen_on_the_same_positions(qt_app):
    view, repaints = _timeline(3)
    try:
        scrolled = []
        for frame in range(9):
            before = _scroll(view)
            view.set_position(60_000 + frame * 33)
            if _scroll(view) != before:
                scrolled.append(view._current_position)
        assert repaints == [60_066, 60_165, 60_264]   # every 3rd position
        assert scrolled == repaints
    finally:
        view.deleteLater()


def test_a_last_position_is_shown_after_updates_stop(qt_app):
    view, repaints = _timeline(3)
    try:
        view.set_position(60_000)          # e.g. a seek while paused
        assert repaints == []
        QTest.qWait(200)
        assert repaints == [60_000]
        target = int(60_000 / 1000 * view._zoom_level) - view.timeline_area.viewport().width() // 2
        assert _scroll(view) == target
    finally:
        view.deleteLater()


class _Video:
    def is_playing(self):
        return True

    def get_position(self):
        return 0


class _Timer:
    def start(self, *_args):
        pass


def test_playback_counts_each_position_once(qt_app):
    view, repaints = _timeline(2)
    try:
        ctrl = AnnotationController.__new__(AnnotationController)
        ctrl.logger = logging.getLogger("test.timeline_update_rate")
        ctrl._timeline_view = view
        ctrl._video_model = _Video()
        ctrl._is_recording = False
        ctrl._is_recording_paused = False
        ctrl._last_position = 0
        ctrl._frame_duration_ms = 33
        ctrl._preserve_annotations_on_rewind = False
        ctrl._ensure_visible_timer = _Timer()

        for frame in range(6):
            ctrl.on_position_changed(60_000 + frame * 33)
        assert repaints == [60_033, 60_099, 60_165]   # every 2nd, not never
    finally:
        view.deleteLater()
