"""Startup import-deferral test (Phase 4-C).

``controllers.app_controller`` transitively imports matplotlib, pandas and the
visualization/reliability views, which dominate import time. It must be
imported lazily inside ``main()`` — not at module top-level — so the splash
screen can appear before that cost is paid.
"""

from __future__ import annotations


def test_app_controller_import_is_deferred():
    import main

    assert not hasattr(main, "AppController"), (
        "AppController must be imported lazily inside main(), not at module "
        "top-level (Phase 4-C splash deferral)."
    )
