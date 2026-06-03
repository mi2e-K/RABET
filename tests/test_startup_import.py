"""Startup import-deferral tests (Phase 4-C + PR-STARTUP-02/03).

``controllers.app_controller`` is imported lazily inside ``main()`` (not at
module top-level) so the splash can appear first. Separately, the
Visualization/Reliability stack (and matplotlib) is imported lazily inside
``_ensure_*`` so it is not pulled in merely by importing app_controller.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


def _modules_present_after(import_stmt, candidates):
    """Run ``import_stmt`` in a clean interpreter; return which of ``candidates``
    landed in sys.modules. A subprocess keeps this independent of whatever the
    rest of the test session already imported."""
    code = (
        "import sys\n"
        f"{import_stmt}\n"
        f"cands = {list(candidates)!r}\n"
        "print(' '.join(m for m in cands if m in sys.modules))\n"
    )
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
        cwd=str(_REPO),
    )
    assert result.returncode == 0, f"subprocess failed:\n{result.stderr}"
    return set(result.stdout.split())


def test_app_controller_import_is_deferred():
    import main

    assert not hasattr(main, "AppController"), (
        "AppController must be imported lazily inside main(), not at module "
        "top-level (Phase 4-C splash deferral)."
    )


def test_app_controller_import_does_not_pull_visualization_stack():
    # PR-STARTUP-02/03: Visualization/Reliability (and matplotlib) import lazily
    # in _ensure_*; importing app_controller must not pull them in.
    present = _modules_present_after(
        "import controllers.app_controller",
        [
            "matplotlib",
            "pingouin",
            "views.visualization_view",
            "views.reliability_view",
            "models.reliability_model",
            "controllers.visualization_controller",
            "controllers.reliability_controller",
        ],
    )
    assert present == set(), (
        f"startup import unexpectedly pulled: {sorted(present)}"
    )
