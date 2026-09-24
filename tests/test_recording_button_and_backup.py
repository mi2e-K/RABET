"""The recording button reads "Stop" once a session runs, and a project
session that replaces a video's annotation file keeps the previous version.
"""

from __future__ import annotations

import logging
import types

from controllers import annotation_controller as annotation_module
from controllers.annotation_controller import AnnotationController
from models.action_map_model import ActionMapModel
from models.annotation_model import AnnotationModel, BehaviorEvent
from views.recording_control_view import RecordingControlView


def test_button_reads_cancel_while_waiting_and_stop_while_recording(qt_app):
    view = RecordingControlView()
    try:
        view.set_waiting_state(300)
        assert view.record_button.text() == "Cancel"

        view.start_recording()
        assert view.record_button.text() == "Stop"

        view.set_paused_state()
        assert view.record_button.text() == "Stop"

        view.set_idle_state()
        assert view.record_button.text() == "Start Recording"
    finally:
        view.deleteLater()


def _exporting_controller(export_path):
    ctrl = AnnotationController.__new__(AnnotationController)
    ctrl.logger = logging.getLogger("test.annotation_controller")
    ctrl._annotation_model = AnnotationModel(ActionMapModel())
    ctrl._annotation_model._events.append(BehaviorEvent("z", "New session", 1000, 2000))
    ctrl._auto_export_path = str(export_path)
    ctrl._project_model = None
    ctrl.config_manager = None
    ctrl._annotations_dirty = True
    ctrl._main_window = types.SimpleNamespace(set_status_message=lambda _msg: None)
    return ctrl


def test_replacing_a_project_annotation_file_keeps_the_previous_version(
    qt_app, tmp_path, monkeypatch
):
    messages = []
    monkeypatch.setattr(
        annotation_module.AutoCloseMessageBox, "information",
        classmethod(lambda cls, _parent, _title, text, timeout=1500: messages.append(text)),
    )
    target = tmp_path / "mouse_annotations.csv"
    target.write_text("previous session\n", encoding="utf-8")

    _exporting_controller(target)._auto_export_annotations()

    backups = list(tmp_path.glob("mouse_annotations.*.csv.bak"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "previous session\n"
    assert "New session" in target.read_text(encoding="utf-8")
    assert backups[0].name in messages[0]
    # Not a .csv, so CSV pickers and the analysis never list it.
    assert [p.name for p in tmp_path.glob("*.csv")] == ["mouse_annotations.csv"]


def test_first_export_of_a_video_makes_no_backup(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(
        annotation_module.AutoCloseMessageBox, "information",
        classmethod(lambda cls, *a, **k: None),
    )
    target = tmp_path / "mouse_annotations.csv"

    _exporting_controller(target)._auto_export_annotations()

    assert target.exists()
    assert list(tmp_path.glob("*.bak")) == []
