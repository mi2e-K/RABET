"""Helpers for finding the bundled RABET application icon."""

from __future__ import annotations

import sys
from pathlib import Path


def _icon_names_for_platform() -> list[str]:
    if sys.platform == "darwin":
        return ["RABET.icns", "RABET.png", "RABET.ico", "icon.ico"]
    if sys.platform.startswith("linux"):
        return ["RABET.png", "RABET.ico", "RABET.icns", "icon.ico"]
    return ["RABET.ico", "RABET.png", "RABET.icns", "icon.ico"]


def _base_dirs() -> list[Path]:
    bases = [Path.cwd()]

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        bases.extend(
            [
                exe_dir,
                exe_dir.parent,
                exe_dir.parent / "Resources",
            ]
        )

        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bases.append(Path(meipass))

    return bases


def find_app_icon_path() -> str | None:
    """Return the first existing icon path suitable for the current platform."""
    names = _icon_names_for_platform()
    relative_paths: list[Path] = []
    for name in names:
        relative_paths.append(Path("resources") / name)
        if name.endswith(".png"):
            relative_paths.append(Path("images") / name)
        relative_paths.append(Path(name))

    seen: set[Path] = set()
    for base_dir in _base_dirs():
        for relative_path in relative_paths:
            candidate = (base_dir / relative_path).resolve()
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate.exists():
                return str(candidate)

    return None


def find_resource_path(filename: str) -> str | None:
    """Return the path to a bundled resource file, or None if missing.

    Searches ``resources/<filename>`` (and the bare ``<filename>``) under
    the same base directories used for the app icon, so it resolves both
    in a source checkout and inside a PyInstaller bundle (``sys._MEIPASS``).
    """
    relative_paths = [Path("resources") / filename, Path(filename)]
    seen: set[Path] = set()
    for base_dir in _base_dirs():
        for relative_path in relative_paths:
            candidate = (base_dir / relative_path).resolve()
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate.exists():
                return str(candidate)
    return None
