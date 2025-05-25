# utils/loading_overlay.py - Enhanced with input blocking
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QProgressBar
from PySide6.QtCore import Qt, QSize, QEvent
from PySide6.QtGui import QPainter, QColor, QPalette

class LoadingOverlay(QWidget):
    """
    A semi-transparent overlay widget that shows loading status.
    This overlay captures all user input while visible, preventing UI interactions.
    
    Enhanced to ensure it properly blocks all input events to prevent premature
    interaction with the application during critical loading operations.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Make this a transparent overlay
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Important: Make sure event filtering is enabled and transparent for mouse events is false
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        
        # Install event filter on parent to block all events
        if parent:
            parent.installEventFilter(self)
        
        # Set up layout
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Loading label
        self.loading_label = QLabel("Loading video...")
        self.loading_label.setStyleSheet("""
            color: white; 
            font-size: 16px; 
            font-weight: bold;
            background-color: rgba(0, 0, 0, 0);
            padding: 10px;
        """)
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(120)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(250)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #2980b9;
                border-radius: 5px;
                background-color: #34495e;
                height: 25px;
                text-align: center;
                color: white;
            }
            
            QProgressBar::chunk {
                background-color: #3498db;
                width: 10px;
                margin: 0.5px;
            }
        """)
        
        # Add widgets to layout
        self.layout.addWidget(self.loading_label)
        self.layout.addWidget(self.progress_bar)
        
        # Set z-order to ensure it's on top
        self.raise_()
        
        # Initially hide
        self.hide()
    
    def eventFilter(self, watched, event):
        """
        Event filter to block events to parent widget while overlay is visible.
        This ensures no interaction can occur during critical operations.
        
        Args:
            watched: The watched object
            event: The event
            
        Returns:
            bool: True if event was filtered (blocked), False otherwise
        """
        # If we're visible, block most events to the parent widget
        if self.isVisible():
            # Block all mouse and keyboard events
            if (event.type() in [QEvent.Type.MouseButtonPress, 
                                QEvent.Type.MouseButtonRelease,
                                QEvent.Type.MouseButtonDblClick,
                                QEvent.Type.MouseMove,
                                QEvent.Type.KeyPress,
                                QEvent.Type.KeyRelease,
                                QEvent.Type.Wheel]):
                return True  # Block the event
        
        # Allow all other events
        return False
    
    def paintEvent(self, event):
        """Paint a semi-transparent background."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 180))  # Semi-transparent black
    
    def showEvent(self, event):
        """Resize to parent size when shown."""
        if self.parentWidget():
            self.resize(self.parentWidget().size())
            # Make sure we're on top
            self.raise_()
        super().showEvent(event)
    
    def set_progress(self, value):
        """Update progress bar value."""
        self.progress_bar.setValue(value)
    
    def set_message(self, message):
        """Update loading message."""
        self.loading_label.setText(message)
    
    def show_loading(self, message="Loading video..."):
        """Show the loading overlay with specified message."""
        self.set_message(message)
        self.progress_bar.setValue(0)
        if self.parentWidget():
            self.resize(self.parentWidget().size())
        self.raise_()
        self.show()
    
    def hide_loading(self):
        """Hide the loading overlay."""
        self.hide()