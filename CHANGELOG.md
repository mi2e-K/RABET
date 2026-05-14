# Changelog

All notable changes to RABET are documented in this file.

Repository: https://github.com/mi2e-K/RABET

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.1] — 2026-05-14

Sprints 1 through 3 of the post-1.2.0 follow-ups. Sprint 1 added the
user-visible quick wins (Undo, Recent Files, CSV spec) and the metadata
clean-up; Sprint 2 hardens behaviour-event tracking, tightens the
analysis-config API, expands the test suite and wires up GitHub Actions
CI; Sprint 3 finishes the structural cleanup (defaults consolidation,
layout-diagnostics extraction), rounds out the UI (global drag&drop,
Shortcuts dialog, rich About dialog) and adds lint / benchmark / release
automation.

### Added

- **Recording Undo (Ctrl+Z)**: a new `Edit -> Undo Last Annotation` menu
  item removes the most recently recorded annotation. The synthetic
  `RecordingStart` marker is skipped so the recording session itself is
  never lost.
- **Recent Files menus**: `File -> Open Recent Video` and `File -> Recent
  Annotations` submenus list the 10 most recently opened files (persisted
  via `ConfigManager`). Each menu also offers a "Clear Recent Files"
  action.
- **CSV format specification**: a new [`docs/CSV_FORMAT.md`](docs/CSV_FORMAT.md)
  describes every CSV layout RABET produces, the `v0` / `v1` schema
  versioning, the compatibility matrix and a minimal pandas parser.
  Linked from `README.md`.
- **CSV compatibility test fixtures**: `tests/fixtures/sample_v1_0_annotation.csv`
  and `tests/fixtures/sample_v1_2_annotation.csv`, exercised by a new
  `tests/test_csv_compat.py` suite that locks in the cross-version
  parsing guarantees.
- ORCID identifier (`0009-0009-0556-3906`) for the author in `CITATION.cff`.
- **Sprint 2 — `AnalysisMetricsConfig.replace_metrics`**: a public API
  that atomically swaps both metric lists. Callers no longer need to
  poke at the underscore-prefixed attributes.
- **Sprint 2 — Expanded persistence**: video-player step size, playback
  rate, volume, frame-by-frame mode, timeline zoom level and the
  annotation-page splitter sizes now survive a restart together with the
  geometry / view / recording-control settings introduced in 1.2.0.
- **Sprint 2 — New test suites** covering `ActionMapModel` (10 cases),
  `ProjectModel` (4 cases) and a mocked `VideoModel` audio-state surface
  (5 cases). Total test count grew from 26 (1.2.0) to 50 (1.2.1).
- **Sprint 2 — GitHub Actions CI** (`.github/workflows/ci.yml`) runs the
  test suite on Linux / Windows / macOS with Python 3.11 and 3.12 on
  every push and pull request to `main`. Headless Qt is enabled via
  `QT_QPA_PLATFORM=offscreen` and the platform-appropriate VLC build is
  installed as a prerequisite. A CI badge is added to the README.
- **Sprint 3 — `defaults.py`** centralises the bundled action map, the
  default latency / total-time metric definitions and the default
  behaviour colour map. `ActionMapModel`, `AnalysisMetricsConfig`,
  `ConfigPathManager.ensure_default_configs` and
  `AnalysisController.on_configure_metrics_requested` now all source
  their fallbacks from this single module, eliminating five separate
  hardcoded copies.
- **Sprint 3 — `utils/layout_diagnostics.py`** holds the previously
  duplicated layout-diagnostic helpers (``widget_summary``,
  ``schedule_snapshot_burst``). `MainWindow` and `RecordingControlView`
  delegate to it; the diagnostic code remains dormant by default.
- **Sprint 3 — Keyboard Shortcuts dialog** (`Help -> Show Shortcuts`,
  shortcut: F1). Built-in shortcuts and the user's current action-map
  keys are displayed in a small read-only table.
- **Sprint 3 — Rich About dialog**: the `Help -> About` entry now opens
  a `QDialog` that renders HTML, lets the user click through to the
  GitHub repository / DOI, and offers a Copy-to-Clipboard button for the
  citation BibTeX snippet. The original plain `QMessageBox` survives as
  a fallback if the rich dialog fails to construct.
- **Sprint 3 — Global Drag & Drop**: dragging a video or CSV file onto
  *any* part of the main window (menubar, toolbar, empty area...) now
  works. The window automatically switches to the appropriate view and
  dispatches the file to the matching controller.
- **Sprint 3 — ruff linting** with a conservative rule set
  (`F`, `E711`-`E714`, `E722`, `B007`, `B904`, `B905`). Build scripts
  (`build_*_optimized.py`) are excluded because they intentionally use
  looser patterns. A dedicated lint job runs ahead of the test matrix
  in CI; the test job invokes pytest with `--benchmark-skip` so the new
  benchmarks do not slow PR validation.
- **Sprint 3 — `pytest-benchmark` perf tests** in `tests/test_perf.py`
  cover ``_calculate_total_aggression`` and ``_analyze_intervals`` on a
  5000-event synthetic dataset, providing a recordable baseline for
  future regression comparisons.
- **Sprint 3 — Release workflow** (`.github/workflows/release.yml`):
  pushing a `v*` tag triggers a Windows build, runs the test suite,
  packages `dist/RABET` into a versioned zip and publishes a GitHub
  Release whose body is sourced from the matching `CHANGELOG.md`
  section. Pre-release tags (`-rc`, `-beta`) are automatically marked
  pre-release on GitHub.

### Changed

- `CITATION.cff` / `pyproject.toml`: removed the author's personal email
  address from public-facing metadata. The author remains identifiable via
  GitHub handle (`mi2e-K`) and ORCID.
- **Sprint 2 — Recording-control styling consolidated**: the four
  per-state inline style strings in `RecordingControlView` were replaced
  by a single class-level style sheet whose visuals are selected via
  ``state`` / ``role`` dynamic properties. State transitions now toggle
  a property rather than swap a whole stylesheet, which makes future
  theming and palette work much easier.
- **Sprint 2 — `AnalysisView` status label** no longer hard-codes a
  fluorescent-yellow text colour, so the message remains readable on
  both dark and light Qt palettes.
- **Sprint 2 — `ActionMapDialog` validation**: the key field now accepts
  only a single alphanumeric character (regex-validated) and the *Add*
  flow asks for confirmation before overwriting an existing mapping.
- **Sprint 2 — Log-level discipline**: noisy `WARNING` lines for
  expected events (duplicate key press, release without a press,
  unmapped keys, etc.) were demoted to `DEBUG` so production log files
  stay clean.
- **Sprint 3 — Recording-control style consolidation continues**: the
  styling work begun in Sprint 2 is now exclusively driven by Qt dynamic
  properties applied in `_apply_button_state` / `_apply_status_role`.
- **Sprint 3 — Bare ``except`` blocks** in `views/project_view.py` were
  tightened to catch only `(TypeError, ValueError)`.
- **Sprint 3 — ``zip(..., strict=False)``** on the visualisation view's
  raster plot makes intent explicit.

### Fixed

- **B4**: Custom-behaviour colour pool cycled through only 4 of its 6
  available colours after the initial pool was exhausted. The 7th+ custom
  behaviour now correctly reuses all 6 indices (8-13) of
  `TimelineView._ordered_colors`.
- **B15**: When VLC failed to report a video's duration within the 10-second
  polling window, RABET silently fell back to a 1-minute duration. Long
  videos opened in this state appeared truncated and could not be fully
  annotated. RABET now stops polling, emits an `error_occurred` signal and
  surfaces a clear error dialog instead.
- **B7**: ``AnnotationModel._find_key_for_behavior`` no longer falls back
  to the hardcoded literal ``'I'`` when an imported behaviour has no
  matching action-map entry; it now returns an empty key, which the
  timeline gracefully renders without a glyph and the export round-trips
  without spurious collisions when the user later maps ``'I'``.
- **B12**: ``on_key_released`` now mirrors the gating in
  ``on_key_pressed``. If recording was paused (or the video stopped)
  between the press and the release, the event is finalised using the
  press-time position plus one frame duration instead of the post-pause
  position, eliminating the inconsistent offsets the asymmetric checks
  used to produce.
- **B13**: ``AnalysisController.on_configure_metrics_requested`` no
  longer assigns to ``config._latency_metrics`` /
  ``config._total_time_metrics`` directly; it uses the new public
  ``replace_metrics`` API.
- **processEvents removal**: three more redundant
  ``QApplication.processEvents()`` calls were removed
  (`_on_loading_started`, `_on_vlc_stabilized`, `switch_to_video_mode`).
  The remaining call inside the loading-progress handler keeps the
  progress dialog responsive and is intentional.

### Notes

- **B6 (multi-event-per-key)** is documented as an explicit design
  choice: ``_active_events`` remains a flat ``Dict[str, BehaviorEvent]``
  because behavioural coding workflows do not need overlapping events on
  the same key. The warning that previously fired on duplicate presses
  was demoted to a debug-level log entry.
- ``directories.last_*_directory`` persistence is deferred again - the
  remaining work intercepts each ``QFileDialog`` call site and is best
  done together with the broader "remembered file-dialog history" UX
  pass.

## [1.2.0] — 2026-05-14

Major correctness, performance and packaging release that accompanies the
RABET tool paper submission.

### Added

- MIT `LICENSE`, project `README.md`, `CITATION.cff` and a minimal
  `pyproject.toml` so the project can be installed via `pip install -e .`
  and cited reproducibly.
- Schema-versioned CSV exports: every exported annotation and summary file
  now carries a `RABET Version` and `Format Schema` row so downstream
  tools can detect the producing application. Older CSVs without these
  rows continue to load (with a debug-level note).
- On-screen Summary and Intervals tabs in the Analysis view, with a
  one-click "Copy to Clipboard" button on each. The Analysis pane used to
  emit results only via CSV export.
- Confirmation dialog before annotations are discarded when a new video
  is loaded (previously the in-memory annotations were silently cleared).
- Persistent UI settings backed by `ConfigManager`: window geometry, last
  active view, last recording duration, "preserve on rewind" preference
  and interval-analysis settings are restored on next launch.
- `tests/` directory with `pytest`-based smoke tests for module imports,
  version handling and core annotation / analysis round-trips.

### Changed

- All real-time wall-clock measurements (`time.time()`) replaced with
  monotonic clocks (`time.monotonic()`) to avoid NTP jumps corrupting
  minimum-duration enforcement.
- Annotation editing safety: when the user rewinds past an active
  (still-pressed) event during recording, that event is now discarded
  cleanly via `AnnotationModel.discard_active_event` instead of being
  finalised later with a misleading onset.
- Export dialogs for annotations and summary tables now use a `while`
  loop instead of recursion to handle repeated overwrite-decline cycles
  without growing the Python stack.
- Interval-analysis "Frequency" column relabelled to
  `Frequency (events overlapping interval)` in the exported CSV header to
  clearly distinguish it from the standard whole-session onset count.
- Audio volume is no longer reset to 80 every time a new video is loaded;
  the user's chosen volume (and mute state) is preserved across loads.

### Fixed

- **B1**: `_export_standard_summary` and `_export_interval_summary` no
  longer shadow the `file_path` parameter inside their `for` loops.
- **B2**: Removed blocking `time.sleep()` calls in `models/video_model.py`
  that froze the entire UI for ~0.7 s on every video load. Replaced with
  a `QEventLoop`-based wait that keeps Qt paint events flowing.
- **B3**: Replaced wall-clock measurements (`time.time()`) with
  `time.monotonic()` so duration enforcement is immune to NTP jumps.
- **B5**: Annotation clearance on video load now requires explicit user
  confirmation.
- **B8**: Export dialogs no longer recurse on overwrite-decline; they use
  a bounded `while` loop instead.
- **B9**: Clarified the meaning of the per-interval Frequency column.
- **B10**: Active (still-pressed) events are now correctly discarded when
  the user rewinds past their onset during recording.
- **B11**: Audio volume / mute state survives video loads.

### Removed (dead code)

- `_perform_multiple_forward_steps` / `_continue_multiple_steps` /
  `_perform_multiple_backward_steps` (folded into a single
  `handle_step_backward` using `seek_with_retry`).
- `video_overlay_panel` system in `VideoPlayerView` (was always hidden,
  add API never invoked).
- Unused `QEventLoop` imports in `video_controller.py` and
  `video_player_view.py`; unused `time`/`platform` imports in
  `video_controller.py`; unused `sys`/`QTimer` imports in
  `analysis_controller.py`.
- `add_mapping_requested` signal in `ActionMapView` (never emitted) and
  its empty slot in `ActionMapController`.
- Duplicate `ensure_app_directories` call in `AppController.__init__`
  (already called from `main.py`).
- Unused `truncated_event` local in `AnnotationController` and unused
  `_get_configs_directory` helper in `AnalysisController`.

### Performance

- Timeline drawing is now O(N) per repaint instead of O(N^2);
  `list.index` per event removed in favour of `enumerate`.
- `AnnotationController.on_position_changed` no longer rebuilds the full
  events list every 100 ms during recording. Active events update their
  right edge automatically through `_current_position`.
- `AnalysisModel._analyze_intervals` and `_calculate_total_aggression`
  reimplemented with NumPy: per-event filtering and the timeline sweep
  use vectorised operations instead of `iterrows`.
- `VideoModel._update_position` emits `position_changed` only when the
  reported value actually changes, removing redundant signal traffic when
  paused.
- Removed the application-wide event filter in `MainWindow`; focus
  tracking now installs only on the specific widgets that need it and
  reuses a single `QTimer` instead of allocating a new one per click.

### Deferred to 1.2.1

- Extraction of `_layout_diagnostics_*` helpers into a dedicated
  `utils/layout_diagnostics.py` module. The diagnostic code remains
  dormant (`_layout_diagnostics_enabled = False` by default) so this is
  purely a code-organisation cleanup.
- A `File → Recent Files` submenu backed by the persisted
  `recent_files.videos` / `recent_files.annotations` keys.

## [1.1.4] — 2025

Last release in the 1.1.x line. See git history for incremental fixes
around macOS / Linux packaging, action-map persistence and timeline
rendering.

[1.2.1]: #121--2026-05-14
[1.2.0]: #120--2026-05-14
[1.1.4]: #114--2025
