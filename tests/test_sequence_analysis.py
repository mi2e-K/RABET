"""Tests for the pure first-order transition engine (models/sequence_analysis.py)."""

from __future__ import annotations

import numpy as np
import pytest

from models.sequence_analysis import (
    antecedent_window_metric,
    clean_events,
    collapse_repeats,
    collapse_to_bouts,
    compute_transitions,
    lag_profile,
    pool_transitions,
    tidy_rows,
)


def _seq(labels, dt=1.0, dur=0.4):
    """Build evenly-spaced (behavior, onset, offset) events from a label list."""
    return [(lab, i * dt, i * dt + dur) for i, lab in enumerate(labels)]


def test_clean_events_filters_sorts_and_swaps():
    events = [
        ("B", 2.0, 2.5),
        ("RecordingStart", 0.0, 0.0),
        ("A", 1.0, 0.5),   # inverted -> swapped
        ("", 3.0, 3.5),    # empty behaviour -> dropped
    ]
    cleaned = clean_events(events)
    assert [e[0] for e in cleaned] == ["A", "B"]  # RecordingStart + empty gone
    assert cleaned[0] == ("A", 0.5, 1.0)          # swapped + sorted first


def test_collapse_repeats_merges_runs():
    events = _seq(["A", "A", "A", "B", "A"])
    collapsed = collapse_repeats(events)
    assert [e[0] for e in collapsed] == ["A", "B", "A"]
    # First merged token spans first onset to last offset of the run.
    assert collapsed[0][1] == 0.0
    assert collapsed[0][2] == pytest.approx(2.4)


def test_basic_counts_and_conditional_probability():
    result = compute_transitions(_seq(["A", "B", "A", "B", "A"]), ["A", "B"])
    assert result.counts.tolist() == [[0.0, 2.0], [2.0, 0.0]]
    assert result.n_transitions == 4
    assert result.cond_prob[0, 1] == pytest.approx(1.0)
    assert result.cond_prob[1, 0] == pytest.approx(1.0)


def test_window_filters_distant_transitions():
    events = [("A", 0.0, 0.5), ("B", 5.0, 5.5)]  # gap 4.5 s
    assert compute_transitions(events, ["A", "B"], window=2.0).n_transitions == 0
    far = compute_transitions(events, ["A", "B"], window=None)
    assert far.n_transitions == 1
    assert far.counts[0, 1] == 1.0


def test_raw_keeps_self_transitions_collapsed_removes_them():
    events = _seq(["A", "A", "B", "A"])
    raw = compute_transitions(events, ["A", "B"], mode="raw_events")
    assert raw.counts[0, 0] == 1.0          # A->A is real in raw mode
    assert raw.exclude_self is False

    collapsed = compute_transitions(events, ["A", "B"], mode="bout_collapsed")
    assert collapsed.counts[0, 0] == 0.0    # merged away
    assert collapsed.exclude_self is True
    # Diagonal is a structural zero: expected ~0 and residual undefined.
    assert collapsed.expected[0, 0] == pytest.approx(0.0, abs=1e-6)
    assert np.isnan(collapsed.adjusted_residual[0, 0])
    # IPF preserves the observed marginals.
    assert collapsed.expected.sum(axis=1) == pytest.approx(collapsed.counts.sum(axis=1))
    assert collapsed.expected.sum(axis=0) == pytest.approx(collapsed.counts.sum(axis=0))


def test_adjusted_residual_sign_reflects_over_representation():
    # A->B occurs more than chance; A->A less (it never happens).
    result = compute_transitions(_seq(["A", "B", "A", "B", "A", "B"]), ["A", "B"])
    assert result.adjusted_residual[0, 1] > 0   # A->B over-represented
    assert result.adjusted_residual[0, 0] < 0   # A->A under-represented


def test_tidy_rows_skips_diagonal_when_self_excluded():
    result = compute_transitions(_seq(["A", "A", "B", "A"]), ["A", "B"],
                                 mode="bout_collapsed")
    rows = tidy_rows(result, animal_id="1175")
    assert len(rows) == 2  # 2 behaviours, diagonal skipped
    assert all(r["antecedent"] != r["consequent"] for r in rows)
    assert all(r["animal_id"] == "1175" for r in rows)


def test_low_count_flag_for_small_antecedent_base():
    result = compute_transitions(_seq(["A", "B", "A"]), ["A", "B"])
    # Tiny sequence -> every antecedent base is < 30, so all cells flagged.
    assert result.low_count.all()


# --- 1.4.0 Tier 1-2 additions ---------------------------------------------- #


def test_collapse_to_bouts_merges_by_gap():
    events = [("A", 0.0, 0.1), ("A", 0.3, 0.4), ("A", 2.0, 2.1)]  # gaps 0.2, 1.6
    bouts = collapse_to_bouts(events, bci=0.5)
    assert len(bouts) == 2
    assert bouts[0] == ("A", 0.0, 0.4)
    assert bouts[1] == ("A", 2.0, 2.1)


def test_bout_bci_collapses_bursts_in_transitions():
    # Three rapid A "bites" then a B. Raw: A->A twice; bout-collapsed: one A.
    events = [("A", 0.0, 0.1), ("A", 0.3, 0.4), ("A", 0.6, 0.7), ("B", 1.0, 1.1)]
    raw = compute_transitions(events, ["A", "B"], mode="raw_events")
    assert raw.counts[0, 0] == 2.0  # A->A within the burst
    burst = compute_transitions(events, ["A", "B"], bout_bci=0.5)
    assert burst.bout_bci == 0.5
    assert burst.counts[0, 0] == 0.0  # burst collapsed to a single A token
    assert burst.counts[0, 1] == 1.0  # A(burst) -> B


def test_odds_ratio_finite_value():
    result = compute_transitions(_seq(["A", "B", "B", "A", "A", "B", "B", "A"]), ["A", "B"])
    # Worked example: OR[A->B] = (2*2)/(1*2) = 2.0
    assert result.odds_ratio[0, 1] == pytest.approx(2.0)


def test_antecedent_window_metric_event_and_bout():
    events = [("S", 1.0, 1.1), ("X", 1.5, 1.6), ("X", 10.0, 10.1)]
    r = antecedent_window_metric(events, "X", ["S"], window=2.0, target_level="event")
    assert r["n_targets"] == 2
    assert r["observed"] == pytest.approx(0.5)  # only the first X is preceded by S
    # chance-correction runs and yields a finite above-chance value.
    rc = antecedent_window_metric(events, "X", ["S"], window=2.0,
                                  n_perm=200, session_duration=12.0, seed=0)
    assert rc["chance_mean"] == rc["chance_mean"]  # not NaN
    assert rc["above_chance"] == rc["above_chance"]


def test_antecedent_permutation_uses_one_circular_shift(monkeypatch):
    calls = []

    class FakeRng:
        def uniform(self, low, high=None):
            calls.append((low, high))
            return 10.0

    monkeypatch.setattr(
        "models.sequence_analysis.np.random.default_rng",
        lambda seed: FakeRng(),
    )
    events = [
        ("S", 0.0, 0.1),
        ("S", 2.0, 2.1),
        ("X", 11.0, 11.1),
        ("X", 13.0, 13.1),
    ]

    result = antecedent_window_metric(
        events,
        "X",
        ["S"],
        window=1.5,
        n_perm=1,
        session_duration=20.0,
        seed=123,
    )

    assert len(calls) == 1
    assert result["chance_mean"] == pytest.approx(1.0)


def test_lag_profile_positive_at_lag1():
    z = lag_profile(_seq(["A", "B", "A", "B", "A", "B"]), ["A"], "B", lags=(1, 2, 3))
    assert len(z) == 3
    assert z[0] > 0  # A strongly precedes B at lag 1


def test_pool_transitions_sums_counts_without_boundary_leak():
    beh = ["A", "B"]
    a1 = _seq(["A", "B", "A", "B"])  # A->B x2, B->A x1
    a2 = _seq(["A", "B"])            # A->B x1
    s1 = compute_transitions(a1, beh)
    s2 = compute_transitions(a2, beh)
    pooled = pool_transitions([a1, a2], beh)
    idx = {b: i for i, b in enumerate(beh)}
    # Pooled counts are the per-animal sum...
    assert np.array_equal(pooled.counts, s1.counts + s2.counts)
    assert pooled.counts[idx["A"], idx["B"]] == 3
    # ...and crucially NO spurious B(last of a1) -> A(first of a2) boundary edge.
    assert pooled.counts[idx["B"], idx["A"]] == 1
    assert pooled.n_transitions == s1.n_transitions + s2.n_transitions
    assert pooled.behaviors == beh
