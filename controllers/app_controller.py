# controllers/app_controller.py - Updated with icon management, theme integration, and visualization support
import logging
import os
import sys
from version import __version__
from PySide6.QtCore import QObject, Slot, QTimer
from PySide6.QtGui import QIcon

from models.video_model import VideoModel
from models.action_map_model import ActionMapModel
from models.annotation_model import AnnotationModel
from models.analysis_model import AnalysisModel
from models.project_model import ProjectModel

from views.main_window import MainWindow
from views.project_view import ProjectView
from views.log_viewer_dialog import LogViewerDialog
from views.visualization_view import VisualizationView  # Add visualization view import
from views.reliability_view import ReliabilityView  # 1.3.2: Reliability tab

from controllers.video_controller import VideoController
from controllers.annotation_controller import AnnotationController
from controllers.action_map_controller import ActionMapController
from controllers.analysis_controller import AnalysisController
from controllers.project_controller import ProjectController
from controllers.visualization_controller import VisualizationController  # Add visualization controller import
from controllers.reliability_controller import ReliabilityController  # 1.3.2

from utils.file_manager import FileManager
from utils.log_manager import LogManager
from utils.theme_manager import ThemeManager
from utils.config_manager import ConfigManager

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
        self.action_map_model = ActionMapModel()
        self.annotation_model = AnnotationModel(self.action_map_model, self.video_model)
        self.analysis_model = AnalysisModel()
        self.project_model = ProjectModel(self.file_manager)
        
        # Initialize main window
        self.main_window = MainWindow()
        
        # Set application window icon
        self.set_application_icon()
        
        # Initialize project view
        self.project_view = ProjectView()
        
        # Initialize visualization view
        self.visualization_view = VisualizationView()

        # 1.3.2: Reliability view
        self.reliability_view = ReliabilityView()

        # Add views to main window
        self.main_window.add_view("Project", self.project_view)
        self.main_window.add_view("Visualization", self.visualization_view)  # Add visualization view
        self.main_window.add_view("Reliability", self.reliability_view)  # 1.3.2
        
        # Initialize controllers
        self.video_controller = VideoController(self.video_model, self.main_window.video_player_view)
        self.action_map_controller = ActionMapController(self.action_map_model, self.main_window.action_map_view)
        self.annotation_controller = AnnotationController(
            self.annotation_model, 
            self.video_model,
            self.main_window,
            self.main_window.timeline_view
        )
        self.analysis_controller = AnalysisController(self.analysis_model, self.main_window.analysis_view)
        self.project_controller = ProjectController(
            self.project_model,
            self.project_view,
            self.video_controller,
            self.action_map_controller,
            self.annotation_controller,
            self.analysis_controller
        )
        
        # Initialize visualization controller
        # CRITICAL FIX: Completely decouple visualization from analysis model
        self.visualization_controller = VisualizationController(self.visualization_view)

        # 1.3.2: Reliability controller. The second positional argument is
        # a QObject parent (this AppController), which Qt uses for normal
        # parent-child lifetime tracking - not a strong app-wide reference
        # cycle, so memory management is delegated to Qt as usual.
        self.reliability_controller = ReliabilityController(self.reliability_view, self)
        
        # Keep the main window on the visualization screen when files are
        # dropped there, but let the visualization controller own the load.
        self.visualization_view.files_dropped.connect(self.handle_visualization_files_dropped)
        self.main_window.analysis_view.visualize_files_requested.connect(
            self.handle_analysis_visualize_requested
        )
        
        # Provide the annotation controller reference to the main window
        self.main_window.annotation_controller = self.annotation_controller
        
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
        # 1.3.2: Reliability tab remembers its picker directories across
        # sessions via ConfigManager.
        self.reliability_controller.set_config_manager(self.config_manager)

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
        file_paths = self.analysis_model.get_file_paths()
        if not file_paths:
            self.main_window.show_info("No annotation files are loaded in Analysis.")
            return

        self.visualization_controller.load_files(file_paths)
        self.main_window.switch_to_view("Visualization")
    
    def set_application_icon(self):
        """Set the application and window icons."""
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
        self.analysis_model.error_occurred.connect(self.main_window.show_error)
        self.project_model.error_occurred.connect(self.main_window.show_error)
    
    def toggle_play_pause(self):
        """Toggle between play and pause states."""
        if self.video_model.is_playing():
            self.video_model.pause()
        else:
            self.video_model.play()
    
    def handle_exit_action(self):
        """Handle exit action, checking for unsaved project changes."""
        # Check if project has unsaved changes
        if self.project_model.is_project_open() and self.project_model.is_modified():
            from PySide6.QtWidgets import QMessageBox
            result = QMessageBox.question(
                self.main_window,
                "Save Project Changes",
                "The current project has unsaved changes. Save before exiting?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            
            if result == QMessageBox.StandardButton.Cancel:
                return
            
            if result == QMessageBox.StandardButton.Yes:
                if not self.project_model.save_project():
                    # Save failed, don't exit
                    return
        
        # Close the main window
        self.main_window.close()
    
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
