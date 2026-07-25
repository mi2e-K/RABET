"""Tests for non-project auto-save filenames (1.4.2).

A shared auto-save folder collapses videos that share a basename across
folders onto one CSV name. The source folder is prefixed to keep them
distinguishable, but only when saving somewhere other than next to the video —
there the folder already does that job, and the historical name must not
change.
"""

from __future__ import annotations

import os

import pytest

from controllers.annotation_controller import AnnotationController


stem = AnnotationController._auto_save_stem
sanitize = AnnotationController._sanitize_path_segment


class _Dummy:
    """Stands in for the controller: _auto_save_stem only needs os.path."""

    _sanitize_path_segment = staticmethod(sanitize)


# --- Saving next to the video keeps the historical name ----------------


def test_saving_beside_the_video_is_unqualified():
    video = os.path.join("C:", os.sep, "data", "subject1", "trial.mp4")
    video_dir = os.path.dirname(video)

    assert stem(_Dummy(), video, video_dir, video_dir) == "trial"


def test_same_folder_written_differently_still_counts_as_beside():
    """A trailing separator or a relative form must not trigger the prefix."""
    video_dir = os.path.join("C:", os.sep, "data", "subject1")
    video = os.path.join(video_dir, "trial.mp4")

    assert stem(_Dummy(), video, video_dir + os.sep, video_dir) == "trial"


# --- A shared folder qualifies with the source folder ------------------


def test_shared_folder_prefixes_the_source_folder():
    shared = os.path.join("C:", os.sep, "annotations")
    a_dir = os.path.join("C:", os.sep, "data", "subject1")
    b_dir = os.path.join("C:", os.sep, "data", "subject2")

    a = stem(_Dummy(), os.path.join(a_dir, "trial.mp4"), shared, a_dir)
    b = stem(_Dummy(), os.path.join(b_dir, "trial.mp4"), shared, b_dir)

    assert a == "subject1_trial"
    assert b == "subject2_trial"
    # The collision this feature exists to prevent.
    assert a != b


def test_video_at_a_drive_root_falls_back_to_the_bare_name():
    """basename("D:\\") is empty, so there is no parent to qualify with."""
    root = "D:" + os.sep
    video = root + "trial.mp4"

    assert stem(_Dummy(), video, os.path.join("C:", os.sep, "out"), root) == "trial"


def test_dotted_video_name_keeps_only_the_extension_stripped():
    d = os.path.join("C:", os.sep, "data", "day1")
    video = os.path.join(d, "trial.v2.mp4")

    assert stem(_Dummy(), video, os.path.join("C:", os.sep, "out"), d) == "day1_trial.v2"


# --- Folder names unsafe for filenames ---------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("subject:1", "subject_1"),
        ('a"b', "a_b"),
        ("a|b?c*d", "a_b_c_d"),
        ("trailing. ", "trailing"),
        ("  ", ""),
    ],
)
def test_sanitize_removes_characters_windows_rejects(raw, expected):
    assert sanitize(raw) == expected


def test_sanitize_caps_length():
    assert len(sanitize("x" * 200)) == 64


def test_unsafe_folder_name_does_not_produce_an_invalid_filename():
    d = os.path.join("C:", os.sep, "data", "cond:A")
    result = stem(_Dummy(), os.path.join(d, "trial.mp4"),
                  os.path.join("C:", os.sep, "out"), d)

    assert result == "cond_A_trial"
    assert not any(c in result for c in '<>:"/\\|?*')
