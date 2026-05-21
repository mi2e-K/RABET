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
cd /path/to/RABET_1.3.1
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python packaging/build_macos_optimized.py
```

Outputs:

- `dist/RABET.app`
- `dist/RABET-macOS.zip`
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
# ``libxcb-cursor0`` is still needed by Qt 6 on headless / minimal
# Linux installs (Qt's xcb plugin loads it lazily).
sudo apt install -y python3 python3-venv python3-pip libxcb-cursor0
cd /path/to/RABET_1.3.1
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python packaging/build_linux_optimized.py
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
python packaging/build_linux_optimized.py --onefile
python packaging/build_linux_optimized.py --upx
python packaging/build_linux_optimized.py --spec-only
```

Notes:

- The folder build is the recommended default for Qt applications.
- `--onefile` is convenient but often starts slower because it extracts files at launch.
- `--upx` can reduce size if UPX is installed, but test carefully because compressed Qt binaries can be fragile.
- Build on the oldest Ubuntu version you plan to support when possible. Newer Linux builds can depend on newer system libraries.
