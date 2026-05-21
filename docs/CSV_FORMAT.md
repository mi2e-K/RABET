# RABET CSV File Format Specification

This document describes the layout of the CSV files RABET reads and writes.
Three distinct files are involved:

1. **Annotation CSV** 窶・one file per video / per recording session, produced
   by the annotation view (Export Annotations / Auto-Save) and consumed by
   both the annotation view (Import Annotations) and the analysis view.
2. **Summary CSV** 窶・one row per animal / file, produced by the analysis
   view when interval analysis is **disabled**.
3. **Interval Summary CSV** 窶・one row per (animal, interval) pair, produced
   when interval analysis is **enabled**.

All files use the UTF-8 encoding, a comma (`,`) field separator and `\n`
line endings written through Python's standard `csv` module.

---

## 1. Schema versions at a glance

| Schema | Introduced in | Distinguishing feature |
| --- | --- | --- |
| `v0` | RABET 竕､ 1.1.4 | No provenance / schema rows; metadata section contains only `Test Duration (seconds)`. |
| `v1` | RABET 1.2.0+ | Adds explicit `RABET Version` and `Format Schema` rows to every export. |

RABET 1.2.0+ writes the **`v1`** schema. It still reads `v0` files for
back-compatibility; only a debug-level log line is emitted to indicate the
absence of a schema marker. Future schema versions (`v2`, ...) will keep
this contract: a missing/unknown `Format Schema` row triggers a warning
but never blocks the import.

---

## 2. Annotation CSV (`v1`)

The annotation CSV is divided into three sections separated by blank lines.

### 2.1 Layout

```
Metadata
RABET Version,<X.Y.Z>
Format Schema,v1
Test Duration (seconds),<float>

Event,Onset,Offset
RecordingStart,<float>,<float>
<behavior>,<float>,<float>
...

Behavior,Duration,Frequency
<behavior>,<float>,<int>
...
```

### 2.2 Section reference

#### Metadata

| Row | Type | Notes |
| --- | --- | --- |
| `Metadata` (literal) | string | Section marker. Always present. |
| `RABET Version,<X.Y.Z>` | string | Version of the producing application. Omitted in `v0`. |
| `Format Schema,v1` | string | Schema identifier. Omitted in `v0`. |
| `Test Duration (seconds),<float>` | float | Length of the timed-recording session in seconds. `0` if no timed recording was performed. |

#### Event log

| Column | Type | Notes |
| --- | --- | --- |
| `Event` | string | Behavior label as configured in the action map, or the literal `RecordingStart` for the synthetic recording marker. |
| `Onset` | float (s) | Onset time in seconds from the start of the video, four decimal places. |
| `Offset` | float (s) | Offset time in seconds. Empty for active events that were never released (rare in exports). |

Events appear in the order they were finalised. The synthetic
`RecordingStart` row, if any, is emitted with identical `Onset` and
`Offset` values. Onset and Offset are stored internally in milliseconds
and converted to seconds at export time.

#### Summary

| Column | Type | Notes |
| --- | --- | --- |
| `Behavior` | string | Behavior label (also appears in the Event section, but here even with zero occurrences). |
| `Duration` | float (s) | Sum of `offset 竏・onset` over all instances. |
| `Frequency` | int | Number of times this behavior was tagged (counted by onset). |

`RecordingStart` is omitted from this section.

### 2.3 Example

```csv
Metadata
RABET Version,1.2.2
Format Schema,v1
Test Duration (seconds),60

Event,Onset,Offset
RecordingStart,0.0000,0.0000
Attack bites,1.0000,1.5000
Sideways threats,2.0000,2.2000
Attack bites,3.0000,3.4000

Behavior,Duration,Frequency
Attack bites,0.90,2
Sideways threats,0.20,1
Tail rattles,0.00,0
Chasing,0.00,0
Social contact,0.00,0
Self-grooming,0.00,0
Locomotion,0.00,0
Rearing,0.00,0
```

### 2.4 Importing older (`v0`) files

`v0` files lack the `RABET Version` and `Format Schema` rows. RABET 1.2.0+
still imports them correctly; only a debug message is logged. No content
adjustments are required.

---

## 3. Summary CSV (whole-session, `v1`)

Produced as the whole-session summary. When `Enable interval analysis` is
on, RABET exports this file alongside the interval summary.
One header band + one row per loaded animal / file.

### 3.1 Layout

```
,<Duration band: behaviors...>,<spacer>,<Frequency band: behaviors...>,<spacer>,<custom metric names...>
animal_id,<behavior cols>,<empty>,<behavior cols>,<empty>,<custom metric values>
...
```

### 3.2 Notes

- The Duration band and Frequency band each list the *same* ordered set
  of behaviors. Empty spacer columns make the table easier to read in
  spreadsheets.
- Custom metric columns at the end follow the order configured in the
  Metrics dialog. They include both **latency** metrics (one behavior
  each) and **total-time** metrics (a set of behaviors collapsed into a
  single overlap-aware duration).

### 3.3 `animal_id` derivation

The `animal_id` is the basename of the source annotation CSV minus a
trailing `_annotations` suffix, if any. Example:
`mouse_05_annotations.csv` 竊・`mouse_05`.

---

## 4. Interval Summary CSV (`v1`)

Produced when `Enable interval analysis` is **on**. The header reports the
interval size in seconds.

### 4.1 Layout

```
Interval analysis (<N>-second intervals)
<...,Duration band,<spacer>,Frequency,...>
animal_id,Interval,Time (sec),<spacer>,<behaviors duration>,<spacer>,<behaviors freq>,<spacer>,<custom metrics>
...rows: one per (animal, interval) pair...
```

### 4.2 Important semantics

- **Duration** is the number of seconds each behaviour overlaps the interval.
- **Frequency** is the number of events whose onset falls inside the interval.
- **`Time (sec)`** 窶・string like `0.0-60.0`, the closed-open interval
  boundary in seconds from the recording start.
- **Empty intervals** still produce a row (all metric columns zero).
- Animals are separated by a blank row.

### 4.3 Example header

```csv
Interval analysis (60-second intervals)
,,,,Duration,,,,,,,,Frequency,,,,,,,,
animal_id,Interval,Time (sec),,Attack bites,Sideways threats,...,,Attack bites,Sideways threats,...,,Total Aggression
```

---

## 5. Reading RABET CSVs from external tools

### 5.1 Pandas

```python
import pandas as pd

# Annotation CSV: read just the Event section.
def load_rabet_events(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Event,Onset,Offset"))
    # Stop at the blank line or the Behavior section.
    end = next(
        (i for i in range(start + 1, len(lines))
         if not lines[i].strip() or lines[i].startswith("Behavior,")),
        len(lines),
    )
    return pd.read_csv(pd.io.common.StringIO("".join(lines[start:end])))
```

The same parsing helper used internally is available via
`utils.annotation_csv_parser.extract_event_dataframe`.

### 5.2 Schema detection

Read the first 10 lines and search for `RABET Version,` and
`Format Schema,`. Absent rows imply schema `v0`.

---

## 6. Version compatibility matrix

| Producer | Consumer | Status |
| --- | --- | --- |
| RABET 竕､ 1.1.4 (`v0`) | RABET 1.2.x | 笨・Reads cleanly (logs a debug note about missing schema). |
| RABET 1.2.x (`v1`) | RABET 1.2.x | 笨・Full round-trip preserved. |
| RABET 1.2.x (`v1`) | RABET 竕､ 1.1.4 | 笞・・Annotation CSV metadata rows live in the Metadata section, which older readers safely ignore. Summary CSVs are table-first in 1.2.2+. |
| RABET 竕･ 2.0 (hypothetical `v2`) | RABET 1.2.x | 笞・・Loads with a warning; behavior depends on whether `v2` is a strict extension. Always check the changelog. |

---

## 7. Reference fixtures

The repository ships small reference fixtures under `tests/fixtures/`:

- `sample_v1_0_annotation.csv` 窶・pre-1.2.0 annotation file.
- `sample_v1_2_annotation.csv` 窶・1.2.0+ annotation file.

These files are exercised by `tests/test_csv_compat.py`. Use them as a
starting point when validating your own parser against RABET output.
