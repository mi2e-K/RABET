# utils/auto_close_message.py
from PySide6.QtWidgets import QMessageBox, QDialog
from PySide6.QtCore import Qt, QTimer


class AutoCloseMessageBox(QMessageBox):
    """
    A message box that automatically closes after a specified time.
    Useful for notifications that shouldn't require user interaction.
    """
    
    def __init__(self, parent=None, timeout=1500):
        """
        Initialize the auto-closing message box.
        
        Args:
            parent: Parent widget
            timeout (int): Time in milliseconds before auto-closing (default: 1500ms)
        """
        super().__init__(parent)
        
        # Set up the timer
        self.timeout = timeout
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.close)
        
        # Always ensure there's a button to click manually
        self.setStandardButtons(QMessageBox.StandardButton.Ok)
        
        # Flag to track if autoclose is enabled
        self._auto_close_enabled = True
    
    def showEvent(self, event):
        """Start the timer when the dialog is shown."""
        super().showEvent(event)
        if self._auto_close_enabled:
            self.timer.start(self.timeout)
    
    def closeEvent(self, event):
        """Clean up when the dialog is closed."""
        if self.timer.isActive():
            self.timer.stop()
        super().closeEvent(event)
    
    def disable_auto_close(self):
        """Disable auto-closing behavior."""
        self._auto_close_enabled = False
        if self.timer.isActive():
            self.timer.stop()
    
    @classmethod
    def information(cls, parent, title, text, timeout=1500):
        """
        Show an information message box that auto-closes.
        
        Args:
            parent: Parent widget
            title (str): Dialog title
            text (str): Message text
            timeout (int): Time in milliseconds before auto-closing
            
        Returns:
            int: Result from dialog execution
        """
        box = cls(parent, timeout)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Information)
        return box.exec()