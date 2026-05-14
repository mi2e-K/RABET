"""Tests for ``VideoModel`` audio-state preservation using a VLC mock."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def video_model(qt_app):
    """A VideoModel with its VLC media player replaced by a MagicMock.

    Building a real VLC ``MediaPlayer`` in tests is fragile (needs the VLC
    runtime, opens an audio device, etc.). We use ``MagicMock`` for the
    audio-related calls we want to assert against.
    """
    from models.video_model import VideoModel

    model = VideoModel()
    model.media_player = MagicMock()
    return model


def test_default_volume_state(video_model):
    """``_volume`` defaults to 80 with mute off, matching the docs."""
    assert video_model.get_volume() == 80
    assert video_model.is_muted() is False


def test_set_volume_persists_in_model(video_model):
    """``set_volume`` clamps + persists, and forwards to the player."""
    video_model.set_volume(30)
    assert video_model.get_volume() == 30
    video_model.media_player.audio_set_volume.assert_called_with(30)


def test_set_volume_clamps_to_valid_range(video_model):
    """Values outside 0-100 are clamped silently."""
    video_model.set_volume(-50)
    assert video_model.get_volume() == 0
    video_model.set_volume(250)
    assert video_model.get_volume() == 100


def test_set_volume_ignores_invalid_values(video_model):
    """Non-numeric input is rejected without changing state."""
    video_model.set_volume(50)
    video_model.set_volume("not a number")
    assert video_model.get_volume() == 50


def test_set_muted_round_trip(video_model):
    """Mute state is reflected back from the model and player."""
    video_model.set_muted(True)
    assert video_model.is_muted() is True
    video_model.media_player.audio_set_mute.assert_called_with(True)

    video_model.set_muted(False)
    assert video_model.is_muted() is False
