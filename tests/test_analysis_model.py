"""Tests for models.analysis_model correctness invariants (1.3.4).

Focus areas:
* ``_calculate_behavior_latency`` must not mutate the caller's DataFrame
  (cross-cut B / read-only df). Repeated metric passes over the same df
  must stay deterministic.
* ``_extract_summary_data`` must honour CSV quoting so a behaviour name
  containing a comma is parsed as a single field (BUG-015).
"""

from __future__ import annotations

import pandas as pd
import pytest

from models.analysis_model import AnalysisModel


@pytest.fixture
def model():
    return AnalysisModel()


def _events_df():
    """Object-dtype event frame, as produced by the CSV parser."""
    return pd.DataFrame(
        {
            "Event": ["RecordingStart", "Attack bites", "Attack bites"],
            "Onset": ["0.0000", "5.0000", "9.0000"],
            "Offset": ["0.0000", "6.0000", "10.0000"],
        }
    )


def test_latency_does_not_mutate_input_df(model):
    df = _events_df()
    before_dtype = df["Onset"].dtype  # object (strings)

    latency = model._calculate_behavior_latency(df, "Attack bites", 300)

    # First Attack bites at 5s, RecordingStart at 0s -> 5s latency.
    assert latency == pytest.approx(5.0)
    # The caller's frame is untouched: still object dtype, same values.
    assert df["Onset"].dtype == before_dtype
    assert list(df["Onset"]) == ["0.0000", "5.0000", "9.0000"]


def test_repeated_metric_passes_are_stable(model):
    df = _events_df()

    first = model._calculate_behavior_latency(df, "Attack bites", 300)
    # A different metric over the same df (total time) ...
    total = model._calculate_total_aggression(df, ["Attack bites"])
    # ... must not change a re-computed latency.
    second = model._calculate_behavior_latency(df, "Attack bites", 300)

    assert first == pytest.approx(second)
    assert total == pytest.approx(2.0)  # 1s + 1s, no overlap


def test_event_parser_normalizes_spaced_bom_header():
    from utils.annotation_csv_parser import extract_event_dataframe

    # Header with a leading BOM, surrounding spaces and odd casing, plus an
    # extra trailing column — all must still be recognised (BUG-016).
    content = (
        "﻿Metadata\n"
        "RABET Version,1.3.4\n"
        "\n"
        " Event , Onset , Offset ,Duration\n"
        "Attack bites,5.0,6.0,1.0\n"
        "Chasing,7.0,8.0,1.0\n"
        "\n"
        "Behavior,Duration,Frequency\n"
        "Attack bites,1.0,1\n"
    )
    df = extract_event_dataframe(content)

    assert list(df.columns[:3]) == ["Event", "Onset", "Offset"]
    # Only the two event rows are captured (summary section excluded).
    assert list(df["Event"]) == ["Attack bites", "Chasing"]
    assert df["Onset"].iloc[0] == pytest.approx(5.0)


def test_summary_parser_accepts_quoted_behavior_with_comma(model):
    content = (
        "Metadata\n"
        "RABET Version,1.3.4\n"
        "\n"
        "Behavior,Duration,Frequency\n"
        '"Investigate, object",1.25,2\n'
        "Attack bites,3.50,4\n"
    )
    summary = model._extract_summary_data(content)

    # The quoted comma must not split into an extra column.
    assert "Investigate, object" in summary
    assert summary["Investigate, object"]["duration"] == pytest.approx(1.25)
    assert summary["Investigate, object"]["frequency"] == 2
    assert summary["Attack bites"]["frequency"] == 4


def _summary_only_csv(tmp_path):
    """A summary-only CSV (no Event,Onset,Offset section)."""
    p = tmp_path / "summary_only.csv"
    p.write_text(
        "Metadata\n"
        "RABET Version,1.3.4\n"
        "Test Duration (seconds),300\n"
        "\n"
        "Behavior,Duration,Frequency\n"
        "Attack bites,2.00,3\n"
        "Sideways threats,1.00,2\n"
        "Chasing,1.50,1\n"
        "Tail rattles,0.50,1\n",
        encoding="utf-8",
    )
    return p


def test_summary_only_multi_behavior_metric_is_approximate(model, tmp_path):
    # Default metrics include multi-behaviour "Total Aggression".
    p = _summary_only_csv(tmp_path)
    assert model.load_files([str(p)]) is True

    approx = model.get_approximate_metric_names()
    assert "Total Aggression" in approx


def test_summary_only_single_behavior_metric_is_exact(model, tmp_path):
    # Configure a single-behaviour total-time metric; it must NOT be approximate.
    from models.analysis_config import AnalysisMetricsConfig
    cfg = AnalysisMetricsConfig()
    cfg.replace_metrics(
        [],
        [{"name": "Attack Only", "behaviors": ["Attack bites"], "enabled": True}],
    )
    model.set_metrics_config(cfg)

    p = _summary_only_csv(tmp_path)
    assert model.load_files([str(p)]) is True

    assert "Attack Only" not in model.get_approximate_metric_names()


def test_raw_event_total_time_not_marked_approximate(model, tmp_path):
    # A file WITH raw events computes overlap-aware metrics -> never approximate.
    p = tmp_path / "with_events.csv"
    p.write_text(
        "Metadata\n"
        "RABET Version,1.3.4\n"
        "Test Duration (seconds),300\n"
        "\n"
        "Event,Onset,Offset\n"
        "RecordingStart,0.0,0.0\n"
        "Attack bites,5.0,6.0\n"
        "Sideways threats,5.5,6.5\n"
        "\n"
        "Behavior,Duration,Frequency\n"
        "Attack bites,1.00,1\n",
        encoding="utf-8",
    )
    assert model.load_files([str(p)]) is True
    assert model.get_approximate_metric_names() == set()
