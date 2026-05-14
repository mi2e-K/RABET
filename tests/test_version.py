"""Version-string sanity checks."""
from __future__ import annotations

import re

import version


def test_version_string_is_semver_triplet():
    """``version.__version__`` must be a MAJOR.MINOR.PATCH string."""
    assert isinstance(version.__version__, str)
    assert re.fullmatch(r"\d+\.\d+\.\d+", version.__version__), (
        f"Unexpected version format: {version.__version__!r}"
    )


def test_version_is_at_least_1_2_0():
    """The 1.2.0 series introduces the schema-versioned CSV format."""
    major, minor, _patch = (int(part) for part in version.__version__.split("."))
    assert (major, minor) >= (1, 2)
