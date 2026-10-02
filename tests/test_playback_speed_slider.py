"""The playback speed slider moves in 0.1x steps and its saved value is applied.

The slider counted hundredths (0.25x-2.00x): 176 values on about 116 mouse
positions, so values such as 0.50x could not be reached by dragging. A speed
restored at start-up only changed the slider; the decoder kept playing at 1.0x
until the slider was touched.
"""

from __future__ import annotations

import pytest

from views.main_window import MainWindow
from views.video_player_view import VideoPlayerView


class _FakeConfig:
    def __init__(self, sections):
        self._sections = sections
        self.saved = {}

    def get(self, section, key=None, default=None):
        values = self._sections.get(section, {})
        return values if key is None else values.get(key, default)

    def set(self, section, key, value):
        self.saved[(section, key)] = value

    def save_config(self):
        pass


def test_slider_moves_in_tenths(qt_app):
    view = VideoPlayerView()
    try:
        view._enable_controls()
        slider = view.rate_slider
        assert (slider.minimum(), slider.maximum(), slider.value()) == (2, 20, 10)
        assert slider.singleStep() == slider.pageStep() == 1

        rates = []
        view.rate_changed.connect(rates.append)
        slider.setValue(13)
        assert view.rate_value_label.text() == "1.3x"
        view.reset_playback_rate()
        assert (slider.value(), view.rate_value_label.text()) == (10, "1.0x")
        assert rates[0] == 1.3 and set(rates[1:]) == {1.0}
    finally:
        view.deleteLater()


@pytest.mark.parametrize(
    "saved, slider_value, label",
    [(0.5, 5, "0.5x"), (1.07, 11, "1.1x"), (0.25, 2, "0.2x"), (3.0, 20, "2.0x")],
)
def test_saved_speed_is_shown_and_applied(qt_app, saved, slider_value, label):
    win = MainWindow()
    try:
        vpv = win.video_player_view
        applied = []
        vpv.rate_changed.connect(applied.append)
        win.set_config_manager(_FakeConfig({"video": {"default_playback_rate": saved}}))
        assert vpv.rate_slider.value() == slider_value
        assert vpv.rate_value_label.text() == label
        assert applied == [slider_value / 10]   # reaches the decoder, not only the slider
    finally:
        win.set_close_guard(lambda: True)
        win.deleteLater()


def test_speed_is_saved_as_a_multiple(qt_app):
    win = MainWindow()
    try:
        config = _FakeConfig({})
        win.set_config_manager(config)
        win.video_player_view.rate_slider.setValue(13)
        win._persist_settings()
        assert config.saved[("video", "default_playback_rate")] == 1.3
    finally:
        win.set_close_guard(lambda: True)
        win.deleteLater()
