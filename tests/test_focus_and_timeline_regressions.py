"""Regressions where annotation keys were swallowed by a focused widget, and
where the timeline selection drifted to another event.

- clicking an action-map table cell arms the existing focus-reset timer (the
  click lands on the table's viewport, which the filter did not watch);
- the position slider does not take focus on click;
- Enter in the step-size box hands focus back to the main window;
- with the timeline canvas focused (after selecting an event), Left/Right
  still reach the main window instead of scrolling the timeline;
- the timeline selection follows the selected event when the list changes.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from models.annotation_model import BehaviorEvent
from views.main_window import MainWindow
from views.timeline_view import TimelineView
from views.video_player_view import VideoPlayerView


def test_clicking_a_table_cell_arms_the_focus_reset(qt_app):
    win = MainWindow()
    try:
        win.show()
        win.installGlobalFocusTracking()
        table = win.action_map_view.mappings_table
        assert not win._focus_reset_timer.isActive()

        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton)

        assert win._focus_reset_timer.isActive()
    finally:
        win.set_close_guard(lambda: True)
        win.deleteLater()


def test_position_slider_does_not_take_focus_on_click(qt_app):
    view = VideoPlayerView()
    try:
        assert view.position_slider.focusPolicy() == Qt.FocusPolicy.TabFocus
    finally:
        view.deleteLater()


def test_enter_in_the_step_size_box_returns_focus(qt_app):
    win = MainWindow()
    try:
        win.installGlobalFocusTracking()
        spin = win.video_player_view.step_size_spin
        calls = []
        win.resetFocus = lambda: calls.append("reset")

        spin.hasFocus = lambda: True  # Enter: the box still has focus
        spin.editingFinished.emit()
        spin.hasFocus = lambda: False  # focus-out: eventFilter's timer handles it
        spin.editingFinished.emit()

        assert calls == ["reset"]
    finally:
        win.set_close_guard(lambda: True)
        win.deleteLater()


class _KeyRecorder(QWidget):
    def __init__(self):
        super().__init__()
        self.keys = []

    def keyPressEvent(self, event):
        self.keys.append(event.key())


def test_arrow_keys_on_the_focused_timeline_reach_the_main_window(qt_app):
    host = _KeyRecorder()
    timeline = TimelineView()
    QVBoxLayout(host).addWidget(timeline)
    try:
        for key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(timeline.timeline_canvas, event)
        assert host.keys == [Qt.Key.Key_Left, Qt.Key.Key_Right]
    finally:
        host.deleteLater()


def _event(onset):
    return BehaviorEvent("z", "Behaviour z", onset, onset + 500)


def test_timeline_selection_follows_the_event_when_the_list_changes(qt_app):
    timeline = TimelineView()
    try:
        first, second, earlier = _event(1000), _event(2000), _event(500)
        timeline.set_events([first, second])
        timeline.select_event(1)

        timeline.set_events([earlier, first, second])
        assert timeline._selected_event == 2

        requested = []
        timeline.event_delete_requested.connect(requested.append)
        timeline.request_delete_selected_event()
        assert requested == [2]

        timeline.set_events([earlier, first])
        assert timeline._selected_event == -1
    finally:
        timeline.deleteLater()
