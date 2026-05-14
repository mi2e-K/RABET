import logging
from PySide6.QtCore import QObject, QTimer, Signal


class ThreadedVideoLoader(QObject):
    """
    Coordinates staged video loading while keeping VLC interactions on the
    owning Qt thread.

    VLC media objects and the timers owned by VideoModel are not thread-safe
    across Qt threads, so the actual load is executed on the model's thread.
    We still emit staged progress updates so the UI can remain responsive and
    communicate progress consistently.
    """

    loading_started = Signal()
    loading_finished = Signal(bool)
    loading_error = Signal(str)
    loading_progress = Signal(int)

    def __init__(self, video_model):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self._video_model = video_model
        self._pending_video_path = None
        self._is_loading = False
        self._abort = False

    def is_loading(self):
        """Check if a loading operation is in progress."""
        return self._is_loading

    def load_video(self, video_path):
        """
        Start a staged load sequence for a video file.

        Args:
            video_path (str): Path to the video file

        Returns:
            bool: True if loading started successfully, False otherwise
        """
        if self._is_loading:
            self.logger.warning("Ignoring load request - already loading a video")
            return False

        self.logger.info(f"Starting safe video loading sequence: {video_path}")
        self._pending_video_path = video_path
        self._is_loading = True
        self._abort = False

        self.loading_started.emit()
        QTimer.singleShot(0, self._emit_initial_progress)
        return True

    def abort_loading(self):
        """Abort the current loading operation."""
        if not self._is_loading:
            return

        self.logger.info("Aborting video loading")
        self._abort = True

    def _emit_initial_progress(self):
        if not self._can_continue():
            return

        self.loading_progress.emit(20)
        QTimer.singleShot(50, self._emit_parse_progress)

    def _emit_parse_progress(self):
        if not self._can_continue():
            return

        self.loading_progress.emit(40)
        QTimer.singleShot(50, self._perform_load)

    def _perform_load(self):
        if not self._can_continue():
            return

        self.loading_progress.emit(60)
        video_path = self._pending_video_path

        try:
            success = self._video_model.load_video(video_path)
        except Exception as exc:
            error_message = f"Failed to load video: {exc}"
            self.logger.error(error_message, exc_info=True)
            self.loading_error.emit(error_message)
            self._finalize(False)
            return

        if not success:
            self.loading_error.emit(f"Failed to load video: {video_path}")
            self._finalize(False)
            return

        self.loading_progress.emit(80)
        QTimer.singleShot(0, self._complete_success)

    def _complete_success(self):
        if not self._can_continue():
            return

        self.loading_progress.emit(100)
        self._finalize(True)

    def _can_continue(self):
        if not self._is_loading:
            return False

        if self._abort:
            self._finalize(False)
            return False

        if not self._pending_video_path:
            self.loading_error.emit("No video path specified")
            self._finalize(False)
            return False

        return True

    def _finalize(self, success):
        if not self._is_loading:
            return

        self.logger.info(f"Video loading finished (success: {success})")
        self._pending_video_path = None
        self._is_loading = False
        self._abort = False
        self.loading_finished.emit(success)
