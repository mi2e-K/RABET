# controllers/annotation_controller.py - Improved state tracking and synchronization
import logging
import os
import time
from PySide6.QtCore import QObject, QTimer, Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox
from utils.auto_close_message import AutoCloseMessageBox

class AnnotationController(QObject):
    """
    Controller for behavior annotations.
    """
    
    def __init__(self, annotation_model, video_model, main_window, timeline_view):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing AnnotationController")
        
        self._annotation_model = annotation_model
        self._video_model = video_model
        self._main_window = main_window
        self._timeline_view = timeline_view
        
        # Timer for timed recording
        self._recording_timer = QTimer(self)
        self._recording_timer.setInterval(100)  # Update more frequently (every 100ms)
        self._recording_timer.timeout.connect(self._update_recording_time)
        
        # Recording state
        self._is_recording = False
        self._recording_duration = 0  # Total duration of recording session in seconds
        self._recording_start_position = 0  # Video position when recording started
        self._is_recording_paused = False
        self._last_position = 0  # Track position for detecting rewinds
        
        # Flag to skip auto-export when explicitly resetting
        self._skip_auto_export = False
        
        # Toggle for preserving annotations on rewind (default: False - delete annotations)
        self._preserve_annotations_on_rewind = False
        
        # Last loaded video path
        self._current_video_path = None
        
        # Key press tracking with high-precision system time
        self._key_press_times = {}  # Key -> (timestamp, system_time)
        
        # State synchronization flags
        self._synchronizing_states = False
        self._state_sync_timer = QTimer(self)
        self._state_sync_timer.setInterval(100)  # Check every 100ms
        self._state_sync_timer.setSingleShot(True)
        self._state_sync_timer.timeout.connect(self._complete_state_synchronization)
        
        # Get frame duration in milliseconds
        self._frame_duration_ms = self._get_frame_duration()
        
        # Project mode support
        self._project_mode = False
        self._project_model = None
        self._current_video_id = None
        self._auto_export_path = None
        
        # Connect signals
        self._connect_signals()
    
    def _get_frame_duration(self):
        """Get the frame duration in milliseconds, with a reasonable default."""
        if hasattr(self._video_model, '_frame_duration_ms'):
            return self._video_model._frame_duration_ms
        return 33  # Default ~30fps (33ms per frame)
    
    def _connect_signals(self):
        """Connect signals between models and views."""
        # Connect keyboard events
        self._main_window.key_pressed.connect(self.on_key_pressed)
        self._main_window.key_released.connect(self.on_key_released)
        
        # Connect video model signals
        self._video_model.position_changed.connect(self.on_position_changed)
        self._video_model.duration_changed.connect(self._timeline_view.set_duration)
        self._video_model.video_loaded.connect(self._on_video_loaded)
        self._video_model.playback_state_changed.connect(self._on_playback_state_changed)
        
        # Connect annotation model signals
        self._annotation_model.annotation_added.connect(self.on_annotation_added)
        self._annotation_model.annotation_updated.connect(self.on_annotation_updated)
        self._annotation_model.annotation_removed.connect(self.on_annotation_removed)
        self._annotation_model.annotations_cleared.connect(self.on_annotations_cleared)
        self._annotation_model.active_events_changed.connect(self.on_active_events_changed)
        
        # Connect recording control view signals
        recording_control_view = self._main_window.recording_control_view
        recording_control_view.timed_recording_requested.connect(self.start_timed_recording)
        recording_control_view.timed_recording_canceled.connect(self.stop_timed_recording)
        recording_control_view.preserve_annotations_changed.connect(self.set_preserve_annotations)
    
    # Project mode methods
    def set_project_mode(self, enabled):
        """
        Enable or disable project mode.
        
        Args:
            enabled (bool): Whether project mode is enabled
        """
        self._project_mode = enabled
        self.logger.info(f"Project mode {'enabled' if enabled else 'disabled'}")
    
    def set_project_model(self, project_model):
        """
        Set the project model for integration.
        
        Args:
            project_model: Project model reference
        """
        self._project_model = project_model
        self.logger.debug("Project model set for annotation controller")
    
    def set_current_video_id(self, video_id):
        """
        Set the ID of the current video being annotated.
        
        Args:
            video_id (str): ID of the video (basename without extension)
        """
        self._current_video_id = video_id
        self.logger.info(f"Set current video ID: {video_id}")
    
    def set_auto_export_path(self, export_path):
        """
        Set the path for automatic export of annotations.
        
        Args:
            export_path (str): Path to export annotations to
        """
        self._auto_export_path = export_path
        self.logger.info(f"Set auto export path: {export_path}")
    
    def set_preserve_annotations(self, enabled):
        """
        Set whether to preserve annotations on rewind.
        
        Args:
            enabled (bool): Whether to preserve annotations on rewind
        """
        self._preserve_annotations_on_rewind = enabled
        self.logger.info(f"Preserve annotations on rewind: {enabled}")
    
    @Slot(bool)
    def _on_playback_state_changed(self, is_playing):
        """
        Handle changes in video playback state.
        This ensures recording state is properly synchronized with playback.
        
        Args:
            is_playing (bool): Whether video is now playing
        """
        # Skip if we're in the process of synchronizing states
        if self._synchronizing_states:
            return
            
        self.logger.debug(f"Video playback state changed: is_playing={is_playing}")
        
        # Only perform sync if recording is active
        if self._is_recording:
            self._synchronizing_states = True
            
            try:
                # If video is playing but recording is paused, resume recording
                if is_playing and self._is_recording_paused:
                    self.logger.debug("Auto-resuming recording to match video play state")
                    self.resume_recording()
                
                # If video is paused but recording is active, pause recording
                elif not is_playing and not self._is_recording_paused:
                    self.logger.debug("Auto-pausing recording to match video pause state")
                    self.pause_recording()
            except Exception as e:
                self.logger.error(f"Error during state synchronization: {str(e)}")
            
            # Schedule completion of state sync
            self._state_sync_timer.start()
    
    def _complete_state_synchronization(self):
        """Complete state synchronization process."""
        self._synchronizing_states = False
        self.logger.debug("State synchronization complete")
    
    @Slot(int)
    def on_position_changed(self, position):
        """
        Handle video position changed event.
        
        Args:
            position (int): New position in milliseconds
        """
        # Update timeline view
        self._timeline_view.set_position(position)
        
        # Check for rewind during any recording state (paused or active)
        if self._is_recording:
            # If position changed backward (rewind operation)
            # Use a smaller threshold (100ms) to catch more rewind operations
            if self._last_position - position > 100:
                self.logger.debug(f"Rewind detected: {self._last_position}ms -> {position}ms")
                
                # Only remove annotations if preservation is not enabled
                if not self._preserve_annotations_on_rewind:
                    self.remove_future_annotations(position)
        
        # Update last position
        self._last_position = position
        
        # If there are active events, we need to update the timeline to reflect
        # the current position as the temporary end point
        if self._annotation_model.get_active_events() and self._is_recording and not self._is_recording_paused:
            self._timeline_view.set_events(self._annotation_model.get_all_events_with_active())
        
        # If we're recording but not paused, update recording time
        if self._is_recording and not self._is_recording_paused:
            self._update_recording_time_display()
    
    def remove_future_annotations(self, current_position=None):
        """
        Remove annotations that occur after or overlap with the current video position.
        Called after rewinding during recording session.
        
        Args:
            current_position (int, optional): Position to use as cutoff. 
                                             If None, use current video position.
        
        Returns:
            bool: True if session was reset, False otherwise
        """
        if not self._is_recording:
            return False
        
        if current_position is None:
            current_position = self._video_model.get_position()
        
        events = self._annotation_model.get_all_events()
        
        # Identify annotations that occur after or overlap with the current position
        future_annotations = []
        annotations_to_truncate = []
        recording_start_index = None
        recording_start_event = None
        
        for i, event in enumerate(events):
            # Check for RecordingStart event
            if event.behavior == "RecordingStart":
                recording_start_index = i
                recording_start_event = event
                continue
                
            # Case 1: Annotation starts after current position - remove completely
            if event.onset > current_position:
                future_annotations.append(i)
                
            # Case 2: Annotation starts before but extends past current position - truncate it
            elif event.offset is not None and event.offset > current_position:
                annotations_to_truncate.append((i, event))
        
        # Check if we've rewound past the recording start point
        if recording_start_event and current_position < recording_start_event.onset:
            # Prompt user for decision about resetting the entire recording session
            from PySide6.QtWidgets import QMessageBox
            
            # Create a custom dialog with larger text
            dialog = QMessageBox(self._main_window)
            dialog.setWindowTitle("Reset Recording Session")  # Simple title
            dialog.setIcon(QMessageBox.Icon.Warning)
            
            # Use HTML formatting for larger text with line wrapping
            dialog.setText("<span style='font-size: 12pt;'>You have rewound before the recording start point. Would you like to reset the entire recording session?</span>")
            
            dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            dialog.setDefaultButton(QMessageBox.StandardButton.No)
            
            result = dialog.exec()
            
            if result == QMessageBox.StandardButton.Yes:
                # Stop the current recording and clear all annotations
                self.logger.info("User chose to reset recording session after rewinding past start point")
                # Set flag to skip auto-export when stopping recording
                self._skip_auto_export = True
                self.stop_timed_recording()
                self._annotation_model.clear_events()
                
                # Provide feedback to the user
                self._main_window.set_status_message("Recording session reset. Press 'Start Recording' to begin a new session.")
                
                # Update the timeline
                self._timeline_view.set_events([])
                
                # Update project status if in project mode
                if self._project_mode and self._project_model and self._current_video_id:
                    self._project_model.set_video_annotation_status(self._current_video_id, "not_annotated")
                
                return True
            else:
                self.logger.info("User chose to continue recording after rewinding past start point")
                # Continue with normal annotation removal based on the preserve toggle
        
        # Only proceed with annotation removal if preservation is not enabled
        if self._preserve_annotations_on_rewind:
            self.logger.debug("Annotations preserved on rewind (toggle enabled)")
            return False
            
        # First truncate annotations that overlap with the current position
        truncated_count = 0
        for i, event in annotations_to_truncate:
            # Create a copy of the event with updated offset
            from models.annotation_model import BehaviorEvent
            truncated_event = BehaviorEvent(
                event.key,
                event.behavior,
                event.onset,
                current_position,  # Truncate to current position
                event.system_onset_time,
                time.time()  # New system time for offset
            )
            
            # Replace the old event with the truncated one
            if self._annotation_model.update_event(i, offset=current_position):
                truncated_count += 1
                self.logger.debug(f"Truncated event {event.behavior} at position {current_position}ms")
        
        # Then remove annotations that start after the current position
        # This needs to be done in reverse order to maintain valid indices
        removed_count = 0
        for index in sorted(future_annotations, reverse=True):
            if self._annotation_model.remove_event(index):
                removed_count += 1
        
        total_affected = removed_count + truncated_count
        if total_affected > 0:
            status_msg = f"Removed {removed_count} and truncated {truncated_count} annotation(s) after rewinding"
            self._main_window.set_status_message(status_msg)
            self.logger.info(
                f"After rewinding to {current_position}ms: " +
                f"Removed {removed_count} and truncated {truncated_count} annotations"
            )
            
            # Update timeline to reflect the changes
            self._timeline_view.set_events(self._annotation_model.get_all_events())
            
            # Update project status if annotations were affected
            if self._project_mode and self._project_model and self._current_video_id:
                # If no annotations remain, mark as not annotated
                if not self._annotation_model.get_all_events():
                    self._project_model.set_video_annotation_status(self._current_video_id, "not_annotated")
                
        return False
    
    @Slot(str)
    def _on_video_loaded(self, video_path):
        """
        Handle video loaded event.
        
        Args:
            video_path (str): Path to the loaded video
        """
        self._current_video_path = video_path
        self._last_position = 0
        self.logger.debug(f"Video loaded: {video_path}")
        
        # In project mode, try to load existing annotations
        if self._project_mode and self._auto_export_path and os.path.exists(self._auto_export_path):
            # Ask if user wants to load existing annotations
            result = QMessageBox.question(
                self._main_window,
                "Existing Annotations",
                f"Existing annotations found for this video. Load them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if result == QMessageBox.StandardButton.Yes:
                # Clear existing annotations first
                self._annotation_model.clear_events()
                # Import existing annotations
                self._annotation_model.import_from_csv(self._auto_export_path)
                self.logger.info(f"Loaded existing annotations from {self._auto_export_path}")
                
                # Update timeline
                self._timeline_view.set_events(self._annotation_model.get_all_events())
            else:
                # New feature: Clear existing annotations when a new video is loaded
                self.logger.info("Clearing existing annotations due to new video load")
                self._annotation_model.clear_events()
                self._main_window.set_status_message("Annotations cleared for new video")
        else:
            # New feature: Clear existing annotations when a new video is loaded
            if self._annotation_model.get_all_events():
                self.logger.info("Clearing existing annotations due to new video load")
                self._annotation_model.clear_events()
                self._main_window.set_status_message("Annotations cleared for new video")
        
        # Update frame duration based on the loaded video
        if hasattr(self._video_model, '_frame_duration_ms'):
            self._frame_duration_ms = self._video_model._frame_duration_ms
            self.logger.debug(f"Updated frame duration to {self._frame_duration_ms}ms based on loaded video")
    
    @Slot(str)
    def on_key_pressed(self, key):
        """
        Handle key press event.
        
        Args:
            key (str): Key character
        """
        # Only process if video is loaded and playing, and recording is active and not paused
        if not self._video_model.is_playing() or not self._is_recording or self._is_recording_paused:
            return
        
        # Get current video position and system time
        position = self._video_model.get_position()
        system_time = time.time()
        
        # Store both position and system time
        self._key_press_times[key] = (position, system_time)
        
        # Start event in annotation model
        if self._annotation_model.start_event(key, position):
            self.logger.debug(f"Started event for key {key} at {position}ms (system time: {system_time:.6f})")
            # Update timeline to show active event
            self._timeline_view.set_events(self._annotation_model.get_all_events_with_active())
    
    @Slot(str)
    def on_key_released(self, key):
        """
        Handle key release event.
        
        Args:
            key (str): Key character
        """
        # Only process if video is loaded and recording is active and not paused
        if self._video_model.get_duration() == 0 or not self._is_recording or self._is_recording_paused:
            return
        
        # Get current video position and system time
        current_position = self._video_model.get_position()
        current_system_time = time.time()
        
        # Check if we have a stored press time for this key
        if key not in self._key_press_times:
            self.logger.warning(f"No key press recorded for key {key}")
            return
            
        # Get the stored position and system time
        press_position, press_system_time = self._key_press_times[key]
        
        # Calculate system time duration in milliseconds
        system_duration_ms = int((current_system_time - press_system_time) * 1000)
        
        # Ensure minimum duration of one frame
        if system_duration_ms < self._frame_duration_ms or current_position <= press_position:
            # Calculate offset by adding at least one frame duration to onset
            adjusted_position = press_position + self._frame_duration_ms
            self.logger.debug(f"Enforcing minimum duration for key {key}: {system_duration_ms}ms -> {self._frame_duration_ms}ms")
            current_position = adjusted_position
        
        # End event in annotation model with the adjusted position if needed
        if self._annotation_model.end_event(key, current_position):
            self.logger.debug(f"Ended event for key {key} at {current_position}ms (system duration: {system_duration_ms}ms)")
            # Remove from tracked keys
            del self._key_press_times[key]
            
            # Update project status if in project mode
            if self._project_mode and self._project_model and self._current_video_id:
                # Mark video as annotated
                self._project_model.set_video_annotation_status(self._current_video_id, "annotated")
    
    @Slot(object)
    def on_annotation_added(self, event):
        """
        Handle new annotation event.
        
        Args:
            event (BehaviorEvent): New behavior event
        """
        # Update timeline with all events including active ones
        self._timeline_view.set_events(self._annotation_model.get_all_events_with_active())
        
        # Update status message
        behavior = event.behavior
        duration = event.duration / 1000.0  # Convert to seconds
        self._main_window.set_status_message(f"Added: {behavior} ({duration:.2f}s)")
        
        # Update project status if in project mode and not a RecordingStart event
        if self._project_mode and self._project_model and self._current_video_id and behavior != "RecordingStart":
            # Mark video as annotated
            self._project_model.set_video_annotation_status(self._current_video_id, "annotated")
    
    @Slot()
    def on_active_events_changed(self):
        """Handle changes to active events."""
        # Update timeline with all events including active ones
        self._timeline_view.set_events(self._annotation_model.get_all_events_with_active())
        self.logger.debug("Timeline updated with active events")
    
    @Slot(object)
    def on_annotation_updated(self, event):
        """
        Handle updated annotation event.
        
        Args:
            event (BehaviorEvent): Updated behavior event
        """
        # Update timeline with all events including active ones
        self._timeline_view.set_events(self._annotation_model.get_all_events_with_active())
        
        # Update status message
        behavior = event.behavior
        duration = event.duration / 1000.0  # Convert to seconds
        self._main_window.set_status_message(f"Updated: {behavior} ({duration:.2f}s)")
    
    @Slot(int)
    def on_annotation_removed(self, index):
        """
        Handle removed annotation event.
        
        Args:
            index (int): Index of removed event
        """
        # Update timeline with all events including active ones
        self._timeline_view.set_events(self._annotation_model.get_all_events_with_active())
        
        # Update status message
        self._main_window.set_status_message(f"Removed annotation at index {index}")
        
        # If no annotations remain and we're in project mode, update status
        if self._project_mode and self._project_model and self._current_video_id:
            # If no annotations remain (except RecordingStart), mark as not annotated
            events = self._annotation_model.get_all_events()
            has_annotations = False
            for evt in events:
                if evt.behavior != "RecordingStart":
                    has_annotations = True
                    break
                    
            if not has_annotations:
                self._project_model.set_video_annotation_status(self._current_video_id, "not_annotated")
    
    @Slot()
    def on_annotations_cleared(self):
        """Handle cleared annotations."""
        # Update timeline to remove all events
        self._timeline_view.set_events([])
        
        # Update status message
        self._main_window.set_status_message("All annotations cleared")
        
        # Update project status if in project mode
        if self._project_mode and self._project_model and self._current_video_id:
            # Mark video as not annotated
            self._project_model.set_video_annotation_status(self._current_video_id, "not_annotated")
    
    @Slot(int)
    def start_timed_recording(self, duration_seconds):
        """
        Start a timed annotation recording session.
        
        Args:
            duration_seconds (int): Duration of the recording in seconds
        """
        # Check if video is loaded
        if self._video_model.get_duration() == 0:
            self._main_window.show_error("No video loaded. Please load a video before starting recording.")
            self._main_window.recording_control_view.set_idle_state()
            return
        
        # Store recording parameters
        self._recording_duration = duration_seconds
        self._is_recording = True
        self._is_recording_paused = False
        
        # Get starting position from video
        self._recording_start_position = self._video_model.get_position()
        self._last_position = self._recording_start_position
        
        # Clear any existing key press times
        self._key_press_times = {}
        
        # Start timer for UI updates
        self._recording_timer.start()
        
        # Start video playback if not already playing
        if not self._video_model.is_playing():
            self._video_model.play()
        
        # Add "RecordingStart" event with same onset and offset
        from models.annotation_model import BehaviorEvent
        recording_start_event = BehaviorEvent("R", "RecordingStart", 
                                             self._recording_start_position,
                                             self._recording_start_position)
        self._annotation_model.add_recording_start_event(recording_start_event)
        
        # Set the test duration in the annotation model (new)
        self._annotation_model.set_test_duration(duration_seconds)
        
        # Update UI
        self._main_window.set_status_message(f"Recording started. Duration: {duration_seconds} seconds")
        self.logger.info(f"Started timed recording for {duration_seconds} seconds")
        
        # Initial update of recording time display
        self._update_recording_time_display()
    
    @Slot()
    def stop_timed_recording(self):
        """Stop the current timed recording session."""
        if self._is_recording:
            self._is_recording = False
            self._is_recording_paused = False
            self._recording_timer.stop()
            
            # End any active events
            for key, (position, _) in list(self._key_press_times.items()):
                # Calculate a reasonable offset with minimum duration
                current_position = self._video_model.get_position()
                if current_position <= position:
                    current_position = position + self._frame_duration_ms
                
                # End the event
                self._annotation_model.end_event(key, current_position)
            
            # Clear key press times
            self._key_press_times = {}
            
            # Update UI
            self._main_window.set_status_message("Recording stopped manually")
            self._main_window.recording_control_view.set_idle_state()
            self.logger.info("Recording stopped manually")
            
            # Automatically export annotations if we have a video path
            # and auto-export hasn't been skipped and we're in project mode
            if self._current_video_path and not self._skip_auto_export and self._project_mode and self._auto_export_path:
                self._auto_export_annotations()
            
            # Reset the skip flag
            self._skip_auto_export = False
    
    def pause_recording(self):
        """Pause the current recording."""
        # Skip if already paused or not recording
        if not self._is_recording or self._is_recording_paused:
            return
        
        self.logger.debug("Pausing recording...")
            
        # Pause timer
        self._recording_timer.stop()
        self._is_recording_paused = True
        
        # Update UI in recording control view
        self._main_window.recording_control_view.set_paused_state()
        
        # Update status message
        self._main_window.set_status_message("Recording paused")
        
        # Store current position for rewinding detection
        self._last_position = self._video_model.get_position()
        
        # End any active events
        for key, (position, _) in list(self._key_press_times.items()):
            # Calculate a reasonable offset with minimum duration
            current_position = self._video_model.get_position()
            if current_position <= position:
                current_position = position + self._frame_duration_ms
                
            # End the event
            self._annotation_model.end_event(key, current_position)
        
        # Clear key press times for the paused state
        self._key_press_times = {}
        
        self.logger.info("Recording paused")
    
    def resume_recording(self):
        """Resume the paused recording."""
        # Skip if not paused or not recording
        if not self._is_recording or not self._is_recording_paused:
            return
            
        self.logger.debug("Resuming recording...")
            
        # Resume timer
        self._recording_timer.start()
        self._is_recording_paused = False
        
        # Update UI in recording control view
        self._main_window.recording_control_view.resume_recording()
        
        # Update status message
        self._main_window.set_status_message("Recording resumed")
        
        self.logger.info("Recording resumed")
    
    def handle_seek(self, position):
        """
        Handle seek operation.
        
        Args:
            position (int): New position in milliseconds
        """
        # Check for rewind in any recording state (paused or active)
        if self._is_recording:
            if self._last_position > position:
                # This is a rewind operation
                self.logger.debug(f"Seek rewind detected: {self._last_position}ms -> {position}ms")
                
                # Find the recording start position to check if we've rewound before it
                recording_start_position = None
                events = self._annotation_model.get_all_events()
                for event in events:
                    if event.behavior == "RecordingStart":
                        recording_start_position = event.onset
                        break
                
                # If we've rewound before the recording start, handle specially
                if recording_start_position is not None and position < recording_start_position:
                    self.logger.debug(f"Rewound before recording start point: {recording_start_position}ms -> {position}ms")
                    # The confirmation and reset will be handled in remove_future_annotations
                
                # Only remove annotations if preservation is not enabled
                if not self._preserve_annotations_on_rewind:
                    self.remove_future_annotations(position)
        
        # Update last position
        self._last_position = position
        
        # If recording is active, update the time display
        if self._is_recording:
            self._update_recording_time_display()
    
    def is_recording_paused(self):
        """
        Check if recording is paused.
        
        Returns:
            bool: True if recording is paused, False otherwise
        """
        return self._is_recording and self._is_recording_paused
    
    def _update_recording_time_display(self):
        """
        Update the recording time display based on video position.
        This is now called both by the timer and when the video position changes.
        """
        if not self._is_recording:
            return
        
        # Get current position
        current_position = self._video_model.get_position()
        
        # Calculate elapsed time in seconds, based on video position, not wall clock
        elapsed_seconds = (current_position - self._recording_start_position) / 1000
        
        # Calculate remaining time based on elapsed time
        remaining_seconds = max(0, self._recording_duration - elapsed_seconds)
        
        # Update progress in view
        self._main_window.recording_control_view.update_progress(int(remaining_seconds))
        
        # Check if recording should stop
        if remaining_seconds <= 0 and self._is_recording:
            self._complete_recording()
    
    def _update_recording_time(self):
        """
        Timer callback to update recording time.
        Now primarily updates the display, with time calculation based on video position.
        """
        if not self._is_recording or self._is_recording_paused:
            return
        
        # Update the time display
        self._update_recording_time_display()
    
    def _complete_recording(self):
        """Complete the recording when time is up."""
        if not self._is_recording:
            return
            
        self._is_recording = False
        self._is_recording_paused = False
        self._recording_timer.stop()
        
        # End any active events
        for key, (position, _) in list(self._key_press_times.items()):
            # Calculate a reasonable offset with minimum duration
            current_position = self._video_model.get_position()
            if current_position <= position:
                current_position = position + self._frame_duration_ms
            
            # End the event
            self._annotation_model.end_event(key, current_position)
        
        # Clear key press times
        self._key_press_times = {}
        
        # Update UI
        self._main_window.set_status_message("Recording completed")
        self._main_window.recording_control_view.set_complete_state()
        self.logger.info("Recording completed automatically")
        
        # Automatically export annotations if in project mode
        if self._project_mode and self._auto_export_path and not self._skip_auto_export:
            self._auto_export_annotations()
            
        # Reset the skip flag
        self._skip_auto_export = False
    
    def _auto_export_annotations(self):
        """Automatically export annotations to the project directory."""
        if not self._auto_export_path or not self._annotation_model.get_all_events():
            return
        
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self._auto_export_path), exist_ok=True)
            
            # Export annotations
            if self._annotation_model.export_to_csv(self._auto_export_path, include_header=True):
                self._main_window.set_status_message(f"Annotations exported to {self._auto_export_path}")
                self.logger.info(f"Annotations automatically exported to {self._auto_export_path}")
                
                # Show information message that auto-closes after 1.5 seconds
                AutoCloseMessageBox.information(
                    self._main_window,
                    "Export Successful",
                    f"Annotations have been automatically exported to:\n{self._auto_export_path}",
                    timeout=1500  # Auto-close after 1.5 seconds
                )
                
                # Update the project if in project mode
                if self._project_model:
                    # Get relative path for proper project tracking
                    project_path = self._project_model.get_project_path()
                    rel_path = os.path.join("annotations", os.path.basename(self._auto_export_path))
                    
                    # Add annotation to project if not already there
                    annotations = self._project_model.get_annotations()
                    if rel_path not in annotations:
                        self._project_model.add_annotation(self._auto_export_path, False, True)
                        self._project_model.save_project()
                        self.logger.info(f"Added annotation file to project: {rel_path}")
            else:
                self._main_window.set_status_message("Failed to export annotations automatically")
                self.logger.error(f"Failed to export annotations to {self._auto_export_path}")
        except Exception as e:
            self._main_window.set_status_message(f"Error exporting annotations: {str(e)}")
            self.logger.error(f"Error in auto export: {str(e)}", exc_info=True)
    
    @Slot()
    def export_annotations_dialog(self):
        """Open a dialog to export annotations to CSV."""
        # Check if there are any annotations to export
        if not self._annotation_model.get_all_events():
            QMessageBox.information(
                self._main_window, 
                "No Annotations", 
                "There are no annotations to export."
            )
            return
        
        # Determine default export path
        default_export_path = ""
        if self._project_mode and self._auto_export_path:
            # In project mode, use the auto-export path as default
            default_export_path = self._auto_export_path
        elif self._current_video_path:
            # Otherwise, use video path + _annotations.csv as default
            video_dir = os.path.dirname(self._current_video_path)
            video_name = os.path.splitext(os.path.basename(self._current_video_path))[0]
            default_export_path = os.path.join(video_dir, f"{video_name}_annotations.csv")
        
        # Get save file path
        file_path, _ = QFileDialog.getSaveFileName(
            self._main_window, "Export Annotations", default_export_path, "CSV Files (*.csv)"
        )
        
        if file_path:
            # Add .csv extension if not present
            if not file_path.lower().endswith('.csv'):
                file_path += '.csv'
            
            # Check if file already exists
            if os.path.exists(file_path):
                result = QMessageBox.question(
                    self._main_window,
                    "File Already Exists",
                    f"The file {os.path.basename(file_path)} already exists.\nDo you want to overwrite it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                
                if result == QMessageBox.StandardButton.No:
                    # Offer to choose a different filename
                    self.logger.info("User chose not to overwrite file. Reopening save dialog.")
                    self.export_annotations_dialog()
                    return
            
            # Export annotations
            if self._annotation_model.export_to_csv(file_path):
                self._main_window.set_status_message(f"Annotations exported to {file_path}")
                
                # Show information message that auto-closes after 1.5 seconds
                AutoCloseMessageBox.information(
                    self._main_window,
                    "Export Successful", 
                    f"Annotations exported to {file_path}",
                    timeout=1500  # Auto-close after 1.5 seconds
                )
                
                # If in project mode, check if we need to update the project
                if self._project_mode and self._project_model:
                    project_path = self._project_model.get_project_path()
                    
                    # If not saved in project directory, ask if user wants to add to project
                    if not file_path.startswith(project_path):
                        result = QMessageBox.question(
                            self._main_window,
                            "Add to Project",
                            "Would you like to add this annotation file to the project?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                        )
                        
                        if result == QMessageBox.StandardButton.Yes:
                            # Ask if file should be copied to project
                            copy_result = QMessageBox.question(
                                self._main_window,
                                "Copy to Project",
                                "Copy the file to the project directory?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                            )
                            
                            copy_to_project = copy_result == QMessageBox.StandardButton.Yes
                            
                            # Add to project
                            self._project_model.add_annotation(file_path, copy_to_project)
                            self._project_model.save_project()
                            
                            # Update video annotation status
                            if self._current_video_id:
                                self._project_model.set_video_annotation_status(
                                    self._current_video_id, "annotated"
                                )
            else:
                self._main_window.set_status_message("Failed to export annotations")
    
    @Slot()
    def import_annotations_dialog(self):
        """Open a dialog to import annotations from CSV."""
        # Confirm with user if there are existing annotations
        if self._annotation_model.get_all_events():
            result = QMessageBox.question(
                self._main_window,
                "Existing Annotations",
                "Importing will replace existing annotations. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if result != QMessageBox.StandardButton.Yes:
                return
        
        # Determine initial directory
        initial_dir = ""
        if self._project_mode and self._project_model:
            # In project mode, use project annotations directory as default
            project_path = self._project_model.get_project_path()
            if project_path:
                initial_dir = os.path.join(project_path, "annotations")
        elif self._current_video_path:
            # Otherwise, use video directory as default
            initial_dir = os.path.dirname(self._current_video_path)
        
        # Get file path
        file_path, _ = QFileDialog.getOpenFileName(
            self._main_window, "Import Annotations", initial_dir, "CSV Files (*.csv)"
        )
        
        if file_path:
            # Import annotations
            if self._annotation_model.import_from_csv(file_path):
                self._main_window.set_status_message(f"Annotations imported from {file_path}")
                
                # Update timeline with imported events
                self._timeline_view.set_events(self._annotation_model.get_all_events_with_active())
                
                # Update project status if in project mode
                if self._project_mode and self._project_model and self._current_video_id:
                    self._project_model.set_video_annotation_status(
                        self._current_video_id, "annotated"
                    )
                    
                    # Add the imported file to the project if it's not already there
                    if file_path not in self._project_model.get_annotations():
                        # Ask if user wants to add the file to the project
                        result = QMessageBox.question(
                            self._main_window,
                            "Add to Project",
                            "Would you like to add this annotation file to the project?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                        )
                        
                        if result == QMessageBox.StandardButton.Yes:
                            # Determine if file should be copied
                            project_path = self._project_model.get_project_path()
                            copy_to_project = not file_path.startswith(project_path)
                            
                            # Add to project
                            self._project_model.add_annotation(file_path, copy_to_project)
                            self._project_model.save_project()
            else:
                self._main_window.set_status_message("Failed to import annotations")
    
    @Slot()
    def clear_annotations(self):
        """Clear all annotations after confirmation."""
        # Check if there are any annotations to clear
        if not self._annotation_model.get_all_events():
            return
        
        # Confirm with user
        result = QMessageBox.question(
            self._main_window,
            "Clear Annotations",
            "Are you sure you want to clear all annotations?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if result == QMessageBox.StandardButton.Yes:
            self._annotation_model.clear_events()
            self._main_window.set_status_message("All annotations cleared")