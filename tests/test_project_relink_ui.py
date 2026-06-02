"""PR-S3-3: relink prompt wiring in ProjectController (GUI calls mocked).

The model-level relink is covered by test_project_relink.py. Here we only check
that the controller drives it correctly: it asks before doing anything, opens a
file dialog per missing video, and relinks the chosen file.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QFileDialog, QMessageBox

from controllers.project_controller import ProjectController
from models.project_model import ProjectModel
from utils.file_manager import FileManager


def _controller_with_model(model):
    """Build a ProjectController without running its heavy __init__."""
    controller = ProjectController.__new__(ProjectController)
    controller._model = model
    controller._view = None  # GUI calls are monkeypatched away
    controller.logger = logging.getLogger("test")
    controller._update_view_with_project_info = lambda: None
    return controller


def _project_with_external_video(tmp_path):
    model = ProjectModel(FileManager())
    model.create_project(str(tmp_path), "P")
    video = tmp_path / "ext.mp4"
    video.write_bytes(b"video-bytes")
    assert model.add_video(str(video), copy_to_project=False) is True
    return model, video


def test_no_missing_never_prompts(tmp_path, qt_app, monkeypatch):
    model, _video = _project_with_external_video(tmp_path)
    controller = _controller_with_model(model)

    calls = {"q": 0}
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: calls.__setitem__("q", calls["q"] + 1) or QMessageBox.Yes,
    )
    controller._check_and_offer_relink()
    assert calls["q"] == 0  # nothing missing -> never asked


def test_missing_relinks_via_prompt(tmp_path, qt_app, monkeypatch):
    model, video = _project_with_external_video(tmp_path)
    original_id = model.get_video_id(str(video))

    moved = tmp_path / "moved" / "ext.mp4"
    moved.parent.mkdir()
    video.rename(moved)
    assert model.get_missing_videos() == [str(video)]

    controller = _controller_with_model(model)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **k: (str(moved), "")
    )

    controller._check_and_offer_relink()

    assert model.get_missing_videos() == []
    assert str(moved) in model.get_videos()
    assert model.get_video_id(str(moved)) == original_id  # id preserved


def test_missing_user_declines(tmp_path, qt_app, monkeypatch):
    model, video = _project_with_external_video(tmp_path)
    moved = tmp_path / "moved.mp4"
    video.rename(moved)

    controller = _controller_with_model(model)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    opened = {"n": 0}
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        lambda *a, **k: opened.__setitem__("n", 1) or ("", ""),
    )

    controller._check_and_offer_relink()
    assert opened["n"] == 0  # declined -> file dialog never opened
    assert str(video) in model.get_videos()  # unchanged


def test_mismatch_requires_confirmation(tmp_path, qt_app, monkeypatch):
    model, video = _project_with_external_video(tmp_path)
    # A decoy file with different content.
    decoy = tmp_path / "decoy.mp4"
    decoy.write_bytes(b"totally-different-content")
    video.unlink()  # make the original go missing

    controller = _controller_with_model(model)
    # First question (locate now?) = Yes; second (relink anyway?) = No.
    answers = iter([QMessageBox.Yes, QMessageBox.No])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: next(answers))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.No)
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **k: (str(decoy), "")
    )

    controller._check_and_offer_relink()
    # Mismatch + declined force -> not relinked.
    assert str(decoy) not in model.get_videos()
