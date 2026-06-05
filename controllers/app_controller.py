# controllers/app_controller.py - Updated with icon management, theme integration, and visualization support
import logging
from version import __version__
from PySide6.QtCore import QObject, Slot, QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout

from models.video_model import VideoModel
from models.action_map_model import ActionMapModel
from models.annotation_model import AnnotationModel
# AnalysisModel: lazily imported in _ensure_analysis (PR-STARTUP-04) so pandas
# stays out of the startup path (Annotation-first shell).
from models.project_model import ProjectModel

from views.main_window import MainWindow
from views.project_view import ProjectView
from views.log_viewer_dialog import LogViewerDialog
# NOTE (PR-STARTUP-02): VisualizationView / ReliabilityView are imported lazily
# inside _ensure_visualization / _ensure_reliability so matplotlib (and the
# reliability stats stack) do not load at startup -- Annotation-first shell.

from controllers.video_controller import VideoController
from controllers.annotation_controller import AnnotationController
from controllers.action_map_controller import ActionMapController
# AnalysisController: lazily imported in _ensure_analysis (PR-STARTUP-04).
from controllers.project_controller import ProjectController
# VisualizationController / ReliabilityController: lazily imported in
# _ensure_visualization / _ensure_reliability (see note above).

from utils.file_manager import FileManager
from utils.log_manager import LogManager
from utils.theme_manager import ThemeManager
from utils.config_manager import ConfigManager
from utils.app_icon import find_app_icon_path

class AppController(QObject):
    """
    Main application controller that coordinates other controllers.
    """
    
    def __init__(self, development_mode=False):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing AppController")
        
        # Store development mode flag
        self.development_mode = development_mode
        
        # Initialize file manager
        self.file_manager = FileManager()

        # Application-wide settings persistence (window geometry, recent
        # files, last directories, etc.). Lives in the user-data dir managed
        # by FileManager.
        self.config_manager = ConfigManager(self.file_manager)

        # Initialize log manager
        self.log_manager = LogManager()

        # Initialize theme manager
        self.theme_manager = ThemeManager()
        
        # Schedule periodic log cleanup
        self.log_cleanup_timer = QTimer(self)
        self.log_cleanup_timer.setInterval(24 * 60 * 60 * 1000)  # 24 hours
        self.log_cleanup_timer.timeout.connect(self.perform_log_cleanup)
        self.log_cleanup_timer.start()

        # Application directories are ensured in ``main.py`` before the
        # QApplication is created; no duplicate call is necessary here.

        # Initialize models
        self.video_model = VideoModel()
        # Stop the video decode worker thread cleanly on application exit (the
        # model runs PyAV on its own QThread, A-1).
        from PySide6.QtWidgets import QApplication
        _app = QApplication.instance()
        if _app is not None:
            _app.aboutToQuit.connect(self.video_model.shutdown)
        self.action_map_model = ActionMapModel()
        self.annotation_model = AnnotationModel(self.action_map_model, self.video_model)
        # Analysis is lazy (PR-STARTUP-04): AnalysisModel/AnalysisController pull
        # in pandas, so they are built in _ensure_analysis on first switch to the
        # Analysis tab. The AnalysisView itself is light and stays eager.
        self.analysis_model = None
        self.analysis_controller = None
        self.project_model = ProjectModel(self.file_manager)
        
        # Initialize main window
        self.main_window = MainWindow()
        
        # Set application window icon
        self.set_application_icon()
        
        # Register the (eager, light) Analysis view as a lazy tab so its
        # model/controller (which pull in pandas) build on first switch
        # (PR-STARTUP-04). MainWindow no longer adds analysis_view to the stack.
        self.main_window.register_lazy_view(
            "Analysis", self.main_window.analysis_view, self._ensure_analysis
        )

        # Initialize project view
        self.project_view = ProjectView()

        # Add the (lightweight) Project view eagerly.
        self.main_window.add_view("Project", self.project_view)

        # Visualization and Reliability are matplotlib-backed and dominate
        # startup construction time. Build them lazily on first tab switch
        # (Phase 5-2): a placeholder container reserves each stack slot now, and
        # _ensure_visualization / _ensure_reliability populate it on demand.
        self.visualization_view = None
        self.visualization_controller = None
        self._visualization_container = QWidget()
        QVBoxLayout(self._visualization_container).setContentsMargins(0, 0, 0, 0)
        self.main_window.register_lazy_view(
            "Visualization", self._visualization_container, self._ensure_visualization
        )

        self.reliability_view = None
        self.reliability_controller = None
        self._reliability_container = QWidget()
        QVBoxLayout(self._reliability_container).setContentsMargins(0, 0, 0, 0)
        self.main_window.register_lazy_view(
            "Reliability", self._reliability_container, self._ensure_reliability
        )
        
        # Initialize controllers
        self.video_controller = VideoController(self.video_model, self.main_window.video_player_view)
        self.action_map_controller = ActionMapController(self.action_map_model, self.main_window.action_map_view)
        self.annotation_controller = AnnotationController(
            self.annotation_model, 
            self.video_model,
            self.main_window,
            self.main_window.timeline_view
        )
        # analysis_controller is built lazily in _ensure_analysis (None for now);
        # project_controller only stores the reference and never calls it.
        self.project_controller = ProjectController(
            self.project_model,
            self.project_view,
            self.video_controller,
            self.action_map_controller,
            self.annotation_controller,
            self.analysis_controller
        )
        
        # Visualization / Reliability controllers are created lazily alongside
        # their views (see _ensure_visualization / _ensure_reliability). The
        # analysis -> visualize bridge is wired eagerly; its handler builds the
        # Visualization tab on demand.
        self.main_window.analysis_view.visualize_files_requested.connect(
            self.handle_analysis_visualize_requested
        )
        
        # Provide the annotation controller reference to the main window
        self.main_window.annotation_controller = self.annotation_controller

        # Route every close path (X button, Alt+F4, File > Exit) through one
        # unsaved-data guard (BUG-003).
        self.main_window.set_close_guard(self.confirm_application_close)

        # React to the whole application losing focus during a recording
        # session (§16-3 / BUG-022). Bound to applicationStateChanged so it
        # fires only on app-level (in)activation, never on in-window focus
        # changes.
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.applicationStateChanged.connect(self._on_application_state_changed)
        except Exception:
            self.logger.exception("Failed to connect applicationStateChanged")

        # Connect main window signals
        self.connect_main_window_signals()
        
        # Connect the preserve_annotations_changed signal
        self.main_window.recording_control_view.preserve_annotations_changed.connect(
            self.annotation_controller.set_preserve_annotations
        )

        self.connect_action_map_to_timeline()

        # Check if action map loaded successfully
        if not self.action_map_model.is_loaded():
            self.logger.warning("Action map failed to load from files, using fallback")
            # The model will have already created a default, so we don't need to do anything

        # Wire persistence: hand the ConfigManager to MainWindow so it can
        # restore saved geometry / view / recording-control / analysis
        # interval settings now that all child widgets are constructed and
        # signals are connected. The window will also save these on close.
        self.main_window.set_config_manager(self.config_manager)

        # Controllers that need to record "recently opened" files (Recent
        # Files menu) also receive a reference to ConfigManager.
        self.video_controller.config_manager = self.config_manager
        self.video_controller.project_model = self.project_model
        self.annotation_controller.config_manager = self.config_manager
        # The Reliability tab's ConfigManager wiring (picker-directory memory)
        # now happens in _ensure_reliability when that tab is first built.

        # Expose the video controller on main_window so menu actions
        # (e.g. Open Recent Video) can drive video loads without going
        # through AppController plumbing.
        self.main_window.video_controller = self.video_controller
    
    def connect_action_map_to_timeline(self):
        """Connect action map changes to timeline color management."""
        
        # Connect the action map model's mapping_removed signal to timeline
        self.action_map_model.mapping_removed.connect(
            self.main_window.timeline_view.on_behavior_removed
        )
        
        self.logger.info("Connected action map changes to timeline color management")

    # Handle files dropped on visualization view
    def handle_visualization_files_dropped(self, file_paths):
        """
        Handle files dropped on the visualization view.
        This ensures the main window stays in visualization mode while the
        visualization controller handles the actual file load.
        
        Args:
            file_paths (list): List of dropped file paths
        """
        self.logger.info(f"App controller handling {len(file_paths)} files dropped on visualization view")
        
        # Ensure we stay in visualization view
        self.main_window.switch_to_view("Visualization")

    @Slot()
    def handle_analysis_visualize_requested(self):
        """Load the files currently in Analysis into Visualization."""
        # The visualize bridge is wired eagerly to the (eager) AnalysisView, so
        # ensure the lazy Analysis model/controller exist before reading them.
        self._ensure_analysis()
        file_paths = self.analysis_model.get_file_paths()
        if not file_paths:
            self.main_window.show_info("No annotation files are loaded in Analysis.")
            return

        # Build the Visualization tab on demand if the user has not opened it yet.
        self._ensure_visualization()
        self.visualization_controller.load_files(file_paths)
        self.main_window.switch_to_view("Visualization")

    def _warm_up_lazy_tabs(self):
        """Build the heavy lazy tabs (Visualization / Reliability / Analysis) in
        the background, one per idle tick, so the first on-screen switch to them
        is smooth. Runs after the window is shown so it does not slow startup;
        each builder is idempotent and exception-safe."""
        builders = [
            self._ensure_visualization,
            self._ensure_reliability,
            self._ensure_analysis,
        ]

        def _run_next(index):
            if index >= len(builders):
                self.logger.info("Lazy tabs warm-up complete")
                return
            try:
                builders[index]()
            except Exception:
                self.logger.exception("Background warm-up of a lazy tab failed")
            # Next builder on a fresh idle tick so we never block the UI in one
            # chunk (keeps recording/playback responsive during warm-up).
            QTimer.singleShot(0, lambda: _run_next(index + 1))

        _run_next(0)

    def _ensure_analysis(self):
        """Lazily construct the Analysis model + controller (PR-STARTUP-04).

        AnalysisView is built eagerly by MainWindow (it does not import pandas),
        but AnalysisModel/AnalysisController do, so they are created here on the
        first switch to the Analysis tab -- keeping pandas off the startup path.
        Idempotent.
        """
        if self.analysis_model is not None:
            return
        from controllers.analysis_controller import AnalysisController
        from models.analysis_model import AnalysisModel
        self.analysis_model = AnalysisModel()
        self.analysis_controller = AnalysisController(
            self.analysis_model, self.main_window.analysis_view
        )
        # project_controller kept a None placeholder; keep it consistent (it only
        # stores the reference today, never calls it).
        if hasattr(self, "project_controller"):
            self.project_controller._analysis_controller = self.analysis_controller
        self.analysis_model.error_occurred.connect(self.main_window.show_error)
        self.logger.info("Analysis tab constructed lazily")

    def _ensure_visualization(self):
        """Lazily construct the Visualization view + controller (Phase 5-2).

        Idempotent: safe to call from the tab-switch builder, the analysis ->
        visualize bridge, and the drop handler.
        """
        if self.visualization_view is not None:
            return
        # Lazy import (PR-STARTUP-02): matplotlib loads only on first open.
        from controllers.visualization_controller import VisualizationController
        from views.visualization_view import VisualizationView
        self.visualization_view = VisualizationView()
        self._visualization_container.layout().addWidget(self.visualization_view)
        self.visualization_controller = VisualizationController(
            self.visualization_view,
            config_manager=self.config_manager,
        )
        self.visualization_view.files_dropped.connect(
            self.handle_visualization_files_dropped
        )
        self.logger.info("Visualization tab constructed lazily")

    def _ensure_reliability(self):
        """Lazily construct the Reliability view + controller (Phase 5-2)."""
        if self.reliability_view is not None:
            return
        # Lazy import (PR-STARTUP-02): pingouin/scipy load only on first open.
        from controllers.reliability_controller import ReliabilityController
        from views.reliability_view import ReliabilityView
        self.reliability_view = ReliabilityView()
        self._reliability_container.layout().addWidget(self.reliability_view)
        self.reliability_controller = ReliabilityController(
            self.reliability_view, self
        )
        self.reliability_controller.set_config_manager(self.config_manager)
        self.logger.info("Reliability tab constructed lazily")

    def set_application_icon(self):
        """Set the application and window icons."""
        icon_path = find_app_icon_path()
        
        if not icon_path:
            self.logger.warning("Application icon not found in any of the expected locations")
            return
        
        try:
            self.logger.info(f"Setting application icon from: {icon_path}")
            
            # Create icon
            app_icon = QIcon(icon_path)
            
            # Verify the icon was loaded successfully
            if app_icon.isNull():
                self.logger.error(f"Failed to load icon from {icon_path} - icon is null")
                return
                
            # Set the window icon
            if self.main_window:
                self.main_window.setWindowIcon(app_icon)
                self.logger.info("Window icon set successfully")
        except Exception as e:
            self.logger.error(f"Error setting application icon: {str(e)}")
    
    def show_main_window(self):
        """Show the main application window and center it on screen."""
        # Show the window
        self.main_window.show()
        
        # Center the window on screen
        self.main_window.center_on_screen()
        
        # Ensure the icon is properly set after the window is shown
        # This helps with taskbar icon issues
        if self.main_window and self.main_window.windowIcon().isNull():
            self.set_application_icon()
        
        self.logger.info("Main window shown and centered on screen")

        # Heavy tabs stay lazy so startup remains responsive. Their first
        # access now shows MainWindow's PhaseLoadingOverlay instead of doing a
        # hidden post-launch warm-up that can freeze the annotation workspace.
    
    def connect_main_window_signals(self):
        """Connect main window signals to controllers."""
        # Connect menu actions
        self.main_window.open_video_action.triggered.connect(self.video_controller.open_video_dialog)
        self.main_window.load_action_map_action.triggered.connect(self.action_map_controller.load_action_map_dialog)
        self.main_window.save_action_map_action.triggered.connect(self.action_map_controller.save_action_map_dialog)
        self.main_window.reset_action_map_action.triggered.connect(self.action_map_controller.reset_to_default)
        
        self.main_window.export_annotations_action.triggered.connect(self.annotation_controller.export_annotations_dialog)
        self.main_window.import_annotations_action.triggered.connect(self.annotation_controller.import_annotations_dialog)
        self.main_window.undo_annotation_action.triggered.connect(self.annotation_controller.undo_last_annotation)
        self.main_window.clear_annotations_action.triggered.connect(self.annotation_controller.clear_annotations)
        self.main_window.exit_action.triggered.connect(self.handle_exit_action)
        self.main_window.about_action.triggered.connect(self.show_about_dialog)
        if hasattr(self.main_window, 'shortcuts_action'):
            self.main_window.shortcuts_action.triggered.connect(self.show_shortcuts_dialog)
        
        # Connect log management actions
        if hasattr(self.main_window, 'view_logs_action'):
            self.main_window.view_logs_action.triggered.connect(self.show_log_viewer)
        if hasattr(self.main_window, 'cleanup_logs_action'):
            self.main_window.cleanup_logs_action.triggered.connect(self.perform_log_cleanup)
        
        # Connect video player toggle play function to space key
        self.main_window.video_player_view.toggle_play = self.toggle_play_pause
        
        # Connect error signals
        self.video_model.error_occurred.connect(self.main_window.show_error)
        self.action_map_model.error_occurred.connect(self.main_window.show_error)
        self.annotation_model.error_occurred.connect(self.main_window.show_error)
        # analysis_model.error_occurred is connected in _ensure_analysis (lazy).
        self.project_model.error_occurred.connect(self.main_window.show_error)
    
    def toggle_play_pause(self):
        """Toggle between play and pause states."""
        if self.video_model.is_playing():
            self.video_model.pause()
        else:
            self.video_model.play()

    @Slot(Qt.ApplicationState)
    def _on_application_state_changed(self, state):
        """Forward app-level deactivation to the annotation controller.

        Only ``ApplicationInactive`` (the whole app lost focus) triggers the
        active-event safeguard; other states are ignored.
        """
        if state == Qt.ApplicationState.ApplicationInactive:
            try:
                self.annotation_controller.on_application_inactive()
            except Exception:
                self.logger.exception("on_application_inactive handler failed")
    
    def handle_exit_action(self):
        """Handle File > Exit.

        Routes through ``main_window.close()`` so the single
        ``confirm_application_close`` guard (installed via ``set_close_guard``)
        runs for both the menu action and the OS window-close (BUG-003).
        """
        self.main_window.close()

    def confirm_application_close(self):
        """Unsaved-data guard run before the application window closes.

        Order (BUG-003): stop any recording and finalise active events, then
        prompt about unsaved in-memory annotations, then about an unsaved
        project. Returns True to proceed with the close, False to veto it.
        """
        from PySide6.QtWidgets import QMessageBox

        ac = self.annotation_controller

        # 1. Stop an in-progress recording. stop_timed_recording finalises all
        #    active events (real-time and FBF) and auto-saves if enabled.
        try:
            if ac is not None and ac.is_recording():
                ac.stop_timed_recording()
        except Exception:
            self.logger.exception("confirm_application_close: stop recording failed")

        # 2. Unsaved in-memory annotations.
        try:
            if ac is not None and ac.has_unsaved_annotations():
                result = QMessageBox.question(
                    self.main_window,
                    "Unsaved Annotations",
                    "You have unsaved annotations. Export them before exiting?",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No
                    | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if result == QMessageBox.StandardButton.Cancel:
                    return False
                if result == QMessageBox.StandardButton.Yes:
                    # Run the export dialog; it marks annotations saved on
                    # success. If they are still dirty afterwards the user
                    # cancelled the save dialog, so veto the close.
                    ac.export_annotations_dialog()
                    if ac.has_unsaved_annotations():
                        return False
        except Exception:
            self.logger.exception("confirm_application_close: annotation check failed")

        # 3. Unsaved project.
        try:
            if self.project_model.is_project_open() and self.project_model.is_modified():
                result = QMessageBox.question(
                    self.main_window,
                    "Save Project Changes",
                    "The current project has unsaved changes. Save before exiting?",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No
                    | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if result == QMessageBox.StandardButton.Cancel:
                    return False
                if result == QMessageBox.StandardButton.Yes:
                    if not self.project_model.save_project():
                        return False
        except Exception:
            self.logger.exception("confirm_application_close: project check failed")

        return True
    
    def perform_log_cleanup(self):
        """Perform automatic log cleanup."""
        try:
            deleted_old, deleted_excess = self.log_manager.cleanup_old_logs()
            self.logger.info(f"Automatic log cleanup: {deleted_old} old files and {deleted_excess} excess files deleted")
            
            # Show notification if called manually (not via timer)
            sender = self.sender()
            if sender and not isinstance(sender, QTimer):
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(
                    self.main_window,
                    "Log Cleanup Complete",
                    f"Removed {deleted_old} old log files and {deleted_excess} excess files."
                )
        except Exception as e:
            self.logger.error(f"Error during log cleanup: {str(e)}")
            
            # Show error if called manually
            sender = self.sender()
            if sender and not isinstance(sender, QTimer):
                self.main_window.show_error(f"Error during log cleanup: {str(e)}")
    
    def show_log_viewer(self):
        """Show the log viewer dialog."""
        try:
            log_viewer = LogViewerDialog(self.log_manager, self.main_window)
            log_viewer.exec()
        except Exception as e:
            self.logger.error(f"Error showing log viewer: {str(e)}")
            self.main_window.show_error(f"Error showing log viewer: {str(e)}")
    
    @Slot()
    def show_shortcuts_dialog(self):
        """Open the keyboard-shortcuts reference dialog."""
        try:
            from views.shortcuts_dialog import ShortcutsDialog
            mapped = self.action_map_model.get_all_mappings().items()
            dialog = ShortcutsDialog(self.main_window, mapped_keys=mapped)
            dialog.exec()
        except Exception as exc:
            self.logger.error(f"Failed to open shortcuts dialog: {exc}", exc_info=True)
            self.main_window.show_error(f"Failed to open shortcuts dialog: {exc}")

    @Slot()
    def show_about_dialog(self):
        """Show the rich-content About dialog (rendered HTML + BibTeX copy)."""
        try:
            from views.about_dialog import AboutDialog
            dialog = AboutDialog(self.main_window)
            dialog.exec()
        except Exception as exc:
            self.logger.error(f"Failed to open About dialog: {exc}", exc_info=True)
            # Fall back to the plain-text message box if the rich dialog
            # cannot be constructed for some reason.
            self.main_window.show_info(
                f"RABET - Real-time Animal Behavior Event Tagger\n\n"
                f"Version: {__version__}\n"
                f"© 2026 Koshiro Mitsui\n"
                "Released under the MIT License.\n"
                "Repository: https://github.com/mi2e-K/RABET\n"
                "DOI (all versions): https://doi.org/10.5281/zenodo.15313025"
            )
