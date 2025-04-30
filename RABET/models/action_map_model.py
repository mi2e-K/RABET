# models/action_map_model.py
import json
import logging
from PySide6.QtCore import QObject, Signal, Slot

class ActionMapModel(QObject):
    """
    Model for managing key-to-behavior mappings.
    
    Signals:
        map_changed: Emitted when the action map changes
        active_behaviors_changed: Emitted when active behaviors change
        error_occurred: Emitted when an error occurs
    """
    
    map_changed = Signal()
    active_behaviors_changed = Signal()  # New signal for active behavior changes
    error_occurred = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing ActionMapModel")
        
        # Initialize empty action map
        self._action_map = {}
        self._active_behaviors = set()  # Currently active behaviors
    
    def load_from_json(self, json_path):
        """
        Load action map from a JSON file.
        
        Args:
            json_path (str): Path to the JSON file
            
        Returns:
            bool: True if loaded successfully, False otherwise
        """
        try:
            self.logger.info(f"Loading action map from: {json_path}")
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            # Validate format
            if not isinstance(data, dict):
                raise ValueError("Action map must be a dictionary")
            
            # Validate key format
            for key, value in data.items():
                if not isinstance(key, str) or len(key) != 1:
                    raise ValueError(f"Invalid key format: {key}")
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"Invalid behavior label for key {key}: {value}")
            
            self._action_map = data
            self.map_changed.emit()
            return True
        except Exception as e:
            error_msg = f"Failed to load action map: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def save_to_json(self, json_path):
        """
        Save action map to a JSON file.
        
        Args:
            json_path (str): Path to the JSON file
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            self.logger.info(f"Saving action map to: {json_path}")
            with open(json_path, 'w') as f:
                json.dump(self._action_map, f, indent=2)
            return True
        except Exception as e:
            error_msg = f"Failed to save action map: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def add_mapping(self, key, behavior):
        """
        Add a new key-to-behavior mapping.
        
        Args:
            key (str): Key character
            behavior (str): Behavior label
            
        Returns:
            bool: True if added successfully, False otherwise
        """
        # Validate key
        if not isinstance(key, str) or len(key) != 1:
            error_msg = f"Invalid key format: {key}"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False
        
        # Validate behavior
        if not isinstance(behavior, str) or not behavior.strip():
            error_msg = f"Invalid behavior label: {behavior}"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False
        
        self.logger.debug(f"Adding mapping: {key} -> {behavior}")
        self._action_map[key] = behavior
        self.map_changed.emit()
        return True
    
    def remove_mapping(self, key):
        """
        Remove a key-to-behavior mapping.
        
        Args:
            key (str): Key character
            
        Returns:
            bool: True if removed successfully, False otherwise
        """
        if key in self._action_map:
            self.logger.debug(f"Removing mapping for key: {key}")
            del self._action_map[key]
            self.map_changed.emit()
            return True
        else:
            self.logger.warning(f"Key not found in action map: {key}")
            return False
    
    def get_behavior(self, key):
        """
        Get behavior label for a key.
        
        Args:
            key (str): Key character
            
        Returns:
            str: Behavior label or None if key not found
        """
        return self._action_map.get(key)
    
    def get_all_mappings(self):
        """
        Get all key-to-behavior mappings.
        
        Returns:
            dict: Dictionary of key-to-behavior mappings
        """
        return self._action_map.copy()
    
    def set_behavior_active(self, key, active=True):
        """
        Set a behavior as active or inactive.
        
        Args:
            key (str): Key character
            active (bool): True to set active, False to set inactive
        """
        behavior = self.get_behavior(key)
        if behavior:
            # Track the previous state to detect changes
            was_active = key in self._active_behaviors
            
            if active:
                self._active_behaviors.add(key)
                # Only emit if the state actually changed
                if not was_active:
                    self.logger.debug(f"Behavior '{behavior}' activated")
                    self.active_behaviors_changed.emit()
            else:
                self._active_behaviors.discard(key)
                # Only emit if the state actually changed
                if was_active:
                    self.logger.debug(f"Behavior '{behavior}' deactivated")
                    self.active_behaviors_changed.emit()
    
    def is_behavior_active(self, key):
        """
        Check if a behavior is currently active.
        
        Args:
            key (str): Key character
            
        Returns:
            bool: True if active, False otherwise
        """
        return key in self._active_behaviors
    
    def get_active_behaviors(self):
        """
        Get all currently active behaviors.
        
        Returns:
            dict: Dictionary of active key-to-behavior mappings
        """
        return {k: self._action_map[k] for k in self._active_behaviors if k in self._action_map}
    
    def clear_active_behaviors(self):
        """Clear all active behaviors."""
        if self._active_behaviors:
            self._active_behaviors.clear()
            self.active_behaviors_changed.emit()