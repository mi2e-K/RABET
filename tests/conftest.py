"""Pytest configuration and shared fixtures."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Make the project root importable when the tests are run from the repo root
# (``python -m pytest``) regardless of the current working directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def qt_app():
    """
    Provide a single ``QCoreApplication`` for the whole test session.

    PySide6 ``QObject`` subclasses require a running QCoreApplication, but
    we do not need a GUI for unit tests, so we use the lightweight core
    variant rather than ``QApplication``.
    """
    # ``QCoreApplication`` is sufficient because the tests under this folder
    # never instantiate widgets (they exercise models / utils only).
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance()
    created = False
    if app is None:
        app = QCoreApplication(["rabet-tests"])
        created = True

    yield app

    if created:
        # Ensure deferred deletions are processed before the next session run.
        app.processEvents()


@pytest.fixture()
def fixtures_dir() -> Path:
    """Return the path to the ``tests/fixtures`` directory."""
    return Path(__file__).resolve().parent / "fixtures"
