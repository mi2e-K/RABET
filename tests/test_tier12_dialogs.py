"""Construction/compute smoke tests for the 1.4.0 Tier 1-2 analysis UI.

Bout raster and antecedent-window predictability are integrated as tabs of the
Bout Analysis and Transition Analysis dialogs respectively (1.4.0)."""

from __future__ import annotations

_EV = [
    ("Social contact", 1.0, 1.5), ("Attack bites", 1.7, 1.8), ("Attack bites", 2.0, 2.1),
    ("Sideways threats", 3.0, 3.2), ("Attack bites", 3.5, 3.6), ("Attack bites", 3.8, 3.9),
]
_EBB = {
    "Attack bites": [(1.7, 1.8), (2.0, 2.1), (3.5, 3.6), (3.8, 3.9)],
    "Social contact": [(1.0, 1.5)], "Sideways threats": [(3.0, 3.2)],
}
_BEH = ["Attack bites", "Social contact", "Sideways threats"]


def test_transition_dialog_bout_level_or_and_predictability_tab(qt_app):
    from views.transition_analysis_dialog import TransitionAnalysisDialog
    d = TransitionAnalysisDialog(None, [("a", _EV)], _BEH)
    # Three tabs: Matrix + Heatmap + Predictability.
    assert d.tab_widget.count() == 3
    assert [d.tab_widget.tabText(i) for i in range(3)] == ["Matrix", "Heatmap", "Predictability"]
    d.level_combo.setCurrentIndex(1)   # bout level -> bout_bci set
    d.metric_combo.setCurrentIndex(2)  # odds ratio
    assert d._result.bout_bci is not None
    assert d.matrix_table.rowCount() == len(_BEH)
    assert d.profile_table.rowCount() == len(_BEH)
    # Embedded predictability panel computed on construction (with its chart).
    assert d.pred_panel.table.rowCount() == 1
    assert d.pred_panel.chart is not None
    assert d.pred_panel._rows[0]["n_targets"] == 4
    assert d.pred_panel.lag_label.text()


def test_bout_dialog_table_and_raster_tabs(qt_app):
    from views.bout_analysis_dialog import BoutAnalysisDialog
    d = BoutAnalysisDialog(None, [("a", _EBB, 300.0)], _BEH)
    assert d.tab_widget.count() == 2  # Table + Raster
    # Table tab: only first behaviour checked by default -> one row.
    assert d.results_table.rowCount() == 1
    # Raster tab: bouts computed for the selected behaviour.
    data, max_t = d._raster_bouts()
    assert len(data) == 1
    assert max_t >= 3.9


def test_figure_export_path_normalisation():
    from utils.figure_export import normalise_figure_export_path

    assert normalise_figure_export_path(
        "bout_raster", "SVG Files (*.svg)"
    ) == ("bout_raster.svg", "svg")
    assert normalise_figure_export_path(
        "transition_heatmap.pdf", "PNG Files (*.png)"
    ) == ("transition_heatmap.pdf", "pdf")


def test_bout_raster_figure_export_uses_dpi_and_format(monkeypatch, tmp_path, qt_app):
    from views import bout_analysis_dialog as mod

    dialog = mod.BoutAnalysisDialog(None, [("a", _EBB, 300.0)], _BEH)
    target = tmp_path / "bout_raster"
    calls = {}

    monkeypatch.setattr(
        mod.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(target), "SVG Files (*.svg)"),
    )
    monkeypatch.setattr(
        mod,
        "save_qwidget_figure",
        lambda widget, path, fmt, dpi: calls.update(
            widget=widget,
            path=path,
            fmt=fmt,
            dpi=dpi,
        ),
    )
    monkeypatch.setattr(
        mod,
        "show_export_complete",
        lambda parent, path, timeout_ms=1000: calls.update(
            complete_path=path,
            timeout_ms=timeout_ms,
        ),
    )

    dialog.raster_dpi_spin.setValue(450)
    dialog._export_raster_figure()

    assert calls["widget"] is dialog.raster_canvas
    assert calls["path"] == str(target) + ".svg"
    assert calls["fmt"] == "svg"
    assert calls["dpi"] == 450
    assert calls["complete_path"] == str(target) + ".svg"
    assert calls["timeout_ms"] == 1000


def test_transition_heatmap_figure_export_uses_dpi_and_format(monkeypatch, tmp_path, qt_app):
    from views import transition_analysis_dialog as mod

    dialog = mod.TransitionAnalysisDialog(None, [("a", _EV)], _BEH)
    target = tmp_path / "transition_heatmap"
    calls = {}

    monkeypatch.setattr(
        mod.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(target), "PDF Files (*.pdf)"),
    )
    monkeypatch.setattr(
        mod,
        "save_matplotlib_figure",
        lambda figure, path, fmt, dpi: calls.update(
            figure=figure,
            path=path,
            fmt=fmt,
            dpi=dpi,
        ),
    )
    monkeypatch.setattr(
        mod,
        "show_export_complete",
        lambda parent, path, timeout_ms=1000: calls.update(
            complete_path=path,
            timeout_ms=timeout_ms,
        ),
    )

    dialog.heatmap_dpi_spin.setValue(600)
    dialog._export_heatmap_figure()

    assert calls["figure"] is dialog.heatmap_chart.figure
    assert calls["path"] == str(target) + ".pdf"
    assert calls["fmt"] == "pdf"
    assert calls["dpi"] == 600
    assert calls["complete_path"] == str(target) + ".pdf"
    assert calls["timeout_ms"] == 1000


def test_predictability_figure_export_uses_dpi_and_format(monkeypatch, tmp_path, qt_app):
    from views import predictability_dialog as mod

    panel = mod.PredictabilityPanel(None, [("a", _EV)], _BEH)
    target = tmp_path / "predictability.svg"
    calls = {}

    monkeypatch.setattr(
        mod.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(target), "PNG Files (*.png)"),
    )
    monkeypatch.setattr(
        mod,
        "save_matplotlib_figure",
        lambda figure, path, fmt, dpi: calls.update(
            figure=figure,
            path=path,
            fmt=fmt,
            dpi=dpi,
        ),
    )
    monkeypatch.setattr(
        mod,
        "show_export_complete",
        lambda parent, path, timeout_ms=1000: calls.update(
            complete_path=path,
            timeout_ms=timeout_ms,
        ),
    )

    panel.figure_dpi_spin.setValue(250)
    panel._export_figure()

    assert calls["figure"] is panel.chart.figure
    assert calls["path"] == str(target)
    assert calls["fmt"] == "svg"
    assert calls["dpi"] == 250
    assert calls["complete_path"] == str(target)
    assert calls["timeout_ms"] == 1000
