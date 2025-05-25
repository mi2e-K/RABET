# views/log_viewer_dialog.py - Updated for in-memory logs
import logging
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, 
    QPushButton, QComboBox, QLabel, QSplitter, 
    QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QCheckBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor

class LogViewerDialog(QDialog):
    """
    Dialog for viewing application logs with filtering and refresh capabilities.
    Updated to work with in-memory logs for distribution builds.
    """
    
    def __init__(self, log_manager, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.log_manager = log_manager
        
        self.setWindowTitle("Log Viewer")
        self.resize(800, 600)
        
        # Auto-refresh timer
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_log_content)
        self.refresh_timer.setInterval(3000)  # Refresh every 3 seconds
        
        self.setup_ui()
        
        # Load initial log content
        self.refresh_log_content()
        self.load_log_files()
        
        # Start auto-refresh
        self.refresh_timer.start()
    
    def setup_ui(self):
        """Set up the user interface."""
        # Main layout
        self.layout = QVBoxLayout(self)
        
        # Controls layout
        self.controls_layout = QHBoxLayout()
        
        # Log section selection
        self.file_label = QLabel("Log Section:")
        self.controls_layout.addWidget(self.file_label)
        
        self.file_combo = QComboBox()
        self.file_combo.setMinimumWidth(200)
        self.controls_layout.addWidget(self.file_combo)
        
        # Lines to show
        self.lines_label = QLabel("Max Lines:")
        self.controls_layout.addWidget(self.lines_label)
        
        self.lines_combo = QComboBox()
        self.lines_combo.addItems(["100", "500", "1000", "5000", "All"])
        self.lines_combo.setCurrentText("1000")
        self.controls_layout.addWidget(self.lines_combo)
        
        # Search text
        self.search_label = QLabel("Filter:")
        self.controls_layout.addWidget(self.search_label)
        
        self.search_box = QTextEdit()
        self.search_box.setMaximumHeight(28)
        self.search_box.setPlaceholderText("Filter log (case-insensitive)")
        self.controls_layout.addWidget(self.search_box)
        
        # Auto-refresh checkbox
        self.auto_refresh_checkbox = QCheckBox("Auto-refresh")
        self.auto_refresh_checkbox.setChecked(True)
        self.auto_refresh_checkbox.stateChanged.connect(self.toggle_auto_refresh)
        self.controls_layout.addWidget(self.auto_refresh_checkbox)
        
        # Add controls to main layout
        self.layout.addLayout(self.controls_layout)
        
        # Splitter for log content and file list
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Log content area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.log_text.setFont(QFont("Courier New", 9))
        self.splitter.addWidget(self.log_text)
        
        # File list area with reduced importance for in-memory logs
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(3)
        self.file_table.setHorizontalHeaderLabels(["Section", "Size", "Date"])
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.file_table.setMinimumHeight(100)  # Reduced height
        self.file_table.setMaximumHeight(150)
        self.splitter.addWidget(self.file_table)
        
        # Set initial splitter sizes - Give more space to log content
        self.splitter.setSizes([500, 100])
        
        # Add splitter to main layout
        self.layout.addWidget(self.splitter)
        
        # Buttons layout
        self.buttons_layout = QHBoxLayout()
        
        # Refresh button
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_log_content)
        self.buttons_layout.addWidget(self.refresh_button)
        
        # Clear logs button
        self.clear_button = QPushButton("Clear Logs")
        self.clear_button.clicked.connect(self.clear_logs)
        self.buttons_layout.addWidget(self.clear_button)
        
        # Export button
        self.export_button = QPushButton("Export Log")
        self.export_button.clicked.connect(self.export_log)
        self.buttons_layout.addWidget(self.export_button)
        
        # Add "Close" button
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        self.buttons_layout.addWidget(self.close_button)
        
        # Add buttons to main layout
        self.layout.addLayout(self.buttons_layout)
        
        # Connect signals
        self.file_combo.currentIndexChanged.connect(self.refresh_log_content)
        self.lines_combo.currentIndexChanged.connect(self.refresh_log_content)
        self.search_box.textChanged.connect(self.refresh_log_content)
        self.file_table.itemDoubleClicked.connect(self.on_file_double_clicked)
    
    def load_log_files(self):
        """Load the list of available log sections."""
        # Clear existing items
        self.file_combo.clear()
        
        # Get log sections
        log_sections = self.log_manager.get_log_files()
        
        # Add to combo box
        for section in log_sections:
            self.file_combo.addItem(section['name'], section['path'])
        
        # Update file table
        self.file_table.setRowCount(0)
        for section in log_sections:
            row = self.file_table.rowCount()
            self.file_table.insertRow(row)
            
            self.file_table.setItem(row, 0, QTableWidgetItem(section['name']))
            self.file_table.setItem(row, 1, QTableWidgetItem(section['size']))
            self.file_table.setItem(row, 2, QTableWidgetItem(section['date']))
    
    def refresh_log_content(self):
        """Refresh the log content display."""
        try:
            # Check if auto-refresh is enabled
            if not self.refresh_timer.isActive() and self.auto_refresh_checkbox.isChecked():
                self.refresh_timer.start()
            
            # Get selected log section
            section_index = self.file_combo.currentIndex()
            if section_index < 0:
                return
                
            section_id = self.file_combo.itemData(section_index)
            
            # Get max lines
            max_lines_text = self.lines_combo.currentText()
            if max_lines_text == "All":
                max_lines = -1
            else:
                max_lines = int(max_lines_text)
            
            # Apply filtering
            filter_text = self.search_box.toPlainText().strip()
            
            # Get log content
            content = self.log_manager.get_log_content(max_lines, filter_text)
            
            if not content:
                self.log_text.setPlainText("No log entries found.")
                return
            
            # Apply colored formatting - highlight different log levels
            self.log_text.clear()
            for line in content.splitlines():
                # Determine color based on log level
                if " ERROR " in line or " CRITICAL " in line:
                    color = QColor(255, 0, 0)  # Red
                elif " WARNING " in line:
                    color = QColor(255, 165, 0)  # Orange
                elif " INFO " in line:
                    color = QColor(0, 128, 0)  # Green
                elif " DEBUG " in line:
                    color = QColor(128, 128, 128)  # Gray
                else:
                    color = QColor(0, 0, 0)  # Black
                
                # Insert with color
                self.log_text.setTextColor(color)
                self.log_text.append(line)
            
            # Return to default color
            self.log_text.setTextColor(QColor(0, 0, 0))
            
            # Scroll to the end
            scrollbar = self.log_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            
        except Exception as e:
            self.logger.error(f"Error refreshing log content: {str(e)}")
            self.log_text.setPlainText(f"Error refreshing log content: {str(e)}")
    
    def toggle_auto_refresh(self, state):
        """
        Toggle auto-refresh based on checkbox state.
        
        Args:
            state: Checkbox state
        """
        if state == Qt.CheckState.Checked.value:
            self.refresh_timer.start()
            self.logger.debug("Auto-refresh enabled")
        else:
            self.refresh_timer.stop()
            self.logger.debug("Auto-refresh disabled")
    
    def clear_logs(self):
        """Clear in-memory logs."""
        # Confirm cleanup
        result = QMessageBox.question(
            self,
            "Confirm Clear Logs",
            "This will clear all in-memory logs. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if result != QMessageBox.StandardButton.Yes:
            return
        
        # Perform cleanup
        try:
            success = self.log_manager.clear_logs()
            
            # Show results
            if success:
                QMessageBox.information(
                    self,
                    "Logs Cleared",
                    "In-memory logs have been cleared."
                )
            else:
                QMessageBox.warning(
                    self,
                    "Clear Failed",
                    "Failed to clear in-memory logs."
                )
            
            # Refresh log content
            self.refresh_log_content()
            
        except Exception as e:
            self.logger.error(f"Error clearing logs: {str(e)}")
            QMessageBox.warning(
                self,
                "Clear Error",
                f"An error occurred while clearing logs: {str(e)}"
            )
    
    def export_log(self):
        """Export the currently displayed log to a file."""
        # Get current log content
        content = self.log_text.toPlainText()
        if not content:
            QMessageBox.information(
                self,
                "No Content",
                "There is no log content to export."
            )
            return
        
        # Get file name
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Log",
            "",
            "Log Files (*.log);;Text Files (*.txt);;All Files (*.*)"
        )
        
        if not file_path:
            return
        
        # Add extension if not provided
        if not any(file_path.endswith(ext) for ext in ['.log', '.txt']):
            file_path += '.log'
        
        # Export content
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            QMessageBox.information(
                self,
                "Export Successful",
                f"Log exported to {file_path}"
            )
        except Exception as e:
            self.logger.error(f"Error exporting log: {str(e)}")
            QMessageBox.warning(
                self,
                "Export Error",
                f"An error occurred during export: {str(e)}"
            )
    
    def on_file_double_clicked(self, item):
        """
        Handle double-click on a log section in the table.
        
        Args:
            item: The clicked item
        """
        row = item.row()
        section_name = self.file_table.item(row, 0).text()
        
        # Find this section in the combo box and select it
        for i in range(self.file_combo.count()):
            if self.file_combo.itemText(i) == section_name:
                self.file_combo.setCurrentIndex(i)
                break
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Stop timer when window is closed
        self.refresh_timer.stop()
        super().closeEvent(event)