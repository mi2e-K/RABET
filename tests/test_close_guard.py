"""Tests for the unified application-close guard (BUG-003, 1.3.4).

Verifies that the window-close path consults the guard and that a cancelled
unsaved-changes prompt vetoes the close. Uses lightweight fakes for the
controller so we don't construct the whole app, plus a real MainWindow to
confirm closeEvent honours the guard.
"""

from __future__ import annotations

import types

import pytest
from PySide6.QtGui import QCloseEvent

from controllers.app_controller import AppController
from views.main_window import MainWindow


# -------------------------------------------------------------------- #
# MainWindow.closeEvent honours the guard
# -------------------------------------------------------------------- #


def test_close_event_vetoed_when_guard_returns_false(qt_app):
    win = MainWindow()
    try:
        calls = {"persisted": False}
        win._persist_settings = lambda: calls.__setitem__("persisted", True)

        win.set_close_guard(lambda: False)  # veto
        ev = QCloseEvent()
        win.closeEvent(ev)

        assert not ev.isAccepted()           # close vetoed
        assert calls["persisted"] is False   # settings not persisted on veto
    finally:
        win.set_close_guard(lambda: True)
        win.deleteLater()


def test_close_event_proceeds_when_guard_returns_true(qt_app):
    win = MainWindow()
    try:
        calls = {"persisted": False}
        win._persist_settings = lambda: calls.__setitem__("persisted", True)

        win.set_close_guard(lambda: True)
        ev = QCloseEvent()
        win.closeEvent(ev)

        assert calls["persisted"] is True    # settings persisted on proceed
    finally:
        win.deleteLater()


# -------------------------------------------------------------------- #
# confirm_application_close decision logic
# -------------------------------------------------------------------- #


def _guard_with_fakes(monkeypatch, *, recording=False, dirty_ann=False,
                      project_open=False, project_modified=False,
                      answer="Yes"):
    """Build an AppController shell with just enough state for the guard."""
    from PySide6.QtWidgets import QMessageBox

    ctrl = AppController.__new__(AppController)
    import logging
    ctrl.logger = logging.getLogger("test.app_controller")

    exported = {"called": False}

    def _export():
        exported["called"] = True
        # Simulate a successful export clearing the dirty flag.
        ann._dirty = False

    ann = types.SimpleNamespace(
        _dirty=dirty_ann,
        is_recording=lambda: recording,
        stop_timed_recording=lambda: None,
        has_unsaved_annotations=lambda: ann._dirty,
        export_annotations_dialog=_export,
    )
    ctrl.annotation_controller = ann
    ctrl.project_model = types.SimpleNamespace(
        is_project_open=lambda: project_open,
        is_modified=lambda: project_modified,
        save_project=lambda: True,
    )
    ctrl.main_window = None  # only used as QMessageBox parent

    button = getattr(QMessageBox.StandardButton, answer)
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: button),
    )
    return ctrl, exported


def test_guard_proceeds_when_nothing_unsaved(monkeypatch, qt_app):
    ctrl, _ = _guard_with_fakes(monkeypatch)
    assert ctrl.confirm_application_close() is True


def test_guard_cancel_on_unsaved_annotations_vetoes(monkeypatch, qt_app):
    ctrl, _ = _guard_with_fakes(monkeypatch, dirty_ann=True, answer="Cancel")
    assert ctrl.confirm_application_close() is False


def test_guard_export_on_unsaved_annotations_proceeds(monkeypatch, qt_app):
    ctrl, exported = _guard_with_fakes(monkeypatch, dirty_ann=True, answer="Yes")
    assert ctrl.confirm_application_close() is True
    assert exported["called"] is True


def test_guard_cancel_on_unsaved_project_vetoes(monkeypatch, qt_app):
    ctrl, _ = _guard_with_fakes(
        monkeypatch, project_open=True, project_modified=True, answer="Cancel"
    )
    assert ctrl.confirm_application_close() is False
