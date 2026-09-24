"""Unreadable settings files are set aside instead of overwritten, and the
project "Remove" confirmation says whether the file is deleted from disk.
"""

from __future__ import annotations

import json
import logging

import pytest
from PySide6.QtWidgets import QMessageBox

from models.action_map_model import ActionMapModel
from utils.config_manager import ConfigManager
from utils.config_path_manager import ConfigPathManager
from utils.file_manager import FileManager
from views.project_view import ProjectView


@pytest.fixture
def user_configs(tmp_path, monkeypatch):
    directory = tmp_path / "user-configs"
    directory.mkdir()
    monkeypatch.setattr(
        ConfigPathManager, "_init_user_config_dir",
        lambda self: setattr(self, "_user_config_dir", directory),
    )
    return directory


@pytest.fixture
def app_data(tmp_path, monkeypatch):
    directory = tmp_path / "app-data"
    monkeypatch.setattr(FileManager, "_get_app_data_dir", lambda self: directory)
    return directory


@pytest.fixture
def quiet_logs():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


def test_unreadable_user_action_map_is_set_aside(qt_app, user_configs, quiet_logs):
    user_map = user_configs / "user_action_map.json"
    user_map.write_text('{"o": "Attack bites",', encoding="utf-8")  # truncated

    model = ActionMapModel()

    kept = list(user_configs.glob("user_action_map.json.corrupt-*"))
    assert len(kept) == 1
    assert kept[0].read_text(encoding="utf-8") == '{"o": "Attack bites",'
    assert model.recovered_files == [(str(user_map), str(kept[0]))]
    assert model.get_all_mappings()  # fell back to the default map, as before


def test_first_run_without_a_user_map_sets_nothing_aside(qt_app, user_configs, quiet_logs):
    model = ActionMapModel()
    assert model.recovered_files == []
    assert list(user_configs.glob("*.corrupt-*")) == []


def test_unparseable_settings_json_is_set_aside(qt_app, app_data, quiet_logs):
    settings = app_data / "config" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{not json", encoding="utf-8")

    manager = ConfigManager(FileManager())

    kept = list(settings.parent.glob("settings.json.corrupt-*"))
    assert len(kept) == 1
    assert kept[0].read_text(encoding="utf-8") == "{not json"
    assert manager.recovered_files == [(str(settings), str(kept[0]))]
    json.loads(settings.read_text(encoding="utf-8"))  # a fresh, valid file


def test_settings_json_with_a_broken_section_is_copied_first(qt_app, app_data, quiet_logs):
    settings = app_data / "config" / "settings.json"
    settings.parent.mkdir(parents=True)
    original = json.dumps({"ui": "garbage", "general": {"recent_files_max": 5}})
    settings.write_text(original, encoding="utf-8")

    manager = ConfigManager(FileManager())

    kept = list(settings.parent.glob("settings.json.corrupt-*"))
    assert len(kept) == 1
    assert kept[0].read_text(encoding="utf-8") == original
    assert isinstance(manager.get("ui"), dict)  # still degraded to defaults


def test_valid_settings_json_is_left_alone(qt_app, app_data, quiet_logs):
    ConfigManager(FileManager())  # first run writes a valid file
    manager = ConfigManager(FileManager())
    assert manager.recovered_files == []
    assert list((app_data / "config").glob("*.corrupt-*")) == []


class _Item:
    def __init__(self, path):
        self._path = path

    def text(self, _column):
        return self._path


def _removal_prompt(monkeypatch, path, file_type):
    asked = {}

    def question(_parent, _title, text, _buttons, default=None):
        asked["text"], asked["default"] = text, default
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    view = ProjectView()
    try:
        view.on_remove_file(_Item(path), file_type)
    finally:
        view.deleteLater()
    return asked


def test_removing_a_project_copy_says_it_is_deleted(qt_app, monkeypatch):
    asked = _removal_prompt(monkeypatch, "annotations/mouse_annotations.csv", "annotations")
    assert "deleted from disk" in asked["text"]
    assert asked["default"] == QMessageBox.StandardButton.No


def test_removing_an_external_file_says_it_stays(qt_app, monkeypatch):
    asked = _removal_prompt(monkeypatch, "/data/videos/mouse.mp4", "videos")
    assert "stays on disk" in asked["text"]


def test_set_aside_files_are_reported_once_after_startup(qt_app, monkeypatch):
    import types

    from controllers.app_controller import AppController

    shown = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda _parent, title, text: shown.append((title, text))),
    )
    ctrl = AppController.__new__(AppController)
    ctrl.main_window = None
    ctrl.config_manager = types.SimpleNamespace(
        recovered_files=[("/cfg/settings.json", "/cfg/settings.json.corrupt-20260101-000000")]
    )
    ctrl.action_map_model = types.SimpleNamespace(recovered_files=[])

    ctrl._report_recovered_config_files()

    assert len(shown) == 1
    assert "settings.json.corrupt-20260101-000000" in shown[0][1]

    shown.clear()
    ctrl.config_manager.recovered_files = []
    ctrl._report_recovered_config_files()
    assert shown == []
