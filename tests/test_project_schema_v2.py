"""PR-S1: project manifest schema v2 on-disk shape (internal repr preserved).

The internal ProjectModel representation (string-list videos + status/files
maps) is unchanged; only the on-disk form becomes v2 (schema_version + one
object per video with embedded id/storage/status/path). A v1 file is migrated
to v2 on load+save.
"""

from __future__ import annotations

import json
from pathlib import Path

from models.project_model import ProjectModel
from utils.file_manager import FileManager


def _model():
    return ProjectModel(FileManager())


def _read_manifest(project_dir: Path):
    return json.loads((project_dir / "project.json").read_text(encoding="utf-8"))


def test_new_project_is_saved_as_v2(tmp_path, qt_app):
    m = _model()
    assert m.create_project(str(tmp_path), "P") is True
    raw = _read_manifest(tmp_path / "P")
    assert raw.get("schema_version") == 2
    assert isinstance(raw.get("videos"), list)


def test_video_serialised_as_object_with_embedded_status(tmp_path, qt_app):
    m = _model()
    m.create_project(str(tmp_path), "P")
    proj = tmp_path / "P"

    video = tmp_path / "ext.mp4"
    video.write_bytes(b"x")
    assert m.add_video(str(video), copy_to_project=False) is True
    m.set_video_annotation_status(str(video), "annotated")
    # save_project does not run _update_annotation_status, so the value sticks.
    m.save_project()

    raw = _read_manifest(proj)
    assert raw["schema_version"] == 2
    assert len(raw["videos"]) == 1
    entry = raw["videos"][0]
    assert entry["path"] == str(video)
    assert entry["storage"] == "external"
    assert entry["annotation_status"] == "annotated"
    assert "id" in entry and entry["id"]
    # Top-level maps no longer exist on disk (embedded per-video).
    assert "video_annotation_status" not in raw
    assert "video_annotation_files" not in raw


def test_v1_manifest_loads_and_migrates_to_v2(tmp_path, qt_app):
    proj = tmp_path / "P"
    (proj / "videos").mkdir(parents=True)
    (proj / "annotations").mkdir()
    (proj / "action_maps").mkdir()
    (proj / "analyses").mkdir()
    (proj / "videos" / "mouse.mp4").write_bytes(b"x")

    # Build the v1 video_id the way the model does.
    seed = _model()
    seed._project_path = str(proj)
    vid = seed._get_video_id("videos/mouse.mp4")

    v1 = {
        "name": "P", "description": "", "created_date": "", "modified_date": "",
        "videos": ["videos/mouse.mp4"],
        "annotations": [], "action_maps": [], "analyses": [],
        "video_annotation_status": {vid: "not_annotated"},
        "video_annotation_files": {},
    }
    (proj / "project.json").write_text(json.dumps(v1), encoding="utf-8")

    m = _model()
    assert m.load_project(str(proj)) is True
    # Internal representation: a path list.
    assert m.get_videos() == ["videos/mouse.mp4"]

    # Loading a v1 file re-saves it as v2.
    raw = _read_manifest(proj)
    assert raw["schema_version"] == 2
    assert isinstance(raw["videos"][0], dict)
    assert raw["videos"][0]["path"] == "videos/mouse.mp4"
    assert raw["videos"][0]["storage"] == "copied"


def test_v2_round_trip_preserves_videos(tmp_path, qt_app):
    m = _model()
    m.create_project(str(tmp_path), "P")
    proj = tmp_path / "P"

    video = tmp_path / "ext.mp4"
    video.write_bytes(b"x")
    m.add_video(str(video), copy_to_project=False)
    m.save_project()

    # Reload the (now v2) manifest into a fresh model.
    m2 = _model()
    assert m2.load_project(str(proj)) is True
    assert m2.get_videos() == [str(video)]
    raw = _read_manifest(proj)
    assert raw["schema_version"] == 2
