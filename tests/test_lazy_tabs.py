"""Lazy construction of the heavy Visualization/Reliability tabs (Phase 5-2)."""

from __future__ import annotations

from controllers.app_controller import AppController


def test_heavy_tabs_are_lazy_until_switched(qt_app):
    c = AppController()
    try:
        assert c.visualization_view is None
        assert c.reliability_view is None

        c.main_window.switch_to_view("Visualization")
        assert c.visualization_view is not None
        assert c.visualization_controller is not None

        c.main_window.switch_to_view("Reliability")
        assert c.reliability_view is not None
        assert c.reliability_controller is not None
    finally:
        c.main_window.deleteLater()


def test_lazy_build_is_idempotent(qt_app):
    c = AppController()
    try:
        c.main_window.switch_to_view("Visualization")
        built = c.visualization_view
        c.main_window.switch_to_view("Annotation")
        c.main_window.switch_to_view("Visualization")
        assert c.visualization_view is built  # same instance, not rebuilt
    finally:
        c.main_window.deleteLater()


def test_analysis_visualize_builds_visualization(qt_app, monkeypatch):
    c = AppController()
    try:
        # Analysis is lazy now (PR-STARTUP-04): build it before patching.
        c._ensure_analysis()
        monkeypatch.setattr(
            c.analysis_model, "get_file_paths", lambda: ["nonexistent.csv"]
        )
        try:
            c.handle_analysis_visualize_requested()
        except Exception:
            pass  # load may fail on a fake path; we only assert the lazy build
        assert c.visualization_view is not None
    finally:
        c.main_window.deleteLater()


def test_warm_up_builds_all_lazy_tabs(qt_app):
    # Idle pre-warming (tab-jank mitigation): _warm_up_lazy_tabs constructs the
    # heavy tabs in the background, one per idle tick. Draining the chained
    # singleShot(0) builders should leave every one of them constructed.
    c = AppController()
    try:
        assert c.visualization_view is None
        assert c.reliability_view is None
        assert c.analysis_model is None

        c._warm_up_lazy_tabs()
        for _ in range(20):  # drain the chained singleShot(0) builders
            qt_app.processEvents()

        assert c.visualization_view is not None
        assert c.reliability_view is not None
        assert c.analysis_model is not None
    finally:
        c.main_window.deleteLater()


def test_warm_up_does_not_rebuild_an_open_tab(qt_app):
    # Warm-up must be idempotent with a tab the user already opened: the
    # _ensure_* guards mean the pre-built instance is reused, not replaced.
    c = AppController()
    try:
        c.main_window.switch_to_view("Visualization")
        built = c.visualization_view

        c._warm_up_lazy_tabs()
        for _ in range(20):
            qt_app.processEvents()

        assert c.visualization_view is built  # same instance, not rebuilt
    finally:
        c.main_window.deleteLater()
