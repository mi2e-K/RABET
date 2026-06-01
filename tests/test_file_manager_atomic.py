"""Tests for FileManager.save_json atomic write (BUG-019, 1.3.4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from utils.file_manager import FileManager


@pytest.fixture
def fm():
    return FileManager()


def test_atomic_save_writes_valid_json(fm, tmp_path: Path):
    target = tmp_path / "data.json"
    assert fm.save_json({"a": 1, "nested": {"b": 2}}, target) is True
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1, "nested": {"b": 2}}


def test_atomic_save_preserves_previous_on_serialisation_failure(fm, tmp_path: Path):
    target = tmp_path / "data.json"
    fm.save_json({"good": True}, target)
    original = target.read_text(encoding="utf-8")

    # A set is not JSON-serialisable -> save fails, but the existing file must
    # be untouched (BUG-019).
    assert fm.save_json({"bad": {1, 2, 3}}, target) is False
    assert target.read_text(encoding="utf-8") == original


def test_atomic_save_writes_backup(fm, tmp_path: Path):
    target = tmp_path / "project.json"
    fm.save_json({"v": 1}, target, backup=True)
    fm.save_json({"v": 2}, target, backup=True)

    # Latest content plus a .bak holding the prior version.
    assert json.loads(target.read_text(encoding="utf-8")) == {"v": 2}
    bak = target.with_name("project.json.bak")
    assert bak.exists()
    assert json.loads(bak.read_text(encoding="utf-8")) == {"v": 1}


def test_atomic_save_leaves_no_temp_files(fm, tmp_path: Path):
    target = tmp_path / "data.json"
    fm.save_json({"x": 1}, target)
    # Only the target file should remain (no .tmp leftovers).
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "data.json"]
    assert leftovers == []
