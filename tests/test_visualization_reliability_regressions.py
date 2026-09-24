"""Regressions in the visualization and reliability tabs.

- point events (onset == offset) are drawn in the raster;
- "Export Individual Plots" writes each file's own figure (the redraw was
  debounced past the save, so every file got the same image);
- action maps with point behaviours ({"behavior": ..., "kind": "point"}) load;
- custom colormaps are saved to the per-user config folder and found there;
- the trailing "Note" row of a summary table is not read as an animal.
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QFileDialog

from controllers.visualization_controller import VisualizationController
from models.reliability_model import _parse_summary_table
from views.visualization_view import RasterPlotWidget


def _raster_widget(bar_height=12):
    widget = RasterPlotWidget.__new__(RasterPlotWidget)
    widget._bar_height = bar_height
    widget.logger = logging.getLogger("test")
    return widget


def _agg_axes(**figure_kwargs):
    """Axes on an explicit Agg canvas (independent of pyplot's backend)."""
    fig = Figure(**figure_kwargs)
    FigureCanvasAgg(fig)
    return fig, fig.add_subplot(111)


def _red_columns(fig):
    fig.canvas.draw()
    image = np.asarray(fig.canvas.buffer_rgba())
    red = (image[..., 0] > 200) & (image[..., 1] < 80) & (image[..., 2] < 80)
    return np.where(red.any(axis=0))[0]


def test_point_events_are_drawn(qt_app):
    widget = _raster_widget()
    fig, ax = _agg_axes(figsize=(6, 2), dpi=100)
    ax.set_xlim(0, 300)
    ax.set_ylim(-1, 1)
    events = pd.DataFrame({"Event": ["b"], "Onset": [100.0], "Offset": [100.0]})

    assert widget._add_event_segments(ax, events, 0.0, 0, [1, 0, 0], 1.0, 1) == 1

    columns = _red_columns(fig)
    assert columns.size > 0
    # The mark is centred on the onset.
    x_pixel = ax.transData.transform((100.0, 0.0))[0]
    assert columns.min() <= x_pixel <= columns.max()


def test_state_events_keep_their_exact_extent(qt_app):
    widget = _raster_widget()
    _fig, ax = _agg_axes()
    events = pd.DataFrame({"Event": ["b", "b"], "Onset": [1.0, 5.0], "Offset": [2.0, 5.0]})
    assert widget._add_event_segments(ax, events, 0.0, 0, [1, 0, 0], 1.0, 1) == 2
    state, point = ax.collections
    assert "butt" in str(state.get_capstyle()).lower()
    assert [list(map(tuple, seg)) for seg in state.get_segments()] == [[(1.0, 0), (2.0, 0)]]
    assert "projecting" in str(point.get_capstyle()).lower()


def _session(onset):
    return pd.DataFrame({
        "Event": ["RecordingStart", "Attack bites"],
        "Onset": [0.0, onset],
        "Offset": [0.0, onset + 20.0],
    })


def test_individual_exports_redraw_each_file_before_saving(qt_app, tmp_path, monkeypatch):
    widget = RasterPlotWidget()
    try:
        first = str(tmp_path / "m1_annotations.csv")
        second = str(tmp_path / "m2_annotations.csv")
        widget.set_data({first: _session(10.0), second: _session(200.0)})

        # Record which files the figure showed when it was last redrawn, and
        # what that was at each save. (Comparing the image bytes is not
        # enough: two saves of one unchanged figure can already differ.)
        drawn = {}
        real_update = widget.update_plot

        def update_plot():
            drawn["visible"] = sorted(
                path for path, shown in widget._file_visibility.items() if shown
            )
            real_update()

        saved_with = []
        real_save = widget._save_current_figure_to_path

        def save(path, file_format):
            saved_with.append(drawn.get("visible"))
            real_save(path, file_format)

        widget.update_plot = update_plot
        widget._save_current_figure_to_path = save
        target = tmp_path / "plots.png"
        monkeypatch.setattr(
            QFileDialog, "getSaveFileName",
            staticmethod(lambda *a, **k: (str(target), "PNG Files (*.png)")),
        )
        widget._show_timed_information = lambda *a, **k: None

        widget.export_individual_plots()

        assert saved_with == [[first], [second]]
        assert len(sorted(tmp_path.glob("plots_*.png"))) == 2
    finally:
        widget.deleteLater()


def test_action_map_with_point_behaviours_is_read(qt_app, tmp_path):
    path = tmp_path / "map.json"
    path.write_text(json.dumps({
        "o": "Attack bites",
        "p": {"behavior": "Freezing", "kind": "point"},
    }), encoding="utf-8")

    behaviors = RasterPlotWidget._read_action_map_behaviors(_raster_widget(), str(path))

    assert behaviors == ["Attack bites", "Freezing"]


class _FakeConfigPaths:
    def __init__(self, bundled, user):
        self.bundled = bundled
        self.user = user

    def get_config_directory(self):
        return self.bundled

    def get_user_config_directory(self):
        return self.user


def _visualization_controller(paths):
    ctrl = VisualizationController.__new__(VisualizationController)
    ctrl.logger = logging.getLogger("test.visualization_controller")
    ctrl._config_path_manager = paths
    ctrl._available_custom_colormaps = {}
    ctrl._view = None
    return ctrl


def test_custom_colormap_is_saved_per_user_and_found_again(qt_app, tmp_path):
    bundled = tmp_path / "bundle" / "configs"
    user = tmp_path / "user" / "configs"
    bundled.mkdir(parents=True)
    user.mkdir(parents=True)
    (bundled / "custom_shipped.json").write_text(json.dumps({"A": "#112233"}), encoding="utf-8")
    ctrl = _visualization_controller(_FakeConfigPaths(bundled, user))

    saved = ctrl.save_custom_colormap("mine", {"Attack bites": "#FF0000"})

    assert saved == "custom_mine"
    assert (user / "custom_mine.json").exists()
    assert not (bundled / "custom_mine.json").exists()
    assert set(ctrl._available_custom_colormaps) == {"custom_shipped", "custom_mine"}


def test_summary_note_row_is_not_an_animal(qt_app, tmp_path):
    path = tmp_path / "summary_table.csv"
    path.write_text(
        ",Duration,,Frequency,,\n"
        "animal_id,Chasing,,Chasing,,Total\n"
        "m1,1.00,,1,,1.00\n"
        "m2,2.00,,2,,2.00\n"
        "mean,1.50,,1.50,,1.50\n"
        "SEM,0.50,,0.50,,0.50\n"
        "\n"
        "Note,Approximate (overlap not considered; computed from summary-only input): Total\n",
        encoding="utf-8",
    )

    assert list(_parse_summary_table(str(path))["animal_id"]) == ["m1", "m2"]
