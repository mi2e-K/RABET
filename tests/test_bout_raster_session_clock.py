"""The bout raster is drawn on the session clock (RecordingStart = 0).

Rows used video time, so animals whose sessions began at different points
of their videos did not line up. Export Bouts keeps the video-time columns
and adds session-relative ones.
"""

from __future__ import annotations

import csv

import pytest

from controllers.analysis_controller import AnalysisController
from models.analysis_model import AnalysisModel
from models.bout_analysis import compute_bouts

_BITES = [(31.0, 31.25), (31.5, 31.75), (40.0, 40.25), (40.5, 40.75), (41.0, 41.5)]
_EBB = {"Attack bites": _BITES}
_BEH = ["Attack bites"]
_BCI = 1.0


def _dialog(per_file):
    from views.bout_analysis_dialog import BoutAnalysisDialog

    dialog = BoutAnalysisDialog(None, per_file, _BEH)
    dialog.bci_spin.setValue(_BCI)
    return dialog


def _drawn(dialog):
    (animal_id, bouts), = dialog.raster_canvas._data
    return animal_id, [(bt.start, bt.end, bt.n_events) for bt in bouts], dialog.raster_canvas._max_t


def _exported(dialog, tmp_path, monkeypatch):
    import views.bout_analysis_dialog as mod

    target = tmp_path / "bouts.csv"
    monkeypatch.setattr(
        mod.QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    monkeypatch.setattr(mod.QMessageBox, "information", lambda *a, **k: None)
    dialog._export_raster()
    with open(target, newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle))


def test_session_at_video_start_draws_as_before(qt_app, tmp_path, monkeypatch):
    video_time = [(bt.start, bt.end, bt.n_events) for bt in compute_bouts(_BITES, _BCI)]
    legacy = _dialog([("a", _EBB, 300.0)])  # three-item entries still work
    assert _drawn(legacy) == ("a", video_time, 41.5)
    dialog = _dialog([("a", _EBB, 300.0, 0.0)])
    assert _drawn(dialog) == ("a", video_time, 41.5)

    rows = _exported(dialog, tmp_path, monkeypatch)
    assert rows[0][:8] == ["animal_id", "behavior", "bci_s", "bout_index",
                           "start_s", "end_s", "n_events", "duration_s"]
    assert rows[1][:8] == ["a", "Attack bites", "1.00", "1", "31.0000", "31.7500", "2", "0.7500"]
    assert rows[1][8:] == ["31.0000", "31.7500"]


def test_late_session_is_drawn_from_its_recording_start(qt_app, tmp_path, monkeypatch):
    dialog = _dialog([("a", _EBB, 300.0, 30.0)])

    animal_id, drawn, max_t = _drawn(dialog)
    assert drawn == [(1.0, 1.75, 2), (10.0, 11.5, 3)]
    assert max_t == pytest.approx(11.5)

    rows = _exported(dialog, tmp_path, monkeypatch)
    assert rows[0][8:] == ["start_from_recording_s", "end_from_recording_s"]
    assert [row[4:6] + row[8:] for row in rows[1:]] == [
        ["31.0000", "31.7500", "1.0000", "1.7500"],
        ["40.0000", "41.5000", "10.0000", "11.5000"],
    ]


def test_raster_axis_is_titled_with_the_session_clock(qt_app, monkeypatch):
    import views.bout_raster_dialog as raster_module

    texts = []

    class _SpyPainter(raster_module.QPainter):
        def drawText(self, *args):
            texts.append(args[-1])
            return super().drawText(*args)

    monkeypatch.setattr(raster_module, "QPainter", _SpyPainter)
    dialog = _dialog([("a", _EBB, 300.0, 30.0)])
    dialog.raster_canvas.resize(600, 200)
    dialog.raster_canvas.grab()
    assert "Time from recording start (s)" in texts


def _csv(recording_start):
    lines = [
        "Metadata", "RABET Version,1.4.0", "Format Schema,v1",
        "Test Duration (seconds),300", "", "Event,Onset,Offset",
        f"RecordingStart,{recording_start:.4f},{recording_start:.4f}",
    ]
    lines += [f"Attack bites,{on:.4f},{off:.4f}" for on, off in _BITES]
    lines += ["", "Behavior,Duration,Frequency", "Attack bites,1.25,5", ""]
    return "\n".join(lines)


def test_controller_passes_each_files_recording_start(qt_app, monkeypatch, tmp_path):
    paths = []
    for name, start in (("1_zero_annotations.csv", 0.0), ("2_late_annotations.csv", 30.0)):
        path = tmp_path / name
        path.write_text(_csv(start), encoding="utf-8")
        paths.append(str(path))
    model = AnalysisModel()
    assert model.load_files(paths) is True

    captured = {}

    class _FakeDialog:
        def __init__(self, parent, per_file, ordered):
            captured["per_file"] = per_file

        def exec(self):
            return 0

    import views.bout_analysis_dialog as dialog_module

    monkeypatch.setattr(dialog_module, "BoutAnalysisDialog", _FakeDialog)
    ctrl = AnalysisController.__new__(AnalysisController)
    ctrl._model = model
    ctrl._view = None
    ctrl.on_bout_analysis_requested()

    starts = {entry[0]: entry[3] for entry in captured["per_file"]}
    assert starts == {"1_zero": 0.0, "2_late": 30.0}
    # Events stay on video time; only the raster and new columns shift.
    assert captured["per_file"][1][1]["Attack bites"][0] == (31.0, 31.25)
