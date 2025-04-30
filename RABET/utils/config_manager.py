# utils/config_manager.py
import os
import json
import logging
from pathlib import Path

class ConfigManager:
    """
    Manages application configuration and settings.
    Provides methods to load, save, and access application settings.
    """
    
    # Default configuration values
    DEFAULT_CONFIG = {
        "general": {
            "remember_last_directory": True,
            "auto_save_annotations": True,
            "auto_save_interval_min": 5,
            "recent_files_max": 10
        },
        "video": {
            "default_step_size_ms": 100,
            "default_playback_rate": 1.0,
            "default_volume": 80,
            "enable_frame_by_frame": True
        },
        "annotation": {
            "timeline_zoom_level": 100,
            "annotation_colors": {
                "default": "#7F7F7F",  # Gray
                "social": "#1F77B4",   # Blue
                "grooming": "#FF7F0E", # Orange
                "feeding": "#2CA02C",  # Green
                "locomotion": "#D62728" # Red
            },
            "show_duration_labels": True,
            "show_behavior_labels": True
        },
        "analysis": {
            "default_export_format": "csv",
            "include_statistics": True,
            "include_raw_data": True
        },
        "ui": {
            "theme": "system",
            "font_size": 12,
            "show_toolbar": True,
            "show_statusbar": True
        },
        "directories": {
            "last_video_directory": "",
            "last_annotation_directory": "",
            "last_action_map_directory": ""
        },
        "recent_files": {
            "videos": [],
            "action_maps": [],
            "annotations": []
        }
    }
    
    def __init__(self, file_manager):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing ConfigManager")
        
        self._file_manager = file_manager
        self._config = self.DEFAULT_CONFIG.copy()
        
        # Path to the config file
        self._config_file = self._file_manager.app_data_dir / 'config' / 'settings.json'
        
        # Load config on initialization
        self.load_config()
    
    def load_config(self):
        """
        Load configuration from file.
        If the file doesn't exist or is invalid, default values are used.
        
        Returns:
            bool: True if loading was successful, False otherwise
        """
        self.logger.debug(f"Loading config from {self._config_file}")
        
        # Check if config file exists
        if not self._config_file.exists():
            self.logger.info("Config file not found, using defaults")
            return self.save_config()  # Create default config file
        
        try:
            # Load and merge with defaults
            loaded_config = self._file_manager.load_json(self._config_file)
            
            if loaded_config:
                # Deep merge with defaults to ensure all keys exist
                self._deep_merge(self._config, loaded_config)
                self.logger.info("Config loaded successfully")
                return True
            else:
                self.logger.warning("Invalid config file, using defaults")
                return self.save_config()  # Re-create config file with defaults
        except Exception as e:
            self.logger.error(f"Error loading config: {str(e)}")
            return False
    
    def save_config(self):
        """
        Save current configuration to file.
        
        Returns:
            bool: True if saving was successful, False otherwise
        """
        self.logger.debug(f"Saving config to {self._config_file}")
        
        return self._file_manager.save_json(self._config, self._config_file)
    
    def get(self, section, key=None):
        """
        Get a configuration value or section.
        
        Args:
            section (str): Configuration section
            key (str, optional): Configuration key within section.
                                 If None, entire section is returned.
        
        Returns:
            any: Configuration value or section, or None if not found
        """
        if section not in self._config:
            self.logger.warning(f"Config section not found: {section}")
            return None
        
        if key is None:
            return self._config[section]
        
        if key not in self._config[section]:
            self.logger.warning(f"Config key not found: {section}.{key}")
            return None
        
        return self._config[section][key]
    
    def set(self, section, key, value):
        """
        Set a configuration value.
        
        Args:
            section (str): Configuration section
            key (str): Configuration key
            value (any): Value to set
        
        Returns:
            bool: True if the value was set successfully, False otherwise
        """
        if section not in self._config:
            self.logger.warning(f"Config section not found: {section}")
            return False
        
        try:
            self._config[section][key] = value
            return True
        except Exception as e:
            self.logger.error(f"Error setting config value: {str(e)}")
            return False
    
    def update_section(self, section, values):
        """
        Update multiple values in a section.
        
        Args:
            section (str): Configuration section
            values (dict): Dictionary of key-value pairs to update
        
        Returns:
            bool: True if the section was updated successfully, False otherwise
        """
        if section not in self._config:
            self.logger.warning(f"Config section not found: {section}")
            return False
        
        try:
            self._config[section].update(values)
            return True
        except Exception as e:
            self.logger.error(f"Error updating config section: {str(e)}")
            return False
    
    def add_recent_file(self, file_type, file_path):
        """
        Add a file to the recent files list.
        
        Args:
            file_type (str): Type of file (videos, action_maps, annotations)
            file_path (str): Path to the file
        
        Returns:
            bool: True if the file was added successfully, False otherwise
        """
        if file_type not in self._config["recent_files"]:
            self.logger.warning(f"Invalid recent file type: {file_type}")
            return False
        
        try:
            # Convert to string in case it's a Path object
            file_path = str(file_path)
            
            # Get the list and maximum size
            recent_files = self._config["recent_files"][file_type]
            max_recent = self._config["general"]["recent_files_max"]
            
            # Remove if already exists
            if file_path in recent_files:
                recent_files.remove(file_path)
            
            # Add to the beginning
            recent_files.insert(0, file_path)
            
            # Trim to maximum size
            if len(recent_files) > max_recent:
                recent_files = recent_files[:max_recent]
            
            # Update the list
            self._config["recent_files"][file_type] = recent_files
            
            return True
        except Exception as e:
            self.logger.error(f"Error adding recent file: {str(e)}")
            return False
    
    def get_recent_files(self, file_type):
        """
        Get the list of recent files.
        
        Args:
            file_type (str): Type of file (videos, action_maps, annotations)
        
        Returns:
            list: List of recent file paths, or empty list if not found
        """
        if file_type not in self._config["recent_files"]:
            self.logger.warning(f"Invalid recent file type: {file_type}")
            return []
        
        return self._config["recent_files"][file_type]
    
    def update_last_directory(self, directory_type, directory_path):
        """
        Update the last used directory.
        
        Args:
            directory_type (str): Type of directory (video, annotation, action_map)
            directory_path (str): Path to the directory
        
        Returns:
            bool: True if the directory was updated successfully, False otherwise
        """
        key = f"last_{directory_type}_directory"
        
        if key not in self._config["directories"]:
            self.logger.warning(f"Invalid directory type: {directory_type}")
            return False
        
        try:
            # Convert to string in case it's a Path object
            directory_path = str(directory_path)
            
            # Update the directory
            self._config["directories"][key] = directory_path
            
            return True
        except Exception as e:
            self.logger.error(f"Error updating last directory: {str(e)}")
            return False
    
    def get_last_directory(self, directory_type):
        """
        Get the last used directory.
        
        Args:
            directory_type (str): Type of directory (video, annotation, action_map)
        
        Returns:
            str: Path to the last used directory, or empty string if not found
        """
        key = f"last_{directory_type}_directory"
        
        if key not in self._config["directories"]:
            self.logger.warning(f"Invalid directory type: {directory_type}")
            return ""
        
        return self._config["directories"][key]
    
    def reset_to_defaults(self):
        """
        Reset configuration to default values.
        
        Returns:
            bool: True if reset was successful, False otherwise
        """
        self._config = self.DEFAULT_CONFIG.copy()
        return self.save_config()
    
    def _deep_merge(self, target, source):
        """
        Deep merge two dictionaries.
        Values from source override values in target.
        
        Args:
            target (dict): Target dictionary to merge into
            source (dict): Source dictionary to merge from
        """
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_merge(target[key], value)
            else:
                target[key] = value