# controllers/app_controller.py - Updated with icon management and theme integration
import logging
import os
import sys
from pathlib import Path
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

from controllers.video_controller import VideoController
from controllers.annotation_controller import AnnotationController
from controllers.action_map_controller import ActionMapController
from controllers.analysis_controller import AnalysisController
from controllers.project_controller import ProjectController

from utils.file_manager import FileManager
from utils.log_manager import LogManager
from utils.theme_manager import ThemeManager

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
        
        # Initialize log manager
        self.log_manager = LogManager()
        
        # Initialize theme manager
        self.theme_manager = ThemeManager()
        
        # Schedule periodic log cleanup
        self.log_cleanup_timer = QTimer(self)
        self.log_cleanup_timer.setInterval(24 * 60 * 60 * 1000)  # 24 hours
        self.log_cleanup_timer.timeout.connect(self.perform_log_cleanup)
        self.log_cleanup_timer.start()
        
        # Ensure required directories exist (using the utility)
        from utils.directory_init import ensure_app_directories
        ensure_app_directories()
        
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
        
        # Add project view to main window
        self.main_window.add_view("Project", self.project_view)
        
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
        
        # Provide the annotation controller reference to the main window
        self.main_window.annotation_controller = self.annotation_controller
        
        # Connect main window signals
        self.connect_main_window_signals()
        
        # Load default action map
        self._load_default_action_map()
    
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
        self.main_window.export_annotations_action.triggered.connect(self.annotation_controller.export_annotations_dialog)
        self.main_window.import_annotations_action.triggered.connect(self.annotation_controller.import_annotations_dialog)
        self.main_window.clear_annotations_action.triggered.connect(self.annotation_controller.clear_annotations)
        self.main_window.exit_action.triggered.connect(self.handle_exit_action)
        self.main_window.about_action.triggered.connect(self.show_about_dialog)
        
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
    
    def _load_default_action_map(self):
        """Load default action map."""
        # Create a default action map
        default_mappings = {
            'o': 'Attack bites',
            'j': 'Sideways threats',
            'p': 'Tail rattles',
            'q': 'Chasing',
            'a': 'Social contact',
            'e': 'Self-grooming',
            't': 'Locomotion',
            'r': 'Rearing',
        }
        
        # Add default mappings
        for key, behavior in default_mappings.items():
            self.action_map_model.add_mapping(key, behavior)
    
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
    def show_about_dialog(self):
        """Show about dialog."""
        about_text = (
            "RABET - Real-time Animal Behavior Event Tagger\n\n"
            "Version: 1.0.0\n\n"
            "A desktop application for animal behavioral annotation.\n\n"
            "Features:\n"
            "- Video playback with precise control\n"
            "- Keyboard-based real-time annotation\n"
            "- Timeline visualization of behavior events\n"
            "- CSV analysis mode for multiple annotation files\n"
            "- Project management for organizing research assets\n"
            "- Timed recording with pause/resume capability\n\n"
            "© 2023"
        )
        self.main_window.show_info(about_text)