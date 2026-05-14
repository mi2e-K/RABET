"""Backward-compatibility tests for the RABET CSV file format.

These tests guarantee that:

* v1.0.x annotation files (no schema metadata) still load cleanly.
* v1.2.x annotation files (with ``RABET Version`` / ``Format Schema`` rows)
  load cleanly and their numbers match the original event data.
* The fixture files committed to ``tests/fixtures`` remain in sync with the
  parser - any future schema bump must also update these fixtures.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from models.action_map_model import ActionMapModel
from models.annotation_model import AnnotationModel


def _import_fixture(qt_app, fixtures_dir: Path, fname: str):
    action_map = ActionMapModel()
    model = AnnotationModel(action_map)
    csv_path = fixtures_dir / fname
    assert csv_path.exists(), f"Fixture missing: {csv_path}"
    assert model.import_from_csv(str(csv_path)), f"Import failed for {csv_path}"
    return model


def test_import_v1_0_annotation_csv(qt_app, fixtures_dir):
    """The pre-1.2.0 annotation CSV format must still parse."""
    model = _import_fixture(qt_app, fixtures_dir, "sample_v1_0_annotation.csv")
    events = model.get_all_events()

    # The fixture contains 1 RecordingStart marker + 3 real events.
    assert len(events) == 4
    behaviors = [e.behavior for e in events]
    assert behaviors.count("RecordingStart") == 1
    assert behaviors.count("Attack bites") == 2
    assert behaviors.count("Sideways threats") == 1

    # Onsets / offsets converted from seconds to milliseconds correctly.
    attack_events = [e for e in events if e.behavior == "Attack bites"]
    attack_events.sort(key=lambda ev: ev.onset)
    assert attack_events[0].onset == 1000
    assert attack_events[0].offset == 1500
    assert attack_events[1].onset == 3000
    assert attack_events[1].offset == 3400


def test_import_v1_2_annotation_csv(qt_app, fixtures_dir):
    """The 1.2.0+ annotation CSV format must parse and yield identical data."""
    model = _import_fixture(qt_app, fixtures_dir, "sample_v1_2_annotation.csv")
    events = model.get_all_events()

    assert len(events) == 4
    attack_events = [e for e in events if e.behavior == "Attack bites"]
    attack_events.sort(key=lambda ev: ev.onset)
    assert (attack_events[0].onset, attack_events[0].offset) == (1000, 1500)
    assert (attack_events[1].onset, attack_events[1].offset) == (3000, 3400)


def test_v1_0_and_v1_2_imports_equivalent(qt_app, fixtures_dir):
    """The two fixtures only differ by the schema header; data must match."""
    v1_0 = _import_fixture(qt_app, fixtures_dir, "sample_v1_0_annotation.csv")
    v1_2 = _import_fixture(qt_app, fixtures_dir, "sample_v1_2_annotation.csv")

    def signature(model):
        return sorted(
            (e.behavior, e.onset, e.offset) for e in model.get_all_events()
        )

    assert signature(v1_0) == signature(v1_2)


def test_v1_2_annotation_has_schema_metadata(qt_app, fixtures_dir):
    """The v1.2 fixture must literally contain the schema header rows."""
    text = (fixtures_dir / "sample_v1_2_annotation.csv").read_text()
    assert "RABET Version" in text
    assert "Format Schema,v1" in text


def test_v1_0_annotation_has_no_schema_metadata(qt_app, fixtures_dir):
    """The v1.0 fixture must NOT contain the new schema header rows."""
    text = (fixtures_dir / "sample_v1_0_annotation.csv").read_text()
    assert "RABET Version" not in text
    assert "Format Schema" not in text
