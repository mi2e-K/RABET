"""PR-S2: UUID-based, move-stable video ids (BUG-006 / §16-5).

The v2 manifest stores each video's id explicitly. Loading rebuilds the
``stored-path -> id`` map, so a copied video keeps the same id (and therefore
its annotation status) even after the whole project folder is relocated — the
exact case that used to break, because the old id embedded the absolute path.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from models.project_model import ProjectModel
from utils.file_manager import FileManager


def _model():
    return ProjectModel(FileManager())


def _manifest(project_dir: Path):
    return json.loads((project_dir / "project.json").read_text(encoding="utf-8"))


def test_add_video_registers_minted_id(tmp_path, qt_app):
    """add_video mints an id and persists it in the path->id map (not the
    legacy absolute-path hash)."""
    m = _model()
    m.create_project(str(tmp_path), "P")

    external = tmp_path / "ext.mp4"
    external.write_bytes(b"x")
    assert m.add_video(str(external), copy_to_project=False) is True

    rel = str(external)
    vid = m._get_video_id(rel)
    assert m._video_id_by_path.get(rel) == vid
    # Minted (uuid suffix) differs from the legacy (sha1 suffix) id.
    assert vid != m._legacy_hash_id(rel)


def test_close_project_clears_id_map(tmp_path, qt_app):
    m = _model()
    m.create_project(str(tmp_path), "P")
    external = tmp_path / "ext.mp4"
    external.write_bytes(b"x")
    m.add_video(str(external), copy_to_project=False)
    assert m._video_id_by_path  # populated

    m.close_project()
    assert m._video_id_by_path == {}


def test_copied_video_id_survives_project_relocation(tmp_path, qt_app):
    """The core BUG-006 fix: a copied video's id and annotation status survive
    moving the whole project folder to a different path."""
    home = tmp_path / "home"
    home.mkdir()
    m = _model()
    m.create_project(str(home), "P")
    proj = home / "P"

    external = tmp_path / "mouse.mp4"
    external.write_bytes(b"video-bytes")
    assert m.add_video(str(external), copy_to_project=True) is True
    rel = os.path.join("videos", "mouse.mp4")
    assert m.get_videos() == [rel]

    # Attach an annotation CSV so the derived status is "annotated" (this is how
    # RABET decides annotated: by matching an annotation file to the video).
    ann_rel = os.path.join("annotations", "mouse_annotations.csv")
    (proj / "annotations").mkdir(exist_ok=True)
    (proj / ann_rel).write_text("Behavior,Onset,Offset\n", encoding="utf-8")
    m._project_config["annotations"].append(ann_rel)
    m._update_annotation_status()
    assert m.get_video_annotation_status(rel) == "annotated"
    m.save_project()

    original_id = _manifest(proj)["videos"][0]["id"]
    assert original_id  # non-empty

    # Relocate the entire project folder (move to a new machine / OneDrive path
    # / external disk — the BUG-006 scenario).
    moved = tmp_path / "relocated"
    shutil.move(str(proj), str(moved))

    m2 = _model()
    assert m2.load_project(str(moved)) is True
    assert m2.get_videos() == [rel]
    # The id is unchanged even though project_path is now different...
    assert m2._get_video_id(rel) == original_id
    assert m2.get_video_id(rel) == original_id
    # ...so the annotation is still recognised after the move.
    assert m2.get_video_annotation_status(rel) == "annotated"


def test_v1_load_adopts_legacy_id_into_map(tmp_path, qt_app):
    """A v1 manifest's video adopts its legacy hash id as the persisted id and
    is re-saved in v2 form with that id preserved."""
    proj = tmp_path / "P"
    (proj / "videos").mkdir(parents=True)
    (proj / "annotations").mkdir()
    (proj / "action_maps").mkdir()
    (proj / "analyses").mkdir()
    (proj / "videos" / "mouse.mp4").write_bytes(b"x")

    rel = "videos/mouse.mp4"
    seed = _model()
    seed._project_path = str(proj)
    legacy = seed._get_video_id(rel)

    v1 = {
        "name": "P", "description": "", "created_date": "", "modified_date": "",
        "videos": [rel],
        "annotations": [], "action_maps": [], "analyses": [],
        "video_annotation_status": {legacy: "not_annotated"},
        "video_annotation_files": {},
    }
    (proj / "project.json").write_text(json.dumps(v1), encoding="utf-8")

    m = _model()
    assert m.load_project(str(proj)) is True
    # The legacy id was adopted as the persisted id for this stored path...
    assert m._video_id_by_path.get(rel) == legacy
    # ...and re-saved in v2 form with that id preserved (so it stays stable
    # across later moves).
    raw = _manifest(proj)
    assert raw["schema_version"] == 2
    assert raw["videos"][0]["id"] == legacy
