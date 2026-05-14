"""Tests for ``ActionMapModel`` covering add/remove/load/save/reset paths."""
from __future__ import annotations

import json

import pytest

from models.action_map_model import ActionMapModel


@pytest.fixture()
def model(qt_app):
    return ActionMapModel()


def test_default_map_loaded(model):
    """A freshly created model must have at least the bundled defaults."""
    assert model.is_loaded()
    mappings = model.get_all_mappings()
    assert "o" in mappings and mappings["o"] == "Attack bites"


def test_add_mapping(model):
    assert model.add_mapping("z", "Test behavior") is True
    assert model.get_behavior("z") == "Test behavior"


def test_add_mapping_rejects_multi_char_key(model):
    """Multi-character keys must be refused with no model mutation."""
    snapshot = model.get_all_mappings()
    assert model.add_mapping("zz", "Test") is False
    assert model.get_all_mappings() == snapshot


def test_add_mapping_rejects_empty_behavior(model):
    snapshot = model.get_all_mappings()
    assert model.add_mapping("z", "") is False
    assert model.get_all_mappings() == snapshot


def test_remove_mapping_unknown_key_is_noop(model):
    snapshot = model.get_all_mappings()
    assert model.remove_mapping("@") is False
    assert model.get_all_mappings() == snapshot


def test_remove_mapping_known_key(model):
    model.add_mapping("y", "Yawning")
    assert "y" in model.get_all_mappings()
    assert model.remove_mapping("y") is True
    assert "y" not in model.get_all_mappings()


def test_set_behavior_active_round_trip(model):
    model.add_mapping("y", "Yawning")
    model.set_behavior_active("y", True)
    assert "y" in model.get_active_behaviors()
    model.set_behavior_active("y", False)
    assert "y" not in model.get_active_behaviors()


def test_load_from_json_roundtrip(model, tmp_path):
    """A saved JSON file must reload to the same mappings."""
    target = tmp_path / "map.json"
    custom = {"a": "Alpha", "b": "Beta", "c": "Gamma"}
    target.write_text(json.dumps(custom))
    assert model.load_from_json(str(target), auto_save=False) is True
    assert model.get_all_mappings() == custom


def test_load_from_json_rejects_invalid_format(model, tmp_path):
    """Loading non-dict JSON must fail without mutating the live map."""
    target = tmp_path / "bad.json"
    target.write_text(json.dumps(["not", "a", "dict"]))
    snapshot = model.get_all_mappings()
    assert model.load_from_json(str(target), auto_save=False) is False
    assert model.get_all_mappings() == snapshot


def test_reset_to_default_restores_known_keys(model):
    model._action_map = {}
    assert model.reset_to_default() is True
    # The hardcoded fallback contains at least one of the standard mappings.
    assert model.get_behavior("o") == "Attack bites"
