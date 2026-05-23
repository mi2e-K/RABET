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

        # Optional ConfigManager reference used for recent-files tracking.
        # AppController calls ``set_config_manager`` once construction is done.
        self.config_manager = None
        
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
        self._annotations_dirty = False
        self._suppress_annotation_dirty = False
        # 1.3.3+: one-shot flag set in _on_video_loaded to absorb the
        # immediate seek-to-0 the loader fires for a freshly-loaded
        # video, so it does not look like a rewind past the previous
        # recording start.
        self._skip_next_seek_rewind = False
        
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
        
        # Auto-save preference (default: True)
        self._auto_save_enabled = True
        
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

        if hasattr(self._timeline_view, 'event_delete_requested'):
            self._timeline_view.event_delete_requested.connect(
                self.delete_timeline_annotation
            )
        
        # Connect recording control view signals
        recording_control_view = self._main_window.recording_control_view
        recording_control_view.timed_recording_requested.connect(self.start_timed_recording)
        recording_control_view.timed_recording_canceled.connect(self.stop_timed_recording)
        recording_control_view.preserve_annotations_changed.connect(self.set_preserve_annotations)

        # 1.3.3+: react to FBF mode toggles so any active events from the
        # old mode get cleanly finalised (or aborted) instead of being
        # stranded when the press/release contract changes underfoot.
        video_player_view = getattr(self._main_window, 'video_player_view', None)
        if video_player_view is not None and hasattr(
            video_player_view, 'frame_by_frame_mode_changed'
        ):
            video_player_view.frame_by_frame_mode_changed.connect(
                self._on_fbf_mode_toggled
            )
    
    def _record_recent_annotation(self, file_path):
        """Append a file path to the Recent Annotations list."""
        if self.config_manager is None or not file_path:
            return
        try:
            self.config_manager.add_recent_file('annotations', file_path)
            self.config_manager.save_config()
        except Exception as exc:
            self.logger.warning(f"Failed to record recent annotation: {exc}")

    def _mark_annotations_dirty(self):
        """Remember that in-memory annotations have unsaved edits."""
        if not self._suppress_annotation_dirty:
            self._annotations_dirty = True

    def _mark_annotations_saved(self):
        """Remember that in-memory annotations match a saved/imported file."""
        self._annotations_dirty = False

    def _has_unsaved_annotations(self):
        """Return whether there are in-memory events that still need saving."""
        return self._annotations_dirty and bool(self._annotation_model.get_all_events())

    def _clear_annotations_without_dirtying(self):
        """Clear events as part of a video switch/import workflow."""
        self._suppress_annotation_dirty = True
        try:
            self._annotation_model.clear_events()
        finally:
            self._suppress_annotation_dirty = False
        self._mark_annotations_saved()

    def _replace_annotations_from_file(self, file_path):
        """Load annotations from a saved CSV and leave the dirty flag clean."""
        self._suppress_annotation_dirty = True
        try:
            success = self._annotation_model.import_from_csv(file_path)
        finally:
            self._suppress_annotation_dirty = False

        if success:
            self._mark_annotations_saved()
            self._record_recent_annotation(file_path)
            self._timeline_view.set_events(
                self._annotation_model.get_all_events_with_active()
            )
        return success

    def import_annotations_from_file(self, file_path):
        """Import a saved annotation CSV without marking it as unsaved."""
        return self._replace_annotations_from_file(file_path)

    def _confirm_or_clear_existing_annotations_for_new_video(self, project_mode=False):
        """
        Clear annotations from the previous video.

        A confirmation dialog is only needed when the in-memory annotations
        contain edits that have not been written to a CSV yet.
        """
        if not self._annotation_model.get_all_events():
            return True

        if not self._has_unsaved_annotations():
            self.logger.debug("Clearing saved annotations while switching videos")
            self._clear_annotations_without_dirtying()
            return True

        if project_mode:
            message = (
                "Unsaved annotations from another video are still in memory. "
                "Discard them to continue with this project video?\n\n"
                "Choose No to keep them so you can export them first."
            )
        else:
            message = (
                "Unsaved annotations from the previous video are still in memory. "
                "Discard them to start fresh for the new video?\n\n"
                "Choose No to keep them so you can export them first."
            )

        discard = QMessageBox.question(
            self._main_window,
            "Discard Unsaved Annotations?",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if discard == QMessageBox.StandardButton.Yes:
            self.logger.info("User confirmed clearing unsaved annotations")
            self._clear_annotations_without_dirtying()
            self._main_window.set_status_message("Annotations cleared for new video")
            return True

        self.logger.info("User kept unsaved annotations")
        return False

    # Project mode methods
    def set_project_mode(self, enabled):
        """
        Enable or disable project mode.
        
        Args:
            enabled (bool): Whether project mode is enabled
        """
        self._project_mode = enabled
        self.logger.info(f"Project mode {'enabled' if enabled else 'disabled'}")

    def clear_project_context(self):
        """Clear project-specific annotation routing for regular video loads."""
        self._project_mode = False
        self._project_model = None
        self._current_video_id = None
        self._auto_export_path = None
        self.logger.info("Project annotation context cleared")
    
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
        Set the project video reference of the current video being annotated.
        
        Args:
            video_id (str): Stored project video reference or legacy video ID
        """
        self._current_video_id = video_id
        self.logger.info(f"Set current video ID: {video_id}")

    def _is_path_in_project(self, file_path):
        """Check whether a path resolves inside the current project directory."""
        if not self._project_model:
            return False

        project_path = self._project_model.get_project_path()
        if not project_path:
            return False

        try:
            normalized_file = os.path.normcase(os.path.abspath(file_path))
            normalized_project = os.path.normcase(os.path.abspath(project_path))
            return os.path.commonpath([normalized_file, normalized_project]) == normalized_project
        except ValueError:
            return False
    
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
    
    def set_auto_save_enabled(self, enabled):
        """
        Set whether to automatically save annotations when recording completes.
        
        Args:
            enabled (bool): Whether to enable auto-save
        """
        self._auto_save_enabled = enabled
        self.logger.info(f"Auto-save enabled: {enabled}")
    
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
        
        # Ensure timeline controls remain visible during state changes. The
        # singleShot below already returns control to Qt's event loop, which
        # naturally flushes pending paint events - an explicit
        # ``processEvents()`` call was redundant and could cause re-entrant
        # signal handling.
        if hasattr(self._timeline_view, 'ensure_controls_visible'):
            QTimer.singleShot(10, self._timeline_view.ensure_controls_visible)
        
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
        
        # CRITICAL FIX: Final check to ensure controls are visible
        if hasattr(self._timeline_view, 'ensure_controls_visible'):
            self._timeline_view.ensure_controls_visible()
    
    @Slot(int)
    def on_position_changed(self, position):
        """
        Handle video position changed event.
        
        Args:
            position (int): New position in milliseconds
        """
        # Always update timeline position for smooth playback indicator.
        # ``set_position`` repaints the canvas, and active events (offset=None)
        # are drawn against ``_current_position`` automatically, so we do NOT
        # need to rebuild the full event list every frame here. Triggering
        # ``should_update`` is still useful to keep the throttle counter
        # advancing for any code paths that depend on it.
        self._timeline_view.set_position(position)
        self._timeline_view.should_update()

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

        # If we're recording but not paused, update recording time
        if self._is_recording and not self._is_recording_paused:
            self._update_recording_time_display()

        # Ensure controls remain visible during position updates. Reuse a
        # single QTimer (parented to self) instead of leaking a new one.
        if hasattr(self._timeline_view, 'ensure_controls_visible'):
            if not hasattr(self, '_ensure_visible_timer'):
                self._ensure_visible_timer = QTimer(self)
                self._ensure_visible_timer.setSingleShot(True)
                self._ensure_visible_timer.timeout.connect(self._timeline_view.ensure_controls_visible)

            # Reset timer to call after 50ms of no position changes
            self._ensure_visible_timer.start(50)
    
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

        # Discard active (still-pressed) events whose onset is now in the
        # "future" relative to the rewound position. Without this step those
        # events would later be finalised with a wildly inconsistent onset.
        discarded_active = 0
        for key, active_event in list(self._annotation_model.get_active_events().items()):
            if active_event.onset > current_position:
                if self._annotation_model.discard_active_event(key):
                    self._key_press_times.pop(key, None)
                    discarded_active += 1

        if discarded_active:
            self.logger.info(
                f"Discarded {discarded_active} active event(s) whose onset was "
                f"after the rewind point ({current_position}ms)"
            )

        # First truncate annotations that overlap with the current position
        truncated_count = 0
        for i, event in annotations_to_truncate:
            # Replace the old event's offset; AnnotationModel handles the rest.
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
    
    @Slot()
    def on_new_video_load_starting(self):
        """Hook called by ``VideoController.load_video`` BEFORE the
        background loader is kicked off.

        This is the earliest place we can intervene in a video switch —
        crucially earlier than ``_on_video_loaded``. Without this hook
        the loader's reset-to-position-0 used to reach
        ``handle_seek(0)`` while a recording was still ``_is_recording``,
        which tripped the "You have rewound before the recording start
        point" dialog on top of the loading overlay (Issue #2).
        """
        if self._is_recording:
            self.logger.info(
                "New video load starting while recording is active — "
                "auto-stopping the recording session first."
            )
            # Suppress auto-export so the partial session does not write
            # itself out under the previous video's path; the Discard
            # Unsaved Annotations prompt fires later in _on_video_loaded
            # and lets the user keep or drop the in-memory events.
            self._skip_auto_export = True
            try:
                self.stop_timed_recording()
            except Exception:
                self.logger.exception(
                    "on_new_video_load_starting: stop_timed_recording raised"
                )
            finally:
                # Belt-and-braces: stop_timed_recording normally clears
                # this flag on its happy path, but if it raised before
                # that point we MUST reset it here. Otherwise the next
                # legitimate stop would silently skip auto-export.
                self._skip_auto_export = False

        # One-shot guard: when the loader subsequently fires its
        # position=0 seek, ``handle_seek`` will see this flag and skip
        # the rewind-detection branch entirely.
        self._skip_next_seek_rewind = True
        self._last_position = 0

    def _on_video_loaded(self, video_path):
        """
        Handle video loaded event.

        Args:
            video_path (str): Path to the loaded video
        """
        # 1.3.3+: the heavy lifting (auto-stopping any in-progress
        # recording, arming the seek-rewind guard) moved to
        # ``on_new_video_load_starting`` so it runs strictly *before*
        # any loader-emitted position signals. By the time we get here
        # the previous session is already closed and the next seek=0
        # will be silently absorbed.
        self._current_video_path = video_path
        # Belt-and-braces: keep the guard armed in case some path reaches
        # _on_video_loaded without going through load_video (e.g. tests).
        self._skip_next_seek_rewind = True
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
                # Clear in-memory annotations first, then import saved ones
                if self._replace_annotations_from_file(self._auto_export_path):
                    self.logger.info(f"Loaded existing annotations from {self._auto_export_path}")
            else:
                self._confirm_or_clear_existing_annotations_for_new_video(project_mode=True)
        else:
            self._confirm_or_clear_existing_annotations_for_new_video(
                project_mode=self._project_mode
            )
        
        # Update frame duration based on the loaded video
        if hasattr(self._video_model, '_frame_duration_ms'):
            self._frame_duration_ms = self._video_model._frame_duration_ms
            self.logger.debug(f"Updated frame duration to {self._frame_duration_ms}ms based on loaded video")
    
    def _is_frame_by_frame_mode(self):
        """
        Return True when the video player view's frame-by-frame toggle is on.

        Guarded with hasattr/AttributeError so unit tests that stub out the
        main window with a minimal mock don't blow up here.
        """
        try:
            vpv = self._main_window.video_player_view
        except AttributeError:
            return False
        if not hasattr(vpv, "is_frame_by_frame_mode"):
            return False
        try:
            return bool(vpv.is_frame_by_frame_mode())
        except Exception:  # pragma: no cover - defensive
            return False

    @Slot(bool)
    def _on_fbf_mode_toggled(self, enabled):
        """React to the user toggling the frame-by-frame checkbox.

        The press/release contract changes between modes (real-time mode
        uses press + release; FBF uses press + press), so any in-progress
        events from the previous mode would otherwise be stranded.  Offer
        to finalise them at the current playhead position; otherwise
        leave them alone (the user can use Esc to abort manually).

        Only acts during an open recording session — toggling FBF outside
        of recording can never have active events.
        """
        if not self._is_recording:
            return
        active = self._annotation_model.get_active_events()
        if not active:
            return

        # 1.3.3+: pause playback before the modal dialog appears.
        # Otherwise the video keeps running behind the QMessageBox, which
        # both wastes time and (in real-time mode) silently extends
        # active events while the user reads the dialog.
        if self._video_model is not None:
            try:
                if self._video_model.is_playing():
                    self._video_model.pause()
            except Exception:
                self.logger.exception(
                    "FBF toggle: pausing video before dialog raised"
                )

        mode_label = "frame-by-frame" if enabled else "real-time"
        names = ", ".join(
            f"{ev.behavior} (key={k})" for k, ev in active.items()
        )
        result = QMessageBox.question(
            self._main_window,
            "End active annotations?",
            f"You just switched to {mode_label} mode while these annotations "
            f"are still in progress:\n\n  {names}\n\n"
            f"End them at the current video position? Choose No to keep "
            f"them open — but note that the new mode may not finish them "
            f"the way you expect.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if result != QMessageBox.StandardButton.Yes:
            self.logger.info(
                f"FBF toggle ({enabled}): user chose to keep "
                f"{len(active)} active event(s) open."
            )
            return

        position = self._video_model.get_position() if self._video_model else 0
        ended = 0
        for key in list(active.keys()):
            if self._annotation_model.end_event(key, position):
                ended += 1
        # Drop any stale real-time press-time tracking so the next press
        # starts cleanly under the new contract.
        self._key_press_times.clear()
        self._timeline_view.set_events(
            self._annotation_model.get_all_events_with_active()
        )
        self.logger.info(
            f"FBF toggle ({enabled}): ended {ended}/{len(active)} active "
            f"event(s) at position {position}ms."
        )
        self._main_window.set_status_message(
            f"Ended {ended} active annotation(s) on mode switch."
        )

    @Slot()
    def abort_all_active_events(self):
        """Discard every in-progress annotation. Bound to Esc.

        Used as an emergency escape hatch when the user thinks the
        active-events dict is out of sync (e.g. a key seems "stuck"
        despite repeated presses). Confirmation is intentional — we do
        not want Esc to silently destroy work if it is mashed by accident.
        """
        if not self._is_recording:
            return
        active = self._annotation_model.get_active_events()
        if not active:
            self._main_window.set_status_message("No active annotations to cancel.")
            return

        names = ", ".join(
            f"{ev.behavior} (key={k})" for k, ev in active.items()
        )
        result = QMessageBox.question(
            self._main_window,
            "Cancel active annotations?",
            f"Discard the following in-progress annotation(s) without "
            f"recording them?\n\n  {names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        for key in list(active.keys()):
            self._annotation_model.discard_active_event(key)
        self._key_press_times.clear()
        self._timeline_view.set_events(
            self._annotation_model.get_all_events_with_active()
        )
        self.logger.warning(
            f"Esc abort: discarded {len(active)} active annotation(s)."
        )
        self._main_window.set_status_message(
            f"Cancelled {len(active)} active annotation(s)."
        )

    def _handle_fbf_key_press(self, key):
        """
        Frame-by-frame annotation: same key toggles start (1st press) and
        end (2nd press) of an event.

        Unlike the real-time path, this does NOT require video playback —
        the user is expected to have paused the video and stepped to the
        exact frame they want to tag. The first press starts an event at
        the current frame; the second press of the same key ends it at the
        new current frame, enforcing a minimum 1-frame duration so two
        presses on the same frame still produce a non-zero event.

        Uses the existing start_event / end_event APIs so timeline
        rendering, project status updates, undo, and CSV export all keep
        working unchanged.
        """
        position = self._video_model.get_position()
        active = self._annotation_model.get_active_events()

        if key in active:
            # Second press -> end the event at the current frame.
            press_event = active[key]
            min_offset = press_event.onset + self._frame_duration_ms
            end_position = max(position, min_offset)

            if self._annotation_model.end_event(key, end_position):
                self.logger.info(
                    f"FBF: ended '{press_event.behavior}' (key={key}) at "
                    f"{end_position}ms (onset was {press_event.onset}ms)"
                )
                # Drop any stale press-time tracking; FBF doesn't use it
                # but the real-time path might have left an entry behind
                # if the user toggled FBF mid-session.
                self._key_press_times.pop(key, None)

                self._timeline_view.set_events(
                    self._annotation_model.get_all_events_with_active()
                )
                self._main_window.set_status_message(
                    f"Frame-by-frame: end marked for "
                    f"'{press_event.behavior}' "
                    f"({(end_position - press_event.onset) / 1000:.2f}s)"
                )

                # Mark video annotated in project mode (mirrors the
                # real-time release path so the project view's coloured
                # status indicator stays accurate).
                if (self._project_mode and self._project_model
                        and self._current_video_id):
                    self._project_model.set_video_annotation_status(
                        self._current_video_id, "annotated"
                    )
            return

        # First press -> start a new event at the current frame.
        if self._annotation_model.start_event(key, position):
            behavior = self._annotation_model._action_map_model.get_behavior(key)
            self.logger.info(
                f"FBF: started '{behavior}' (key={key}) at {position}ms — "
                f"press '{key}' again at the end frame to finish"
            )
            self._timeline_view.set_events(
                self._annotation_model.get_all_events_with_active()
            )
            if behavior:
                self._main_window.set_status_message(
                    f"Frame-by-frame: start marked for '{behavior}' — "
                    f"press '{key}' again at the end frame"
                )
        else:
            # 1.3.3+: start_event refused the press because the key is
            # already active. Surface this to the user instead of failing
            # silently — invisible duplicate-ignore was a likely
            # contributor to the "FBF won't stop" report.
            self._main_window.set_status_message(
                f"Key '{key}' is already active — press again at the end "
                f"frame, or press Esc to cancel."
            )

    @Slot(str)
    def on_key_pressed(self, key):
        """
        Handle key press event.

        Two annotation flows are supported:

        1. **Real-time mode** (frame-by-frame toggle OFF): the original
           RABET flow. Video must be playing AND the recording must not
           be paused; key down starts an event and key up ends it.

        2. **Frame-by-frame mode** (frame-by-frame toggle ON): the user is
           expected to have paused the video and to be stepping frames
           one-by-one. Pausing the video auto-pauses the recording timer
           via _on_playback_state_changed, so we must NOT gate on
           ``_is_recording_paused`` in this mode — otherwise no FBF key
           press would ever land. The 1st press of a key starts an event
           at the current frame and the 2nd press of the *same* key ends
           it. Key release is a no-op (handled in on_key_released).

        Both modes still require a recording session to be open
        (``_is_recording == True``).

        Args:
            key (str): Key character
        """
        # Gate 1 (both modes): a recording session must be open at all.
        # If the user hasn't pressed "Start Recording" yet, key presses
        # mean nothing.
        if not self._is_recording:
            return

        # Gate 2 (FBF mode only): tolerate paused playback / paused
        # recording, because that's the *normal* state during FBF work.
        # Route directly to the toggle-style handler and return.
        if self._is_frame_by_frame_mode():
            self._handle_fbf_key_press(key)
            return

        # Gate 3 (real-time mode only): require both an active (non-paused)
        # recording AND a playing video. This preserves the original
        # RABET behaviour where annotations are captured live as the
        # video plays.
        if self._is_recording_paused or not self._video_model.is_playing():
            return

        # Get current video position and monotonic system time
        position = self._video_model.get_position()
        system_time = time.monotonic()

        # Store both position and system time
        self._key_press_times[key] = (position, system_time)

        # Start event in annotation model
        if self._annotation_model.start_event(key, position):
            self.logger.debug(f"Started event for key {key} at {position}ms (system time: {system_time:.6f})")
            # Update timeline to show active event
            self._timeline_view.set_events(self._annotation_model.get_all_events_with_active())
        else:
            # 1.3.3+: duplicate press for an already-active key. In
            # real-time mode this normally only happens when the OS
            # produced two press events without an intervening release
            # (e.g. focus loss, foreign key-event hooks). Make the
            # situation visible so the user can release & re-press or
            # use Esc to abort.
            self._main_window.set_status_message(
                f"Key '{key}' is already active — release it before pressing again, "
                f"or press Esc to cancel."
            )
    
    @Slot(str)
    def on_key_released(self, key):
        """
        Handle key release event.

        The acceptance checks mirror ``on_key_pressed`` so that a key press
        that was admitted is always finalised by exactly one of the paths
        below, regardless of whether the user paused playback between the
        press and the release. Previously the asymmetry meant that releases
        could fire with an offset captured *after* an auto-pause, producing
        misleading duration values.

        In **frame-by-frame mode** this becomes a no-op: both start and end
        are triggered by key PRESS events instead (1st press = start, 2nd
        press = end). Acting on release would close events the user only
        meant to start.

        Args:
            key (str): Key character
        """
        # FBF mode: release is a no-op. Do this before any other gating so
        # the user's release never accidentally finalises a press that was
        # supposed to be the "start" half of a two-press FBF event.
        if self._is_frame_by_frame_mode():
            return

        # Drop releases entirely when nothing was tracked - keeps idle key
        # events (Tab, modifier keys, etc.) from generating warnings.
        if key not in self._key_press_times:
            return

        # If recording is not currently active, finalise the event using the
        # information captured at press time so that onset/offset remain
        # internally consistent. This mirrors the press-time gating in
        # ``on_key_pressed``.
        if (self._video_model.get_duration() == 0
                or not self._is_recording
                or self._is_recording_paused):
            press_position, _press_system_time = self._key_press_times.pop(key)
            # Ensure the event satisfies the minimum-duration requirement.
            self._annotation_model.end_event(
                key, press_position + self._frame_duration_ms
            )
            return

        # Get current video position and monotonic system time
        current_position = self._video_model.get_position()
        current_system_time = time.monotonic()
            
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
        self._mark_annotations_dirty()
        
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
        self._mark_annotations_dirty()
        
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
        self._mark_annotations_dirty()
        
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
        self._mark_annotations_dirty()
        
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
        if hasattr(self._main_window, 'schedule_layout_diagnostic_snapshots'):
            self._main_window.schedule_layout_diagnostic_snapshots("annotation_controller_start_timed_recording")
        if hasattr(self._main_window, 'schedule_annotation_layout_stabilization'):
            self._main_window.schedule_annotation_layout_stabilization()
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
            self._pause_video_after_recording()
            
            # Automatically export annotations
            if not self._skip_auto_export:
                self._auto_save_annotations()
            
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
        # 1.3.3+: swallow the loader-emitted seek that fires immediately
        # after _on_video_loaded so we do not interpret it as a user
        # rewind past the (now-irrelevant) previous recording start.
        if getattr(self, "_skip_next_seek_rewind", False):
            self._skip_next_seek_rewind = False
            self._last_position = position
            return

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
        self._pause_video_after_recording()
        
        # Automatically save annotations
        if not self._skip_auto_export:
            self._auto_save_annotations()
            
        # Reset the skip flag
        self._skip_auto_export = False
        self._return_to_project_mode_after_recording()

    def _pause_video_after_recording(self):
        """Pause playback once a recording session has ended."""
        try:
            if self._video_model.is_playing():
                self._video_model.pause()
                self.logger.info("Paused video after recording ended")
        except Exception as exc:
            self.logger.warning(f"Failed to pause video after recording: {exc}")

    def _return_to_project_mode_after_recording(self):
        """Return to Project view after finishing a project-mode annotation."""
        if not (self._project_mode and self._project_model):
            return
        if not getattr(self._project_model, "is_project_open", lambda: False)():
            return

        try:
            if hasattr(self._main_window, 'switch_to_project_mode'):
                QTimer.singleShot(0, self._main_window.switch_to_project_mode)
                self.logger.info("Scheduled return to project mode after recording")
        except Exception as exc:
            self.logger.warning(f"Failed to return to project mode: {exc}")
    
    def _auto_save_annotations(self):
        """
        Automatically save annotations when recording completes.
        Works in both project mode and non-project mode.
        """
        # Don't save if no annotations exist
        if not self._annotation_model.get_all_events():
            self.logger.info("No annotations to save")
            return
        
        # Don't save if auto-save is disabled
        if not self._auto_save_enabled:
            self.logger.info("Auto-save is disabled")
            return
        
        # In project mode, use the auto-export path
        if self._project_mode and self._auto_export_path:
            self._auto_export_annotations()
        else:
            # In non-project mode, save to default location based on video filename
            if self._current_video_path:
                self._auto_export_non_project_annotations()
    
    def _auto_export_non_project_annotations(self):
        """Automatically export annotations in non-project mode."""
        if not self._current_video_path:
            self.logger.warning("No video path available for auto-export")
            return
        
        try:
            # Generate default export path based on video filename
            video_dir = os.path.dirname(self._current_video_path)
            video_name = os.path.splitext(os.path.basename(self._current_video_path))[0]
            
            # Create timestamp for uniqueness if file exists
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Try without timestamp first
            export_path = os.path.join(video_dir, f"{video_name}_annotations.csv")
            
            # If file exists, add timestamp
            if os.path.exists(export_path):
                export_path = os.path.join(video_dir, f"{video_name}_annotations_{timestamp}.csv")
            
            # Export annotations
            if self._annotation_model.export_to_csv(export_path, include_header=True):
                self._mark_annotations_saved()
                self._record_recent_annotation(export_path)
                self._main_window.set_status_message(f"Annotations auto-saved to {os.path.basename(export_path)}")
                self.logger.info(f"Annotations automatically saved to {export_path}")
                
                # Show information message that auto-closes after 2 seconds
                AutoCloseMessageBox.information(
                    self._main_window,
                    "Auto-Save Successful",
                    f"Annotations have been automatically saved to:\n{export_path}",
                    timeout=2000  # Auto-close after 2 seconds
                )
            else:
                self._main_window.set_status_message("Failed to auto-save annotations")
                self.logger.error(f"Failed to auto-save annotations to {export_path}")
                
                # Prompt user to save manually
                QMessageBox.warning(
                    self._main_window,
                    "Auto-Save Failed",
                    "Failed to automatically save annotations.\nPlease save manually using File > Export Annotations."
                )
        except Exception as e:
            self._main_window.set_status_message(f"Error auto-saving annotations: {str(e)}")
            self.logger.error(f"Error in auto-save: {str(e)}", exc_info=True)
            
            # Prompt user to save manually
            QMessageBox.warning(
                self._main_window,
                "Auto-Save Error",
                f"Error auto-saving annotations: {str(e)}\nPlease save manually using File > Export Annotations."
            )
    
    def _auto_export_annotations(self):
        """Automatically export annotations to the project directory."""
        if not self._auto_export_path or not self._annotation_model.get_all_events():
            return
        
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self._auto_export_path), exist_ok=True)
            
            # Export annotations
            if self._annotation_model.export_to_csv(self._auto_export_path, include_header=True):
                self._mark_annotations_saved()
                self._record_recent_annotation(self._auto_export_path)
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
                    # Compute the relative path used for project tracking. The
                    # absolute project root used to be kept in a local
                    # ``project_path`` variable; it is no longer needed since
                    # ``add_annotation`` resolves the project root itself.
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
        
        # Get save file path, looping until the user picks a non-conflicting
        # filename or cancels. Using a loop (instead of recursion) keeps the
        # call stack bounded if the user repeatedly declines to overwrite.
        file_path = None
        current_default = default_export_path
        while True:
            chosen_path, _ = QFileDialog.getSaveFileName(
                self._main_window,
                "Export Annotations",
                current_default,
                "CSV Files (*.csv)",
            )
            if not chosen_path:
                return  # User cancelled

            # Add .csv extension if not present
            if not chosen_path.lower().endswith('.csv'):
                chosen_path += '.csv'

            # Check if file already exists
            if os.path.exists(chosen_path):
                result = QMessageBox.question(
                    self._main_window,
                    "File Already Exists",
                    f"The file {os.path.basename(chosen_path)} already exists.\nDo you want to overwrite it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )

                if result == QMessageBox.StandardButton.No:
                    # Re-open the dialog so the user can pick another name.
                    self.logger.info("User chose not to overwrite file. Reopening save dialog.")
                    current_default = chosen_path
                    continue

            file_path = chosen_path
            break

        if file_path:
            # Export annotations
            if self._annotation_model.export_to_csv(file_path):
                self._mark_annotations_saved()
                self._record_recent_annotation(file_path)
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
                    # If not saved in project directory, ask if user wants to add to project
                    if not self._is_path_in_project(file_path):
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
                self._mark_annotations_saved()
                self._record_recent_annotation(file_path)
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
                            copy_to_project = not self._is_path_in_project(file_path)
                            
                            # Add to project
                            self._project_model.add_annotation(file_path, copy_to_project)
                            self._project_model.save_project()
            else:
                self._main_window.set_status_message("Failed to import annotations")
    
    @Slot()
    def undo_last_annotation(self):
        """
        Remove the most recently recorded annotation.

        Triggered by ``Edit -> Undo Last Annotation`` / Ctrl+Z. Skips the
        synthetic ``RecordingStart`` marker so the user can keep undoing real
        events without ever wiping the recording session itself. The model
        emits ``annotation_removed`` so the timeline and project status
        update automatically.
        """
        events = self._annotation_model.get_all_events()
        if not events:
            self._main_window.set_status_message("Nothing to undo.")
            return

        # Find the most recent index that isn't the RecordingStart marker.
        target_index = -1
        for i in range(len(events) - 1, -1, -1):
            if events[i].behavior != "RecordingStart":
                target_index = i
                break

        if target_index < 0:
            self._main_window.set_status_message(
                "Only the recording-start marker remains; nothing to undo."
            )
            return

        removed_event = events[target_index]
        if self._annotation_model.remove_event(target_index):
            self.logger.info(
                f"Undid annotation #{target_index}: {removed_event.behavior} "
                f"({removed_event.onset}-{removed_event.offset}ms)"
            )
            self._main_window.set_status_message(
                f"Undid: {removed_event.behavior}"
            )
        else:
            self.logger.warning(f"Failed to undo annotation at index {target_index}")

    @Slot(int)
    def delete_timeline_annotation(self, index):
        """Delete the annotation selected on the timeline.

        Uses ``get_all_events_with_active`` (1.3.3+) so the deletion path
        reaches in-progress events too — previously the active tail of the
        combined list was selectable on the timeline but the ``_events``-
        only ``get_all_events`` range check below silently dropped the
        request, leaving stuck FBF events un-deletable until restart.
        """
        events = self._annotation_model.get_all_events_with_active()
        if not (0 <= index < len(events)):
            return

        event = events[index]
        if event.behavior == "RecordingStart":
            self._main_window.set_status_message("Recording start marker cannot be deleted.")
            return

        if self._annotation_model.remove_event(index):
            if hasattr(self._timeline_view, 'clear_selection'):
                self._timeline_view.clear_selection()
            # Refresh the timeline so the discarded active event vanishes
            # from view immediately (active events live in a separate
            # dict, so the model's annotation_removed signal alone does
            # not redraw their bars).
            self._timeline_view.set_events(
                self._annotation_model.get_all_events_with_active()
            )
            self.logger.info(
                f"Deleted timeline annotation #{index}: {event.behavior} "
                f"({event.onset}-{event.offset}ms)"
            )
            self._main_window.set_status_message(f"Deleted: {event.behavior}")
        else:
            self.logger.warning(f"Failed to delete timeline annotation at index {index}")

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
