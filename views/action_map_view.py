# views/action_map_view.py
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QLineEdit, QLabel, QDialogButtonBox, QMessageBox
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QBrush, QFont

class ActionMapView(QWidget):
    """
    View for displaying and editing action map.
    
    Signals:
        add_mapping_requested: Emitted when add mapping is requested
        edit_mapping_requested: Emitted when edit mapping is requested (key, new_behavior)
        remove_mapping_requested: Emitted when remove mapping is requested (key)
    """
    
    add_mapping_requested = Signal()
    edit_mapping_requested = Signal(str, str)
    remove_mapping_requested = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing ActionMapView")
        
        self.setup_ui()
        self.connect_signals()
    
    def setup_ui(self):
        """Set up user interface."""
        # Main layout
        self.layout = QVBoxLayout(self)
        
        # Title
        self.title_label = QLabel("Action Map")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.layout.addWidget(self.title_label)
        
        # Table for displaying key mappings
        self.mappings_table = QTableWidget()
        self.mappings_table.setColumnCount(2)
        self.mappings_table.setHorizontalHeaderLabels(["Key", "Behavior"])
        self.mappings_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.mappings_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.mappings_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.layout.addWidget(self.mappings_table)
        
        # Buttons layout
        self.buttons_layout = QHBoxLayout()
        
        # Add button
        self.add_button = QPushButton("Add")
        self.buttons_layout.addWidget(self.add_button)
        
        # Edit button
        self.edit_button = QPushButton("Edit")
        self.buttons_layout.addWidget(self.edit_button)
        
        # Remove button
        self.remove_button = QPushButton("Remove")
        self.buttons_layout.addWidget(self.remove_button)
        
        # Add buttons layout to main layout
        self.layout.addLayout(self.buttons_layout)
        
        # Active behaviors section
        self.active_label = QLabel("Active Behaviors:")
        self.active_label.setStyleSheet("font-weight: bold;")
        self.layout.addWidget(self.active_label)
        
        self.active_behaviors = QTableWidget()
        self.active_behaviors.setColumnCount(2)
        self.active_behaviors.setHorizontalHeaderLabels(["Key", "Behavior"])
        self.active_behaviors.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.active_behaviors.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.active_behaviors.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.active_behaviors.setMaximumHeight(150)
        self.layout.addWidget(self.active_behaviors)
    
    def connect_signals(self):
        """Connect widget signals to slots."""
        self.add_button.clicked.connect(self.on_add_clicked)
        self.edit_button.clicked.connect(self.on_edit_clicked)
        self.remove_button.clicked.connect(self.on_remove_clicked)
    
    def on_add_clicked(self):
        """Handle add button clicked."""
        dialog = ActionMapDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            key = dialog.key_edit.text()
            behavior = dialog.behavior_edit.text()
            
            if key and behavior:
                self.edit_mapping_requested.emit(key, behavior)
            else:
                QMessageBox.warning(self, "Invalid Input", "Key and behavior cannot be empty.")
    
    def on_edit_clicked(self):
        """Handle edit button clicked."""
        # Get selected row
        selected_rows = self.mappings_table.selectedItems()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select a mapping to edit.")
            return
        
        # Get key and current behavior
        row = selected_rows[0].row()
        key = self.mappings_table.item(row, 0).text()
        current_behavior = self.mappings_table.item(row, 1).text()
        
        # Show dialog with current values
        dialog = ActionMapDialog(self, key, current_behavior)
        dialog.key_edit.setEnabled(False)  # Can't edit the key
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_behavior = dialog.behavior_edit.text()
            
            if new_behavior:
                self.edit_mapping_requested.emit(key, new_behavior)
            else:
                QMessageBox.warning(self, "Invalid Input", "Behavior cannot be empty.")
    
    def on_remove_clicked(self):
        """Handle remove button clicked."""
        # Get selected row
        selected_rows = self.mappings_table.selectedItems()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select a mapping to remove.")
            return
        
        # Get key
        row = selected_rows[0].row()
        key = self.mappings_table.item(row, 0).text()
        
        # Confirm removal
        result = QMessageBox.question(
            self, "Confirm Removal", 
            f"Are you sure you want to remove the mapping for key '{key}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if result == QMessageBox.StandardButton.Yes:
            self.remove_mapping_requested.emit(key)
    
    @Slot(dict)
    def update_mappings(self, mappings):
        """
        Update the mappings table.
        
        Args:
            mappings (dict): Key-to-behavior mappings
        """
        self.mappings_table.setRowCount(0)
        
        for key, behavior in sorted(mappings.items()):
            row = self.mappings_table.rowCount()
            self.mappings_table.insertRow(row)
            
            key_item = QTableWidgetItem(key)
            behavior_item = QTableWidgetItem(behavior)
            
            self.mappings_table.setItem(row, 0, key_item)
            self.mappings_table.setItem(row, 1, behavior_item)
    
    @Slot(dict)
    def update_active_behaviors(self, active_behaviors):
        """
        Update the active behaviors table.
        
        Args:
            active_behaviors (dict): Key-to-behavior mappings for active behaviors
        """
        self.active_behaviors.setRowCount(0)
        
        self.logger.debug(f"Updating active behaviors: {active_behaviors}")
        
        # Set a distinctive font for active behaviors (instead of background color)
        font = QFont()
        font.setBold(True)
        
        for key, behavior in sorted(active_behaviors.items()):
            row = self.active_behaviors.rowCount()
            self.active_behaviors.insertRow(row)
            
            key_item = QTableWidgetItem(key)
            behavior_item = QTableWidgetItem(behavior)
            
            # Use bold font instead of background color
            key_item.setFont(font)
            behavior_item.setFont(font)
            
            self.active_behaviors.setItem(row, 0, key_item)
            self.active_behaviors.setItem(row, 1, behavior_item)


class ActionMapDialog(QDialog):
    """Dialog for adding or editing action map entries."""
    
    def __init__(self, parent=None, key="", behavior=""):
        super().__init__(parent)
        
        self.setWindowTitle("Action Map Entry")
        self.resize(300, 150)
        
        # Main layout
        self.layout = QVBoxLayout(self)
        
        # Key input
        self.key_layout = QHBoxLayout()
        self.key_label = QLabel("Key:")
        self.key_edit = QLineEdit(key)
        self.key_edit.setMaxLength(1)
        self.key_layout.addWidget(self.key_label)
        self.key_layout.addWidget(self.key_edit)
        self.layout.addLayout(self.key_layout)
        
        # Behavior input
        self.behavior_layout = QHBoxLayout()
        self.behavior_label = QLabel("Behavior:")
        self.behavior_edit = QLineEdit(behavior)
        self.behavior_layout.addWidget(self.behavior_label)
        self.behavior_layout.addWidget(self.behavior_edit)
        self.layout.addLayout(self.behavior_layout)
        
        # Buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)