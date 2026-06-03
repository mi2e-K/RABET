"""vis Files list: a click anywhere on a row toggles its checkbox (not only the
indicator), while dragging still reorders (ReorderableListWidget)."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QListWidgetItem

from views.visualization_view import ReorderableListWidget


def _checkable_item(text="video1.mp4"):
    item = QListWidgetItem(text)
    item.setFlags(
        item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
    )
    item.setCheckState(Qt.CheckState.Unchecked)
    return item


def _list_with_item(qt_app):
    widget = ReorderableListWidget()
    item = _checkable_item()
    widget.addItem(item)
    widget.resize(240, 120)
    widget.show()
    QTest.qWait(10)
    return widget, item


def test_label_click_toggles_checkbox(qt_app):
    widget, item = _list_with_item(qt_app)
    try:
        rect = widget.visualItemRect(item)
        # Right of the checkbox indicator = the name/label area.
        label_point = QPoint(
            rect.center().x() + rect.width() // 4, rect.center().y()
        )
        QTest.mouseClick(
            widget.viewport(), Qt.MouseButton.LeftButton, pos=label_point
        )
        assert item.checkState() == Qt.CheckState.Checked
        QTest.mouseClick(
            widget.viewport(), Qt.MouseButton.LeftButton, pos=label_point
        )
        assert item.checkState() == Qt.CheckState.Unchecked
    finally:
        widget.deleteLater()


def test_checkbox_indicator_click_toggles_once(qt_app):
    widget, item = _list_with_item(qt_app)
    try:
        rect = widget.visualItemRect(item)
        cb_point = QPoint(rect.left() + 8, rect.center().y())
        QTest.mouseClick(
            widget.viewport(), Qt.MouseButton.LeftButton, pos=cb_point
        )
        # Exactly one toggle - no double-fire from base handler + manual toggle.
        assert item.checkState() == Qt.CheckState.Checked
    finally:
        widget.deleteLater()


def test_drag_does_not_toggle(qt_app):
    widget, item = _list_with_item(qt_app)
    try:
        rect = widget.visualItemRect(item)
        p1 = QPoint(rect.center().x(), rect.center().y())
        p2 = QPoint(p1.x() + 80, p1.y())  # same row, beyond drag threshold
        QTest.mousePress(widget.viewport(), Qt.MouseButton.LeftButton, pos=p1)
        QTest.mouseRelease(widget.viewport(), Qt.MouseButton.LeftButton, pos=p2)
        assert item.checkState() == Qt.CheckState.Unchecked  # drag, not a click
    finally:
        widget.deleteLater()
