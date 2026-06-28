"""Lazy construction of the heavy Visualization/Reliability tabs (Phase 5-2)."""

from __future__ import annotations

from types import SimpleNamespace

from controllers.app_controller import AppController


def _dispose_controller(c):
    c.video_model.shutdown()
    c.main_window.deleteLater()


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
        assert c.reliability_controller._model is None
        assert c.reliability_view.summary_canvas is None
        assert c.reliability_view.detailed_canvas is None
    finally:
        _dispose_controller(c)


def test_lazy_build_is_idempotent(qt_app):
    c = AppController()
    try:
        c.main_window.switch_to_view("Visualization")
        built = c.visualization_view
        c.main_window.switch_to_view("Annotation")
        c.main_window.switch_to_view("Visualization")
        assert c.visualization_view is built  # same instance, not rebuilt
    finally:
        _dispose_controller(c)


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
        _dispose_controller(c)


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
        _dispose_controller(c)


def test_heavy_import_warmup_is_idempotent(monkeypatch):
    # Option 2: a daemon thread pre-imports the heavy libs after startup. Stub
    # out the real thread and call the method on a tiny stand-in object. This
    # keeps the test focused on the warm-up guard without creating AppController's
    # Qt worker threads.
    started = []

    class _StubThread:
        def __init__(self, *args, **kwargs):
            started.append(kwargs.get("name"))

        def start(self):
            pass

    monkeypatch.setattr(
        "controllers.app_controller._HEAVY_IMPORT_THREAD_FACTORY", _StubThread
    )
    c = SimpleNamespace()
    assert getattr(c, "_heavy_warm_started", False) is False
    AppController._warm_up_heavy_imports(c)
    assert c._heavy_warm_started is True
    assert started == ["HeavyImportWarmup"]
    AppController._warm_up_heavy_imports(c)  # idempotent: no second worker
    assert started == ["HeavyImportWarmup"]


def test_lazy_loader_overlay_gated_on_warm_completion(qt_app):
    # The "Preparing" overlay shows until the background warm-up has FULLY
    # finished (flag flips). A sys.modules probe is deliberately NOT used: a
    # module is registered at the start of its multi-second import, which would
    # hide the overlay mid-warm while the build still blocks on that import.
    c = AppController()
    try:
        mw = c.main_window
        assert "Reliability" in mw._lazy_view_builders
        mw._heavy_imports_ready = False
        assert mw._should_show_lazy_view_loader("Reliability") is True   # warming
        mw.mark_heavy_imports_ready()
        assert mw._heavy_imports_ready is True
        assert mw._should_show_lazy_view_loader("Reliability") is False  # warm done
    finally:
        _dispose_controller(c)
        qt_app.processEvents()


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
        _dispose_controller(c)
