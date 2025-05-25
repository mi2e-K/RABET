#!/usr/bin/env python3
# main.py - Application entry point for RABET (Real-time Animal Behavior Event Tagger)
# Updated with icon fixes and optimized memory handling

import sys
import os
import argparse
import logging
from pathlib import Path
from PySide6.QtWidgets import QApplication, QStyleFactory
from PySide6.QtCore import QSize, QRect
from PySide6.QtGui import QScreen, QIcon

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
    root_logger = setup_logger(use_file_logging=args.dev)
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
        
        # Apply dark theme
        logger.info("Available styles: " + str(QStyleFactory.keys()))
        theme_manager = ThemeManager()
        theme_manager.apply_dark_theme(app)
        
        # Initialize main controller
        # Pass development mode flag if the app_controller accepts it
        try:
            controller = AppController(development_mode=args.dev)
        except TypeError:
            # Fall back to standard initialization if the controller doesn't accept the parameter
            controller = AppController()
        
        # Show main window
        controller.show_main_window()
        
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
        
        # Start application event loop
        sys.exit(app.exec())
    except Exception as e:
        logger.error(f"Unhandled exception in main application: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    main()