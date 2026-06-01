"""Tests for ConfigManager defaults isolation + schema validation (1.3.4).

Covers BUG-018 (deep-copied defaults) and the lightweight structural
validation that degrades a corrupt settings.json to defaults (BUG-005).
"""

from __future__ import annotations

from utils.config_manager import ConfigManager
from utils.file_manager import FileManager


def _new_config():
    return ConfigManager(FileManager())


def test_instances_do_not_share_nested_defaults():
    a = _new_config()
    b = _new_config()

    a.set("annotation", "timeline_zoom_level", 777)

    # The class default and a second instance must be unaffected (BUG-018).
    assert b.get("annotation", "timeline_zoom_level") != 777
    assert ConfigManager.DEFAULT_CONFIG["annotation"]["timeline_zoom_level"] != 777


def test_validate_rejects_non_dict_top_level():
    cm = _new_config()
    assert cm._validate_loaded_config([1, 2, 3]) == {}


def test_validate_drops_type_mismatched_section():
    cm = _new_config()
    loaded = {"ui": "garbage", "general": {"recent_files_max": 5}}
    sane = cm._validate_loaded_config(loaded)

    # The malformed 'ui' section is dropped; the well-formed one is kept.
    assert "ui" not in sane
    assert sane["general"] == {"recent_files_max": 5}


def test_validate_passes_unknown_sections_through():
    cm = _new_config()
    loaded = {"future_section": {"x": 1}}
    assert cm._validate_loaded_config(loaded) == {"future_section": {"x": 1}}


def test_corrupt_section_falls_back_to_default(tmp_path, monkeypatch):
    cm = _new_config()
    # Simulate load_json returning a corrupt structure for 'ui'.
    monkeypatch.setattr(
        cm._file_manager, "load_json",
        lambda *_a, **_k: {"ui": "not-an-object"},
    )
    # Force the file-exists branch.
    monkeypatch.setattr(type(cm._config_file), "exists", lambda self: True)

    assert cm.load_config() is True
    # 'ui' kept its default object shape rather than the corrupt scalar.
    assert isinstance(cm.get("ui"), dict)
    assert "last_view" in cm.get("ui")
