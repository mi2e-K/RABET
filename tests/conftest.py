import gc
import os

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qt_app():
    """Provide a QApplication for tests that instantiate Qt-backed models."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def pytest_sessionfinish(session, exitstatus):
    """Delete the windows the tests left behind before Python shuts down.

    Many tests build windows and dialogs without deleting them. PySide6 6.12
    destroys whatever is still alive while the interpreter exits, and that
    crashed the process after every test had passed (exit code 139 or 134).
    Deleting them here, while Python and Qt are both intact, keeps the exit
    clean. They are deleted, not closed, so no close handler runs.
    """
    if QApplication.instance() is None:
        return
    gc.collect()
    for widget in QApplication.topLevelWidgets():
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()
