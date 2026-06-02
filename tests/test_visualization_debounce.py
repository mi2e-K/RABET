"""Tests for raster-plot redraw debounce (Phase 4, 1.3.x).

The debounce lives on RasterPlotWidget (the actual plotting widget that
VisualizationView wraps).
"""

from __future__ import annotations

import time

from PySide6.QtCore import QCoreApplication

from views.visualization_view import RasterPlotWidget


def _wait_until(predicate, timeout=1.0):
    deadline = time.time() + timeout
    while not predicate() and time.time() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.02)


def _stub_update(widget):
    """Replace update_plot with a counter; clear any timer from construction."""
    calls = {"n": 0}
    widget.update_plot = lambda: calls.__setitem__("n", calls["n"] + 1)
    timer = getattr(widget, "_plot_update_timer", None)
    if timer is not None:
        timer.stop()
    return calls


def test_schedule_plot_update_coalesces(qt_app):
    widget = RasterPlotWidget()
    try:
        calls = _stub_update(widget)
        widget._schedule_plot_update()
        widget._schedule_plot_update()
        widget._schedule_plot_update()
        assert calls["n"] == 0  # debounced, nothing yet
        _wait_until(lambda: calls["n"] > 0)
        assert calls["n"] == 1  # a single coalesced redraw
    finally:
        widget.deleteLater()


def test_flush_runs_pending_update_now(qt_app):
    widget = RasterPlotWidget()
    try:
        calls = _stub_update(widget)
        widget._schedule_plot_update()
        assert calls["n"] == 0
        widget._flush_pending_plot_update()
        assert calls["n"] == 1  # ran immediately, no waiting
    finally:
        widget.deleteLater()


def test_flush_without_pending_is_noop(qt_app):
    widget = RasterPlotWidget()
    try:
        calls = _stub_update(widget)
        widget._flush_pending_plot_update()  # nothing scheduled
        assert calls["n"] == 0
    finally:
        widget.deleteLater()
