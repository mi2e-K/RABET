#!/usr/bin/env bash
#
# Build a RABET .dmg from the built .app bundle.
#
# A drag-to-Applications disk image -- the idiomatic macOS deliverable, the
# counterpart of the Windows installer.
#
# Prerequisite: build the .app first, which produces dist/RABET.app:
#   python packaging/build_macos_optimized.py
#
# Then:
#   bash packaging/build_macos_dmg.sh [VERSION] [ARCH]
#
# VERSION defaults to version.py; ARCH defaults to `uname -m`. Produces
# dist/RABET-macOS-<ARCH>-<VERSION>.dmg.
#
# NOTE: the .app is unsigned / un-notarised, so Gatekeeper blocks the first
# launch. The image includes a short "How to open" note; signing+notarisation
# (an Apple Developer ID) is the only way to remove that prompt.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="${1:-$(python -c 'import sys; sys.path.insert(0, "."); from version import __version__; print(__version__)')}"
ARCH="${2:-$(uname -m)}"
APP="dist/RABET.app"
OUT="dist/RABET-macOS-${ARCH}-${VERSION}.dmg"

if [ ! -d "$APP" ]; then
  echo "ERROR: app bundle not found at $APP" >&2
  echo "Run first: python packaging/build_macos_optimized.py" >&2
  exit 1
fi

STAGE="build/dmg-staging"
rm -rf "$STAGE"
mkdir -p "$STAGE"

# Drag-to-install layout: the app plus an Applications symlink.
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

# First-run help for the unsigned bundle.
cat > "$STAGE/How to open (unsigned).txt" <<'EOF'
RABET is not code-signed, so on first launch macOS may say it "cannot be
opened because it is from an unidentified developer" (or that it is damaged).

To open it:
  1. Drag RABET.app onto the Applications folder in this window.
  2. In Applications, right-click (Control-click) RABET.app -> Open -> Open.
     You only need to do this once.

If macOS still refuses, open Terminal and run:
  xattr -dr com.apple.quarantine /Applications/RABET.app
then open RABET normally.
EOF

rm -f "$OUT"
echo "Building $OUT ..."
hdiutil create -volname "RABET" -srcfolder "$STAGE" -ov -format UDZO "$OUT"

echo "Created: $OUT"
