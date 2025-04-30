# utils/theme_manager.py
import logging
from PySide6.QtGui import QPalette, QColor, QBrush
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

class ThemeManager:
    """
    Manages application theming to ensure consistent dark mode appearance
    across different platforms and environments.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def apply_dark_theme(self, app):
        """
        Apply a consistent dark theme to the entire application.
        
        Args:
            app (QApplication): The application instance
        """
        self.logger.info("Applying dark theme to application")
        
        # Create dark palette
        palette = QPalette()
        
        # Set window/background colors
        palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        
        # Text colors
        palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(127, 127, 127))
        
        # Button colors
        palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        
        # Link colors
        palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.LinkVisited, QColor(108, 113, 196))
        
        # Highlight colors
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        
        # Group/panel related colors
        palette.setColor(QPalette.ColorRole.Light, QColor(60, 60, 60))
        palette.setColor(QPalette.ColorRole.Midlight, QColor(65, 65, 65))
        palette.setColor(QPalette.ColorRole.Mid, QColor(70, 70, 70))
        palette.setColor(QPalette.ColorRole.Dark, QColor(80, 80, 80))
        palette.setColor(QPalette.ColorRole.Shadow, QColor(20, 20, 20))
        
        # Apply the palette to the application
        app.setPalette(palette)
        
        # Additional stylesheet for fine-tuning
        stylesheet = """
        /* QWidget base style */
        QWidget {
            background-color: #353535;
            color: #FFFFFF;
        }
        
        /* QMainWindow and central widget */
        QMainWindow, QMainWindow > QWidget {
            background-color: #353535;
        }
        
        /* QMainWindow title bar area override (including top parts) */
        QMainWindow::title {
            background-color: #252525;
            color: #FFFFFF;
        }
        
        /* Title bar text and background */
        QWidget#titleBar, QLabel#titleLabel {
            background-color: #252525;
            color: #FFFFFF;
        }
        
        /* QMenuBar styling */
        QMenuBar {
            background-color: #2D2D2D;
            color: #FFFFFF;
        }
        
        QMenuBar::item:selected {
            background-color: #3A3A3A;
        }
        
        /* QMenu styling */
        QMenu {
            background-color: #2D2D2D;
            color: #FFFFFF;
            border: 1px solid #555555;
        }
        
        QMenu::item:selected {
            background-color: #3A3A3A;
        }
        
        /* QToolBar styling */
        QToolBar {
            background-color: #2D2D2D;
            border: none;
        }
        
        /* QToolBar button styling - critical for mode buttons */
        QToolButton {
            background-color: #2D2D2D;
            color: #FFFFFF;
            border: 1px solid #454545;
            border-radius: 3px;
            padding: 3px;
        }
        
        QToolButton:hover {
            background-color: #3D3D3D;
        }
        
        QToolButton:pressed {
            background-color: #252525;
        }
        
        QToolButton:checked {
            background-color: #E0E0E0;
            color: #000000;  /* Black text for checked state */
            border: 1px solid #CCCCCC;
        }
        
        /* QStatusBar styling */
        QStatusBar {
            background-color: #2D2D2D;
            color: #CCCCCC;
        }
        
        /* QTabWidget and QTabBar styling */
        QTabWidget::pane {
            border: 1px solid #555555;
            background-color: #353535;
        }
        
        QTabBar::tab {
            background-color: #2A2A2A;
            color: #CCCCCC;
            padding: 5px 10px;
            border: 1px solid #555555;
            border-bottom: none;
        }
        
        QTabBar::tab:selected {
            background-color: #353535;
            color: #FFFFFF;
        }
        
        QTabBar::tab:!selected {
            margin-top: 2px;
        }
        
        /* QHeaderView (table headers) */
        QHeaderView::section {
            background-color: #2A2A2A;
            color: #FFFFFF;
            padding: 5px;
            border: 1px solid #555555;
        }
        
        /* QTableWidget styling */
        QTableWidget {
            gridline-color: #555555;
            background-color: #252525;
            border: 1px solid #555555;
            color: #FFFFFF;
        }
        
        QTableWidget::item:selected {
            background-color: #2A75CC;
        }
        
        /* QScrollBar styling */
        QScrollBar:vertical {
            border: none;
            background-color: #2A2A2A;
            width: 12px;
            margin: 15px 0 15px 0;
        }
        
        QScrollBar::handle:vertical {
            background-color: #555555;
            min-height: 30px;
            border-radius: 6px;
        }
        
        QScrollBar::handle:vertical:hover {
            background-color: #777777;
        }
        
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            border: none;
            background: none;
            height: 15px;
        }
        
        QScrollBar:horizontal {
            border: none;
            background-color: #2A2A2A;
            height: 12px;
            margin: 0 15px 0 15px;
        }
        
        QScrollBar::handle:horizontal {
            background-color: #555555;
            min-width: 30px;
            border-radius: 6px;
        }
        
        QScrollBar::handle:horizontal:hover {
            background-color: #777777;
        }
        
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            border: none;
            background: none;
            width: 15px;
        }
        
        /* QLineEdit and QTextEdit styling */
        QLineEdit, QTextEdit {
            background-color: #252525;
            color: #FFFFFF;
            border: 1px solid #555555;
            padding: 2px;
        }
        
        /* QComboBox styling */
        QComboBox {
            background-color: #252525;
            color: #FFFFFF;
            border: 1px solid #555555;
            padding: 2px;
        }
        
        QComboBox:drop-down {
            background-color: #252525;
            width: 15px;
        }
        
        QComboBox QAbstractItemView {
            background-color: #252525;
            color: #FFFFFF;
            border: 1px solid #555555;
        }
        
        /* QPushButton styling */
        QPushButton {
            background-color: #353535;
            color: #FFFFFF;
            border: 1px solid #555555;
            padding: 5px 10px;
            border-radius: 3px;
        }
        
        QPushButton:hover {
            background-color: #454545;
            border: 1px solid #666666;
        }
        
        QPushButton:pressed {
            background-color: #252525;
        }
        
        QPushButton:disabled {
            background-color: #2A2A2A;
            color: #666666;
            border: 1px solid #3A3A3A;
        }
        
        /* QGroupBox styling */
        QGroupBox {
            border: 1px solid #555555;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 10px;
        }
        
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top center;
            padding: 0 5px;
            color: #FFFFFF;
        }
        
        /* QSlider styling */
        QSlider::groove:horizontal {
            height: 5px;
            background: #353535;
            border: 1px solid #555555;
            border-radius: 2px;
        }
        
        QSlider::handle:horizontal {
            background: #777777;
            border: 1px solid #555555;
            width: 12px;
            margin: -5px 0;
            border-radius: 6px;
        }
        
        QSlider::handle:horizontal:hover {
            background: #999999;
        }
        
        /* QProgressBar styling */
        QProgressBar {
            border: 1px solid #555555;
            border-radius: 3px;
            background-color: #252525;
            text-align: center;
            color: #FFFFFF;
        }
        
        QProgressBar::chunk {
            background-color: #2A75CC;
            width: 10px;
        }
        
        /* QSpinBox styling */
        QSpinBox {
            background-color: #252525;
            color: #FFFFFF;
            border: 1px solid #555555;
            padding: 2px;
        }
        
        QSpinBox::up-button, QSpinBox::down-button {
            background-color: #353535;
            width: 16px;
            border: 1px solid #555555;
        }
        
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {
            background-color: #454545;
        }
        
        /* Video frame styling */
        QFrame#video_frame {
            background-color: #000000;
            border: 1px solid #555555;
        }
        
        /* Timeline related styles */
        QScrollArea {
            background-color: #353535;
            border: 1px solid #555555;
        }
        """
        
        # Apply stylesheet
        app.setStyleSheet(stylesheet)
        
        # Set a dark icon theme if available
        app.setStyle("Fusion")  # Fusion style tends to look better with dark themes
        
        self.logger.info("Dark theme applied successfully")
        
    def apply_light_theme(self, app):
        """
        Apply a light theme to the application (for potential future use).
        
        Args:
            app (QApplication): The application instance
        """
        # Reset to default
        app.setPalette(QApplication.style().standardPalette())
        app.setStyleSheet("")
        
        self.logger.info("Light theme applied (default system palette)")