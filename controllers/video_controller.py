# controllers/video_controller.py - Enhanced for reliable loading and improved state handling
import logging
import os
import platform
import time
from PySide6.QtCore import QObject, Slot, QTimer, QEventLoop
from PySide6.QtWidgets import QFileDialog, QProgressDialog, QApplication, QMessageBox

from utils.threaded_loader import ThreadedVideoLoader

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
        
        # Set up a timer to set window handle with a slight delay
        # This helps ensure the widget is fully initialized
        self._init_timer = QTimer(self)
        self._init_timer.setSingleShot(True)
        self._init_timer.timeout.connect(self._delayed_set_window_handle)
        self._init_timer.start(100)  # 100ms delay

        # VLC initialization stabilization timer
        self._vlc_stabilize_timer = QTimer(self)
        self._vlc_stabilize_timer.setSingleShot(True)
        self._vlc_stabilize_timer.timeout.connect(self._on_vlc_stabilized)
    
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
        
        # Ensure the view's loading overlay is shown
        self._view.show_loading_overlay(True)
        self._view.set_loading_progress(0)
        
        # Process events to update UI
        QApplication.processEvents()
    
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
            # Do not hide the loading overlay yet - wait for VLC to stabilize
            # Instead, update the message to indicate we're finalizing
            self._view.show_loading_overlay(True)
            self._view.loading_overlay.set_message("Initializing video player...")
            
            # Set the video window handle with a delay
            # This sequence is critical for proper VLC initialization
            QTimer.singleShot(300, self._set_window_handle)
            
            # Start the VLC stabilization timer - this gives VLC time to fully initialize
            # This is critical to prevent UI freezes
            self._vlc_stabilize_timer.start(1500)  # 1.5 second delay to ensure VLC is ready
            
            # Update UI with video info
            self._update_video_info()
        else:
            # If loading failed, hide the overlay
            self._view.show_loading_overlay(False)
            self._video_initializing = False
    
    def _on_vlc_stabilized(self):
        """
        Called when VLC is considered stabilized after initialization.
        This prevents premature interaction with the video.
        """
        self.logger.debug("VLC stabilization period complete")
        
        # Hide the loading overlay now that VLC is stable
        self._view.show_loading_overlay(False)
        
        # Clear the initialization flag
        self._video_initializing = False
        
        # Make a final refresh of the window to ensure proper display
        if self._video_model.is_playing():
            # If video is already playing, briefly pause and resume to ensure frame display
            was_playing = True
            self._video_model.pause()
        else:
            was_playing = False
            
        # Force a frame refresh
        self._video_model.refresh_frame()
        
        # Resume playback if it was playing
        if was_playing:
            QTimer.singleShot(200, self._video_model.play)
            
        # Process pending events
        QApplication.processEvents()
        
        # Reset focus to main window after loading completes
        # This ensures keyboard shortcuts work immediately after video loads
        main_window = self._view.window()
        if main_window:
            QTimer.singleShot(300, main_window.resetFocus)
    
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
    
    def _delayed_set_window_handle(self):
        """Set window handle after a short delay."""
        self.logger.debug("Setting window handle after initialization delay")
        self._set_window_handle()
    
    def _set_window_handle(self):
        """Set the window handle for VLC to embed video."""
        if self._video_model.media_player is None:
            self.logger.error("Cannot set window handle: media player not initialized")
            return False
            
        video_widget = self._view.get_video_frame()
        
        if video_widget is None:
            self.logger.error("Cannot set window handle: video frame widget not available")
            return False
        
        try:
            # Make sure widget is visible and ready
            if not video_widget.isVisible():
                self.logger.warning("Video widget is not visible yet")
                # Try again later
                QTimer.singleShot(500, self._set_window_handle)
                return False
            
            if not video_widget.winId():
                self.logger.warning("Video widget does not have a window ID yet")
                # Try again later
                QTimer.singleShot(500, self._set_window_handle)
                return False
            
            # Get the window handle
            win_id = int(video_widget.winId())
            
            # Use it in the model
            success = self._video_model.set_window_handle(win_id)
            
            if success:
                self.logger.info(f"Successfully set window handle: {win_id}")
            else:
                self.logger.error("Failed to set window handle in model")
            
            return success
        except Exception as e:
            self.logger.error(f"Error setting window handle: {str(e)}", exc_info=True)
            return False
    
    def _connect_model_signals(self):
        """Connect signals from the model."""
        self._video_model.playback_state_changed.connect(self._view.set_playing_state)
        self._video_model.position_changed.connect(self._view.set_position)
        self._video_model.duration_changed.connect(self._view.set_duration)
        # Get frame rate when video is loaded
        self._video_model.video_loaded.connect(self._update_frame_rate)
    
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
        self._view.volume_changed.connect(self._video_model.set_volume)
        
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
        Handle step forward request with improved frame handling.
        
        Args:
            time_ms (int): Time to step forward in milliseconds
        
        Returns:
            bool: True if successful, False otherwise
        """
        # Guard against overlapping operations
        if self._video_model is None or self._stepping_in_progress:
            return False
            
        # Set stepping flag
        self._stepping_in_progress = True
        
        try:
            # Get current position
            before_pos = self._video_model.get_position()
            
            # Make sure video is paused for frame stepping
            was_playing = self._video_model.is_playing()
            if was_playing:
                self._video_model.pause()
            
            # If this is a frame-by-frame step (small time value), use exact frame duration
            if time_ms <= 50:  # Assume this is a frame-by-frame step
                # Use the actual frame duration from the video if available
                if hasattr(self._video_model, '_frame_duration_ms') and self._video_model._frame_duration_ms > 0:
                    frame_duration = self._video_model._frame_duration_ms
                else:
                    frame_duration = 33  # Default ~30fps
                
                self.logger.debug(f"Frame-by-frame step forward using {frame_duration}ms")
                
                # Calculate target position precisely - ensure we step exactly one frame
                target_pos = before_pos + frame_duration
                
                # Perform the step with extra force refresh
                self._video_model.seek_with_retry(target_pos)
                
                # Force a frame refresh with a small delay to ensure VLC completes the seek
                QTimer.singleShot(50, self._force_refresh_frame)
            else:
                # Regular step with user-specified time
                # Ensure step size is reasonable (use a minimum of one frame duration)
                min_step = max(10, self._frame_duration_ms)
                time_ms = max(min_step, min(time_ms, 5000))
                
                # Calculate target position precisely (align to frame boundaries if possible)
                frames_to_move = max(1, round(time_ms / max(1, self._frame_duration_ms)))
                frame_aligned_step = frames_to_move * self._frame_duration_ms
                
                # Calculate a more precise target position
                target_pos = min(before_pos + frame_aligned_step, self._video_model.get_duration())
                
                self.logger.debug(f"Stepping forward from {before_pos}ms to {target_pos}ms "
                                f"({frames_to_move} frames, {frame_aligned_step}ms)")
                
                # Store position explicitly
                self._video_model._last_seek_position = target_pos
                
                # Use precision seeking
                self._video_model.seek_with_retry(target_pos)
            
            # Schedule finalization with a delay to ensure seek completes
            self._step_complete_timer.start(100)
            
            # Resume playback if it was playing before (with delay to ensure seek completes)
            if was_playing:
                QTimer.singleShot(250, self._video_model.play)
                
            return True
        except Exception as e:
            self.logger.error(f"Error in handle_step_forward: {str(e)}")
            self._stepping_in_progress = False
            return False
    
    def _force_refresh_frame(self):
        """Force a VLC frame refresh to fix display issues."""
        try:
            # The most reliable way to refresh is to use next_frame
            self._video_model.refresh_frame()
            
            # Log success
            self.logger.debug("Forced frame refresh")
        except Exception as e:
            self.logger.error(f"Error during forced frame refresh: {str(e)}")
        finally:
            # Ensure we release the operation lock
            # Set flag to false directly since this is a simple operation
            self._stepping_in_progress = False
    
    def _perform_multiple_forward_steps(self, total_ms):
        """
        Break a large step into multiple smaller steps for better precision.
        
        Args:
            total_ms (int): Total step size in milliseconds
        """
        # Calculate number of steps (use 100ms per step)
        step_size = 100
        num_steps = max(1, total_ms // step_size)
        
        self.logger.debug(f"Breaking {total_ms}ms step into {num_steps} steps of {step_size}ms each")
        
        # Store whether video was playing
        was_playing = self._video_model.is_playing()
        if was_playing:
            self._video_model.pause()
        
        # Perform first step immediately
        initial_pos = self._video_model.get_position()
        self._video_model.seek(initial_pos + step_size)
        
        # Schedule remaining steps with delays
        remaining_steps = num_steps - 1
        if remaining_steps > 0:
            QTimer.singleShot(50, lambda: self._continue_multiple_steps(remaining_steps, step_size, was_playing))
        else:
            # Only one step needed, finalize now
            QTimer.singleShot(100, self._finalize_step_operation)
            
            # Resume if needed
            if was_playing:
                QTimer.singleShot(150, self._video_model.play)
    
    def _continue_multiple_steps(self, steps_left, step_size, resume_playing):
        """
        Continue a multi-step operation.
        
        Args:
            steps_left (int): Number of steps remaining
            step_size (int): Size of each step in milliseconds
            resume_playing (bool): Whether to resume playback when done
        """
        if steps_left <= 0:
            # All steps complete, finalize
            self._finalize_step_operation()
            
            # Resume if needed
            if resume_playing:
                QTimer.singleShot(50, self._video_model.play)
            return
        
        # Get current position
        current_pos = self._video_model.get_position()
        
        # Perform next step
        self._video_model.seek(current_pos + step_size)
        
        # Schedule next step or finalization
        if steps_left > 1:
            QTimer.singleShot(50, lambda: self._continue_multiple_steps(steps_left - 1, step_size, resume_playing))
        else:
            # Last step, finalize
            QTimer.singleShot(100, self._finalize_step_operation)
            
            # Resume if needed
            if resume_playing:
                QTimer.singleShot(150, self._video_model.play)
    
    def handle_step_backward(self, time_ms=100):
        """
        Handle step backward request with improved frame handling.
        
        Args:
            time_ms (int): Time to step backward in milliseconds
        """
        # Guard against overlapping operations
        if self._stepping_in_progress or self._video_initializing:
            self.logger.debug("Step backward request ignored - operation in progress")
            return
            
        self._stepping_in_progress = True
        
        try:
            # Need to ensure we're using exact step size from UI
            actual_step_ms = time_ms
            
            # Use multiple steps for larger intervals to improve precision
            if actual_step_ms > 200:
                self.logger.debug(f"Breaking large step backward of {actual_step_ms}ms into multiple smaller steps")
                self._perform_multiple_backward_steps(actual_step_ms)
                return
            
            # Log the step operation
            self.logger.debug(f"Performing step backward of {actual_step_ms}ms")
            
            # Get current position
            before_pos = self._video_model.get_position()
            
            # Make sure video is paused for frame stepping
            was_playing = self._video_model.is_playing()
            if was_playing:
                self._video_model.pause()
            
            # Calculate target position precisely - ensure we don't go below 0
            target_pos = max(0, before_pos - actual_step_ms)
            
            # Perform the step
            self._video_model.seek(target_pos)
            
            # Schedule finalization with a delay to ensure seek completes
            self._step_complete_timer.start(100)
            
            # Resume playback if it was playing before
            if was_playing:
                QTimer.singleShot(200, self._video_model.play)
        except Exception as e:
            self.logger.error(f"Error in handle_step_backward: {str(e)}")
            self._stepping_in_progress = False
    
    def _perform_multiple_backward_steps(self, total_ms):
        """
        Break a large backward step into multiple smaller steps for better precision.
        
        Args:
            total_ms (int): Total step size in milliseconds
        """
        # Calculate number of steps (use 100ms per step)
        step_size = 100
        num_steps = max(1, total_ms // step_size)
        
        self.logger.debug(f"Breaking {total_ms}ms backward step into {num_steps} steps of {step_size}ms each")
        
        # Store whether video was playing
        was_playing = self._video_model.is_playing()
        if was_playing:
            self._video_model.pause()
        
        # Get starting position
        initial_pos = self._video_model.get_position()
        
        # For backward steps, we'll do a direct seek to the final position first
        target_pos = max(0, initial_pos - (num_steps * step_size))
        self._video_model.seek(target_pos)
        
        # Finalize after a delay to ensure seek completes
        self._step_complete_timer.start(150)
        
        # Resume if needed
        if was_playing:
            QTimer.singleShot(200, self._video_model.play)
    
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
            self._view, "Open Video", "", "Video Files (*.mp4 *.avi *.mkv *.mov *.wmv)"
        )
        
        if file_path:
            self.load_video(file_path)
    
    def load_video(self, file_path):
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
        
        # Check if loading is already in progress
        if self._loader.is_loading():
            self.logger.warning("Video loading already in progress")
            return False
        
        # Ensure the loading overlay is shown before starting the load
        self._view.show_loading_overlay(True)
        self._view.set_loading_progress(0)
        
        # Start loading in background thread
        return self._loader.load_video(file_path)