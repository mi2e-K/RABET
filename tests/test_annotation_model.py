"""Smoke tests for ``AnnotationModel`` round-tripping events through CSV."""
from __future__ import annotations

import os

from models.action_map_model import ActionMapModel
from models.annotation_model import AnnotationModel, BehaviorEvent


def _make_model(qt_app):
    action_map = ActionMapModel()
    return action_map, AnnotationModel(action_map)


def test_export_import_round_trip(qt_app, tmp_path):
    """Exported events must be re-importable and preserve onset / offset."""
    _, annotation_model = _make_model(qt_app)

    annotation_model._events = [
        BehaviorEvent("o", "Attack bites", 1000, 1500),
        BehaviorEvent("j", "Sideways threats", 2000, 2200),
    ]
    annotation_model.set_test_duration(60)

    csv_path = tmp_path / "round_trip.csv"
    assert annotation_model.export_to_csv(str(csv_path))

    text = csv_path.read_text()
    # Schema markers are written by v1.2.0+ exports.
    assert "RABET Version" in text
    assert "Format Schema,v1" in text
    assert "Event,Onset,Offset" in text

    _, model2 = _make_model(qt_app)
    assert model2.import_from_csv(str(csv_path))
    events = model2.get_all_events()
    assert len(events) == 2

    assert events[0].behavior == "Attack bites"
    assert events[0].onset == 1000 and events[0].offset == 1500
    assert events[1].behavior == "Sideways threats"
    assert events[1].onset == 2000 and events[1].offset == 2200


def test_discard_active_event(qt_app):
    """``discard_active_event`` removes the active event without finalising it."""
    _, annotation_model = _make_model(qt_app)

    assert annotation_model.start_event("o", 1000) is True
    assert "o" in annotation_model.get_active_events()

    assert annotation_model.discard_active_event("o") is True
    assert "o" not in annotation_model.get_active_events()
    # Discarded events must NOT appear in the finalised list.
    assert annotation_model.get_all_events() == []
