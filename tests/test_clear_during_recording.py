"""Clearing annotations during a recording discards the whole session.

Clear used to empty the event list while the recording kept running, so
the session lost its RecordingStart marker and the next save wrote a file
the analysis could not place in time. It now stops the session without
saving (the reset already offered after rewinding before the recording
start); Import waits for the recording to end.
"""

from __future__ import annotations

import logging

import PySide6.QtWidgets as QtWidgets
from PySide6.QtWidgets import QFileDialog, QMessageBox

from controllers.annotation_controller import AnnotationController
from models.action_map_model import ActionMapModel
from models.annotation_model import AnnotationModel, BehaviorEvent

Yes = QMessageBox.StandardButton.Yes
No = QMessageBox.StandardButton.No


class _FakeVideo:
    def __init__(self, position=5000):
        self.playing = True
        self.position = position

    def is_playing(self):
        return self.playing

    def pause(self):
        self.playing = False

    def get_position(self):
        return self.position


class _FakeRecordingPanel:
    def __init__(self):
        self.state = "recording"

    def set_idle_state(self):
        self.state = "idle"


class _FakeMainWindow:
    def __init__(self):
        self.status = None
        self.recording_control_view = _FakeRecordingPanel()

    def set_status_message(self, message):
        self.status = message


class _FakeTimeline:
    def __init__(self):
        self.events = None

    def set_events(self, events):
        self.events = list(events)


class _FakeTimer:
    def __init__(self):
        self.running = True

    def start(self):
        self.running = True

    def stop(self):
        self.running = False


def _controller(*, recording=True):
    ctrl = AnnotationController.__new__(AnnotationController)
    ctrl.logger = logging.getLogger("test.clear_during_recording")
    ctrl._annotation_model = AnnotationModel(ActionMapModel())
    ctrl._video_model = _FakeVideo()
    ctrl._timeline_view = _FakeTimeline()
    ctrl._main_window = _FakeMainWindow()
    ctrl._recording_timer = _FakeTimer()
    ctrl._key_press_times = {}
    ctrl._is_recording = recording
    ctrl._is_recording_paused = False
    ctrl._frame_duration_ms = 33
    ctrl._skip_auto_export = False
    ctrl._preserve_annotations_on_rewind = False
    ctrl._project_mode = False
    ctrl._project_model = None
    ctrl._current_video_id = None
    ctrl._annotations_dirty = False
    ctrl._suppress_annotation_dirty = False
    ctrl.saves = []
    ctrl._auto_save_annotations = lambda: ctrl.saves.append(True)

    model = ctrl._annotation_model
    model.add_recording_start_event(BehaviorEvent("R", "RecordingStart", 1000, 1000))
    model._events.append(BehaviorEvent("a", "Attack bites", 2000, 3000))
    model.start_event("a", 4000)  # a key still held down
    assert model.get_active_events()
    return ctrl


def _answer(monkeypatch, answer):
    asked = []

    def question(_parent, title, text, buttons=None, default=None):
        asked.append((title, text, default))
        return answer

    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    return asked


def _assert_reset(ctrl):
    assert ctrl._is_recording is False
    assert ctrl._recording_timer.running is False
    assert ctrl._main_window.recording_control_view.state == "idle"
    assert ctrl._video_model.playing is False
    assert ctrl.saves == []  # discarded, not auto-saved
    assert ctrl._skip_auto_export is False  # the next real stop saves again
    assert ctrl._annotation_model.get_all_events() == []
    assert ctrl._annotation_model.get_active_events() == {}
    assert ctrl._timeline_view.events == []
    assert "Recording session reset" in ctrl._main_window.status


def test_clear_during_recording_discards_the_session(monkeypatch):
    ctrl = _controller()
    asked = _answer(monkeypatch, Yes)

    ctrl.clear_annotations()

    (title, text, default), = asked
    assert "recording session is in progress" in text
    assert "without saving" in text
    assert default == No
    _assert_reset(ctrl)


def test_declining_keeps_the_recording_and_its_events(monkeypatch):
    ctrl = _controller()
    _answer(monkeypatch, No)

    ctrl.clear_annotations()

    assert ctrl._is_recording is True
    assert ctrl._main_window.recording_control_view.state == "recording"
    assert [e.behavior for e in ctrl._annotation_model.get_all_events()] == [
        "RecordingStart", "Attack bites",
    ]
    assert ctrl.saves == []


def test_clear_while_not_recording_is_unchanged(monkeypatch):
    ctrl = _controller(recording=False)
    asked = _answer(monkeypatch, Yes)

    ctrl.clear_annotations()

    assert asked == [(
        "Clear Annotations", "Are you sure you want to clear all annotations?", None,
    )]
    assert ctrl._annotation_model.get_all_events() == []
    assert ctrl._main_window.recording_control_view.state == "recording"  # untouched
    assert ctrl.saves == []


def test_rewind_before_the_start_still_resets_the_session(qt_app, monkeypatch):
    class _AnswerYes(QMessageBox):
        def __init__(self, _parent=None):
            super().__init__()

        def exec(self):
            return Yes

    monkeypatch.setattr(QtWidgets, "QMessageBox", _AnswerYes)
    ctrl = _controller()

    assert ctrl.remove_future_annotations(current_position=500) is True
    _assert_reset(ctrl)


def test_import_waits_for_the_recording_to_end(monkeypatch):
    ctrl = _controller()
    notices = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda _parent, title, text: notices.append(text)),
    )
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("picker opened"))),
    )

    ctrl.import_annotations_dialog()

    assert notices and "recording session is in progress" in notices[0]
    assert ctrl._is_recording is True
    assert len(ctrl._annotation_model.get_all_events()) == 2
