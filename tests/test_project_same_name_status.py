"""Annotation status of same-name videos survives a project reload.

Two videos that share a file name (``a/mouse.mp4`` and ``b/mouse.mp4``) get
distinct annotation files (``mouse_annotations.csv`` and
``mouse_2_annotations.csv``). The status recomputed on load matched files to
videos by name only, could not tie either file to its video, and reset both
to "not annotated".
"""

from __future__ import annotations

import logging
from pathlib import Path

from models.project_model import ProjectModel
from utils.file_manager import FileManager


def _project_with_same_name_videos(tmp_path):
    model = ProjectModel(FileManager())
    assert model.create_project(str(tmp_path), "P")
    root = Path(model.get_project_path())
    videos = []
    for folder in ("a", "b"):
        (tmp_path / folder).mkdir()
        video = tmp_path / folder / "mouse.mp4"
        video.write_bytes(b"video-bytes")
        assert model.add_video(str(video), copy_to_project=False)
        videos.append(video)
    return model, root, videos


def _record_annotation(model, root, video):
    rel_path = model.get_annotation_relative_path_for_video(str(video))
    full_path = root / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text("Event,Onset,Offset\n", encoding="utf-8")
    assert model.add_annotation(str(full_path), False, True)
    return rel_path


def test_same_name_videos_keep_their_status_after_reload(qt_app, tmp_path):
    logging.disable(logging.WARNING)
    try:
        model, root, videos = _project_with_same_name_videos(tmp_path)
        rel_paths = [_record_annotation(model, root, video) for video in videos]
        assert Path(rel_paths[1]).name == "mouse_2_annotations.csv"
        assert model.get_annotated_video_count() == 2
        assert model.save_project()

        reloaded = ProjectModel(FileManager())
        assert reloaded.load_project(str(root))
    finally:
        logging.disable(logging.NOTSET)

    statuses = reloaded.get_video_annotation_status()
    assert sorted(statuses.values()) == ["annotated", "annotated"]
    assert reloaded.get_annotated_video_count() == 2


def test_only_the_recorded_same_name_video_is_annotated(qt_app, tmp_path):
    logging.disable(logging.WARNING)
    try:
        model, root, videos = _project_with_same_name_videos(tmp_path)
        _record_annotation(model, root, videos[1])  # only b/mouse.mp4
        assert model.save_project()

        reloaded = ProjectModel(FileManager())
        assert reloaded.load_project(str(root))
    finally:
        logging.disable(logging.NOTSET)

    assert reloaded.get_video_annotation_status(str(videos[0])) == "not_annotated"
    assert reloaded.get_video_annotation_status(str(videos[1])) == "annotated"
