#!/usr/bin/env python3
"""Update the RABET version number in version.py.

Usage:
  python bump_version.py            # Show current version
  python bump_version.py --patch    # 1.2.0 -> 1.2.1
  python bump_version.py --minor    # 1.2.0 -> 1.3.0
  python bump_version.py --major    # 1.2.0 -> 2.0.0
  python bump_version.py --set 1.2.3
"""

import argparse
import re
import sys
from pathlib import Path

VERSION_FILE = Path(__file__).parent / "version.py"


def read_version() -> str:
    text = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        sys.exit(f"Could not parse version from {VERSION_FILE}")
    return match.group(1)


def write_version(new_version: str) -> None:
    VERSION_FILE.write_text(f'__version__ = "{new_version}"\n', encoding="utf-8")


def bump(version: str, part: str) -> str:
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        sys.exit(f"Version '{version}' is not in MAJOR.MINOR.PATCH format.")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump RABET version number.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--patch", action="store_true", help="Bump patch version (x.y.Z)")
    group.add_argument("--minor", action="store_true", help="Bump minor version (x.Y.0)")
    group.add_argument("--major", action="store_true", help="Bump major version (X.0.0)")
    group.add_argument("--set", metavar="VERSION", help="Set explicit version string")
    args = parser.parse_args()

    current = read_version()

    if not any([args.patch, args.minor, args.major, args.set]):
        print(f"Current version: {current}")
        return

    if args.set:
        new = args.set
        if not re.fullmatch(r"\d+\.\d+\.\d+", new):
            sys.exit(f"Invalid version format '{new}'. Use MAJOR.MINOR.PATCH.")
    elif args.major:
        new = bump(current, "major")
    elif args.minor:
        new = bump(current, "minor")
    else:
        new = bump(current, "patch")

    write_version(new)
    print(f"{current} -> {new}")


if __name__ == "__main__":
    main()
