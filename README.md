<div align="center">

<img src="images/RABET.png" alt="RABET icon" width="180" />

# RABET

## Real-time Animal Behavior Event Tagger

[![Version](https://img.shields.io/badge/version-1.4.0-blue)](https://github.com/mi2e-K/RABET/releases)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](#installation)
[![CI](https://github.com/mi2e-K/RABET/actions/workflows/ci.yml/badge.svg)](https://github.com/mi2e-K/RABET/actions/workflows/ci.yml)
[![Website](https://img.shields.io/badge/website-mi2e--k.github.io%2FRABET-ff5722?logo=githubpages&logoColor=white)](https://mi2e-k.github.io/RABET/)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.15313025-orange)](https://doi.org/10.5281/zenodo.15313025)

</div>

---

## Overview

**RABET** is a cross-platform desktop application for annotating animal
behaviour from video. It combines frame-accurate playback, keyboard-driven
event coding, an interactive timeline, multi-file analysis, raster
visualisation, reliability assessment, bout analysis, and first-order
transition analysis in one self-contained tool.

RABET ships as a **self-contained binary** for Windows, macOS, and Linux. No
system-wide VLC, FFmpeg, Python, R, or codec-pack installation is required for
normal use.

<p align="center">
  <img src="images/screenshot_annotation.png" alt="RABET annotation view" width="820" />
  <br>
  <em>The Annotation view: video player, recording controls, action map, and colour-coded timeline.</em>
</p>

---

## Key Features

**Video and annotation**

- Frame-accurate playback with single-frame stepping and fast seeking.
- Configurable keyboard-to-behaviour action maps.
- **State behaviours** for duration events, recorded from key press to key
  release.
- **Point behaviours** for instantaneous events, recorded as zero-duration
  ticks with onset equal to offset.
- Timed recording sessions with pause, resume, rewind handling, undo, and an
  editable timeline.

**Analysis and export**

- Multi-file annotation analysis with whole-session and interval summaries.
- Per-behaviour duration and frequency columns.
- Custom latency metrics and overlap-aware total-time metrics.
- Mean and SEM summary rows for quick inspection.
- One-click clipboard copy and CSV export.

**Bout and transition analysis**

- Bout analysis with user-defined bout criterion interval (BCI), advisory BCI
  estimation, per-animal bout summaries, and bout raster plots.
- First-order transition analysis with counts, conditional probabilities,
  odds ratios, expected counts, and adjusted residuals.
- Optional bout-level transition analysis, transition time windows, pooled
  count summaries, heatmaps, and antecedent-window predictability.
- PNG / SVG / PDF figure export with user-selectable DPI.

**Reliability assessment**

- **Summary mode** compares two `summary_table.csv` files using ICC(2,1),
  Pearson correlation, and mean absolute difference.
- **Detailed mode** compares two annotation CSVs using time-binned Cohen's
  kappa, Krippendorff's alpha, raw percentage agreement, and event-raster
  disagreement review.
- Summary-mode statistics are cross-checked against an R reference script
  using `psych::ICC`.

**Project management**

- Keep videos, annotations, action maps, and analysis outputs together in a
  project directory.
- Save projects as either self-contained copies or references to existing
  files.
- Persistent UI settings, recent files, and file-dialog locations.

---

## Installation

### Pre-built binaries

The latest release is published on the
[GitHub Releases page](https://github.com/mi2e-K/RABET/releases/latest).
The Zenodo concept DOI is kept for citation and long-term archival reference:
[10.5281/zenodo.15313025](https://doi.org/10.5281/zenodo.15313025).

Download the asset matching your platform:

| Platform | Asset |
| --- | --- |
| Windows installer | `RABET-Windows-1.4.0-Setup.zip` |
| Windows portable | `RABET-Windows-1.4.0-portable.zip` |
| macOS (Apple Silicon) | `RABET-macOS-arm64-1.4.0.dmg` |
| macOS (Intel) | `RABET-macOS-x86_64-1.4.0.dmg` |
| Linux | `RABET-Linux-x86_64-1.4.0.AppImage` |

### Windows

For the installer build, unzip `RABET-Windows-1.4.0-Setup.zip` and run
`RABET-Setup.exe`. For the portable build, unzip
`RABET-Windows-1.4.0-portable.zip` and launch `RABET.exe` directly.

Windows SmartScreen may warn on first launch because the app is not code
signed. Choose **More info** and then **Run anyway** if you trust the
downloaded release.

### macOS

Open the DMG and drag `RABET.app` to Applications. The macOS builds are
unsigned and not notarized, so Gatekeeper may report that the app is damaged
or cannot be verified. This is quarantine metadata, not a corrupt download.

The most reliable one-time fix is:

```bash
xattr -dr com.apple.quarantine /Applications/RABET.app
```

Then open `RABET.app` normally.

### Linux

Make the AppImage executable and run it:

```bash
chmod +x RABET-Linux-x86_64-1.4.0.AppImage
./RABET-Linux-x86_64-1.4.0.AppImage
```

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

Python 3.11 or newer is required. The pinned conda environment uses
Python 3.12.

---

## Documentation

Project website: [mi2e-k.github.io/RABET](https://mi2e-k.github.io/RABET/)

- [User Guide (English)](docs/USER_GUIDE.md)
- [User Guide (Japanese)](docs/USER_GUIDE.ja.md)
- [CSV format specification](docs/CSV_FORMAT.md)
- [Reliability assessment reference](docs/reliability/README.md)
- [Build instructions for macOS / Linux](docs/BUILD_MACOS_LINUX.md)

---

## CSV Format

Annotation exports contain metadata, an event log, and a per-behaviour
summary:

```csv
Metadata
RABET Version,1.4.0
Test Duration (seconds),300

Event,Onset,Offset
RecordingStart,0.0000,0.0000
Attack bites,12.4123,12.6480
Head dip,20.2500,20.2500

Behavior,Duration,Frequency
Attack bites,0.24,1
Head dip,0.00,1
```

State events have duration. Point events are instantaneous and therefore have
`Onset == Offset`; their duration is zero, but their frequency is counted.
Times are seconds with four decimal places. Full details are in
[docs/CSV_FORMAT.md](docs/CSV_FORMAT.md).

---

## Citation

If RABET supports your research, please cite it. Machine-readable metadata is
in [CITATION.cff](CITATION.cff). A human-readable form is:

> Mitsui, K. (2026). *RABET - Real-time Animal Behavior Event Tagger*
> (Version 1.4.0) [Computer software].
> https://github.com/mi2e-K/RABET
> doi:[10.5281/zenodo.15313025](https://doi.org/10.5281/zenodo.15313025)

The DOI above is the Zenodo **concept DOI**, intended to remain stable across
RABET versions. When citing a specific binary release, also report the exact
RABET version used.

A tool paper describing RABET is in preparation.

---

## License

Released under the [MIT License](LICENSE).

---

## Contributing

Bug reports, feature requests, and pull requests are welcome.

- Issues: include reproducible steps, the RABET version from **Help > About**,
  and the relevant log file when possible.
- Pull requests: keep them scoped, include a short description, and reference
  the related issue when applicable.

---

## Acknowledgements

RABET is built on PySide6, PyAV, numpy, pandas, matplotlib, scipy, pingouin,
krippendorff, filetype, and PyInstaller. We are grateful to the maintainers
and contributors of these projects.
