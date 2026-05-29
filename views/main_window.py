# views/main_window.py - Updated with mode switching functions and visualization support
import logging
import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QStackedWidget, QToolBar, 
    QMessageBox, QSplitter, QApplication, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QEvent
from PySide6.QtGui import QIcon, QAction

from views.video_player_view import VideoPlayerView
from views.timeline_view import TimelineView
from views.action_map_view import ActionMapView
from views.recording_control_view import RecordingControlView
from views.analysis_view import AnalysisView
from utils.app_icon import find_app_icon_path
from utils.video_detection import is_video_file


class CurrentPageStackedWidget(QStackedWidget):
    """A stacked widget whose size hints follow only the currently visible page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(self._on_current_changed)

    def addWidget(self, widget):
        self._track_page(widget)
        return super().addWidget(widget)

    def insertWidget(self, index, widget):
        self._track_page(widget)
        return super().insertWidget(index, widget)

    def _track_page(self, widget):
        if widget is not None:
            widget.installEventFilter(self)

    def _on_current_changed(self, _index):
        self.updateGeometry()

    def eventFilter(self, watched, event):
        if watched == self.currentWidget() and event.type() in (
            QEvent.Type.LayoutRequest,
            QEvent.Type.ShowToParent,
            QEvent.Type.HideToParent,
            QEvent.Type.StyleChange,
            QEvent.Type.FontChange,
        ):
            self.updateGeometry()
        return super().eventFilter(watched, event)

    def sizeHint(self):
        current = self.currentWidget()
        if current is None:
            return super().sizeHint()

        hint = current.sizeHint()
        if not hint.isValid():
            return super().sizeHint()
        return hint.expandedTo(current.minimumSizeHint())

    def minimumSizeHint(self):
        current = self.currentWidget()
        if current is None:
            return super().minimumSizeHint()

        hint = current.minimumSizeHint()
        if not hint.isValid():
            return super().minimumSizeHint()
        return hint

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
        # These flags can be read by Qt event handlers before __init__ finishes.
        self._layout_diagnostics_enabled = False
        self._disable_manual_layout_stabilization = False
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing MainWindow")

        # Settings persistence is wired in via ``set_config_manager`` after
        # construction (see AppController). Until then operations that depend
        # on it must be no-ops.
        self.config_manager = None
        self._settings_restored = False

        self.setWindowTitle("RABET - Real-time Animal Behavior Event Tagger")
        # Increase default window size, but never open larger than the
        # screen (laptops / 1080p) — otherwise the window spills off the
        # right edge on smaller displays.
        default_w, default_h = 1400, 900
        try:
            from PySide6.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                avail = screen.availableGeometry()
                default_w = min(default_w, avail.width() - 40)
                default_h = min(default_h, avail.height() - 80)
        except Exception:
            pass
        self.resize(max(800, default_w), max(600, default_h))
        
        # Set app icon for window and taskbar
        self.setup_window_icon()
        
        # Set strong focus policy to ensure main window can receive keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Accept drag-and-drop globally; the per-view drop targets
        # (VideoPlayerView, AnalysisView, VisualizationView) keep their own
        # finer-grained handlers, but the main window dispatches any drop
        # that lands on the menubar, toolbar or empty regions.
        self.setAcceptDrops(True)
        
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
        # Consistent margins on all sides
        self.main_layout.setContentsMargins(6, 6, 6, 6)
        # Minimize spacing between elements
        self.main_layout.setSpacing(2)
        
        # Keep the window minimum size tied to the visible page, not hidden pages.
        self.stacked_widget = CurrentPageStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)
        
        # Create annotation view
        self.annotation_widget = QWidget()
        self.annotation_layout = QVBoxLayout(self.annotation_widget)
        # Remove margins to maximize space
        self.annotation_layout.setContentsMargins(0, 0, 0, 0)
        # Small spacing between elements
        self.annotation_layout.setSpacing(4)
        
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
        self.right_layout.setSpacing(4)
        self.right_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.right_widget.setMinimumHeight(0)
        self.recording_control_view.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.action_map_view.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.action_map_view.setMinimumHeight(0)
        
        # Add recording control above action map
        self.right_layout.addWidget(self.recording_control_view, 0)
        self.right_layout.addWidget(self.action_map_view, 1)
        self.right_layout.setStretch(0, 0)
        self.right_layout.setStretch(1, 1)
        
        # Add right widget to splitter
        self.upper_splitter.addWidget(self.right_widget)
        
        # Give more space to the video (increased ratio for video, reduced for action map)
        self.upper_splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.upper_splitter.setMinimumHeight(0)
        self.upper_splitter.setChildrenCollapsible(False)
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
        self.annotation_layout.setStretchFactor(self.upper_splitter, 10)  # More space for video
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
        
        # Status bar removed - status messages now integrated into timeline view
        
        # Create toolbar
        self.toolbar = QToolBar("Main Toolbar")
        self.addToolBar(self.toolbar)
        
        # Create menu
        self.create_menus()
        
        # Setup toolbar with quick access buttons
        self.setup_toolbar()
        self._relocate_timeline_auxiliary_controls()
        
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

        # Leave diagnostics off during normal use.
        self._layout_diagnostics_enabled = False
        self._disable_manual_layout_stabilization = True
        
        # Uncomment this line to enable state logging during development
        # self._debug_timer.start()

    def _relocate_timeline_auxiliary_controls(self):
        """Move timeline-adjacent controls into compact toolbar/playback rows."""
        self.video_player_view.add_widgets_to_controls_row(
            self.timeline_view.get_controls_for_playback_row(),
            leading_spacing=8,
        )

        self.timeline_view.zoom_slider.setFixedWidth(110)
        self.timeline_view.zoom_value.setFixedWidth(28)
        self.timeline_view.zoom_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.timeline_view.toolbar_info_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        overlay_text_style = "color: white; background: transparent;"
        self.timeline_view.zoom_label.setStyleSheet(overlay_text_style)
        self.timeline_view.zoom_value.setStyleSheet(overlay_text_style)
        self.timeline_view.toolbar_info_label.setStyleSheet(
            "color: rgba(255, 255, 255, 220); background: transparent;"
        )
        self.timeline_view.toolbar_info_label.setMaximumWidth(420)
        self.timeline_view.toolbar_info_label.setWordWrap(False)

        self.toolbar.addSeparator()
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.toolbar.addWidget(spacer)
        self.toolbar.addWidget(self.timeline_view.get_toolbar_info_widget())

        self.timeline_view.use_external_auxiliary_controls()
    
    def setup_window_icon(self):
        """Set up the window and taskbar icon."""
        icon_path = find_app_icon_path()
        
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

    def _widget_size_summary(self, name, widget):
        """Return a compact one-line summary for layout diagnostics.

        Delegates to the shared helper in ``utils.layout_diagnostics`` so
        the same primitive is used by ``RecordingControlView`` too.
        """
        from utils.layout_diagnostics import widget_summary
        return widget_summary(name, widget)

    def _window_state_summary(self):
        """Return top-level window geometry and hint information for diagnostics."""
        frame = self.frameGeometry()
        normal = self.normalGeometry()
        hint = self.sizeHint()
        min_hint = self.minimumSizeHint()
        return (
            "main_window_state: "
            f"window={self.width()}x{self.height()} "
            f"frame={frame.width()}x{frame.height()} "
            f"normal={normal.width()}x{normal.height()} "
            f"hint={hint.width()}x{hint.height()} "
            f"minHint={min_hint.width()}x{min_hint.height()} "
            f"min={self.minimumWidth()}x{self.minimumHeight()} "
            f"max={self.maximumWidth()}x{self.maximumHeight()} "
            f"maximized={self.isMaximized()} active={self.isActiveWindow()}"
        )

    def log_annotation_layout_snapshot(self, reason):
        """Log the current annotation-page layout state for diagnosis."""
        if not getattr(self, '_layout_diagnostics_enabled', False):
            return
        if not hasattr(self, 'annotation_widget'):
            return

        splitter_sizes = self.upper_splitter.sizes() if hasattr(self, 'upper_splitter') else []
        recording_state = getattr(self.recording_control_view, '_recording_state', None)
        annotation_view_active = (
            hasattr(self, 'stacked_widget') and
            self.stacked_widget.currentWidget() == self.annotation_widget
        )

        lines = [
            f"[LAYOUT_DIAG] {reason}",
            f"  {self._window_state_summary()}",
            f"  annotation_view_active={annotation_view_active} splitter_sizes={splitter_sizes}",
            f"  recording_state={recording_state} waiting={self.recording_control_view.is_in_waiting_state()}",
            "  " + self._widget_size_summary("central_widget", self.central_widget),
            "  " + self._widget_size_summary("stacked_widget", self.stacked_widget),
            "  " + self._widget_size_summary("menu_bar", self.menuBar()),
            "  " + self._widget_size_summary("tool_bar", self.toolbar),
            "  " + self._widget_size_summary("annotation_widget", self.annotation_widget),
            "  " + self._widget_size_summary("upper_splitter", self.upper_splitter),
            "  " + self._widget_size_summary("right_widget", self.right_widget),
            "  " + self._widget_size_summary("recording_control_view", self.recording_control_view),
            "  " + self._widget_size_summary("recording_group", self.recording_control_view.recording_group),
            "  " + self._widget_size_summary("action_map_view", self.action_map_view),
            "  " + self._widget_size_summary("mappings_table", self.action_map_view.mappings_table),
            "  " + self._widget_size_summary("active_behaviors", self.action_map_view.active_behaviors),
            "  " + self._widget_size_summary("timeline_view", self.timeline_view),
            "  " + self._widget_size_summary("timeline_area", self.timeline_view.timeline_area),
            "  " + self._widget_size_summary("timeline_canvas", self.timeline_view.timeline_canvas),
        ]
        self.logger.info("\n".join(lines))

    def schedule_layout_diagnostic_snapshots(self, reason):
        """Capture several snapshots around a state transition."""
        from utils.layout_diagnostics import schedule_snapshot_burst
        schedule_snapshot_burst(
            self.log_annotation_layout_snapshot,
            reason,
            enabled=bool(getattr(self, '_layout_diagnostics_enabled', False)),
        )

    def on_record_button_clicked_layout_diagnostic(self):
        """Record layout state immediately after the record button changes the UI."""
        self.schedule_layout_diagnostic_snapshots("record_button_clicked")
    
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
        self.annotation_mode_toolbar_action = QAction("Annotation", self)
        self.annotation_mode_toolbar_action.setCheckable(True)
        self.annotation_mode_toolbar_action.setChecked(True)  # Default is annotation mode
        self.annotation_mode_toolbar_action.setStatusTip("Switch to annotation mode")
        self.annotation_mode_toolbar_action.triggered.connect(lambda: self.switch_to_view("Annotation"))
        self.toolbar.addAction(self.annotation_mode_toolbar_action)
        
        self.analysis_mode_toolbar_action = QAction("Analysis", self)
        self.analysis_mode_toolbar_action.setCheckable(True)
        self.analysis_mode_toolbar_action.setStatusTip("Switch to analysis mode")
        self.analysis_mode_toolbar_action.triggered.connect(lambda: self.switch_to_view("Analysis"))
        self.toolbar.addAction(self.analysis_mode_toolbar_action)
        
        # Add Visualization toolbar action
        self.visualization_mode_toolbar_action = QAction("Visualization", self)
        self.visualization_mode_toolbar_action.setCheckable(True)
        self.visualization_mode_toolbar_action.setStatusTip("Switch to visualization mode")
        self.visualization_mode_toolbar_action.triggered.connect(lambda: self.switch_to_view("Visualization"))
        self.toolbar.addAction(self.visualization_mode_toolbar_action)

        # Add Reliability toolbar action (1.3.2)
        self.reliability_mode_toolbar_action = QAction("Reliability", self)
        self.reliability_mode_toolbar_action.setCheckable(True)
        self.reliability_mode_toolbar_action.setStatusTip(
            "Switch to reliability assessment mode"
        )
        self.reliability_mode_toolbar_action.triggered.connect(
            lambda: self.switch_to_view("Reliability")
        )
        self.toolbar.addAction(self.reliability_mode_toolbar_action)

        # Add these actions to the mode group
        self.mode_group.addAction(self.annotation_mode_toolbar_action)
        self.mode_group.addAction(self.analysis_mode_toolbar_action)
        self.mode_group.addAction(self.visualization_mode_toolbar_action)
        self.mode_group.addAction(self.reliability_mode_toolbar_action)
        
        # Add Project toolbar action
        self.project_mode_toolbar_action = QAction("Project", self)
        self.project_mode_toolbar_action.setCheckable(True)
        self.project_mode_toolbar_action.setStatusTip("Switch to project management mode")
        self.project_mode_toolbar_action.triggered.connect(self.switch_to_project_mode)
        self.toolbar.addAction(self.project_mode_toolbar_action)
        
        # Add to the mode group
        self.mode_group.addAction(self.project_mode_toolbar_action)
    
    def create_menus(self):
        """Create application menus."""
        from PySide6.QtWidgets import QMenu

        # File menu - Remove the ampersand (&) to disable menu mnemonics
        self.file_menu = self.menuBar().addMenu("File")

        self.open_video_action = QAction("Open Video", self)
        self.open_video_action.setStatusTip("Open a video file")
        self.file_menu.addAction(self.open_video_action)

        # Recent Videos submenu - populated dynamically from ConfigManager.
        self.recent_videos_menu = QMenu("Open Recent Video", self)
        self.recent_videos_menu.aboutToShow.connect(self._populate_recent_videos_menu)
        self.file_menu.addMenu(self.recent_videos_menu)

        self.load_action_map_action = QAction("Load Action Map", self)
        self.load_action_map_action.setStatusTip("Load an action map from a JSON file")
        self.file_menu.addAction(self.load_action_map_action)

        self.save_action_map_action = QAction("Save Action Map", self)
        self.save_action_map_action.setStatusTip("Save action map to a JSON file")
        self.file_menu.addAction(self.save_action_map_action)

        self.reset_action_map_action = QAction("Reset Action Map to Default", self)
        self.reset_action_map_action.setStatusTip("Reset action map to default settings")
        self.file_menu.addAction(self.reset_action_map_action)

        self.file_menu.addSeparator()

        self.export_annotations_action = QAction("Export Annotations", self)
        self.export_annotations_action.setStatusTip("Export annotations to a CSV file")
        self.file_menu.addAction(self.export_annotations_action)

        self.import_annotations_action = QAction("Import Annotations", self)
        self.import_annotations_action.setStatusTip("Import annotations from a CSV file")
        self.file_menu.addAction(self.import_annotations_action)

        # Recent Annotations submenu - populated dynamically from ConfigManager.
        self.recent_annotations_menu = QMenu("Recent Annotations", self)
        self.recent_annotations_menu.aboutToShow.connect(self._populate_recent_annotations_menu)
        self.file_menu.addMenu(self.recent_annotations_menu)

        self.file_menu.addSeparator()
        
        self.exit_action = QAction("Exit", self)
        self.exit_action.setStatusTip("Exit the application")
        self.file_menu.addAction(self.exit_action)
        
        # Edit menu
        self.edit_menu = self.menuBar().addMenu("Edit")

        self.undo_annotation_action = QAction("Undo Last Annotation", self)
        self.undo_annotation_action.setShortcut("Ctrl+Z")
        self.undo_annotation_action.setStatusTip(
            "Remove the most recently recorded annotation"
        )
        self.edit_menu.addAction(self.undo_annotation_action)

        self.edit_menu.addSeparator()

        self.clear_annotations_action = QAction("Clear Annotations", self)
        self.clear_annotations_action.setStatusTip("Clear all annotations")
        self.edit_menu.addAction(self.clear_annotations_action)
        
        # View menu (for switching between views)
        self.view_menu = self.menuBar().addMenu("View")
        
        self.annotation_mode_action = QAction("Annotation", self)
        self.annotation_mode_action.setStatusTip("Switch to annotation mode")
        self.annotation_mode_action.setCheckable(True)
        self.annotation_mode_action.setChecked(True)
        self.view_menu.addAction(self.annotation_mode_action)
        
        self.analysis_mode_action = QAction("Analysis", self)
        self.analysis_mode_action.setStatusTip("Switch to analysis mode")
        self.analysis_mode_action.setCheckable(True)
        self.view_menu.addAction(self.analysis_mode_action)
        
        # Add Visualization menu action
        self.visualization_mode_action = QAction("Visualization", self)
        self.visualization_mode_action.setStatusTip("Switch to visualization mode")
        self.visualization_mode_action.setCheckable(True)
        self.view_menu.addAction(self.visualization_mode_action)

        # Add Reliability menu action (1.3.2)
        self.reliability_mode_action = QAction("Reliability", self)
        self.reliability_mode_action.setStatusTip(
            "Switch to reliability assessment mode"
        )
        self.reliability_mode_action.setCheckable(True)
        self.view_menu.addAction(self.reliability_mode_action)

        # Add Project menu action
        self.project_mode_action = QAction("Project", self)
        self.project_mode_action.setStatusTip("Switch to project management mode")
        self.project_mode_action.setCheckable(True)
        self.view_menu.addAction(self.project_mode_action)

        # Connect view menu actions
        self.annotation_mode_action.triggered.connect(lambda: self.switch_to_view("Annotation"))
        self.analysis_mode_action.triggered.connect(lambda: self.switch_to_view("Analysis"))
        self.visualization_mode_action.triggered.connect(lambda: self.switch_to_view("Visualization"))
        self.reliability_mode_action.triggered.connect(lambda: self.switch_to_view("Reliability"))
        self.project_mode_action.triggered.connect(self.switch_to_project_mode)
        
        # Help menu
        self.help_menu = self.menuBar().addMenu("Help")

        self.shortcuts_action = QAction("Show Shortcuts", self)
        self.shortcuts_action.setShortcut("F1")
        self.shortcuts_action.setStatusTip(
            "Display a quick reference of every keyboard shortcut RABET recognises"
        )
        self.help_menu.addAction(self.shortcuts_action)

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
        self.mode_group.addAction(self.visualization_mode_action)
        self.mode_group.addAction(self.reliability_mode_action)
        self.mode_group.addAction(self.project_mode_action)
        self.mode_group.setExclusive(True)
    
    # New methods for project mode integration
    def switch_to_video_mode(self):
        """
        Switch the main interface to video player mode.
        Used when annotating videos from the project view.
        """
        self.logger.debug("Switching to video player mode")
        
        # Select the annotation mode in the stacked widget
        self.stacked_widget.setCurrentIndex(self._view_index["Annotation"])
        
        # Update checkable actions. All mode actions are created during
        # __init__, so the hasattr guards added during 1.3.2 development
        # were redundant and have been removed.
        self.annotation_mode_action.setChecked(True)
        self.annotation_mode_toolbar_action.setChecked(True)
        self.analysis_mode_action.setChecked(False)
        self.analysis_mode_toolbar_action.setChecked(False)
        self.visualization_mode_action.setChecked(False)
        self.visualization_mode_toolbar_action.setChecked(False)
        self.reliability_mode_action.setChecked(False)
        self.reliability_mode_toolbar_action.setChecked(False)
        self.project_mode_action.setChecked(False)
        self.project_mode_toolbar_action.setChecked(False)

        self._sync_toolbar_status_for_view("Annotation")

        # Ensure the video player view has focus for key events. Qt
        # delivers the focus change on the next event-loop iteration; an
        # explicit ``processEvents`` is not needed for ``setFocus`` itself.
        self.video_player_view.setFocus()
        
        # Log transition completion
        self.logger.info("Successfully switched to video mode")
    
    def switch_to_project_mode(self):
        """
        Switch the main interface to project management mode.
        """
        self.logger.debug("Switching to project mode")
        
        # If we have a project view, set it as current
        if "Project" in self._view_index:
            self.stacked_widget.setCurrentIndex(self._view_index["Project"])
            
            # Update checkable actions
            self.annotation_mode_action.setChecked(False)
            self.annotation_mode_toolbar_action.setChecked(False)
            self.analysis_mode_action.setChecked(False)
            self.analysis_mode_toolbar_action.setChecked(False)
            self.visualization_mode_action.setChecked(False)
            self.visualization_mode_toolbar_action.setChecked(False)
            self.reliability_mode_action.setChecked(False)
            self.reliability_mode_toolbar_action.setChecked(False)
            self.project_mode_action.setChecked(True)
            self.project_mode_toolbar_action.setChecked(True)
            
            self.timeline_view.set_toolbar_context("Project")
            self.set_status_message("Project Mode: Manage videos and annotations")
        else:
            self.logger.warning("Project view not found in view index")

    def _sync_toolbar_status_for_view(self, view_name):
        """Keep toolbar summary text aligned with the active top-level view."""
        self.timeline_view.set_toolbar_context(view_name)
        current_status = self.timeline_view.status_message.text().strip()
        mode_specific_statuses = {
            "Ready",
            "Video Mode: Annotation enabled",
            "Project Mode: Manage videos and annotations",
        }

        if view_name == "Annotation":
            if current_status in {"", "Video Mode: Annotation enabled", "Project Mode: Manage videos and annotations"}:
                self.set_status_message("Ready")
        elif current_status in mode_specific_statuses:
            self.set_status_message("")

    def set_annotation_mode_enabled(self, enabled):
        """
        Enable or disable annotation mode features.
        
        Args:
            enabled (bool): Whether annotation mode should be enabled
        """
        # Enable or disable action map and timeline views
        if hasattr(self, 'action_map_view'):
            self.action_map_view.setEnabled(enabled)
        
        if hasattr(self, 'timeline_view'):
            self.timeline_view.setEnabled(enabled)
    
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
        
        # CRITICAL FIX: Ensure timeline controls remain visible after state change
        if hasattr(self, 'timeline_view'):
            self.timeline_view.ensure_controls_visible()
        
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

    def stabilize_annotation_layout(self):
        """Force the annotation page layouts to settle after dynamic UI changes."""
        if getattr(self, '_disable_manual_layout_stabilization', False):
            if getattr(self, '_layout_diagnostics_enabled', False):
                self.logger.info("[LAYOUT_DIAG] stabilize_annotation_layout skipped (manual stabilization disabled)")
            self.schedule_layout_diagnostic_snapshots("stabilize_skipped")
            return
        if not hasattr(self, 'annotation_layout'):
            return

        self.sync_annotation_panel_heights()
        self.sync_right_column_panel_heights()

        splitter_sizes = self.upper_splitter.sizes() if hasattr(self, 'upper_splitter') else None

        widgets = [
            self.recording_control_view,
            self.action_map_view,
            self.right_widget,
            self.video_player_view,
            self.upper_splitter,
            self.timeline_view,
            self.annotation_widget,
            self.central_widget,
        ]

        for widget in widgets:
            if widget is not None:
                widget.updateGeometry()

        if hasattr(self, 'right_layout'):
            self.right_layout.activate()
        self.annotation_layout.activate()

        if splitter_sizes:
            self.upper_splitter.setSizes(splitter_sizes)

        self.sync_annotation_panel_heights()
        self.sync_right_column_panel_heights()

        if hasattr(self, 'timeline_view'):
            self.timeline_view.ensure_controls_visible()

        self.central_widget.updateGeometry()
        self.central_widget.update()

    def sync_annotation_panel_heights(self):
        """Temporarily pin the upper annotation area so the timeline row keeps its space."""
        if getattr(self, '_disable_manual_layout_stabilization', False):
            return
        if not hasattr(self, 'upper_splitter') or not hasattr(self, 'timeline_view'):
            return
        if hasattr(self, 'stacked_widget') and self.stacked_widget.currentWidget() != self.annotation_widget:
            return

        available_height = self.annotation_widget.contentsRect().height()
        if available_height <= 0:
            return

        spacing = self.annotation_layout.spacing()
        timeline_height = self.timeline_view.maximumHeight()
        if timeline_height < 0:
            timeline_height = 0

        upper_height = max(0, available_height - timeline_height - spacing)
        if upper_height <= 0:
            return

        self.upper_splitter.setMinimumHeight(upper_height)
        self.upper_splitter.setMaximumHeight(upper_height)
        self.upper_splitter.updateGeometry()

    def sync_right_column_panel_heights(self):
        """Keep the Action Map confined to the remaining height in the right column."""
        if getattr(self, '_disable_manual_layout_stabilization', False):
            return
        if not hasattr(self, 'right_widget') or not hasattr(self, 'action_map_view'):
            return
        if hasattr(self, 'stacked_widget') and self.stacked_widget.currentWidget() != self.annotation_widget:
            return

        available_height = self.right_widget.contentsRect().height()
        if available_height <= 0:
            return

        recording_height = self.recording_control_view.height()
        if recording_height <= 0:
            recording_height = self.recording_control_view.sizeHint().height()

        spacing = self.right_layout.spacing()
        action_map_height = max(120, available_height - recording_height - spacing)

        self.action_map_view.setMinimumHeight(action_map_height)
        self.action_map_view.setMaximumHeight(action_map_height)
        self.action_map_view.updateGeometry()

    def release_annotation_panel_height_constraints(self):
        """Release temporary height constraints after the layout has stabilized."""
        if getattr(self, '_disable_manual_layout_stabilization', False):
            return
        if not hasattr(self, 'upper_splitter'):
            return
        self.upper_splitter.setMinimumHeight(0)
        self.upper_splitter.setMaximumHeight(16777215)
        self.upper_splitter.updateGeometry()
        self.sync_right_column_panel_heights()

    def schedule_annotation_layout_stabilization(self):
        """Run layout stabilization after recording-state UI changes, then release the temporary clamp."""
        if getattr(self, '_disable_manual_layout_stabilization', False):
            if getattr(self, '_layout_diagnostics_enabled', False):
                self.logger.info("[LAYOUT_DIAG] schedule_annotation_layout_stabilization skipped (manual stabilization disabled)")
            self.schedule_layout_diagnostic_snapshots("schedule_stabilization_skipped")
            return
        QTimer.singleShot(0, self.stabilize_annotation_layout)
        QTimer.singleShot(50, self.stabilize_annotation_layout)
        QTimer.singleShot(140, self.release_annotation_panel_height_constraints)
        
    def resetFocus(self):
        """Reset focus to the main window to handle keyboard shortcuts."""
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._need_focus_reset = False
        self.logger.debug("Focus reset to main window")
    
    def installGlobalFocusTracking(self):
        """Install event filters on the specific widgets we need to monitor.

        Previously we installed an event filter on ``QApplication.instance()``
        which fires for every Qt event in the entire application. Now we only
        watch the controls that should auto-return focus to the main window,
        which significantly reduces event-filter overhead on every mouse move.
        """
        self.logger.info("Installing focus tracking on specific widgets")

        # Single, reusable timer for resetting focus to the main window. Using
        # one QTimer instance and re-arming it via ``start()`` avoids the
        # allocation churn of ``QTimer.singleShot`` on every mouse click.
        self._focus_reset_timer = QTimer(self)
        self._focus_reset_timer.setSingleShot(True)
        self._focus_reset_timer.setInterval(3000)
        self._focus_reset_timer.timeout.connect(self.resetFocus)

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
            self.action_map_view.active_behaviors,
        ]

        for widget in focus_managed_widgets:
            widget.installEventFilter(self)

        # Add hover tracking to step buttons
        self.video_player_view.step_forward_button.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.video_player_view.step_backward_button.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        self.logger.debug(f"Installed event filters on {len(focus_managed_widgets)} widgets")

    def _schedule_focus_reset(self):
        """Re-arm the shared focus-reset timer (single allocation)."""
        if not hasattr(self, '_focus_reset_timer'):
            return
        self._focus_reset_timer.start()

    def eventFilter(self, watched, event):
        """
        Event filter for the specific widgets installed in
        ``installGlobalFocusTracking``. Returns ``False`` so the event still
        reaches the normal handler.
        """
        # Honour exclusions for input widgets in views that need to keep focus
        current_view = self.stacked_widget.currentWidget()

        if ((hasattr(self, 'analysis_view') and current_view == self.analysis_view and
             hasattr(self.analysis_view, 'interval_seconds_spinner') and
             watched == self.analysis_view.interval_seconds_spinner) or
            (hasattr(self, 'visualization_view') and current_view == self.visualization_view)):
            return super().eventFilter(watched, event)

        event_type = event.type()
        if event_type == event.Type.MouseButtonRelease and watched is not self:
            self._last_clicked_widget = watched
            self._need_focus_reset = True
            self._schedule_focus_reset()
        elif event_type == event.Type.FocusOut:
            if watched in (self.video_player_view.step_size_spin,
                           self.recording_control_view.duration_time_edit):
                self._need_focus_reset = True
                self._schedule_focus_reset()

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
        
        # Check if frame-by-frame mode is enabled
        if self.video_player_view.is_frame_by_frame_mode():
            # In frame-by-frame mode, override step size to use exactly one frame
            # Get frame duration from video model via controller
            if hasattr(self, 'annotation_controller') and hasattr(self.annotation_controller, '_frame_duration_ms'):
                frame_step = self.annotation_controller._frame_duration_ms
            else:
                # Default to 33ms if frame duration is not available (30fps)
                frame_step = 33
            
            self.logger.debug(f"Frame-by-frame mode: using step size of {frame_step}ms (one frame)")
            
            # Right arrow - step forward one frame
            if event.key() == Qt.Key.Key_Right:
                self.logger.debug("Right arrow pressed in frame-by-frame mode - stepping forward one frame")
                self.video_player_view.step_forward_clicked.emit(frame_step)
                return
                
            # Left arrow - step backward one frame
            if event.key() == Qt.Key.Key_Left:
                self.logger.debug("Left arrow pressed in frame-by-frame mode - stepping backward one frame")
                self.video_player_view.step_backward_clicked.emit(frame_step)
                return
        else:
            # Normal mode - use configured step size
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
            
        # 1.3.3+: Esc is the emergency escape hatch for stuck active
        # events. Routed straight to the annotation controller, which
        # prompts for confirmation before discarding anything.
        if event.key() == Qt.Key.Key_Escape and not event.isAutoRepeat():
            annotation_controller = getattr(self, 'annotation_controller', None)
            if annotation_controller is not None and hasattr(
                annotation_controller, 'abort_all_active_events'
            ):
                try:
                    annotation_controller.abort_all_active_events()
                except Exception:
                    self.logger.exception(
                        "Esc handler: abort_all_active_events raised"
                    )
                event.accept()
                return

        # Convert key to string for normal key handling
        key = event.text()

        # Check if in waiting state for recording
        if self.recording_control_view.is_in_waiting_state():
            # Start actual recording upon any key press
            if key and not event.isAutoRepeat():
                self.logger.debug("Starting recording from waiting state")
                self.recording_control_view.start_recording()
                self.schedule_layout_diagnostic_snapshots("waiting_key_started_recording")
                
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
            self._sync_toolbar_status_for_view(view_name)
            
            # Update action check state for both menu and toolbar
            for action in self.mode_group.actions():
                if action.text() == f"{view_name} Mode":
                    action.setChecked(True)
                    break
            
            # Update toolbar buttons separately
            if view_name == "Annotation":
                self.annotation_mode_toolbar_action.setChecked(True)
                self.analysis_mode_toolbar_action.setChecked(False)
                self.visualization_mode_toolbar_action.setChecked(False)
                self.reliability_mode_toolbar_action.setChecked(False)
                if hasattr(self, 'project_mode_toolbar_action'):
                    self.project_mode_toolbar_action.setChecked(False)
                QTimer.singleShot(0, self.video_player_view.refresh_empty_placeholder)
            elif view_name == "Analysis":
                self.annotation_mode_toolbar_action.setChecked(False)
                self.analysis_mode_toolbar_action.setChecked(True)
                self.visualization_mode_toolbar_action.setChecked(False)
                self.reliability_mode_toolbar_action.setChecked(False)
                if hasattr(self, 'project_mode_toolbar_action'):
                    self.project_mode_toolbar_action.setChecked(False)
            elif view_name == "Visualization":
                self.annotation_mode_toolbar_action.setChecked(False)
                self.analysis_mode_toolbar_action.setChecked(False)
                self.visualization_mode_toolbar_action.setChecked(True)
                self.reliability_mode_toolbar_action.setChecked(False)
                if hasattr(self, 'project_mode_toolbar_action'):
                    self.project_mode_toolbar_action.setChecked(False)
            elif view_name == "Reliability":
                self.annotation_mode_toolbar_action.setChecked(False)
                self.analysis_mode_toolbar_action.setChecked(False)
                self.visualization_mode_toolbar_action.setChecked(False)
                self.reliability_mode_toolbar_action.setChecked(True)
                if hasattr(self, 'project_mode_toolbar_action'):
                    self.project_mode_toolbar_action.setChecked(False)
            elif view_name == "Project":
                self.annotation_mode_toolbar_action.setChecked(False)
                self.analysis_mode_toolbar_action.setChecked(False)
                self.visualization_mode_toolbar_action.setChecked(False)
                self.reliability_mode_toolbar_action.setChecked(False)
                if hasattr(self, 'project_mode_toolbar_action'):
                    self.project_mode_toolbar_action.setChecked(True)
        else:
            self.logger.warning(f"View not found: {view_name}")
    
    def set_status_message(self, message):
        """
        Set status bar message.
        
        Args:
            message (str): Status message
        """
        self.timeline_view.set_status_message(message)
    
    def set_video_info(self, info):
        """
        Set video information in status bar.
        
        Args:
            info (str): Video information
        """
        self.timeline_view.set_video_info(info)
    
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
            
            # Don't automatically add menu actions or toolbar buttons
            # They are now added explicitly in create_menus() and setup_toolbar()
            
            self.logger.debug(f"Added view: {name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to add view {name}: {str(e)}")
            return False

    def _current_view_name(self):
        """Return the name of the currently visible top-level view."""
        current_index = self.stacked_widget.currentIndex()
        for name, index in self._view_index.items():
            if index == current_index:
                return name
        return ""

    def _view_by_name(self, name):
        """Return a top-level view widget by registered name."""
        index = self._view_index.get(name)
        if index is None:
            return None
        return self.stacked_widget.widget(index)
    
    # ------------------------------------------------------------------ #
    # Recent Files menus
    # ------------------------------------------------------------------ #

    def _populate_recent_videos_menu(self):
        """Refresh the "Open Recent Video" submenu when it is about to show."""
        self._populate_recent_menu(
            self.recent_videos_menu,
            file_type="videos",
            on_select=self._open_recent_video,
        )

    def _populate_recent_annotations_menu(self):
        """Refresh the "Recent Annotations" submenu when it is about to show."""
        self._populate_recent_menu(
            self.recent_annotations_menu,
            file_type="annotations",
            on_select=self._open_recent_annotation,
        )

    def _populate_recent_menu(self, menu, file_type, on_select):
        """
        Dynamically build a submenu of recent files.

        Args:
            menu (QMenu): Target submenu to clear and rebuild.
            file_type (str): ConfigManager key (e.g. ``"videos"``).
            on_select (callable): Function called with the selected path.
        """
        menu.clear()

        config_manager = getattr(self, "config_manager", None)
        if config_manager is None:
            disabled = menu.addAction("(Settings unavailable)")
            disabled.setEnabled(False)
            return

        try:
            recent = config_manager.get_recent_files(file_type) or []
        except Exception as exc:
            self.logger.warning(f"Failed to read recent {file_type}: {exc}")
            recent = []

        if not recent:
            disabled = menu.addAction("(No recent files)")
            disabled.setEnabled(False)
            return

        # Action for each path. We capture ``path`` via default argument so the
        # lambda doesn't close over the loop variable.
        for path in recent:
            label = os.path.basename(path) or path
            action = menu.addAction(f"{label}    -    {path}")
            action.setToolTip(path)
            action.triggered.connect(lambda _checked=False, p=path: on_select(p))

        menu.addSeparator()
        clear_action = menu.addAction("Clear Recent Files")
        clear_action.triggered.connect(lambda _checked=False, t=file_type: self._clear_recent_files(t))

    def _open_recent_video(self, path):
        """Trigger the video controller to load ``path``."""
        video_controller = getattr(self, "video_controller", None)
        if video_controller is None:
            self.show_error("Video controller is unavailable.")
            return
        if not os.path.exists(path):
            self.show_error(f"File not found:\n{path}")
            return
        video_controller.load_video(path)

    def _open_recent_annotation(self, path):
        """Trigger the annotation controller to import ``path``."""
        annotation_controller = getattr(self, "annotation_controller", None)
        if annotation_controller is None:
            self.show_error("Annotation controller is unavailable.")
            return
        if not os.path.exists(path):
            self.show_error(f"File not found:\n{path}")
            return
        # Drop existing annotations only after confirmation if any exist.
        if annotation_controller._annotation_model.get_all_events():
            from PySide6.QtWidgets import QMessageBox
            result = QMessageBox.question(
                self,
                "Existing Annotations",
                "Importing will replace the existing annotations. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if result != QMessageBox.StandardButton.Yes:
                return
        if annotation_controller.import_annotations_from_file(path):
            self.set_status_message(f"Annotations imported from {path}")

    def _clear_recent_files(self, file_type):
        """Empty the recent-files list for the given category."""
        config_manager = getattr(self, "config_manager", None)
        if config_manager is None:
            return
        try:
            config_manager.set("recent_files", file_type, [])
            config_manager.save_config()
            self.set_status_message(f"Cleared recent {file_type}.")
        except Exception as exc:
            self.logger.warning(f"Failed to clear recent {file_type}: {exc}")

    def set_config_manager(self, config_manager):
        """
        Attach the application's ConfigManager and restore persisted settings.

        Called by AppController once the rest of the GUI is wired up so that
        restored settings can flow into child views (recording duration,
        interval analysis options, etc.).
        """
        self.config_manager = config_manager
        self._restore_settings()

    def _restore_settings(self):
        """Apply user-persisted settings to the window and child views."""
        if self.config_manager is None or self._settings_restored:
            return

        try:
            ui = self.config_manager.get("ui") or {}

            geometry = ui.get("window_geometry")
            if isinstance(geometry, (list, tuple)) and len(geometry) == 4:
                try:
                    x, y, w, h = (int(v) for v in geometry)
                    self.move(x, y)
                    self.resize(w, h)
                except (TypeError, ValueError):
                    self.logger.warning("Ignoring malformed window_geometry: %r", geometry)

            last_view = ui.get("last_view")
            if isinstance(last_view, str) and last_view in self._view_index:
                # Defer the view switch until after the main loop is running
                # so child widgets are fully laid out.
                QTimer.singleShot(0, lambda v=last_view: self.switch_to_view(v))

            # Propagate analysis interval settings to the AnalysisView so the
            # spinner / checkbox come up with the user's previous choice.
            analysis_section = self.config_manager.get("analysis") or {}
            interval_enabled = bool(analysis_section.get("interval_enabled", False))
            interval_seconds = int(analysis_section.get("interval_seconds", 60) or 60)
            if hasattr(self, 'analysis_view') and hasattr(self.analysis_view, 'set_interval_settings'):
                self.analysis_view.set_interval_settings(interval_enabled, interval_seconds)

            # Restore recording-control preferences.
            annotation_section = self.config_manager.get("annotation") or {}
            if hasattr(self, 'recording_control_view'):
                from PySide6.QtCore import QTime
                rcv = self.recording_control_view
                rcv.duration_time_edit.setTime(QTime(
                    int(annotation_section.get("last_recording_hours", 0) or 0),
                    int(annotation_section.get("last_recording_minutes", 5) or 5),
                    int(annotation_section.get("last_recording_seconds", 0) or 0),
                ))
                rcv.preserve_annotations_checkbox.setChecked(
                    bool(annotation_section.get("preserve_on_rewind", False))
                )

            # Video-player preferences (step size, playback rate, volume,
            # frame-by-frame). Each control's blockSignals() / setValue() pair
            # avoids re-emitting on restore. Slider values are integers in
            # the same units the UI uses.
            video_section = self.config_manager.get("video") or {}
            if hasattr(self, 'video_player_view'):
                vpv = self.video_player_view

                step_ms = int(video_section.get("default_step_size_ms", 100) or 100)
                vpv.step_size_spin.blockSignals(True)
                vpv.step_size_spin.setValue(max(vpv.step_size_spin.minimum(),
                                                min(step_ms, vpv.step_size_spin.maximum())))
                vpv.step_size_spin.blockSignals(False)

                rate = float(video_section.get("default_playback_rate", 1.0) or 1.0)
                rate_value = int(round(rate * 100))
                vpv.rate_slider.blockSignals(True)
                vpv.rate_slider.setValue(max(vpv.rate_slider.minimum(),
                                             min(rate_value, vpv.rate_slider.maximum())))
                vpv.rate_slider.blockSignals(False)
                vpv.rate_value_label.setText(f"{rate:.2f}x")

                # NOTE (1.3.1): volume restoration was removed along with
                # audio playback in the PyAV migration. The setting value
                # is left in settings.json so older builds can still read
                # it; we just don't apply it here.

                fbf = bool(video_section.get("enable_frame_by_frame", False))
                vpv.frame_by_frame_checkbox.blockSignals(True)
                vpv.frame_by_frame_checkbox.setChecked(fbf)
                vpv.frame_by_frame_checkbox.blockSignals(False)
                vpv._frame_by_frame_mode = fbf

            # Timeline zoom level.
            if hasattr(self, 'timeline_view'):
                zoom = int(annotation_section.get("timeline_zoom_level",
                                                  self.timeline_view._zoom_level)
                           or self.timeline_view._zoom_level)
                self.timeline_view.zoom_slider.blockSignals(True)
                self.timeline_view.zoom_slider.setValue(
                    max(self.timeline_view.zoom_slider.minimum(),
                        min(zoom, self.timeline_view.zoom_slider.maximum()))
                )
                self.timeline_view.zoom_slider.blockSignals(False)
                # Mirror the value into the internal state so subsequent
                # repaints use the restored zoom even before the slider
                # change signal is fired manually.
                self.timeline_view._zoom_level = zoom

            # Annotation page splitter (video / right column).
            splitter_sizes = ui.get("upper_splitter_sizes")
            if (isinstance(splitter_sizes, (list, tuple))
                    and len(splitter_sizes) == 2
                    and hasattr(self, 'upper_splitter')):
                try:
                    sizes = [int(v) for v in splitter_sizes]
                    if all(s >= 0 for s in sizes) and sum(sizes) > 0:
                        self.upper_splitter.setSizes(sizes)
                except (TypeError, ValueError):
                    self.logger.warning("Ignoring malformed upper_splitter_sizes: %r", splitter_sizes)

            self._settings_restored = True
            self.logger.info("Restored persisted UI settings")
        except Exception as exc:
            self.logger.warning("Failed to restore settings: %s", exc, exc_info=True)

    def _persist_settings(self):
        """Save current window/child settings to ConfigManager and disk."""
        if self.config_manager is None:
            return

        try:
            # Window geometry
            frame = self.geometry()
            self.config_manager.set("ui", "window_geometry",
                                    [frame.x(), frame.y(), frame.width(), frame.height()])

            # Last active view: look up the index → name mapping
            current_index = self.stacked_widget.currentIndex()
            for name, idx in self._view_index.items():
                if idx == current_index:
                    self.config_manager.set("ui", "last_view", name)
                    break

            # Analysis interval settings
            if hasattr(self, 'analysis_view'):
                enabled, seconds = self.analysis_view.get_interval_settings()
                self.config_manager.set("analysis", "interval_enabled", bool(enabled))
                self.config_manager.set("analysis", "interval_seconds", int(seconds))

            # Recording-control preferences
            if hasattr(self, 'recording_control_view'):
                qtime = self.recording_control_view.duration_time_edit.time()
                self.config_manager.set("annotation", "last_recording_hours", qtime.hour())
                self.config_manager.set("annotation", "last_recording_minutes", qtime.minute())
                self.config_manager.set("annotation", "last_recording_seconds", qtime.second())
                self.config_manager.set(
                    "annotation",
                    "preserve_on_rewind",
                    self.recording_control_view.preserve_annotations_checkbox.isChecked(),
                )

            # Video-player preferences. Slider values are stored in the same
            # units the UI exposes them in (ms, percent, 0-100 volume).
            if hasattr(self, 'video_player_view'):
                vpv = self.video_player_view
                self.config_manager.set("video", "default_step_size_ms",
                                        int(vpv.step_size_spin.value()))
                self.config_manager.set("video", "default_playback_rate",
                                        float(vpv.rate_slider.value()) / 100.0)
                # ``default_volume`` no longer persisted as of 1.3.1
                # (audio playback removed). Reading still works for
                # backward-compat on older settings files.
                self.config_manager.set("video", "enable_frame_by_frame",
                                        bool(vpv.frame_by_frame_checkbox.isChecked()))

            # Timeline zoom.
            if hasattr(self, 'timeline_view'):
                self.config_manager.set("annotation", "timeline_zoom_level",
                                        int(self.timeline_view.zoom_slider.value()))

            # Annotation page splitter sizes.
            if hasattr(self, 'upper_splitter'):
                self.config_manager.set("ui", "upper_splitter_sizes",
                                        list(self.upper_splitter.sizes()))

            self.config_manager.save_config()
            self.logger.info("Persisted UI settings to disk")
        except Exception as exc:
            self.logger.warning("Failed to persist settings: %s", exc, exc_info=True)

    def closeEvent(self, event):
        """Persist user settings before the window actually closes."""
        self._persist_settings()
        super().closeEvent(event)

    # ------------------------------------------------------------------ #
    # Global Drag & Drop
    # ------------------------------------------------------------------ #

    # Recognised by the global handler. The per-view drop zones keep their
    # own filters; this is purely a fallback so users do not have to aim
    # at the right pane.
    #
    # Video acceptance now goes through utils.video_detection.is_video_file,
    # which cascades extension whitelist -> magic-number sniff -> PyAV
    # trial-open. The extension tuple below is kept as a convenience for
    # docs/log messages but is no longer the authoritative gate.
    _CSV_EXTS = (".csv",)

    def _classify_dropped_paths(self, urls):
        """Split dropped URLs into recognised video / CSV / unsupported buckets."""
        videos = []
        csvs = []
        for url in urls:
            local_path = url.toLocalFile()
            if not local_path:
                continue
            lower = local_path.lower()
            if lower.endswith(self._CSV_EXTS):
                csvs.append(local_path)
            elif is_video_file(local_path):
                videos.append(local_path)
        return videos, csvs

    def dragEnterEvent(self, event):
        """Accept a drag if it contains at least one recognised file."""
        mime = event.mimeData()
        if not mime.hasUrls():
            event.ignore()
            return

        videos, csvs = self._classify_dropped_paths(mime.urls())
        if videos or csvs:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        # Re-use the same classification so the cursor reflects acceptance.
        if event.mimeData().hasUrls():
            videos, csvs = self._classify_dropped_paths(event.mimeData().urls())
            if videos or csvs:
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        """Route dropped files to the appropriate controller."""
        mime = event.mimeData()
        if not mime.hasUrls():
            event.ignore()
            return

        videos, csvs = self._classify_dropped_paths(mime.urls())
        if not videos and not csvs:
            event.ignore()
            return

        event.acceptProposedAction()

        # Video drops: switch to the annotation view and load the first
        # recognised file (RABET only handles a single active video).
        if videos:
            self.switch_to_view("Annotation")
            video_controller = getattr(self, "video_controller", None)
            if video_controller is not None:
                video_controller.load_video(videos[0])
            else:
                self.show_error("Video controller is not available yet.")

        # CSV drops are delivered to the analysis view's existing handler so
        # behaviour stays consistent with dropping them directly on that pane.
        # If Visualization is already visible, keep the drop in Visualization.
        # This covers edge drops around the Visualization drop label where Qt
        # can let the global MainWindow fallback see the event first.
        if csvs:
            if self._current_view_name() == "Visualization":
                self.switch_to_view("Visualization")
                visualization_view = self._view_by_name("Visualization")
                if visualization_view is not None:
                    visualization_view.files_dropped.emit(csvs)
            elif hasattr(self, "analysis_view"):
                self.switch_to_view("Analysis")
                self.analysis_view.files_dropped.emit(csvs)

    def showEvent(self, event):
        """Handle window show event to ensure icon is properly set."""
        super().showEvent(event)

        # Ensure icon is properly set
        if self.windowIcon().isNull():
            self.setup_window_icon()
        self.schedule_layout_diagnostic_snapshots("main_window_show")

    def resizeEvent(self, event):
        """Keep the right annotation column from claiming extra height after resizes."""
        super().resizeEvent(event)
        if not getattr(self, '_disable_manual_layout_stabilization', False):
            self.sync_right_column_panel_heights()
        if getattr(self, '_layout_diagnostics_enabled', False):
            old_size = event.oldSize()
            new_size = event.size()
            self.logger.info(
                "[LAYOUT_DIAG] main_window_resize_event "
                f"old={old_size.width()}x{old_size.height()} "
                f"new={new_size.width()}x{new_size.height()}"
            )
            self.log_annotation_layout_snapshot("main_window_resize")
