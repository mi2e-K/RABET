"""Tests for reading files RABET did not write (1.4.2).

RABET's own JSON is pure ASCII (``json.dumps`` escapes non-ASCII), so its
round-trip was always safe. Files that arrive from outside — hand-edited,
script-generated, or carrying a BOM — are UTF-8, and reading those with the
platform codepage either failed or, on a Japanese Windows install, silently
produced mojibake.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from models.action_map_model import ActionMapModel
from models.analysis_config import AnalysisMetricsConfig
from utils.file_manager import FileManager


JP = {"name": "実験A", "description": "オス同士の対戦"}


# --- JSON manifests / settings -----------------------------------------


def test_load_json_reads_utf8_without_bom(tmp_path: Path):
    path = tmp_path / "utf8.json"
    path.write_text(json.dumps(JP, ensure_ascii=False), encoding="utf-8")

    loaded = FileManager().load_json(path)

    assert loaded is not None
    # Must be the real text, not mojibake decoded via a locale codepage.
    assert loaded["name"] == "実験A"
    assert loaded["description"] == "オス同士の対戦"


def test_load_json_tolerates_a_bom(tmp_path: Path):
    """Windows editors and PowerShell 5.1's Out-File add a UTF-8 BOM."""
    path = tmp_path / "bom.json"
    path.write_text(json.dumps({"name": "Study"}), encoding="utf-8-sig")

    loaded = FileManager().load_json(path)

    assert loaded == {"name": "Study"}


def test_rabet_written_json_still_round_trips(tmp_path: Path):
    """The pre-existing (ASCII) path must be unaffected."""
    fm = FileManager()
    path = tmp_path / "written.json"

    assert fm.save_json(JP, path) is True
    assert path.read_bytes().isascii()  # non-ASCII is \u-escaped on disk
    assert fm.load_json(path) == JP


# --- Action maps --------------------------------------------------------


def test_action_map_loads_japanese_labels(tmp_path: Path, qt_app):
    path = tmp_path / "jp_map.json"
    path.write_text(
        json.dumps({"a": "攻撃", "g": "グルーミング"}, ensure_ascii=False),
        encoding="utf-8",
    )

    model = ActionMapModel()
    assert model.load_from_json(str(path), auto_save=False, emit_signal=False) is True
    assert model.get_all_mappings() == {"a": "攻撃", "g": "グルーミング"}


def test_action_map_tolerates_a_bom(tmp_path: Path, qt_app):
    path = tmp_path / "bom_map.json"
    path.write_text(json.dumps({"a": "Attack"}), encoding="utf-8-sig")

    model = ActionMapModel()
    assert model.load_from_json(str(path), auto_save=False, emit_signal=False) is True
    assert model.get_all_mappings() == {"a": "Attack"}


def test_action_map_written_by_rabet_reloads(tmp_path: Path, qt_app):
    """Japanese labels typed into the GUI must keep round-tripping."""
    model = ActionMapModel()
    model._action_map = {}
    model._behavior_kinds = {}
    model.add_mapping("a", "攻撃")

    path = tmp_path / "gui_map.json"
    assert model.save_to_json(str(path)) is True

    reloaded = ActionMapModel()
    assert reloaded.load_from_json(str(path), auto_save=False, emit_signal=False) is True
    assert reloaded.get_all_mappings()["a"] == "攻撃"


# --- Metrics configuration ---------------------------------------------


def test_metrics_config_reads_utf8_with_bom(tmp_path: Path):
    path = tmp_path / "metrics.json"
    # Content shape is irrelevant here; the read must not raise on the BOM.
    path.write_text(json.dumps({"metrics": []}), encoding="utf-8-sig")

    config = AnalysisMetricsConfig()
    # Either outcome is acceptable as long as it is not a decode failure.
    result = config.load_from_json(str(path))
    assert result in (True, False)


def test_csv_reader_handles_utf8(tmp_path: Path):
    path = tmp_path / "events.csv"
    path.write_text("Event,Onset,Offset\n攻撃,1.0,2.0\n", encoding="utf-8")

    rows = FileManager().load_csv(path)

    assert rows is not None
    assert rows[0]["Event"] == "攻撃"
