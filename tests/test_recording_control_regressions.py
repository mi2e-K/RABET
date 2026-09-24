"""Regressions in the recording-control flow.

- a seek during playback no longer leaves the recording paused while the
  video plays (the play half of the seek's pause/play pair was swallowed by
  the synchronisation guard);
- a playback tick delivered between a seek request and its landing no longer
  consumes the seek intent, so a user rewind with "Preserve on rewind" off
  deletes the future annotations every time;
- answering "load existing annotations" still offers to keep unsaved ones;
- closing a project stops a running recording first;
- the "already active" notice is shown only for a key that really is active;
- rewinding exactly onto a state event's onset removes it instead of leaving
  a zero-length (point-like) event.
"""

from __future__ import annotations

import logging
import time
import types

from PySide6.QtWidgets import QMessageBox

from controllers.annotation_controller import AnnotationController
from controllers.project_controller import ProjectController
from models.action_map_model import ActionMapModel
from models.annotation_model import AnnotationModel, BehaviorEvent


class _FakeVideo:
    def __init__(self, playing=True, position=1000):
        self.playing = playing
        self.position = position

    def is_playing(self):
        return self.playing

    def get_position(self):
        return self.position

    def get_duration(self):
        return 60_000


class _FakeRecordingPanel:
    def __init__(self):
        self.state = "recording"

    def set_paused_state(self):
        self.state = "paused"

    def resume_recording(self):
        self.state = "recording"

    def update_progress(self, _remaining_seconds):
        pass


class _FakeMainWindow:
    def __init__(self):
        self.status = None
        self.recording_control_view = _FakeRecordingPanel()
        self.video_player_view = types.SimpleNamespace(is_frame_by_frame_mode=lambda: False)

    def set_status_message(self, message):
        self.status = message

    def status_message_text(self):
        return self.status or ""


class _FakeTimeline:
    def set_events(self, _events):
        pass

    def set_position(self, _position):
        pass

    def should_update(self):
        return True


class _FakeTimer:
    def __init__(self):
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False


def _controller(action_map=None, *, playing=True, position=1000):
    action_map = action_map or ActionMapModel()
    ctrl = AnnotationController.__new__(AnnotationController)
    ctrl.logger = logging.getLogger("test.annotation_controller")
    ctrl._annotation_model = AnnotationModel(action_map)
    ctrl._video_model = _FakeVideo(playing=playing, position=position)
    ctrl._timeline_view = _FakeTimeline()
    ctrl._main_window = _FakeMainWindow()
    ctrl._recording_timer = _FakeTimer()
    ctrl._state_sync_timer = _FakeTimer()
    ctrl._synchronizing_states = False
    ctrl._key_press_times = {}
    ctrl._is_recording = True
    ctrl._is_recording_paused = False
    ctrl._recording_start_position = 0
    ctrl._recording_duration = 600
    ctrl._frame_duration_ms = 33
    ctrl._last_position = position
    ctrl._preserve_annotations_on_rewind = False
    ctrl._skip_next_seek_rewind = False
    ctrl._pending_seek_origin = None
    ctrl._project_mode = False
    ctrl._project_model = None
    ctrl._current_video_id = None
    ctrl._annotations_dirty = False
    ctrl._suppress_annotation_dirty = False
    return ctrl


def _mapped(*keys):
    action_map = ActionMapModel()
    for key in keys:
        action_map.add_mapping(key, f"Behaviour {key}")
    return action_map


# -------------------------------------------------------------------- #
# Recording / playback synchronisation
# -------------------------------------------------------------------- #


def test_seek_during_playback_leaves_the_recording_running():
    ctrl = _controller()
    video = ctrl._video_model

    # The worker's seek: pause, land, play again a few milliseconds later.
    video.playing = False
    ctrl._on_playback_state_changed(False)
    video.playing = True
    ctrl._on_playback_state_changed(True)  # arrives inside the guard
    assert ctrl._is_recording_paused

    ctrl._complete_state_synchronization()  # guard timer fires

    assert ctrl._is_recording_paused is False
    assert ctrl._main_window.recording_control_view.state == "recording"
    assert ctrl._main_window.status == "Recording resumed"


def test_seek_pause_still_finalises_held_keys_at_the_pre_seek_position():
    ctrl = _controller(_mapped("z"), position=4000)
    ctrl._annotation_model.start_event("z", 3000)
    # The key has been held for a second of wall time (end_event clamps
    # sub-frame holds to one frame).
    ctrl._annotation_model.get_active_events()["z"].system_onset_time -= 1.0
    ctrl._key_press_times["z"] = (3000, time.monotonic())

    ctrl._video_model.playing = False
    ctrl._on_playback_state_changed(False)
    ctrl._video_model.playing = True
    ctrl._on_playback_state_changed(True)
    ctrl._complete_state_synchronization()

    events = ctrl._annotation_model.get_all_events()
    assert [(e.onset, e.offset) for e in events] == [(3000, 4000)]
    assert ctrl._annotation_model.get_active_events() == {}


def test_resume_keeps_a_message_posted_after_the_pause():
    ctrl = _controller()
    ctrl._video_model.playing = False
    ctrl._on_playback_state_changed(False)
    ctrl._main_window.set_status_message(
        "Removed 1 and truncated 0 annotation(s) after rewinding"
    )
    ctrl._video_model.playing = True
    ctrl._complete_state_synchronization()

    assert ctrl._is_recording_paused is False
    assert ctrl._main_window.status.startswith("Removed 1")


def test_pause_that_arrived_inside_the_guard_is_applied():
    ctrl = _controller()
    ctrl._synchronizing_states = True
    ctrl._video_model.playing = False
    ctrl._on_playback_state_changed(False)  # swallowed by the guard

    ctrl._complete_state_synchronization()

    assert ctrl._is_recording_paused is True


# -------------------------------------------------------------------- #
# Seek intent vs. playback ticks
# -------------------------------------------------------------------- #


def _with_future_events(ctrl):
    ctrl._annotation_model._events.append(BehaviorEvent("z", "Behaviour z", 1000, 2000))
    ctrl._annotation_model._events.append(BehaviorEvent("z", "Behaviour z", 5000, 6000))
    ctrl._update_recording_time_display = lambda: None
    return ctrl


def test_tick_before_the_seek_lands_does_not_consume_the_intent():
    ctrl = _with_future_events(_controller(_mapped("z"), position=7000))

    ctrl.notify_seek_intent("user")
    ctrl.on_position_changed(7033)  # a playback tick queued before the seek ran
    ctrl.on_position_changed(3000)  # the rewind lands

    remaining = ctrl._annotation_model.get_all_events()
    assert [e.onset for e in remaining] == [1000]


def test_forward_step_while_paused_consumes_the_intent():
    ctrl = _controller(playing=False, position=7000)

    ctrl.notify_seek_intent("step")
    ctrl.on_position_changed(7033)

    assert ctrl._pending_seek_origin is None


def test_stale_intent_is_dropped_instead_of_applied():
    ctrl = _with_future_events(_controller(_mapped("z"), position=7000))

    ctrl.notify_seek_intent("user")
    ctrl._pending_seek_time = time.monotonic() - 60
    ctrl.on_position_changed(3000)

    assert len(ctrl._annotation_model.get_all_events()) == 2
    assert ctrl._pending_seek_origin is None


def test_rewind_onto_an_onset_removes_the_event_instead_of_zeroing_it():
    ctrl = _controller(_mapped("z"), position=7000)
    ctrl._annotation_model._events.append(BehaviorEvent("z", "Behaviour z", 1000, 2000))
    ctrl._annotation_model._events.append(BehaviorEvent("z", "Behaviour z", 3000, 4000))
    ctrl._update_recording_time_display = lambda: None

    ctrl.notify_seek_intent("user")
    ctrl.on_position_changed(3000)

    assert [(e.onset, e.offset) for e in ctrl._annotation_model.get_all_events()] == [
        (1000, 2000)
    ]


# -------------------------------------------------------------------- #
# Key press notices
# -------------------------------------------------------------------- #


def test_unmapped_key_is_ignored_without_an_already_active_notice():
    ctrl = _controller()
    ctrl.on_key_pressed("=")
    assert ctrl._main_window.status is None


def test_duplicate_press_of_an_active_key_is_reported():
    ctrl = _controller(_mapped("z"))
    ctrl.on_key_pressed("z")
    ctrl.on_key_pressed("z")
    assert "already active" in ctrl._main_window.status


# -------------------------------------------------------------------- #
# "Load existing annotations?" -> Yes with unsaved annotations in memory
# -------------------------------------------------------------------- #


def _loading_controller(tmp_path, monkeypatch, *, unsaved, discard_answer):
    ctrl = _controller(_mapped("z"))
    ctrl._is_recording = False
    ctrl._project_mode = True
    saved = tmp_path / "b_annotations.csv"
    saved.write_text("Event,Onset,Offset\n")
    ctrl._auto_export_path = str(saved)
    if unsaved:
        ctrl._annotation_model._events.append(BehaviorEvent("z", "Behaviour z", 1000, 2000))
        ctrl._annotations_dirty = True
    loaded = []
    ctrl._replace_annotations_from_file = lambda path: loaded.append(path) or True
    answers = {
        "Existing Annotations": QMessageBox.StandardButton.Yes,
        "Discard Unsaved Annotations?": discard_answer,
    }
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda _parent, title, *a, **k: answers[title]),
    )
    return ctrl, loaded


def test_loading_existing_annotations_can_keep_unsaved_ones(tmp_path, monkeypatch):
    ctrl, loaded = _loading_controller(
        tmp_path, monkeypatch, unsaved=True, discard_answer=QMessageBox.StandardButton.No
    )
    ctrl._on_video_loaded("/videos/b.mp4")

    assert loaded == []
    assert len(ctrl._annotation_model.get_all_events()) == 1


def test_loading_existing_annotations_after_discarding_unsaved_ones(tmp_path, monkeypatch):
    ctrl, loaded = _loading_controller(
        tmp_path, monkeypatch, unsaved=True, discard_answer=QMessageBox.StandardButton.Yes
    )
    ctrl._on_video_loaded("/videos/b.mp4")

    assert loaded == [ctrl._auto_export_path]


def test_loading_existing_annotations_without_unsaved_ones_needs_no_extra_prompt(
    tmp_path, monkeypatch
):
    ctrl, loaded = _loading_controller(
        tmp_path, monkeypatch, unsaved=False, discard_answer=None
    )
    ctrl._on_video_loaded("/videos/b.mp4")

    assert loaded == [ctrl._auto_export_path]


# -------------------------------------------------------------------- #
# Closing a project during a recording
# -------------------------------------------------------------------- #


def _closing_project(*, recording, unsaved):
    calls = []
    state = {"recording": recording, "unsaved": unsaved}

    def _stop():
        calls.append("stop")
        state["recording"] = False

    annotation = types.SimpleNamespace(
        is_recording=lambda: state["recording"],
        stop_timed_recording=_stop,
        has_unsaved_annotations=lambda: state["unsaved"],
        export_annotations_dialog=lambda: calls.append("export"),
    )
    ctrl = ProjectController.__new__(ProjectController)
    ctrl.logger = logging.getLogger("test.project_controller")
    ctrl._annotation_controller = annotation
    ctrl._view = None
    ctrl._model = types.SimpleNamespace(
        is_modified=lambda: False,
        close_project=lambda: calls.append("close"),
    )
    return ctrl, calls


def test_closing_a_project_stops_the_recording_first():
    ctrl, calls = _closing_project(recording=True, unsaved=False)
    ctrl.on_close_project_requested()
    assert calls == ["stop", "close"]


def test_closing_a_project_can_be_cancelled_over_unsaved_annotations(monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel),
    )
    ctrl, calls = _closing_project(recording=False, unsaved=True)
    ctrl.on_close_project_requested()
    assert calls == []
