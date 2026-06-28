#!/usr/bin/env python3
# main.py - Application entry point for RABET (Real-time Animal Behavior Event Tagger)
# Updated with icon fixes and optimized memory handling

import sys
import argparse
import logging
import os
import random
from PySide6.QtWidgets import (
    QApplication, QStyleFactory, QSplashScreen,
)
from PySide6.QtCore import Qt, QSize, QRectF, QEventLoop, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont

# NOTE: ``controllers.app_controller`` is imported lazily inside main() AFTER
# the splash screen is shown (Phase 4-C). It transitively pulls in matplotlib,
# pandas and the visualization/reliability views, which dominate import time;
# deferring it lets the splash appear almost immediately.
from utils.logger import setup_logger
from utils.theme_manager import ThemeManager
from utils.config_path_manager import ConfigPathManager
from utils.directory_init import ensure_app_directories
from utils.app_icon import find_app_icon_path

def setup_application_icon(app):
    """
    Set up the application icon for all windows and taskbar.
    
    Args:
        app (QApplication): The Qt application instance
        
    Returns:
        bool: True if icon was set successfully, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    icon_path = find_app_icon_path()
    
    if not icon_path:
        logger.warning("Application icon not found in any of the expected locations")
        return False
    
    try:
        logger.debug(f"Setting application icon from: {icon_path}")
        
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
    """Startup splash that reveals the RABET dot logo as initialization runs."""

    def __init__(self, icon_path: str | None = None) -> None:
        from utils.rabet_logo_cells import LOGO_FILL_PATTERNS, logo_cells
        from version import __version__ as app_version

        requested_pattern = os.environ.get("RABET_LOGO_FILL_PATTERN", "random")
        if requested_pattern == "random":
            requested_pattern = random.choice(LOGO_FILL_PATTERNS)
        elif requested_pattern not in LOGO_FILL_PATTERNS:
            requested_pattern = "center_out"

        self._splash_size = QSize(560, 360)
        self._logo_fill_pattern = requested_pattern
        self._logo_cells = logo_cells(requested_pattern)
        self._progress = 0.0
        self._message = "Preparing..."
        self._version = app_version

        super().__init__(self._render_pixmap(), Qt.WindowType.WindowStaysOnTopHint)
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

    def set_progress(self, value: int, message: str = "") -> None:
        target = max(0, min(100, int(value)))
        if message:
            self._message = message

        start = self._progress
        steps = max(1, min(18, int(abs(target - start) / 4) or 1))
        for step in range(1, steps + 1):
            amount = step / steps
            eased = 1 - (1 - amount) * (1 - amount)
            self._progress = start + (target - start) * eased
            self.setPixmap(self._render_pixmap())
            QApplication.processEvents()

    def hold_complete(self, milliseconds: int = 180) -> None:
        """Keep the completed logo visible briefly before the splash closes."""
        if milliseconds <= 0:
            return
        hold_loop = QEventLoop()
        QTimer.singleShot(milliseconds, hold_loop.quit)
        hold_loop.exec(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

    def _render_pixmap(self) -> QPixmap:
        from utils.rabet_logo_cells import LOGO_PALETTE, LOGO_ROWS

        pixmap = QPixmap(self._splash_size)
        pixmap.fill(QColor("#030303"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setPen(QColor("#20262b"))
        painter.drawRoundedRect(0, 0, self._splash_size.width() - 1, self._splash_size.height() - 1, 10, 10)

        cell_step = 7
        cell_size = 6
        logo_width = max(len(row) for row in LOGO_ROWS) * cell_step
        logo_height = len(LOGO_ROWS) * cell_step
        logo_x = (self._splash_size.width() - logo_width) / 2
        logo_y = 26

        visible = int(len(self._logo_cells) * (self._progress / 100.0))
        for row, col, value in self._logo_cells[:visible]:
            x = logo_x + col * cell_step
            y = logo_y + row * cell_step
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(LOGO_PALETTE[value]))
            painter.drawRoundedRect(QRectF(x, y, cell_size, cell_size), 1.4, 1.4)

        title_font = QFont("Segoe UI", 18)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor("#f7fbfd"))
        painter.drawText(
            QRectF(0, 298, self._splash_size.width(), 28),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            "RABET",
        )

        detail_font = QFont("Segoe UI", 9)
        painter.setFont(detail_font)
        painter.setPen(QColor("#9baab2"))
        painter.drawText(
            QRectF(0, 324, self._splash_size.width(), 18),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            f"{self._message}  v{self._version}",
        )
        painter.end()
        return pixmap


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
    logger.debug(f"Screen dimensions: {screen_rect.width()}x{screen_rect.height()}")
    logger.debug(f"Window dimensions: {window_rect.width()}x{window_rect.height()}")
    
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
        logger.debug(f"Window width adjusted from {window_rect.width()} to {new_width}")
    
    if window_rect.height() > max_height:
        new_height = max_height
        needs_adjustment = True
        logger.debug(f"Window height adjusted from {window_rect.height()} to {new_height}")
    
    if needs_adjustment:
        # Resize the window
        window.resize(new_width, new_height)
        logger.debug(f"Window resized to fit screen: {new_width}x{new_height}")
        
        # Center the window on screen
        center_x = screen_rect.x() + (screen_rect.width() - new_width) // 2
        center_y = screen_rect.y() + (screen_rect.height() - new_height) // 2
        window.move(center_x, center_y)
        logger.debug(f"Window centered at ({center_x}, {center_y})")

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

    # Startup profiling (PR-STARTUP-01): perf_counter milestones. Enable per-mark
    # logs with RABET_STARTUP_PROFILE=1; a one-line summary is always emitted.
    from utils.startup_profiler import StartupProfiler
    profiler = StartupProfiler()

    # Set up logging based on mode
    # In distribution mode, logs are kept in memory only
    setup_logger(use_file_logging=args.dev)
    profiler.mark("logger")
    logger = logging.getLogger(__name__)
    logger.info("Starting RABET application")
    
    # Ensure application directories exist
    # This is critical for both runtime and build processes
    if not ensure_app_directories():
        logger.warning("Failed to initialize one or more application directories")

    # Initialize the configuration system
    if not initialize_configuration():
        logger.warning("Failed to initialize configuration system - using defaults")
    profiler.mark("config")

    try:
        # Create Qt application
        app = QApplication(sys.argv)
        app.setApplicationName("RABET")
        profiler.mark("qapplication")

        # Set application icon (crucial for taskbar and window icon)
        setup_application_icon(app)
        profiler.mark("icon")

        # Show the splash screen as early as possible so the user sees
        # something the moment the process starts. The progress is
        # updated at each major construction phase below.
        splash = RabetSplash()
        splash.show()
        splash.set_progress(5, "Loading theme...")
        profiler.mark("splash")

        # Apply dark theme
        logger.debug("Available styles: " + str(QStyleFactory.keys()))
        theme_manager = ThemeManager()
        theme_manager.apply_dark_theme(app)
        splash.set_progress(25, "Initialising controllers...")
        profiler.mark("theme")

        # Lazy import (Phase 4-C): pull in the heavy view/model/matplotlib stack
        # only now, after the splash is already on screen.
        from controllers.app_controller import AppController
        profiler.mark("appctrl_import")

        # Initialize main controller
        # Pass development mode flag if the app_controller accepts it
        try:
            controller = AppController(development_mode=args.dev)
        except TypeError:
            # Fall back to standard initialization if the controller doesn't accept the parameter
            controller = AppController()
        profiler.mark("appctrl_init")
        splash.set_progress(80, "Preparing main window...")

        # Show main window
        controller.show_main_window()
        profiler.mark("mainwindow_shown")
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
        splash.hold_complete(180)
        splash.finish(controller.main_window)
        profiler.summary()

        # Start application event loop
        sys.exit(app.exec())
    except Exception as e:
        logger.error(f"Unhandled exception in main application: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
