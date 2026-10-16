"""Time markers stay on the same seconds while the timeline scrolls.

Below 100 px/s the ruler labels every 2nd, 5th or 10th second. Viewport
culling (1.3.4) started that loop at the visible edge, so the labelled seconds
changed whenever the edge passed a whole second: during playback the ruler
jumped back a second at a time and did not move with the events.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QRect

from views.timeline_view import TimelineView


class _Painter:
    """Records the time labels the ruler draws, by marker position."""

    def __init__(self):
        self.labels = {}

    def setFont(self, _font):
        pass

    def setPen(self, _pen):
        pass

    def drawLine(self, *_args):
        pass

    def drawText(self, x, _y, text):
        minutes, seconds = (int(part) for part in text.split(":"))
        self.labels[x - 2] = minutes * 60 + seconds  # drawn 2 px right of the line


@pytest.mark.parametrize("zoom", [100, 50, 30, 20, 10])
def test_markers_keep_their_seconds_while_scrolling(qt_app, zoom):
    view = TimelineView()
    try:
        view._duration = 300_000
        view._zoom_level = zoom
        step = max(1, int(100 / zoom))
        width = 1000
        # The visible slice one playback frame (30 fps) at a time over 6 s.
        for frame in range(30 * 6):
            left = int((60 + frame / 30) * zoom)
            painter = _Painter()
            view.timeline_canvas._draw_time_markers(painter, QRect(left, 0, width, 60))

            visible = {x: s for x, s in painter.labels.items() if left <= x < left + width}
            expected = [s for s in range(0, 301, step) if left <= int(s * zoom) < left + width]
            assert sorted(visible.values()) == expected
            assert all(x == int(s * zoom) for x, s in visible.items())
    finally:
        view.deleteLater()
