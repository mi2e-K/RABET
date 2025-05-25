# views/metrics_config_dialog.py
import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QCheckBox, QComboBox, QLineEdit,
    QGroupBox, QListWidget, QListWidgetItem, QAbstractItemView,
    QDialogButtonBox, QFormLayout, QInputDialog, QFrame
)
from PySide6.QtCore import Qt, Signal

class MetricsConfigDialog(QDialog):
    """
    Dialog for configuring analysis metrics.
    Allows users to define custom latency and total time metrics.
    """
    
    def __init__(self, parent=None, behaviors=None, config=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        
        # Store behaviors list and config
        self._behaviors = behaviors or []
        self._config = config
        
        # Initialize UI
        self.setWindowTitle("Configure Analysis Metrics")
        self.resize(700, 500)
        self.setup_ui()
        
        # Load current configurations
        self.load_configurations()
    
    def setup_ui(self):
        """Set up the dialog UI."""
        # Main layout
        self.layout = QVBoxLayout(self)
        
        # Tab widget for different metric types
        self.tab_widget = QTabWidget()
        
        # Tab for latency metrics
        self.latency_tab = QWidget()
        self.latency_layout = QVBoxLayout(self.latency_tab)
        
        # Latency metrics table
        self.latency_table = QTableWidget()
        self.latency_table.setColumnCount(3)
        self.latency_table.setHorizontalHeaderLabels(["Metric Name", "Target Behavior", "Enabled"])
        self.latency_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.latency_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.latency_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.latency_layout.addWidget(self.latency_table)
        
        # Latency buttons
        self.latency_buttons_layout = QHBoxLayout()
        self.add_latency_button = QPushButton("Add")
        self.edit_latency_button = QPushButton("Edit")
        self.remove_latency_button = QPushButton("Remove")
        self.latency_buttons_layout.addWidget(self.add_latency_button)
        self.latency_buttons_layout.addWidget(self.edit_latency_button)
        self.latency_buttons_layout.addWidget(self.remove_latency_button)
        self.latency_buttons_layout.addStretch()
        self.latency_layout.addLayout(self.latency_buttons_layout)
        
        # Connect latency buttons
        self.add_latency_button.clicked.connect(self.add_latency_metric)
        self.edit_latency_button.clicked.connect(self.edit_latency_metric)
        self.remove_latency_button.clicked.connect(self.remove_latency_metric)
        
        # Tab for total time metrics
        self.total_time_tab = QWidget()
        self.total_time_layout = QVBoxLayout(self.total_time_tab)
        
        # Total time metrics table
        self.total_time_table = QTableWidget()
        self.total_time_table.setColumnCount(3)
        self.total_time_table.setHorizontalHeaderLabels(["Metric Name", "Included Behaviors", "Enabled"])
        self.total_time_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.total_time_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.total_time_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.total_time_layout.addWidget(self.total_time_table)
        
        # Total time buttons
        self.total_time_buttons_layout = QHBoxLayout()
        self.add_total_time_button = QPushButton("Add")
        self.edit_total_time_button = QPushButton("Edit")
        self.remove_total_time_button = QPushButton("Remove")
        self.total_time_buttons_layout.addWidget(self.add_total_time_button)
        self.total_time_buttons_layout.addWidget(self.edit_total_time_button)
        self.total_time_buttons_layout.addWidget(self.remove_total_time_button)
        self.total_time_buttons_layout.addStretch()
        self.total_time_layout.addLayout(self.total_time_buttons_layout)
        
        # Connect total time buttons
        self.add_total_time_button.clicked.connect(self.add_total_time_metric)
        self.edit_total_time_button.clicked.connect(self.edit_total_time_metric)
        self.remove_total_time_button.clicked.connect(self.remove_total_time_metric)
        
        # Add tabs
        self.tab_widget.addTab(self.latency_tab, "Latency Metrics")
        self.tab_widget.addTab(self.total_time_tab, "Total Time Metrics")
        self.layout.addWidget(self.tab_widget)
        
        # Add explanation text
        explanation_text = (
            "<b>Latency Metrics:</b> Measure the time from recording start to the first occurrence of a specific behavior.<br>"
            "<b>Total Time Metrics:</b> Calculate the total duration of specified behaviors, accounting for overlaps."
        )
        explanation_label = QLabel(explanation_text)
        explanation_label.setWordWrap(True)
        explanation_label.setStyleSheet("color: #777777; font-style: italic;")
        self.layout.addWidget(explanation_label)
        
        # Create buttons for the bottom of the dialog
        # Create Restore Defaults button
        self.restore_button = QPushButton("Restore Defaults")
        self.restore_button.clicked.connect(self.restore_defaults)
        
        # Create standard dialog buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        
        # Create Save/Load config buttons
        self.save_button = QPushButton("Save Config...")
        self.save_button.clicked.connect(self.save_config)
        self.load_button = QPushButton("Load Config...")
        self.load_button.clicked.connect(self.load_config)
        
        # Add all buttons to the horizontal layout
        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(self.restore_button)
        buttons_layout.addWidget(self.save_button)
        buttons_layout.addWidget(self.load_button)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.button_box)
        
        # Add the button layout to the main layout
        self.layout.addLayout(buttons_layout)
    
    def load_configurations(self):
        """Load current metric configurations into the UI."""
        if not self._config:
            return
        
        # Load latency metrics
        self.latency_table.setRowCount(0)
        for metric in self._config.get_latency_metrics():
            self._add_latency_row(metric["name"], metric["behavior"], metric["enabled"])
        
        # Load total time metrics
        self.total_time_table.setRowCount(0)
        for metric in self._config.get_total_time_metrics():
            behaviors_str = ", ".join(metric["behaviors"])
            self._add_total_time_row(metric["name"], behaviors_str, metric["enabled"])
    
    def _add_latency_row(self, name, behavior, enabled):
        """
        Add a row to the latency metrics table.
        
        Args:
            name (str): Metric name
            behavior (str): Target behavior
            enabled (bool): Whether the metric is enabled
        """
        # Create new row
        row = self.latency_table.rowCount()
        self.latency_table.insertRow(row)
        
        # Add name item
        name_item = QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # Make non-editable
        self.latency_table.setItem(row, 0, name_item)
        
        # Add behavior item
        behavior_item = QTableWidgetItem(behavior)
        behavior_item.setFlags(behavior_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.latency_table.setItem(row, 1, behavior_item)
        
        # Add enabled checkbox
        enabled_checkbox = QTableWidgetItem()
        enabled_checkbox.setFlags(enabled_checkbox.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        enabled_checkbox.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
        self.latency_table.setItem(row, 2, enabled_checkbox)
    
    def _add_total_time_row(self, name, behaviors, enabled):
        """
        Add a row to the total time metrics table.
        
        Args:
            name (str): Metric name
            behaviors (str): Comma-separated list of behaviors
            enabled (bool): Whether the metric is enabled
        """
        # Create new row
        row = self.total_time_table.rowCount()
        self.total_time_table.insertRow(row)
        
        # Add name item
        name_item = QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # Make non-editable
        self.total_time_table.setItem(row, 0, name_item)
        
        # Add behaviors item
        behaviors_item = QTableWidgetItem(behaviors)
        behaviors_item.setFlags(behaviors_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.total_time_table.setItem(row, 1, behaviors_item)
        
        # Add enabled checkbox
        enabled_checkbox = QTableWidgetItem()
        enabled_checkbox.setFlags(enabled_checkbox.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        enabled_checkbox.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
        self.total_time_table.setItem(row, 2, enabled_checkbox)
    
    def add_latency_metric(self):
        """Show dialog to add a new latency metric."""
        # Create dialog
        dialog = LatencyMetricDialog(self, self._behaviors)
        
        # Show dialog
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Get values
            name = dialog.name_edit.text()
            behavior = dialog.get_selected_behavior()
            enabled = True
            
            # Check if name exists
            if self._check_latency_name_exists(name):
                QMessageBox.warning(self, "Duplicate Name", f"A metric with the name '{name}' already exists.")
                return
            
            # Add to table
            self._add_latency_row(name, behavior, enabled)
    
    def edit_latency_metric(self):
        """Show dialog to edit a selected latency metric."""
        # Get selected row
        selected_rows = self.latency_table.selectedItems()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select a metric to edit.")
            return
        
        row = selected_rows[0].row()
        
        # Get current values
        name = self.latency_table.item(row, 0).text()
        behavior = self.latency_table.item(row, 1).text()
        enabled = self.latency_table.item(row, 2).checkState() == Qt.CheckState.Checked
        
        # Create dialog
        dialog = LatencyMetricDialog(self, self._behaviors, name, behavior, enabled)
        
        # Show dialog
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Get new values
            new_name = dialog.name_edit.text()
            new_behavior = dialog.get_selected_behavior()
            new_enabled = dialog.enabled_checkbox.isChecked()
            
            # Check if name exists (if changed)
            if name != new_name and self._check_latency_name_exists(new_name):
                QMessageBox.warning(self, "Duplicate Name", f"A metric with the name '{new_name}' already exists.")
                return
            
            # Update table
            self.latency_table.item(row, 0).setText(new_name)
            self.latency_table.item(row, 1).setText(new_behavior)
            self.latency_table.item(row, 2).setCheckState(
                Qt.CheckState.Checked if new_enabled else Qt.CheckState.Unchecked
            )
    
    def remove_latency_metric(self):
        """Remove a selected latency metric."""
        # Get selected row
        selected_rows = self.latency_table.selectedItems()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select a metric to remove.")
            return
        
        row = selected_rows[0].row()
        
        # Get metric name
        name = self.latency_table.item(row, 0).text()
        
        # Confirm removal
        result = QMessageBox.question(
            self, 
            "Confirm Removal",
            f"Are you sure you want to remove the latency metric '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if result == QMessageBox.StandardButton.Yes:
            # Check if this is the last metric
            if self.latency_table.rowCount() <= 1:
                QMessageBox.warning(
                    self,
                    "Cannot Remove",
                    "At least one latency metric must remain."
                )
                return
            
            # Remove from table
            self.latency_table.removeRow(row)
    
    def add_total_time_metric(self):
        """Show dialog to add a new total time metric."""
        # Create dialog
        dialog = TotalTimeMetricDialog(self, self._behaviors)
        
        # Show dialog
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Get values
            name = dialog.name_edit.text()
            selected_behaviors = dialog.get_selected_behaviors()
            enabled = True
            
            # Check if name exists
            if self._check_total_time_name_exists(name):
                QMessageBox.warning(self, "Duplicate Name", f"A metric with the name '{name}' already exists.")
                return
            
            # Check if behaviors are selected
            if not selected_behaviors:
                QMessageBox.warning(self, "No Behaviors", "Please select at least one behavior.")
                return
            
            # Add to table
            behaviors_str = ", ".join(selected_behaviors)
            self._add_total_time_row(name, behaviors_str, enabled)
    
    def edit_total_time_metric(self):
        """Show dialog to edit a selected total time metric."""
        # Get selected row
        selected_rows = self.total_time_table.selectedItems()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select a metric to edit.")
            return
        
        row = selected_rows[0].row()
        
        # Get current values
        name = self.total_time_table.item(row, 0).text()
        behaviors_str = self.total_time_table.item(row, 1).text()
        behaviors = [b.strip() for b in behaviors_str.split(",")]
        enabled = self.total_time_table.item(row, 2).checkState() == Qt.CheckState.Checked
        
        # Create dialog
        dialog = TotalTimeMetricDialog(self, self._behaviors, name, behaviors, enabled)
        
        # Show dialog
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Get new values
            new_name = dialog.name_edit.text()
            selected_behaviors = dialog.get_selected_behaviors()
            new_enabled = dialog.enabled_checkbox.isChecked()
            
            # Check if name exists (if changed)
            if name != new_name and self._check_total_time_name_exists(new_name):
                QMessageBox.warning(self, "Duplicate Name", f"A metric with the name '{new_name}' already exists.")
                return
            
            # Check if behaviors are selected
            if not selected_behaviors:
                QMessageBox.warning(self, "No Behaviors", "Please select at least one behavior.")
                return
            
            # Update table
            behaviors_str = ", ".join(selected_behaviors)
            self.total_time_table.item(row, 0).setText(new_name)
            self.total_time_table.item(row, 1).setText(behaviors_str)
            self.total_time_table.item(row, 2).setCheckState(
                Qt.CheckState.Checked if new_enabled else Qt.CheckState.Unchecked
            )
    
    def remove_total_time_metric(self):
        """Remove a selected total time metric."""
        # Get selected row
        selected_rows = self.total_time_table.selectedItems()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select a metric to remove.")
            return
        
        row = selected_rows[0].row()
        
        # Get metric name
        name = self.total_time_table.item(row, 0).text()
        
        # Confirm removal
        result = QMessageBox.question(
            self, 
            "Confirm Removal",
            f"Are you sure you want to remove the total time metric '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if result == QMessageBox.StandardButton.Yes:
            # Check if this is the last metric
            if self.total_time_table.rowCount() <= 1:
                QMessageBox.warning(
                    self,
                    "Cannot Remove",
                    "At least one total time metric must remain."
                )
                return
            
            # Remove from table
            self.total_time_table.removeRow(row)
    
    def restore_defaults(self):
        """Restore default metric configurations."""
        # Confirm restoration
        result = QMessageBox.question(
            self, 
            "Restore Defaults",
            "This will reset all metrics to their default values. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if result == QMessageBox.StandardButton.Yes:
            # Reset the configuration
            self._config.reset_to_defaults()
            
            # Reload the UI
            self.load_configurations()
    
    def save_config(self):
        """Save metrics configuration to a JSON file."""
        # Find configs directory
        default_dir = self._get_configs_directory()
        
        # Get file path
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Metrics Configuration",
            os.path.join(default_dir, "metrics_config.json"),
            "JSON Files (*.json)"
        )
        
        if not file_path:
            return
        
        # Add .json extension if not present
        if not file_path.lower().endswith('.json'):
            file_path += '.json'
        
        # Get current configurations
        latency_metrics = self.get_latency_metrics()
        total_time_metrics = self.get_total_time_metrics()
        
        # Create a temporary config object to save the current state
        from models.analysis_config import AnalysisMetricsConfig
        temp_config = AnalysisMetricsConfig()
        
        # Clear default metrics
        temp_config._latency_metrics = []
        temp_config._total_time_metrics = []
        
        # Add current metrics
        for metric in latency_metrics:
            temp_config._latency_metrics.append(metric)
        
        for metric in total_time_metrics:
            temp_config._total_time_metrics.append(metric)
        
        # Save to file
        if temp_config.save_to_json(file_path):
            QMessageBox.information(
                self,
                "Save Successful",
                f"Metrics configuration saved to:\n{file_path}"
            )
        else:
            QMessageBox.warning(
                self,
                "Save Failed",
                f"Failed to save metrics configuration to:\n{file_path}"
            )
    
    def load_config(self):
        """Load metrics configuration from a JSON file."""
        # Find configs directory
        default_dir = self._get_configs_directory()
        
        # Get file path
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Metrics Configuration",
            default_dir,
            "JSON Files (*.json)"
        )
        
        if not file_path:
            return
        
        # Create a temporary config object to load the file
        from models.analysis_config import AnalysisMetricsConfig
        temp_config = AnalysisMetricsConfig()
        
        # Load from file
        if temp_config.load_from_json(file_path):
            # Confirm before replacing current configuration
            result = QMessageBox.question(
                self,
                "Replace Configuration",
                "This will replace your current metrics configuration. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if result != QMessageBox.StandardButton.Yes:
                return
            
            # Update UI with loaded configuration
            self.latency_table.setRowCount(0)
            for metric in temp_config.get_latency_metrics():
                self._add_latency_row(
                    metric["name"],
                    metric["behavior"],
                    metric.get("enabled", True)
                )
            
            self.total_time_table.setRowCount(0)
            for metric in temp_config.get_total_time_metrics():
                behaviors_str = ", ".join(metric["behaviors"])
                self._add_total_time_row(
                    metric["name"],
                    behaviors_str,
                    metric.get("enabled", True)
                )
            
            QMessageBox.information(
                self,
                "Load Successful",
                f"Metrics configuration loaded from:\n{file_path}"
            )
        else:
            QMessageBox.warning(
                self,
                "Load Failed",
                f"Failed to load metrics configuration from:\n{file_path}"
            )
            
    def _get_configs_directory(self):
        """
        Get the directory for metrics configurations.
        Attempts to find or create a 'configs' directory.
        
        Returns:
            str: Path to the configs directory
        """
        # Look in common locations
        possible_paths = [
            "configs",  # Current directory
            os.path.join("..", "configs"),  # Parent directory
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "configs")  # Relative to script
        ]
        
        # For packaged app, also check relative to executable
        if getattr(sys, 'frozen', False):
            # We're running in a bundle
            bundle_dir = os.path.dirname(sys.executable)
            possible_paths.append(os.path.join(bundle_dir, "configs"))
        
        # Find first existing configs directory
        for path in possible_paths:
            if os.path.exists(path) and os.path.isdir(path):
                return os.path.abspath(path)
        
        # If not found, create one in current directory
        os.makedirs("configs", exist_ok=True)
        return os.path.abspath("configs")
    
    def _check_latency_name_exists(self, name):
        """
        Check if a latency metric with the given name already exists.
        
        Args:
            name (str): Metric name to check
            
        Returns:
            bool: True if name exists, False otherwise
        """
        for row in range(self.latency_table.rowCount()):
            if self.latency_table.item(row, 0).text() == name:
                return True
        return False
    
    def _check_total_time_name_exists(self, name):
        """
        Check if a total time metric with the given name already exists.
        
        Args:
            name (str): Metric name to check
            
        Returns:
            bool: True if name exists, False otherwise
        """
        for row in range(self.total_time_table.rowCount()):
            if self.total_time_table.item(row, 0).text() == name:
                return True
        return False
    
    def get_latency_metrics(self):
        """
        Get the current latency metrics configuration.
        
        Returns:
            list: List of latency metric configurations
        """
        metrics = []
        for row in range(self.latency_table.rowCount()):
            name = self.latency_table.item(row, 0).text()
            behavior = self.latency_table.item(row, 1).text()
            enabled = self.latency_table.item(row, 2).checkState() == Qt.CheckState.Checked
            
            metrics.append({
                "name": name,
                "behavior": behavior,
                "enabled": enabled
            })
        
        return metrics
    
    def get_total_time_metrics(self):
        """
        Get the current total time metrics configuration.
        
        Returns:
            list: List of total time metric configurations
        """
        metrics = []
        for row in range(self.total_time_table.rowCount()):
            name = self.total_time_table.item(row, 0).text()
            behaviors_str = self.total_time_table.item(row, 1).text()
            behaviors = [b.strip() for b in behaviors_str.split(",")]
            enabled = self.total_time_table.item(row, 2).checkState() == Qt.CheckState.Checked
            
            metrics.append({
                "name": name,
                "behaviors": behaviors,
                "enabled": enabled
            })
        
        return metrics


class LatencyMetricDialog(QDialog):
    """Dialog for adding or editing a latency metric."""
    
    def __init__(self, parent=None, behaviors=None, name="", behavior="", enabled=True):
        super().__init__(parent)
        
        self._behaviors = behaviors or []
        self._custom_behaviors = []  # List to store custom behaviors added during this dialog session
        
        self.setWindowTitle("Latency Metric")
        self.resize(400, 250)
        
        # Main layout
        self.layout = QVBoxLayout(self)
        
        # Form layout
        self.form_layout = QFormLayout()
        
        # Name field
        self.name_edit = QLineEdit(name)
        self.form_layout.addRow("Name:", self.name_edit)
        
        # Behavior selection section
        self.behavior_section_layout = QVBoxLayout()
        
        # Dropdown with existing behaviors
        self.behavior_selection_layout = QHBoxLayout()
        self.behavior_combo = QComboBox()
        self.update_behavior_combo(behavior)  # Initial population of dropdown
        
        self.behavior_selection_layout.addWidget(self.behavior_combo, 1)
        
        # Add custom behavior button
        self.add_custom_behavior_btn = QPushButton("Add Custom...")
        self.add_custom_behavior_btn.clicked.connect(self.add_custom_behavior)
        self.behavior_selection_layout.addWidget(self.add_custom_behavior_btn)
        
        self.behavior_section_layout.addLayout(self.behavior_selection_layout)
        
        # Add the behavior section to the form
        self.form_layout.addRow("Target Behavior:", self.behavior_section_layout)
        
        # Enabled checkbox
        self.enabled_checkbox = QCheckBox("Enabled")
        self.enabled_checkbox.setChecked(enabled)
        self.form_layout.addRow("", self.enabled_checkbox)
        
        self.layout.addLayout(self.form_layout)
        
        # Explanation text
        explanation_text = (
            "A latency metric measures the time from the start of recording to the "
            "first occurrence of the specified behavior.\n\n"
            "You can select an existing behavior from the dropdown or add a custom behavior name."
        )
        explanation_label = QLabel(explanation_text)
        explanation_label.setWordWrap(True)
        explanation_label.setStyleSheet("color: #777777; font-style: italic;")
        self.layout.addWidget(explanation_label)
        
        # Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.validate_and_accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)
    
    def update_behavior_combo(self, selected_behavior=""):
        """
        Update the behavior combo box with existing and custom behaviors.
        
        Args:
            selected_behavior (str, optional): Behavior to select
        """
        self.behavior_combo.clear()
        
        # Add all behaviors from both standard list and custom additions
        all_behaviors = self._behaviors + self._custom_behaviors
        self.behavior_combo.addItems(all_behaviors)
        
        # Select the specified behavior if it exists
        if selected_behavior and selected_behavior in all_behaviors:
            self.behavior_combo.setCurrentText(selected_behavior)
    
    def add_custom_behavior(self):
        """Show dialog to add a custom behavior name."""
        custom_behavior, ok = QInputDialog.getText(
            self,
            "Add Custom Behavior",
            "Enter custom behavior name:",
            QLineEdit.EchoMode.Normal,
            ""
        )
        
        if ok and custom_behavior:
            # Check if this behavior already exists
            all_behaviors = self._behaviors + self._custom_behaviors
            if custom_behavior in all_behaviors:
                QMessageBox.warning(
                    self,
                    "Duplicate Behavior",
                    f"The behavior '{custom_behavior}' already exists in the list."
                )
                return
            
            # Add the custom behavior to our list
            self._custom_behaviors.append(custom_behavior)
            
            # Update the combo box and select the new behavior
            self.update_behavior_combo(custom_behavior)
    
    def get_selected_behavior(self):
        """
        Get the selected behavior.
        
        Returns:
            str: Selected behavior name
        """
        return self.behavior_combo.currentText()
    
    def validate_and_accept(self):
        """Validate inputs before accepting."""
        name = self.name_edit.text().strip()
        behavior = self.get_selected_behavior()
        
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a name for the metric.")
            return
        
        if not behavior:
            QMessageBox.warning(self, "Missing Behavior", "Please select or add a target behavior.")
            return
        
        self.accept()


class TotalTimeMetricDialog(QDialog):
    """Dialog for adding or editing a total time metric."""
    
    def __init__(self, parent=None, behaviors=None, name="", selected_behaviors=None, enabled=True):
        super().__init__(parent)
        
        self._behaviors = behaviors or []
        self._selected_behaviors = selected_behaviors or []
        self._custom_behaviors = []  # List to store custom behaviors added during this dialog session
        
        self.setWindowTitle("Total Time Metric")
        self.resize(500, 500)
        
        # Main layout
        self.layout = QVBoxLayout(self)
        
        # Form layout for name and enabled
        self.form_layout = QFormLayout()
        
        # Name field
        self.name_edit = QLineEdit(name)
        self.form_layout.addRow("Name:", self.name_edit)
        
        # Enabled checkbox
        self.enabled_checkbox = QCheckBox("Enabled")
        self.enabled_checkbox.setChecked(enabled)
        self.form_layout.addRow("", self.enabled_checkbox)
        
        self.layout.addLayout(self.form_layout)
        
        # Behaviors selection
        self.behaviors_group = QGroupBox("Included Behaviors")
        self.behaviors_layout = QVBoxLayout(self.behaviors_group)
        
        # Add custom behavior section
        self.custom_behavior_layout = QHBoxLayout()
        self.custom_behavior_edit = QLineEdit()
        self.custom_behavior_edit.setPlaceholderText("Enter custom behavior name")
        self.custom_behavior_layout.addWidget(self.custom_behavior_edit, 1)
        
        self.add_custom_btn = QPushButton("Add Custom")
        self.add_custom_btn.clicked.connect(self.add_custom_behavior)
        self.custom_behavior_layout.addWidget(self.add_custom_btn)
        
        self.behaviors_layout.addLayout(self.custom_behavior_layout)
        
        # Add divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        self.behaviors_layout.addWidget(divider)
        
        # Behaviors list with checkbox items
        self.behaviors_list = QListWidget()
        
        # Add behaviors to list
        self.update_behaviors_list()
        
        self.behaviors_layout.addWidget(self.behaviors_list)
        
        # Select all/none buttons
        self.select_buttons_layout = QHBoxLayout()
        self.select_all_button = QPushButton("Select All")
        self.select_none_button = QPushButton("Select None")
        self.select_all_button.clicked.connect(self.select_all_behaviors)
        self.select_none_button.clicked.connect(self.select_no_behaviors)
        self.select_buttons_layout.addWidget(self.select_all_button)
        self.select_buttons_layout.addWidget(self.select_none_button)
        self.behaviors_layout.addLayout(self.select_buttons_layout)
        
        self.layout.addWidget(self.behaviors_group)
        
        # Explanation text
        explanation_text = (
            "A total time metric calculates the total duration of the selected behaviors, "
            "accounting for overlaps between behaviors. For example, 'Total Aggression' might "
            "include multiple aggressive behaviors.\n\n"
            "You can select from existing behaviors or add custom behavior names."
        )
        explanation_label = QLabel(explanation_text)
        explanation_label.setWordWrap(True)
        explanation_label.setStyleSheet("color: #777777; font-style: italic;")
        self.layout.addWidget(explanation_label)
        
        # Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.validate_and_accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)
    
    def update_behaviors_list(self):
        """Update the behaviors list with all available behaviors."""
        # Remember the currently selected behaviors
        currently_selected = []
        for i in range(self.behaviors_list.count()):
            item = self.behaviors_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                currently_selected.append(item.text())
        
        # Clear the list
        self.behaviors_list.clear()
        
        # Add both standard and custom behaviors
        all_behaviors = self._behaviors + self._custom_behaviors
        
        # Remove duplicates (shouldn't happen, but just in case)
        all_behaviors = list(dict.fromkeys(all_behaviors))
        
        for behavior in all_behaviors:
            item = QListWidgetItem(behavior)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            
            # Check if this behavior should be selected
            if behavior in currently_selected or behavior in self._selected_behaviors:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
                
            self.behaviors_list.addItem(item)
    
    def add_custom_behavior(self):
        """Add a custom behavior to the list."""
        custom_behavior = self.custom_behavior_edit.text().strip()
        
        if not custom_behavior:
            return
        
        # Check if this behavior already exists
        all_behaviors = self._behaviors + self._custom_behaviors
        if custom_behavior in all_behaviors:
            QMessageBox.warning(
                self,
                "Duplicate Behavior",
                f"The behavior '{custom_behavior}' already exists in the list."
            )
            return
        
        # Add to custom behaviors
        self._custom_behaviors.append(custom_behavior)
        
        # Update the list
        self.update_behaviors_list()
        
        # Clear the input field
        self.custom_behavior_edit.clear()
    
    def select_all_behaviors(self):
        """Select all behaviors."""
        for i in range(self.behaviors_list.count()):
            self.behaviors_list.item(i).setCheckState(Qt.CheckState.Checked)
    
    def select_no_behaviors(self):
        """Deselect all behaviors."""
        for i in range(self.behaviors_list.count()):
            self.behaviors_list.item(i).setCheckState(Qt.CheckState.Unchecked)
    
    def get_selected_behaviors(self):
        """
        Get list of selected behaviors.
        
        Returns:
            list: Selected behaviors
        """
        selected = []
        for i in range(self.behaviors_list.count()):
            item = self.behaviors_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
        return selected
    
    def validate_and_accept(self):
        """Validate inputs before accepting."""
        name = self.name_edit.text().strip()
        selected_behaviors = self.get_selected_behaviors()
        
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a name for the metric.")
            return
        
        if not selected_behaviors:
            QMessageBox.warning(self, "No Behaviors", "Please select at least one behavior.")
            return
        
        self.accept()