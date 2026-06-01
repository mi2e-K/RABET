"""Tests for models.annotation_model lifecycle and CSV round-trip (1.3.4).

GUI-free: AnnotationModel only needs an ActionMapModel (and optionally a
VideoModel) and never touches widgets, so these run headless.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from models.action_map_model import ActionMapModel
from models.annotation_model import AnnotationModel, BehaviorEvent


@pytest.fixture
def action_map():
    return ActionMapModel()


@pytest.fixture
def model(action_map):
    return AnnotationModel(action_map)


# -------------------------------------------------------------------- #
# start_event / end_event lifecycle
# -------------------------------------------------------------------- #


def test_start_event_rejects_unmapped_key(model):
    # 'unmapped' key not in the default action map.
    assert model.start_event("=", 1000) is False
    assert model.get_active_events() == {}


def test_end_event_enforces_minimum_one_frame(model, action_map):
    action_map.add_mapping("z", "Test behavior")
    assert model.start_event("z", 1000) is True
    # End at the same position -> clamped to onset + frame_duration.
    assert model.end_event("z", 1000) is True
    events = model.get_all_events()
    assert len(events) == 1
    assert events[0].offset > events[0].onset
    # No stranded active event.
    assert model.get_active_events() == {}


def test_duplicate_press_is_ignored(model, action_map):
    action_map.add_mapping("z", "Test behavior")
    assert model.start_event("z", 1000) is True
    # Second press while still active -> rejected, original onset preserved.
    assert model.start_event("z", 1500) is False
    assert model.get_active_events()["z"].onset == 1000


# -------------------------------------------------------------------- #
# CSV round-trip
# -------------------------------------------------------------------- #


def test_recording_start_remains_zero_duration_after_round_trip(model, tmp_path: Path):
    # RecordingStart marker is zero-duration by design.
    rs = BehaviorEvent("R", "RecordingStart", 1000, 1000)
    model.add_recording_start_event(rs)

    out = tmp_path / "ann.csv"
    assert model.export_to_csv(str(out)) is True
    assert model.import_from_csv(str(out)) is True

    events = model.get_all_events()
    rs_events = [e for e in events if e.behavior == "RecordingStart"]
    assert len(rs_events) == 1
    # Must NOT have been clamped to onset + one frame (BUG-009).
    assert rs_events[0].onset == rs_events[0].offset


def test_invalid_import_preserves_existing_annotations(model, action_map, tmp_path: Path):
    # Start with one existing event.
    action_map.add_mapping("z", "Test behavior")
    model._events.append(BehaviorEvent("z", "Test behavior", 1000, 2000))

    bad = tmp_path / "garbage.csv"
    bad.write_text("not,a,valid\nrabet,file,at all\n", encoding="utf-8")

    assert model.import_from_csv(str(bad)) is False
    # Existing annotation must survive a failed import (BUG-004).
    events = model.get_all_events()
    assert len(events) == 1
    assert events[0].onset == 1000


def test_empty_import_preserves_existing_annotations(model, action_map, tmp_path: Path):
    action_map.add_mapping("z", "Test behavior")
    model._events.append(BehaviorEvent("z", "Test behavior", 1000, 2000))

    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")

    assert model.import_from_csv(str(empty)) is False
    assert len(model.get_all_events()) == 1


def test_valid_import_replaces_existing_annotations_once(model, action_map, tmp_path: Path):
    action_map.add_mapping("z", "Test behavior")
    # Pre-existing event that should be replaced by the import.
    model._events.append(BehaviorEvent("z", "Old", 100, 200))

    # Build a valid export from a different model, then import it.
    src = AnnotationModel(action_map)
    src._events.append(BehaviorEvent("z", "Test behavior", 1000, 2000))
    out = tmp_path / "valid.csv"
    assert src.export_to_csv(str(out)) is True

    assert model.import_from_csv(str(out)) is True
    events = [e for e in model.get_all_events() if e.behavior != "RecordingStart"]
    assert len(events) == 1
    assert events[0].behavior == "Test behavior"
    assert events[0].onset == 1000


def test_export_import_round_trip_preserves_events(model, action_map, tmp_path: Path):
    action_map.add_mapping("z", "Test behavior")
    model._events.append(BehaviorEvent("z", "Test behavior", 1000, 2500))

    out = tmp_path / "ann.csv"
    assert model.export_to_csv(str(out)) is True
    assert model.import_from_csv(str(out)) is True

    events = [e for e in model.get_all_events() if e.behavior == "Test behavior"]
    assert len(events) == 1
    # Onset/offset in ms preserved (4-decimal seconds in the file).
    assert events[0].onset == 1000
    assert events[0].offset == 2500
