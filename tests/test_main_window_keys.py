"""GUI tests for MainWindow waiting-state key handling (BUG-001).

Runs headless (offscreen Qt). Constructs a real MainWindow but without the
full controller stack: we assert that the first non-autorepeat key starts the
session and is consumed without being forwarded via ``key_pressed``.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from views.main_window import MainWindow


@pytest.fixture
def main_window(qt_app):
    win = MainWindow()
    yield win
    win.close()
    win.deleteLater()


def _press(key, text):
    return QKeyEvent(
        QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text
    )


def test_behavior_key_in_waiting_state_starts_without_forwarding(main_window):
    rcv = main_window.recording_control_view
    rcv.set_waiting_state(300)
    assert rcv.is_in_waiting_state()

    forwarded = []
    main_window.key_pressed.connect(forwarded.append)

    # A behaviour key starts the session but is only the start signal; it must
    # not open an event at time 0.
    main_window.keyPressEvent(_press(Qt.Key.Key_A, "a"))

    assert rcv.is_recording()           # transitioned out of waiting
    assert forwarded == []              # first key is not an annotation


def test_space_in_waiting_state_starts_without_forwarding(main_window):
    rcv = main_window.recording_control_view
    rcv.set_waiting_state(300)

    forwarded = []
    main_window.key_pressed.connect(forwarded.append)

    # Space starts the session but is not a behaviour, so nothing is forwarded.
    main_window.keyPressEvent(_press(Qt.Key.Key_Space, " "))

    assert rcv.is_recording()
    assert forwarded == []


def test_autorepeat_in_waiting_state_is_ignored(main_window):
    rcv = main_window.recording_control_view
    rcv.set_waiting_state(300)

    # Autorepeat should not start the session.
    ev = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier,
        "a", True, 1,
    )
    main_window.keyPressEvent(ev)

    assert rcv.is_in_waiting_state()
