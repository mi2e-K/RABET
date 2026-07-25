"""Tests for project-scoped action maps (1.4.2).

A project binds its own action map so the same key always means the same
behaviour for every video in it. While a project is open, edits must go to the
project's map and leave the user's global map untouched; closing the project
must restore the global map exactly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from models.action_map_model import ActionMapModel
from models.project_model import ProjectModel
from utils.file_manager import FileManager


class _StubConfigPaths:
    """Redirect user/default action map lookups into a temp directory.

    Keeps tests from reading — or worse, auto-saving over — the developer's
    real ``user_action_map.json`` in %APPDATA%/~/.config.
    """

    def __init__(self, base: Path):
        self._base = base

    def get_action_map_config_path(self, filename):
        return self._base / filename

    def ensure_default_configs(self):
        return None


GLOBAL_MAP = {"g": "Global behaviour"}
PROJECT_MAP = {"p": "Project behaviour"}


@pytest.fixture
def isolated_model(tmp_path: Path, qt_app):
    """An ActionMapModel whose global map lives in tmp_path."""
    config_dir = tmp_path / "userconfig"
    config_dir.mkdir()
    (config_dir / "user_action_map.json").write_text(
        json.dumps(GLOBAL_MAP), encoding="utf-8"
    )

    model = ActionMapModel()
    # Swap in the stub, then reload so the model starts from the temp global map.
    model._config_path_manager = _StubConfigPaths(config_dir)
    model._load_action_map()
    assert model.get_all_mappings() == GLOBAL_MAP

    model._config_dir = config_dir
    return model


def _global_map_on_disk(model) -> dict:
    return json.loads(
        (model._config_dir / "user_action_map.json").read_text(encoding="utf-8")
    )


# --- Manifest -----------------------------------------------------------


def test_manifest_round_trips_bound_action_map(tmp_path: Path, qt_app):
    model = ProjectModel(FileManager())
    assert model.create_project(str(tmp_path), "P") is True

    rel = model.get_default_action_map_rel_path()
    assert model.set_action_map(rel) is True
    assert model.save_project() is True

    reloaded = ProjectModel(FileManager())
    assert reloaded.load_project(str(tmp_path / "P")) is True
    assert reloaded.get_action_map_rel_path() == rel
    assert reloaded.get_action_map_path() == str(tmp_path / "P" / rel)


def test_legacy_project_without_field_has_no_bound_map(tmp_path: Path, qt_app):
    """A pre-1.4.2 manifest keeps using the global map (backward compatible)."""
    project_dir = tmp_path / "Legacy"
    (project_dir / "action_maps").mkdir(parents=True)
    (project_dir / "project.json").write_text(
        json.dumps(
            {
                "name": "Legacy",
                "description": "",
                "created_date": "",
                "modified_date": "",
                "videos": [],
                "annotations": [],
                "action_maps": [],
                "analyses": [],
            }
        ),
        encoding="utf-8",
    )

    model = ProjectModel(FileManager())
    assert model.load_project(str(project_dir)) is True
    assert model.get_action_map_rel_path() == ""
    assert model.get_action_map_path() is None


def test_set_action_map_rejects_path_outside_project(tmp_path: Path, qt_app):
    model = ProjectModel(FileManager())
    assert model.create_project(str(tmp_path), "P") is True

    outside = tmp_path / "elsewhere" / "map.json"
    assert model.set_action_map(str(outside)) is False
    assert model.get_action_map_rel_path() == ""


# --- Scope switching ----------------------------------------------------


def test_enter_scope_snapshots_current_map_when_missing(isolated_model, tmp_path):
    target = tmp_path / "proj" / "action_maps" / "project_action_map.json"

    assert isolated_model.enter_project_scope(str(target)) is True
    assert isolated_model.is_project_scoped() is True
    # The snapshot froze the map that was active at creation time.
    assert json.loads(target.read_text(encoding="utf-8")) == GLOBAL_MAP


def test_enter_scope_loads_existing_project_map(isolated_model, tmp_path):
    target = tmp_path / "project_action_map.json"
    target.write_text(json.dumps(PROJECT_MAP), encoding="utf-8")

    assert isolated_model.enter_project_scope(str(target)) is True
    assert isolated_model.get_all_mappings() == PROJECT_MAP


def test_edits_while_scoped_do_not_touch_global_map(isolated_model, tmp_path):
    target = tmp_path / "project_action_map.json"
    target.write_text(json.dumps(PROJECT_MAP), encoding="utf-8")
    assert isolated_model.enter_project_scope(str(target)) is True

    assert isolated_model.add_mapping("z", "Scoped addition") is True
    isolated_model._flush_auto_save()

    # The edit landed in the project's map...
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "p": "Project behaviour",
        "z": "Scoped addition",
    }
    # ...and the user's global map is exactly as it was.
    assert _global_map_on_disk(isolated_model) == GLOBAL_MAP


def test_exit_scope_restores_global_map(isolated_model, tmp_path):
    target = tmp_path / "project_action_map.json"
    target.write_text(json.dumps(PROJECT_MAP), encoding="utf-8")
    isolated_model.enter_project_scope(str(target))
    isolated_model.add_mapping("z", "Scoped addition")

    assert isolated_model.exit_project_scope() is True

    assert isolated_model.is_project_scoped() is False
    assert isolated_model.get_all_mappings() == GLOBAL_MAP
    # The pending edit was flushed into the project map, not the global one.
    assert "z" in json.loads(target.read_text(encoding="utf-8"))
    assert _global_map_on_disk(isolated_model) == GLOBAL_MAP


def test_edits_after_exit_go_back_to_global_map(isolated_model, tmp_path):
    target = tmp_path / "project_action_map.json"
    target.write_text(json.dumps(PROJECT_MAP), encoding="utf-8")
    isolated_model.enter_project_scope(str(target))
    isolated_model.exit_project_scope()

    assert isolated_model.add_mapping("w", "Global addition") is True
    isolated_model._flush_auto_save()

    on_disk = _global_map_on_disk(isolated_model)
    assert on_disk == {"g": "Global behaviour", "w": "Global addition"}
    # The project map did not pick up a global-scope edit.
    assert "w" not in json.loads(target.read_text(encoding="utf-8"))


def test_snapshot_always_overwrites_a_leftover_project_map(isolated_model, tmp_path):
    """Explicit binding must write the map the user is looking at.

    A stale file at the target path must not be adopted in its place, which
    would silently bind mappings the user never chose.
    """
    target = tmp_path / "project_action_map.json"
    target.write_text(json.dumps(PROJECT_MAP), encoding="utf-8")

    assert isolated_model.enter_project_scope(str(target), snapshot_always=True) is True

    assert isolated_model.get_all_mappings() == GLOBAL_MAP
    assert json.loads(target.read_text(encoding="utf-8")) == GLOBAL_MAP


def test_exit_scope_is_a_noop_when_not_scoped(isolated_model):
    assert isolated_model.exit_project_scope() is False
    assert isolated_model.get_all_mappings() == GLOBAL_MAP


def test_corrupt_project_map_leaves_model_global(isolated_model, tmp_path):
    target = tmp_path / "broken.json"
    target.write_text("{not valid json", encoding="utf-8")

    assert isolated_model.enter_project_scope(str(target)) is False
    assert isolated_model.is_project_scoped() is False
    # Falls back to the global map rather than some other project's mappings.
    assert isolated_model.get_all_mappings() == GLOBAL_MAP


def test_missing_map_without_snapshot_does_not_enter_scope(isolated_model, tmp_path):
    target = tmp_path / "absent.json"

    assert (
        isolated_model.enter_project_scope(str(target), snapshot_if_missing=False)
        is False
    )
    assert isolated_model.is_project_scoped() is False
    assert not target.exists()
