"""Tests for packaged-app config path resolution."""

from __future__ import annotations

import sys

from utils.config_path_manager import ConfigPathManager


def test_frozen_config_directory_prefers_meipass_configs(tmp_path, monkeypatch):
    meipass_configs = tmp_path / "meipass" / "configs"
    meipass_configs.mkdir(parents=True)
    (meipass_configs / "default_metrics.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "meipass"), raising=False)

    manager = ConfigPathManager()

    assert manager.get_config_directory() == meipass_configs
    assert manager.get_config_file_path("default_metrics.json") == (
        meipass_configs / "default_metrics.json"
    )


def test_frozen_defaults_copy_from_meipass_configs(tmp_path, monkeypatch):
    meipass_configs = tmp_path / "meipass" / "configs"
    meipass_configs.mkdir(parents=True)
    source = meipass_configs / "default_action_map.json"
    source.write_text('{"x": "Example"}', encoding="utf-8")

    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "meipass"), raising=False)

    manager = ConfigPathManager()
    manager.copy_defaults_to_user_dir()

    copied = tmp_path / "appdata" / "RABET" / "configs" / "default_action_map.json"
    assert copied.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
