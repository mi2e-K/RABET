"""Tests for the action-map change guard (1.4.2).

Changing what a key means after a project already holds annotations splits the
dataset, so the user is warned first. The guard must warn on changes that
redefine or remove a key, stay silent on purely additive ones (otherwise it
trains the user to dismiss it), and never fire outside a project.
"""

from __future__ import annotations

import pytest

from controllers.action_map_controller import ActionMapController
from models.action_map_model import ActionMapModel


class _StubView:
    """Minimal stand-in for ActionMapView (no Qt widgets needed)."""

    def __init__(self):
        self.mappings = None

    # Signals the controller connects to.
    class _Signal:
        def connect(self, *_args, **_kwargs):
            return None

    def __getattr__(self, name):
        if name.endswith("_requested"):
            return self._Signal()
        raise AttributeError(name)

    def update_mappings(self, mappings, kinds=None):
        self.mappings = mappings

    def update_active_behaviors(self, *_args):
        return None


class _StubProject:
    def __init__(self, open_=True, annotated=0):
        self._open = open_
        self._annotated = annotated

    def is_project_open(self):
        return self._open

    def get_annotated_video_count(self):
        return self._annotated


@pytest.fixture
def controller(qt_app, tmp_path, monkeypatch):
    model = ActionMapModel()
    # Keep every auto-save inside tmp_path rather than the real user config.
    monkeypatch.setattr(model, "_project_map_path", str(tmp_path / "map.json"))
    model._action_map = {"a": "Attack bites", "b": "Chasing"}
    model._behavior_kinds = {"a": "state", "b": "state"}

    ctrl = ActionMapController(model, _StubView())
    return ctrl


def _record_prompts(controller, monkeypatch, answer=True):
    """Record every confirmation dialog the guard actually raises.

    Patches ``QMessageBox.question`` rather than the guard method itself, so
    the real risk assessment (project open? annotations present?) still runs
    and an empty record genuinely means "the user was never interrupted".
    """
    from PySide6.QtWidgets import QMessageBox

    prompts = []
    reply = (
        QMessageBox.StandardButton.Yes if answer else QMessageBox.StandardButton.No
    )

    def fake_question(_parent, title, text, *_args, **_kwargs):
        prompts.append(f"{title}\n{text}")
        return reply

    monkeypatch.setattr(
        "controllers.action_map_controller.QMessageBox.question",
        staticmethod(fake_question),
    )
    return prompts


# --- When the guard should stay silent ---------------------------------


def test_no_guard_without_project_model(controller, monkeypatch):
    prompts = _record_prompts(controller, monkeypatch)
    controller.on_edit_mapping_requested("a", "Renamed", "state")
    assert prompts == []
    assert controller._model.get_behavior("a") == "Renamed"


def test_no_guard_when_project_has_no_annotations(controller, monkeypatch):
    controller.project_model = _StubProject(annotated=0)
    assert controller.annotated_video_count() == 0

    prompts = _record_prompts(controller, monkeypatch)
    controller.on_edit_mapping_requested("a", "Renamed", "state")
    assert prompts == []


def test_no_guard_when_project_closed(controller):
    controller.project_model = _StubProject(open_=False, annotated=5)
    assert controller.annotated_video_count() == 0


def test_adding_a_new_key_is_not_guarded(controller, monkeypatch):
    """Additive changes must not prompt, or the warning loses its meaning."""
    controller.project_model = _StubProject(annotated=3)
    prompts = _record_prompts(controller, monkeypatch)

    controller.on_edit_mapping_requested("z", "Rearing", "state")

    assert prompts == []
    assert controller._model.get_behavior("z") == "Rearing"


def test_reconfirming_the_same_mapping_is_not_guarded(controller, monkeypatch):
    controller.project_model = _StubProject(annotated=3)
    prompts = _record_prompts(controller, monkeypatch)

    controller.on_edit_mapping_requested("a", "Attack bites", "state")

    assert prompts == []


# --- When the guard should fire ----------------------------------------


def test_renaming_an_existing_key_is_guarded(controller, monkeypatch):
    controller.project_model = _StubProject(annotated=3)
    prompts = _record_prompts(controller, monkeypatch)

    controller.on_edit_mapping_requested("a", "Something else", "state")

    assert len(prompts) == 1
    assert "'a'" in prompts[0]
    # The message must state the stakes concretely, not just "are you sure".
    assert "3 videos" in prompts[0]


def test_changing_behaviour_kind_is_guarded(controller, monkeypatch):
    """state <-> point changes what gets recorded, so it counts as a redefinition."""
    controller.project_model = _StubProject(annotated=3)
    prompts = _record_prompts(controller, monkeypatch)

    controller.on_edit_mapping_requested("a", "Attack bites", "point")

    assert len(prompts) == 1


def test_removing_a_mapping_is_guarded(controller, monkeypatch):
    controller.project_model = _StubProject(annotated=2)
    prompts = _record_prompts(controller, monkeypatch)

    controller.on_remove_mapping_requested("b")

    assert len(prompts) == 1
    assert "Chasing" in prompts[0]


def test_reset_to_default_is_guarded_and_shows_one_dialog(controller, monkeypatch):
    """The guard replaces the generic confirmation rather than stacking on it."""
    controller.project_model = _StubProject(annotated=4)
    prompts = _record_prompts(controller, monkeypatch, answer=False)

    controller.reset_to_default()

    assert len(prompts) == 1
    assert "4 videos" in prompts[0]
    # Declining must leave the mappings alone.
    assert controller._model.get_behavior("a") == "Attack bites"


def test_reset_without_annotations_uses_the_plain_confirmation(controller, monkeypatch):
    controller.project_model = _StubProject(annotated=0)
    prompts = _record_prompts(controller, monkeypatch, answer=False)

    controller.reset_to_default()

    assert len(prompts) == 1
    assert "Reset to Default" in prompts[0]
    assert "already has" not in prompts[0]


def test_load_dialog_guards_before_replacing_mappings(controller, monkeypatch, tmp_path):
    controller.project_model = _StubProject(annotated=2)

    chosen = tmp_path / "other.json"
    chosen.write_text('{"q": "Imported"}', encoding="utf-8")
    monkeypatch.setattr(
        "controllers.action_map_controller.QFileDialog.getOpenFileName",
        staticmethod(lambda *a, **k: (str(chosen), "")),
    )
    prompts = _record_prompts(controller, monkeypatch, answer=False)

    controller.load_action_map_dialog()

    assert len(prompts) == 1
    assert "2 videos" in prompts[0]
    # Declining must not import the file.
    assert controller._model.get_all_mappings() == {"a": "Attack bites", "b": "Chasing"}


# --- Declining must leave the map untouched ----------------------------


def test_declining_leaves_edit_unapplied(controller, monkeypatch):
    controller.project_model = _StubProject(annotated=3)
    _record_prompts(controller, monkeypatch, answer=False)

    controller.on_edit_mapping_requested("a", "Something else", "state")

    assert controller._model.get_behavior("a") == "Attack bites"


def test_declining_leaves_removal_unapplied(controller, monkeypatch):
    controller.project_model = _StubProject(annotated=3)
    _record_prompts(controller, monkeypatch, answer=False)

    controller.on_remove_mapping_requested("b")

    assert controller._model.get_behavior("b") == "Chasing"


def test_declining_resyncs_the_view(controller, monkeypatch):
    """The view must not keep showing an edit the model rejected."""
    controller.project_model = _StubProject(annotated=3)
    _record_prompts(controller, monkeypatch, answer=False)

    controller.on_edit_mapping_requested("a", "Something else", "state")

    assert controller._view.mappings == {"a": "Attack bites", "b": "Chasing"}
