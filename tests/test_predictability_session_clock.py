"""Transition analysis puts event times on the session clock (RecordingStart = 0).

The predictability chance baseline circularly shifts antecedent onsets over
[0, last offset). On raw video time, a session that started late was padded
with its pre-session gap, which lowered the chance level and inflated
above_chance.
"""

from __future__ import annotations

import pytest

import controllers.analysis_controller as analysis_controller_module
from controllers.analysis_controller import AnalysisController
from models.analysis_model import AnalysisModel
from models.sequence_analysis import antecedent_window_metric

# Session-relative (behavior, onset, offset); binary-exact times so shifted
# copies compare equal.
_RELATIVE_EVENTS = [
    ("Social contact", 5.0, 5.5), ("Attack bites", 6.0, 6.25),
    ("Social contact", 15.0, 15.5), ("Attack bites", 16.0, 16.25),
    ("Social contact", 25.0, 25.5), ("Attack bites", 26.0, 26.25),
    ("Social contact", 35.0, 35.5), ("Attack bites", 36.0, 36.25),
    ("Social contact", 45.0, 45.5), ("Attack bites", 46.0, 46.25),
]


def _csv(recording_start, *, with_marker=True):
    lines = [
        "Metadata",
        "RABET Version,1.4.0",
        "Format Schema,v1",
        "Test Duration (seconds),60",
        "",
        "Event,Onset,Offset",
    ]
    if with_marker:
        lines.append(f"RecordingStart,{recording_start:.4f},{recording_start:.4f}")
    for behavior, onset, offset in _RELATIVE_EVENTS:
        lines.append(
            f"{behavior},{onset + recording_start:.4f},{offset + recording_start:.4f}")
    lines += [
        "",
        "Behavior,Duration,Frequency",
        "Attack bites,1.25,5",
        "Social contact,2.50,5",
        "",
    ]
    return "\n".join(lines)


def _load(tmp_path, files):
    paths = []
    for name, text in files:
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        paths.append(str(path))
    model = AnalysisModel()
    assert model.load_files(paths) is True
    return model, paths


def _per_file_from_controller(monkeypatch, model):
    """Run the controller entry point and capture what reaches the dialog."""
    captured = {}

    class _FakeProgress:
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    class _FakeDialog:
        def __init__(self, parent, per_file, ordered, progress_cb=None):
            captured["per_file"] = per_file

        def exec(self):
            return 0

    import views.transition_analysis_dialog as dialog_module

    monkeypatch.setattr(analysis_controller_module, "QProgressDialog", _FakeProgress)
    monkeypatch.setattr(dialog_module, "TransitionAnalysisDialog", _FakeDialog)

    ctrl = AnalysisController.__new__(AnalysisController)
    ctrl._model = model
    ctrl._view = None
    ctrl.on_transition_analysis_requested()
    return dict(captured["per_file"])


def test_recording_start_reads_marker_and_defaults_to_zero(tmp_path):
    model, (late, unmarked) = _load(tmp_path, [
        ("1_late_annotations.csv", _csv(120.0)),
        ("2_unmarked_annotations.csv", _csv(0.0, with_marker=False)),
    ])
    assert model.get_file_recording_start(late) == 120.0
    assert model.get_file_recording_start(unmarked) == 0.0
    assert model.get_file_recording_start("not-loaded.csv") == 0.0


def test_session_at_zero_passes_events_unchanged(qt_app, monkeypatch, tmp_path):
    model, (path,) = _load(tmp_path, [("1_zero_annotations.csv", _csv(0.0))])
    per_file = _per_file_from_controller(monkeypatch, model)
    assert per_file["1_zero"] == model.get_event_tuples(path)


def test_late_session_is_shifted_to_its_own_clock(qt_app, monkeypatch, tmp_path):
    model, (zero, late) = _load(tmp_path, [
        ("1_zero_annotations.csv", _csv(0.0)),
        ("2_late_annotations.csv", _csv(120.0)),
    ])
    per_file = _per_file_from_controller(monkeypatch, model)
    # Same session recorded later in the video -> identical session-clock events.
    assert per_file["2_late"] == per_file["1_zero"]
    assert per_file["1_zero"] == list(_RELATIVE_EVENTS)
    # The raw (video-time) events are still what the model reports.
    assert model.get_event_tuples(late)[0][1] == pytest.approx(125.0)


def test_chance_baseline_no_longer_depends_on_session_start(qt_app, monkeypatch, tmp_path):
    model, (_zero, late) = _load(tmp_path, [
        ("1_zero_annotations.csv", _csv(0.0)),
        ("2_late_annotations.csv", _csv(120.0)),
    ])
    per_file = _per_file_from_controller(monkeypatch, model)

    def metric(events):
        return antecedent_window_metric(
            events, "Attack bites", ["Social contact"], 2.0, n_perm=200, seed=0)

    reference = metric(per_file["1_zero"])
    shifted = metric(per_file["2_late"])
    assert shifted["chance_mean"] == reference["chance_mean"]
    assert shifted["above_chance"] == reference["above_chance"]

    # On raw video time the 120 s pre-session gap diluted the chance level,
    # which is the bias this change removes.
    raw = metric(model.get_event_tuples(late))
    assert raw["observed"] == reference["observed"]
    assert raw["chance_mean"] < reference["chance_mean"]
    assert raw["above_chance"] > reference["above_chance"]
