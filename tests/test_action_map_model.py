"""Tests for ActionMapModel duplicate-behavior policy (§16-2 / BUG-011)."""

from __future__ import annotations

import json

import pytest

from models.action_map_model import ActionMapModel


@pytest.fixture
def model():
    m = ActionMapModel()
    # Start from a known small map.
    m._action_map = {"a": "Attack bites", "b": "Chasing"}
    return m


def test_add_mapping_rejects_duplicate_behavior_on_new_key(model):
    # 'c' tries to reuse an existing behaviour name (different case).
    assert model.add_mapping("c", "attack bites") is False
    assert "c" not in model.get_all_mappings()


def test_add_mapping_allows_edit_same_key(model):
    # Editing 'a' to a NEW unique behaviour is fine.
    assert model.add_mapping("a", "Sideways threats") is True
    assert model.get_behavior("a") == "Sideways threats"


def test_add_mapping_allows_reconfirm_same_pair(model):
    assert model.add_mapping("a", "Attack bites") is True


def test_add_mapping_accepts_unique_behavior(model):
    assert model.add_mapping("c", "Rearing") is True
    assert model.get_behavior("c") == "Rearing"


def test_has_behavior_ignores_given_key(model):
    assert model.has_behavior("Attack bites") is True
    # Ignoring 'a' makes its own behaviour invisible.
    assert model.has_behavior("Attack bites", ignore_key="a") is False


def test_load_tolerates_duplicate_behaviors(tmp_path, model):
    # A legacy map with two keys mapping to the same behaviour must still load
    # (backward compatibility), only logging a warning.
    p = tmp_path / "legacy.json"
    p.write_text(json.dumps({"a": "Attack bites", "x": "attack bites"}),
                 encoding="utf-8")
    assert model.load_from_json(str(p), auto_save=False, emit_signal=False) is True
    assert len(model.get_all_mappings()) == 2


def test_find_key_for_behavior_is_deterministic():
    from models.annotation_model import AnnotationModel

    m = ActionMapModel()
    # Two keys map to the same behaviour (legacy). Resolution is the first key
    # in sorted order regardless of dict insertion order.
    m._action_map = {"x": "Chasing", "a": "Chasing"}
    ann = AnnotationModel(m)
    assert ann._find_key_for_behavior("Chasing") == "a"


# --- 1.4.0: behaviour kind (state vs point) -------------------------------- #


def test_get_kind_defaults_to_state(model):
    assert model.get_kind("a") == "state"
    assert model.get_kind("zzz-unmapped") == "state"


def test_add_mapping_with_point_kind(model):
    assert model.add_mapping("c", "Head dip", kind="point") is True
    assert model.get_behavior("c") == "Head dip"
    assert model.get_kind("c") == "point"
    # get_all_mappings still returns a plain {key: name} dict (no kind leakage).
    assert model.get_all_mappings()["c"] == "Head dip"


def test_add_mapping_none_kind_preserves_existing(model):
    model.add_mapping("c", "Head dip", kind="point")
    # Re-confirming the same pair with kind=None must NOT reset it to state.
    model.add_mapping("c", "Head dip")
    assert model.get_kind("c") == "point"


def test_remove_mapping_drops_kind(model):
    model.add_mapping("c", "Head dip", kind="point")
    assert model.remove_mapping("c") is True
    assert model.get_kind("c") == "state"  # gone -> default


def test_load_parses_union_value_form(tmp_path, model):
    p = tmp_path / "map.json"
    p.write_text(
        json.dumps({
            "a": "Attack bites",                                # state (string)
            "h": {"behavior": "Head dip", "kind": "point"},     # point (object)
        }),
        encoding="utf-8",
    )
    assert model.load_from_json(str(p), auto_save=False, emit_signal=False) is True
    assert model.get_behavior("a") == "Attack bites"
    assert model.get_kind("a") == "state"
    assert model.get_behavior("h") == "Head dip"
    assert model.get_kind("h") == "point"


def test_serialize_roundtrip_state_stays_string(tmp_path, model):
    model.add_mapping("c", "Head dip", kind="point")
    model._action_map["a"] = "Attack bites"  # state
    out = tmp_path / "out.json"
    assert model.save_to_json(str(out)) is True

    raw = json.loads(out.read_text(encoding="utf-8"))
    assert raw["a"] == "Attack bites"                               # bare string
    assert raw["c"] == {"behavior": "Head dip", "kind": "point"}    # object

    # Round-trips through load.
    fresh = ActionMapModel()
    assert fresh.load_from_json(str(out), auto_save=False, emit_signal=False) is True
    assert fresh.get_kind("a") == "state"
    assert fresh.get_kind("c") == "point"
