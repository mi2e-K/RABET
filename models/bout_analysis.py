# models/bout_analysis.py - Pure, Qt-free bout (cluster) analysis.
#
# A "bout" is a run of same-behaviour events separated by gaps no larger than
# a bout-criterion interval (BCI). Events further apart than the BCI start a
# new bout. This is the standard ethological approach to collapsing rapid
# repetitions (e.g. an attack "burst") into a single behavioural unit.
#
# Design:
#   * This module is intentionally dependency-light (stdlib + numpy only) and
#     Qt-free, mirroring the pure-function pattern used by
#     ``reliability_model.build_disagreement_review`` so it is trivially
#     unit-testable without a QApplication.
#   * Callers pass plain ``(onset, offset)`` second tuples per behaviour; the
#     pandas/CSV extraction stays in the controller/dialog layer.
#   * The gap between two consecutive events is ``next.onset - running_max_
#     offset``. Because a *point* event is stored with ``offset == onset``,
#     the same formula degenerates to an onset-to-onset gap with no special
#     casing — so bout analysis works for both state and point behaviours
#     without needing to know the behaviour's kind.

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

EventPair = Tuple[float, float]


@dataclass
class Bout:
    """A single bout: a merged run of same-behaviour events."""

    start: float          # onset of the first event in the bout
    end: float            # max offset across the events in the bout
    n_events: int         # number of events merged into this bout
    active_time: float    # sum of individual event durations (0 for points)

    @property
    def duration(self) -> float:
        """Span from first onset to last offset."""
        return self.end - self.start


@dataclass
class BoutStats:
    """Per-(file, behaviour) bout summary."""

    behavior: str = ""
    bci: float = 0.0
    n_events: int = 0
    n_bouts: int = 0
    events_per_bout_mean: Optional[float] = None
    events_per_bout_median: Optional[float] = None
    bout_duration_mean: Optional[float] = None
    bout_duration_median: Optional[float] = None
    bout_duration_total: float = 0.0
    within_bout_active_total: float = 0.0
    inter_bout_interval_mean: Optional[float] = None
    bout_rate_per_min: Optional[float] = None
    bouts: List[Bout] = field(default_factory=list)


def _clean_events(events: Sequence[EventPair]) -> List[EventPair]:
    """Coerce to finite ``(onset, offset)`` floats, fix swaps, sort by onset."""
    cleaned: List[EventPair] = []
    for pair in events:
        try:
            onset, offset = pair
            onset = float(onset)
            offset = float(offset)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(onset) and math.isfinite(offset)):
            continue
        if offset < onset:
            onset, offset = offset, onset
        cleaned.append((onset, offset))
    cleaned.sort(key=lambda pair: (pair[0], pair[1]))
    return cleaned


def inter_event_intervals(events: Sequence[EventPair]) -> List[float]:
    """Return gaps between consecutive same-behaviour events.

    Gap = ``next.onset - running_max_offset``. Overlapping events yield a
    non-positive gap; only the magnitudes matter to the caller. Point events
    (offset == onset) collapse to onset-to-onset gaps automatically.
    """
    cleaned = _clean_events(events)
    if len(cleaned) < 2:
        return []
    gaps: List[float] = []
    running_max_offset = cleaned[0][1]
    for onset, offset in cleaned[1:]:
        gaps.append(onset - running_max_offset)
        if offset > running_max_offset:
            running_max_offset = offset
    return gaps


def compute_bouts(events: Sequence[EventPair], bci: float) -> List[Bout]:
    """Merge consecutive same-behaviour events whose gap <= ``bci`` into bouts.

    Args:
        events: iterable of ``(onset, offset)`` in seconds, one behaviour.
        bci: bout-criterion interval in seconds (negative is treated as 0).

    Returns:
        Bouts in chronological order.
    """
    cleaned = _clean_events(events)
    if not cleaned:
        return []
    if bci < 0:
        bci = 0.0

    bouts: List[Bout] = []
    cur_start, cur_end = cleaned[0]
    cur_n = 1
    cur_active = cur_end - cur_start

    for onset, offset in cleaned[1:]:
        gap = onset - cur_end
        if gap <= bci:
            # Same bout (gap == bci merges; see PLAN spec).
            cur_n += 1
            cur_active += (offset - onset)
            if offset > cur_end:
                cur_end = offset
        else:
            bouts.append(Bout(cur_start, cur_end, cur_n, cur_active))
            cur_start, cur_end, cur_n, cur_active = onset, offset, 1, offset - onset

    bouts.append(Bout(cur_start, cur_end, cur_n, cur_active))
    return bouts


def compute_bout_stats(
    events: Sequence[EventPair],
    bci: float,
    behavior: str = "",
    session_duration: Optional[float] = None,
) -> BoutStats:
    """Compute the full bout summary for one behaviour in one file."""
    cleaned = _clean_events(events)
    bouts = compute_bouts(cleaned, bci)
    stats = BoutStats(
        behavior=behavior,
        bci=float(max(0.0, bci)),
        n_events=len(cleaned),
        n_bouts=len(bouts),
        bouts=bouts,
    )
    if not bouts:
        return stats

    events_per_bout = [bout.n_events for bout in bouts]
    durations = [bout.duration for bout in bouts]

    stats.events_per_bout_mean = float(statistics.mean(events_per_bout))
    stats.events_per_bout_median = float(statistics.median(events_per_bout))
    stats.bout_duration_mean = float(statistics.mean(durations))
    stats.bout_duration_median = float(statistics.median(durations))
    stats.bout_duration_total = float(sum(durations))
    stats.within_bout_active_total = float(sum(bout.active_time for bout in bouts))

    if len(bouts) >= 2:
        ibis = [bouts[i + 1].start - bouts[i].end for i in range(len(bouts) - 1)]
        stats.inter_bout_interval_mean = float(statistics.mean(ibis))

    if session_duration and session_duration > 0:
        stats.bout_rate_per_min = len(bouts) / (float(session_duration) / 60.0)

    return stats


def _line_sse(x: np.ndarray, y: np.ndarray) -> float:
    """Sum of squared residuals of an ordinary least-squares line fit."""
    if x.size < 2:
        return 0.0
    slope, intercept = np.polyfit(x, y, 1)
    resid = y - (slope * x + intercept)
    return float(np.sum(resid ** 2))


def _positive_gaps(events: Sequence[EventPair]) -> np.ndarray:
    """Sorted, strictly-positive inter-event intervals as a float array."""
    gaps = [gap for gap in inter_event_intervals(events) if gap > 0]
    return np.sort(np.asarray(gaps, dtype=float))


def estimate_bci_broken_stick(events: Sequence[EventPair]) -> Optional[float]:
    """Bout-criterion estimate via the log-frequency broken-stick method.

    Sibly, Nott & Fletcher (1990): on a log time axis the frequency histogram
    of inter-event intervals tends to fall as two straight segments — a steep
    within-bout limb and a shallow between-bout limb — and the bout criterion
    is where they cross. Unlike a log-survivorship curve the histogram's points
    are independent, which is why this line fit is preferred.

    Degenerate-data guards return ``None`` when a stable two-line fit is not
    possible (too few intervals, too few distinct values, or too few non-empty
    histogram bins).
    """
    gaps = _positive_gaps(events)
    n = gaps.size
    if n < 10 or np.unique(gaps).size < 4:
        return None

    x = np.log(gaps)
    n_bins = int(min(40, max(6, round(2.0 * n ** (1.0 / 3.0)))))  # Rice-like
    counts, edges = np.histogram(x, bins=n_bins)
    centers = 0.5 * (edges[:-1] + edges[1:])
    nonzero = counts > 0
    cx = centers[nonzero]
    cy = np.log(counts[nonzero].astype(float))
    if cx.size < 4:
        return None

    best_sse: Optional[float] = None
    best_split: Optional[int] = None
    for split in range(2, cx.size - 1):  # both segments need >= 2 points
        sse = _line_sse(cx[:split], cy[:split]) + _line_sse(cx[split:], cy[split:])
        if best_sse is None or sse < best_sse:
            best_sse, best_split = sse, split
    if best_split is None:
        return None

    try:
        slope1, int1 = np.polyfit(cx[:best_split], cy[:best_split], 1)
        slope2, int2 = np.polyfit(cx[best_split:], cy[best_split:], 1)
        if not math.isclose(slope1, slope2):
            x_star = (int2 - int1) / (slope1 - slope2)
            if cx[0] <= x_star <= cx[-1]:
                return float(np.exp(x_star))
    except Exception:
        pass
    return float(np.exp(cx[best_split]))  # fall back to the break abscissa


def estimate_bci_lognormal_mixture(events: Sequence[EventPair]) -> Optional[float]:
    """Bout-criterion estimate via a two-component log-normal mixture.

    Tolkamp & Kyriazakis (1999): log-transformed inter-event intervals are
    modelled as a mixture of two Gaussians (within-bout and between-bout
    populations) fitted by EM; the bout criterion is the antimode where the two
    components cross. This is the most defensible of the common methods but
    needs enough, genuinely bimodal data.

    Returns ``None`` when the fit is degenerate: too few / too uniform
    intervals, a vanishing component, non-separated means, or no antimode
    between the two means.
    """
    gaps = _positive_gaps(events)
    n = gaps.size
    if n < 10 or np.unique(gaps).size < 4:
        return None

    x = np.log(gaps)
    half = n // 2
    m1 = float(np.mean(x[:half]))   # x is already sorted (from _positive_gaps)
    m2 = float(np.mean(x[half:]))
    if math.isclose(m1, m2):
        return None
    v1 = v2 = max(float(np.var(x)), 1e-6)
    w1 = w2 = 0.5

    def _normpdf(vals, mu, var):
        var = max(var, 1e-9)
        return np.exp(-0.5 * (vals - mu) ** 2 / var) / math.sqrt(2.0 * math.pi * var)

    prev_ll: Optional[float] = None
    for _ in range(300):
        p1 = w1 * _normpdf(x, m1, v1)
        p2 = w2 * _normpdf(x, m2, v2)
        denom = p1 + p2
        denom[denom <= 0] = 1e-300
        r1 = p1 / denom
        n1 = float(r1.sum())
        n2 = float(n - n1)
        if n1 < 1e-6 or n2 < 1e-6:
            return None
        w1, w2 = n1 / n, n2 / n
        m1 = float((r1 * x).sum() / n1)
        m2 = float(((1.0 - r1) * x).sum() / n2)
        v1 = max(float((r1 * (x - m1) ** 2).sum() / n1), 1e-6)
        v2 = max(float(((1.0 - r1) * (x - m2) ** 2).sum() / n2), 1e-6)
        ll = float(np.sum(np.log(denom)))
        if prev_ll is not None and abs(ll - prev_ll) < 1e-8:
            break
        prev_ll = ll

    if m1 > m2:  # order components low -> high mean
        m1, m2, v1, v2, w1, w2 = m2, m1, v2, v1, w2, w1
    # The between-bout population is naturally the minority (few bouts, many
    # within-bout intervals), so the weight floor is deliberately low; the real
    # guards against a degenerate fit are mean separation + an antimode that
    # actually lies between the two means.
    if min(w1, w2) < 0.02 or m2 - m1 <= 0:
        return None

    # Antimode: solve w1*N(x|m1,v1) == w2*N(x|m2,v2) for x in (m1, m2).
    a = 1.0 / (2.0 * v2) - 1.0 / (2.0 * v1)
    b = m1 / v1 - m2 / v2
    k = math.log(w1) - 0.5 * math.log(v1) - math.log(w2) + 0.5 * math.log(v2)
    c = -m1 * m1 / (2.0 * v1) + m2 * m2 / (2.0 * v2) + k

    roots = []
    if abs(a) < 1e-12:
        if abs(b) > 1e-12:
            roots = [-c / b]
    else:
        disc = b * b - 4.0 * a * c
        if disc >= 0:
            sq = math.sqrt(disc)
            roots = [(-b + sq) / (2.0 * a), (-b - sq) / (2.0 * a)]
    between = [r for r in roots if m1 <= r <= m2]
    if not between:
        return None
    return float(np.exp(between[0]))


def estimate_bci(events: Sequence[EventPair], method: str = "auto") -> Optional[float]:
    """Advisory bout-criterion estimate. **Advisory only** — never auto-applied.

    Args:
        events: ``(onset, offset)`` pairs for one behaviour.
        method:
            * ``"mixture"``      – two-component log-normal mixture
              (Tolkamp & Kyriazakis; most defensible).
            * ``"broken_stick"`` – log-frequency broken-stick (Sibly et al.).
            * ``"auto"`` (default) – mixture first, broken-stick fallback.

    Returns the estimate in seconds, or ``None`` when no method can fit.
    """
    if method == "broken_stick":
        return estimate_bci_broken_stick(events)
    if method == "mixture":
        return estimate_bci_lognormal_mixture(events)
    value = estimate_bci_lognormal_mixture(events)
    if value is None:
        value = estimate_bci_broken_stick(events)
    return value
