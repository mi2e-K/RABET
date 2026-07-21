"""Release metadata must stay aligned with the canonical application version."""

from __future__ import annotations

import re
from pathlib import Path

from version import __version__


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_inno_setup_default_matches_application_version():
    inno_text = (REPO_ROOT / "packaging" / "RABET.iss").read_text(encoding="utf-8")
    match = re.search(r'#define AppVersion "([^"]+)"', inno_text)

    assert match is not None
    assert match.group(1) == __version__
