# RABET — Real-time Animal Behavior Event Tagger

![Version](https://img.shields.io/badge/version-1.2.1-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![CI](https://github.com/mi2e-K/RABET/actions/workflows/ci.yml/badge.svg)

RABET is a desktop application for **behavioural annotation of video
recordings of animals**. Researchers can play back a video, tag behaviours
with keyboard shortcuts in real time, visualise events on a timeline, and
export annotated data for downstream statistical analysis.

The 1.2.0 release accompanies the tool paper submission and bundles several
correctness and performance improvements over 1.1.x (see
[CHANGELOG.md](CHANGELOG.md)).

---

## Features

- Video playback with frame-by-frame stepping (VLC-backed)
- Configurable key → behaviour mapping (JSON) with default mouse-aggression
  schema
- Real-time keyboard tagging with monotonic time stamping
- Behaviour timeline with auto-scrolling playhead and colour-coded events
- Timed recording sessions with pause / resume and rewind handling
- Multi-file CSV analysis: per-session and per-interval summaries, custom
  latency and total-time metrics
- On-screen Summary / Intervals tabs with one-click clipboard export
- Raster-plot visualisation across multiple animals
- Project mode for grouping videos, annotations and analyses
- Persistent UI settings (window geometry, last view, recording duration,
  interval analysis options) under the user's app-data directory

---

## Quick start (development environment)

```bash
# Clone or unpack the repository
cd RABET_1.2.0

# Recommended: use the pinned conda environment
conda env create -f environment.yml
conda activate rabet_build

# Or install with pip (after installing VLC system-wide):
pip install -e .

# Launch the application
python main.py
```

VLC must be installed on the host machine for video playback to work. On
macOS and Linux RABET deliberately does **not** bundle VLC to keep build
sizes small; see [docs/BUILD_MACOS_LINUX.md](docs/BUILD_MACOS_LINUX.md) for
platform notes.

### Building standalone packages

| Platform | Script |
| --- | --- |
| Windows | `python packaging/build_windows_optimized.py` |
| macOS | `python packaging/build_macos_optimized.py` |
| Linux | `python packaging/build_linux_optimized.py` |

Builds produce a distributable folder (`dist/RABET/` or `dist/RABET.app/`).
See [`packaging/README.md`](packaging/README.md) for build-script details
and [`scripts/README.md`](scripts/README.md) for developer utilities such
as the version bumper.

---

## CSV format (schema v1)

Annotation exports follow this layout:

```
Metadata
RABET Version,1.2.0
Format Schema,v1
Test Duration (seconds),300

Event,Onset,Offset
Attack bites,12.4123,12.6480
...

Behavior,Duration,Frequency
Attack bites,2.10,3
...
```

Onsets / offsets are in seconds (4-decimal precision). The Frequency column
in the **whole-session** summary counts onsets; in the **interval** summary
it is labelled `Frequency (events overlapping interval)` to make clear that
events spanning multiple intervals are counted in each interval they touch.

RABET writes a `RABET Version` row and `Format Schema` row on every export so
downstream tools can detect the producing application. Older CSVs without
these rows are still readable.

The full file-format specification (Annotation CSV, Summary CSV, Interval
Summary CSV, schema versioning, compatibility matrix and example parsers)
lives in [docs/CSV_FORMAT.md](docs/CSV_FORMAT.md).

---

## Citation

If RABET is useful in your research, please cite it. Machine-readable
metadata lives in [CITATION.cff](CITATION.cff); a human-readable form is:

> Mitsui, K. (2026). *RABET — Real-time Animal Behavior Event Tagger*
> (Version 1.2.1) [Computer software]. https://github.com/mi2e-K/RABET
> doi:10.5281/zenodo.15313025

The DOI above is the **concept DOI** that always resolves to the latest
RABET release on Zenodo, so the citation stays valid as new versions are
published. Each individual release additionally receives its own
version-specific DOI (v1.0.0: `10.5281/zenodo.15313026`).

A tool paper describing RABET is in preparation. Once published, please
cite the paper in addition to (or instead of) the Zenodo deposit.

---

## License

Released under the MIT License — see [LICENSE](LICENSE) for the full text.

---

## Contributing

- Bug reports and feature requests: please open an issue with reproducible
  steps and the application version (see Help → About).
- Pull requests: include a short description, a reference to the related
  issue, and the relevant changes. Aim to keep PRs scoped and accompanied
  by tests when adding new behaviour.

A minimal test suite lives under `tests/`. Run it with:

```bash
python -m pytest tests/ -v
```

Smoke tests cover module imports, version handling, and core annotation /
analysis round-trips. Broader unit coverage is planned for v1.3.

---

## Acknowledgements

RABET depends on PySide6, python-vlc, numpy, pandas, matplotlib and
PyInstaller, among others. We are grateful to those projects' maintainers.
