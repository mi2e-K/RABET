# RABET User Guide

> **Audience.** This guide is written for behavioural-research scientists
> who want to use RABET to score animal-behaviour video recordings, run
> downstream analyses, and assess inter-rater agreement. It assumes only
> basic familiarity with a desktop application and CSV files.

> **Scope.** Every feature of RABET 1.3.2 is covered. A separate file
> [`USER_GUIDE.ja.md`](USER_GUIDE.ja.md) provides the same content in
> Japanese.

---

## Table of contents

1. [Getting started](#1-getting-started)
2. [Annotating a video](#2-annotating-a-video)
3. [Analysing multiple recordings](#3-analysing-multiple-recordings)
4. [Visualising data](#4-visualising-data)
5. [Assessing inter-rater / intra-rater reliability](#5-assessing-inter-rater--intra-rater-reliability)
6. [Project mode](#6-project-mode)
7. [Keyboard shortcuts reference](#7-keyboard-shortcuts-reference)
8. [Configuration files and persistent settings](#8-configuration-files-and-persistent-settings)
9. [CSV file formats](#9-csv-file-formats)
10. [Troubleshooting](#10-troubleshooting)
11. [Getting help and citing RABET](#11-getting-help-and-citing-rabet)

---

## 1. Getting started

### 1.1 Downloading RABET

RABET is **officially distributed via Zenodo**, which assigns each release
a permanent DOI that you can cite:

> **Zenodo (official)**: https://doi.org/10.5281/zenodo.15313025
> *(concept DOI — always resolves to the latest version)*

Open the Zenodo record, locate the assets for your platform, and
download the corresponding archive:

| Platform | Asset |
| --- | --- |
| Windows | `RABET-Windows-1.3.2.zip` |
| macOS (Apple Silicon) | `RABET-macOS-arm64-1.3.2.zip` |
| macOS (Intel) | `RABET-macOS-x86_64-1.3.2.zip` |
| Linux | `RABET-Linux-x86_64-1.3.2.tar.gz` |

A mirror of the same binaries is published on the
[GitHub Releases page](https://github.com/mi2e-K/RABET/releases) for
convenience. Either source contains the same files.

### 1.2 Launching RABET

#### Windows

1. Unzip the archive (`RABET-Windows-1.3.2.zip`) anywhere — Desktop or
   a dedicated `Tools\` folder both work.
2. Open the extracted `RABET` folder and double-click **`RABET.exe`**,
   or use the bundled **`Launch RABET.bat`** if you prefer a shortcut.
3. Windows SmartScreen may show "Windows protected your PC" on the
   first launch because the binary is not code-signed. Click
   *More info* → *Run anyway*.

#### macOS

1. Unzip the archive matching your CPU architecture (Apple Silicon ≈
   M1/M2/M3/M4; Intel ≈ pre-2020 Macs).
2. Move the resulting **`RABET.app`** into your `Applications` folder.
3. The first launch must be done with right-click → **Open** because
   the bundle is unsigned. Subsequent launches behave normally.

#### Linux

1. Extract the tarball:
   ```bash
   tar -xzf RABET-Linux-x86_64-1.3.2.tar.gz
   ```
2. From the extracted directory, run:
   ```bash
   ./run_rabet.sh
   ```
3. Optionally install a desktop entry so RABET appears in your
   application menu:
   ```bash
   ./install_desktop_entry.sh
   ```

### 1.3 First launch — what RABET creates on disk

On its first launch, RABET creates three folders in the user
application-data directory of your operating system:

- **`configs/`** — JSON files for the action map, custom metrics, and
  colour palette
- **`logs/`** — runtime log file (`rabet_<date>.log`); useful for
  troubleshooting
- **`projects/`** — default location where new projects are saved

The exact path depends on the platform:

| OS | Location |
| --- | --- |
| Windows | `%APPDATA%\RABET\` |
| macOS | `~/Library/Application Support/RABET/` |
| Linux | `~/.config/RABET/` |

RABET also remembers the last directories used in each file dialog so
that subsequent picks open in the right place automatically.

### 1.4 The main window at a glance

The application window is organised as follows:

```
┌──────────────────────────────────────────────────────────────────┐
│  File   Edit   View   Log   Help                                 │  ← menu bar
├──────────────────────────────────────────────────────────────────┤
│  [Annotation] [Analysis] [Visualization] [Reliability] [Project] │  ← mode tabs
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│                  (active mode's main panel)                      │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│  Status bar: short messages, current file, recording state       │
└──────────────────────────────────────────────────────────────────┘
```

The **mode tabs** correspond to the five major workflows of RABET. You
can switch between them at any time from the **View** menu or by
clicking the tab; the active mode is highlighted.

---

## 2. Annotating a video

The **Annotation** view is RABET's primary workspace. It combines a
video player, a timeline, a recording-control panel, and an action-map
panel into a single screen.

```
┌───────────────────────────────────────────────────────────────────┐
│                                                  │ Action Map     │
│              Video player (frame-accurate)       │ ┌────┬───────┐ │
│                                                  │ │Key │Behav. │ │
│                                                  │ ├────┼───────┤ │
│                                                  │ │ o  │Attack │ │
│                                                  │ │ j  │Side.  │ │
│                                                  │ │... │ ...   │ │
├──────────────────────────────────────────────────│ └────┴───────┘ │
│  Recording controls — duration, Start/Pause/Stop │ [Add][Edit]    │
├───────────────────────────────────────────────────────────────────┤
│  Timeline — colour-coded events, playhead                         │
└───────────────────────────────────────────────────────────────────┘
```

### 2.1 Opening a video

Three equivalent ways:

1. **Menu**: `File → Open Video`
2. **Recent**: `File → Open Recent Video` — lists the 10 most recently
   opened video files
3. **Drag-and-drop**: drag a video file onto any part of the RABET
   window; RABET switches to Annotation mode automatically

Standard containers (`.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`, `.m4v`,
`.wmv`, `.flv`, `.ts`) are accepted by extension. If a file's extension
is unusual (some recording software writes custom suffixes such as
`.video` around a standard MP4 container), RABET falls back to a magic-
number sniff and finally to a PyAV trial-open, so the file should still
load if its bytes are valid.

After opening, RABET shows the first frame in the video display area
and resets the playhead to 0.

### 2.2 The Action Map panel

The Action Map maps **single keyboard keys** to **behaviour labels**.
While you are recording, pressing a mapped key starts a behaviour
event; releasing the same key ends it.

**Default mappings** (loaded from `configs/default_action_map.json`):

| Key | Behaviour |
| :-: | --- |
| `o` | Attack bites |
| `j` | Sideways threats |
| `p` | Tail rattles |
| `q` | Chasing |
| `a` | Social contact |
| `e` | Self-grooming |
| `t` | Locomotion |
| `r` | Rearing |

The Action Map panel (right side of the Annotation view) shows the
active map as an editable table. Use the buttons below the table to:

- **Add** — add a new key → behaviour mapping. The key field accepts
  one alphanumeric character; existing mappings prompt for confirmation
  before they are overwritten.
- **Edit** — change the behaviour label for a selected row.
- **Remove** — delete a mapping. Removing a behaviour does **not**
  delete already-recorded annotations using that label.

Saving and loading maps:

- `File → Save Action Map` writes the current map to a `.json` file
  you choose.
- `File → Load Action Map` replaces the current map with a saved one.
- `File → Reset Action Map to Default` restores the built-in map shown
  above.

### 2.3 Video controls

| Action | Shortcut |
| --- | --- |
| Toggle play / pause | `Space` |
| Step forward by one configured step | `→` (Right Arrow) |
| Step backward by one configured step | `←` (Left Arrow) |

The step size and playback rate live in the video player's control
strip below the video frame. Step size defaults to one frame; you can
change it to 5 or 10 frames if you want coarser navigation while paused.

The current playhead position is displayed as a time stamp
(`hh:mm:ss.ms`) directly below the video. While a recording session is
active, the same area also shows the **session-relative** clock.

### 2.4 Configuring a timed recording session

Above the timeline is the **Recording controls** panel. Set the test
duration with the `hh:mm:ss` input field (e.g. `00:05:00` for a
5-minute test).

If the **Preserve on rewind** checkbox is on, rewinding the video past
an active (still-pressed) behaviour will **keep** that event in the
record. If it is off (default), the active event is **discarded** as
the playhead crosses backward through its onset — useful when you
realise you started an event a few seconds too early.

### 2.5 Recording — state diagram

```
        Start Recording                Pause
  IDLE ─────────────────► WAITING ─► RECORDING ─► PAUSED
   ▲                                   ▲   │       │
   │                                   │   │ Resume│
   │                                   └───┴───────┘
   │                                   │
   │           Stop / duration elapsed │
   └───────────────────────────────────┘
```

Visual cues in the Recording controls panel:

| State | Button label | Status colour |
| --- | --- | --- |
| Idle | **Start Recording** (green) | (blank) |
| Waiting | **Cancel** (grey) | blue |
| Recording | **Pause** (orange) | red |
| Paused | **Resume** (green) / **Stop** (red) | orange |

To make a recording:

1. Open a video and set the test duration.
2. Click **Start Recording**. The state advances to **Waiting**.
3. Play the video (`Space`). The session begins (state → **Recording**)
   when the playhead first moves; all event time stamps are measured
   from that moment.
4. Press behaviour keys to tag events; release keys to end them.
5. Click **Pause** if you need to step away or review a moment — the
   playhead pauses too. Click **Resume** to continue.
6. The session ends automatically when the duration elapses, or you
   can click **Stop** at any time.

When the session ends, the video also pauses automatically. If the
recording was started from inside a project, RABET returns to the
**Project** tab after auto-saving.

### 2.6 The Timeline view

The timeline at the bottom of the Annotation view shows all recorded
events as colour-coded bars. The playhead (vertical line) tracks the
video.

Common timeline operations:

- **Zoom in / out** — use the zoom controls or the mouse wheel over
  the timeline.
- **Select an event** — click it. The selection highlights and the
  event's onset and offset appear in the status bar.
- **Delete the selected event** — press `Delete` or `Backspace`.
- **Undo the most recent recording** — `Edit → Undo Last Annotation`
  or `Ctrl + Z`. (The synthetic `RecordingStart` marker is never the
  target of Undo.)

The timeline auto-scrolls horizontally so the playhead stays in view
during playback.

### 2.7 Saving annotations

`File → Export Annotations` writes a CSV file with three sections in
the schema-v1 layout:

1. **Metadata** — RABET version, schema version, test duration
2. **Event log** — `Event, Onset, Offset` (seconds with 4-decimal
   precision)
3. **Per-behaviour summary** — `Behavior, Duration, Frequency`

For the full specification see [`CSV_FORMAT.md`](CSV_FORMAT.md).

If the file you choose already exists, RABET asks before overwriting.
If you decline, the dialog reopens so you can pick a different name —
RABET never silently drops your data.

### 2.8 Re-loading annotations

`File → Import Annotations` reads a previously exported CSV and
populates the timeline. RABET accepts both schema v0 (pre-1.2.0
exports) and v1.

`File → Recent Annotations` lists the 10 most recently opened
annotation files.

Importing into a session that already has events prompts you to
confirm; the existing in-memory annotations are cleared on confirmation.

---

## 3. Analysing multiple recordings

The **Analysis** view aggregates several annotation CSV files into one
table so you can compare animals, conditions, or repeated sessions
without writing a script.

```
┌─────────────────────────────────────────────────────────────────┐
│ [Load Files]  [Configure Metrics]   ✓ Enable interval (60 sec) │
├─────────────────────────────────────────────────────────────────┤
│ ┌────────────────┬─────────────────────────────────────────┐    │
│ │   Summary      │  Intervals                              │    │
│ ├────────────────┴─────────────────────────────────────────┤    │
│ │ animal_id │ Attack Latency │ Total Aggression │ ...      │    │
│ │ rat-01    │ 18.43          │ 92.11            │ ...      │    │
│ │ rat-02    │ 25.92          │ 71.30            │ ...      │    │
│ │ ...                                                      │    │
│ └──────────────────────────────────────────────────────────┘    │
│ [Copy to Clipboard]  [Export CSV]  [Visualize Files]            │
└─────────────────────────────────────────────────────────────────┘
```

### 3.1 Loading CSV files

Two ways:

1. Click **Load Files** and select one or more annotation CSV files.
2. Drag annotation CSVs onto the window.

RABET parses each file, extracts the `animal_id` from the file name
(by default, the file name stem), and applies the current metrics
configuration. Files that fail to parse are skipped with a warning in
the log.

### 3.2 The Summary tab

The **Summary** tab shows one row per file with the following columns:

- `animal_id`
- One pair of columns per behaviour: `<behaviour> Duration`,
  `<behaviour> Frequency`
- Custom metric columns (see §3.4)

`Duration` is the total time (seconds) spent in the behaviour during
the whole session. `Frequency` is the number of distinct events.

Click **Copy to Clipboard** to copy the entire table in a format
suitable for direct paste into Excel, JASP, R, or SPSS.

### 3.3 The Intervals tab — time-binned analysis

Tick **Enable interval analysis** to split each session into fixed-
length windows (default 60 seconds). The Intervals tab then shows one
row per `(animal, interval)` pair.

Important interpretation note:

- **`Duration`** is the number of seconds of the behaviour that
  *overlap* the interval — a behaviour that straddles two intervals is
  apportioned to both.
- **`Frequency`** counts behaviours whose **onset** falls inside the
  interval — a single behaviour is counted once even if it spans
  multiple intervals.

This makes per-interval Duration suitable for cumulative rate plots and
Frequency suitable for event-count statistics.

### 3.4 Configuring custom metrics

Click **Configure Metrics** to open the metrics editor. Two kinds of
metrics are supported:

#### Latency metrics

Time, in seconds, from the start of the session to the **first**
occurrence of a chosen behaviour. The default configuration ships
with:

- *Attack Latency* — first `Attack bites` event

You can add as many latency metrics as you need (e.g. *Sideways
threats Latency*) and toggle each on or off independently.

#### Total-time metrics

Overlap-aware total time across a chosen set of behaviours. When raw
events are available, overlapping intervals are collapsed so simultaneous
behaviours are not double-counted. The default configuration ships with:

- *Total Aggression* — Attack bites + Sideways threats + Tail rattles
  + Chasing
- *Total Aggression (without tail-rattles)* — Attack bites + Sideways
  threats + Chasing

The set of behaviours per total-time metric is editable, so you can
define category sums tailored to your study (e.g. *Exploration* =
Locomotion + Rearing).

When only a Summary section is available and raw event onsets/offsets
are missing, RABET can only sum the listed behaviour durations. Multi-
behaviour total-time metrics from summary-only input are therefore marked
as approximate.

### 3.5 Exporting results

- **Copy to Clipboard** copies the active tab as TSV (tab-separated
  values) ready for spreadsheet import.
- **Export CSV** writes the Summary table as `summary_table.csv`. If
  interval analysis is enabled, the interval table is also exported as
  `summary_intervals.csv` alongside it.
- **Visualize Files** switches to the Visualization tab with the
  currently loaded files already selected.

### 3.6 Bout and transition figure export

The optional **Bout Analysis** and **Transition Analysis** windows are
opened from the Analysis view. Figure tabs now include **Export
Figure...** controls:

- Bout Analysis **Raster** can be saved as PNG, SVG, or PDF.
- Transition Analysis **Heatmap** can be saved as PNG, SVG, or PDF.
- Transition Analysis **Predictability** can save its bar chart as PNG,
  SVG, or PDF.

Use the adjacent **DPI** control before exporting. The Windows file
dialog lets you choose the destination and file extension; if the
extension is omitted, RABET uses the selected file-type filter. The
export-complete notification closes automatically after one second.

---

## 4. Visualising data

The **Visualization** view renders a raster plot — one row per
animal/file, one tick per event, colour-coded by behaviour.

### 4.1 Raster plot basics

After loading annotation CSVs (or jumping in from Analysis via
**Visualize Files**), each file becomes a horizontal track. Events
appear as coloured tick marks at their onset time.

On a first load with multiple files, RABET defaults to showing **only
the first file** to keep the view legible; the remaining files appear
unchecked in the file list on the right.

### 4.2 Filtering

Two panels of checkboxes control what is shown:

- **Files / individuals** — toggle each animal track on or off.
- **Behaviours** — toggle each behaviour colour on or off. A colour
  swatch is shown next to each behaviour label.

Use these to focus on a subset (e.g. only aggressive behaviours, only
the test animals from one condition) without re-loading data.

### 4.3 Customising colours

Click a colour swatch next to a behaviour name to open a colour
picker. The selected colour is applied immediately and saved to
`configs/custom_color_map.json`, so it persists across application
restarts.

To reset to the default palette, delete `custom_color_map.json` while
RABET is closed.

### 4.4 Grid lines and axis range

- **Vertical grid / Horizontal grid** — toggle separately.
- **Grid colour** — click the grid colour swatch to change.
- **Max range** — set the visible x-axis maximum (seconds). Useful for
  comparing a 5-minute and a 10-minute session side by side without
  the longer one stretching the shorter one.

### 4.5 Exporting the plot

Click **Export** to save the current view as **PNG**, **SVG**, or
**PDF**. The file format is taken from the file extension you choose;
if you omit the extension, the format selected in the dialog filter is
used (no surprises).

---

## 5. Assessing inter-rater / intra-rater reliability

The **Reliability** view computes agreement metrics directly from
RABET's own outputs. Two modes are provided, both reachable from the
mode bar at the top of the view.

### 5.1 What the Reliability tab does

- **Inter-rater reliability** — two scorers code the same videos, and
  you want to know how closely their numbers agree.
- **Intra-rater reliability** — one scorer codes the same video twice
  (separated in time), to test their own consistency.

The same RABET tab handles both: it does not care whether the two
CSV files came from the same scorer or different ones.

### 5.2 Summary mode

**Required inputs.** Two `summary_table.csv` files exported from the
Analysis view, one per scorer (or one per scoring round). Each row in
each file represents one animal identified by `animal_id`.

**Procedure.**

1. Switch to the **Reliability** view (`View → Reliability`).
2. Choose **Summary mode**.
3. Click **Load Summary CSV A** and pick the first file.
4. Click **Load Summary CSV B** and pick the second file.
5. RABET matches animals on `animal_id` across the two files and
   computes, **per metric**:
   - **ICC(2,1)** — two-way random, single-measurement intraclass
     correlation
   - **Pearson r** — linear correlation of paired metrics
   - **Mean absolute difference** — average `|A − B|` across matched
     animals
   A scatter plot per metric is rendered automatically.

ICC and Pearson r are shown as unavailable when the paired metric has no
between-animal variance. Exact equality of constant values is still exact
equality, but the statistic itself is not identifiable.

**Output.** The results table colour-codes ICC values using Cicchetti
(1994) bands:

| ICC | Interpretation | Colour |
| --- | --- | --- |
| ≥ 0.75 | excellent | green |
| 0.50 – 0.75 | fair / good | amber |
| < 0.50 | poor | red |

Click **Export Results** to save the table as a CSV.

Animals that appear in only one file are listed under
**Unmatched animals** below the table, so you can verify that any
missing IDs are intentional.

### 5.3 Detailed mode

**Required inputs.** Two annotation CSVs (one per scorer / round)
scored on the **same video**, so onset / offset times are directly
comparable.

**Procedure.**

1. Choose **Detailed mode** in the Reliability view.
2. Load Annotation CSV A and Annotation CSV B.
3. Set the **bin width** (seconds). A bin width of 1 s is a common
   default for moment-to-moment behavioural coding.
4. RABET converts each annotation track into a per-bin behaviour
   vector and computes, for every behaviour found in either file:
   - **Cohen's κ** — chance-corrected agreement
   - **Krippendorff's α** — alpha with nominal data treatment
   - **Raw % agreement** — fraction of bins where both raters agree
5. A pairwise event-raster overlay shows both raters' events stacked
   vertically per behaviour, with disagreement segments visible at a
   glance.

If a behaviour is absent from every compared bin for both raters, raw %
agreement can be 100% while Cohen's kappa and Krippendorff's alpha are
unavailable; this is the correct degenerate-case treatment rather than
evidence of perfect chance-corrected reliability.

The κ values are colour-coded using Landis & Koch (1977) bands:

| κ | Interpretation | Colour |
| --- | --- | --- |
| ≥ 0.70 | substantial | green |
| 0.40 – 0.70 | moderate | amber |
| < 0.40 | poor | red |

Krippendorff's α uses the same bands as κ.

### 5.4 Interpretation guide

The colour banding is meant as a **screening tool**, not a substitute
for context-specific judgment:

- Cicchetti's ICC bands (poor / fair / good / excellent at 0.4 / 0.59
  / 0.74) come from clinical-measurement contexts; behavioural-science
  conventions are similar but vary by field.
- Landis & Koch's κ bands are widely cited but were proposed as a
  *guideline*, not a hard rule. In dense, fast-changing behaviour, even
  good raters often land in the 0.4 – 0.6 range.

If you see agreement that is lower than you expect, the **Detailed
mode raster overlay** is the fastest way to spot the source —
typically a constant offset (one rater starts each event 1–2 s late) or
a class-confusion (one rater splits a behaviour into two sub-classes
the other rater does not use).

### 5.5 Cross-language reproducibility

`docs/reliability/compute_agreement.R` is a stand-alone R script that
reproduces every Summary-mode statistic (`ICC(2,1)` via `psych::ICC`,
Pearson r via `cor`, mean absolute difference). Run it as a sanity
check or to embed RABET-derived agreement numbers into an R analysis
pipeline:

```r
source("docs/reliability/compute_agreement.R")
compute_agreement("rater_a_summary.csv", "rater_b_summary.csv")
```

---

## 6. Project mode

A **project** in RABET is a directory plus a small manifest file that
groups related assets:

- **Videos** to score
- **Annotation CSVs** scored from those videos
- **Action maps** used during scoring
- **Analyses** (saved summary tables, interval tables, etc.)

Projects help when you are scoring an experiment with many videos and
want a single place to track which ones have been done and how.

### 6.1 Creating a new project

1. `View → Project` to switch to the Project mode.
2. Click **New Project**.
3. Choose a parent directory, enter a project name and an optional
   description.

RABET creates a project subdirectory and an empty manifest file. The
project view now shows the (still empty) tree.

### 6.2 Adding files

Use the **Add Video**, **Add Annotation**, **Add Action Map**, and
**Add Analysis** buttons. Each opens a file picker.

- A confirmation dialog asks whether to **copy the file into the
  project directory** (recommended for reproducibility, makes the
  project self-contained) or **link by reference** (leaves the file
  where it is).
- Adding many files is allowed; the manifest is auto-saved after each
  change.

### 6.3 Annotating from inside a project

Select a video in the tree and click **Annotate**. RABET:

1. switches to the Annotation view,
2. loads the selected video,
3. records annotations into a file inside the project directory.

When the recording session ends, RABET returns to the Project view
automatically and the new annotation appears in the tree.

The annotation file name follows a human-readable pattern (e.g.
`rat-01_2026-05-21_001.csv`) — the older versions used an opaque
internal video hash in the file name, which 1.2.2 removed.

### 6.4 Saving and re-opening projects

- **Save Project** is implicit: the manifest is rewritten after each
  Add / Remove / Annotate operation.
- **Open Project** asks for a project directory.
- **Close Project** clears the in-memory project state and returns the
  Project view to the empty start screen.

If you have one project open and try to load a video whose annotation
would collide with the project's, RABET warns rather than silently
reusing the project's annotation path.

---

## 7. Keyboard shortcuts reference

Open the **Help → Show Shortcuts** dialog (or press `F1`) to see the
current set, including your behaviour-key map. For reference, the
**built-in** shortcuts are:

| Shortcut | Action |
| --- | --- |
| `Space` | Toggle video play / pause |
| `→` | Step forward by the configured step size |
| `←` | Step backward by the configured step size |
| `Ctrl + Z` | Undo the most recently recorded annotation |
| `Delete` or `Backspace` | Delete the selected timeline annotation |
| `F1` | Open the Shortcuts dialog |
| (any mapped key) | Tag the corresponding behaviour while recording |

Behaviour keys come from the active action map and are editable from
the Action Map panel — see §2.2.

---

## 8. Configuration files and persistent settings

### 8.1 Where RABET stores user data

| OS | Path |
| --- | --- |
| Windows | `%APPDATA%\RABET\` |
| macOS | `~/Library/Application Support/RABET/` |
| Linux | `~/.config/RABET/` |

Below that root, RABET maintains:

- `configs/default_action_map.json` — built-in defaults (never
  modified after first launch)
- `configs/user_action_map.json` — the action map you've edited; this
  is what RABET loads on startup
- `configs/default_metrics.json` — the latency / total-time metrics
  configuration
- `configs/custom_color_map.json` — per-behaviour raster-plot colours
- `logs/rabet_<date>.log` — runtime log

### 8.2 Persistent UI settings

The window geometry, last-opened view, recording duration, step size,
playback rate, "preserve on rewind" flag, interval-analysis settings,
recent-files lists and last-used file-dialog directories are stored
between runs.

### 8.3 Resetting to defaults

The fastest reset:

- **Action map**: `File → Reset Action Map to Default`
- **Custom colours**: delete `configs/custom_color_map.json`
- **Everything**: close RABET and delete the entire RABET application
  data folder

---

## 9. CSV file formats

RABET exports three CSV layouts:

- **Annotation CSV** — produced by `File → Export Annotations` from
  the Annotation view. Three sections (metadata, event log, summary).
- **Summary CSV** (`summary_table.csv`) — produced by the Analysis
  view. One row per animal with custom-metric columns.
- **Interval summary CSV** (`summary_intervals.csv`) — produced by the
  Analysis view when interval analysis is enabled. One row per
  `(animal, interval)` pair.

All three carry `RABET Version` and `Format Schema` metadata so
downstream tools can detect the producing application. Times are
seconds with 4-decimal precision; the encoding is UTF-8.

The complete schema, the v0 → v1 compatibility matrix, and a minimal
pandas parser live in [`CSV_FORMAT.md`](CSV_FORMAT.md).

---

## 10. Troubleshooting

### "Video won't open even though VLC can play it"

RABET 1.3.2 accepts any file whose extension is in its whitelist, or
whose first bytes match a known video container (via the `filetype`
library), or which PyAV can open as a trial. If a file fails all three
tests, RABET shows an error. Convert the file with FFmpeg as a
last resort:

```bash
ffmpeg -i input.unknown -c copy output.mp4
```

### "Reliability tab metrics show as blank / None"

The Reliability tab depends on `pingouin`, `scipy`, `statsmodels`,
and `krippendorff`. In the pre-built binary these are bundled. If you
run from source, install with:

```bash
pip install pingouin krippendorff
```

If you see `ImportError` in `logs/rabet_<date>.log` mentioning these
packages, the bundle is missing them — please open an issue with the
log attached.

### "I rewound past an event and lost it"

By default, RABET discards an active (still-pressed) event when the
playhead rewinds past its onset. Toggle the **Preserve on rewind**
checkbox in the Recording controls panel to keep such events instead.

### "RABET shows the wrong fonts on first launch"

On macOS, the first-launch font scan may flag a handful of system
fonts as unloadable. This is benign; the rest of the matplotlib font
database loads fine and RABET uses Qt's default font for its widgets.

### Where to find the log file

`Log → View Logs` opens the log directory in your OS file manager. The
most recent file is `rabet_<today>.log`. You can also use
`Log → Clean Up Logs` to delete log files older than 30 days.

---

## 11. Getting help and citing RABET

### Help and bug reports

- **Issues**: https://github.com/mi2e-K/RABET/issues
- Please include the application version (`Help → About`) and the
  relevant log file when reporting a problem.

### Citing RABET

Machine-readable citation metadata lives in
[`CITATION.cff`](../CITATION.cff). A human-readable form is:

> Mitsui, K. (2026). *RABET — Real-time Animal Behavior Event Tagger*
> (Version 1.3.2). https://github.com/mi2e-K/RABET
> doi:[10.5281/zenodo.15313025](https://doi.org/10.5281/zenodo.15313025)

The DOI above is the **concept DOI** and always resolves to the
latest RABET release on Zenodo. Each individual release also receives
its own version-specific DOI.

A tool paper describing RABET is in preparation. Once published,
please cite the paper in addition to (or instead of) the Zenodo
deposit.
