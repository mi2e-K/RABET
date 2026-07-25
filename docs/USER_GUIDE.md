# RABET User Guide

This guide covers RABET 1.4.2. It is written for researchers who want to
annotate animal-behaviour videos, aggregate annotation files, visualise event
patterns, assess scorer reliability, and run the bout and transition analyses
included in RABET.

The Japanese version is available through the documentation site's language
switcher and in the repository as
[USER_GUIDE.ja.md](https://github.com/mi2e-K/RABET/blob/main/docs/USER_GUIDE.ja.md).

---

## Contents

1. [Getting Started](#1-getting-started)
2. [Annotating Videos](#2-annotating-videos)
3. [Analysing Annotation Files](#3-analysing-annotation-files)
4. [Bout Analysis](#4-bout-analysis)
5. [Transition Analysis](#5-transition-analysis)
6. [Visualisation](#6-visualisation)
7. [Reliability Assessment](#7-reliability-assessment)
8. [Project Mode](#8-project-mode)
9. [Configuration and Files](#9-configuration-and-files)
10. [Troubleshooting](#10-troubleshooting)
11. [Citation and Support](#11-citation-and-support)

---

## 1. Getting Started

### 1.1 Download RABET

The latest binaries are published on the
[GitHub Releases page](https://github.com/mi2e-K/RABET/releases/latest).
The Zenodo concept DOI is provided for citation and long-term archival
reference: [10.5281/zenodo.15313025](https://doi.org/10.5281/zenodo.15313025).

| Platform | File |
| --- | --- |
| Windows installer | `RABET-Windows-1.4.2-Setup.zip` |
| Windows portable | `RABET-Windows-1.4.2-portable.zip` |
| macOS Apple Silicon | `RABET-macOS-arm64-1.4.2.dmg` |
| macOS Intel | `RABET-macOS-x86_64-1.4.2.dmg` |
| Linux | `RABET-Linux-x86_64-1.4.2.AppImage` |

All packages are self-contained. You do not need a separate VLC, FFmpeg,
Python, R, scipy, or codec-pack installation to use the released app.

### 1.2 Launch RABET

**Windows installer**

1. Unzip `RABET-Windows-1.4.2-Setup.zip`.
2. Run `RABET-Setup.exe`.
3. Launch RABET from the Start Menu or desktop shortcut.

**Windows portable**

1. Unzip `RABET-Windows-1.4.2-portable.zip`.
2. Open the extracted folder.
3. Run `RABET.exe`.

Windows SmartScreen may warn on first launch because the binaries are not code
signed. Choose **More info** and **Run anyway** if you trust the release file.

**macOS**

1. Open the DMG for your CPU architecture.
2. Drag `RABET.app` to Applications.
3. If macOS says the app is damaged or cannot be verified, remove the download
   quarantine once:

```bash
xattr -dr com.apple.quarantine /Applications/RABET.app
```

Then open `RABET.app` normally.

**Linux**

```bash
chmod +x RABET-Linux-x86_64-1.4.2.AppImage
./RABET-Linux-x86_64-1.4.2.AppImage
```

### 1.3 What RABET Creates

On first launch, RABET creates a user data folder:

| OS | Location |
| --- | --- |
| Windows | `%APPDATA%\RABET\` |
| macOS | `~/Library/Application Support/RABET/` |
| Linux | `~/.config/RABET/` |

The folder contains:

- `configs/`: action maps, metric settings, and colour maps.
- `logs/`: runtime logs for troubleshooting.
- `projects/`: default location for RABET projects.

RABET also remembers the last folders used in file dialogs.

### 1.4 Main Workflows

The main window is organised into five tabs:

| Tab | Purpose |
| --- | --- |
| Annotation | Open videos and record behaviour events. |
| Analysis | Aggregate annotation CSVs, export summaries, open bout and transition tools. |
| Visualization | Draw multi-file raster plots. |
| Reliability | Compare two scorers or two scoring rounds. |
| Project | Manage videos, annotations, action maps, and analyses together. |

Some heavier tabs are constructed lazily to keep startup fast. On first access,
RABET may briefly show a loading overlay.

---

## 2. Annotating Videos

### 2.1 Open a Video

You can open a video in any of these ways:

1. `File > Open Video`
2. `File > Open Recent Video`
3. Drag a video file onto the RABET window

Common video extensions such as `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`,
`.m4v`, `.wmv`, `.flv`, and `.ts` are accepted. If an unusual extension wraps
a normal video container, RABET also tries file-signature detection and a PyAV
trial open.

### 2.2 Action Maps

The Action Map assigns one keyboard key to one behaviour label. In RABET 1.4.0
each mapping also has a **Type**:

| Type | Meaning | Recording behaviour |
| --- | --- | --- |
| State | Records an interval with an onset and offset. | Press key to start, release key to end. |
| Point | Records a single timestamp without duration. | Press key once to record the event. |

Choose State when onset and offset should be recorded, and Point when the event
should be represented by a single timestamp. This choice reflects the desired
data representation rather than how quickly the behaviour occurs.

Use the Action Map buttons:

- **Add**: create a new mapping and choose State or Point.
- **Edit**: change a label or type for the selected key.
- **Remove**: delete a mapping. Existing annotations are not deleted.

Action maps are saved as JSON. Older maps remain compatible: a plain
`"key": "Behaviour"` entry is treated as a State event. Point mappings are
stored with an explicit `kind`.

#### Which action map is in use

The heading above the mapping table names the map you are currently editing
and recording with:

| Heading | Meaning |
| --- | --- |
| `Action Map` | No project is open. The global action map is in use. |
| `Action Map — <project>` | The open project has its own action map. Edits are saved into the project and leave the global map untouched. |
| `Action Map — global` | A project is open but has no action map of its own, so the global one is in use. Edits here change the global map. |

See [Project action maps](#project-action-maps) for how a project gets its own
map.

#### Changing a map that already has annotations

If the open project already contains annotated videos, RABET asks for
confirmation before a change that redefines what a key means — renaming a
behaviour, switching a key between State and Point, removing a mapping, or
replacing the whole map through Load or Reset. Adding a new key is purely
additive and is never questioned.

Existing annotation CSVs are never modified. The warning is about consistency:
recordings made after the change may not be directly comparable with those
already collected. You can always continue if the change is intended.

### 2.3 Video Controls

| Action | Shortcut |
| --- | --- |
| Play or pause | `Space` |
| Step forward | `Right Arrow` |
| Step backward | `Left Arrow` |
| Undo last annotation | `Ctrl + Z` |
| Delete selected timeline event | `Delete` or `Backspace` |
| Show shortcuts | `F1` |

The step size and playback rate are set in the video control strip below the
frame. The timestamp display shows video time and, during recording,
session-relative time.

### 2.4 Timed Recording

Set the test duration in the Recording controls panel, then click
**Start Recording**. RABET enters a waiting state. Press any key to start the
session and video playback. This first keypress is used only as the start
signal and never creates an annotation, even if it is mapped to a behaviour.

Typical flow:

1. Open a video.
2. Set the test duration, for example `00:05:00`.
3. Click **Start Recording**.
4. Press `Space` to start the session and play the video.
5. Press behaviour keys while scoring.
6. Use **Pause**, **Resume**, or **Stop** as needed.

When the duration elapses, RABET stops the recording and pauses playback.

### 2.5 Rewind Handling

If **Preserve on rewind** is off, an active state event is discarded when the
playhead is moved backward past its onset. This is useful when you started an
event too early. If the checkbox is on, that active event is kept.

Point events are completed immediately, so they are not held in the active
key list.

### 2.6 Timeline Editing

The timeline shows state events as bars and point events as narrow ticks.

Common actions:

- Click an event to select it.
- Press `Delete` or `Backspace` to remove the selected event.
- Use `Ctrl + Z` to undo the most recently recorded event.
- Use the zoom controls or mouse wheel to inspect dense sections.

### 2.7 Export and Import Annotations

`File > Export Annotations` writes an annotation CSV with:

1. Metadata
2. Event log
3. Per-behaviour summary

State events have `Offset > Onset` unless they are zero-length by design.
Point events have `Onset == Offset`. Frequency counts both state and point
events. Duration for point events is zero.

`File > Import Annotations` reloads a RABET annotation CSV into the timeline.
If events are already loaded, RABET asks before replacing them.

#### Where recordings are auto-saved

When a timed recording ends, RABET writes the annotation CSV automatically.

Outside Project mode the file is saved next to the source video as
`<video name>_annotations.csv`. To collect these in one place instead, use
`File > Set Auto-Save Folder` and choose a directory; every later non-project
recording is written there. `File > Reset Auto-Save Folder to Default` returns
to saving next to each video. The choice persists across sessions.

If a file of that name already exists, RABET appends a timestamp rather than
overwriting it. Note that videos with the same filename in different folders
produce the same CSV name, so collecting them into a shared folder makes the
timestamped copies harder to tell apart.

In Project mode the destination is fixed to the project's `annotations`
folder and is not affected by this setting.

---

## 3. Analysing Annotation Files

The Analysis tab aggregates multiple annotation CSVs into tables suitable for
spreadsheets or statistical software.

### 3.1 Load Files

Load one or more annotation CSVs with **Load Files** or by drag and drop.
RABET derives `animal_id` from each file name. Files are naturally sorted, so
`RI_2` is shown before `RI_10`.

The **Files** tab lists loaded file names and paths.

### 3.2 Summary Table

The **Summary** tab contains one row per file plus `mean` and `SEM` rows.
Columns are grouped as:

- `animal_id`
- one duration column per behaviour, labelled `<behaviour> (s)`
- one frequency column per behaviour, labelled `<behaviour> (n)`
- custom latency metrics
- custom total-time metrics

Point behaviours usually contribute to frequency, not duration.

### 3.3 Interval Analysis

Enable **Enable interval analysis** and set an interval size in seconds.
The **Intervals** tab then contains one row per animal and interval.

Interpretation:

- Duration is overlap-aware. A state event crossing an interval boundary is
  split across intervals.
- Frequency is counted by onset. An event is counted in the interval where it
  starts.
- Point events have zero duration but still contribute to frequency.

### 3.4 Custom Metrics

Open **Configure Metrics...** to edit study-specific metrics.

**Latency metrics** measure time from recording start to the first occurrence
of one behaviour. If the behaviour never occurs, the value is blank.

**Total-time metrics** sum time across a set of behaviours. When raw event
onsets and offsets are available, RABET collapses overlapping intervals so
simultaneous behaviours are not double-counted.

### 3.5 Output

- **Copy to Clipboard** copies the active table as tab-separated text.
- **Export Summary Table** writes `summary_table.csv`; when interval analysis
  is enabled, it also writes `summary_intervals.csv`.
- **Visualize** opens the loaded files in the Visualization tab.
- **Bout Analysis...** opens the bout-analysis dialog.
- **Transition Analysis...** opens the transition-analysis dialog.

The standard Summary and Intervals tables are intentionally kept separate from
bout and transition analysis. Opening those tools does not alter the normal
summary export.

---

## 4. Bout Analysis

Bout analysis clusters repeated events of the same behaviour into episodes.
This is useful when a rapid burst of repeated acts should be treated as one
behavioural unit.

### 4.1 Open the Dialog

1. Load annotation CSVs in the Analysis tab.
2. Click **Bout Analysis...**.
3. Select one or more behaviours.
4. Set the **Bout criterion (s)**, also called BCI.

Two consecutive same-behaviour events belong to the same bout when their gap
is less than or equal to the BCI.

For state events, the gap is the next onset minus the current bout's running
maximum offset. For point events, onset and offset are identical, so the same
calculation becomes onset-to-onset spacing.

### 4.2 Choosing the BCI

You can type a BCI directly or click **Estimate BCI...**. The estimate is
advisory and is applied to the spin box for review. RABET tries a two-component
log-normal mixture first and falls back to a broken-stick estimate when the
mixture cannot be fit. Sparse or unimodal data may not yield a stable estimate.

Use the same BCI across groups when you intend to compare group-level bout
statistics.

### 4.3 Bout Table

The Table tab reports each selected `(animal_id, behaviour)` pair:

- number of events
- number of bouts
- mean events per bout
- mean, median, and total bout duration
- active time within bouts
- mean inter-bout interval
- bouts per minute when session duration is available

You can copy the table or export it as CSV.

### 4.4 Bout Raster and Figure Export

The Raster tab displays bouts per animal. Bar height and colour indicate the
number of events in each bout. You can export:

- the bout raster figure as PNG, SVG, or PDF
- the underlying bout list as CSV

Set **DPI** before exporting figures. The completion dialog closes
automatically after one second.

---

## 5. Transition Analysis

Transition analysis counts first-order transitions: which behaviour follows
which behaviour next. Rows are antecedents and columns are consequents.

### 5.1 Open the Dialog

1. Load annotation CSVs in the Analysis tab.
2. Click **Transition Analysis...**.
3. Choose an animal or **All animals (pooled)**.
4. Choose Event level or Bout level.
5. Optionally set a time window or exclude self-transitions.

Pooled results are computed by counting transitions within each animal first
and then summing matrices. RABET does not create artificial transitions
between the end of one animal and the start of another.

### 5.2 Event Level and Bout Level

**Event (each event)** uses each recorded event as a token. Repeated events of
the same behaviour can therefore produce self-transitions such as `Attack ->
Attack`.

**Bout (collapse by BCI)** first merges same-behaviour bursts into bouts, then
counts transitions between those episode-level tokens. This is often more
appropriate when bursts would otherwise dominate the diagonal.

### 5.3 Window and Self-Transitions

**Window (s, 0=off)** restricts a transition to consecutive events whose gap
is within the specified time. A long delay can therefore be excluded rather
than treated as a meaningful transition.

**Exclude self-transitions** treats the diagonal as structural zero. Expected
counts are then fitted with iterative proportional fitting so row and column
margins remain matched.

### 5.4 Matrix Metrics

The **Show** menu changes the text displayed in each matrix cell:

| Metric | Meaning |
| --- | --- |
| Adjusted residual (z) | Chance-corrected residual. Positive means more transitions than expected; negative means fewer. |
| Conditional P(j\|i) | Raw probability of consequent `j` given antecedent `i`. |
| Odds ratio (vs rest) | Association of antecedent `i` with consequent `j` compared with all other antecedents and consequents. |
| Counts | Observed transition count. |

Cell colour always represents the adjusted residual z. Bold cells indicate
`|z| > 1.96`, approximately `p < .05` under large-sample assumptions. Cells
with antecedent base count below 30 are flagged as unstable and should be
interpreted cautiously.

### 5.5 Heatmap and CSV Export

The Heatmap tab visualises adjusted residuals. Export the heatmap as PNG, SVG,
or PDF with a chosen DPI.

**Export Tidy CSV (all animals)...** writes one long-format row per
`animal_id, antecedent, consequent` combination, including observed count,
conditional probability, expected count, adjusted residual, odds ratio, flags,
level, BCI, and window.

### 5.6 Predictability

The Predictability tab asks a focused question:

> Of all target occurrences, what fraction were preceded within a time window
> by any selected antecedent behaviour?

Choose:

- target behaviour
- antecedent set
- window size
- event-level or bout-level target definition
- optional chance correction

Chance correction circularly shifts antecedent times to estimate a baseline
given how common the antecedents are. The table reports per-animal observed
fraction, chance mean, and above-chance fraction. Group comparisons should be
run downstream.

The bar chart can be exported as PNG, SVG, or PDF.

---

## 6. Visualisation

The Visualization tab creates raster plots across multiple annotation files.

### 6.1 Load and Filter

Load annotation files directly or open them from Analysis with **Visualize**.
Each file becomes one row. Events are drawn at their onset time and coloured
by behaviour.

Use the file and behaviour checklists to control visibility. Colour swatches
beside behaviour names open a colour picker.

### 6.2 Plot Options

Options include:

- vertical and horizontal grid lines
- grid colour
- x-axis maximum range
- file label numbering
- file separators
- automatic sizing
- transparent outside-plot background

Custom behaviour colours are saved in `configs/custom_color_map.json`.

### 6.3 Export

Use **Export** to save PNG, SVG, or PDF. PNG export has a DPI setting.

---

## 7. Reliability Assessment

The Reliability tab supports inter-rater and intra-rater checks. RABET does
not need to know which design you used; it simply compares two sets of files.

### 7.1 Summary Mode

Use Summary mode when you have two `summary_table.csv` files from the Analysis
tab, usually one per scorer or scoring round.

RABET matches rows by `animal_id` and computes each metric separately:

- ICC(2,1): two-way random, absolute-agreement, single-measure ICC
- Pearson correlation
- mean absolute difference

ICC and Pearson correlation are unavailable when the paired metric has no
between-animal variance. This is expected: exact equality of constants can be
true, but correlation-style statistics are not identifiable.

The companion script `docs/reliability/compute_agreement.R` reproduces the
Summary-mode ICC, Pearson r, and mean absolute difference using R.

### 7.2 Detailed Mode

Use Detailed mode when you have two annotation CSVs scored on the same video.
RABET bins time into a user-selected bin width and compares behaviour presence
per bin.

For each behaviour, RABET reports:

- Cohen's kappa
- Krippendorff's alpha for nominal data
- raw percentage agreement

If both raters are all-zero for a behaviour, raw agreement may be 100%, but
kappa and alpha are unavailable. This avoids reporting perfect
chance-corrected reliability where the statistic is undefined.

The disagreement review table and raster overlay help identify timing offsets,
missed events, and category confusions.

### 7.3 Disagreement Review

After computing agreement in Detailed mode, click **Review disagreements...**
to inspect individual event-level differences. The first annotation CSV loaded
in Detailed mode is treated as the **Reference**, and the second as the
**Trainee**. Click **Load video...** and select the video scored in both files.
The dialog then links each review item to the corresponding position in the
video and shows the Reference and Trainee annotations in separate raster rows.

Use **First**, **Prev**, **Next**, and **Last** to move through review items in
time order. **Behavior** restricts the displayed list to one behaviour, and
**Type** restricts it to one disagreement class. These filters affect only the
displayed list; they do not change the agreement calculations, event matching,
or CSV export. **Behavior display settings...**, **Show legend**, and
**White background** change only the raster appearance.

#### Review parameters

- **Window: +/-** is the temporal tolerance used for event matching. The
  default is 2 s. A same-behaviour pair is classified as **Time matched** only
  when both its onset difference and offset difference are no greater than the
  selected Window. Smaller values apply stricter temporal matching; larger
  values allow greater scorer-to-scorer timing variation and may pair events
  that should instead be reviewed separately.
- **Pre-roll** controls how many seconds before the selected review item video
  playback begins. The default is 1 s. It is a navigation aid only and does not
  affect matching, kappa, alpha, or the exported review CSV.

The Disagreement Review Window is separate from the **bin width** used by
Detailed mode. Bin width controls the time bins used to compute Cohen's kappa,
Krippendorff's alpha, and raw agreement. Changing the review Window rebuilds
the event matches but does not recompute those bin-based statistics.

RABET compares only events with the same behaviour label and creates
one-to-one pairs. It prioritises pairs with stronger temporal overlap, then
closer event timing. Each event is assigned one of four statuses:

- **Time matched**: both onset and offset differences are within Window.
  These events appear in the counts but are omitted from the disagreement
  navigation list and review CSV.
- **Timing offset**: RABET found a plausible same-behaviour pair, but its onset
  or offset difference exceeds Window.
- **Reference only**: no Trainee event was paired with the Reference event.
- **Trainee only**: no Reference event was paired with the Trainee event.

#### Disagreement review CSV

Click **Export review CSV...** to write `disagreement_review.csv`. The export
contains one row for every **Timing offset**, **Reference only**, and
**Trainee only** item. It always contains the complete disagreement set,
regardless of the current Behavior and Type filters. Time-matched pairs are not
included.

| Column | Meaning |
| --- | --- |
| `Type` | Disagreement class: `timing_offset`, `reference_only`, or `trainee_only`. |
| `Behavior` | Behaviour label shared by the event pair, or belonging to the unmatched event. |
| `Jump_time_s` | Video navigation target before Pre-roll is applied. For a paired row, this is the earlier onset; for an unmatched row, it is that event's onset. |
| `Review_start_s` | Start of the event interval to review: the earlier onset for a pair, or the unmatched event onset. |
| `Review_end_s` | End of the event interval to review: the later offset for a pair, or the unmatched event offset. |
| `Reference_onset_s` | Original Reference onset. Blank for `trainee_only`. |
| `Reference_offset_s` | Original Reference offset. Blank for `trainee_only`. |
| `Trainee_onset_s` | Original Trainee onset. Blank for `reference_only`. |
| `Trainee_offset_s` | Original Trainee offset. Blank for `reference_only`. |
| `Onset_delta_s` | Absolute onset difference for a paired row. Blank for an unmatched row. |
| `Offset_delta_s` | Absolute offset difference for a paired row. Blank for an unmatched row. |
| `Overlap_s` | Temporal intersection of the paired events in seconds; 0 for non-overlapping or unmatched events. |
| `IoU` | Intersection over union of the two event intervals, from 0 to 1; larger values indicate greater temporal overlap. Blank for an unmatched row. |
| `Matching_window_s` | Window value used to build and classify the event matches. |

Use the `Type` and scorer-specific timestamp columns first to identify a missed,
extra, or mistimed event. The delta, overlap, and IoU columns then quantify the
size of a timing discrepancy. The review CSV is a quality-control aid; it does
not replace the per-behaviour kappa, alpha, and raw-agreement table exported
from Detailed mode with **Export results...**.

### 7.4 Interpreting Reliability Values

Colour bands are screening aids, not field-independent rules. Cicchetti-style
ICC bands and Landis-Koch-style kappa bands are widely used, but acceptable
values depend on behaviour density, event duration, and the purpose of the
scoring.

For publication, report the bin width, behaviours analysed, sample size, and
whether values came from Summary or Detailed mode.

---

## 8. Project Mode

A RABET project groups related files:

- videos
- annotation CSVs
- action maps
- analysis outputs

Create a project with **New Project**. Add files using **Add Video**,
**Add Annotation**, **Add Action Map**, or **Add Analysis**. For each file you
can copy it into the project directory or keep a reference to its current
location.

When you annotate a video from Project mode, RABET switches to Annotation,
loads the video, saves the annotation into the project, then returns to
Project mode after the recording ends.

Project manifests are saved automatically after changes.

### Project action maps

A project keeps its own action map so that one key means the same behaviour
for every video in it, no matter what the global map is changed to later.

When you create a project, RABET saves a copy of the action map you are using
at that moment into the project's `action_maps` folder and records it in
`project.json`. Opening the project loads that map; closing it restores your
global map. While the project is open, any edit you make to the map is saved
into the project, so your global map is never altered.

**Projects created before RABET 1.4.2** have no map of their own and keep using
the global action map, exactly as before. To give one its own map, open it and
choose `File > Use Current Action Map for This Project`. RABET does not do this
automatically: it cannot know whether the map loaded right now is the one those
videos were originally scored with, so the decision is left to you. Once bound,
the project behaves like any newly created one.

#### When the map changes on opening a project

If opening a project changes what any key means, RABET shows the differences
before you can record. This happens when you switch between projects that use
different schemes, and also when you move from a project with its own map to
one without. Nothing is shown when the map is unchanged.

Check the Action Map panel heading if you are unsure which scheme is active.

---

## 9. Configuration and Files

### 9.1 User Settings

RABET persists:

- window size and position
- last active tab
- recording duration
- playback step size and rate
- interval-analysis settings
- preserve-on-rewind setting
- recent files
- last-used file-dialog folders

### 9.2 Configuration Files

Typical files under the RABET user data folder:

- `configs/default_action_map.json`
- `configs/user_action_map.json` — the global action map. A project with its
  own map stores it in the project instead (see
  [Project action maps](#project-action-maps)).
- `configs/default_metrics.json`
- `configs/custom_color_map.json`
- `logs/rabet_<date>.log`

Configuration and project files are read as UTF-8, with or without a byte
order mark, so a hand-edited file keeps non-ASCII behaviour labels intact.

### 9.3 CSV Files

RABET writes:

- Annotation CSVs from the Annotation tab.
- `summary_table.csv` from the Analysis tab.
- `summary_intervals.csv` when interval analysis is enabled.
- Bout-analysis CSVs from the Bout Analysis dialog.
- Transition-analysis tidy CSVs from the Transition Analysis dialog.
- Reliability result CSVs from the Reliability tab.

See [CSV_FORMAT.md](CSV_FORMAT.md) for the annotation, summary, and interval
summary schemas.

---

## 10. Troubleshooting

### A Video Does Not Open

RABET accepts common video extensions, known video file signatures, and files
that PyAV can open. If a file still fails, convert or remux it with FFmpeg:

```bash
ffmpeg -i input.unknown -c copy output.mp4
```

### macOS Says the App Is Damaged

For unsigned DMG builds, remove quarantine:

```bash
xattr -dr com.apple.quarantine /Applications/RABET.app
```

### Reliability Values Are Blank

Blank ICC, Pearson, kappa, or alpha values can be legitimate when the statistic
is undefined. For example, correlation is undefined for constant paired
values, and kappa is undefined when both raters are all-zero for a behaviour.

If you run from source and imports fail, install the scientific dependencies
from `pyproject.toml` or use the provided conda environment.

### Logs

Use `Log > View Logs` to open the log folder. `Log > Clean Up Logs` removes
old logs.

When reporting a bug, include the log file and the RABET version shown in
`Help > About`.

---

## 11. Citation and Support

Issues: <https://github.com/mi2e-K/RABET/issues>

If RABET supports your research, please cite:

> Mitsui, K. (2026). *RABET - Real-time Animal Behavior Event Tagger*
> (Version 1.4.2) [Computer software].
> https://github.com/mi2e-K/RABET
> doi:[10.5281/zenodo.15313025](https://doi.org/10.5281/zenodo.15313025)

The DOI is the Zenodo concept DOI. When reproducibility matters, report the
exact RABET version used.
