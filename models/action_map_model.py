# models/action_map_model.py
import json
import logging
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot
from utils.config_path_manager import ConfigPathManager  # Import the new class

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
        
        # Initialize config path manager
        self._config_path_manager = ConfigPathManager()
        
        # Initialize empty action map
        self._action_map = {}
        self._active_behaviors = set()  # Currently active behaviors
        
        # Try to load default action map
        self._try_load_default_map()
    
    def _try_load_default_map(self):
        """
        Try to load the default action map from the configs directory.
        """
        try:
            # Get path to default action map
            config_path = self._config_path_manager.get_action_map_config_path("default_action_map.json")
            
            if config_path and config_path.exists():
                self.logger.info(f"Found default action map: {config_path}")
                if self.load_from_json(config_path):
                    self.logger.info(f"Loaded default action map from {config_path}")
                    return
                else:
                    self.logger.warning(f"Failed to load default action map from {config_path}")
            else:
                self.logger.info("Default action map not found")
                
                # Ensure default config exists for next time
                self._config_path_manager.ensure_default_configs()
        except Exception as e:
            self.logger.warning(f"Error loading default action map: {str(e)}")
            
        # If we get here, no valid action map was found
        # Create a default action map in the configs directory
        self.logger.info("Creating default action map in configs directory")
        try:
            # Create a default action map
            default_map = {
                "o": "Attack bites",
                "j": "Sideways threats",
                "p": "Tail rattles",
                "q": "Chasing",
                "a": "Social contact",
                "e": "Self-grooming",
                "t": "Locomotion",
                "r": "Rearing"
            }
            
            # Save to the configs directory
            new_path = self._config_path_manager.get_action_map_config_path("default_action_map.json")
            if new_path:
                # Ensure parent directory exists
                new_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(new_path, 'w') as f:
                    json.dump(default_map, f, indent=2)
                
                self._action_map = default_map
                self.map_changed.emit()
                self.logger.info(f"Created default action map at {new_path}")
        except Exception as e:
            self.logger.error(f"Failed to create default action map: {str(e)}")
    
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