"""Integration: AnalysisModel event accessors + BoutAnalysisDialog wiring.

Uses a small synthetic RABET annotation CSV (no dependency on the private
sample data, so this runs in CI).
"""

from __future__ import annotations

import pytest

from models.analysis_model import AnalysisModel

_CSV = """Metadata
RABET Version,1.4.0
Format Schema,v1
Test Duration (seconds),60

Event,Onset,Offset
RecordingStart,0.0000,0.0000
Attack bites,10.0000,10.1000
Attack bites,10.3000,10.4000
Attack bites,10.6000,10.7000
Attack bites,30.0000,30.1000
Social contact,5.0000,6.0000

Behavior,Duration,Frequency
Attack bites,0.40,4
Social contact,1.00,1
"""


@pytest.fixture
def loaded_model(tmp_path):
    path = tmp_path / "1175_test_annotations.csv"
    path.write_text(_CSV, encoding="utf-8")
    model = AnalysisModel()
    assert model.load_files([str(path)]) is True
    return model, str(path)


def test_get_events_by_behavior_excludes_recording_start(loaded_model):
    model, path = loaded_model
    events = model.get_events_by_behavior(path)
    assert "RecordingStart" not in events
    assert len(events["Attack bites"]) == 4
    onset, offset = events["Attack bites"][0]
    assert onset == pytest.approx(10.0)
    assert offset == pytest.approx(10.1)
    assert model.get_file_test_duration(path) == pytest.approx(60.0)


def test_bout_stats_from_loaded_model(loaded_model):
    from models.bout_analysis import compute_bout_stats

    model, path = loaded_model
    events = model.get_events_by_behavior(path)
    stats = compute_bout_stats(
        events["Attack bites"], 1.0, behavior="Attack bites",
        session_duration=model.get_file_test_duration(path),
    )
    assert stats.n_events == 4
    # Three within 1 s of each other + one far away = 2 bouts.
    assert stats.n_bouts == 2
    assert stats.events_per_bout_mean == pytest.approx(2.0)


def test_dialog_constructs_and_lists_rows(qt_app, loaded_model):
    from PySide6.QtCore import Qt

    from views.bout_analysis_dialog import BoutAnalysisDialog

    model, path = loaded_model
    events = model.get_events_by_behavior(path)
    per_file = [("1175_test", events, model.get_file_test_duration(path))]
    dialog = BoutAnalysisDialog(None, per_file, ["Attack bites", "Social contact"])
    # Only the first behaviour is checked by default -> one row.
    assert dialog.results_table.rowCount() == 1
    # Checking the second behaviour recomputes and adds its row.
    dialog.behavior_list.item(1).setCheckState(Qt.CheckState.Checked)
    assert dialog.results_table.rowCount() == 2
