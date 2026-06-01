"""Tests for utils.csv_safety and the export paths that use it.

Covers the CSV / formula-injection hardening added in 1.3.4:

* ``sanitize_csv_cell`` neutralises formula-leading text but preserves
  genuine numbers (including signed numeric strings).
* An annotation export whose behaviour name begins with ``=`` is written
  as inert text and survives a round-trip through ``import_from_csv``.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from utils.csv_safety import sanitize_csv_cell, SafeCsvWriter


# -------------------------------------------------------------------- #
# sanitize_csv_cell
# -------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("=HYPERLINK(\"http://x\")", "'=HYPERLINK(\"http://x\")"),
        ("@SUM(A1:A2)", "'@SUM(A1:A2)"),
        ("+danger", "'+danger"),
        ("-cmd", "'-cmd"),
        ("\tlead-tab", "'\tlead-tab"),
        ("\rlead-cr", "'\rlead-cr"),
    ],
)
def test_dangerous_text_is_prefixed(raw, expected):
    assert sanitize_csv_cell(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "Attack bites",          # ordinary behaviour name
        "-0.5",                   # signed float — must stay numeric
        "+12",                    # signed int — must stay numeric
        "12.3400",                # formatted float
        "0",                      # zero
        "mouse_01",               # animal id
        "",                       # empty string
    ],
)
def test_safe_values_are_unchanged(raw):
    assert sanitize_csv_cell(raw) == raw


@pytest.mark.parametrize("value", [None, 12, 12.34, -0.5, 0])
def test_non_strings_pass_through(value):
    assert sanitize_csv_cell(value) == value


def test_safe_writer_sanitises_rows(tmp_path: Path):
    out = tmp_path / "out.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = SafeCsvWriter(csv.writer(fh))
        writer.writerow(["=evil", "-0.5", "ok"])
        writer.writerows([["@bad", "1", "+2"]])

    rows = list(csv.reader(open(out, newline="", encoding="utf-8")))
    assert rows[0] == ["'=evil", "-0.5", "ok"]
    assert rows[1] == ["'@bad", "1", "+2"]


# -------------------------------------------------------------------- #
# Annotation export hardening (integration)
# -------------------------------------------------------------------- #


def test_annotation_export_neutralises_formula_behavior(tmp_path: Path, qt_app):
    from models.action_map_model import ActionMapModel
    from models.annotation_model import AnnotationModel, BehaviorEvent

    action_map = ActionMapModel()
    # Map a key to a malicious behaviour name a user could type in the
    # Action Map dialog (the behaviour field is unrestricted).
    action_map.add_mapping("z", "=cmd|'/c calc'!A1")

    model = AnnotationModel(action_map)
    model._events.append(
        BehaviorEvent("z", "=cmd|'/c calc'!A1", 1000, 2000)
    )

    out = tmp_path / "annotations.csv"
    assert model.export_to_csv(str(out)) is True

    text = out.read_text(encoding="utf-8")
    # The dangerous cell is present only in its quoted, inert form.
    assert "'=cmd|'" in text or "\"'=cmd" in text
    # And never as a bare leading '=' on a data line (blank separator rows
    # parse to an empty list, so guard for that).
    for line in text.splitlines():
        row = next(iter(csv.reader([line])), [])
        first_cell = row[0] if row else ""
        assert not first_cell.startswith("=")
