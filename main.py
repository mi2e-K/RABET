#!/usr/bin/env python3
# main.py - Application entry point for RABET (Real-time Animal Behavior Event Tagger)
# Updated with icon fixes and optimized memory handling

import sys
import os
import argparse
import logging
from PySide6.QtWidgets import (
    QApplication, QStyleFactory, QSplashScreen, QProgressBar, QLabel,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont

from controllers.app_controller import AppController
from utils.logger import setup_logger
from utils.theme_manager import ThemeManager
from utils.config_path_manager import ConfigPathManager
from utils.directory_init import ensure_app_directories

def setup_application_icon(app):
    """
    Set up the application icon for all windows and taskbar.
    
    Args:
        app (QApplication): The Qt application instance
        
    Returns:
        bool: True if icon was set successfully, False otherwise
    """
    logger = logging.getLogger(__name__)
    
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
        logger.warning("Application icon not found in any of the expected locations")
        return False
    
    try:
        logger.info(f"Setting application icon from: {icon_path}")
        
        # Create icon and set it for the application
        app_icon = QIcon(icon_path)
        
        # Verify the icon was loaded successfully
        if app_icon.isNull():
            logger.error(f"Failed to load icon from {icon_path} - icon is null")
            return False
            
        # Set the application icon - this affects all windows and the taskbar
        app.setWindowIcon(app_icon)
        
        return True
    except Exception as e:
        logger.error(f"Error setting application icon: {str(e)}")
        return False

class RabetSplash(QSplashScreen):
    """Custom splash window with a title, status text and a determinate
    progress bar. Stays on top of every other RABET widget while the
    main window is being constructed."""

    def __init__(self, icon_path: str | None = None) -> None:
        # Build a clean 480x240 background pixmap. We paint a dark
        # rounded rectangle with the RABET version on it so the splash
        # looks intentional rather than relying on an external image.
        from version import __version__ as app_version
        pixmap = QPixmap(QSize(480, 240))
        pixmap.fill(QColor("#1f1f1f"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Border
        painter.setPen(QColor("#3a3a3a"))
        painter.drawRoundedRect(0, 0, 479, 239, 8, 8)
        # Title
        painter.setPen(QColor("#f5f5f5"))
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(
            pixmap.rect().adjusted(0, 40, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "RABET",
        )
        # Subtitle
        painter.setPen(QColor("#bdbdbd"))
        sub_font = QFont()
        sub_font.setPointSize(10)
        painter.setFont(sub_font)
        painter.drawText(
            pixmap.rect().adjusted(0, 80, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "Real-time Animal Behavior Event Tagger",
        )
        # Version
        painter.setPen(QColor("#9e9e9e"))
        ver_font = QFont()
        ver_font.setPointSize(9)
        painter.setFont(ver_font)
        painter.drawText(
            pixmap.rect().adjusted(0, 110, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            f"v{app_version}",
        )
        painter.end()

        super().__init__(pixmap, Qt.WindowType.WindowStaysOnTopHint)
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        # A child progress bar painted over the bottom of the splash.
        self._progress = QProgressBar(self)
        self._progress.setGeometry(40, 180, 400, 18)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            "QProgressBar { background-color: #2a2a2a;"
            " border: 1px solid #3a3a3a; border-radius: 4px; }"
            " QProgressBar::chunk { background-color: #4caf50;"
            " border-radius: 3px; }"
        )

    def set_progress(self, value: int, message: str = "") -> None:
        self._progress.setValue(max(0, min(100, int(value))))
        if message:
            self.showMessage(
                message,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                QColor("#e0e0e0"),
            )
        QApplication.processEvents()


def adjust_window_to_screen(window):
    """
    Adjust window size to fit within the screen if it's too large.
    
    Args:
        window: The main window to adjust
    """
    logger = logging.getLogger(__name__)
    
    # Get the primary screen
    screen = QApplication.primaryScreen()
    if not screen:
        logger.warning("Could not get primary screen information")
        return
        
    # Get available screen geometry (accounts for taskbars/docks)
    screen_rect = screen.availableGeometry()
    window_rect = window.geometry()
    
    # Log the screen and window dimensions
    logger.info(f"Screen dimensions: {screen_rect.width()}x{screen_rect.height()}")
    logger.info(f"Window dimensions: {window_rect.width()}x{window_rect.height()}")
    
    # Check if window is larger than screen
    needs_adjustment = False
    new_width = window_rect.width()
    new_height = window_rect.height()
    
    # Add some margin to avoid touching screen edges
    margin = 20
    max_width = screen_rect.width() - margin * 2
    max_height = screen_rect.height() - margin * 2
    
    if window_rect.width() > max_width:
        new_width = max_width
        needs_adjustment = True
        logger.info(f"Window width adjusted from {window_rect.width()} to {new_width}")
    
    if window_rect.height() > max_height:
        new_height = max_height
        needs_adjustment = True
        logger.info(f"Window height adjusted from {window_rect.height()} to {new_height}")
    
    if needs_adjustment:
        # Resize the window
        window.resize(new_width, new_height)
        logger.info(f"Window resized to fit screen: {new_width}x{new_height}")
        
        # Center the window on screen
        center_x = screen_rect.x() + (screen_rect.width() - new_width) // 2
        center_y = screen_rect.y() + (screen_rect.height() - new_height) // 2
        window.move(center_x, center_y)
        logger.info(f"Window centered at ({center_x}, {center_y})")

def initialize_configuration():
    """
    Initialize and ensure configuration system is properly set up.
    
    Returns:
        bool: True if initialization was successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Initialize the configuration path manager
        config_path_manager = ConfigPathManager()
        
        # Ensure default configurations exist
        config_path_manager.ensure_default_configs()
        
        return True
    except Exception as e:
        logger.error(f"Error initializing configuration system: {str(e)}")
        return False

def main():
    """Application entry point."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='RABET - Real-time Animal Behavior Event Tagger')
    parser.add_argument('--dev', action='store_true', help='Run in development mode with file logging')
    args = parser.parse_args()
    
    # Set up logging based on mode
    # In distribution mode, logs are kept in memory only
    setup_logger(use_file_logging=args.dev)
    logger = logging.getLogger(__name__)
    logger.info("Starting RABET application")
    
    # Ensure application directories exist
    # This is critical for both runtime and build processes
    if not ensure_app_directories():
        logger.warning("Failed to initialize one or more application directories")

    # Initialize the configuration system
    if not initialize_configuration():
        logger.warning("Failed to initialize configuration system - using defaults")
    
    try:
        # Create Qt application
        app = QApplication(sys.argv)
        app.setApplicationName("RABET")
        app.setApplicationDisplayName("Real-time Animal Behavior Event Tagger")

        # Set application icon (crucial for taskbar and window icon)
        setup_application_icon(app)

        # Show the splash screen as early as possible so the user sees
        # something the moment the process starts. The progress is
        # updated at each major construction phase below.
        splash = RabetSplash()
        splash.show()
        splash.set_progress(5, "Loading theme...")

        # Apply dark theme
        logger.info("Available styles: " + str(QStyleFactory.keys()))
        theme_manager = ThemeManager()
        theme_manager.apply_dark_theme(app)
        splash.set_progress(25, "Initialising controllers...")

        # Initialize main controller
        # Pass development mode flag if the app_controller accepts it
        try:
            controller = AppController(development_mode=args.dev)
        except TypeError:
            # Fall back to standard initialization if the controller doesn't accept the parameter
            controller = AppController()
        splash.set_progress(80, "Preparing main window...")

        # Show main window
        controller.show_main_window()
        splash.set_progress(100, "Ready.")
        
        # After window is shown, set its icon explicitly
        if hasattr(controller, 'main_window'):
            window_icon = app.windowIcon()
            if not window_icon.isNull():
                controller.main_window.setWindowIcon(window_icon)
        
        # After window is shown, adjust size if needed
        adjust_window_to_screen(controller.main_window)
        
        # Install global focus tracking
        controller.main_window.installGlobalFocusTracking()
        
        # Ensure the main window has focus
        controller.main_window.setFocus()

        # Hide splash now that the main window is up.
        splash.finish(controller.main_window)

        # Start application event loop
        sys.exit(app.exec())
    except Exception as e:
        logger.error(f"Unhandled exception in main application: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    main()