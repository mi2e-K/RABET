# controllers/action_map_controller.py
import logging
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox, QMenu
from PySide6.QtGui import QAction

class ActionMapController(QObject):
    """
    Controller for managing key-to-behavior mappings.
    """
    
    def __init__(self, action_map_model, action_map_view):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing ActionMapController")
        
        self._model = action_map_model
        self._view = action_map_view
        
        # Connect model signals
        self._connect_model_signals()
        
        # Connect view signals
        self._connect_view_signals()
        
        # Trigger initial view update now that connections are established
        self._model.initialize_view()
    
    def _connect_model_signals(self):
        """Connect signals from the model."""
        self._model.map_changed.connect(self.on_map_changed)
        # Add connection for active behaviors changed signal
        self._model.active_behaviors_changed.connect(self.on_active_behaviors_changed)
    
    def _connect_view_signals(self):
        """Connect signals from the view."""
        self._view.edit_mapping_requested.connect(self.on_edit_mapping_requested)
        self._view.remove_mapping_requested.connect(self.on_remove_mapping_requested)
    
    @Slot()
    def on_map_changed(self):
        """Handle action map changes."""
        # Update action map view with current mappings (+ per-key kind, 1.4.0)
        self._view.update_mappings(
            self._model.get_all_mappings(), self._model.get_all_kinds()
        )
        
        # Also update active behaviors display
        self._view.update_active_behaviors(self._model.get_active_behaviors())
        
        self.logger.debug("Action map view updated")
    
    @Slot()
    def on_active_behaviors_changed(self):
        """Handle changes to active behaviors."""
        # Update active behaviors display
        active_behaviors = self._model.get_active_behaviors()
        self._view.update_active_behaviors(active_behaviors)
        self.logger.debug(f"Active behaviors updated: {active_behaviors}")
    
    @Slot(str, str, str)
    def on_edit_mapping_requested(self, key, behavior, kind="state"):
        """
        Handle request to add or edit a mapping.

        Args:
            key (str): Key character
            behavior (str): Behavior label
            kind (str): "state" or "point" (1.4.0)
        """
        # Add or update the mapping in the model
        if self._model.add_mapping(key, behavior, kind=kind):
            self.logger.info(f"Mapping added/updated: {key} -> {behavior} ({kind})")
    
    @Slot(str)
    def on_remove_mapping_requested(self, key):
        """
        Handle request to remove a mapping.
        
        Args:
            key (str): Key character
        """
        # Remove the mapping from the model
        if self._model.remove_mapping(key):
            self.logger.info(f"Mapping removed: {key}")
    
    @Slot()
    def load_action_map_dialog(self):
        """Open a dialog to load an action map from JSON."""
        file_path, _ = QFileDialog.getOpenFileName(
            self._view, "Load Action Map", "", "JSON Files (*.json)"
        )
        
        if file_path:
            # Confirm if there are existing mappings
            if self._model.get_all_mappings():
                result = QMessageBox.question(
                    self._view,
                    "Existing Mappings",
                    "Loading will replace existing mappings. Continue?",
                    QMessageBox.Yes | QMessageBox.No
                )
                
                if result != QMessageBox.Yes:
                    return
            
            # Load the action map (auto_save=True will persist it as user map)
            if self._model.load_from_json(file_path, auto_save=True):
                self.logger.info(f"Action map loaded from: {file_path}")
                QMessageBox.information(
                    self._view,
                    "Action Map Loaded",
                    f"Action map loaded successfully from {file_path}."
                )
            else:
                self.logger.error(f"Failed to load action map from: {file_path}")
    
    @Slot()
    def save_action_map_dialog(self):
        """Open a dialog to save the action map to JSON."""
        # Check if there are any mappings to save
        if not self._model.get_all_mappings():
            QMessageBox.information(
                self._view,
                "No Mappings",
                "There are no mappings to save."
            )
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self._view, "Save Action Map", "", "JSON Files (*.json)"
        )
        
        if file_path:
            # Add .json extension if not present
            if not file_path.lower().endswith('.json'):
                file_path += '.json'
                
            # Save the action map
            if self._model.save_to_json(file_path):
                self.logger.info(f"Action map saved to: {file_path}")
                QMessageBox.information(
                    self._view,
                    "Action Map Saved",
                    f"Action map saved to {file_path}."
                )
            else:
                self.logger.error(f"Failed to save action map to: {file_path}")
    
    @Slot()
    def reset_to_default(self):
        """Reset action map to default configuration."""
        # Confirm reset
        result = QMessageBox.question(
            self._view,
            "Reset to Default",
            "Are you sure you want to reset the action map to default settings?\n"
            "This will replace all current mappings.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if result == QMessageBox.Yes:
            if self._model.reset_to_default():
                QMessageBox.information(
                    self._view,
                    "Reset Complete",
                    "Action map has been reset to default settings."
                )
            else:
                QMessageBox.warning(
                    self._view,
                    "Reset Failed",
                    "Failed to reset action map to default settings."
                )
    
    def create_action_map_menu(self):
        """
        Create a menu with action map operations.
        
        Returns:
            QMenu: Menu with action map operations
        """
        menu = QMenu("Action Map", self._view)
        
        # Load action
        load_action = QAction("Load from file...", self._view)
        load_action.triggered.connect(self.load_action_map_dialog)
        menu.addAction(load_action)
        
        # Save action
        save_action = QAction("Save to file...", self._view)
        save_action.triggered.connect(self.save_action_map_dialog)
        menu.addAction(save_action)
        
        menu.addSeparator()
        
        # Reset to default action
        reset_action = QAction("Reset to default", self._view)
        reset_action.triggered.connect(self.reset_to_default)
        menu.addAction(reset_action)
        
        return menu