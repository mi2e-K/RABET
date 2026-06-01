"""Tests for ProjectModel create/save robustness (BUG-007, 1.3.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from models.project_model import ProjectModel
from utils.file_manager import FileManager


class _FailingFileManager(FileManager):
    """FileManager whose JSON save always fails (simulated disk error)."""

    def save_json(self, *args, **kwargs):
        return False


def test_create_project_fails_when_manifest_write_fails(tmp_path: Path, qt_app):
    model = ProjectModel(_FailingFileManager())

    created = []
    errors = []
    model.project_created.connect(created.append)
    model.error_occurred.connect(errors.append)

    ok = model.create_project(str(tmp_path), "MyProject")

    assert ok is False                      # not reported as success
    assert model.is_project_open() is False  # not in "open" state
    assert created == []                     # no project_created signal
    assert errors                            # an error was surfaced
    # The half-created directory was rolled back so a retry is not blocked.
    assert not (tmp_path / "MyProject").exists()


def test_create_project_succeeds_with_working_file_manager(tmp_path: Path, qt_app):
    model = ProjectModel(FileManager())

    ok = model.create_project(str(tmp_path), "MyProject")

    assert ok is True
    assert model.is_project_open() is True
    assert (tmp_path / "MyProject" / "project.json").exists()
