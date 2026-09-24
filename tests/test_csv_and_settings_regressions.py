"""Regressions in CSV import/export and in restored/loaded settings.

- the metadata Test Duration survives an import/export round trip (it was
  skipped on import, so re-exports wrote 0 or a stale value);
- timestamps round to the nearest millisecond, integers still read as the
  legacy millisecond format, and a BOM no longer breaks header-first files;
- a saved recording duration with 0 minutes is restored as saved;
- loading a metrics configuration enforces the unique-name invariant;
- the metrics dialogs keep behaviour names they do not list themselves and
  names that contain commas.
"""

from __future__ import annotations

import json

from models.action_map_model import ActionMapModel
from models.analysis_config import AnalysisMetricsConfig
from models.annotation_model import AnnotationModel
from views.main_window import MainWindow
from views.metrics_config_dialog import (
    LatencyMetricDialog,
    MetricsConfigDialog,
    TotalTimeMetricDialog,
)

RABET_CSV = (
    "Metadata\n"
    "RABET Version,1.4.2\n"
    "Format Schema,1\n"
    "Test Duration (seconds),300\n"
    "\n"
    "Event,Onset,Offset\n"
    "RecordingStart,10.0000,10.0000\n"
    "Attack bites,12.0000,13.0010\n"
    "\n"
    "Behavior,Duration,Frequency\n"
    "Attack bites,1.00,1\n"
)


def _model():
    return AnnotationModel(ActionMapModel())


def _test_duration_row(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("Test Duration"):
            return line
    return None


def test_test_duration_survives_import_and_export(qt_app, tmp_path):
    source = tmp_path / "in.csv"
    source.write_text(RABET_CSV, encoding="utf-8")
    model = _model()
    model.set_test_duration(600)  # left over from an earlier session

    assert model.import_from_csv(str(source))
    out = tmp_path / "out.csv"
    assert model.export_to_csv(str(out))

    assert _test_duration_row(out) == "Test Duration (seconds),300"


def test_file_without_test_duration_does_not_inherit_a_stale_one(qt_app, tmp_path):
    source = tmp_path / "in.csv"
    source.write_text("Event,Onset,Offset\nAttack bites,1.0000,2.0000\n", encoding="utf-8")
    model = _model()
    model.set_test_duration(600)

    assert model.import_from_csv(str(source))
    out = tmp_path / "out.csv"
    assert model.export_to_csv(str(out))

    # 0 = "no timed recording", as documented in CSV_FORMAT.md.
    assert _test_duration_row(out) == "Test Duration (seconds),0"


def test_timestamps_round_to_the_nearest_millisecond(qt_app, tmp_path):
    model = _model()
    assert model._parse_timestamp("1.001") == 1001
    assert model._parse_timestamp("13.0010") == 13001
    # No decimal point: the legacy millisecond format, kept as before.
    assert model._parse_timestamp("12") == 12


def test_bom_does_not_break_a_header_first_file(qt_app, tmp_path):
    source = tmp_path / "excel.csv"
    source.write_text(
        "Event,Onset,Offset\nAttack bites,12.5000,14.0000\n", encoding="utf-8-sig"
    )
    model = _model()

    assert model.import_from_csv(str(source))
    assert [(e.behavior, e.onset, e.offset) for e in model.get_all_events()] == [
        ("Attack bites", 12500, 14000)
    ]


class _FakeConfig:
    def __init__(self, sections):
        self._sections = sections

    def get(self, section, key=None, default=None):
        values = self._sections.get(section, {})
        return values if key is None else values.get(key, default)

    def set(self, *_args):
        pass


def test_saved_recording_duration_with_zero_minutes_is_restored(qt_app):
    win = MainWindow()
    try:
        win.set_config_manager(_FakeConfig({
            "annotation": {
                "last_recording_hours": 0,
                "last_recording_minutes": 0,
                "last_recording_seconds": 30,
            },
        }))
        restored = win.recording_control_view.duration_time_edit.time()
        assert (restored.hour(), restored.minute(), restored.second()) == (0, 0, 30)
    finally:
        win.set_close_guard(lambda: True)
        win.deleteLater()


COLLIDING = {
    "latency_metrics": [{"name": "Attack", "behavior": "Attack bites", "enabled": True}],
    "total_time_metrics": [
        {"name": "attack ", "behaviors": ["Attack bites", "Chasing"], "enabled": True}
    ],
}


def test_loading_colliding_metric_names_is_refused(qt_app, tmp_path):
    config = AnalysisMetricsConfig()
    before = (config.get_latency_metrics(), config.get_total_time_metrics())

    assert config.from_dict(COLLIDING) is False
    assert "collide" in config.last_load_error
    assert (config.get_latency_metrics(), config.get_total_time_metrics()) == before

    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(COLLIDING), encoding="utf-8")
    assert config.load_from_file(str(path)) is False


def test_loading_a_valid_metrics_configuration_still_works(qt_app):
    config = AnalysisMetricsConfig()
    valid = {
        "latency_metrics": [{"name": "Attack latency", "behavior": "Attack bites", "enabled": True}],
        "total_time_metrics": [],
    }
    assert config.from_dict(valid) is True
    assert config.get_latency_metrics() == valid["latency_metrics"]


def test_total_time_behaviours_with_commas_survive_the_table(qt_app):
    dialog = MetricsConfigDialog(None, behaviors=["Investigate, object", "Chasing"])
    try:
        dialog._add_total_time_row("Contact", ["Investigate, object", "Chasing"], True)
        assert dialog.get_total_time_metrics()[0]["behaviors"] == [
            "Investigate, object", "Chasing",
        ]
    finally:
        dialog.deleteLater()


def test_latency_dialog_keeps_a_target_it_does_not_list(qt_app):
    dialog = LatencyMetricDialog(None, behaviors=["Attack bites"], behavior="Freezing")
    try:
        assert dialog.get_selected_behavior() == "Freezing"
    finally:
        dialog.deleteLater()


def test_total_time_dialog_keeps_selected_names_it_does_not_list(qt_app):
    dialog = TotalTimeMetricDialog(
        None, behaviors=["Attack bites"], selected_behaviors=["Freezing", "Attack bites"]
    )
    try:
        assert sorted(dialog.get_selected_behaviors()) == ["Attack bites", "Freezing"]
    finally:
        dialog.deleteLater()
