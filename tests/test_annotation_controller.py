"""Controller-level tests for AnnotationController press tracking (1.3.4).

These avoid the full Qt signal wiring by constructing the controller via
``__new__`` and setting only the attributes ``on_key_pressed`` touches, with
lightweight fakes. This keeps the BUG-010 regression fast and headless.
"""

from __future__ import annotations

import logging
import types

from controllers.annotation_controller import AnnotationController
from models.action_map_model import ActionMapModel
from models.annotation_model import AnnotationModel, BehaviorEvent


class _FakeVideo:
    def __init__(self):
        self._playing = True

    def is_playing(self):
        return self._playing

    def get_position(self):
        return 1000

    def get_duration(self):
        return 10000


class _FakeTimeline:
    def __init__(self):
        self.events = None
        self.position = None

    def set_events(self, events):
        self.events = events

    def set_position(self, position):
        self.position = position

    def should_update(self):
        return True
    # Deliberately no ``ensure_controls_visible`` so on_position_changed skips
    # the QTimer block (the controller is built via __new__ in these tests and
    # is not a fully-initialised QObject).


class _FakeMainWindow:
    def __init__(self):
        self.status = None
        # video_player_view with FBF off
        self.video_player_view = types.SimpleNamespace(
            is_frame_by_frame_mode=lambda: False
        )

    def set_status_message(self, msg):
        self.status = msg


def _make_controller(action_map):
    """Build an AnnotationController without running __init__/signal wiring."""
    ctrl = AnnotationController.__new__(AnnotationController)
    ctrl.logger = logging.getLogger("test.annotation_controller")
    ctrl._annotation_model = AnnotationModel(action_map)
    ctrl._video_model = _FakeVideo()
    ctrl._timeline_view = _FakeTimeline()
    ctrl._main_window = _FakeMainWindow()
    ctrl._key_press_times = {}
    ctrl._is_recording = True
    ctrl._is_recording_paused = False
    ctrl._frame_duration_ms = 33
    ctrl._project_mode = False
    ctrl._project_model = None
    ctrl._current_video_id = None
    return ctrl


def test_unmapped_key_does_not_leave_press_tracking():
    action_map = ActionMapModel()
    ctrl = _make_controller(action_map)

    # '=' is not mapped; start_event will refuse it.
    ctrl.on_key_pressed("=")

    assert ctrl._key_press_times == {}
    assert ctrl._annotation_model.get_active_events() == {}


def test_mapped_key_records_press_tracking():
    action_map = ActionMapModel()
    action_map.add_mapping("z", "Test behavior")
    ctrl = _make_controller(action_map)

    ctrl.on_key_pressed("z")

    assert "z" in ctrl._key_press_times
    assert "z" in ctrl._annotation_model.get_active_events()


# -------------------------------------------------------------------- #
# Seek-intent model: rewind only deletes on an explicit user seek
# -------------------------------------------------------------------- #


def _make_recording_controller_with_events(action_map):
    """Controller in an active recording session with two completed events."""
    ctrl = _make_controller(action_map)
    ctrl._preserve_annotations_on_rewind = False
    ctrl._skip_next_seek_rewind = False
    ctrl._pending_seek_origin = None
    ctrl._last_position = 7000
    # Paused so on_position_changed skips _update_recording_time_display (which
    # needs more recording state); rewind deletion is not gated on pause.
    ctrl._is_recording_paused = True
    # Two completed events; the second one (onset 5000) is "in the future"
    # relative to a rewind to 3000ms and would be deleted by a user rewind.
    ctrl._annotation_model._events.append(
        BehaviorEvent("z", "Test behavior", 1000, 2000)
    )
    ctrl._annotation_model._events.append(
        BehaviorEvent("z", "Test behavior", 5000, 6000)
    )
    return ctrl


def test_step_backward_with_preserve_off_deletes_future():
    action_map = ActionMapModel()
    action_map.add_mapping("z", "Test behavior")
    ctrl = _make_recording_controller_with_events(action_map)  # preserve OFF

    # Frame steps now honour the Preserve toggle just like the slider: with
    # preservation OFF, a backward step removes the future event.
    ctrl.notify_seek_intent("step")
    ctrl.on_position_changed(3000)

    remaining = ctrl._annotation_model.get_all_events()
    assert len(remaining) == 1
    assert remaining[0].onset == 1000


def test_step_backward_with_preserve_on_keeps():
    action_map = ActionMapModel()
    action_map.add_mapping("z", "Test behavior")
    ctrl = _make_recording_controller_with_events(action_map)
    ctrl._preserve_annotations_on_rewind = True

    # Preserve ON: a backward step keeps everything (the toggle wins).
    ctrl.notify_seek_intent("step")
    ctrl.on_position_changed(3000)

    assert len(ctrl._annotation_model.get_all_events()) == 2


def test_user_slider_rewind_during_recording_deletes_future_events():
    action_map = ActionMapModel()
    action_map.add_mapping("z", "Test behavior")
    ctrl = _make_recording_controller_with_events(action_map)

    # Explicit slider seek tags "user": with preservation off, the future
    # event (onset 5000 > 3000) is removed; the past event survives.
    ctrl.notify_seek_intent("user")
    ctrl.on_position_changed(3000)

    remaining = ctrl._annotation_model.get_all_events()
    assert len(remaining) == 1
    assert remaining[0].onset == 1000


def test_plain_playback_backward_does_not_delete():
    action_map = ActionMapModel()
    action_map.add_mapping("z", "Test behavior")
    ctrl = _make_recording_controller_with_events(action_map)

    # No intent tagged (ordinary playback position update): never deletes,
    # even on an (unexpected) backward jump.
    ctrl.on_position_changed(3000)

    assert len(ctrl._annotation_model.get_all_events()) == 2


def test_user_rewind_with_preserve_on_keeps_events():
    action_map = ActionMapModel()
    action_map.add_mapping("z", "Test behavior")
    ctrl = _make_recording_controller_with_events(action_map)
    ctrl._preserve_annotations_on_rewind = True

    ctrl.notify_seek_intent("user")
    ctrl.on_position_changed(3000)

    assert len(ctrl._annotation_model.get_all_events()) == 2


# -------------------------------------------------------------------- #
# Unified active-event cleanup (BUG-002 / BUG-008)
# -------------------------------------------------------------------- #


def test_finalize_active_events_closes_fbf_event():
    action_map = ActionMapModel()
    action_map.add_mapping("z", "Test behavior")
    ctrl = _make_controller(action_map)

    # Simulate a frame-by-frame event: started via the model directly, so it
    # lives in _active_events but NOT in _key_press_times.
    ctrl._annotation_model.start_event("z", 1000)
    assert "z" in ctrl._annotation_model.get_active_events()
    assert ctrl._key_press_times == {}  # FBF never tracks press times

    ended = ctrl._finalize_active_events(end_position=2000)

    # The FBF event is finalised (not stranded) and exported correctly.
    assert ended == 1
    assert ctrl._annotation_model.get_active_events() == {}
    completed = ctrl._annotation_model.get_all_events()
    assert len(completed) == 1
    assert completed[0].offset >= completed[0].onset + ctrl._frame_duration_ms


def test_finalize_active_events_enforces_min_duration():
    action_map = ActionMapModel()
    action_map.add_mapping("z", "Test behavior")
    ctrl = _make_controller(action_map)

    ctrl._annotation_model.start_event("z", 5000)
    # End at a position before the onset -> clamped to onset + one frame.
    ended = ctrl._finalize_active_events(end_position=1000)

    assert ended == 1
    ev = ctrl._annotation_model.get_all_events()[0]
    assert ev.offset == 5000 + ctrl._frame_duration_ms


# -------------------------------------------------------------------- #
# One CSV = one session (§16-1 / BUG-014)
# -------------------------------------------------------------------- #


def _make_session_guard_controller(action_map, dirty):
    ctrl = _make_controller(action_map)
    ctrl._annotations_dirty = dirty
    ctrl._suppress_annotation_dirty = False
    # Pre-existing annotations from a prior session.
    ctrl._annotation_model._events.append(
        BehaviorEvent("R", "RecordingStart", 0, 0)
    )
    ctrl._annotation_model._events.append(
        BehaviorEvent("z", "Test behavior", 1000, 2000)
    )
    return ctrl


def test_new_session_guard_empty_is_ok(monkeypatch):
    action_map = ActionMapModel()
    ctrl = _make_controller(action_map)
    assert ctrl._confirm_replace_annotations_for_new_session() is True


def test_new_session_guard_saved_confirm_yes_clears(monkeypatch):
    import controllers.annotation_controller as mod

    action_map = ActionMapModel()
    action_map.add_mapping("z", "Test behavior")
    ctrl = _make_session_guard_controller(action_map, dirty=False)

    monkeypatch.setattr(
        mod.QMessageBox, "question",
        staticmethod(lambda *a, **k: mod.QMessageBox.StandardButton.Yes),
    )
    assert ctrl._confirm_replace_annotations_for_new_session() is True
    assert ctrl._annotation_model.get_all_events() == []


def test_new_session_guard_saved_confirm_no_keeps(monkeypatch):
    import controllers.annotation_controller as mod

    action_map = ActionMapModel()
    action_map.add_mapping("z", "Test behavior")
    ctrl = _make_session_guard_controller(action_map, dirty=False)

    monkeypatch.setattr(
        mod.QMessageBox, "question",
        staticmethod(lambda *a, **k: mod.QMessageBox.StandardButton.No),
    )
    assert ctrl._confirm_replace_annotations_for_new_session() is False
    assert len(ctrl._annotation_model.get_all_events()) == 2


def test_new_session_guard_dirty_cancel_keeps(monkeypatch):
    import controllers.annotation_controller as mod

    action_map = ActionMapModel()
    action_map.add_mapping("z", "Test behavior")
    ctrl = _make_session_guard_controller(action_map, dirty=True)

    monkeypatch.setattr(
        mod.QMessageBox, "question",
        staticmethod(lambda *a, **k: mod.QMessageBox.StandardButton.Cancel),
    )
    assert ctrl._confirm_replace_annotations_for_new_session() is False
    assert len(ctrl._annotation_model.get_all_events()) == 2


# -------------------------------------------------------------------- #
# Focus loss (§16-3 / BUG-022)
# -------------------------------------------------------------------- #


def _make_focus_controller(action_map, fbf):
    ctrl = _make_controller(action_map)
    ctrl._is_recording = True
    ctrl._is_recording_paused = False
    ctrl._main_window.video_player_view = types.SimpleNamespace(
        is_frame_by_frame_mode=lambda: fbf
    )
    # Stub pause_recording so we don't need the full recording-control view.
    ctrl._paused = False

    def _pause():
        ctrl._paused = True

    ctrl.pause_recording = _pause
    return ctrl


def test_focus_loss_realtime_finalizes_and_pauses():
    action_map = ActionMapModel()
    action_map.add_mapping("z", "Test behavior")
    ctrl = _make_focus_controller(action_map, fbf=False)

    ctrl._annotation_model.start_event("z", 1000)
    assert "z" in ctrl._annotation_model.get_active_events()

    ctrl.on_application_inactive()

    # The in-progress event was finalised and the session paused.
    assert ctrl._annotation_model.get_active_events() == {}
    assert len(ctrl._annotation_model.get_all_events()) == 1
    assert ctrl._paused is True


def test_focus_loss_fbf_keeps_active_event():
    action_map = ActionMapModel()
    action_map.add_mapping("z", "Test behavior")
    ctrl = _make_focus_controller(action_map, fbf=True)

    ctrl._annotation_model.start_event("z", 1000)
    ctrl.on_application_inactive()

    # FBF active event must persist; no pause.
    assert "z" in ctrl._annotation_model.get_active_events()
    assert ctrl._paused is False


def test_focus_loss_no_active_events_is_noop():
    action_map = ActionMapModel()
    action_map.add_mapping("z", "Test behavior")
    ctrl = _make_focus_controller(action_map, fbf=False)

    ctrl.on_application_inactive()
    # Nothing in progress -> do not pause the session.
    assert ctrl._paused is False
