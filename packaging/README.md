# Packaging scripts

Developer-only PyInstaller helpers that build standalone RABET binaries
for each supported platform. They are not shipped to end users and are
**not** importable as Python modules from the application code.

| Script | Output |
| --- | --- |
| `build_windows_optimized.py` | `dist/RABET/` (folder mode) or `dist/RABET.exe` with `--onefile` |
| `build_macos_optimized.py` | `dist/RABET.app/` + `dist/RABET-macOS.zip` |
| `build_linux_optimized.py` | `dist/RABET-linux/` + `dist/RABET-linux-<arch>.tar.gz` |
| `build_packaging_common.py` | Shared library imported by the macOS / Linux builders. Not a CLI. |

## How to run

Always invoke from the **project root** so that relative paths to
`configs/`, `resources/`, `images/` and the bundled `version.py` resolve
correctly. Each script auto-injects the project root onto `sys.path`,
but the working directory must still be the repository root.

```bash
# from RABET_1.2.x/ (the project root)
python packaging/build_windows_optimized.py
python packaging/build_macos_optimized.py --target-arch arm64
python packaging/build_linux_optimized.py
```

## Per-platform notes

For step-by-step macOS and Linux instructions (virtualenv setup,
signing tips, …), see
[`../docs/BUILD_MACOS_LINUX.md`](../docs/BUILD_MACOS_LINUX.md).

As of RABET 1.3.1 the video pipeline runs on PyAV (FFmpeg python
bindings) instead of python-vlc. PyAV's wheels ship a bundled FFmpeg
build, so the PyInstaller artefact is fully self-contained: end users
do **not** need to install VLC, FFmpeg or any other video runtime on
the target machine.

## CI hookup

The GitHub Actions `Release` workflow (`.github/workflows/release.yml`)
triggers on `v*` tags or manual `workflow_dispatch` runs. It builds:

- Windows zip on a Windows runner.
- Unsigned macOS zip archives for Apple Silicon (`arm64`) and Intel
  (`x86_64`) Macs on GitHub-hosted macOS runners.
- Linux `tar.gz` on an Ubuntu runner.

The workflow publishes all produced archives to one GitHub Release. The
Windows archive is built in PyInstaller `--onefile` mode and contains
`RABET.exe` plus the small runtime folders/files copied alongside it.
Download it from the GitHub Releases page rather than the Actions artifact
list; Actions artifacts are zip wrappers around the release zip.

The macOS archives are intentionally unsigned and not notarized; end users may
need to use right-click > Open, or allow the app from macOS Privacy &
Security settings on first launch.

The legacy `.github/workflows/build-mac.yml` workflow is kept as a manual
fallback only. Normal releases should use `.github/workflows/release.yml`.
