# views/recording_control_view.py
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QGroupBox, QTimeEdit, QProgressBar, QSizePolicy,
    QCheckBox
)
from PySide6.QtCore import Qt, Signal, Slot, QTime, QTimer

class RecordingControlView(QWidget):
    """
    View for controlling timed annotation recording.
    
    Signals:
        timed_recording_requested: Emitted when timed recording is requested (duration in seconds)
        timed_recording_canceled: Emitted when timed recording is canceled
        preserve_annotations_changed: Emitted when the preserve annotations toggle is changed (is_enabled)
    """
    
    timed_recording_requested = Signal(int)  # Signal for requesting timed recording
    timed_recording_canceled = Signal()  # Signal for canceling recording
    preserve_annotations_changed = Signal(bool)  # Signal for preserve annotations toggle
    
    # Recording state constants
    STATE_IDLE = 0
    STATE_WAITING = 1
    STATE_RECORDING = 2
    STATE_PAUSED = 3
    
    # Consolidated style sheet for the recording panel. Each state's visual
    # treatment is selected via the ``state`` dynamic property on the button
    # and the ``role`` property on the status label, so changing state means
    # toggling a property rather than swapping a whole style string.
    _PANEL_STYLE = """
        QPushButton#recordButton {
            color: white;
            font-weight: bold;
            font-size: 14px;
            padding: 8px 15px;
        }
        QPushButton#recordButton[state="idle"],
        QPushButton#recordButton[state="complete"] {
            background-color: #2ecc71;  /* green */
        }
        QPushButton#recordButton[state="waiting"],
        QPushButton#recordButton[state="recording"],
        QPushButton#recordButton[state="paused"] {
            background-color: #e74c3c;  /* red */
        }
        QLabel#recordingStatusLabel { font-weight: bold; }
        QLabel#recordingStatusLabel[role="idle"]     { color: gray; }
        QLabel#recordingStatusLabel[role="waiting"]  { color: #3498db; }
        QLabel#recordingStatusLabel[role="active"]   { color: red; }
        QLabel#recordingStatusLabel[role="paused"]   { color: #f39c12; }
        QLabel#recordingStatusLabel[role="complete"] { color: blue; }
    """

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing RecordingControlView")
        self._layout_diagnostics_enabled = False

        self._recording_state = self.STATE_IDLE

        self.setup_ui()
        # Single consolidated style sheet; state-specific colouring is
        # driven by ``state`` / ``role`` dynamic properties further down.
        self.setStyleSheet(self._PANEL_STYLE)
        self.connect_signals()
        QTimer.singleShot(0, self._freeze_stable_height)

        # Prevent space key from triggering the button
        self.record_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    
    def setup_ui(self):
        """Set up user interface."""
        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)  # Reduce margins to save space
        
        # Recording Group Box
        self.recording_group = QGroupBox("Timed Recording")
        self.recording_layout = QVBoxLayout()
        self.recording_layout.setSpacing(5)  # Reduce spacing to make it more compact
        
        # Duration selection layout
        self.duration_layout = QHBoxLayout()
        
        # Duration setting
        self.duration_label = QLabel("Duration:")
        self.duration_layout.addWidget(self.duration_label)
        
        # Use QTimeEdit for more intuitive time input (hours:minutes:seconds)
        self.duration_time_edit = QTimeEdit()
        self.duration_time_edit.setDisplayFormat("hh:mm:ss")
        self.duration_time_edit.setTime(QTime(0, 5, 0))  # Default to 5 minutes
        self.duration_layout.addWidget(self.duration_time_edit, 1)
        
        # Add duration layout to recording layout
        self.recording_layout.addLayout(self.duration_layout)
        
        # Recording control layout
        self.recording_control_layout = QHBoxLayout()
        
        # Start/Stop recording button. Visual styling is driven by the
        # ``state`` dynamic property (see ``_PANEL_STYLE``).
        self.record_button = QPushButton("Start Recording")
        self.record_button.setObjectName("recordButton")
        self.record_button.setProperty("state", "idle")
        # Make button height larger
        self.record_button.setMinimumHeight(40)
        # Set preferred size policy
        self.record_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.recording_control_layout.addWidget(self.record_button)
        
        # Recording status label. Styling is driven by the ``role`` dynamic
        # property (see ``_PANEL_STYLE``).
        self.status_label = QLabel("Not Recording")
        self.status_label.setObjectName("recordingStatusLabel")
        self.status_label.setProperty("role", "idle")
        self.status_label.setWordWrap(False)
        self.status_label.setMinimumHeight(22)
        self.recording_control_layout.addWidget(self.status_label, 1)
        
        # Add recording control layout to recording layout
        self.recording_layout.addLayout(self.recording_control_layout)
        
        # Progress bar for recording time
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Time remaining: %v seconds")
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        progress_bar_policy = self.progress_bar.sizePolicy()
        progress_bar_policy.setVerticalPolicy(QSizePolicy.Policy.Fixed)
        progress_bar_policy.setRetainSizeWhenHidden(True)
        self.progress_bar.setSizePolicy(progress_bar_policy)
        self.progress_bar.setVisible(False)
        self.recording_layout.addWidget(self.progress_bar)
        
        # Add preserve annotations on rewind checkbox
        self.options_layout = QHBoxLayout()
        self.preserve_annotations_checkbox = QCheckBox("Preserve annotations on rewind")
        self.preserve_annotations_checkbox.setChecked(False)  # Default is to delete annotations
        self.preserve_annotations_checkbox.setToolTip(
            "When unchecked (default), annotations in rewound video sections will be removed. "
            "When checked, annotations will be preserved when rewinding."
        )
        # CRITICAL FIX: Set focus policy to prevent space key from toggling the checkbox
        self.preserve_annotations_checkbox.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.options_layout.addWidget(self.preserve_annotations_checkbox)
        self.options_layout.addStretch()  # Add stretch to push checkbox to the left
        self.recording_layout.addLayout(self.options_layout)
        
        # Set recording group layout
        self.recording_group.setLayout(self.recording_layout)
        
        # Set a fixed size policy
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.recording_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        
        # Add recording group to main layout
        self.layout.addWidget(self.recording_group)

    def _freeze_stable_height(self):
        """Keep the recording panel height stable across idle/waiting/recording states."""
        stable_height = self.sizeHint().height()
        if stable_height > 0:
            self.setMinimumHeight(stable_height)
            self.setMaximumHeight(stable_height)
            if self._layout_diagnostics_enabled:
                self.logger.info(
                    f"[LAYOUT_DIAG] recording_control stable_height frozen at {stable_height}px"
                )
            self.schedule_layout_diagnostic_snapshots("stable_height_frozen")

    def _widget_diag_summary(self, name, widget):
        """Return a compact one-line summary for recording-control diagnostics."""
        from utils.layout_diagnostics import widget_summary
        return widget_summary(name, widget)

    def log_layout_diagnostic(self, reason):
        """Log internal recording-control geometry and size hints."""
        if not self._layout_diagnostics_enabled:
            return
        duration_text = self.duration_time_edit.time().toString("hh:mm:ss")
        lines = [
            (
                f"[LAYOUT_DIAG] recording_control::{reason} "
                f"state={self._recording_state} duration={duration_text} "
                f"button={self.record_button.text()!r} "
                f"status={self.status_label.text()!r} "
                f"progressVisible={self.progress_bar.isVisible()}"
            ),
            "  " + self._widget_diag_summary("recording_control_view", self),
            "  " + self._widget_diag_summary("recording_group", self.recording_group),
            "  " + self._widget_diag_summary("duration_label", self.duration_label),
            "  " + self._widget_diag_summary("duration_time_edit", self.duration_time_edit),
            "  " + self._widget_diag_summary("record_button", self.record_button),
            "  " + self._widget_diag_summary("status_label", self.status_label),
            "  " + self._widget_diag_summary("progress_bar", self.progress_bar),
            "  " + self._widget_diag_summary(
                "preserve_annotations_checkbox",
                self.preserve_annotations_checkbox
            ),
        ]
        self.logger.info("\n".join(lines))

    def schedule_layout_diagnostic_snapshots(self, reason):
        """Capture several recording-control snapshots around a state transition."""
        from utils.layout_diagnostics import schedule_snapshot_burst
        schedule_snapshot_burst(
            self.log_layout_diagnostic,
            reason,
            enabled=bool(self._layout_diagnostics_enabled),
        )
    
    def connect_signals(self):
        """Connect widget signals to slots."""
        self.record_button.clicked.connect(self.on_record_button_clicked)
        self.preserve_annotations_checkbox.stateChanged.connect(self.on_preserve_annotations_changed)
    
    def on_record_button_clicked(self):
        """Handle record button clicked."""
        if self._recording_state == self.STATE_IDLE:
            # Request to start recording (enter waiting state)
            time = self.duration_time_edit.time()
            # Convert to seconds
            duration_seconds = time.hour() * 3600 + time.minute() * 60 + time.second()
            
            if duration_seconds <= 0:
                # Invalid duration, use default of 5 minutes
                duration_seconds = 300
                self.duration_time_edit.setTime(QTime(0, 5, 0))
            
            # Enter waiting state
            self.set_waiting_state(duration_seconds)
            
        else:
            # Cancel recording (either from waiting or recording state)
            self.set_idle_state()
            # Emit signal
            self.timed_recording_canceled.emit()
            
            self.logger.info("Recording canceled")
    
    def on_preserve_annotations_changed(self, state):
        """Handle preserve annotations checkbox state changed."""
        is_preserve_enabled = (state == Qt.CheckState.Checked.value)
        self.logger.debug(f"Preserve annotations on rewind: {is_preserve_enabled}")
        self.preserve_annotations_changed.emit(is_preserve_enabled)
    
    def is_preserve_annotations_enabled(self):
        """
        Check if preserving annotations on rewind is enabled.
        
        Returns:
            bool: True if preservation is enabled, False if annotations should be deleted
        """
        return self.preserve_annotations_checkbox.isChecked()
    
    def set_preserve_annotations(self, enabled):
        """
        Set the preserve annotations checkbox state.
        
        Args:
            enabled (bool): Whether to enable preservation
        """
        self.preserve_annotations_checkbox.setChecked(enabled)
    
    def _apply_button_state(self, state):
        """Re-evaluate the record button's stylesheet after a state change."""
        self.record_button.setProperty("state", state)
        self.record_button.style().unpolish(self.record_button)
        self.record_button.style().polish(self.record_button)

    def _apply_status_role(self, role):
        """Re-evaluate the status label's stylesheet after a state change."""
        self.status_label.setProperty("role", role)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def set_waiting_state(self, duration_seconds):
        """
        Set the view to waiting state.

        Args:
            duration_seconds (int): Duration in seconds for the recording
        """
        self.log_layout_diagnostic("set_waiting_state_before_ui_change")
        self._recording_state = self.STATE_WAITING
        self._duration_seconds = duration_seconds

        # Update UI
        self.record_button.setText("Cancel")
        self._apply_button_state("waiting")
        self.status_label.setText("Press any key to start...")
        self._apply_status_role("waiting")
        
        # Hide progress bar
        self.progress_bar.setVisible(False)
        
        # Disable duration edit
        self.duration_time_edit.setEnabled(False)
        
        # Keep preserve annotations checkbox enabled during recording
        # self.preserve_annotations_checkbox.setEnabled(False)  # Removed
        
        self.logger.info(f"Entered waiting state for {duration_seconds} seconds recording")
        if self._layout_diagnostics_enabled:
            self.logger.info(
                "[LAYOUT_DIAG] set_waiting_state "
                f"sizeH={self.height()} hintH={self.sizeHint().height()} "
                f"groupH={self.recording_group.height()} progressVisible={self.progress_bar.isVisible()}"
            )
        self.log_layout_diagnostic("set_waiting_state_after_ui_change")
        self.schedule_layout_diagnostic_snapshots("set_waiting_state")
    
    def start_recording(self):
        """
        Start actual recording after waiting state.
        
        Returns:
            int: Duration in seconds
        """
        if self._recording_state != self.STATE_WAITING:
            return 0
        
        self.log_layout_diagnostic("start_recording_before_ui_change")
        self._recording_state = self.STATE_RECORDING

        # Update UI
        self._apply_button_state("recording")
        self.status_label.setText("Recording Active")
        self._apply_status_role("active")

        # Show progress bar
        self.progress_bar.setMaximum(self._duration_seconds)
        self.progress_bar.setValue(self._duration_seconds)
        self.progress_bar.setVisible(True)
        
        # Emit signal with duration
        self.timed_recording_requested.emit(self._duration_seconds)
        
        self.logger.info(f"Started actual recording for {self._duration_seconds} seconds")
        if self._layout_diagnostics_enabled:
            self.logger.info(
                "[LAYOUT_DIAG] start_recording "
                f"sizeH={self.height()} hintH={self.sizeHint().height()} "
                f"groupH={self.recording_group.height()} progressVisible={self.progress_bar.isVisible()}"
            )
        self.log_layout_diagnostic("start_recording_after_ui_change")
        self.schedule_layout_diagnostic_snapshots("start_recording")
        
        return self._duration_seconds
    
    def set_paused_state(self):
        """Set the view to paused state."""
        if self._recording_state != self.STATE_RECORDING:
            return
            
        self._recording_state = self.STATE_PAUSED

        # Update UI
        self._apply_button_state("paused")
        self.status_label.setText("Recording Paused")
        self._apply_status_role("paused")
        
        # Show pause indicator on progress bar
        self.progress_bar.setFormat("PAUSED - Time remaining: %v seconds")
        
        self.logger.info("Recording paused")
    
    def resume_recording(self):
        """Resume recording from paused state."""
        if self._recording_state != self.STATE_PAUSED:
            return
            
        self._recording_state = self.STATE_RECORDING

        # Update UI
        self._apply_button_state("recording")
        self.status_label.setText("Recording Active")
        self._apply_status_role("active")

        # Reset progress bar format
        self.progress_bar.setFormat("Time remaining: %v seconds")
        
        self.logger.info("Recording resumed")
    
    def set_idle_state(self):
        """Set the view to idle state."""
        self.log_layout_diagnostic("set_idle_state_before_ui_change")
        self._recording_state = self.STATE_IDLE
        
        # Update UI
        self.record_button.setText("Start Recording")
        self._apply_button_state("idle")
        self.status_label.setText("Not Recording")
        self._apply_status_role("idle")

        # Hide progress bar
        self.progress_bar.setVisible(False)

        # Enable duration edit
        self.duration_time_edit.setEnabled(True)

        # The preserve annotations checkbox remains enabled throughout
        # self.preserve_annotations_checkbox.setEnabled(True)  # Removed

        self.logger.info("Returned to idle state")
        self.log_layout_diagnostic("set_idle_state_after_ui_change")
        self.schedule_layout_diagnostic_snapshots("set_idle_state")
    
    def set_complete_state(self):
        """Set the view to recording completed state."""
        self._recording_state = self.STATE_IDLE
        
        # Update UI
        self.record_button.setText("Start Recording")
        self._apply_button_state("complete")
        self.status_label.setText("Recording Complete")
        self._apply_status_role("complete")
        
        # Hide progress bar
        self.progress_bar.setVisible(False)
        
        # Enable duration edit
        self.duration_time_edit.setEnabled(True)
        
        # The preserve annotations checkbox remains enabled throughout
        # self.preserve_annotations_checkbox.setEnabled(True)  # Removed
        
        self.logger.info("Recording completed")
    
    @Slot(int)
    def update_progress(self, seconds_remaining):
        """
        Update recording progress bar.
        
        Args:
            seconds_remaining (int): Seconds remaining in the recording
        """
        if seconds_remaining >= 0 and (self._recording_state == self.STATE_RECORDING or
                                      self._recording_state == self.STATE_PAUSED):
            self.progress_bar.setValue(seconds_remaining)
    
    def is_in_waiting_state(self):
        """
        Check if view is in waiting state.
        
        Returns:
            bool: True if in waiting state, False otherwise
        """
        return self._recording_state == self.STATE_WAITING
    
    def is_recording(self):
        """
        Check if view is in recording state.
        
        Returns:
            bool: True if recording, False otherwise
        """
        return self._recording_state == self.STATE_RECORDING
    
    def is_paused(self):
        """
        Check if recording is paused.
        
        Returns:
            bool: True if paused, False otherwise
        """
        return self._recording_state == self.STATE_PAUSED
