"""Unit tests for ``models.reliability_model.build_disagreement_review``.

These tests cover the pure event-level matching surface used by the
Disagreement Review dialog. They intentionally avoid Qt so they can run
without a QApplication. The dialog's UI behaviour is exercised
elsewhere; here we only verify that:

* events are normalised correctly (empty names dropped, swapped
  onset/offset handled, zero-duration accepted),
* matching is behaviour-specific and one-to-one,
* status classification (``time_matched`` / ``timing_offset`` /
  ``reference_only`` / ``trainee_only``) follows the spec,
* ``review_items`` excludes ``time_matched`` events but counts include
  every status,
* output ordering is by ``jump_time``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from models.reliability_model import (
    DisagreementReviewResult,
    EventMatch,
    ReliabilityModel,
    build_disagreement_review,
)


_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "reliability_disagreement"


def _status_counts(result: DisagreementReviewResult) -> dict[str, int]:
    return dict(result.counts_by_type)


# -------------------------------------------------------------------- #
# 14.1 Perfect match
# -------------------------------------------------------------------- #


def test_perfect_match_is_time_matched() -> None:
    result = build_disagreement_review(
        events_reference=[("Attack bites", 10.0, 11.0)],
        events_trainee=[("Attack bites", 10.1, 11.1)],
        matching_window_seconds=2.0,
    )
    counts = _status_counts(result)
    assert counts["time_matched"] == 1
    assert counts["timing_offset"] == 0
    assert counts["reference_only"] == 0
    assert counts["trainee_only"] == 0
    assert result.review_items == []


# -------------------------------------------------------------------- #
# 14.2 Reference only
# -------------------------------------------------------------------- #


def test_reference_only_no_trainee_event() -> None:
    result = build_disagreement_review(
        events_reference=[("Attack bites", 10.0, 11.0)],
        events_trainee=[],
        matching_window_seconds=2.0,
    )
    counts = _status_counts(result)
    assert counts["reference_only"] == 1
    assert counts["trainee_only"] == 0
    assert len(result.review_items) == 1
    item = result.review_items[0]
    assert item.status == "reference_only"
    assert item.reference is not None
    assert item.trainee is None
    assert item.jump_time == pytest.approx(10.0)


# -------------------------------------------------------------------- #
# 14.3 Trainee only
# -------------------------------------------------------------------- #


def test_trainee_only_no_reference_event() -> None:
    result = build_disagreement_review(
        events_reference=[],
        events_trainee=[("Attack bites", 10.0, 11.0)],
        matching_window_seconds=2.0,
    )
    counts = _status_counts(result)
    assert counts["trainee_only"] == 1
    assert counts["reference_only"] == 0
    assert len(result.review_items) == 1
    item = result.review_items[0]
    assert item.status == "trainee_only"
    assert item.reference is None
    assert item.trainee is not None
    assert item.jump_time == pytest.approx(10.0)


# -------------------------------------------------------------------- #
# 14.4 Timing offset
# -------------------------------------------------------------------- #


def test_timing_offset_when_deltas_exceed_window() -> None:
    """Gap (1.5s) is within the matching window, so the pair becomes a
    candidate, but the onset and offset deltas (2.5s) exceed it, so the
    pair is classified as ``timing_offset`` rather than
    ``time_matched``."""
    result = build_disagreement_review(
        events_reference=[("Attack bites", 10.0, 11.0)],
        events_trainee=[("Attack bites", 12.5, 13.5)],
        matching_window_seconds=2.0,
    )
    counts = _status_counts(result)
    assert counts["timing_offset"] == 1
    assert counts["time_matched"] == 0
    assert counts["reference_only"] == 0
    assert counts["trainee_only"] == 0
    assert len(result.review_items) == 1
    item = result.review_items[0]
    assert item.status == "timing_offset"
    assert item.onset_delta == pytest.approx(2.5)
    assert item.offset_delta == pytest.approx(2.5)
    assert item.jump_time == pytest.approx(10.0)
    assert item.review_end == pytest.approx(13.5)


# -------------------------------------------------------------------- #
# 14.5 Different behaviour should not match
# -------------------------------------------------------------------- #


def test_different_behavior_never_matches() -> None:
    result = build_disagreement_review(
        events_reference=[("Attack bites", 10.0, 11.0)],
        events_trainee=[("Chasing", 10.0, 11.0)],
        matching_window_seconds=5.0,
    )
    counts = _status_counts(result)
    assert counts["reference_only"] == 1
    assert counts["trainee_only"] == 1
    assert counts["time_matched"] == 0
    assert counts["timing_offset"] == 0


# -------------------------------------------------------------------- #
# 14.6 One-to-one matching
# -------------------------------------------------------------------- #


def test_one_to_one_matching_for_same_behavior() -> None:
    """With one Reference event and two candidate Trainee events, only
    one Trainee event matches; the other becomes ``trainee_only``."""
    result = build_disagreement_review(
        events_reference=[("Attack bites", 10.0, 11.0)],
        events_trainee=[
            ("Attack bites", 10.1, 11.1),
            ("Attack bites", 10.2, 11.2),
        ],
        matching_window_seconds=2.0,
    )
    counts = _status_counts(result)
    assert counts["time_matched"] + counts["timing_offset"] == 1
    assert counts["trainee_only"] == 1
    assert counts["reference_only"] == 0


# -------------------------------------------------------------------- #
# 14.7 Reversed onset/offset is normalised
# -------------------------------------------------------------------- #


def test_reversed_onset_offset_is_normalized() -> None:
    result = build_disagreement_review(
        events_reference=[("Attack bites", 11.0, 10.0)],
        events_trainee=[("Attack bites", 10.0, 11.0)],
        matching_window_seconds=2.0,
    )
    counts = _status_counts(result)
    assert counts["time_matched"] == 1
    assert result.review_items == []


# -------------------------------------------------------------------- #
# 14.8 Zero-duration event
# -------------------------------------------------------------------- #


def test_zero_duration_event_does_not_crash() -> None:
    result = build_disagreement_review(
        events_reference=[("Attack bites", 10.0, 10.0)],
        events_trainee=[("Attack bites", 10.0, 10.0)],
        matching_window_seconds=2.0,
    )
    counts = _status_counts(result)
    assert counts["time_matched"] == 1


# -------------------------------------------------------------------- #
# 14.9 Review item sorting
# -------------------------------------------------------------------- #


def test_review_items_sorted_by_jump_time() -> None:
    """Disagreements created in arbitrary order must appear sorted by
    ``jump_time``."""
    result = build_disagreement_review(
        events_reference=[
            ("Reference solo", 30.0, 31.0),
            ("Timing offset behavior", 20.0, 21.0),
        ],
        events_trainee=[
            ("Trainee solo", 10.0, 11.0),
            ("Timing offset behavior", 25.0, 26.0),
        ],
        matching_window_seconds=10.0,  # wide enough to keep gap-based candidates
    )
    statuses = [item.status for item in result.review_items]
    jump_times = [item.jump_time for item in result.review_items]
    # We expect three review items:
    # - trainee_only at 10.0
    # - timing_offset at 20.0
    # - reference_only at 30.0
    assert jump_times == sorted(jump_times)
    assert jump_times[0] == pytest.approx(10.0)
    assert jump_times[-1] == pytest.approx(30.0)
    assert statuses[0] == "trainee_only"
    assert statuses[-1] == "reference_only"


# -------------------------------------------------------------------- #
# 14.10 Counts by behaviour
# -------------------------------------------------------------------- #


def test_counts_by_behavior_populated() -> None:
    """For one behaviour with mixed statuses, the per-behaviour count
    dict tracks every status."""
    result = build_disagreement_review(
        events_reference=[
            ("Attack bites", 10.0, 11.0),   # time_matched against trainee 10.1-11.1
            ("Attack bites", 20.0, 21.0),   # timing_offset against trainee 22.5-26.5
            ("Attack bites", 50.0, 51.0),   # reference_only (no trainee within window)
            ("Attack bites", 100.0, 101.0), # reference_only
        ],
        events_trainee=[
            ("Attack bites", 10.1, 11.1),   # time_matched with 10.0-11.0
            ("Attack bites", 22.5, 26.5),   # timing_offset with 20.0-21.0
            ("Attack bites", 200.0, 201.0), # trainee_only
        ],
        matching_window_seconds=2.0,
    )
    counts = result.counts_by_behavior["Attack bites"]
    assert counts["time_matched"] == 1
    assert counts["timing_offset"] == 1
    assert counts["reference_only"] == 2
    assert counts["trainee_only"] == 1


# -------------------------------------------------------------------- #
# Extra sanity coverage beyond §14
# -------------------------------------------------------------------- #


def test_review_items_exclude_time_matched() -> None:
    """``time_matched`` events appear in ``matches`` but not in
    ``review_items``."""
    result = build_disagreement_review(
        events_reference=[
            ("Attack bites", 10.0, 11.0),
            ("Attack bites", 50.0, 51.0),
        ],
        events_trainee=[
            ("Attack bites", 10.05, 11.05),
            ("Attack bites", 100.0, 101.0),
        ],
        matching_window_seconds=1.0,
    )
    statuses = [m.status for m in result.matches]
    assert "time_matched" in statuses
    review_statuses = [item.status for item in result.review_items]
    assert "time_matched" not in review_statuses


def test_pre_roll_seconds_stored_on_result() -> None:
    result = build_disagreement_review(
        events_reference=[("Attack bites", 5.0, 6.0)],
        events_trainee=[],
        matching_window_seconds=2.0,
        pre_roll_seconds=1.5,
    )
    assert result.pre_roll_seconds == pytest.approx(1.5)
    assert result.matching_window_seconds == pytest.approx(2.0)


def test_empty_inputs_produce_empty_result() -> None:
    result = build_disagreement_review(
        events_reference=[],
        events_trainee=[],
        matching_window_seconds=2.0,
    )
    assert result.matches == []
    assert result.review_items == []
    assert result.counts_by_type["time_matched"] == 0
    assert result.counts_by_type["timing_offset"] == 0
    assert result.counts_by_type["reference_only"] == 0
    assert result.counts_by_type["trainee_only"] == 0


def test_behavior_specific_one_to_one_with_overlap_preference() -> None:
    """When two Trainee events overlap the same Reference event, the
    candidate with the higher IoU wins regardless of input order."""
    result = build_disagreement_review(
        events_reference=[("Attack bites", 10.0, 12.0)],
        events_trainee=[
            ("Attack bites", 10.0, 10.5),  # small overlap (~25%)
            ("Attack bites", 10.0, 11.9),  # large overlap (~95%)
        ],
        matching_window_seconds=5.0,
    )
    matched_pairs = [m for m in result.matches if m.reference and m.trainee]
    assert len(matched_pairs) == 1
    # The larger-overlap trainee event must be the one chosen.
    assert matched_pairs[0].trainee is not None
    assert matched_pairs[0].trainee.offset == pytest.approx(11.9)
    # And the smaller-overlap trainee event ends up as trainee_only.
    leftovers = [
        m for m in result.matches
        if m.status == "trainee_only" and m.trainee is not None
    ]
    assert len(leftovers) == 1
    assert leftovers[0].trainee is not None
    assert leftovers[0].trainee.offset == pytest.approx(10.5)


def test_event_match_jump_time_uses_earlier_onset() -> None:
    """For a paired EventMatch, ``jump_time`` is the earlier onset."""
    result = build_disagreement_review(
        events_reference=[("Attack bites", 12.0, 13.0)],
        events_trainee=[("Attack bites", 10.0, 11.0)],
        matching_window_seconds=3.0,
    )
    item: EventMatch = result.matches[0]
    assert item.jump_time == pytest.approx(10.0)
    assert item.review_start == pytest.approx(10.0)
    assert item.review_end == pytest.approx(13.0)


def test_negative_matching_window_treated_as_zero() -> None:
    """A negative ``matching_window_seconds`` is clamped to zero rather
    than blowing up; this makes the dialog's spinbox more forgiving."""
    result = build_disagreement_review(
        events_reference=[("Attack bites", 10.0, 11.0)],
        events_trainee=[("Attack bites", 10.0, 11.0)],
        matching_window_seconds=-1.0,
    )
    # With window == 0 they still match exactly (deltas are 0).
    assert result.counts_by_type["time_matched"] == 1


def test_empty_behavior_name_is_skipped() -> None:
    result = build_disagreement_review(
        events_reference=[("", 10.0, 11.0), ("Attack bites", 20.0, 21.0)],
        events_trainee=[("Attack bites", 20.1, 21.1)],
        matching_window_seconds=2.0,
    )
    assert result.counts_by_type["time_matched"] == 1
    # The blank-behaviour event must be dropped, not counted as
    # reference_only.
    assert result.counts_by_type["reference_only"] == 0


# -------------------------------------------------------------------- #
# Fixture-based integration with the existing Detailed-mode parser
# -------------------------------------------------------------------- #


def test_fixture_files_round_trip_through_detailed_mode(qt_app) -> None:
    """End-to-end: feed two annotation CSV fixtures through the existing
    Detailed-mode parser and then build the disagreement review from the
    resulting events. This protects against the dialog growing its own
    parser by accident — the parser path stays inside ReliabilityModel.
    """
    pytest.importorskip("pingouin")

    reference_path = _FIXTURE_DIR / "reference_annotation.csv"
    trainee_path = _FIXTURE_DIR / "trainee_annotation.csv"
    assert reference_path.exists()
    assert trainee_path.exists()

    model = ReliabilityModel()
    detailed = model.compute_from_annotations(
        str(reference_path), str(trainee_path), bin_seconds=1.0,
    )
    assert detailed is not None
    assert detailed.events_a, "reference fixture parsed no events"
    assert detailed.events_b, "trainee fixture parsed no events"

    review = build_disagreement_review(
        events_reference=detailed.events_a,
        events_trainee=detailed.events_b,
        matching_window_seconds=2.0,
    )

    # The fixtures are designed to produce a mix of every status.
    counts = review.counts_by_type
    assert counts["time_matched"] >= 1
    assert counts["timing_offset"] >= 1
    assert counts["reference_only"] >= 1
    assert counts["trainee_only"] >= 1

    # Review items must exclude time_matched and be sorted by jump_time.
    statuses = [item.status for item in review.review_items]
    assert "time_matched" not in statuses
    jump_times = [item.jump_time for item in review.review_items]
    assert jump_times == sorted(jump_times)
