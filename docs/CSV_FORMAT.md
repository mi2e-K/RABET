# RABET CSV File Format Specification

This document describes the layout of the CSV files RABET reads and writes.
Three distinct files are involved:

1. **Annotation CSV** — one file per video / per recording session, produced
   by the annotation view (Export Annotations / Auto-Save) and consumed by
   both the annotation view (Import Annotations) and the analysis view.
2. **Summary CSV** — one row per animal / file, produced by the analysis
   view when interval analysis is **disabled**.
3. **Interval Summary CSV** — one row per (animal, interval) pair, produced
   when interval analysis is **enabled**.

All files use the UTF-8 encoding, a comma (`,`) field separator and `\n`
line endings written through Python's standard `csv` module.

---

## 1. Annotation CSV

The annotation CSV is divided into three sections separated by blank lines.

### 1.1 Layout

```
Metadata
RABET Version,<X.Y.Z>
Test Duration (seconds),<float>

Event,Onset,Offset
RecordingStart,<float>,<float>
<behavior>,<float>,<float>
...

Behavior,Duration,Frequency
<behavior>,<float>,<int>
...
```

### 1.2 Section reference

#### Metadata

| Row | Type | Notes |
| --- | --- | --- |
| `Metadata` (literal) | string | Section marker. Always present. |
| `RABET Version,<X.Y.Z>` | string | Version of the producing application. |
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
| `Duration` | float (s) | Sum of `Offset − Onset` over all instances. |
| `Frequency` | int | Number of times this behavior was tagged (counted by onset). |

`RecordingStart` is omitted from this section.

### 1.3 Example

```csv
Metadata
RABET Version,1.3.5
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

---

## 2. Summary CSV (whole-session)

Produced as the whole-session summary. When `Enable interval analysis` is
on, RABET exports this file alongside the interval summary.
One header band + one row per loaded animal / file.

### 2.1 Layout

```
,<Duration band: behaviors...>,<spacer>,<Frequency band: behaviors...>,<spacer>,<custom metric names...>
animal_id,<behavior cols>,<empty>,<behavior cols>,<empty>,<custom metric values>
...
```

### 2.2 Notes

- The Duration band and Frequency band each list the *same* ordered set
  of behaviors. Empty spacer columns make the table easier to read in
  spreadsheets.
- Custom metric columns at the end follow the order configured in the
  Metrics dialog. They include both **latency** metrics (one behavior
  each) and **total-time** metrics (a set of behaviors collapsed into a
  single overlap-aware duration).

### 2.3 `animal_id` derivation

The `animal_id` is the basename of the source annotation CSV minus a
trailing `_annotations` suffix, if any. Example:
`mouse_05_annotations.csv` → `mouse_05`.

---

## 3. Interval Summary CSV

Produced when `Enable interval analysis` is **on**. The header reports the
interval size in seconds.

### 3.1 Layout

```
Interval analysis (<N>-second intervals)
<...,Duration band,<spacer>,Frequency,...>
animal_id,Interval,Time (sec),<spacer>,<behaviors duration>,<spacer>,<behaviors freq>,<spacer>,<custom metrics>
...rows: one per (animal, interval) pair...
```

### 3.2 Important semantics

- **Duration** is the number of seconds each behaviour overlaps the interval.
- **Frequency** is the number of events whose onset falls inside the interval.
- **`Time (sec)`** — string like `0.0-60.0`, the closed-open interval
  boundary in seconds from the recording start.
- **Empty intervals** still produce a row (all metric columns zero).
- Animals are separated by a blank row.

### 3.3 Example header

```csv
Interval analysis (60-second intervals)
,,,,Duration,,,,,,,,Frequency,,,,,,,,
animal_id,Interval,Time (sec),,Attack bites,Sideways threats,...,,Attack bites,Sideways threats,...,,Total Aggression
```
