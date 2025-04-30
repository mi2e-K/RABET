# views/video_player_view.py - Enhanced loading overlay handling
import logging
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QSlider, QFrame, QSpinBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QDateTime, QEventLoop
from PySide6.QtGui import QIcon, QDragEnterEvent, QDropEvent

from utils.loading_overlay import LoadingOverlay

class VideoPlayerView(QWidget):
    """
    View for video playback and controls.
    
    Signals:
        play_clicked: Emitted when play button is clicked
        pause_clicked: Emitted when pause button is clicked
        seek_requested: Emitted when seek is requested (position in milliseconds)
        step_forward_clicked: Emitted when step forward button is clicked
        step_backward_clicked: Emitted when step backward button is clicked
        rate_changed: Emitted when playback rate is changed (float)
        volume_changed: Emitted when volume is changed (int 0-100)
        video_dropped: Emitted when video file is dropped (file path)
    """
    
    play_clicked = Signal()
    pause_clicked = Signal()
    seek_requested = Signal(int)
    step_forward_clicked = Signal(int)
    step_backward_clicked = Signal(int)
    rate_changed = Signal(float)
    volume_changed = Signal(int)
    video_dropped = Signal(str)  # New signal for drag and drop
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing VideoPlayerView")
        
        # Enable drag and drop
        self.setAcceptDrops(True)
        
        self.setup_ui()
        self.connect_signals()
        
        # Set initial state
        self._is_playing = False
        self._duration = 1  # Avoid division by zero
        
        # Add throttling for slider updates
        self._last_seek_time = 0
        self._slider_throttle_ms = 100  # Limit seek rate to every 100ms
        
        # Flag to prevent button rapid-fire issues
        self._step_in_progress = False
        self._step_cooldown_ms = 300  # Longer cooldown to ensure proper refresh
        self._step_timer = QTimer()
        self._step_timer.setSingleShot(True)
        self._step_timer.timeout.connect(self._reset_step_flag)
        
        # Flag to track if controls are disabled
        self._controls_disabled = False
        
        # Add visual feedback for step buttons
        self._forward_button_timer = QTimer()
        self._forward_button_timer.setSingleShot(True)
        self._forward_button_timer.timeout.connect(self._reset_forward_button)
        
        self._backward_button_timer = QTimer()
        self._backward_button_timer.setSingleShot(True) 
        self._backward_button_timer.timeout.connect(self._reset_backward_button)
        
        # Original button styles
        self._original_button_style = ""
        
        # Create loading overlay
        self._loading_overlay = LoadingOverlay(self)
        self.loading_overlay = self._loading_overlay  # Public access for other components
    
    def setup_ui(self):
        """Set up user interface."""
        # Main layout
        self.layout = QVBoxLayout(self)
        # Reduce margins and spacing
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(2)
        
        # Video display area - MODIFIED FOR BETTER EMBEDDING
        self.video_frame = QFrame()
        self.video_frame.setFrameShape(QFrame.Shape.Panel)
        self.video_frame.setFrameShadow(QFrame.Shadow.Sunken)
        self.video_frame.setStyleSheet("background-color: black;")
        self.video_frame.setMinimumHeight(200)
        
        # Set size policy to expand both horizontally and vertically
        self.video_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Add drop indicator label
        self.drop_label = QLabel("Drop Video File Here")
        self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_label.setStyleSheet("""
            color: white; 
            font-size: 24px; 
            font-weight: bold;
            background-color: rgba(0, 0, 0, 0.5);
            padding: 10px;
            border-radius: 5px;
        """)
        
        # Add label to video frame using absolute positioning
        self.video_layout = QVBoxLayout(self.video_frame)
        self.video_layout.setContentsMargins(0, 0, 0, 0)
        self.video_layout.addWidget(self.drop_label, 0, Qt.AlignmentFlag.AlignCenter)
        
        # Make sure the frame has a proper window handle
        self.video_frame.setAttribute(Qt.WA_NativeWindow)
        self.video_frame.setAttribute(Qt.WA_DontCreateNativeAncestors)
        
        # Ensure it's visible
        self.video_frame.setVisible(True)
        
        self.layout.addWidget(self.video_frame)
        
        # Time display
        self.time_layout = QHBoxLayout()
        self.time_layout.setContentsMargins(2, 0, 2, 0)
        self.current_time_label = QLabel("00:00:00")
        self.duration_label = QLabel("00:00:00")
        self.time_layout.addWidget(self.current_time_label)
        self.time_layout.addStretch()
        self.time_layout.addWidget(self.duration_label)
        self.layout.addLayout(self.time_layout)
        
        # Position slider
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setMinimum(0)
        self.position_slider.setMaximum(1000)
        self.position_slider.setValue(0)
        self.layout.addWidget(self.position_slider)
        
        # Control buttons layout
        self.controls_layout = QHBoxLayout()
        self.controls_layout.setContentsMargins(2, 0, 2, 0)
        # Reduce spacing between elements
        self.controls_layout.setSpacing(4)
        
        # Combined Play/Pause button
        self.play_pause_button = QPushButton("Play")
        # Prevent space key from activating button when it has focus, to avoid duplicate actions
        self.play_pause_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.controls_layout.addWidget(self.play_pause_button)
        
        # Step backward button
        self.step_backward_button = QPushButton("<<")
        self.step_backward_button.setObjectName("stepBackwardButton")
        # Prevent from stealing focus
        self.step_backward_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        # Save original style
        self._original_button_style = self.step_backward_button.styleSheet()
        self.controls_layout.addWidget(self.step_backward_button)
        
        # Step forward button
        self.step_forward_button = QPushButton(">>")
        self.step_forward_button.setObjectName("stepForwardButton")
        # Prevent from stealing focus
        self.step_forward_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.controls_layout.addWidget(self.step_forward_button)
        
        # Step size control - REDUCED SPACING
        self.step_size_label = QLabel("Step (ms):")
        # Make label more compact
        self.step_size_label.setStyleSheet("margin-right: 1px;")
        self.controls_layout.addWidget(self.step_size_label)
        
        self.step_size_spin = QSpinBox()
        self.step_size_spin.setMinimum(10)
        self.step_size_spin.setMaximum(1000)
        self.step_size_spin.setValue(100)
        self.step_size_spin.setSingleStep(10)
        # Make the spinbox more compact
        self.step_size_spin.setFixedWidth(90)  # Increased width from 60 to 90 pixels
        self.controls_layout.addWidget(self.step_size_spin)
        
        # Add a little spacing
        self.controls_layout.addSpacing(4)
        
        # Playback rate control - REDUCED SPACING
        self.rate_label = QLabel("Speed:")
        # Make label more compact
        self.rate_label.setStyleSheet("margin-right: 1px;")
        self.controls_layout.addWidget(self.rate_label)
        
        # Use slider instead of dropdown for playback rate
        self.rate_slider = QSlider(Qt.Orientation.Horizontal)
        self.rate_slider.setMinimum(25)  # 0.25x
        self.rate_slider.setMaximum(200) # 2.00x
        self.rate_slider.setValue(100)   # 1.00x
        self.rate_slider.setFixedWidth(180)  # Increased width from 100 to 180 pixels
        self.controls_layout.addWidget(self.rate_slider)
        
        self.rate_value_label = QLabel("1.00x")
        self.rate_value_label.setFixedWidth(40)
        self.controls_layout.addWidget(self.rate_value_label)
        
        # Add reset button for playback rate
        self.rate_reset_button = QPushButton("Reset")
        self.rate_reset_button.setToolTip("Reset playback speed to 1x")
        self.rate_reset_button.setFixedWidth(60)
        self.rate_reset_button.clicked.connect(self.reset_playback_rate)
        # Prevent button from capturing focus, so space key will still work for play/pause
        self.rate_reset_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.controls_layout.addWidget(self.rate_reset_button)
        
        # Volume control (hidden as requested)
        self.volume_label = QLabel("Volume:")
        self.volume_label.setVisible(False)
        self.controls_layout.addWidget(self.volume_label)
        
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.setVisible(False)
        self.controls_layout.addWidget(self.volume_slider)
        
        # Add controls to main layout
        self.layout.addLayout(self.controls_layout)
    
    def _reset_step_flag(self):
        """Reset the step in progress flag after a delay."""
        self._step_in_progress = False
        self.logger.debug("Step button cooldown complete")
    
    def _reset_forward_button(self):
        """Reset the forward button styling after visual feedback."""
        self.step_forward_button.setStyleSheet(self._original_button_style)
    
    def _reset_backward_button(self):
        """Reset the backward button styling after visual feedback."""
        self.step_backward_button.setStyleSheet(self._original_button_style)
    
    def connect_signals(self):
        """Connect widget signals to slots."""
        self.play_pause_button.clicked.connect(self.toggle_play)
        self.step_forward_button.clicked.connect(self.on_step_forward)
        self.step_backward_button.clicked.connect(self.on_step_backward)
        
        self.position_slider.sliderMoved.connect(self.on_position_moved)
        self.position_slider.sliderReleased.connect(self.on_position_released)
        
        self.rate_slider.valueChanged.connect(self.on_rate_slider_changed)
        self.volume_slider.valueChanged.connect(self.volume_changed)
        # Note: Reset button signal is connected in setup_ui
    
    def show_loading_overlay(self, show=True):
        """
        Show or hide the loading overlay.
        
        Args:
            show (bool): Whether to show or hide the overlay
        """
        if show:
            self._loading_overlay.show_loading()
            # Disable all controls
            self._disable_controls()
        else:
            # Small delay before hiding to allow final UI updates
            QTimer.singleShot(100, self._loading_overlay.hide_loading)
            # Re-enable controls after a short delay to ensure overlay is fully gone
            QTimer.singleShot(200, self._enable_controls)
    
    def set_loading_progress(self, progress):
        """
        Set the loading progress.
        
        Args:
            progress (int): Progress percentage (0-100)
        """
        self._loading_overlay.set_progress(progress)
    
    def _disable_controls(self):
        """Disable all controls during loading."""
        if self._controls_disabled:
            return
            
        self._controls_disabled = True
        self.play_pause_button.setEnabled(False)
        self.step_forward_button.setEnabled(False)
        self.step_backward_button.setEnabled(False)
        self.position_slider.setEnabled(False)
        self.rate_slider.setEnabled(False)
        self.step_size_spin.setEnabled(False)
    
    def _enable_controls(self):
        """Re-enable all controls after loading."""
        if not self._controls_disabled:
            return
            
        self._controls_disabled = False
        self.play_pause_button.setEnabled(True)
        self.step_forward_button.setEnabled(True)
        self.step_backward_button.setEnabled(True)
        self.position_slider.setEnabled(True)
        self.rate_slider.setEnabled(True)
        self.step_size_spin.setEnabled(True)
    
    # Drag and Drop event handlers
    def dragEnterEvent(self, event: QDragEnterEvent):
        """
        Handle drag enter events.
        
        Args:
            event (QDragEnterEvent): The drag enter event
        """
        # Skip if loading overlay is visible
        if hasattr(self, '_loading_overlay') and self._loading_overlay.isVisible():
            event.ignore()
            return
            
        # Check if the drag has URLs and they are video files
        if event.mimeData().hasUrls():
            # Check first URL only
            url = event.mimeData().urls()[0]
            file_path = url.toLocalFile()
            
            # List of supported video extensions
            video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv']
            
            # Accept the drag if the file has a video extension
            if any(file_path.lower().endswith(ext) for ext in video_extensions):
                self.logger.debug(f"Accepting drag enter for video: {file_path}")
                event.acceptProposedAction()
                
                # Highlight drop area
                self.video_frame.setStyleSheet("background-color: #2a3f5f; border: 2px dashed #ffffff;")
                self.drop_label.setStyleSheet("""
                    color: white; 
                    font-size: 18px; 
                    font-weight: bold;
                    background-color: rgba(42, 63, 95, 0.7);
                    padding: 10px;
                    border-radius: 5px;
                """)
                return
        
        # If we get here, the drag is not acceptable
        event.ignore()
    
    def dragLeaveEvent(self, event):
        """Handle drag leave events."""
        # Reset styling when drag leaves
        self.video_frame.setStyleSheet("background-color: black;")
        self.drop_label.setStyleSheet("""
            color: white; 
            font-size: 18px; 
            font-weight: bold;
            background-color: rgba(0, 0, 0, 0.5);
            padding: 10px;
            border-radius: 5px;
        """)
    
    def dropEvent(self, event: QDropEvent):
        """
        Handle drop events.
        
        Args:
            event (QDropEvent): The drop event
        """
        # Skip if loading overlay is visible
        if hasattr(self, '_loading_overlay') and self._loading_overlay.isVisible():
            event.ignore()
            return
            
        # Reset styling
        self.video_frame.setStyleSheet("background-color: black;")
        self.drop_label.setStyleSheet("""
            color: white; 
            font-size: 18px; 
            font-weight: bold;
            background-color: rgba(0, 0, 0, 0.5);
            padding: 10px;
            border-radius: 5px;
        """)
        
        # Process the dropped file
        if event.mimeData().hasUrls():
            # Get the first URL only (we'll only load one video at a time)
            url = event.mimeData().urls()[0]
            file_path = url.toLocalFile()
            
            self.logger.info(f"Video file dropped: {file_path}")
            
            # Emit signal with file path
            self.video_dropped.emit(file_path)
            
            # Accept the drop
            event.acceptProposedAction()
            
            # Show loading overlay
            self.show_loading_overlay(True)
    
    def toggle_play(self):
        """Toggle between play and pause states."""
        # Skip if controls are disabled
        if self._controls_disabled:
            return
            
        if self._is_playing:
            self.pause_clicked.emit()
        else:
            self.play_clicked.emit()
    
    def get_video_frame(self):
        """
        Get the video frame widget for embedding video.
        
        Returns:
            QFrame: Video frame widget
        """
        return self.video_frame
    
    def on_position_moved(self, position):
        """
        Handle position slider moved.
        
        Args:
            position (int): Slider position
        """
        # Skip if controls are disabled
        if self._controls_disabled:
            return
            
        # Update the time label
        self.update_time_label(position)
        
        # Apply throttling to seek requests to avoid overwhelming the player
        current_time = QDateTime.currentMSecsSinceEpoch()
        if current_time - self._last_seek_time >= self._slider_throttle_ms:
            # Convert to milliseconds based on slider range and emit seek request
            position_ms = int(position / 1000.0 * max(1, self._duration))
            self.seek_requested.emit(position_ms)
            self._last_seek_time = current_time
    
    def on_position_released(self):
        """Handle position slider released."""
        # Skip if controls are disabled
        if self._controls_disabled:
            return
            
        position = self.position_slider.value()
        # Convert to milliseconds based on slider range
        position_ms = int(position / 1000.0 * max(1, self._duration))
        self.seek_requested.emit(position_ms)
    
    def on_step_forward(self):
        """Handle step forward button clicked."""
        # Skip if controls are disabled
        if self._controls_disabled:
            return
            
        # Guard against rapid clicking
        if self._step_in_progress:
            self.logger.debug("Step forward ignored - previous step still in progress")
            return
            
        self._step_in_progress = True
        
        # Visual feedback - highlight the button
        self.step_forward_button.setStyleSheet("background-color: #2ecc71; color: white;")
        self._forward_button_timer.start(300)  # Reset after 300ms
        
        # Get exact step size from spinner
        step_size = self.step_size_spin.value()
        
        # Log with exact step size
        self.logger.debug(f"Step forward button clicked with exact step size: {step_size}ms")
        
        # Emit signal with the exact step size
        self.step_forward_clicked.emit(step_size)
        
        # Start cooldown timer to prevent rapid clicking issues
        self._step_timer.start(self._step_cooldown_ms)
    
    def on_step_backward(self):
        """Handle step backward button clicked."""
        # Skip if controls are disabled
        if self._controls_disabled:
            return
            
        # Guard against rapid clicking
        if self._step_in_progress:
            self.logger.debug("Step backward ignored - previous step still in progress")
            return
            
        self._step_in_progress = True
        
        # Visual feedback - highlight the button 
        self.step_backward_button.setStyleSheet("background-color: #3498db; color: white;")
        self._backward_button_timer.start(300)  # Reset after 300ms
        
        # Get exact step size from spinner
        step_size = self.step_size_spin.value()
        
        # Log with exact step size
        self.logger.debug(f"Step backward button clicked with exact step size: {step_size}ms")
        
        # Emit signal with the exact step size
        self.step_backward_clicked.emit(step_size)
        
        # Start cooldown timer to prevent rapid clicking issues
        self._step_timer.start(self._step_cooldown_ms)
    
    def on_rate_slider_changed(self, value):
        """
        Handle playback rate slider changed.
        
        Args:
            value (int): Slider value (25-200)
        """
        # Skip if controls are disabled
        if self._controls_disabled:
            return
            
        # Convert slider value to playback rate (0.25-2.00)
        rate = value / 100.0
        
        # Update label
        self.rate_value_label.setText(f"{rate:.2f}x")
        
        # Emit signal
        self.rate_changed.emit(rate)
    
    @Slot(int)
    def set_position(self, position_ms):
        """
        Set position slider and time label.
        
        Args:
            position_ms (int): Position in milliseconds
        """
        # Only update if we have a valid duration
        if self._duration > 0:
            # Normalize position to slider range (0-1000)
            position_normalized = int((position_ms / max(1, self._duration)) * 1000.0)
            position_normalized = max(0, min(1000, position_normalized))
            
            # Avoid recursive updates by blocking signals
            self.position_slider.blockSignals(True)
            self.position_slider.setValue(position_normalized)
            self.position_slider.blockSignals(False)
            
            self.update_time_label(position_normalized)
    
    @Slot(int)
    def set_duration(self, duration_ms):
        """
        Set video duration.
        
        Args:
            duration_ms (int): Duration in milliseconds
        """
        # Ensure duration is positive
        self._duration = max(1, duration_ms)
        
        # Format duration label
        self.format_time_label(self.duration_label, self._duration)
        
        self.logger.debug(f"Set duration: {self._duration}ms")
    
    def update_time_label(self, position_normalized):
        """
        Update current time label.
        
        Args:
            position_normalized (int): Normalized position (0-1000)
        """
        if self._duration > 0:
            # Calculate time in milliseconds
            current_time_ms = int((position_normalized / 1000.0) * self._duration)
            self.format_time_label(self.current_time_label, current_time_ms)
    
    def format_time_label(self, label, time_ms):
        """
        Format a time label with hours, minutes, seconds.
        
        Args:
            label (QLabel): Label to update
            time_ms (int): Time in milliseconds
        """
        # Ensure time is positive
        time_ms = max(0, time_ms)
        
        # Calculate hours, minutes, seconds
        total_seconds = time_ms / 1000
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        
        # Format and set the label
        label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
    
    @Slot(bool)
    def set_playing_state(self, is_playing):
        """
        Update UI based on playback state.
        
        Args:
            is_playing (bool): True if playing, False if paused
        """
        self._is_playing = is_playing
        
        # Update play/pause button text
        self.play_pause_button.setText("Pause" if is_playing else "Play")
        
        # Hide drop label when video is loaded/playing
        self.drop_label.setVisible(not is_playing)
        
    def reset_playback_rate(self):
        """Reset playback rate to 1x."""
        # Skip if controls are disabled
        if self._controls_disabled:
            return
            
        # Set slider to 100 (1.00x)
        self.rate_slider.setValue(100)
        
        # Update label
        self.rate_value_label.setText("1.00x")
        
        # Emit signal with 1.0 playback rate
        self.rate_changed.emit(1.0)
        
        self.logger.debug("Playback rate reset to 1.00x")
    
    def resizeEvent(self, event):
        """Handle resize events to ensure overlay is properly sized."""
        super().resizeEvent(event)
        if hasattr(self, '_loading_overlay') and self._loading_overlay.isVisible():
            self._loading_overlay.resize(self.size())