"""generate_reliability_qa_data.py - Build synthetic QA fixtures for the
Reliability tab.

This script writes summary_table.csv and annotation CSV pairs into the
target directory in the same on-disk schema RABET produces. The output
exercises every UI path in the Reliability tab:

  - Summary mode with realistic ICC bands (green / amber / red)
  - Detailed mode with mild moment-to-moment disagreement
  - Unmatched animal_id ("only in scorer A" / "only in scorer B")
  - Duplicate animal_id (warning log path)
  - Perfect agreement (degenerate-but-OK case)

Run with default parameters from the repository root:

    python tools/generate_reliability_qa_data.py

Optionally:

    python tools/generate_reliability_qa_data.py \\
        --out tests/fixtures/reliability_qa \\
        --seed 42 \\
        --n-animals 12 \\
        --duration 300
"""

from __future__ import annotations

import argparse
import os
import random
from pathlib import Path
from typing import List, Tuple


# Behaviours present in the standard RABET aggression ethogram. Order
# matches the default Action Map so the generated summary CSV looks
# identical to a real Analysis-view export.
BEHAVIOURS: Tuple[str, ...] = (
    "Attack bites",
    "Sideways threats",
    "Tail rattles",
    "Chasing",
    "Social contact",
    "Self-grooming",
    "Locomotion",
    "Rearing",
    "hard bites",
)

# Custom-metric columns (latency + total aggression variants).
CUSTOM_METRICS: Tuple[str, ...] = (
    "Attack Latency",
    "Total Aggression",
    "Total Aggression(without tail-rattles)",
)

# Per-behaviour generation parameters for the reference scorer (A):
#   - mean_freq, std_freq: per-animal event count
#   - mean_dur_per_event, std_dur_per_event: per-event seconds (clipped at 0.05)
#   - noise_sigma: relative noise injected into scorer B (multiplicative).
#     Larger noise -> lower ICC -> the metric ends up in a different colour
#     band in the UI.
BEHAVIOUR_PARAMS = {
    # Excellent agreement (green band, ICC >= 0.75).
    "Attack bites":      dict(mean_freq=8.0,  std_freq=3.0, dur_mean=0.30, dur_std=0.10, noise_sigma=0.07),
    "Social contact":    dict(mean_freq=24.0, std_freq=6.0, dur_mean=0.70, dur_std=0.20, noise_sigma=0.08),
    "Locomotion":        dict(mean_freq=55.0, std_freq=15.0, dur_mean=0.80, dur_std=0.25, noise_sigma=0.10),
    "Rearing":           dict(mean_freq=22.0, std_freq=8.0, dur_mean=2.00, dur_std=0.80, noise_sigma=0.10),
    "Chasing":           dict(mean_freq=2.5,  std_freq=1.5, dur_mean=1.50, dur_std=0.40, noise_sigma=0.10),
    # Moderate agreement (amber band, 0.50 <= ICC < 0.75). Calibrated
    # against n=12 - small samples need a fairly aggressive noise_sigma
    # to land in the amber band reliably.
    "Sideways threats":  dict(mean_freq=5.0,  std_freq=2.5, dur_mean=0.80, dur_std=0.25, noise_sigma=0.65),
    "Self-grooming":     dict(mean_freq=9.0,  std_freq=4.0, dur_mean=2.40, dur_std=1.00, noise_sigma=0.55),
    # Poor agreement (red band, ICC < 0.50) - simulating a behaviour
    # where scorers disagree on what counts as a tail rattle.
    "Tail rattles":      dict(mean_freq=11.0, std_freq=5.0, dur_mean=0.20, dur_std=0.08, noise_sigma=0.90),
    # Hard bites: scorers agree on "no event" for every animal.
    "hard bites":        dict(mean_freq=0.0,  std_freq=0.0, dur_mean=0.0,  dur_std=0.0,  noise_sigma=0.0),
}


def _truncated_normal(rng: random.Random, mean: float, std: float, low: float = 0.0) -> float:
    """Gaussian draw clamped to ``>= low``."""
    if std <= 0:
        return max(low, mean)
    value = rng.gauss(mean, std)
    return max(low, value)


def _generate_animal_a(rng: random.Random) -> dict:
    """One row of scorer A's summary: per-behaviour frequency and
    duration, plus custom metric values."""
    record = {"frequency": {}, "duration": {}}
    total_aggressive_duration = 0.0
    total_aggressive_dur_no_tail = 0.0
    aggressive_set = {"Attack bites", "Sideways threats", "Tail rattles", "Chasing"}

    for behaviour, params in BEHAVIOUR_PARAMS.items():
        freq = int(round(_truncated_normal(
            rng, params["mean_freq"], params["std_freq"], low=0.0
        )))
        if params["dur_mean"] <= 0:
            duration = 0.0
        else:
            total = 0.0
            for _ in range(freq):
                total += _truncated_normal(
                    rng, params["dur_mean"], params["dur_std"], low=0.05
                )
            duration = total
        record["frequency"][behaviour] = freq
        record["duration"][behaviour] = duration
        if behaviour in aggressive_set:
            total_aggressive_duration += duration
            if behaviour != "Tail rattles":
                total_aggressive_dur_no_tail += duration

    # Attack Latency: seconds until the first attack bite (synthetic).
    # We sample from a heavy-tailed distribution so values span 1-200 s.
    if record["frequency"]["Attack bites"] > 0:
        record["custom"] = {
            "Attack Latency": round(rng.uniform(1.5, 180.0), 2),
            "Total Aggression": round(total_aggressive_duration, 2),
            "Total Aggression(without tail-rattles)": round(total_aggressive_dur_no_tail, 2),
        }
    else:
        # No attack -> latency reported as the session duration (300 s).
        record["custom"] = {
            "Attack Latency": 300.0,
            "Total Aggression": round(total_aggressive_duration, 2),
            "Total Aggression(without tail-rattles)": round(total_aggressive_dur_no_tail, 2),
        }

    return record


def _perturb_to_b(rng: random.Random, record_a: dict) -> dict:
    """Generate scorer B's record from scorer A by multiplicative noise."""
    record_b = {"frequency": {}, "duration": {}, "custom": {}}
    total_aggressive_duration = 0.0
    total_aggressive_dur_no_tail = 0.0
    aggressive_set = {"Attack bites", "Sideways threats", "Tail rattles", "Chasing"}

    for behaviour, params in BEHAVIOUR_PARAMS.items():
        sigma = params["noise_sigma"]
        freq_a = record_a["frequency"][behaviour]
        dur_a = record_a["duration"][behaviour]

        if sigma <= 0:
            freq_b = freq_a
            dur_b = dur_a
        else:
            freq_b = int(round(max(0, freq_a * (1.0 + rng.gauss(0.0, sigma)) + rng.gauss(0.0, 1.0))))
            dur_b = max(0.0, dur_a * (1.0 + rng.gauss(0.0, sigma)) + rng.gauss(0.0, 0.3))

        record_b["frequency"][behaviour] = freq_b
        record_b["duration"][behaviour] = dur_b
        if behaviour in aggressive_set:
            total_aggressive_duration += dur_b
            if behaviour != "Tail rattles":
                total_aggressive_dur_no_tail += dur_b

    # Custom metrics: small noise on the reference latency, recompute
    # totals so the columns stay internally consistent.
    record_b["custom"]["Attack Latency"] = round(
        max(0.0, record_a["custom"]["Attack Latency"] + rng.gauss(0.0, 5.0)), 2
    )
    record_b["custom"]["Total Aggression"] = round(total_aggressive_duration, 2)
    record_b["custom"]["Total Aggression(without tail-rattles)"] = round(
        total_aggressive_dur_no_tail, 2
    )
    return record_b


def _write_summary_csv(
    path: Path,
    animals: List[Tuple[str, dict]],
) -> None:
    """Write a summary_table.csv with RABET's banded layout."""
    # Band row: "Duration" at the start of the duration band,
    # "Frequency" at the start of the frequency band, custom columns
    # have no band marker.
    band_cells = [""]
    for _ in BEHAVIOURS:
        band_cells.append("")
    band_cells[1] = "Duration"
    # spacer after the duration band
    band_cells.append("")
    for _ in BEHAVIOURS:
        band_cells.append("")
    band_cells[2 + len(BEHAVIOURS)] = "Frequency"
    # spacer after the frequency band
    band_cells.append("")
    for _ in CUSTOM_METRICS:
        band_cells.append("")

    header_cells = ["animal_id"]
    header_cells.extend(BEHAVIOURS)
    header_cells.append("")  # spacer
    header_cells.extend(BEHAVIOURS)
    header_cells.append("")  # spacer
    header_cells.extend(CUSTOM_METRICS)

    lines: List[str] = []
    lines.append(",".join(band_cells))
    lines.append(",".join(header_cells))

    for animal_id, record in animals:
        row: List[str] = [animal_id]
        for behaviour in BEHAVIOURS:
            row.append(f"{record['duration'][behaviour]:.2f}")
        row.append("")
        for behaviour in BEHAVIOURS:
            row.append(f"{record['frequency'][behaviour]:d}")
        row.append("")
        for metric in CUSTOM_METRICS:
            row.append(f"{record['custom'][metric]:.2f}")
        lines.append(",".join(row))

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _generate_annotation_events(
    rng: random.Random,
    duration: float,
    base_rate_per_min: float = 12.0,
) -> List[Tuple[str, float, float]]:
    """Generate a moderately busy event sequence for one annotation CSV.

    Returns a list of (behavior, onset_seconds, offset_seconds).
    """
    # Behaviour-specific event characteristics for this synthetic video.
    plan = [
        ("Attack bites",      8, 0.20, 0.10),
        ("Sideways threats",  5, 0.80, 0.30),
        ("Tail rattles",      9, 0.15, 0.05),
        ("Chasing",           2, 1.50, 0.50),
        ("Social contact",   16, 0.80, 0.30),
        ("Self-grooming",     6, 2.40, 1.00),
        ("Locomotion",       30, 0.80, 0.30),
        ("Rearing",          14, 2.00, 0.80),
    ]
    events: List[Tuple[str, float, float]] = []
    for behaviour, count, mean_dur, std_dur in plan:
        for _ in range(count):
            onset = rng.uniform(0.0, max(0.0, duration - mean_dur - 0.1))
            dur = max(0.05, rng.gauss(mean_dur, std_dur))
            offset = min(duration - 0.01, onset + dur)
            if offset <= onset:
                offset = onset + 0.05
            events.append((behaviour, onset, offset))
    events.sort(key=lambda triple: triple[1])
    return events


def _perturb_events(
    rng: random.Random,
    events: List[Tuple[str, float, float]],
    drop_probability: float = 0.08,
    add_probability: float = 0.05,
    time_jitter_sd: float = 0.30,
) -> List[Tuple[str, float, float]]:
    """Perturb scorer A's events to simulate scorer B."""
    out: List[Tuple[str, float, float]] = []
    for behaviour, onset, offset in events:
        if rng.random() < drop_probability:
            continue
        jitter = rng.gauss(0.0, time_jitter_sd)
        dur = offset - onset
        new_onset = max(0.0, onset + jitter)
        new_offset = new_onset + max(0.05, dur + rng.gauss(0.0, 0.10))
        out.append((behaviour, new_onset, new_offset))

    if events:
        added = int(round(len(events) * add_probability))
        for _ in range(added):
            behaviour = rng.choice([e[0] for e in events])
            onset = rng.uniform(0.0, max(0.0, events[-1][2]))
            offset = onset + 0.30
            out.append((behaviour, onset, offset))
    out.sort(key=lambda triple: triple[1])
    return out


def _write_annotation_csv(
    path: Path,
    events: List[Tuple[str, float, float]],
    duration: float,
) -> None:
    """Write an annotation CSV in RABET's v1 schema."""
    lines: List[str] = [
        "Metadata",
        "RABET Version,1.3.2",
        "Format Schema,v1",
        f"Test Duration (seconds),{duration:g}",
        "",
        "Event,Onset,Offset",
        "RecordingStart,0.0000,0.0000",
    ]
    for behaviour, onset, offset in events:
        lines.append(f"{behaviour},{onset:.4f},{offset:.4f}")

    # Per-behaviour summary section.
    lines.append("")
    lines.append("Behavior,Duration,Frequency")
    by_behaviour: dict = {}
    for behaviour, onset, offset in events:
        d, f = by_behaviour.get(behaviour, (0.0, 0))
        by_behaviour[behaviour] = (d + max(0.0, offset - onset), f + 1)
    for behaviour in BEHAVIOURS:
        dur, freq = by_behaviour.get(behaviour, (0.0, 0))
        lines.append(f"{behaviour},{dur:.2f},{freq}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out", default="tests/fixtures/reliability_qa",
        help="Output directory (created if missing).",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducibility.",
    )
    parser.add_argument(
        "--n-animals", type=int, default=12,
        help="Number of synthetic animals in the summary pair.",
    )
    parser.add_argument(
        "--duration", type=float, default=300.0,
        help="Test duration in seconds (used for annotation fixtures).",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------- #
    # Summary-mode fixtures
    # ----------------------------------------------------------- #
    animals_a: List[Tuple[str, dict]] = []
    animals_b: List[Tuple[str, dict]] = []
    for i in range(args.n_animals):
        animal_id = f"qa_mouse_{i + 1:02d}"
        rec_a = _generate_animal_a(rng)
        rec_b = _perturb_to_b(rng, rec_a)
        animals_a.append((animal_id, rec_a))
        animals_b.append((animal_id, rec_b))

    _write_summary_csv(out_dir / "qa_summary_scorerA.csv", animals_a)
    _write_summary_csv(out_dir / "qa_summary_scorerB.csv", animals_b)
    print(f"Wrote {out_dir / 'qa_summary_scorerA.csv'}")
    print(f"Wrote {out_dir / 'qa_summary_scorerB.csv'}")

    # Partial scorer B: drop the last two animals to surface the
    # "Only in scorer A" warning in the UI.
    if args.n_animals >= 3:
        partial = animals_b[: args.n_animals - 2]
        _write_summary_csv(out_dir / "qa_summary_scorerB_partial.csv", partial)
        print(f"Wrote {out_dir / 'qa_summary_scorerB_partial.csv'} ({len(partial)} animals)")

    # Duplicate animal_id case.
    if args.n_animals >= 2:
        dup = animals_a + [animals_a[0]]  # repeat animal 1
        # Mutate the duplicate row a little so the "keep last" rule is
        # observable in the data.
        dup_id, dup_record = dup[0]
        bumped = {
            "frequency": {k: v + 3 for k, v in dup_record["frequency"].items()},
            "duration": {k: v + 1.5 for k, v in dup_record["duration"].items()},
            "custom": dict(dup_record["custom"]),
        }
        dup[-1] = (dup_id, bumped)
        _write_summary_csv(out_dir / "qa_summary_duplicates.csv", dup)
        print(f"Wrote {out_dir / 'qa_summary_duplicates.csv'} (animal 1 listed twice)")

    # ----------------------------------------------------------- #
    # Detailed-mode fixtures
    # ----------------------------------------------------------- #
    events_a = _generate_annotation_events(rng, args.duration)
    events_b = _perturb_events(rng, events_a)
    _write_annotation_csv(out_dir / "qa_annotation_scorerA.csv", events_a, args.duration)
    _write_annotation_csv(out_dir / "qa_annotation_scorerB.csv", events_b, args.duration)
    _write_annotation_csv(out_dir / "qa_annotation_perfect.csv", events_a, args.duration)
    print(f"Wrote {out_dir / 'qa_annotation_scorerA.csv'} ({len(events_a)} events)")
    print(f"Wrote {out_dir / 'qa_annotation_scorerB.csv'} ({len(events_b)} events)")
    print(f"Wrote {out_dir / 'qa_annotation_perfect.csv'} (identical to scorer A)")

    print("\nDone. See", out_dir / "README.md", "for usage instructions.")


if __name__ == "__main__":
    main()
