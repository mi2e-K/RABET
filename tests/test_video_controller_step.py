"""VideoController frame-step completion via the worker's step_finished (A-1).

The step is closed by the worker's step_finished signal landing in
_on_step_finished; the 50ms->2000ms timer is only a fallback. If completion were
governed by a short timer (as it briefly was), key-repeat on "<<" queued steps
on the worker and kept rewinding after release. This test pins the signal path:
step_finished clears _stepping_in_progress on the reported position.
"""

from __future__ import annotations

import logging
import types

from controllers.video_controller import VideoController


def _bare_controller():
    vc = VideoController.__new__(VideoController)
    vc.logger = logging.getLogger("test.video_controller")
    vc._stepping_in_progress = True
    vc._video_model = types.SimpleNamespace(get_position=lambda: 1000)
    # window() -> None so _finalize_step_operation skips the annotation hop.
    vc._view = types.SimpleNamespace(set_position=lambda _p: None, window=lambda: None)
    return vc


def test_on_step_finished_clears_stepping_flag(qt_app):
    vc = _bare_controller()
    vc._on_step_finished(1234)
    assert vc._stepping_in_progress is False


def test_finalize_is_idempotent_when_not_stepping(qt_app):
    # A late fallback-timer finalize after step_finished already closed the step
    # must be a no-op (no crash, flag stays False).
    vc = _bare_controller()
    vc._stepping_in_progress = False
    vc._finalize_step_operation()  # fallback path, position=None
    assert vc._stepping_in_progress is False
