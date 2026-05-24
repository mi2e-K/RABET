# RABET macOS and Linux Build Notes

These scripts create compact PyInstaller-based desktop application packages.
Starting from RABET 1.3.1 the video backend is PyAV (FFmpeg python
bindings) instead of python-vlc; PyAV's wheels bundle FFmpeg, so the
RABET build is fully self-contained and does **not** require any
system-installed video runtime on the target machine.

## Common Rule

Build on the target OS.

- Create the macOS `.app` on macOS.
- Create the Linux package on Linux.
- Use a clean virtual environment for each platform.
- No system VLC/FFmpeg install is required on either build or target
  machines as of 1.3.1.

## macOS

Recommended for a borrowed Mac:

```bash
cd /path/to/RABET_1.3.2
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python packaging/build_macos_optimized.py
```

Outputs:

- `dist/RABET.app`
- `dist/RABET-macOS.zip` containing `RABET.app` and `README.txt`
- `dist/README.txt`

Useful options:

```bash
python packaging/build_macos_optimized.py --target-arch arm64
python packaging/build_macos_optimized.py --target-arch x86_64
python packaging/build_macos_optimized.py --console --verbose
python packaging/build_macos_optimized.py --spec-only
```

Notes:

- Apple Silicon Macs normally produce arm64 builds.
- Intel Macs normally produce x86_64 builds.
- `--target-arch universal2` only works if Python and the installed wheels are universal2-compatible.
- Unsigned apps may need right-click > Open on first launch.
- If the app is shared as a zip and macOS blocks it, the receiver may need to remove quarantine with `xattr -dr com.apple.quarantine RABET.app`.

## Linux / Ubuntu

Recommended on Ubuntu:

```bash
sudo apt update
# Note: ``vlc`` / ``libvlc-bin`` are no longer required as of 1.3.1.
# Qt's xcb platform plugin depends on system GUI runtime libraries.
sudo apt install -y \
  python3 \
  python3-venv \
  python3-pip \
  libxcb-cursor0 \
  libxcb-icccm4 \
  libxcb-image0 \
  libxcb-keysyms1 \
  libxcb-render-util0 \
  libxcb-xkb1 \
  libxcb-randr0 \
  libxcb-render0 \
  libxcb-shape0 \
  libxcb-shm0 \
  libxcb-sync1 \
  libxcb-xfixes0 \
  libxkbcommon-x11-0 \
  libxrender1 \
  libx11-xcb1 \
  libsm6 \
  libice6 \
  libglib2.0-0 \
  libfontconfig1 \
  libfreetype6
cd /path/to/RABET_1.3.2
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python packaging/build_linux_optimized.py --onefile
```

Outputs:

- `dist/RABET-linux/`
- `dist/RABET-linux-<arch>.tar.gz`

Run locally:

```bash
cd dist/RABET-linux
./run_rabet.sh
```

Install a desktop launcher for the current user:

```bash
cd dist/RABET-linux
./install_desktop_entry.sh
```

Useful options:

```bash
python packaging/build_linux_optimized.py --console --verbose
python packaging/build_linux_optimized.py
python packaging/build_linux_optimized.py --upx
python packaging/build_linux_optimized.py --spec-only
```

Notes:

- Release builds use `--onefile`, so the archive should not contain a visible `_internal/` folder.
- Running without `--onefile` is still useful for development/debug builds.
- `--onefile` often starts slower because it extracts files at launch.
- Raw Linux executables do not reliably show custom icons in file managers. Use `install_desktop_entry.sh` for an icon-bearing application launcher.
- `--upx` can reduce size if UPX is installed, but test carefully because compressed Qt binaries can be fragile.
- Build on the oldest Ubuntu version you plan to support when possible. Newer Linux builds can depend on newer system libraries.
