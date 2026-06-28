# models/sequence_analysis.py - Pure, Qt-free first-order transition analysis.
#
# Behaviour-agnostic engine for lag-1 transition (sequential) analysis. It is
# deliberately general — no behaviour names or research paradigm are baked in —
# so domain analyses (e.g. "what precedes attacks") are just a selection on the
# general matrix. See docs/dev/SPEC-transition-analysis.md.
#
# Key methodological choices (grounded in Bakeman & Quera 2011):
#   * The headline statistic is the **adjusted residual** (a chance-corrected
#     z-score), not the raw transitional probability, because raw probabilities
#     are confounded by each behaviour's base rate.
#   * Self-transitions (A->A) are REAL in raw-event mode (RABET allows repeated
#     discrete events, e.g. an attack burst). In bout-collapsed mode — or when
#     ``exclude_self`` is set — the diagonal is a *structural zero* and expected
#     counts are fitted by iterative proportional fitting (IPF).
#   * A time ``window`` restricts a transition to consecutive events whose gap
#     (next.onset - prev.offset) is within the window, so a behaviour long ago
#     is not counted as "preceding" the next one.
#
# This module is dependency-light (stdlib + numpy) and Qt-free for easy unit
# testing, mirroring models.bout_analysis and reliability_model's pure helpers.

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

BehaviorEvent = Tuple[str, float, float]  # (behavior, onset, offset)

RECORDING_START = "RecordingStart"


@dataclass
class TransitionResult:
    """First-order transition table and chance-corrected statistics."""

    behaviors: List[str]
    counts: np.ndarray             # O[i, j]: antecedent i -> consequent j
    cond_prob: np.ndarray          # P(j | i) = O[i, j] / row_i (NaN if row_i==0)
    expected: np.ndarray           # E[i, j] under independence (IPF if structural zeros)
    adjusted_residual: np.ndarray  # z[i, j] (NaN where undefined / structural zero)
    odds_ratio: np.ndarray         # OR[i, j]: antecedent=i vs not, consequent=j vs not
    n_transitions: int
    mode: str                      # "raw_events" | "bout_collapsed"
    window: Optional[float]
    bout_bci: Optional[float]      # if set, events were collapsed to bouts first
    exclude_self: bool             # True when the diagonal is a structural zero
    low_count: np.ndarray          # bool: antecedent base < 30 (z unstable)


def clean_events(
    events: Sequence[BehaviorEvent],
    exclude_recording_start: bool = True,
) -> List[BehaviorEvent]:
    """Coerce, filter and sort raw ``(behavior, onset, offset)`` tuples."""
    cleaned: List[BehaviorEvent] = []
    for item in events:
        try:
            behavior, onset, offset = item
        except (TypeError, ValueError):
            continue
        behavior = str(behavior).strip()
        if not behavior:
            continue
        if exclude_recording_start and behavior == RECORDING_START:
            continue
        try:
            onset = float(onset)
            offset = float(offset)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(onset) and math.isfinite(offset)):
            continue
        if offset < onset:
            onset, offset = offset, onset
        cleaned.append((behavior, onset, offset))
    cleaned.sort(key=lambda event: (event[1], event[2]))
    return cleaned


def collapse_repeats(events: Sequence[BehaviorEvent]) -> List[BehaviorEvent]:
    """Merge consecutive same-behaviour events into one token.

    The merged token spans the first onset to the max offset. This removes
    self-transitions by construction (used by ``bout_collapsed`` mode).
    """
    out: List[BehaviorEvent] = []
    for behavior, onset, offset in events:
        if out and out[-1][0] == behavior:
            prev_behavior, prev_onset, prev_offset = out[-1]
            out[-1] = (prev_behavior, prev_onset, max(prev_offset, offset))
        else:
            out.append((behavior, onset, offset))
    return out


def collapse_to_bouts(events: Sequence[BehaviorEvent], bci: float) -> List[BehaviorEvent]:
    """Collapse each behaviour's events into bouts by a gap criterion (BCI).

    For every behaviour separately, consecutive events whose gap
    (next.onset - running max offset) is <= ``bci`` are merged into one token
    spanning (first onset, max offset). Behaviour-agnostic generalisation of the
    "attack burst = one token" transform: lets transition analysis run at the
    *episode* level instead of the per-event level (1.4.0).
    """
    by_behavior: Dict[str, List[BehaviorEvent]] = {}
    for behavior, onset, offset in clean_events(events, exclude_recording_start=False):
        by_behavior.setdefault(behavior, []).append((behavior, onset, offset))

    out: List[BehaviorEvent] = []
    for behavior, evs in by_behavior.items():
        cur_start, cur_end = evs[0][1], evs[0][2]
        for _b, onset, offset in evs[1:]:
            if onset - cur_end <= bci:
                cur_end = max(cur_end, offset)
            else:
                out.append((behavior, cur_start, cur_end))
                cur_start, cur_end = onset, offset
        out.append((behavior, cur_start, cur_end))
    out.sort(key=lambda event: (event[1], event[2]))
    return out


def build_sequence(
    events: Sequence[BehaviorEvent],
    mode: str = "raw_events",
    exclude_recording_start: bool = True,
    bout_bci: Optional[float] = None,
) -> List[BehaviorEvent]:
    """Return the token sequence for a given mode.

    When ``bout_bci`` is set, events are first collapsed to per-behaviour bouts
    (episode level); ``mode`` then applies on top.
    """
    cleaned = clean_events(events, exclude_recording_start)
    if bout_bci is not None:
        cleaned = collapse_to_bouts(cleaned, bout_bci)
    if mode == "bout_collapsed":
        return collapse_repeats(cleaned)
    return cleaned


def _ipf(observed: np.ndarray, structural_zero: np.ndarray,
         iters: int = 2000, tol: float = 1e-10) -> np.ndarray:
    """Iterative proportional fitting matching the observed row/col marginals
    with the masked cells held at zero (structural zeros)."""
    row_targets = observed.sum(axis=1)
    col_targets = observed.sum(axis=0)
    expected = np.ones_like(observed, dtype=float)
    expected[structural_zero] = 0.0
    for _ in range(iters):
        rs = expected.sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            rf = np.where(rs > 0, row_targets / rs, 0.0)
        expected = expected * rf[:, None]
        cs = expected.sum(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            cf = np.where(cs > 0, col_targets / cs, 0.0)
        expected = expected * cf[None, :]
        if (np.max(np.abs(expected.sum(axis=1) - row_targets)) < tol
                and np.max(np.abs(expected.sum(axis=0) - col_targets)) < tol):
            break
    return expected


def _count_transitions(seq, index, k, window, structural_self):
    """Count lag-1 transitions in one token sequence into a k×k matrix."""
    counts = np.zeros((k, k), dtype=float)
    n_transitions = 0
    for (b1, _on1, off1), (b2, on2, _off2) in zip(seq, seq[1:], strict=False):
        if b1 not in index or b2 not in index:
            continue
        if window is not None and (on2 - off1) > window:
            continue
        if structural_self and b1 == b2:
            continue
        counts[index[b1], index[b2]] += 1.0
        n_transitions += 1
    return counts, n_transitions


def _result_from_counts(counts, behaviors, *, mode, window, bout_bci,
                        structural_self, n_transitions):
    """Derive chance-corrected statistics from a (possibly pooled) count matrix."""
    behaviors = list(behaviors)
    k = len(behaviors)
    row = counts.sum(axis=1)
    col = counts.sum(axis=0)
    total = counts.sum()

    cond = np.full_like(counts, np.nan)
    has_row = row > 0
    cond[has_row] = counts[has_row] / row[has_row, None]

    structural_zero = np.zeros((k, k), dtype=bool)
    if structural_self:
        np.fill_diagonal(structural_zero, True)

    if total > 0:
        if structural_self and k > 1:
            expected = _ipf(counts, structural_zero)
        else:
            expected = np.outer(row, col) / total
    else:
        expected = np.zeros_like(counts)

    # Adjusted residuals (Bakeman & Quera). For the structural-zero case the
    # expected values come from IPF and this is a documented approximation.
    z = np.full_like(counts, np.nan)
    if total > 0:
        with np.errstate(divide="ignore", invalid="ignore"):
            denom = expected * (1.0 - row[:, None] / total) * (1.0 - col[None, :] / total)
            valid = (expected > 0) & (denom > 0) & (~structural_zero)
            z[valid] = (counts[valid] - expected[valid]) / np.sqrt(denom[valid])

    # Per-cell odds ratio: antecedent=i vs not, consequent=j vs not (2x2).
    # Base-rate-robust, so it stays interpretable across conditions/levels.
    odds = np.full_like(counts, np.nan)
    if total > 0:
        for i in range(k):
            for j in range(k):
                if structural_zero[i, j]:
                    continue
                a = counts[i, j]
                b = row[i] - a
                c = col[j] - a
                d = total - a - b - c
                if b * c > 0:
                    odds[i, j] = (a * d) / (b * c)
                elif a > 0:
                    odds[i, j] = math.inf

    low_count = np.zeros((k, k), dtype=bool)
    low_count[row < 30, :] = True  # small antecedent base -> unstable z

    return TransitionResult(
        behaviors=behaviors,
        counts=counts,
        cond_prob=cond,
        expected=expected,
        adjusted_residual=z,
        odds_ratio=odds,
        n_transitions=n_transitions,
        mode=mode,
        window=window,
        bout_bci=bout_bci,
        exclude_self=structural_self,
        low_count=low_count,
    )


def compute_transitions(
    events: Sequence[BehaviorEvent],
    behaviors: Optional[Sequence[str]] = None,
    *,
    mode: str = "raw_events",
    window: Optional[float] = None,
    exclude_self: bool = False,
    exclude_recording_start: bool = True,
    bout_bci: Optional[float] = None,
) -> TransitionResult:
    """Compute the lag-1 transition table and chance-corrected statistics.

    Args:
        events: ``(behavior, onset, offset)`` tuples (any order; sorted here).
        behaviors: behaviour set / ordering for the matrix. Derived (sorted)
            from the data when omitted.
        mode: ``"raw_events"`` (self-transitions kept) or ``"bout_collapsed"``
            (consecutive repeats merged; diagonal becomes a structural zero).
        window: max gap in seconds between consecutive events for a transition
            to count (``None`` = no limit).
        exclude_self: force the diagonal to be a structural zero even in raw
            mode.
        exclude_recording_start: drop the synthetic RecordingStart marker.
    """
    seq = build_sequence(events, mode, exclude_recording_start, bout_bci=bout_bci)
    if behaviors is None:
        behaviors = sorted({behavior for behavior, _, _ in seq})
    behaviors = list(behaviors)
    index: Dict[str, int] = {behavior: i for i, behavior in enumerate(behaviors)}
    k = len(behaviors)
    structural_self = exclude_self or (mode == "bout_collapsed")
    counts, n_transitions = _count_transitions(seq, index, k, window, structural_self)
    return _result_from_counts(
        counts, behaviors, mode=mode, window=window, bout_bci=bout_bci,
        structural_self=structural_self, n_transitions=n_transitions)


def pool_transitions(
    per_animal_events: Sequence[Sequence[BehaviorEvent]],
    behaviors: Optional[Sequence[str]] = None,
    *,
    mode: str = "raw_events",
    window: Optional[float] = None,
    exclude_self: bool = False,
    exclude_recording_start: bool = True,
    bout_bci: Optional[float] = None,
) -> TransitionResult:
    """Pool lag-1 transitions ACROSS animals at the count level.

    Each animal's events are sequenced and counted separately (so no spurious
    transition is created at the boundary between animals); the per-animal count
    matrices are then summed and the chance-corrected statistics computed on the
    pooled counts. A descriptive overview that ignores between-animal
    heterogeneity (animals are weighted by their transition counts).
    """
    sequences = [
        build_sequence(events, mode, exclude_recording_start, bout_bci=bout_bci)
        for events in per_animal_events
    ]
    if behaviors is None:
        behaviors = sorted({b for seq in sequences for b, _, _ in seq})
    behaviors = list(behaviors)
    index: Dict[str, int] = {behavior: i for i, behavior in enumerate(behaviors)}
    k = len(behaviors)
    structural_self = exclude_self or (mode == "bout_collapsed")
    counts = np.zeros((k, k), dtype=float)
    n_transitions = 0
    for seq in sequences:
        seq_counts, seq_n = _count_transitions(seq, index, k, window, structural_self)
        counts += seq_counts
        n_transitions += seq_n
    return _result_from_counts(
        counts, behaviors, mode=mode, window=window, bout_bci=bout_bci,
        structural_self=structural_self, n_transitions=n_transitions)


def tidy_rows(result: TransitionResult, animal_id: str = "") -> List[dict]:
    """Flatten a result into tidy long-format rows (one per antecedent/consequent)."""
    rows: List[dict] = []
    for i, antecedent in enumerate(result.behaviors):
        for j, consequent in enumerate(result.behaviors):
            if result.exclude_self and i == j:
                continue
            rows.append({
                "animal_id": animal_id,
                "antecedent": antecedent,
                "consequent": consequent,
                "n": int(result.counts[i, j]),
                "p_cond": result.cond_prob[i, j],
                "expected": result.expected[i, j],
                "adj_residual": result.adjusted_residual[i, j],
                "odds_ratio": result.odds_ratio[i, j],
                "flag": "low-n" if result.low_count[i, j] else "",
                "level": "bout" if result.bout_bci is not None else "event",
                "bci_s": "" if result.bout_bci is None else result.bout_bci,
                "mode": result.mode,
                "window_s": "" if result.window is None else result.window,
            })
    return rows


def _adj_resid_2x2(observed: np.ndarray) -> float:
    """Adjusted residual for the [0,0] cell of a 2x2 contingency table."""
    row, col, total = observed.sum(1), observed.sum(0), observed.sum()
    if total == 0:
        return float("nan")
    expected = np.outer(row, col) / total
    denom = expected * (1.0 - row[:, None] / total) * (1.0 - col[None, :] / total)
    if expected[0, 0] <= 0 or denom[0, 0] <= 0:
        return float("nan")
    return float((observed[0, 0] - expected[0, 0]) / math.sqrt(denom[0, 0]))


def antecedent_window_metric(
    events: Sequence[BehaviorEvent],
    target: str,
    antecedents: Sequence[str],
    window: float,
    *,
    target_level: str = "event",
    bci: float = 1.0,
    n_perm: int = 0,
    seed: int = 0,
    session_duration: Optional[float] = None,
    exclude_recording_start: bool = True,
) -> dict:
    """Fraction of ``target`` occurrences preceded within ``window`` by any
    antecedent — the behaviour-agnostic "predictability / announced fraction".

    Args:
        target_level: ``"event"`` (each target event) or ``"bout"`` (each target
            bout, merged by ``bci``) — the episode-level view.
        n_perm: if > 0, also compute a chance baseline by circularly shifting
            the antecedent onset times ``n_perm`` times (controls for how common
            the antecedents are); ``above_chance = observed - chance_mean``.
        session_duration: needed for the circular shift; inferred from the max
            offset when omitted.

    Returns a dict with observed, n_targets, n_antecedents, chance_mean,
    above_chance (last two NaN when ``n_perm == 0``).
    """
    cleaned = clean_events(events, exclude_recording_start)
    antecedent_set = set(antecedents)

    if target_level == "bout":
        target_starts = [
            on for b, on, _ in collapse_to_bouts(
                [e for e in cleaned if e[0] == target], bci
            )
        ]
    else:
        target_starts = [on for b, on, _ in cleaned if b == target]
    ant_onsets = [on for b, on, _ in cleaned if b in antecedent_set]

    result = {
        "observed": float("nan"), "n_targets": len(target_starts),
        "n_antecedents": len(ant_onsets), "chance_mean": float("nan"),
        "above_chance": float("nan"),
    }
    if not target_starts:
        return result

    def fraction(onsets):
        oset = sorted(onsets)
        hit = 0
        for start in target_starts:
            lo = start - window
            if any(lo <= t < start for t in oset):
                hit += 1
        return hit / len(target_starts)

    result["observed"] = fraction(ant_onsets)

    if n_perm > 0 and ant_onsets:
        duration = session_duration
        if duration is None:
            duration = max((off for _, _, off in cleaned), default=0.0)
        if duration and duration > 0:
            rng = np.random.default_rng(seed)
            null = []
            for _ in range(n_perm):
                shift = rng.uniform(0, duration)
                shifted = [(t + shift) % duration for t in ant_onsets]
                null.append(fraction(shifted))
            result["chance_mean"] = float(np.mean(null))
            result["above_chance"] = result["observed"] - result["chance_mean"]
    return result


def lag_profile(
    events: Sequence[BehaviorEvent],
    antecedents: Sequence[str],
    target: str,
    lags: Sequence[int] = (1, 2, 3, 4, 5),
    *,
    bout_bci: Optional[float] = None,
    exclude_recording_start: bool = True,
) -> List[float]:
    """Adjusted residual z for [antecedent-set -> target] at each lag.

    Built on the token sequence (optionally bout-collapsed). At lag k the 2x2
    table is (token[i] in antecedent-set vs not) x (token[i+k] == target vs not).
    Returns one z per lag (NaN where undefined).
    """
    seq = build_sequence(events, "raw_events", exclude_recording_start, bout_bci=bout_bci)
    labels = [b for b, _, _ in seq]
    antecedent_set = set(antecedents)
    out: List[float] = []
    for lag in lags:
        observed = np.zeros((2, 2))
        for i in range(len(labels) - lag):
            a = 0 if labels[i] in antecedent_set else 1
            c = 0 if labels[i + lag] == target else 1
            observed[a, c] += 1
        out.append(_adj_resid_2x2(observed))
    return out


def pooled_lag_profile(
    events_list: Sequence[Sequence[BehaviorEvent]],
    antecedents: Sequence[str],
    target: str,
    lags: Sequence[int] = (1, 2, 3, 4, 5),
    *,
    bout_bci: Optional[float] = None,
    exclude_recording_start: bool = True,
) -> List[float]:
    """Lag profile z pooled across several sessions (2x2 tables summed per lag)."""
    antecedent_set = set(antecedents)
    seqs = [
        [b for b, _, _ in build_sequence(ev, "raw_events", exclude_recording_start, bout_bci=bout_bci)]
        for ev in events_list
    ]
    out: List[float] = []
    for lag in lags:
        observed = np.zeros((2, 2))
        for labels in seqs:
            for i in range(len(labels) - lag):
                a = 0 if labels[i] in antecedent_set else 1
                c = 0 if labels[i + lag] == target else 1
                observed[a, c] += 1
        out.append(_adj_resid_2x2(observed))
    return out
