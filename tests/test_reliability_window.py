"""Detailed-mode reliability compares only the time both files recorded.

Bins used to run from video time 0 to the last offset, so a session that
started later in the video added pre-session bins where both scorers were
"absent" (raising raw agreement), and a longer session was compared against
one that had already ended.
"""

from __future__ import annotations

import csv

import numpy as np
import pytest

from controllers.reliability_controller import ReliabilityController
from models.reliability_model import (
    DetailedAgreementResult,
    ReliabilityModel,
    _bin_events,
    _cohen_kappa,
    _krippendorff_alpha,
)


def _write(path, events, *, duration, recording_start=0.0):
    lines = [
        "Metadata",
        "RABET Version,1.4.0",
        "Format Schema,v1",
        f"Test Duration (seconds),{duration:g}",
        "",
        "Event,Onset,Offset",
    ]
    if recording_start is not None:
        lines.append(f"RecordingStart,{recording_start:.4f},{recording_start:.4f}")
    for behavior, onset, offset in events:
        lines.append(f"{behavior},{onset:.4f},{offset:.4f}")
    lines += ["", "Behavior,Duration,Frequency", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def _scorers(start):
    """Two scorers on one 300 s session that begins ``start`` s into the video."""
    rng = np.random.default_rng(2)
    onsets = start + np.sort(rng.uniform(0, 295, 25))
    events_a = [("Attack", t, t + 2.0) for t in onsets]
    events_b = [
        ("Attack", t + rng.normal(0, 0.8), t + 2.0 + rng.normal(0, 0.8))
        for t in onsets[:20]
    ]
    return events_a, events_b


def _compute(tmp_path, file_a, file_b):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    _write(a, *file_a[:1], **file_a[1])
    _write(b, *file_b[:1], **file_b[1])
    result = ReliabilityModel().compute_from_annotations(str(a), str(b), bin_seconds=1.0)
    assert result is not None
    return result, a, b


def _row(result):
    (row,) = result.rows
    return row


def _stats_from_video_zero(result):
    """What Detailed mode computed before: bins over [0, test_duration_seconds)."""
    duration = result.test_duration_seconds
    va = _bin_events(result.events_a, ["Attack"], duration, 1.0)["Attack"]
    vb = _bin_events(result.events_b, ["Attack"], duration, 1.0)["Attack"]
    return len(va), float(np.mean(va == vb)), _cohen_kappa(va, vb), _krippendorff_alpha(va, vb)


def test_session_at_video_start_gives_the_same_numbers_as_before(tmp_path):
    events_a, events_b = _scorers(0.0)
    result, _a, _b = _compute(
        tmp_path,
        (events_a, {"duration": 300}),
        (events_b, {"duration": 300}),
    )
    row = _row(result)
    assert (result.window_start_seconds, result.window_end_seconds) == (0.0, 300.0)
    assert (row.n_bins, row.raw_agreement, row.cohen_kappa, row.krippendorff_alpha) == (
        _stats_from_video_zero(result)
    )


def test_late_session_is_compared_over_its_own_window(tmp_path):
    events_a, events_b = _scorers(120.0)
    result, _a, _b = _compute(
        tmp_path,
        (events_a, {"duration": 300, "recording_start": 120.0}),
        (events_b, {"duration": 300, "recording_start": 120.0}),
    )
    row = _row(result)
    assert (result.window_start_seconds, result.window_end_seconds) == (120.0, 420.0)
    assert row.n_bins == 300
    assert row.raw_agreement == pytest.approx(0.870, abs=5e-4)
    assert row.cohen_kappa == pytest.approx(0.616, abs=5e-4)

    # Before: 408 bins from video 0, including 120 empty pre-session ones.
    n_bins, raw, kappa, _alpha = _stats_from_video_zero(result)
    assert n_bins == 408
    assert raw == pytest.approx(0.904, abs=5e-4)
    assert kappa == pytest.approx(0.642, abs=5e-4)

    # The same session recorded from video 0 gives the same agreement.
    shifted_a, shifted_b = _scorers(0.0)
    at_zero, _a, _b = _compute(
        tmp_path,
        (shifted_a, {"duration": 300}),
        (shifted_b, {"duration": 300}),
    )
    assert _row(at_zero).raw_agreement == pytest.approx(row.raw_agreement, abs=1e-9)
    assert _row(at_zero).cohen_kappa == pytest.approx(row.cohen_kappa, abs=1e-9)


@pytest.mark.parametrize("durations", [(0, 0), (300, 0), (0, 300)])
def test_unknown_test_duration_keeps_the_previous_end(tmp_path, durations):
    events_a, events_b = _scorers(120.0)
    result, _a, _b = _compute(
        tmp_path,
        (events_a, {"duration": durations[0], "recording_start": 120.0}),
        (events_b, {"duration": durations[1], "recording_start": 120.0}),
    )
    assert result.window_start_seconds == 120.0
    assert result.window_end_seconds == result.test_duration_seconds
    assert not result.test_durations_differ


def test_missing_recording_start_keeps_video_zero_as_the_start(tmp_path):
    events_a, events_b = _scorers(120.0)
    result, _a, _b = _compute(
        tmp_path,
        (events_a, {"duration": 0, "recording_start": None}),
        (events_b, {"duration": 0, "recording_start": 120.0}),
    )
    assert result.window_start_seconds == 0.0
    assert _row(result).n_bins == _stats_from_video_zero(result)[0]


def test_events_before_the_later_start_are_not_compared(tmp_path):
    # Scorer A pressed record 5 s before scorer B and marked a bout in
    # between; B was not recording yet, so that bout is not a disagreement.
    early = [("Attack", 122.0, 124.0), ("Attack", 150.0, 152.0)]
    later = [("Attack", 150.0, 152.0)]
    result, _a, _b = _compute(
        tmp_path,
        (early, {"duration": 300, "recording_start": 120.0}),
        (later, {"duration": 295, "recording_start": 125.0}),
    )
    assert (result.window_start_seconds, result.window_end_seconds) == (125.0, 420.0)
    row = _row(result)
    assert row.n_bins == 295
    assert row.n_active_a == row.n_active_b == 2
    assert row.raw_agreement == 1.0
    assert result.test_durations_differ


def test_different_test_durations_end_at_the_earlier_session_end(tmp_path):
    events = [("Attack", 10.0, 12.0), ("Attack", 250.0, 252.0)]
    result, _a, _b = _compute(
        tmp_path,
        (events, {"duration": 300}),
        (events[:1], {"duration": 200}),
    )
    # B's session had ended before A's second bout; it is outside the window.
    assert (result.window_start_seconds, result.window_end_seconds) == (0.0, 200.0)
    row = _row(result)
    assert (row.n_bins, row.raw_agreement) == (200, 1.0)
    assert result.test_durations_differ


def test_sessions_that_do_not_overlap_are_reported(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    _write(a, [("Attack", 10.0, 11.0)], duration=100, recording_start=0.0)
    _write(b, [("Attack", 210.0, 211.0)], duration=100, recording_start=200.0)
    model = ReliabilityModel()
    errors = []
    model.error_occurred.connect(errors.append)
    assert model.compute_from_annotations(str(a), str(b)) is None
    assert errors and "no recorded time in common" in errors[0]


def test_export_lists_the_window_and_the_duration_warning(tmp_path):
    events = [("Attack", 10.0, 12.0)]
    result, _a, _b = _compute(
        tmp_path,
        (events, {"duration": 300}),
        (events, {"duration": 200}),
    )
    out = tmp_path / "detailed.csv"
    ReliabilityController._write_detailed_csv(result, str(out))
    with open(out, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0][:4] == ["Bin width (s)", "1.000", "Test duration (s)", "300.000"]
    assert rows[0][4:] == ["Compared from (s)", "0.000", "Compared to (s)", "200.000"]
    assert rows[1][0] == "Warning" and "300 s" in rows[1][1] and "200 s" in rows[1][1]


def test_view_shows_the_window_and_warns_on_different_durations(qt_app, tmp_path):
    from views.reliability_view import ReliabilityView

    events = [("Attack", 130.0, 132.0), ("Attack", 200.0, 203.0)]
    mismatched, _a, _b = _compute(
        tmp_path,
        (events, {"duration": 300, "recording_start": 120.0}),
        (events, {"duration": 200, "recording_start": 120.0}),
    )
    view = ReliabilityView()
    try:
        view.show_detailed_results(mismatched)
        assert "Compared window: 120.0–320.0 s (200.0 s)" in view.detailed_status.text()
        assert not view.detailed_warning.isHidden()
        assert "Scorer A: 300 s" in view.detailed_warning.text()
        assert "Scorer B: 200 s" in view.detailed_warning.text()

        matched = DetailedAgreementResult(
            rows=mismatched.rows,
            behaviors=mismatched.behaviors,
            test_duration_seconds=420.0,
            window_start_seconds=120.0,
            window_end_seconds=420.0,
            test_duration_a=300.0,
            test_duration_b=300.0,
        )
        view.show_detailed_results(matched)
        assert view.detailed_warning.isHidden()
    finally:
        view.deleteLater()
