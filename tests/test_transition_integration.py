"""Integration: AnalysisModel.get_event_tuples + TransitionAnalysisDialog."""

from __future__ import annotations

import pytest

from models.analysis_model import AnalysisModel

_CSV = """Metadata
RABET Version,1.4.0
Format Schema,v1
Test Duration (seconds),60

Event,Onset,Offset
RecordingStart,0.0000,0.0000
Social contact,1.0000,1.5000
Attack bites,1.7000,1.8000
Attack bites,2.0000,2.1000
Social contact,3.0000,3.5000
Attack bites,3.7000,3.8000

Behavior,Duration,Frequency
Attack bites,0.30,3
Social contact,1.00,2
"""


@pytest.fixture
def loaded_model(tmp_path):
    path = tmp_path / "1175_test_annotations.csv"
    path.write_text(_CSV, encoding="utf-8")
    model = AnalysisModel()
    assert model.load_files([str(path)]) is True
    return model, str(path)


def test_get_event_tuples_ordered_excludes_recording_start(loaded_model):
    model, path = loaded_model
    events = model.get_event_tuples(path)
    assert all(behavior != "RecordingStart" for behavior, _, _ in events)
    assert [b for b, _, _ in events] == [
        "Social contact", "Attack bites", "Attack bites",
        "Social contact", "Attack bites",
    ]
    # Sorted by onset.
    onsets = [on for _, on, _ in events]
    assert onsets == sorted(onsets)


def test_transition_dialog_constructs(qt_app, loaded_model):
    from views.transition_analysis_dialog import TransitionAnalysisDialog

    model, path = loaded_model
    events = model.get_event_tuples(path)
    per_file = [("1175_test", events)]
    dialog = TransitionAnalysisDialog(None, per_file, ["Attack bites", "Social contact"])
    # 2x2 matrix rendered.
    assert dialog.matrix_table.rowCount() == 2
    assert dialog.matrix_table.columnCount() == 2
    # Raw mode keeps the Attack->Attack self-transition (onsets 1.7->2.0).
    assert dialog._result.counts[0, 0] == 1.0
