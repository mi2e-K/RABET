"""PR-S3: content hash recording + external-video relink (BUG-006 relink path).

Move-stability (PR-S2) covers copied videos. An *external* video referenced by
absolute path can still go missing if it is moved/renamed outside the project;
PR-S3 lets the user relink it, using a partial content hash to confirm the
candidate is the same file. The id is unchanged by relink, so annotation status
and links are preserved.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from models.project_model import ProjectModel
from utils.file_manager import FileManager


def _model():
    return ProjectModel(FileManager())


def _manifest(project_dir):
    return json.loads((Path(project_dir) / "project.json").read_text(encoding="utf-8"))


# --- content hash round-trip (PR-S3-1) -------------------------------------


def test_add_video_records_content_hash(tmp_path, qt_app):
    m = _model()
    m.create_project(str(tmp_path), "P")
    proj = tmp_path / "P"

    video = tmp_path / "ext.mp4"
    video.write_bytes(b"some video bytes")
    assert m.add_video(str(video), copy_to_project=False) is True
    m.save_project()

    entry = _manifest(proj)["videos"][0]
    assert entry.get("content_hash")  # present and non-empty


def test_content_hash_survives_round_trip(tmp_path, qt_app):
    m = _model()
    m.create_project(str(tmp_path), "P")
    proj = tmp_path / "P"
    video = tmp_path / "ext.mp4"
    video.write_bytes(b"some video bytes")
    m.add_video(str(video), copy_to_project=False)
    m.save_project()
    original = _manifest(proj)["videos"][0]["content_hash"]

    m2 = _model()
    assert m2.load_project(str(proj)) is True
    vid = m2.get_video_id(str(video))
    assert m2._project_config["video_content_hash"][vid] == original


# --- missing detection + relink (PR-S3-2) ----------------------------------


def _project_with_external_video(tmp_path, data=b"video-bytes-123"):
    m = _model()
    m.create_project(str(tmp_path), "P")
    video = tmp_path / "ext.mp4"
    video.write_bytes(data)
    assert m.add_video(str(video), copy_to_project=False) is True
    return m, video


def test_get_missing_videos_lists_unresolvable(tmp_path, qt_app):
    m, video = _project_with_external_video(tmp_path)
    assert m.get_missing_videos() == []  # present
    video.unlink()
    assert m.get_missing_videos() == [str(video)]


def test_relink_preserves_id_and_status(tmp_path, qt_app):
    m, video = _project_with_external_video(tmp_path)
    proj = tmp_path / "P"

    # Mark annotated via a matching annotation file.
    ann_rel = os.path.join("annotations", "ext_annotations.csv")
    (proj / "annotations").mkdir(exist_ok=True)
    (proj / ann_rel).write_text("Behavior,Onset,Offset\n", encoding="utf-8")
    m._project_config["annotations"].append(ann_rel)
    m._update_annotation_status()
    assert m.get_video_annotation_status(str(video)) == "annotated"
    original_id = m.get_video_id(str(video))

    # Move the file so the external path now dangles.
    moved = tmp_path / "moved" / "ext.mp4"
    moved.parent.mkdir()
    video.rename(moved)
    assert m.get_missing_videos() == [str(video)]

    assert m.relink_video(str(video), str(moved)) is True
    # videos now points at the new location...
    assert str(moved) in m.get_videos()
    assert str(video) not in m.get_videos()
    # ...id is unchanged, so status stays attached.
    assert m.get_video_id(str(moved)) == original_id
    assert m.get_video_annotation_status(str(moved)) == "annotated"
    assert m.get_missing_videos() == []


def test_relink_verify_hash_rejects_mismatch(tmp_path, qt_app):
    m, video = _project_with_external_video(tmp_path, data=b"original-content")
    decoy = tmp_path / "decoy.mp4"
    decoy.write_bytes(b"totally-different")
    assert m.relink_video(str(video), str(decoy), verify_hash=True) is False
    # Still pointing at the original stored path.
    assert str(video) in m.get_videos()


def test_relink_verify_hash_accepts_match(tmp_path, qt_app):
    data = b"same-content-bytes"
    m, video = _project_with_external_video(tmp_path, data=data)
    twin = tmp_path / "twin.mp4"
    twin.write_bytes(data)  # identical content
    assert m.relink_video(str(video), str(twin), verify_hash=True) is True
    assert str(twin) in m.get_videos()


def test_content_hash_matches_reports(tmp_path, qt_app):
    data = b"abc123"
    m, video = _project_with_external_video(tmp_path, data=data)
    twin = tmp_path / "twin.mp4"
    twin.write_bytes(data)
    other = tmp_path / "other.mp4"
    other.write_bytes(b"different")
    assert m.content_hash_matches(str(video), str(twin)) is True
    assert m.content_hash_matches(str(video), str(other)) is False
