#!/usr/bin/env bash
#
# Build a RABET AppImage from the PyInstaller *onedir* output.
#
# A single self-contained, executable file that runs on most Linux distros
# without installation or root. Mirrors the Windows installer/portable split:
# this is the clean "one file" Linux deliverable.
#
# Prerequisite: build the onedir distribution first, which produces
# dist/RABET-linux/ (RABET binary + _internal + resources/RABET.png):
#   python packaging/build_linux_optimized.py
#
# Then:
#   bash packaging/build_linux_appimage.sh [VERSION]
#   ./dist/RABET-Linux-<arch>-<VERSION>.AppImage
#
# VERSION defaults to version.py. Set APPIMAGETOOL=/path/to/appimagetool to
# reuse a local copy instead of downloading it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="${1:-$(python -c 'import sys; sys.path.insert(0, "."); from version import __version__; print(__version__)')}"
ARCH="$(uname -m)"
SRC="dist/RABET-linux"
APPDIR="build/RABET.AppDir"
OUT="dist/RABET-Linux-${ARCH}-${VERSION}.AppImage"

if [ ! -d "$SRC" ]; then
  echo "ERROR: onedir build not found at $SRC" >&2
  echo "Run first: python packaging/build_linux_optimized.py" >&2
  exit 1
fi

echo "Assembling AppDir from $SRC ..."
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# App payload: RABET binary + _internal must stay siblings, plus resources.
cp -a "$SRC/." "$APPDIR/usr/bin/"

# Icon (onedir build copies images/RABET.png to resources/RABET.png).
ICON_SRC="$SRC/resources/RABET.png"
if [ -f "$ICON_SRC" ]; then
  cp "$ICON_SRC" "$APPDIR/RABET.png"
  cp "$ICON_SRC" "$APPDIR/usr/share/icons/hicolor/256x256/apps/RABET.png"
else
  echo "WARNING: icon not found at $ICON_SRC; AppImage will have no icon" >&2
fi

# Top-level desktop entry (required by appimagetool).
cat > "$APPDIR/RABET.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=RABET
Comment=Real-time Animal Behavior Event Tagger
Exec=RABET
Icon=RABET
Terminal=false
Categories=Science;Education;
StartupWMClass=RABET
EOF

# AppRun entry point: launch the bundled binary, forcing Qt's xcb platform
# plugin (the bundled PySide6 ships xcb, not wayland).
cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "${0}")")"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
exec "${HERE}/usr/bin/RABET" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# Obtain appimagetool (continuous build) unless one was provided.
TOOL="${APPIMAGETOOL:-}"
if [ -z "$TOOL" ]; then
  TOOL="build/appimagetool-x86_64.AppImage"
  if [ ! -f "$TOOL" ]; then
    echo "Downloading appimagetool ..."
    curl -fsSL -o "$TOOL" \
      "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$TOOL"
  fi
fi

echo "Building $OUT ..."
# CI runners usually lack FUSE; extract-and-run avoids needing it. ARCH tells
# appimagetool which architecture to stamp on the output.
export APPIMAGE_EXTRACT_AND_RUN=1
export ARCH
"$TOOL" "$APPDIR" "$OUT"

echo "Created: $OUT"
