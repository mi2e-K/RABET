"""Tests for models.reliability_model.

These tests exercise the in-app Reliability computation surface:

* ``_parse_summary_table`` correctly understands the two-banded
  ``summary_table.csv`` layout (Duration / Frequency / custom metrics).
* Summary-mode ICC(2,1), Pearson r, and mean absolute difference are
  produced for matched animal IDs only.
* Detailed-mode time-window kappa / alpha are produced from a pair of
  annotation CSVs.

The tests intentionally use small synthetic CSVs written to ``tmp_path``
so they remain stable across RABET releases.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from models.reliability_model import (
    ReliabilityModel,
    SummaryMatchedPair,
    _parse_summary_table,
    _bin_events,
    _cohen_kappa,
    _icc_two_way_single,
    _krippendorff_alpha,
)
from views.reliability_view import SummaryMatchDialog


# -------------------------------------------------------------------- #
# _parse_summary_table
# -------------------------------------------------------------------- #


def _write_summary(path: Path, rows: list[tuple]) -> None:
    """Write a small summary_table.csv that mirrors RABET's two-banded layout.

    The on-disk shape is two leading band markers ("Duration" and
    "Frequency") followed by empty cells over the rest of the row;
    custom metric columns (Attack Latency, Total Aggression) have NO
    band tag - they only appear in the column-header row.
    """
    # band row: Duration starts at col 1, Frequency starts at col 6,
    # custom metrics (cols 11-12) have no band tag.
    header_band = ",Duration,,,,,Frequency,,,,,,,\n"
    col_header = (
        "animal_id,Attack bites,Sideways threats,Tail rattles,Chasing,,"
        "Attack bites,Sideways threats,Tail rattles,Chasing,,"
        "Attack Latency,Total Aggression\n"
    )
    body_lines = []
    for r in rows:
        body_lines.append(",".join(str(x) for x in r) + "\n")
    path.write_text(header_band + col_header + "".join(body_lines), encoding="utf-8")


def test_parse_summary_table_layout(tmp_path: Path) -> None:
    summary = tmp_path / "summary_table.csv"
    _write_summary(summary, [
        # animal, dur(4), spacer, freq(4), spacer, custom(2)
        ("a01", 1.5, 2.0, 0.5, 0.0, "", 3, 2, 1, 0, "", 12.5, 4.0),
        ("a02", 0.0, 0.0, 0.0, 0.0, "", 0, 0, 0, 0, "", 0.0, 0.0),
    ])
    df = _parse_summary_table(str(summary))
    # animal_id should be preserved; spacer columns should be dropped.
    assert list(df["animal_id"]) == ["a01", "a02"]
    # Per-band metric columns should carry the band suffix.
    assert "Attack bites (Duration)" in df.columns
    assert "Attack bites (Frequency)" in df.columns
    # Custom metrics keep their raw names.
    assert "Attack Latency" in df.columns
    assert "Total Aggression" in df.columns

    # Numeric cells should be coerced to float.
    assert pytest.approx(df.loc[0, "Attack bites (Duration)"], rel=1e-6) == 1.5
    assert df.loc[1, "Total Aggression"] == 0.0


# -------------------------------------------------------------------- #
# Summary mode end-to-end
# -------------------------------------------------------------------- #


@pytest.fixture
def summary_pair(tmp_path: Path) -> tuple[str, str]:
    """Two scorers, three animals, perfect agreement on one metric, mild
    disagreement on another."""
    a = tmp_path / "summary_a.csv"
    b = tmp_path / "summary_b.csv"
    _write_summary(a, [
        ("a01", 1.5, 2.0, 0.5, 0.0, "", 3, 2, 1, 0, "", 12.5, 4.0),
        ("a02", 0.5, 1.0, 0.0, 0.5, "", 1, 1, 0, 1, "", 99.0, 1.5),
        ("a03", 2.5, 3.0, 0.5, 0.5, "", 5, 4, 1, 1, "", 7.0, 6.5),
    ])
    _write_summary(b, [
        ("a01", 1.4, 2.1, 0.5, 0.0, "", 3, 2, 1, 0, "", 12.5, 4.0),
        ("a02", 0.5, 1.0, 0.0, 0.6, "", 1, 1, 0, 1, "", 99.0, 1.5),
        ("a03", 2.6, 3.0, 0.4, 0.5, "", 5, 4, 1, 1, "", 7.0, 6.5),
    ])
    return str(a), str(b)


def test_summary_mode_runs_and_matches_animals(
    summary_pair, qt_app
) -> None:
    pingouin = pytest.importorskip("pingouin")
    path_a, path_b = summary_pair
    model = ReliabilityModel()
    result = model.compute_from_summaries(path_a, path_b)
    assert result is not None
    assert result.matched_animals == ["a01", "a02", "a03"]
    assert [pair.source for pair in result.matched_pairs] == [
        "exact", "exact", "exact",
    ]
    assert not result.unmatched_a
    assert not result.unmatched_b
    # Should have at least the four Duration columns + four Frequency
    # columns + two custom metrics = 10 rows.
    assert len(result.rows) >= 10

    # Frequency for "Attack bites" is identical between scorers, so the
    # ICC must be very close to 1.
    freq_attack_rows = [
        r for r in result.rows if r.metric == "Attack bites (Frequency)"
    ]
    assert freq_attack_rows
    icc = freq_attack_rows[0].icc
    assert icc is not None
    assert icc >= 0.99


def test_summary_mode_reports_unmatched_animals(tmp_path: Path, qt_app) -> None:
    pytest.importorskip("pingouin")
    a = tmp_path / "summary_a.csv"
    b = tmp_path / "summary_b.csv"
    _write_summary(a, [
        ("a01", 1.0, 1.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
        ("a02", 1.0, 1.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
    ])
    _write_summary(b, [
        ("a02", 1.0, 1.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
        ("a03", 1.0, 1.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
    ])
    model = ReliabilityModel()
    result = model.compute_from_summaries(str(a), str(b))
    assert result is not None
    assert result.matched_animals == ["a02"]
    assert result.unmatched_a == ["a01"]
    assert result.unmatched_b == ["a03"]


def test_summary_mode_matches_session_suffix_ids(
    tmp_path: Path, qt_app
) -> None:
    pytest.importorskip("pingouin")
    a = tmp_path / "summary_a.csv"
    b = tmp_path / "summary_b.csv"
    _write_summary(a, [
        ("R01_1", 1.0, 2.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
        ("R02_1", 2.0, 3.0, 0.5, 0.5, "", 3, 3, 1, 1, "", 20.0, 4.0),
    ])
    _write_summary(b, [
        ("R01_2", 1.2, 2.1, 0.5, 0.5, "", 2, 2, 1, 1, "", 11.0, 2.5),
        ("R02_2", 2.2, 3.1, 0.5, 0.5, "", 3, 3, 1, 1, "", 19.0, 3.5),
    ])
    model = ReliabilityModel()
    result = model.compute_from_summaries(str(a), str(b))
    assert result is not None
    assert result.matched_animals == ["R01", "R02"]
    assert [pair.source for pair in result.matched_pairs] == [
        "flexible", "flexible",
    ]
    assert [
        (pair.animal_id_a, pair.animal_id_b)
        for pair in result.matched_pairs
    ] == [("R01_1", "R01_2"), ("R02_1", "R02_2")]
    assert not result.unmatched_a
    assert not result.unmatched_b


def test_summary_mode_manual_pairs_override_and_autofill(
    tmp_path: Path, qt_app
) -> None:
    pytest.importorskip("pingouin")
    a = tmp_path / "summary_a.csv"
    b = tmp_path / "summary_b.csv"
    _write_summary(a, [
        ("R01_1", 1.0, 2.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
        ("R03_1", 2.0, 3.0, 0.5, 0.5, "", 3, 3, 1, 1, "", 20.0, 4.0),
    ])
    _write_summary(b, [
        ("R02_2", 1.2, 2.1, 0.5, 0.5, "", 2, 2, 1, 1, "", 11.0, 2.5),
        ("R03_2", 2.2, 3.1, 0.5, 0.5, "", 3, 3, 1, 1, "", 19.0, 3.5),
    ])
    model = ReliabilityModel()
    result = model.compute_from_summaries(
        str(a), str(b), manual_pairs=[("R01_1", "R02_2")]
    )
    assert result is not None
    assert [
        (pair.animal_id_a, pair.animal_id_b, pair.source)
        for pair in result.matched_pairs
    ] == [
        ("R01_1", "R02_2", "manual"),
        ("R03_1", "R03_2", "flexible"),
    ]
    assert not result.unmatched_a
    assert not result.unmatched_b


def test_build_summary_match_plan_reports_unmatched(
    tmp_path: Path, qt_app
) -> None:
    pytest.importorskip("pingouin")
    a = tmp_path / "summary_a.csv"
    b = tmp_path / "summary_b.csv"
    _write_summary(a, [
        ("a01", 1.0, 1.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
        ("a02", 1.0, 1.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
    ])
    _write_summary(b, [
        ("a01", 1.0, 1.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
        ("b02", 1.0, 1.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
    ])
    model = ReliabilityModel()
    plan = model.build_summary_match_plan(str(a), str(b))
    assert plan is not None
    assert [(pair.animal_id_a, pair.animal_id_b, pair.source) for pair in plan.auto_pairs] == [
        ("a01", "a01", "exact"),
    ]
    assert plan.unmatched_a == ["a02"]
    assert plan.unmatched_b == ["b02"]


def test_summary_mode_matches_annotation_export_suffix(
    tmp_path: Path, qt_app
) -> None:
    pytest.importorskip("pingouin")
    a = tmp_path / "summary_a.csv"
    b = tmp_path / "summary_b.csv"
    _write_summary(a, [
        ("2_01_H_250330193053", 1.0, 2.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
    ])
    _write_summary(b, [
        (
            "2_01_H_250330193053_annotations_20250601_160605",
            1.2, 2.1, 0.5, 0.5, "", 2, 2, 1, 1, "", 11.0, 2.5,
        ),
    ])
    model = ReliabilityModel()
    result = model.compute_from_summaries(str(a), str(b))
    assert result is not None
    assert result.matched_animals == ["2_01_H_250330193053"]
    assert result.matched_pairs[0].source == "flexible"


def test_summary_mode_suffix_ambiguity_is_not_auto_matched(
    tmp_path: Path, qt_app
) -> None:
    pytest.importorskip("pingouin")
    a = tmp_path / "summary_a.csv"
    b = tmp_path / "summary_b.csv"
    _write_summary(a, [
        ("X_1", 1.0, 1.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
        ("X_2", 1.0, 1.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
    ])
    _write_summary(b, [
        ("X_3", 1.0, 1.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
    ])
    model = ReliabilityModel()
    errors: list[str] = []
    model.error_occurred.connect(errors.append)
    result = model.compute_from_summaries(str(a), str(b))
    assert result is None
    assert errors


@pytest.mark.parametrize(
    "manual_pairs, expected_message",
    [
        ([("a01", "b01"), ("a01", "b02")], "duplicate"),
        ([("a99", "b01")], "not in summary A"),
        ([("a01", "")], "empty animal_id"),
    ],
)
def test_summary_mode_rejects_invalid_manual_pairs(
    tmp_path: Path, qt_app, manual_pairs: list[tuple[str, str]],
    expected_message: str
) -> None:
    pytest.importorskip("pingouin")
    a = tmp_path / "summary_a.csv"
    b = tmp_path / "summary_b.csv"
    _write_summary(a, [
        ("a01", 1.0, 1.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
        ("a02", 1.0, 1.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
    ])
    _write_summary(b, [
        ("b01", 1.0, 1.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
        ("b02", 1.0, 1.0, 0.5, 0.5, "", 2, 2, 1, 1, "", 10.0, 2.0),
    ])
    model = ReliabilityModel()
    errors: list[str] = []
    model.error_occurred.connect(errors.append)
    result = model.compute_from_summaries(
        str(a), str(b), manual_pairs=manual_pairs
    )
    assert result is None
    assert errors
    assert expected_message in errors[0]


def test_summary_match_dialog_adds_pairs_and_reads_map(tmp_path: Path, qt_app) -> None:
    auto_pairs = [
        SummaryMatchedPair(
            match_id="a01",
            animal_id_a="a01",
            animal_id_b="b01",
            source="flexible",
        )
    ]
    dialog = SummaryMatchDialog(auto_pairs, ["a02"], ["b02"])
    assert dialog._add_manual_pair("a02", "b02", show_errors=False)
    assert dialog.manual_pairs() == [("a02", "b02")]
    assert dialog.all_pairs() == [("a01", "b01"), ("a02", "b02")]

    match_map = tmp_path / "match_map.csv"
    match_map.write_text("animal_id_a,animal_id_b\na03,b03\n", encoding="utf-8")
    assert SummaryMatchDialog._read_map_csv(str(match_map)) == [("a03", "b03")]


def test_summary_match_dialog_excludes_unmatched_items(qt_app) -> None:
    dialog = SummaryMatchDialog([], ["a01", "a02"], ["b01"])
    dialog.list_a.item(1).setSelected(True)
    dialog._exclude_selected(dialog.list_a, "A")
    assert dialog._list_values(dialog.list_a) == ["a01"]
    assert not dialog._add_manual_pair("a02", "b01", show_errors=False)


def test_summary_match_dialog_pairs_sorted_order(qt_app, monkeypatch) -> None:
    monkeypatch.setattr(
        "views.reliability_view.QMessageBox.information",
        lambda *args, **kwargs: None,
    )
    dialog = SummaryMatchDialog([], ["A10", "A2"], ["B10", "B2"])
    dialog._pair_sorted()
    assert dialog.manual_pairs() == [("A2", "B2"), ("A10", "B10")]
    assert dialog._list_values(dialog.list_a) == []
    assert dialog._list_values(dialog.list_b) == []


# -------------------------------------------------------------------- #
# Detailed mode end-to-end
# -------------------------------------------------------------------- #


def _write_annotation(path: Path, events: list[tuple[str, float, float]], duration: float) -> None:
    """Write a v1-schema annotation CSV with the given events."""
    lines = [
        "Metadata",
        "RABET Version,1.3.2",
        "Format Schema,v1",
        f"Test Duration (seconds),{duration:g}",
        "",
        "Event,Onset,Offset",
        "RecordingStart,0.0000,0.0000",
    ]
    for behavior, onset, offset in events:
        lines.append(f"{behavior},{onset:.4f},{offset:.4f}")
    lines.append("")
    lines.append("Behavior,Duration,Frequency")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_bin_events_overlap_logic() -> None:
    behaviors = ["Attack bites"]
    events = [
        ("Attack bites", 0.0, 1.2),  # bins 0, 1
        ("Attack bites", 4.5, 4.6),  # bin 4
    ]
    binned = _bin_events(events, behaviors, duration_seconds=6.0, bin_seconds=1.0)
    arr = binned["Attack bites"]
    expected = np.array([1, 1, 0, 0, 1, 0], dtype=np.uint8)
    assert np.array_equal(arr, expected)


def test_bin_events_handles_zero_onset_offset() -> None:
    """Regression test for the (offset - 1e-9) / bin_seconds negative-index bug.

    A zero-duration event at time 0 used to produce ``end_idx = -1``, which
    silently dropped the event from the bin grid. With the clamp added in
    1.3.2 the bin that contains the event must be marked.
    """
    behaviors = ["A"]
    events = [("A", 0.0, 0.0)]
    binned = _bin_events(events, behaviors, duration_seconds=5.0, bin_seconds=1.0)
    # The first bin should be flagged active (we treat an instantaneous
    # event at t=0 as falling into bin 0).
    assert binned["A"][0] == 1
    assert binned["A"].sum() == 1


def test_bin_events_endpoint_point_event_marks_last_bin() -> None:
    behaviors = ["A"]
    events = [("A", 10.0, 10.0)]
    binned = _bin_events(events, behaviors, duration_seconds=10.0, bin_seconds=1.0)
    assert binned["A"][-1] == 1
    assert binned["A"].sum() == 1


def test_bin_events_swaps_negative_duration() -> None:
    """If offset < onset the helper should swap them before binning."""
    behaviors = ["A"]
    events = [("A", 5.0, 3.0)]  # equivalent to onset=3.0, offset=5.0
    binned = _bin_events(events, behaviors, duration_seconds=10.0, bin_seconds=1.0)
    expected = np.array([0, 0, 0, 1, 1, 0, 0, 0, 0, 0], dtype=np.uint8)
    # We tolerate either including or excluding the bin that contains the
    # original offset, but bins 3 and 4 must be active.
    assert binned["A"][3] == 1
    assert binned["A"][4] == 1
    assert np.array_equal(binned["A"][:3], expected[:3])
    assert np.array_equal(binned["A"][5:], expected[5:])


def test_detailed_mode_perfect_agreement(tmp_path: Path, qt_app) -> None:
    pytest.importorskip("pingouin")
    events = [
        ("Attack bites", 1.0, 1.5),
        ("Sideways threats", 4.0, 5.0),
        ("Attack bites", 8.0, 8.4),
    ]
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    _write_annotation(a, events, duration=12.0)
    _write_annotation(b, events, duration=12.0)
    model = ReliabilityModel()
    result = model.compute_from_annotations(str(a), str(b), bin_seconds=1.0)
    assert result is not None
    assert sorted(result.behaviors) == ["Attack bites", "Sideways threats"]
    for row in result.rows:
        # Perfect agreement -> kappa should be 1 (or None when one of the
        # sequences has no variance; in that case raw_agreement must be 1).
        if row.cohen_kappa is None:
            assert row.raw_agreement == pytest.approx(1.0, abs=1e-6)
        else:
            assert row.cohen_kappa == pytest.approx(1.0, abs=1e-6)


def test_detailed_mode_partial_disagreement(tmp_path: Path, qt_app) -> None:
    pytest.importorskip("pingouin")
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    _write_annotation(a, [
        ("Attack bites", 0.0, 2.0),
        ("Attack bites", 6.0, 7.0),
    ], duration=10.0)
    _write_annotation(b, [
        ("Attack bites", 0.0, 2.0),
        ("Attack bites", 5.0, 7.0),  # extends one bin earlier
    ], duration=10.0)
    model = ReliabilityModel()
    result = model.compute_from_annotations(str(a), str(b), bin_seconds=1.0)
    assert result is not None
    attack = next(r for r in result.rows if r.behavior == "Attack bites")
    # Raw agreement should still be high (only one bin disagrees out of
    # 10) but kappa strictly less than 1.
    assert attack.raw_agreement >= 0.85
    if attack.cohen_kappa is not None:
        assert attack.cohen_kappa < 1.0


# -------------------------------------------------------------------- #
# Phase D coverage additions (1.3.2 hardening)
# -------------------------------------------------------------------- #


def test_cohen_kappa_both_zero_is_undefined() -> None:
    """Both rasters all-zero have raw agreement of 1.0, but kappa itself
    is undefined because the expected agreement denominator is zero."""
    va = np.zeros(10, dtype=np.uint8)
    vb = np.zeros(10, dtype=np.uint8)
    assert _cohen_kappa(va, vb) is None


def test_icc_constant_identical_values_are_undefined() -> None:
    va = np.array([5.0, 5.0, 5.0])
    vb = np.array([5.0, 5.0, 5.0])
    assert _icc_two_way_single(va, vb) is None


def test_summary_mode_constant_pearson_is_undefined(tmp_path: Path, qt_app) -> None:
    pytest.importorskip("pingouin")
    a = tmp_path / "summary_a.csv"
    b = tmp_path / "summary_b.csv"
    rows = [
        ("a01", 1.0, 0.0, 0.0, 0.0, "", 1, 0, 0, 0, "", 10.0, 2.0),
        ("a02", 1.0, 0.0, 0.0, 0.0, "", 1, 0, 0, 0, "", 10.0, 2.0),
        ("a03", 1.0, 0.0, 0.0, 0.0, "", 1, 0, 0, 0, "", 10.0, 2.0),
    ]
    _write_summary(a, rows)
    _write_summary(b, rows)

    model = ReliabilityModel()
    result = model.compute_from_summaries(str(a), str(b))

    assert result is not None
    attack_duration = next(
        row for row in result.rows if row.metric == "Attack bites (Duration)"
    )
    assert attack_duration.icc is None
    assert attack_duration.pearson_r is None


def test_cohen_kappa_flat_disagree_returns_zero() -> None:
    """When one rater is all-zero and the other is all-one, the two
    label distributions never co-occur on any single unit. Both
    observed agreement and expected agreement are 0, so kappa is
    defined as (0 - 0) / (1 - 0) == 0 - i.e. chance-level. This
    contrasts with the both-zero case which is degenerate-but-perfect.
    """
    va = np.zeros(10, dtype=np.uint8)
    vb = np.ones(10, dtype=np.uint8)
    assert _cohen_kappa(va, vb) == pytest.approx(0.0, abs=1e-9)


def test_krippendorff_alpha_perfect_agreement() -> None:
    """A2: confirm the standalone krippendorff library is wired up and
    returns 1.0 on identical rasters."""
    pytest.importorskip("krippendorff")
    va = np.array([1, 0, 1, 1, 0, 1, 0, 0], dtype=np.uint8)
    vb = va.copy()
    value = _krippendorff_alpha(va, vb)
    assert value is not None
    assert value == pytest.approx(1.0, abs=1e-9)


def test_parse_summary_table_duplicate_animal_id(tmp_path: Path) -> None:
    """A4: when the same animal_id appears twice, the parser must
    de-duplicate (keeping the last row) and not silently double-count."""
    summary = tmp_path / "dup.csv"
    _write_summary(summary, [
        ("a01", 1.0, 1.0, 0.5, 0.0, "", 2, 2, 1, 0, "", 10.0, 1.0),
        ("a01", 2.0, 2.0, 0.5, 0.0, "", 4, 4, 1, 0, "", 5.0,  2.0),
        ("a02", 0.0, 0.0, 0.0, 0.0, "", 0, 0, 0, 0, "", 0.0,  0.0),
    ])
    df = _parse_summary_table(str(summary))
    # Duplicates must be collapsed.
    assert list(df["animal_id"]) == ["a01", "a02"]
    # Last occurrence wins.
    a01 = df.set_index("animal_id").loc["a01"]
    assert a01["Attack bites (Duration)"] == pytest.approx(2.0)
    assert a01["Attack bites (Frequency)"] == pytest.approx(4)
    assert a01["Attack Latency"] == pytest.approx(5.0)


def test_compute_from_annotations_zero_duration(tmp_path: Path, qt_app) -> None:
    """If both annotation files have zero events and no Test Duration
    metadata, the model must surface an error rather than crash."""
    pytest.importorskip("pingouin")
    a = tmp_path / "empty_a.csv"
    b = tmp_path / "empty_b.csv"
    _write_annotation(a, [], duration=0.0)
    _write_annotation(b, [], duration=0.0)
    model = ReliabilityModel()
    errors: list[str] = []
    model.error_occurred.connect(errors.append)
    result = model.compute_from_annotations(str(a), str(b), bin_seconds=1.0)
    assert result is None
    assert errors  # at least one error message emitted


def test_compute_from_summaries_empty_intersection(tmp_path: Path, qt_app) -> None:
    """If the two summary files share no animal_id values the model
    emits an error and returns None."""
    pytest.importorskip("pingouin")
    a = tmp_path / "sa.csv"
    b = tmp_path / "sb.csv"
    _write_summary(a, [
        ("x01", 1.0, 1.0, 0.5, 0.0, "", 2, 2, 1, 0, "", 10.0, 1.0),
    ])
    _write_summary(b, [
        ("y01", 1.0, 1.0, 0.5, 0.0, "", 2, 2, 1, 0, "", 10.0, 1.0),
    ])
    model = ReliabilityModel()
    errors: list[str] = []
    model.error_occurred.connect(errors.append)
    result = model.compute_from_summaries(str(a), str(b))
    assert result is None
    assert errors
