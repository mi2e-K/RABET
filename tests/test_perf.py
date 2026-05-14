"""Performance benchmarks.

These tests are *informational*: they run under ``pytest-benchmark`` and
print timing statistics, but they do not have explicit assertions that
fail on regression. The intent is to record a "known-good" snapshot of
the v1.2.0 vectorised analysis paths so future changes can be compared
with ``pytest --benchmark-compare`` against the saved baseline.

Skip the suite cleanly when ``pytest-benchmark`` is not installed; that
way the rest of the test suite still works without the optional
dependency.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("pytest_benchmark")

from models.analysis_model import AnalysisModel


def _make_synthetic_events(n_events: int = 5000, *, seed: int = 1234) -> pd.DataFrame:
    """Generate a deterministic event DataFrame for benchmarking."""
    rng = np.random.default_rng(seed)
    onsets = np.sort(rng.uniform(0.0, 600.0, size=n_events))
    # Event durations 0.1 - 1.5 s
    durations = rng.uniform(0.1, 1.5, size=n_events)
    offsets = onsets + durations
    behaviors = rng.choice(
        ["Attack bites", "Sideways threats", "Tail rattles", "Chasing"],
        size=n_events,
    )

    df = pd.DataFrame({
        "Event": behaviors,
        "Onset": onsets,
        "Offset": offsets,
    })

    # Prepend a RecordingStart marker so interval analysis behaves naturally.
    rs = pd.DataFrame({"Event": ["RecordingStart"], "Onset": [0.0], "Offset": [0.0]})
    return pd.concat([rs, df], ignore_index=True)


@pytest.fixture(scope="module")
def synthetic_df():
    return _make_synthetic_events()


def test_calculate_total_aggression_perf(qt_app, benchmark, synthetic_df):
    model = AnalysisModel()
    behaviors = ["Attack bites", "Sideways threats", "Tail rattles", "Chasing"]
    result = benchmark(model._calculate_total_aggression, synthetic_df, behaviors)
    assert result > 0.0, "Aggression should aggregate to a positive duration"


def test_analyze_intervals_perf(qt_app, benchmark, synthetic_df):
    model = AnalysisModel()
    # 60-second intervals over a 10-minute fixture.
    model.set_interval_analysis(True, 60)
    result = benchmark(model._analyze_intervals, synthetic_df, 600)
    assert len(result) == 10
