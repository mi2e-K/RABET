<div align="center">

<img src="images/RABET.png" alt="RABET icon" width="180" />

# RABET

# Real-time Animal Behavior Event Tagger

[![Version](https://img.shields.io/badge/version-1.3.5-blue)](https://github.com/mi2e-K/RABET/releases)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](#installation)
[![CI](https://github.com/mi2e-K/RABET/actions/workflows/ci.yml/badge.svg)](https://github.com/mi2e-K/RABET/actions/workflows/ci.yml)
[![Website](https://img.shields.io/badge/website-mi2e--k.github.io%2FRABET-ff5722?logo=githubpages&logoColor=white)](https://mi2e-k.github.io/RABET/)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.15313025-orange)](https://doi.org/10.5281/zenodo.15313025)

</div>

---

## Overview

**RABET** is a desktop application for the behavioural annotation of
video recordings of animals. Researchers play back a video, tag
behaviours in real time with keyboard shortcuts, visualise events on an
interactive timeline, and export annotated data for downstream
statistical analysis — including built-in inter-rater and intra-rater
reliability assessment.

RABET ships as a **self-contained binary**. No system-wide video
runtime (VLC, FFmpeg, codec packs) needs to be installed: the
application bundles its own frame-accurate decoder, so the executable
simply works on a clean Windows / macOS / Linux machine.

<p align="center">
  <img src="images/screenshot_annotation.png" alt="RABET annotation view" width="820" />
  <br>
  <em>The Annotation view — video player, recording controls, action map, and colour-coded timeline.</em>
</p>

---

## Key Features

**Video & annotation**
- Frame-accurate playback with single-frame stepping and instant seek
- Configurable keyboard → behaviour mapping (JSON-driven; ships with a
  sensible default schema for rodent aggression studies)
- Real-time tagging with monotonic time stamping
- Interactive behaviour timeline with auto-scrolling playhead and
  colour-coded events
- Timed recording sessions with pause / resume and rewind handling

**Analysis & export**
- Multi-file CSV analysis: per-session and per-interval summaries
- Custom latency and total-time metrics (e.g. attack latency, total
  aggression) defined declaratively in JSON
- On-screen **Summary** and **Intervals** tabs with one-click clipboard
  export
- Raster-plot visualisation across multiple animals

**Reliability assessment**
- **Summary mode**: compare two `summary_table.csv` files via
  **ICC(2,1)**, Pearson correlation, and mean absolute difference per
  metric, with scatter plots
- **Detailed mode**: compare two annotation CSVs via time-window-binned
  **Cohen's κ**, **Krippendorff's α**, raw percentage agreement, and a
  pairwise event-raster overlay

**Project management**
- Group videos, annotations, and analyses under a single project
- Persistent UI settings (window geometry, last view, recording
  duration, analysis options) stored in the user app-data directory

**Cross-platform**
- Self-contained binaries for Windows, macOS (Intel & Apple Silicon),
  and Linux

---

## Installation

### Pre-built binaries (recommended)

RABET is officially distributed via **[Zenodo](https://doi.org/10.5281/zenodo.15313025)**,
which assigns each release a permanent DOI for citation:

> [![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.15313025-orange)](https://doi.org/10.5281/zenodo.15313025)
> *concept DOI — always resolves to the latest version*

Open the Zenodo record above and download the archive matching your
platform:

| Platform | Asset |
| --- | --- |
| Windows installer | `RABET-Windows-1.3.5-Setup.exe` |
| Windows portable | `RABET-Windows-1.3.5-portable.zip` |
| macOS (Apple Silicon) | `RABET-macOS-arm64-1.3.5.dmg` |
| macOS (Intel) | `RABET-macOS-x86_64-1.3.5.dmg` |
| Linux | `RABET-Linux-x86_64-1.3.5.AppImage` |

The downloads are self-contained — no additional installation step is
required. See the [User Guide](docs/USER_GUIDE.md#12-launching-rabet)
for platform-specific launch instructions.

### macOS first launch

The macOS builds are unsigned and not notarized. After downloading the DMG,
open it and drag `RABET.app` to Applications. On first launch, macOS may report
that the app is "damaged" or cannot be verified. This is Gatekeeper quarantine,
not a corrupt download.

The most reliable fix is to open Terminal and run:

```bash
xattr -dr com.apple.quarantine /Applications/RABET.app
```

Then open `RABET.app` normally. You only need to do this once for each
downloaded copy.

A mirror of the same binaries is also published on the
[GitHub Releases page](https://github.com/mi2e-K/RABET/releases) for
convenience.

### From source

```bash
git clone https://github.com/mi2e-K/RABET.git
cd RABET

# Recommended: pinned conda environment
conda env create -f environment.yml
conda activate rabet_build

# Alternative: pip
# pip install -e .

python main.py
```

> **Python**: 3.11 or newer is required. The pinned conda environment
> uses Python 3.12.

---

## Documentation

> 🌐 **Project website**: **[mi2e-k.github.io/RABET](https://mi2e-k.github.io/RABET/)** — searchable docs site with the full user guide, dark-mode support, and English / Japanese language switcher.

The markdown source for every page below is also browsable directly on GitHub:

- **[User Guide (English)](docs/USER_GUIDE.md)** — step-by-step walkthrough of every feature
- **[User Guide (Japanese)](docs/USER_GUIDE.ja.md)** — Japanese version user guide
- [CSV format specification](docs/CSV_FORMAT.md)
- [Reliability assessment reference](docs/reliability/README.md)
- [Build instructions for macOS / Linux](docs/BUILD_MACOS_LINUX.md)

The [`docs/`](docs/) directory contains an index of all documentation.

---

## Building standalone packages

| Platform | Command |
| --- | --- |
| Windows | `python packaging/build_windows_optimized.py` |
| macOS   | `python packaging/build_macos_optimized.py` |
| Linux   | `python packaging/build_linux_optimized.py` |

Build outputs land in `dist/RABET/` (one-directory mode) or
`dist/RABET.exe` / `dist/RABET.app` / `dist/RABET-linux-*.tar.gz`
(one-file / single-archive mode). See
[`packaging/README.md`](packaging/README.md) for build-script flags and
[`docs/BUILD_MACOS_LINUX.md`](docs/BUILD_MACOS_LINUX.md) for
platform-specific notes.

---

## CSV format

Annotation exports use the layout below; full documentation lives in
[`docs/CSV_FORMAT.md`](docs/CSV_FORMAT.md).

```
Metadata
RABET Version,1.3.5
Test Duration (seconds),300

Event,Onset,Offset
Attack bites,12.4123,12.6480
...

Behavior,Duration,Frequency
Attack bites,2.10,3
...
```

Onsets and offsets are in seconds with 4-decimal precision. In
interval summaries, `Duration` is the number of seconds overlapping
each interval, and `Frequency` counts events whose onset falls inside
that interval. Annotation CSVs include a `RABET Version` row so
downstream tools can detect the producing application; summary CSVs
are kept table-first for easy import into spreadsheet and statistics
software.

---

## Citation

If RABET is useful in your research, please cite it. Machine-readable
metadata lives in [`CITATION.cff`](CITATION.cff); a human-readable form
is:

> Mitsui, K. (2026). *RABET — Real-time Animal Behavior Event Tagger*
> (Version 1.3.5) [Computer software].
> https://github.com/mi2e-K/RABET
> doi:[10.5281/zenodo.15313025](https://doi.org/10.5281/zenodo.15313025)

The DOI above is the **concept DOI** that always resolves to the latest
RABET release on Zenodo, so the citation stays valid as new versions
are published. Each individual release additionally receives its own
version-specific DOI.

A tool paper describing RABET is in preparation. Once published, please
cite the paper in addition to (or instead of) the Zenodo deposit.

---

## License

Released under the **MIT License** — see [LICENSE](LICENSE) for the
full text.

---

## Contributing

Bug reports, feature requests, and pull requests are welcome.

- **Issues**: please include reproducible steps and the application
  version (Help → About).
- **Pull requests**: keep them scoped, include a short description, and
  reference the related issue when applicable.

---

## Acknowledgements

RABET is built on PySide6, PyAV (FFmpeg python bindings), numpy,
pandas, matplotlib, pingouin, krippendorff, filetype, and PyInstaller.
We are grateful to the maintainers and contributors of these projects.
