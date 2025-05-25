# controllers/action_map_controller.py
import logging
import os
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox

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
    
    def _connect_model_signals(self):
        """Connect signals from the model."""
        self._model.map_changed.connect(self.on_map_changed)
        # Add connection for active behaviors changed signal
        self._model.active_behaviors_changed.connect(self.on_active_behaviors_changed)
    
    def _connect_view_signals(self):
        """Connect signals from the view."""
        self._view.add_mapping_requested.connect(self.on_add_mapping_requested)
        self._view.edit_mapping_requested.connect(self.on_edit_mapping_requested)
        self._view.remove_mapping_requested.connect(self.on_remove_mapping_requested)
    
    @Slot()
    def on_map_changed(self):
        """Handle action map changes."""
        # Update action map view with current mappings
        self._view.update_mappings(self._model.get_all_mappings())
        
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
    
    @Slot()
    def on_add_mapping_requested(self):
        """Handle request to add a new mapping."""
        # View will show dialog and emit edit_mapping_requested signal
        pass
    
    @Slot(str, str)
    def on_edit_mapping_requested(self, key, behavior):
        """
        Handle request to add or edit a mapping.
        
        Args:
            key (str): Key character
            behavior (str): Behavior label
        """
        # Add or update the mapping in the model
        if self._model.add_mapping(key, behavior):
            self.logger.info(f"Mapping added/updated: {key} -> {behavior}")
    
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
            
            # Load the action map
            if self._model.load_from_json(file_path):
                self.logger.info(f"Action map loaded from: {file_path}")
                QMessageBox.information(
                    self._view,
                    "Action Map Loaded",
                    f"Action map loaded from {file_path}."
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