"""Smoke tests for ``AnalysisModel`` core algorithms."""
from __future__ import annotations

import pandas as pd

from models.analysis_model import AnalysisModel


def test_calculate_total_aggression_overlapping(qt_app):
    """
    Five events spanning 1.0-9.0 with overlaps must total 8.0 seconds of
    "any active" coverage.
    """
    df = pd.DataFrame(
        {
            "Event":  ["Attack bites", "Attack bites", "Sideways threats",
                       "Sideways threats", "Chasing"],
            "Onset":  [1.0, 5.0, 2.0, 7.0, 4.0],
            "Offset": [3.0, 6.5, 4.5, 9.0, 8.0],
        }
    )
    model = AnalysisModel()
    total = model._calculate_total_aggression(
        df, ["Attack bites", "Sideways threats", "Chasing"]
    )
    assert abs(total - 8.0) < 1e-6


def test_calculate_total_aggression_disjoint(qt_app):
    df = pd.DataFrame(
        {
            "Event": ["Attack bites", "Attack bites"],
            "Onset": [1.0, 5.0],
            "Offset": [2.0, 7.0],
        }
    )
    model = AnalysisModel()
    total = model._calculate_total_aggression(df, ["Attack bites"])
    assert abs(total - 3.0) < 1e-6


def test_interval_analysis_overlap_counting(qt_app):
    """
    With 10-second intervals over 30 seconds, the first two intervals must
    capture Attack and Sideways events; the third must be empty.
    """
    df = pd.DataFrame(
        {
            "Event":  ["RecordingStart", "Attack bites", "Attack bites", "Sideways threats"],
            "Onset":  [0.0, 5.0, 15.0, 8.0],
            "Offset": [0.0, 8.0, 17.0, 12.0],
        }
    )
    model = AnalysisModel()
    model.set_interval_analysis(True, 10)
    result = model._analyze_intervals(df, 30)

    assert len(result) == 3
    i1, i2, i3 = result

    assert i1["Attack bites_duration"] == 3.0
    assert i1["Attack bites_count"] == 1
    assert i1["Sideways threats_duration"] == 2.0
    assert i1["Sideways threats_count"] == 1

    assert i2["Attack bites_duration"] == 2.0
    assert i2["Attack bites_count"] == 1
    assert i2["Sideways threats_duration"] == 2.0
    assert i2["Sideways threats_count"] == 1

    assert i3["Attack bites_duration"] == 0.0
    assert i3["Attack bites_count"] == 0
