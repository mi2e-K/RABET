"""Tests for ``ProjectModel`` covering create / load / video-id stability."""
from __future__ import annotations

import pytest

from models.project_model import ProjectModel
from utils.file_manager import FileManager


@pytest.fixture()
def project_model(qt_app):
    fm = FileManager()
    return ProjectModel(fm)


def test_create_project_creates_subdirectories(project_model, tmp_path):
    """Project creation must lay out the expected subdirectories."""
    parent = tmp_path / "Projects"
    parent.mkdir()

    assert project_model.create_project(str(parent), "MouseStudy") is True

    project_dir = parent / "MouseStudy"
    assert project_dir.is_dir()
    for sub in ("videos", "annotations", "action_maps", "analyses"):
        assert (project_dir / sub).is_dir(), f"Missing subdir: {sub}"
    assert (project_dir / "project.json").exists()


def test_load_project_round_trip(project_model, tmp_path):
    """Create, load and verify the persisted project metadata."""
    parent = tmp_path / "Projects"
    parent.mkdir()
    assert project_model.create_project(str(parent), "RoundTrip",
                                        description="Smoke test")

    # Use a fresh model to ensure data really came from disk.
    fresh = ProjectModel(FileManager())
    assert fresh.load_project(str(parent / "RoundTrip")) is True
    config = fresh._project_config
    assert config.get("name") == "RoundTrip"
    assert config.get("description") == "Smoke test"
    assert config.get("videos") == []
    assert config.get("annotations") == []


def test_create_project_rejects_existing_dir(project_model, tmp_path):
    """Re-using an existing project name must fail cleanly."""
    parent = tmp_path / "Projects"
    parent.mkdir()
    assert project_model.create_project(str(parent), "Dup") is True
    assert project_model.create_project(str(parent), "Dup") is False


def test_video_id_is_stable_for_same_path(project_model):
    """``_get_video_id`` must be deterministic for a given path."""
    path = "/some/where/mouse.mp4"
    a = project_model._get_video_id(path)
    b = project_model._get_video_id(path)
    assert a == b
    # And different paths must yield different IDs.
    c = project_model._get_video_id("/other/mouse.mp4")
    assert a != c
