"""Tests for AnalysisMetricsConfig slug uniqueness (BUG-013, 1.3.4)."""

from __future__ import annotations

import pytest

from models.analysis_config import AnalysisMetricsConfig


@pytest.fixture
def config():
    return AnalysisMetricsConfig()


def test_replace_metrics_rejects_cross_category_collision(config):
    latency = [{"name": "Shared Name", "behavior": "Attack bites", "enabled": True}]
    total = [{"name": "shared name", "behaviors": ["Attack bites"], "enabled": True}]

    with pytest.raises(ValueError):
        config.replace_metrics(latency, total)


def test_replace_metrics_rejects_case_and_trailing_space_variants(config):
    latency = [{"name": "Total Aggression", "behavior": "Attack bites", "enabled": True}]
    total = [{"name": "TOTAL AGGRESSION ", "behaviors": ["Chasing"], "enabled": True}]

    # Differ only by case and a trailing space -> same slug -> collision.
    with pytest.raises(ValueError):
        config.replace_metrics(latency, total)


def test_replace_metrics_accepts_distinct_names(config):
    latency = [{"name": "Attack Latency", "behavior": "Attack bites", "enabled": True}]
    total = [{"name": "Total Aggression", "behaviors": ["Attack bites"], "enabled": True}]

    config.replace_metrics(latency, total)
    assert len(config.get_latency_metrics()) == 1
    assert len(config.get_total_time_metrics()) == 1


def test_find_slug_collisions_empty_when_unique(config):
    assert config.find_slug_collisions(
        [{"name": "A", "behavior": "x"}],
        [{"name": "B", "behaviors": ["y"]}],
    ) == []
