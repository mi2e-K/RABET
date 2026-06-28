"""Tests for the pure bout-analysis module (models/bout_analysis.py)."""

from __future__ import annotations

import pytest

import numpy as np

from models.bout_analysis import (
    compute_bout_stats,
    compute_bouts,
    estimate_bci,
    estimate_bci_broken_stick,
    estimate_bci_lognormal_mixture,
    inter_event_intervals,
)


def _events_from_gaps(gaps):
    """Build point-like events (offset == onset) whose inter-event intervals
    reproduce ``gaps`` exactly."""
    t = 0.0
    events = [(0.0, 0.0)]
    for gap in gaps:
        t += float(gap)
        events.append((t, t))
    return events


def _bimodal_events(seed=0):
    """Bouted structure: many within-bout gaps (~0.3 s) + large between-bout
    gaps (~10 s), with realistic log-normal spread so both estimators have a
    well-populated interval distribution to fit."""
    rng = np.random.default_rng(seed)
    gaps = []
    for bout in range(8):
        gaps.extend(0.3 * np.exp(rng.normal(0.0, 0.5, size=20)))
        if bout < 7:
            gaps.append(10.0 * np.exp(rng.normal(0.0, 0.25)))
    return _events_from_gaps(gaps)


def test_empty_input():
    assert compute_bouts([], bci=1.0) == []
    stats = compute_bout_stats([], bci=1.0, behavior="X")
    assert stats.n_events == 0
    assert stats.n_bouts == 0
    assert stats.events_per_bout_mean is None


def test_gap_equal_to_bci_merges():
    # Two events with an exact 1.0 s gap merge when bci == 1.0.
    events = [(0.0, 0.5), (1.5, 2.0)]  # gap = 1.5 - 0.5 = 1.0
    assert len(compute_bouts(events, bci=1.0)) == 1
    # ...and split when the criterion is stricter.
    assert len(compute_bouts(events, bci=0.5)) == 2


def test_point_events_use_onset_to_onset_gaps():
    # Point events: offset == onset, so gaps are onset-to-onset.
    points = [(1.0, 1.0), (1.2, 1.2), (1.4, 1.4), (5.0, 5.0)]
    assert inter_event_intervals(points) == pytest.approx([0.2, 0.2, 3.6])
    bouts = compute_bouts(points, bci=1.0)
    assert len(bouts) == 2
    assert bouts[0].n_events == 3
    assert bouts[0].active_time == pytest.approx(0.0)  # points have no duration
    assert bouts[0].duration == pytest.approx(0.4)


def test_off_scatter_vs_bci():
    # Subset of real sample 1175 RI1-OFF "Attack bites": gaps ~1.05-1.4 s.
    off = [
        (13.50, 13.60), (14.90, 15.05), (16.10, 16.20),
        (17.30, 17.40), (18.80, 18.85), (20.10, 20.20),
    ]
    # At BCI = 1.0 s every gap exceeds the criterion -> all singletons.
    assert len(compute_bouts(off, bci=1.0)) == 6
    # At BCI = 1.5 s they all collapse into one bout.
    bouts = compute_bouts(off, bci=1.5)
    assert len(bouts) == 1
    assert bouts[0].n_events == 6


def test_on_burst_vs_bci():
    # Subset of real sample 1175 RI2-ON "Attack bites": a tight burst.
    on = [
        (156.40, 156.55), (156.85, 157.00), (157.35, 157.45),
        (157.80, 157.90), (158.20, 158.35), (158.65, 158.80),
        (159.15, 159.30), (160.30, 160.40),
    ]
    # BCI = 1.0 s: the final 1.0 s gap merges -> a single 8-event bout.
    bouts = compute_bouts(on, bci=1.0)
    assert len(bouts) == 1
    assert bouts[0].n_events == 8
    # BCI = 0.5 s: the trailing 1.0 s gap splits off the last event.
    bouts = compute_bouts(on, bci=0.5)
    assert len(bouts) == 2
    assert [b.n_events for b in bouts] == [7, 1]


def test_off_on_contrast_is_detectable():
    # The headline ON-condition signature: fewer, larger attack bouts.
    off = [(13.50, 13.60), (14.90, 15.05), (16.10, 16.20),
           (17.30, 17.40), (18.80, 18.85), (20.10, 20.20)]
    on = [(156.40, 156.55), (156.85, 157.00), (157.35, 157.45),
          (157.80, 157.90), (158.20, 158.35), (158.65, 158.80),
          (159.15, 159.30), (160.30, 160.40)]
    off_stats = compute_bout_stats(off, bci=1.0, behavior="Attack bites")
    on_stats = compute_bout_stats(on, bci=1.0, behavior="Attack bites")
    assert on_stats.n_bouts < off_stats.n_bouts
    assert on_stats.events_per_bout_mean > off_stats.events_per_bout_mean


def test_stats_fields():
    events = [(0.0, 1.0), (1.5, 2.0), (10.0, 11.0)]  # gaps 0.5, 8.0
    stats = compute_bout_stats(events, bci=1.0, behavior="B", session_duration=60.0)
    assert stats.n_events == 3
    assert stats.n_bouts == 2  # first two merge, last is separate
    assert stats.events_per_bout_mean == pytest.approx(1.5)
    assert stats.bout_duration_total == pytest.approx((2.0 - 0.0) + (11.0 - 10.0))
    # One inter-bout interval: 10.0 - 2.0 = 8.0
    assert stats.inter_bout_interval_mean == pytest.approx(8.0)
    # 2 bouts in 60 s -> 2 per minute.
    assert stats.bout_rate_per_min == pytest.approx(2.0)


def test_bci_estimator_too_few_returns_none():
    assert estimate_bci([(0.0, 0.1), (1.0, 1.1)]) is None
    assert estimate_bci_broken_stick([(0.0, 0.1), (1.0, 1.1)]) is None
    assert estimate_bci_lognormal_mixture([(0.0, 0.1), (1.0, 1.1)]) is None


def test_bci_estimators_degenerate_constant_returns_none():
    # All intervals identical -> no bimodality -> every estimator declines.
    events = _events_from_gaps([1.0] * 20)
    assert estimate_bci_broken_stick(events) is None
    assert estimate_bci_lognormal_mixture(events) is None
    assert estimate_bci(events) is None


def test_bci_broken_stick_bimodal_returns_plausible_value():
    bci = estimate_bci_broken_stick(_bimodal_events())
    assert bci is not None
    assert 0.1 < bci < 10.0


def test_bci_lognormal_mixture_bimodal_returns_plausible_value():
    bci = estimate_bci_lognormal_mixture(_bimodal_events())
    assert bci is not None
    assert 0.1 < bci < 10.0


def test_bci_auto_prefers_mixture_then_broken_stick():
    events = _bimodal_events()
    assert estimate_bci(events) == pytest.approx(
        estimate_bci_lognormal_mixture(events)
    )
