"""Regressions in dialog clean-up and log access.

- the disagreement review stops its decode thread however it is closed
  (Esc / reject() end a dialog through done() without a closeEvent, and the
  running thread aborted the app at exit);
- the log viewer stops refreshing when it is dismissed the same way;
- reading the in-memory log takes the handler lock that emit() runs under.
"""

from __future__ import annotations

import threading

from models.reliability_model import DetailedAgreementResult
from utils.in_memory_log_handler import InMemoryLogHandler
from utils.log_manager import LogManager
from views.disagreement_review_view import DisagreementReviewDialog
from views.log_viewer_dialog import LogViewerDialog


def test_rejecting_the_disagreement_review_stops_its_video_thread(qt_app):
    result = DetailedAgreementResult(
        behaviors=["A"],
        events_a=[("A", 1.0, 2.0)],
        events_b=[("A", 1.2, 2.1)],
        test_duration_seconds=10.0,
    )
    dialog = DisagreementReviewDialog(result)
    try:
        assert dialog._video_model._thread.isRunning()
        dialog.reject()
        assert not dialog._video_model._thread.isRunning()
    finally:
        dialog._video_model.shutdown()
        dialog.deleteLater()


def test_rejecting_the_log_viewer_stops_refreshing(qt_app):
    dialog = LogViewerDialog(LogManager())
    try:
        assert dialog.refresh_timer.isActive()
        dialog.reject()
        assert not dialog.refresh_timer.isActive()
    finally:
        dialog.deleteLater()


def test_reading_the_log_waits_for_the_handler_lock():
    handler = InMemoryLogHandler()
    results = []
    handler.acquire()  # as emit() holds it while appending
    try:
        reader = threading.Thread(target=lambda: results.append(handler.get_logs()))
        reader.start()
        reader.join(0.2)
        assert reader.is_alive()  # blocked instead of iterating a mutating deque
    finally:
        handler.release()
    reader.join(2)
    assert results == [[]]
