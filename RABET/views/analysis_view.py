# views/analysis_view.py - Enhanced with file management and export options
import logging
import os
import pandas as pd
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QProgressBar, QPushButton
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QDragEnterEvent, QDropEvent

class AnalysisView(QWidget):
    """
    View for CSV analysis and automatic summary statistics.
    
    Signals:
        files_dropped: Emitted when files are dropped (list of file paths)
        load_files_requested: Emitted when load files button is clicked
        remove_files_requested: Emitted when remove files button is clicked (list of indices)
        clear_files_requested: Emitted when clear files button is clicked
        export_table_requested: Emitted when export button is clicked
    """
    
    files_dropped = Signal(list)
    load_files_requested = Signal()
    remove_files_requested = Signal(list)
    clear_files_requested = Signal()
    export_table_requested = Signal()
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing AnalysisView")
        
        # Enable drag and drop
        self.setAcceptDrops(True)
        
        # Store loaded file paths
        self._file_paths = []
        
        self.setup_ui()
        self.connect_signals()
    
    def setup_ui(self):
        """Set up simplified user interface for automatic analysis."""
        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        
        # Make instructions text much larger and position it lower
        self.instructions = QLabel("Drop CSV annotation files here")
        self.instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.instructions.setStyleSheet("font-size: 20px; font-weight: bold; margin-top: 40px; margin-bottom: 40px;")
        self.layout.addWidget(self.instructions)
        
        # Create a parent widget with no layout for absolute positioning
        self.files_area = QWidget()
        self.layout.addWidget(self.files_area)
        
        # Place the label using absolute positioning
        self.files_label = QLabel("Loaded Files:", self.files_area)
        self.files_label.setStyleSheet("font-weight: bold;")
        # Let's position the label 10 pixels from the top of the container
        self.files_label.setGeometry(10, 10, 100, 20)  # x, y, width, height
        
        # Position the table directly below the label with a small margin (5px)
        self.files_table = QTableWidget(self.files_area)
        self.files_table.setColumnCount(2)
        self.files_table.setHorizontalHeaderLabels(["File Name", "Path"])
        self.files_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.files_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        # Position 5px below the label (label height + 5px margin)
        self.files_table.setGeometry(10, 35, self.files_area.width() - 20, 350)
        self.files_area.setMinimumHeight(400)  # Set minimum height to accommodate the table + label
        
        # We need to handle resizing for this absolute positioning approach
        self.files_area.resizeEvent = self.on_files_area_resize
        
        # File management buttons layout
        self.buttons_layout = QHBoxLayout()
        
        # Load files button
        self.load_button = QPushButton("Load Files")
        self.buttons_layout.addWidget(self.load_button)
        
        # Remove selected files button
        self.remove_button = QPushButton("Remove Selected")
        self.buttons_layout.addWidget(self.remove_button)
        
        # Clear all files button
        self.clear_button = QPushButton("Clear All")
        self.buttons_layout.addWidget(self.clear_button)
        
        # Add spacer to push buttons to the left
        self.buttons_layout.addStretch()
        
        self.layout.addLayout(self.buttons_layout)
        
        # Progress indicator
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)
        
        # Export button layout
        self.export_layout = QHBoxLayout()
        self.export_button = QPushButton("Export Summary Table")
        self.export_button.setStyleSheet("font-weight: bold;")
        self.export_layout.addWidget(self.export_button)
        self.export_layout.addStretch()
        self.layout.addLayout(self.export_layout)
        
        # Status message area with bright yellow color
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #FFFF00; font-weight: bold;")
        self.layout.addWidget(self.status_label)
    
    def on_files_area_resize(self, event):
        """Handle resizing of the files area to maintain layout."""
        # Update table width when container is resized
        width = event.size().width()
        height = event.size().height()
        
        # Keep the table width responsive
        self.files_table.setGeometry(10, 35, width - 20, 350)
    
    def connect_signals(self):
        """Connect widget signals to slots."""
        self.load_button.clicked.connect(self.load_files_requested)
        self.remove_button.clicked.connect(self.on_remove_button_clicked)
        self.clear_button.clicked.connect(self.clear_files_requested)
        self.export_button.clicked.connect(self.export_table_requested)
    
    def on_remove_button_clicked(self):
        """Handle remove button click - get selected rows and emit signal."""
        selected_items = self.files_table.selectedItems()
        
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Please select file(s) to remove.")
            return
        
        # Get unique row indices
        selected_rows = set()
        for item in selected_items:
            selected_rows.add(item.row())
        
        selected_indices = sorted(list(selected_rows))
        self.remove_files_requested.emit(selected_indices)
    
    def dragEnterEvent(self, event):
        """
        Handle drag enter events.
        
        Args:
            event (QDragEnterEvent): Drag enter event
        """
        # Check if the drag contains URLs (files)
        if event.mimeData().hasUrls():
            # Check if all URLs are CSV files
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if not file_path.lower().endswith('.csv'):
                    return
            
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        """
        Handle drop events.
        
        Args:
            event (QDropEvent): Drop event
        """
        # Get file paths from URLs
        file_paths = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            file_paths.append(file_path)
        
        if file_paths:
            self.files_dropped.emit(file_paths)
    
    @Slot(list)
    def update_file_list(self, file_paths):
        """
        Update the list of loaded files.
        
        Args:
            file_paths (list): List of file paths
        """
        # Store the file paths
        self._file_paths = file_paths
        
        # Update table
        self.files_table.setRowCount(0)
        
        for file_path in file_paths:
            row = self.files_table.rowCount()
            self.files_table.insertRow(row)
            
            file_name = os.path.basename(file_path)
            file_name_item = QTableWidgetItem(file_name)
            path_item = QTableWidgetItem(file_path)
            
            self.files_table.setItem(row, 0, file_name_item)
            self.files_table.setItem(row, 1, path_item)
    
    @Slot(dict)
    def update_summary_table(self, results):
        """
        Update the summary table with analysis results.
        
        Args:
            results (dict): Dictionary containing analysis results for each file
                {file_name: {metrics}, ...}
        """
        # Clear existing data rows (keep the header row)
        while self.summary_table.rowCount() > 1:
            self.summary_table.removeRow(1)
        
        # Add each file's results as a row
        row_index = 1  # Start after header row
        for file_name, metrics in results.items():
            self.summary_table.insertRow(row_index)
            
            # Set animal ID (file name without extension and without "_annotations" suffix)
            animal_id = os.path.splitext(os.path.basename(file_name))[0]
            # Remove "_annotations" suffix if present
            if animal_id.endswith("_annotations"):
                animal_id = animal_id[:-12]  # Remove "_annotations"
                
            self.summary_table.setItem(row_index, 0, QTableWidgetItem(animal_id))
            
            # Fill in duration values (columns 1-8)
            behaviors = ["Attack bites", "Sideways threats", "Tail rattles", "Chasing", 
                       "Social contact", "Self-grooming", "Locomotion", "Rearing"]
            
            for i, behavior in enumerate(behaviors):
                duration = metrics.get(f"{behavior}_duration", 0)
                # Convert to seconds with 2 decimal places
                duration_str = f"{duration:.2f}"
                self.summary_table.setItem(row_index, i+1, QTableWidgetItem(duration_str))
            
            # Add empty spacer column
            self.summary_table.setItem(row_index, 9, QTableWidgetItem(""))
            
            # Fill in frequency values (columns 10-17)
            for i, behavior in enumerate(behaviors):
                frequency = metrics.get(f"{behavior}_count", 0)
                self.summary_table.setItem(row_index, i+10, QTableWidgetItem(str(frequency)))
            
            # Add empty spacer column
            self.summary_table.setItem(row_index, 18, QTableWidgetItem(""))
            
            # Add special metrics
            attack_latency = metrics.get("attack_latency", 0)
            total_aggression = metrics.get("total_aggression", 0)
            total_aggression_no_tail = metrics.get("total_aggression_no_tail", 0)
            
            self.summary_table.setItem(row_index, 19, QTableWidgetItem(f"{attack_latency:.2f}"))
            self.summary_table.setItem(row_index, 20, QTableWidgetItem(f"{total_aggression:.2f}"))
            self.summary_table.setItem(row_index, 21, QTableWidgetItem(f"{total_aggression_no_tail:.2f}"))
            
            row_index += 1
        
        # Auto-adjust column widths
        self.summary_table.resizeColumnsToContents()
    
    def show_progress(self, visible=True, value=0):
        """
        Show or hide progress bar.
        
        Args:
            visible (bool): Whether progress bar should be visible
            value (int): Progress value (0-100)
        """
        self.progress_bar.setVisible(visible)
        if visible:
            self.progress_bar.setValue(value)
    
    def set_status_message(self, message):
        """
        Set status message.
        
        Args:
            message (str): Status message to display
        """
        self.status_label.setText(message)
    
    def select_files(self):
        """
        Open file dialog to select files.
        
        Returns:
            list: List of selected file paths
        """
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        file_dialog.setNameFilter("CSV Files (*.csv)")
        
        if file_dialog.exec():
            return file_dialog.selectedFiles()
        else:
            return []
    
    def select_export_file(self, default_dir=None, default_filename="summary_table.csv"):
        """
        Open file dialog to select export destination.
        
        Args:
            default_dir (str, optional): Default directory to start in
            default_filename (str, optional): Default filename to suggest
        
        Returns:
            str: Selected export file path or empty string if canceled
        """
        # Use current directory if no default provided
        if not default_dir:
            default_dir = os.getcwd()
        
        # Combine path and filename
        default_path = os.path.join(default_dir, default_filename)
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Export Summary Table", 
            default_path, 
            "CSV Files (*.csv)"
        )
        
        return file_path