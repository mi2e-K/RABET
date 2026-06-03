"""4-B: raster events drawn as one LineCollection per behavior row.

Replaces the per-event ax.plot loop. We assert that one collection (not N
Line2D) holds all events, that invalid/negative events are filtered exactly as
before, that geometry honours recording_start, and that the flat 'butt' cap is
preserved so the bars look identical.
"""

from __future__ import annotations

import logging

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402

from views.visualization_view import RasterPlotWidget  # noqa: E402


def _widget(bar_height=8):
    widget = RasterPlotWidget.__new__(RasterPlotWidget)
    widget._bar_height = bar_height
    widget.logger = logging.getLogger("test")
    return widget


def _events(onsets, offsets):
    return pd.DataFrame(
        {"Event": ["b"] * len(onsets), "Onset": onsets, "Offset": offsets}
    )


def test_one_collection_per_behavior(qt_app):
    widget = _widget()
    fig, ax = plt.subplots()
    df = _events([1.0, 5.0, 10.0], [2.0, 6.0, 12.0])
    n = widget._add_event_segments(ax, df, 0.0, 3, [0.1, 0.2, 0.3], 0.8, 10)
    assert n == 3
    # One collection holds every event; no per-event Line2D.
    assert len(ax.collections) == 1
    assert isinstance(ax.collections[0], LineCollection)
    assert len(ax.lines) == 0
    plt.close(fig)


def test_filters_negative_and_nonnumeric(qt_app):
    widget = _widget()
    fig, ax = plt.subplots()
    df = _events([-1.0, 5.0, "bad", 10.0], [0.0, 6.0, 7.0, 12.0])
    n = widget._add_event_segments(ax, df, 0.0, 0, [0, 0, 0], 1.0, 1)
    assert n == 2  # negative onset and non-numeric dropped
    plt.close(fig)


def test_empty_adds_nothing(qt_app):
    widget = _widget()
    fig, ax = plt.subplots()
    df = _events([], [])
    n = widget._add_event_segments(ax, df, 0.0, 0, [0, 0, 0], 1.0, 1)
    assert n == 0
    assert len(ax.collections) == 0
    plt.close(fig)


def test_segment_geometry_offsets_by_recording_start(qt_app):
    widget = _widget()
    fig, ax = plt.subplots()
    df = _events([10.0], [12.0])
    widget._add_event_segments(ax, df, 4.0, 7, [0, 0, 0], 1.0, 1)
    seg = ax.collections[0].get_segments()[0]
    # recording_start=4 subtracted; bar is horizontal at y=7.
    assert list(seg[0]) == [6.0, 7.0]
    assert list(seg[1]) == [8.0, 7.0]
    plt.close(fig)


def test_capstyle_is_butt(qt_app):
    widget = _widget()
    fig, ax = plt.subplots()
    df = _events([1.0], [2.0])
    widget._add_event_segments(ax, df, 0.0, 0, [0, 0, 0], 1.0, 1)
    assert "butt" in str(ax.collections[0].get_capstyle()).lower()
    plt.close(fig)
