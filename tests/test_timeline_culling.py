"""Tests for timeline viewport culling (Phase 4, 1.3.x).

Covers the `_span_visible` culling predicate and a headless paint smoke test
that many events render without error through the culled paint path.
"""

from __future__ import annotations

import pytest

from views.timeline_view import TimelineView, TimelineCanvas
from models.annotation_model import BehaviorEvent


def test_span_visible_overlap():
    assert TimelineCanvas._span_visible(100, 200, 150, 300) is True


def test_span_visible_left_of_clip():
    assert TimelineCanvas._span_visible(0, 50, 150, 300) is False


def test_span_visible_right_of_clip():
    assert TimelineCanvas._span_visible(400, 500, 150, 300) is False


def test_span_visible_touching_edges():
    # x1 == clip_right and x2 == clip_left both count as visible (inclusive).
    assert TimelineCanvas._span_visible(300, 400, 150, 300) is True
    assert TimelineCanvas._span_visible(50, 150, 150, 300) is True


def test_span_visible_no_clip_draws_everything():
    assert TimelineCanvas._span_visible(0, 50, None, None) is True


def test_timeline_paints_many_events_without_error(qt_app):
    from PySide6.QtGui import QPixmap

    view = TimelineView()
    view.set_duration(60000)  # 60 s
    events = [
        BehaviorEvent("z", "Test behavior", i * 120, i * 120 + 100)
        for i in range(500)
    ]
    # Include a RecordingStart marker and an active (offset=None) event.
    events.insert(0, BehaviorEvent("R", "RecordingStart", 0, 0))
    events.append(BehaviorEvent("z", "Test behavior", 59000, None))
    view.set_events(events)

    canvas = view.timeline_canvas
    size = canvas.size()
    if size.width() > 0 and size.height() > 0:
        pm = QPixmap(size)
        canvas.render(pm)  # triggers paintEvent through the culled path
    view.deleteLater()
