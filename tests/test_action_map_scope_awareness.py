"""Tests for action-map scope awareness (1.4.2).

Guards against annotating with the wrong scheme after opening a different
project: the panel names the scope in use (passive), and a switch that
actually changes what the keys mean is announced (active).
"""

from __future__ import annotations

import pytest

from views.action_map_view import ActionMapView


# --- (a) The panel names the scope in use ------------------------------


@pytest.fixture
def view(qt_app):
    return ActionMapView()


def test_heading_is_plain_when_no_project_is_open(view):
    view.set_scope(project_name="", project_scoped=False)
    assert view.title_label.text() == "Action Map"


def test_heading_names_the_project_when_bound(view):
    view.set_scope(project_name="Study A", project_scoped=True)
    assert view.title_label.text() == "Action Map — Study A"
    assert "do not affect your global" in view.title_label.toolTip()


def test_heading_says_global_for_an_unbound_project(view):
    """Naming the project here would imply an ownership that does not exist."""
    view.set_scope(project_name="Legacy Study", project_scoped=False)
    assert view.title_label.text() == "Action Map — global"
    # The tooltip still says which project is open, and warns about the reach
    # of edits made in this state.
    assert "Legacy Study" in view.title_label.toolTip()
    assert "change the global" in view.title_label.toolTip()


def test_heading_clears_when_the_project_closes(view):
    view.set_scope(project_name="Study A", project_scoped=True)
    view.set_scope(project_name="", project_scoped=False)
    assert view.title_label.text() == "Action Map"
    assert view.title_label.toolTip() == ""


# --- (b) A real change is announced ------------------------------------


class _StubActionMapController:
    """The "before" side is passed to the notifier explicitly, so the stub
    only has to report the state *after* the switch."""

    def __init__(self, after, scoped=True):
        self._after = after
        self._scoped = scoped

    def get_mappings_snapshot(self):
        return self._after

    def is_project_scoped(self):
        return self._scoped


class _StubProjectModel:
    def __init__(self, name="Study B"):
        self._name = name

    def get_project_name(self):
        return self._name


def _make_controller(monkeypatch, before, after, scoped=True):
    """Build a ProjectController shell wired only for the notification path."""
    from controllers.project_controller import ProjectController

    ctrl = ProjectController.__new__(ProjectController)
    import logging

    ctrl.logger = logging.getLogger("test")
    ctrl._action_map_controller = _StubActionMapController(after, scoped)
    ctrl._model = _StubProjectModel()
    ctrl._view = None

    prompts = []
    monkeypatch.setattr(
        "controllers.project_controller.QMessageBox.information",
        staticmethod(lambda _p, title, text, *a, **k: prompts.append(f"{title}\n{text}")),
    )
    return ctrl, prompts


def test_identical_map_is_not_announced(monkeypatch):
    """Silence when nothing changed keeps the notice meaningful when it fires."""
    same = ({"a": "Attack"}, {"a": "state"})
    ctrl, prompts = _make_controller(monkeypatch, same, same)

    ctrl._notify_if_action_map_changed(*same)

    assert prompts == []


def test_changed_behaviour_is_announced_with_the_difference(monkeypatch):
    before = ({"a": "Attack"}, {"a": "state"})
    after = ({"a": "Grooming"}, {"a": "state"})
    ctrl, prompts = _make_controller(monkeypatch, before, after)

    ctrl._notify_if_action_map_changed(*before)

    assert len(prompts) == 1
    # The message must show what actually changed, not just that something did.
    assert "'a': Attack -> Grooming" in prompts[0]
    assert "Study B" in prompts[0]


def test_added_and_removed_keys_are_described(monkeypatch):
    before = ({"a": "Attack"}, {"a": "state"})
    after = ({"b": "Chasing"}, {"b": "state"})
    ctrl, prompts = _make_controller(monkeypatch, before, after)

    ctrl._notify_if_action_map_changed(*before)

    assert "'a': Attack -> (unused)" in prompts[0]
    assert "'b': (unused) -> Chasing" in prompts[0]


def test_kind_change_alone_is_announced(monkeypatch):
    """state -> point changes what gets recorded even with the same name."""
    before = ({"a": "Attack"}, {"a": "state"})
    after = ({"a": "Attack"}, {"a": "point"})
    ctrl, prompts = _make_controller(monkeypatch, before, after)

    ctrl._notify_if_action_map_changed(*before)

    assert len(prompts) == 1


def test_unbound_project_gets_the_global_wording(monkeypatch):
    """Switching from a bound project to a legacy one must not stay silent."""
    before = ({"a": "Attack"}, {"a": "state"})
    after = ({"a": "Grooming"}, {"a": "state"})
    ctrl, prompts = _make_controller(monkeypatch, before, after, scoped=False)

    ctrl._notify_if_action_map_changed(*before)

    assert len(prompts) == 1
    assert "no action map of its own" in prompts[0]


def test_long_change_list_is_truncated(monkeypatch):
    before = ({k: f"Before {k}" for k in "abcdefghijkl"}, {})
    after = ({k: f"After {k}" for k in "abcdefghijkl"}, {})
    ctrl, prompts = _make_controller(monkeypatch, before, after)

    ctrl._notify_if_action_map_changed(*before)

    assert "and 4 more" in prompts[0]
