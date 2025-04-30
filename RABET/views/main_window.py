# views/main_window.py - Updated with icon handling and title styling
import logging
import os
import sys
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QStackedWidget, QLabel, QStatusBar, QToolBar, 
    QFileDialog, QMessageBox, QSplitter, QApplication
)
from PySide6.QtCore import Qt, Signal, Slot, QSize, QRect, QTimer
from PySide6.QtGui import QKeyEvent, QIcon, QAction

from views.video_player_view import VideoPlayerView
from views.timeline_view import TimelineView
from views.action_map_view import ActionMapView
from views.recording_control_view import RecordingControlView
from views.analysis_view import AnalysisView

class MainWindow(QMainWindow):
    """
    Main application window for RABET.
    
    Signals:
        key_pressed: Emitted when a key is pressed
        key_released: Emitted when a key is released
    """
    
    key_pressed = Signal(str)
    key_released = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing MainWindow")
        
        self.setWindowTitle("RABET - Real-time Animal Behavior Event Tagger")
        # Increase default window size
        self.resize(1400, 900)
        
        # Set app icon for window and taskbar
        self.setup_window_icon()
        
        # Set strong focus policy to ensure main window can receive keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Reference to annotation controller (will be set by app_controller)
        self.annotation_controller = None
        
        # Global focus management (tracks when to redirect focus)
        self._last_clicked_widget = None
        self._need_focus_reset = False
        
        # Create central widget and main layout
        self.central_widget = QWidget()
        self.central_widget.setObjectName("mainCentralWidget")  # Add object name for styling
        self.setCentralWidget(self.central_widget)
        
        self.main_layout = QVBoxLayout(self.central_widget)
        # Remove top and bottom margins to maximize space
        self.main_layout.setContentsMargins(6, 0, 6, 0)
        # Minimize spacing between elements
        self.main_layout.setSpacing(2)
        
        # Create stacked widget instead of tab widget
        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)
        
        # Create annotation view
        self.annotation_widget = QWidget()
        self.annotation_layout = QVBoxLayout(self.annotation_widget)
        # Remove margins to maximize space
        self.annotation_layout.setContentsMargins(0, 0, 0, 0)
        # Minimize spacing between elements
        self.annotation_layout.setSpacing(2)
        
        # Create views
        self.video_player_view = VideoPlayerView()
        self.timeline_view = TimelineView()
        self.recording_control_view = RecordingControlView()
        self.action_map_view = ActionMapView()
        
        # Use a splitter for the upper section to allow resizing between video and action map
        self.upper_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.upper_splitter.addWidget(self.video_player_view)
        
        # Create a widget for the right side (recording control + action map)
        self.right_widget = QWidget()
        self.right_layout = QVBoxLayout(self.right_widget)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Add recording control above action map
        self.right_layout.addWidget(self.recording_control_view)
        self.right_layout.addWidget(self.action_map_view)
        
        # Add right widget to splitter
        self.upper_splitter.addWidget(self.right_widget)
        
        # Give more space to the video (increased ratio for video, reduced for action map)
        self.upper_splitter.setStretchFactor(0, 6)  # Video gets more space
        self.upper_splitter.setStretchFactor(1, 1)  # Right side gets less space
        
        # Set initial sizes (85% for video, 15% for right side)
        total_width = self.width()
        self.upper_splitter.setSizes([int(total_width * 0.85), int(total_width * 0.15)])
        
        # Add to annotation layout with proper spacing
        self.annotation_layout.addWidget(self.upper_splitter)
        
        # Add the timeline with fixed size
        self.annotation_layout.addWidget(self.timeline_view)
        
        # Set stretch factors to make the upper section expand but keep timeline fixed
        # Using larger stretch factor to give more emphasis to the video section
        self.annotation_layout.setStretchFactor(self.upper_splitter, 5)
        self.annotation_layout.setStretchFactor(self.timeline_view, 0)
        
        # Create analysis view
        self.analysis_view = AnalysisView()
        
        # Add pages to stacked widget
        self.stacked_widget.addWidget(self.annotation_widget)
        self.stacked_widget.addWidget(self.analysis_view)
        
        # Dictionary to store views by name
        self._view_index = {
            "Annotation": 0,
            "Analysis": 1
        }
        
        # Create status bar
        self.status_bar = QStatusBar()
        self.status_bar.setContentsMargins(6, 0, 6, 0)  # Minimize top/bottom margins
        self.setStatusBar(self.status_bar)
        
        self.status_message = QLabel("Ready")
        self.status_bar.addWidget(self.status_message)
        
        self.video_info = QLabel("")
        self.status_bar.addPermanentWidget(self.video_info)
        
        # Create toolbar
        self.toolbar = QToolBar("Main Toolbar")
        self.addToolBar(self.toolbar)
        
        # Create menu
        self.create_menus()
        
        # Setup toolbar with quick access buttons
        self.setup_toolbar()
        
        # Step size for arrow keys in milliseconds
        self._arrow_key_step_size = 100
        
        # Flag to prevent double space key processing
        self._space_key_processing = False
        
        # State tracking for more reliable spacebar handling
        self._last_play_state = False  # Track video play state
        self._last_recording_state = False  # Track recording state
        self._last_recording_paused_state = False  # Track recording paused state
        
        # Debug timer for logging states
        self._debug_timer = QTimer(self)
        self._debug_timer.setInterval(2000)  # Log every 2 seconds for debugging
        self._debug_timer.timeout.connect(self._log_current_states)
        
        # Uncomment this line to enable state logging during development
        # self._debug_timer.start()
    
    def setup_window_icon(self):
        """Set up the window and taskbar icon."""
        # Search for the icon in multiple possible locations
        icon_paths = [
            os.path.join("resources", "RABET.ico"),
            os.path.join("resources", "icon.ico"),
            "RABET.ico",
            "icon.ico"
        ]
        
        # For packaged app, also check relative to executable
        if getattr(sys, 'frozen', False):
            # We're running in a bundle
            bundle_dir = os.path.dirname(sys.executable)
            for rel_path in icon_paths.copy():
                icon_paths.append(os.path.join(bundle_dir, rel_path))
        
        # Find the first valid icon path
        icon_path = None
        for path in icon_paths:
            if os.path.exists(path):
                icon_path = path
                break
        
        if not icon_path:
            self.logger.warning("Window icon not found in any of the expected locations")
            return
        
        try:
            self.logger.info(f"Setting window icon from: {icon_path}")
            
            # Create icon
            app_icon = QIcon(icon_path)
            
            # Verify the icon was loaded successfully
            if app_icon.isNull():
                self.logger.error(f"Failed to load icon from {icon_path} - icon is null")
                return
                
            # Set the window icon
            self.setWindowIcon(app_icon)
            
            # Also set it for the application if possible
            app = QApplication.instance()
            if app:
                app.setWindowIcon(app_icon)
                
            self.logger.info("Window icon set successfully")
        except Exception as e:
            self.logger.error(f"Error setting window icon: {str(e)}")
    
    def _log_current_states(self):
        """Log current playback and recording states for debugging."""
        if self.annotation_controller:
            is_playing = self.video_player_view._is_playing
            is_recording = self.annotation_controller._is_recording
            is_paused = self.annotation_controller._is_recording_paused
            
            self.logger.debug(
                f"Current states - playing: {is_playing}, "
                f"recording: {is_recording}, paused: {is_paused}"
            )
    
    def center_on_screen(self):
        """Center the window on the screen."""
        # Get the screen geometry
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        
        # Calculate window position
        window_geometry = self.frameGeometry()
        window_x = (screen_geometry.width() - window_geometry.width()) // 2
        window_y = (screen_geometry.height() - window_geometry.height()) // 2
        
        # Move window to center
        self.move(window_x, window_y)
        self.logger.debug(f"Centered window at ({window_x}, {window_y})")
    
    def setup_toolbar(self):
        """Set up the toolbar with quick access buttons."""
        self.toolbar.setMovable(True)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        
        # Add a divider
        self.toolbar.addSeparator()
        
        # Create a toggle button for switching between annotation and analysis mode
        self.annotation_mode_toolbar_action = QAction("Annotation Mode", self)
        self.annotation_mode_toolbar_action.setCheckable(True)
        self.annotation_mode_toolbar_action.setChecked(True)  # Default is annotation mode
        self.annotation_mode_toolbar_action.setStatusTip("Switch to annotation mode")
        self.annotation_mode_toolbar_action.triggered.connect(lambda: self.switch_to_view("Annotation"))
        self.toolbar.addAction(self.annotation_mode_toolbar_action)
        
        self.analysis_mode_toolbar_action = QAction("Analysis Mode", self)
        self.analysis_mode_toolbar_action.setCheckable(True)
        self.analysis_mode_toolbar_action.setStatusTip("Switch to analysis mode")
        self.analysis_mode_toolbar_action.triggered.connect(lambda: self.switch_to_view("Analysis"))
        self.toolbar.addAction(self.analysis_mode_toolbar_action)
        
        # Add these actions to the mode group
        self.mode_group.addAction(self.annotation_mode_toolbar_action)
        self.mode_group.addAction(self.analysis_mode_toolbar_action)
    
    def create_menus(self):
        """Create application menus."""
        # File menu - Remove the ampersand (&) to disable menu mnemonics
        self.file_menu = self.menuBar().addMenu("File")
        
        self.open_video_action = QAction("Open Video", self)
        self.open_video_action.setStatusTip("Open a video file")
        self.file_menu.addAction(self.open_video_action)
        
        self.load_action_map_action = QAction("Load Action Map", self)
        self.load_action_map_action.setStatusTip("Load an action map from a JSON file")
        self.file_menu.addAction(self.load_action_map_action)
        
        self.save_action_map_action = QAction("Save Action Map", self)
        self.save_action_map_action.setStatusTip("Save action map to a JSON file")
        self.file_menu.addAction(self.save_action_map_action)
        
        self.file_menu.addSeparator()
        
        self.export_annotations_action = QAction("Export Annotations", self)
        self.export_annotations_action.setStatusTip("Export annotations to a CSV file")
        self.file_menu.addAction(self.export_annotations_action)
        
        self.import_annotations_action = QAction("Import Annotations", self)
        self.import_annotations_action.setStatusTip("Import annotations from a CSV file")
        self.file_menu.addAction(self.import_annotations_action)
        
        self.file_menu.addSeparator()
        
        self.exit_action = QAction("Exit", self)
        self.exit_action.setStatusTip("Exit the application")
        self.file_menu.addAction(self.exit_action)
        
        # Edit menu
        self.edit_menu = self.menuBar().addMenu("Edit")
        
        self.clear_annotations_action = QAction("Clear Annotations", self)
        self.clear_annotations_action.setStatusTip("Clear all annotations")
        self.edit_menu.addAction(self.clear_annotations_action)
        
        # View menu (for switching between annotation and analysis modes)
        self.view_menu = self.menuBar().addMenu("View")
        
        self.annotation_mode_action = QAction("Annotation Mode", self)
        self.annotation_mode_action.setStatusTip("Switch to annotation mode")
        self.annotation_mode_action.setCheckable(True)
        self.annotation_mode_action.setChecked(True)
        self.view_menu.addAction(self.annotation_mode_action)
        
        self.analysis_mode_action = QAction("Analysis Mode", self)
        self.analysis_mode_action.setStatusTip("Switch to analysis mode")
        self.analysis_mode_action.setCheckable(True)
        self.view_menu.addAction(self.analysis_mode_action)
        
        # Connect view menu actions
        self.annotation_mode_action.triggered.connect(lambda: self.switch_to_view("Annotation"))
        self.analysis_mode_action.triggered.connect(lambda: self.switch_to_view("Analysis"))
        
        # Help menu
        self.help_menu = self.menuBar().addMenu("Help")
        
        self.about_action = QAction("About", self)
        self.about_action.setStatusTip("Show information about RABET")
        self.help_menu.addAction(self.about_action)

        # Add a Log menu (replacing the Tools menu)
        self.log_menu = self.menuBar().addMenu("Log")
        
        # Add log viewer option to Log menu
        self.view_logs_action = QAction("View Logs", self)
        self.view_logs_action.setStatusTip("View application logs")
        self.log_menu.addAction(self.view_logs_action)
        
        # Add log cleanup option to Log menu
        self.cleanup_logs_action = QAction("Clean Up Logs", self)
        self.cleanup_logs_action.setStatusTip("Remove old log files")
        self.log_menu.addAction(self.cleanup_logs_action)
        
        # Create action group for mode selection
        # (This ensures only one mode is active at a time)
        from PySide6.QtGui import QActionGroup
        self.mode_group = QActionGroup(self)
        self.mode_group.addAction(self.annotation_mode_action)
        self.mode_group.addAction(self.analysis_mode_action)
        self.mode_group.setExclusive(True)
    
    def handleSpaceKey(self):
        """
        Handle space key press more robustly.
        This is a dedicated method to improve play/pause behavior synchronization.
        
        The method has been completely rewritten to use direct state checks rather than
        relying on UI state, and to properly synchronize video playback with recording state.
        """
        if self._space_key_processing:
            return
            
        self._space_key_processing = True
        
        # Detailed logging to track state changes
        self.logger.debug("==== SPACE KEY PRESS PROCESSING START ====")
        
        # Get the current video playback state directly
        was_playing = self.video_player_view._is_playing
        self.logger.debug(f"Video was playing: {was_playing}")
        
        # First, toggle video play/pause using the view's method
        # This is preferable to directly calling the model to ensure proper UI updates
        self.video_player_view.toggle_play()
        
        # Now the video state has toggled
        is_playing = not was_playing
        self.logger.debug(f"Video is now playing: {is_playing}")
        
        # Now handle recording state synchronization
        if self.annotation_controller:
            # Get direct state from annotation controller instead of checking UI
            is_recording = self.annotation_controller._is_recording
            is_paused = self.annotation_controller._is_recording_paused
            
            self.logger.debug(f"Recording state: recording={is_recording}, paused={is_paused}")
            
            # Synchronize recording state with video state if recording is active
            if is_recording:
                # If we were playing and now pausing
                if was_playing and not is_playing:
                    # Pause recording if not already paused
                    if not is_paused:
                        self.logger.debug("Pausing recording to match video pause")
                        self.annotation_controller.pause_recording()
                        
                # If we were paused and now playing
                elif not was_playing and is_playing:
                    # Resume recording if it was paused
                    if is_paused:
                        self.logger.debug("Resuming recording to match video play")
                        self.annotation_controller.resume_recording()
        
        # Log final states for verification
        self.logger.debug(f"Final video state: playing={is_playing}")
        if self.annotation_controller:
            is_recording = self.annotation_controller._is_recording
            is_paused = self.annotation_controller._is_recording_paused
            self.logger.debug(f"Final recording state: recording={is_recording}, paused={is_paused}")
        
        self.logger.debug("==== SPACE KEY PRESS PROCESSING END ====")
        
        # Schedule reset of the processing flag with a longer delay to prevent rapid
        # repeated spacebar presses from causing state inconsistencies
        QTimer.singleShot(400, self.resetSpaceKeyProcessing)
    
    def resetSpaceKeyProcessing(self):
        """Reset the space key processing flag."""
        self._space_key_processing = False
        self.logger.debug("Space key processing reset")
        
    def resetFocus(self):
        """Reset focus to the main window to handle keyboard shortcuts."""
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._need_focus_reset = False
        self.logger.debug("Focus reset to main window")
    
    def installGlobalFocusTracking(self):
        """Install event filters on key widgets to track and manage focus."""
        self.logger.info("Installing global focus tracking")
        
        # Install event filter on the application to catch all events
        QApplication.instance().installEventFilter(self)
        
        # List of widgets that should have focus management
        focus_managed_widgets = [
            # Recording control widgets
            self.recording_control_view.duration_time_edit,
            self.recording_control_view.record_button,
            
            # Video player controls
            self.video_player_view.play_pause_button,
            self.video_player_view.step_forward_button,
            self.video_player_view.step_backward_button,
            self.video_player_view.step_size_spin,
            self.video_player_view.rate_slider,
            self.video_player_view.rate_reset_button,
            
            # Action map widgets
            self.action_map_view.add_button,
            self.action_map_view.edit_button,
            self.action_map_view.remove_button,
            self.action_map_view.mappings_table,
            self.action_map_view.active_behaviors
        ]
        
        # Install event filters on all these widgets
        for widget in focus_managed_widgets:
            widget.installEventFilter(self)
            
        # Add hover tracking to buttons
        self.video_player_view.step_forward_button.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.video_player_view.step_backward_button.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        
        self.logger.debug(f"Installed event filters on {len(focus_managed_widgets)} widgets")
    
    def eventFilter(self, watched, event):
        """
        Global event filter to manage focus for keyboard shortcuts.
        
        Args:
            watched: The widget being watched
            event: The event that occurred
            
        Returns:
            bool: True if event was handled, False to pass to normal handler
        """
        # Track when buttons are clicked
        if event.type() == event.Type.MouseButtonRelease:
            if watched != self:
                self._last_clicked_widget = watched
                self._need_focus_reset = True
                QTimer.singleShot(200, self.resetFocus)
                self.logger.debug(f"Focus to reset after interacting with: {watched}")
        
        # When values change in a spin box or time edit
        elif event.type() == event.Type.FocusOut:
            if watched in [self.video_player_view.step_size_spin, 
                          self.recording_control_view.duration_time_edit]:
                self._need_focus_reset = True
                QTimer.singleShot(200, self.resetFocus)
        
        return super().eventFilter(watched, event)
    
    def keyPressEvent(self, event):
        """
        Handle key press events.
        
        Args:
            event (QKeyEvent): Key event
        """
        # Check the focused widget to prevent space key from affecting recording control buttons
        focused_widget = QApplication.focusWidget()
        
        # Handle space key for play/pause
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            # Check if focus is on a button or other interactive widget in the recording control
            if focused_widget and focused_widget != self:
                # If a button has focus, don't intercept the space key
                parent = focused_widget
                while parent:
                    if parent == self.recording_control_view.record_button:
                        self.logger.debug("Record button has focus, passing space event to Qt")
                        super().keyPressEvent(event)
                        return
                    parent = parent.parent()
            
            # Use the dedicated method to handle space key
            self.handleSpaceKey()
            return
        
        # Handle arrow keys for frame-by-frame navigation when paused
        step_size = self.video_player_view.step_size_spin.value()
        
        # Right arrow - step forward
        if event.key() == Qt.Key.Key_Right:
            self.logger.debug("Right arrow pressed - stepping forward")
            self.video_player_view.step_forward_clicked.emit(step_size)
            return
            
        # Left arrow - step backward
        if event.key() == Qt.Key.Key_Left:
            self.logger.debug("Left arrow pressed - stepping backward")
            self.video_player_view.step_backward_clicked.emit(step_size)
            return
            
        # Convert key to string for normal key handling
        key = event.text()
        
        # Check if in waiting state for recording
        if self.recording_control_view.is_in_waiting_state():
            # Start actual recording upon any key press
            if key and not event.isAutoRepeat():
                self.logger.debug("Starting recording from waiting state")
                self.recording_control_view.start_recording()
                
                # Don't emit key press for this initial trigger
                return
        
        # Emit signal if key is printable and not auto-repeated
        if key and not event.isAutoRepeat():
            self.logger.debug(f"Key pressed: {key}")
            self.key_pressed.emit(key)
        
        # Handle standard key events
        super().keyPressEvent(event)
    
    def keyReleaseEvent(self, event):
        """
        Handle key release events.
        
        Args:
            event (QKeyEvent): Key event
        """
        # Skip space key for play/pause (already handled in press event)
        if event.key() == Qt.Key.Key_Space:
            return
            
        # Skip arrow keys (already handled in press event)
        if event.key() in [Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down]:
            return
            
        # Convert key to string
        key = event.text()
        
        # Emit signal if key is printable and not auto-repeated
        if key and not event.isAutoRepeat():
            self.logger.debug(f"Key released: {key}")
            self.key_released.emit(key)
        
        # Handle standard key events
        super().keyReleaseEvent(event)
    
    @Slot(str)
    def switch_to_view(self, view_name):
        """
        Switch to the specified view.
        
        Args:
            view_name (str): Name of the view to switch to
        """
        if view_name in self._view_index:
            index = self._view_index[view_name]
            self.stacked_widget.setCurrentIndex(index)
            self.logger.debug(f"Switched to {view_name} mode")
            
            # Update action check state for both menu and toolbar
            for action in self.mode_group.actions():
                if action.text() == f"{view_name} Mode":
                    action.setChecked(True)
                    break
            
            # Update toolbar buttons separately
            if view_name == "Annotation":
                self.annotation_mode_toolbar_action.setChecked(True)
                self.analysis_mode_toolbar_action.setChecked(False)
            elif view_name == "Analysis":
                self.annotation_mode_toolbar_action.setChecked(False)
                self.analysis_mode_toolbar_action.setChecked(True)
        else:
            self.logger.warning(f"View not found: {view_name}")
    
    def set_status_message(self, message):
        """
        Set status bar message.
        
        Args:
            message (str): Status message
        """
        self.status_message.setText(message)
    
    def set_video_info(self, info):
        """
        Set video information in status bar.
        
        Args:
            info (str): Video information
        """
        self.video_info.setText(info)
    
    def show_error(self, message):
        """
        Show error message.
        
        Args:
            message (str): Error message
        """
        self.logger.error(f"Error: {message}")
        QMessageBox.critical(self, "Error", message)
    
    def show_info(self, message):
        """
        Show information message.
        
        Args:
            message (str): Information message
        """
        QMessageBox.information(self, "Information", message)
    
    def add_view(self, name, view_widget):
        """
        Add a new view to the application.
        
        Args:
            name (str): Name of the view (used in menu and internal mapping)
            view_widget (QWidget): Widget for the view
        
        Returns:
            bool: True if view was added successfully, False otherwise
        """
        try:
            # Add widget to stacked widget
            index = self.stacked_widget.addWidget(view_widget)
            
            # Store index in view map
            self._view_index[name] = index
            
            # Add action to view menu
            action = QAction(f"{name} Mode", self)
            action.setStatusTip(f"Switch to {name.lower()} mode")
            action.setCheckable(True)
            action.triggered.connect(lambda: self.switch_to_view(name))
            
            # Add to action group
            self.mode_group.addAction(action)
            self.view_menu.addAction(action)
            
            # Only add toolbar buttons for Annotation and Analysis views
            # Skip toolbar button for Project view or any other views
            if name in ["Annotation", "Analysis"]:
                toolbar_action = QAction(f"{name} Mode", self)
                toolbar_action.setStatusTip(f"Switch to {name.lower()} mode")
                toolbar_action.setCheckable(True)
                toolbar_action.triggered.connect(lambda: self.switch_to_view(name))
                self.mode_group.addAction(toolbar_action)
                self.toolbar.addAction(toolbar_action)
            
            self.logger.debug(f"Added view: {name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to add view {name}: {str(e)}")
            return False
    
    def showEvent(self, event):
        """Handle window show event to ensure icon is properly set."""
        super().showEvent(event)
        
        # Ensure icon is properly set
        if self.windowIcon().isNull():
            self.setup_window_icon()