"""near-neighbor candidate generation must equal brute force (§16-6).

The Phase 5 optimisation prunes far-apart (ref, trainee) pairs before scoring
them. These tests assert the produced candidate set is identical to the naive
O(N*M) version across sparse, dense, long-event and random inputs, so the
downstream greedy matching (and therefore the review output) is unchanged.
"""

from __future__ import annotations

import random

from models.reliability_model import (
    ReliabilityEvent,
    _candidate_pairs_for_behavior,
    _build_candidate_pair,
)


def _bruteforce(refs, trns, window):
    out = []
    for ref in refs:
        for trn in trns:
            p = _build_candidate_pair(ref, trn)
            if (
                p.overlap_seconds > 0
                or p.gap <= window
                or p.onset_delta <= window
            ):
                out.append(p)
    return out


def _ids(cands):
    return sorted((c.reference.event_id, c.trainee.event_id) for c in cands)


def _make(prefix, source, specs):
    return [
        ReliabilityEvent(f"{prefix}_{i}", "B", onset, offset, source)
        for i, (onset, offset) in enumerate(specs)
    ]


def _assert_match(refs, trns, window):
    fast = _candidate_pairs_for_behavior(refs, trns, window)
    slow = _bruteforce(refs, trns, window)
    assert _ids(fast) == _ids(slow)


def test_matches_bruteforce_sparse():
    refs = _make("ref", "reference", [(i * 5.0, i * 5.0 + 1.0) for i in range(40)])
    trns = _make("trn", "trainee", [(i * 5.0 + 0.5, i * 5.0 + 1.4) for i in range(40)])
    _assert_match(refs, trns, 2.0)


def test_matches_bruteforce_dense():
    refs = _make("ref", "reference", [(i * 0.3, i * 0.3 + 0.2) for i in range(60)])
    trns = _make("trn", "trainee", [(i * 0.3 + 0.1, i * 0.3 + 0.25) for i in range(60)])
    _assert_match(refs, trns, 1.0)


def test_matches_bruteforce_long_events():
    # A long trainee event (offset far from onset) must not be wrongly pruned.
    refs = _make("ref", "reference", [(10.0, 11.0), (50.0, 51.0)])
    trns = _make("trn", "trainee", [(0.0, 10.5), (49.0, 60.0)])
    _assert_match(refs, trns, 1.0)


def test_matches_bruteforce_random():
    rng = random.Random(42)
    for _ in range(25):
        refs = _make(
            "ref", "reference",
            [(o := rng.uniform(0, 100), o + rng.uniform(0.1, 3.0)) for _ in range(30)],
        )
        trns = _make(
            "trn", "trainee",
            [(o := rng.uniform(0, 100), o + rng.uniform(0.1, 3.0)) for _ in range(30)],
        )
        _assert_match(refs, trns, rng.choice([0.5, 1.0, 2.0]))


def test_empty_inputs_return_no_candidates():
    refs = _make("ref", "reference", [(0.0, 1.0)])
    assert _candidate_pairs_for_behavior(refs, [], 1.0) == []
    assert _candidate_pairs_for_behavior([], refs, 1.0) == []
