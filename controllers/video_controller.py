# controllers/video_controller.py - Enhanced for reliable loading and improved state handling
import logging
import os
from PySide6.QtCore import QObject, Slot, QTimer
from PySide6.QtWidgets import QFileDialog, QProgressDialog, QApplication, QMessageBox

from utils.threaded_loader import ThreadedVideoLoader
from utils.video_detection import is_video_file, video_file_dialog_filter

class VideoController(QObject):
    """
    Controller for video playback operations.
    """
    
    def __init__(self, video_model, video_player_view):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing VideoController")
        
        self._video_model = video_model
        self._view = video_player_view

        # Optional ConfigManager reference used for recent-files tracking.
        # AppController calls ``set_config_manager`` once construction is done.
        self.config_manager = None
        self.project_model = None

        # Create threaded loader
        self._loader = ThreadedVideoLoader(self._video_model)
        
        # Progress dialog for loading
        self._progress_dialog = None
        
        # Connect model signals
        self._connect_model_signals()
        
        # Connect view signals
        self._connect_view_signals()
        
        # Connect loader signals
        self._connect_loader_signals()
        
        # Flag to track ongoing step operations
        self._stepping_in_progress = False
        
        # Flag to track if video is currently being initialized
        self._video_initializing = False
        
        # Step operation complete timer
        self._step_complete_timer = QTimer(self)
        self._step_complete_timer.setSingleShot(True)
        self._step_complete_timer.timeout.connect(self._finalize_step_operation)

        # Frame rate info for better stepping
        self._frame_duration_ms = 40  # Default value, will be updated when video is loaded

        # NB: the legacy ``_init_timer`` and ``_vlc_stabilize_timer`` were
        # removed in 1.3.1. Under PyAV there's no native window handle to
        # plug into and no "wait for VLC to be ready" phase; the view
        # paints the frame directly when VideoModel emits ``frame_ready``.
    
    def _connect_loader_signals(self):
        """Connect signals from the video loader."""
        self._loader.loading_started.connect(self._on_loading_started)
        self._loader.loading_finished.connect(self._on_loading_finished)
        self._loader.loading_error.connect(self._on_loading_error)
        self._loader.loading_progress.connect(self._on_loading_progress)
    
    def _on_loading_started(self):
        """Handle video loading started."""
        self.logger.debug("Video loading started")
        
        # Set the video initialization flag
        self._video_initializing = True
        
        # Get parent widget for progress dialog
        parent = self._view.window()
        
        # Create progress dialog
        self._progress_dialog = QProgressDialog("Loading video...", "Cancel", 0, 100, parent)
        self._progress_dialog.setWindowTitle("Loading Video")
        self._progress_dialog.setModal(True)
        self._progress_dialog.setCancelButton(None)  # No cancel button
        self._progress_dialog.setMinimumDuration(300)  # Only show after 300ms
        self._progress_dialog.setAutoClose(True)
        self._progress_dialog.setAutoReset(True)
        
        # Ensure the view's loading overlay is shown. Qt's own event loop
        # will paint these widgets on the next dispatch; an explicit
        # ``processEvents`` here was redundant.
        self._view.show_loading_overlay(True)
        self._view.set_loading_progress(0)
    
    def _on_loading_progress(self, progress):
        """
        Handle video loading progress.
        
        Args:
            progress (int): Progress percentage (0-100)
        """
        if self._progress_dialog:
            self._progress_dialog.setValue(progress)
        
        # Forward progress to view's loading overlay
        self._view.set_loading_progress(progress)
        
        # Process events to update UI
        QApplication.processEvents()
    
    def _on_loading_finished(self, success):
        """
        Handle video loading finished.
        
        Args:
            success (bool): Whether loading was successful
        """
        self.logger.debug(f"Video loading finished: {success}")
        
        # Close progress dialog
        if self._progress_dialog:
            self._progress_dialog.setValue(100)
            self._progress_dialog = None
        
        # Set final progress 
        self._view.set_loading_progress(100)
        
        if success:
            # Record the freshly loaded file in the Recent Files menu.
            self._record_recent_video()

            # Update UI with video info
            self._update_video_info()

            # Hide the loading overlay immediately. Under VLC we had to
            # stall here for ~1.5s waiting for libvlc to stabilise its
            # native render surface; under PyAV the first frame has
            # already been decoded synchronously in ``load_video`` and
            # painted by the view, so the user is staring at the right
            # picture by this point.
            self._view.show_loading_overlay(False)
            self._video_initializing = False

            # Reset focus to main window so keyboard shortcuts work
            # immediately. (Previously this fired from _on_vlc_stabilized.)
            main_window = self._view.window()
            if main_window is not None and hasattr(main_window, "resetFocus"):
                QTimer.singleShot(50, main_window.resetFocus)
        else:
            # If loading failed, hide the overlay
            self._view.show_loading_overlay(False)
            self._video_initializing = False
    
    def _record_recent_video(self):
        """Append the current video path to the Recent Videos list."""
        if self.config_manager is None:
            return
        try:
            video_path = self._video_model._video_path
            if not video_path:
                return
            self.config_manager.add_recent_file('videos', video_path)
            self.config_manager.save_config()
        except Exception as exc:
            self.logger.warning(f"Failed to record recent video: {exc}")

    # NOTE: ``_on_vlc_stabilized`` was removed in 1.3.1. The PyAV backend
    # has no async stabilisation phase — the first frame is already
    # painted by the time ``_on_loading_finished`` runs.

    def _on_loading_error(self, error_message):
        """
        Handle video loading error.
        
        Args:
            error_message (str): Error message
        """
        self.logger.error(f"Video loading error: {error_message}")
        
        # Close progress dialog
        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None
        
        # Hide loading overlay
        self._view.show_loading_overlay(False)
        
        # Clear initialization flag
        self._video_initializing = False
        
        # Show error message
        if self._view and hasattr(self._view, 'window'):
            window = self._view.window()
            if window and hasattr(window, 'show_error'):
                window.show_error(f"Error loading video: {error_message}")
    
    def _update_video_info(self):
        """Update video information in the UI."""
        # Get video info
        duration_ms = self._video_model.get_duration()
        hours, remainder = divmod(duration_ms / 1000, 3600)
        minutes, seconds = divmod(remainder, 60)
        duration_str = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
        
        fps = self._video_model.get_frame_rate()
        fps_str = f"{fps:.2f} fps" if fps > 0 else "Unknown fps"
        
        file_name = os.path.basename(self._video_model._video_path)
        video_info = f"{file_name} | {duration_str} | {fps_str}"
        
        # Update video info if the view provides this method
        if hasattr(self._view, 'window') and hasattr(self._view.window(), 'set_video_info'):
            self._view.window().set_video_info(video_info)
        
        # Update frame rate info
        self._frame_duration_ms = int(1000 / max(1, fps)) if fps > 0 else 40
    
    # NOTE: the VLC window-handle plumbing (``_delayed_set_window_handle``,
    # ``_set_window_handle``, ``_prepare_embedded_video_surface``) was
    # removed in 1.3.1. Rendering happens through ``VideoModel.frame_ready
    # -> VideoPlayerView.display_frame`` (wired up in
    # ``_connect_model_signals`` below) so no platform-specific surface
    # handle ever needs to leave the GUI layer.

    def _connect_model_signals(self):
        """Connect signals from the model."""
        self._video_model.playback_state_changed.connect(self._view.set_playing_state)
        self._video_model.position_changed.connect(self._view.set_position)
        self._video_model.duration_changed.connect(self._view.set_duration)
        # Get frame rate when video is loaded
        self._video_model.video_loaded.connect(self._update_frame_rate)
        # NEW (1.3.1): decoded frames flow through this signal/slot pair.
        # The view paints the QImage into ``video_display_label`` — that
        # is the entirety of the render path.
        self._video_model.frame_ready.connect(self._view.display_frame)
    
    def _update_frame_rate(self, video_path):
        """Update frame rate info when a video is loaded."""
        # Get the frame rate from the model
        frame_rate = self._video_model.get_frame_rate()
        if frame_rate > 0:
            self._frame_duration_ms = int(1000 / frame_rate)
            self.logger.debug(f"Updated frame duration to {self._frame_duration_ms}ms based on {frame_rate} fps")
        else:
            # Default to 25fps if we can't determine frame rate
            self._frame_duration_ms = 40
            self.logger.debug(f"Using default frame duration of {self._frame_duration_ms}ms (25 fps)")
    
    def _finalize_step_operation(self):
        """Finalize a step operation after everything is complete."""
        if not self._stepping_in_progress:
            return

        # Update position to ensure UI is in sync
        position = self._video_model.get_position()
        self._view.set_position(position)

        self.logger.debug(f"Step operation finalized at position {position}ms")

        # Reset stepping flag
        self._stepping_in_progress = False

        # Notify annotation controller about final position
        main_window = self._view.window()
        if main_window and hasattr(main_window, 'annotation_controller'):
            main_window.annotation_controller.handle_seek(position)
    
    def _connect_view_signals(self):
        """Connect signals from the view."""
        # Connect play/pause signals
        self._view.play_clicked.connect(self._video_model.play)
        self._view.pause_clicked.connect(self._video_model.pause)
        
        # Connect other signals
        self._view.seek_requested.connect(self.handle_seek)
        self._view.step_forward_clicked.connect(self.handle_step_forward)
        self._view.step_backward_clicked.connect(self.handle_step_backward)
        self._view.rate_changed.connect(self._video_model.set_playback_rate)
        # NOTE (1.3.1): the legacy ``volume_changed`` connect was removed
        # together with the VLC backend. Audio is not played at all under
        # the PyAV backend, so there's no model-side volume API to wire
        # up. The view's volume slider is already hidden in setup_ui.

        # Connect drag and drop signal
        if hasattr(self._view, 'video_dropped'):
            self._view.video_dropped.connect(self.load_video)
    
    @Slot()
    def toggle_play_pause(self):
        """Toggle between play and pause."""
        # Don't allow toggling play/pause during video initialization
        if self._video_initializing:
            self.logger.debug("Ignoring play/pause toggle during video initialization")
            return
            
        if self._video_model.is_playing():
            self._video_model.pause()
        else:
            self._video_model.play()
    
    def handle_seek(self, position_ms):
        """
        Handle seek request by updating model and notifying annotation controller.
        
        Args:
            position_ms (int): Position in milliseconds to seek to
        """
        # Skip if a step operation is in progress or video is initializing
        if self._stepping_in_progress or self._video_initializing:
            self.logger.debug(f"Seek to {position_ms}ms ignored - operation in progress")
            return
            
        self.logger.debug(f"Handling seek to position: {position_ms}ms")
        
        # Update the model (which now handles frame refreshing internally)
        self._video_model.seek(position_ms)
        
        # Check if annotation controller is available (it will be set by app_controller)
        main_window = self._view.window()
        if main_window and hasattr(main_window, 'annotation_controller'):
            # Notify annotation controller about the seek operation
            main_window.annotation_controller.handle_seek(position_ms)
    
    def handle_step_forward(self, time_ms=100):
        """
        Handle step forward request — now a thin wrapper over the model.

        Under VLC this method had to align ``time_ms`` to frame boundaries,
        issue a precision seek, schedule a play/pause pulse to wake VLC's
        vout buffer, and manage retry timers. PyAV's ``step_forward`` is
        frame-accurate on first call, so we just forward the request and
        let the model emit ``frame_ready`` directly.

        Args:
            time_ms: target step size in ms. Values <= 50 are treated as
                "one frame" by the model.

        Returns:
            True on success.
        """
        if self._video_model is None or self._stepping_in_progress:
            return False
        self._stepping_in_progress = True
        try:
            self._video_model.step_forward(time_ms)
            return True
        except Exception as exc:
            self.logger.error(f"handle_step_forward failed: {exc}", exc_info=True)
            self._stepping_in_progress = False
            return False
        finally:
            # Finalise after a short delay so the view's position slider /
            # annotation_controller.handle_seek call still get a chance to
            # reflect the new ms. 50 ms is enough — the actual decode
            # already finished synchronously inside step_forward.
            self._step_complete_timer.start(50)

    def handle_step_backward(self, time_ms=100):
        """
        Handle step backward request — thin wrapper over the model.

        PyAV has no native "step back" instruction; the model emulates it
        by ``seek(current_ms - step_ms)`` which is frame-accurate, so the
        legacy VLC-era retry/pulse plumbing is gone.
        """
        if self._video_model is None or self._stepping_in_progress:
            return False
        self._stepping_in_progress = True
        try:
            self._video_model.step_backward(time_ms)
            return True
        except Exception as exc:
            self.logger.error(f"handle_step_backward failed: {exc}", exc_info=True)
            self._stepping_in_progress = False
            return False
        finally:
            self._step_complete_timer.start(50)
    
    @Slot()
    def open_video_dialog(self):
        """Open a file dialog to select a video file."""
        # Don't allow opening a new video during initialization
        if self._video_initializing:
            QMessageBox.information(
                self._view,
                "Video Loading",
                "Please wait until the current video finishes loading."
            )
            return
            
        file_path, _ = QFileDialog.getOpenFileName(
            self._view, "Open Video", "", video_file_dialog_filter()
        )

        if file_path:
            # When the user selects via "All Files", reject anything that
            # neither has a known extension, magic-number signature, nor
            # opens as a video container.
            if not is_video_file(file_path):
                QMessageBox.warning(
                    self._view,
                    "Unsupported file",
                    f"The selected file does not appear to be a video that "
                    f"RABET can decode:\n\n{file_path}",
                )
                return
            self.load_video(file_path)
    
    def _clear_annotation_project_context_for_regular_load(self):
        """Regular video loads must not reuse a stale Project-mode export path."""
        main_window = self._view.window()
        annotation_controller = getattr(main_window, "annotation_controller", None)
        if annotation_controller and hasattr(annotation_controller, "clear_project_context"):
            annotation_controller.clear_project_context()

    def _warn_on_project_same_name_conflict(self, file_path):
        """Block external loads that look like a different copy of a project video."""
        if self.project_model is None or not self.project_model.is_project_open():
            return False

        conflict = self.project_model.find_same_name_video_conflict(file_path)
        if not conflict:
            return False

        stored_video, expected_path = conflict
        QMessageBox.warning(
            self._view,
            "Project Video Name Conflict",
            "A video with the same filename is already managed by the open project, "
            "but the selected file is in a different location.\n\n"
            f"Selected file:\n{file_path}\n\n"
            f"Project video:\n{expected_path}\n\n"
            "To avoid loading the wrong annotations, open the video from the Project "
            "tab or add this file to the project with a unique filename.",
        )
        self.logger.warning(
            "Blocked external video load with same project filename: selected=%s project_ref=%s expected=%s",
            file_path,
            stored_video,
            expected_path,
        )
        return True

    def close_video(self):
        """Close the currently loaded video and reset the playback surface state."""
        try:
            self._video_initializing = False
            if self._progress_dialog:
                self._progress_dialog.close()
                self._progress_dialog = None

            # New VideoModel teardown:  ``close()`` releases the PyAV
            # container (frees the FFmpeg codec context, ~50MB on H264
            # 1080p) and resets the internal position/duration counters.
            # We follow up with explicit signal emissions so the view's
            # slider and label go back to 0 even though the new model
            # also emits ``duration_changed(0)`` from ``_close_container``.
            self._video_model.stop()
            self._video_model.close()
            self._video_model._video_path = None
            self._video_model._duration = 0
            self._video_model._last_seek_position = 0
            self._video_model.duration_changed.emit(0)
            self._video_model.position_changed.emit(0)

            self._view.show_loading_overlay(False)
            self._view.set_position(0)
            self._view.set_duration(0)

            main_window = self._view.window()
            if main_window and hasattr(main_window, "set_video_info"):
                main_window.set_video_info("")

            self.logger.info("Closed current video")
            return True
        except Exception as exc:
            self.logger.error(f"Failed to close video: {exc}", exc_info=True)
            return False

    def load_video(self, file_path, preserve_project_context=False):
        """
        Load a video file using the threaded loader.
        
        Args:
            file_path (str): Path to the video file
            
        Returns:
            bool: True if video loading started successfully, False otherwise
        """
        # Don't allow loading a new video during initialization
        if self._video_initializing:
            self.logger.warning("Ignoring video load request - already initializing a video")
            return False
            
        # Check if file exists
        if not os.path.exists(file_path):
            self.logger.error(f"Video file not found: {file_path}")
            return False

        if not preserve_project_context:
            if self._warn_on_project_same_name_conflict(file_path):
                return False
            self._clear_annotation_project_context_for_regular_load()

        # Check if loading is already in progress
        if self._loader.is_loading():
            self.logger.warning("Video loading already in progress")
            return False

        # 1.3.3+: notify the annotation controller BEFORE the loader
        # starts emitting position-changed signals. Without this the
        # loader's reset-to-position-0 would race against
        # ``_on_video_loaded`` and the "rewound past recording start"
        # dialog could fire on top of the loading overlay (Issue #2).
        # The annotation controller uses this hook to auto-stop any
        # in-progress recording and to set the one-shot
        # ``_skip_next_seek_rewind`` flag.
        main_window = self._view.window()
        annotation_controller = getattr(main_window, "annotation_controller", None)
        if annotation_controller is not None and hasattr(
            annotation_controller, "on_new_video_load_starting"
        ):
            try:
                annotation_controller.on_new_video_load_starting()
            except Exception:
                self.logger.exception(
                    "load_video: on_new_video_load_starting hook raised"
                )

        # Ensure the loading overlay is shown before starting the load
        self._view.show_loading_overlay(True)
        self._view.set_loading_progress(0)

        # 1.3.1 note: under VLC we had to pre-bind a window handle here
        # because libvlc would otherwise spawn a separate popup during the
        # brief play() it performs internally during load. PyAV doesn't
        # touch native windows at all (we paint frames via QLabel), so
        # the surface-prep step is gone.

        # Start loading in background thread
        return self._loader.load_video(file_path)
