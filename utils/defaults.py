"""Centralised default values shared across RABET.

Several modules historically defined their own copy of the bundled
behaviour list and metric configuration. v1.2.1 collapses those copies
into this single module so future tweaks only have to land in one place.
"""
from __future__ import annotations


# Default key → behaviour mapping shipped with RABET. The set is tuned for
# rodent social-interaction studies but can be edited by users at runtime.
DEFAULT_ACTION_MAP: dict[str, str] = {
    "o": "Attack bites",
    "j": "Sideways threats",
    "p": "Tail rattles",
    "q": "Chasing",
    "a": "Social contact",
    "e": "Self-grooming",
    "t": "Locomotion",
    "r": "Rearing",
}


# Behaviours considered in the bundled latency-metric definitions. Each
# latency metric measures the time from the recording start to the first
# occurrence of ``behavior``.
DEFAULT_LATENCY_METRICS: list[dict] = [
    {
        "name": "Attack Latency",
        "behavior": "Attack bites",
        "enabled": True,
    },
]


# Total-time metrics aggregate the durations of several behaviours into a
# single composite value (overlap-aware). Names must remain unique because
# they double as column identifiers in the exported CSVs.
DEFAULT_TOTAL_TIME_METRICS: list[dict] = [
    {
        "name": "Total Aggression",
        "behaviors": ["Attack bites", "Sideways threats", "Tail rattles", "Chasing"],
        "enabled": True,
    },
    {
        "name": "Total Aggression(without tail-rattles)",
        "behaviors": ["Attack bites", "Sideways threats", "Chasing"],
        "enabled": True,
    },
]


# Default colour map for the bundled behaviours (used by the visualisation
# view's raster plots and by the JSON config that ships in ``configs/``).
DEFAULT_BEHAVIOR_COLORS: dict[str, str] = {
    "Attack bites":     "#FF4B00",
    "Sideways threats": "#F6AA00",
    "Tail rattles":     "#C9ACE6",
    "Chasing":          "#FF8082",
    "Social contact":   "#4DC4FF",
    "Self-grooming":    "#03AF7A",
    "Locomotion":       "#FFFFB2",
    "Rearing":          "#FFCABF",
}


def default_action_map() -> dict[str, str]:
    """Return a shallow copy of the default action map."""
    return dict(DEFAULT_ACTION_MAP)


def default_latency_metrics() -> list[dict]:
    """Return deep-copied default latency metric configurations."""
    return [dict(m) for m in DEFAULT_LATENCY_METRICS]


def default_total_time_metrics() -> list[dict]:
    """Return deep-copied default total-time metric configurations."""
    return [{**m, "behaviors": list(m["behaviors"])} for m in DEFAULT_TOTAL_TIME_METRICS]


def default_behavior_colors() -> dict[str, str]:
    """Return a shallow copy of the default behaviour colour map."""
    return dict(DEFAULT_BEHAVIOR_COLORS)
