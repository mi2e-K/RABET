"""Optional merge gap for the Analysis tab (off by default).

Events of the same behaviour separated by no more than the gap are merged into
one episode, from the first onset to the last offset, before the summary and
interval results are computed. The gap is measured as in Bout Analysis.
"""

from __future__ import annotations

import csv
import logging

import pytest

from controllers.analysis_controller import AnalysisController
from models.analysis_model import AnalysisModel
from models.reliability_model import _parse_summary_table
from views.analysis_view import AnalysisView
from views.main_window import MainWindow

EVENTS = """Event,Onset,Offset
RecordingStart,10.0000,10.0000
Self-grooming,12.0000,14.0000
Self-grooming,14.5000,16.0000
Self-grooming,20.0000,21.0000
Chasing,16.2000,17.0000
Attack bites,30.0000,30.0000
Attack bites,30.4000,30.4000
Attack bites,30.9000,30.9000
Attack bites,40.0000,40.0000
"""


def _csv(with_summary=False):
    text = (
        "Metadata\nRABET Version,1.4.3\nFormat Schema,v1\n"
        "Test Duration (seconds),60\n\n" + EVENTS
    )
    if with_summary:
        text += (
            "\nBehavior,Duration,Frequency\nSelf-grooming,4.50,3\n"
            "Chasing,0.80,1\nAttack bites,0.00,4\n"
        )
    return text


@pytest.fixture
def loaded(tmp_path):
    path = tmp_path / "m1_annotations.csv"
    path.write_text(_csv(), encoding="utf-8")
    model = AnalysisModel()
    assert model.load_files([str(path)])
    return model, str(path)


def _values(model, path):
    result = model.get_results()[path]
    return {
        "grooming": (result["Self-grooming_duration"], result["Self-grooming_count"]),
        "chasing": (result["Chasing_duration"], result["Chasing_count"]),
        "bites": (result["Attack bites_duration"], result["Attack bites_count"]),
        "latency": result["attack_latency"],
    }


def test_off_by_default_keeps_the_recorded_events(loaded):
    model, path = loaded
    assert model.get_merge_gap_settings() == (False, 1.0)
    assert _values(model, path) == {
        "grooming": (4.5, 3), "chasing": (pytest.approx(0.8), 1), "bites": (0.0, 4),
        "latency": 20.0,
    }


def test_merging_fills_short_gaps_within_each_behaviour(loaded):
    model, path = loaded
    model.set_merge_gap(True, 1.0)
    values = _values(model, path)
    # 12-14 and 14.5-16 merge into 12-16 (the 0.5 s gap counts); 20-21 stays.
    assert values["grooming"] == (pytest.approx(5.0), 2)
    # Another behaviour in between is not merged with grooming.
    assert values["chasing"] == (pytest.approx(0.8), 1)
    # Point events 30.0 / 30.4 / 30.9 become one 0.9 s episode; 40.0 stays.
    assert values["bites"] == (pytest.approx(0.9), 2)
    assert values["latency"] == 20.0       # first onset unchanged

    model.set_merge_gap(True, 0.4)         # a gap equal to the limit merges
    assert _values(model, path)["grooming"] == (pytest.approx(4.5), 3)
    assert _values(model, path)["bites"] == (pytest.approx(0.4), 3)

    model.set_merge_gap(False, 0.4)        # switching off gives the recorded values back
    assert _values(model, path)["grooming"] == (4.5, 3)
    assert _values(model, path)["bites"] == (0.0, 4)


def test_files_with_a_summary_section_are_merged_without_mismatch_warnings(tmp_path, caplog):
    path = tmp_path / "m2_annotations.csv"
    path.write_text(_csv(with_summary=True), encoding="utf-8")
    model = AnalysisModel()
    model.set_merge_gap(True, 1.0)
    with caplog.at_level(logging.WARNING, logger="models.analysis_model"):
        assert model.load_files([str(path)])
    assert _values(model, str(path))["grooming"] == (pytest.approx(5.0), 2)
    assert not [r for r in caplog.records if "Summary/raw mismatch" in r.getMessage()]


def test_intervals_use_merged_episodes(loaded):
    model, path = loaded
    model.set_merge_gap(True, 1.0)
    model.set_interval_analysis(True, 10)
    intervals = model.get_interval_results()[path]
    # Each merged episode counts once, in the interval where it starts:
    # 2 grooming episodes instead of 3 recorded events.
    counts = [interval.get("Self-grooming_count") for interval in intervals]
    assert sum(counts) == 2


def test_bout_and_transition_inputs_stay_recorded(loaded):
    model, path = loaded
    model.set_merge_gap(True, 1.0)
    assert len(model.get_events_by_behavior(path)["Self-grooming"]) == 3
    assert len([e for e in model.get_event_tuples(path) if e[0] == "Attack bites"]) == 4


def test_exports_record_the_merge_gap(loaded, tmp_path):
    model, path = loaded
    summary = tmp_path / "summary_table.csv"

    assert model.export_standard_summary_csv(str(summary))
    assert "Merge gap" not in summary.read_text(encoding="utf-8")

    model.set_merge_gap(True, 1.0)
    assert model.export_standard_summary_csv(str(summary))
    with open(summary, newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    notes = [row for row in rows if row and row[0] == "Note"]
    assert len(notes) == 1 and notes[0][1].startswith("Merge gap 1 s:")
    # The note is not read as an animal by the Summary-mode reliability parser.
    assert list(_parse_summary_table(str(summary))["animal_id"]) == ["m1"]

    model.set_interval_analysis(True, 10)
    intervals = tmp_path / "summary_intervals.csv"
    assert model.export_summary_csv(str(intervals))
    with open(intervals, newline="", encoding="utf-8") as handle:
        title = next(csv.reader(handle))[0]
    assert title.startswith("Interval analysis (10-second intervals); Merge gap 1 s:")


def test_view_controls_drive_the_model(qt_app, loaded):
    model, path = loaded
    view = AnalysisView()
    try:
        controller = AnalysisController(model, view)  # kept alive for its slots
        assert not view.merge_gap_spinner.isEnabled()
        view.merge_gap_spinner.setValue(1.0)
        view.merge_gap_checkbox.setChecked(True)
        assert view.merge_gap_spinner.isEnabled()
        assert model.get_merge_gap_settings() == (True, 1.0)
        assert _values(model, path)["grooming"] == (pytest.approx(5.0), 2)
        view.merge_gap_checkbox.setChecked(False)
        assert _values(model, path)["grooming"] == (4.5, 3)
        assert controller is not None
    finally:
        view.deleteLater()


class _FakeConfig:
    def __init__(self, sections):
        self._sections = sections
        self.saved = {}

    def get(self, section, key=None, default=None):
        values = self._sections.get(section, {})
        return values if key is None else values.get(key, default)

    def set(self, section, key, value):
        self.saved[(section, key)] = value

    def save_config(self):
        pass


def test_merge_gap_setting_is_restored_and_saved(qt_app):
    win = MainWindow()
    try:
        applied = []
        win.analysis_view.merge_gap_changed.connect(lambda *args: applied.append(args))
        config = _FakeConfig({"analysis": {"merge_gap_enabled": True, "merge_gap_seconds": 0.5}})
        win.set_config_manager(config)
        assert win.analysis_view.get_merge_gap_settings() == (True, 0.5)
        assert applied == [(True, 0.5)]    # reaches the model, not only the controls

        win.analysis_view.merge_gap_spinner.setValue(2.0)
        win._persist_settings()
        assert config.saved[("analysis", "merge_gap_enabled")] is True
        assert config.saved[("analysis", "merge_gap_seconds")] == 2.0
    finally:
        win.set_close_guard(lambda: True)
        win.deleteLater()
