# utils/config_path_manager.py
import os
import sys
import logging
import json
from pathlib import Path

class ConfigPathManager:
    """
    Centralized utility for managing configuration file paths.
    Provides consistent path resolution for all configuration files
    in both development and packaged environments.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing ConfigPathManager")
        
        # Store found paths to avoid repeated searches
        self._config_dir = None
        self._found_paths = {}
    
    def get_config_directory(self):
        """
        Get the base configuration directory.
        Searches in multiple locations and caches the result.
        
        Returns:
            Path: Path to the configs directory
        """
        # Return cached path if already found
        if self._config_dir is not None:
            return self._config_dir
        
        # Possible locations for the configs directory
        possible_paths = [
            Path("configs"),  # In current directory
            Path("..") / "configs",  # Up one level
            Path(__file__).parent.parent / "configs",  # Relative to script
        ]
        
        # For packaged app, also look relative to executable
        if getattr(sys, 'frozen', False):
            # We're running in a bundle
            bundle_dir = Path(sys.executable).parent
            self.logger.debug(f"Running as packaged app. Executable dir: {bundle_dir}")
            possible_paths.append(bundle_dir / "configs")
        
        # Try each possible path
        for path in possible_paths:
            if path.exists() and path.is_dir():
                self.logger.info(f"Found configs directory: {path}")
                self._config_dir = path
                return path
        
        # If not found, create in current directory
        default_path = Path("configs")
        self.logger.info(f"Configs directory not found, creating: {default_path}")
        os.makedirs(default_path, exist_ok=True)
        self._config_dir = default_path
        return default_path
    
    def get_config_file_path(self, file_name, create_dir=True):
        """
        Get the path to a specific configuration file.
        
        Args:
            file_name (str): Name of the configuration file
            create_dir (bool): Whether to create the config directory if it doesn't exist
            
        Returns:
            Path: Path to the configuration file
        """
        # Check cache first
        if file_name in self._found_paths:
            return self._found_paths[file_name]
        
        # Get config directory
        config_dir = self.get_config_directory() if create_dir else None
        
        if config_dir is None:
            # Find without creating
            for path in [
                Path("configs") / file_name,
                Path("..") / "configs" / file_name,
                Path(__file__).parent.parent / "configs" / file_name,
            ]:
                if path.exists():
                    self._found_paths[file_name] = path
                    return path
                    
            # If packaged and not found in standard locations
            if getattr(sys, 'frozen', False):
                bundle_path = Path(sys.executable).parent / "configs" / file_name
                if bundle_path.exists():
                    self._found_paths[file_name] = bundle_path
                    return bundle_path
                    
            return None
        
        # Construct the path to the config file
        config_path = config_dir / file_name
        
        # Cache and return the path
        self._found_paths[file_name] = config_path
        return config_path
    
    def get_action_map_config_path(self, file_name="default_action_map.json"):
        """
        Get the path to an action map configuration file.
        
        Args:
            file_name (str): Name of the action map file
            
        Returns:
            Path: Path to the action map configuration file
        """
        return self.get_config_file_path(file_name)
    
    def get_metrics_config_path(self, file_name="default_metrics.json"):
        """
        Get the path to a metrics configuration file.
        
        Args:
            file_name (str): Name of the metrics configuration file
            
        Returns:
            Path: Path to the metrics configuration file
        """
        return self.get_config_file_path(file_name)
    
    def get_color_map_config_path(self, file_name="custom_color_map.json"):
        """
        Get the path to a color map configuration file.
        
        Args:
            file_name (str): Name of the color map configuration file
            
        Returns:
            Path: Path to the color map configuration file
        """
        return self.get_config_file_path(file_name)
    
    def ensure_default_configs(self):
        """
        Ensure that default configuration files exist.
        Creates them if they don't exist.
        
        Returns:
            bool: True if all default configs exist or were created successfully
        """
        try:
            # Make sure the config directory exists
            config_dir = self.get_config_directory()
            
            # Create default action map if it doesn't exist
            action_map_path = config_dir / "default_action_map.json"
            if not action_map_path.exists():
                self.logger.info(f"Creating default action map at {action_map_path}")
                
                # Default key-to-behavior mappings
                default_mappings = {
                    "o": "Attack bites",
                    "j": "Sideways threats",
                    "p": "Tail rattles",
                    "q": "Chasing",
                    "a": "Social contact",
                    "e": "Self-grooming",
                    "t": "Locomotion",
                    "r": "Rearing"
                }
                
                # Create the file
                with open(action_map_path, 'w') as f:
                    json.dump(default_mappings, f, indent=2)
            
            # Create default metrics config if it doesn't exist
            metrics_path = config_dir / "default_metrics.json"
            if not metrics_path.exists():
                self.logger.info(f"Creating default metrics configuration at {metrics_path}")
                
                # Default metrics configuration - Keep these in sync with the defaults in analysis_config.py
                default_metrics = {
                    "latency_metrics": [
                        {
                            "name": "Attack Latency",
                            "behavior": "Attack bites",
                            "enabled": True
                        }
                    ],
                    "total_time_metrics": [
                        {
                            "name": "Total Aggression",
                            "behaviors": ["Attack bites", "Sideways threats", "Tail rattles", "Chasing"],
                            "enabled": True
                        },
                        {
                            "name": "Total Aggression(without tail-rattles)",
                            "behaviors": ["Attack bites", "Sideways threats", "Chasing"],
                            "enabled": True
                        }
                    ]
                }
                
                # Create the file
                with open(metrics_path, 'w') as f:
                    json.dump(default_metrics, f, indent=2)
            
            # Create default color map config if it doesn't exist
            color_map_path = config_dir / "custom_color_map.json"
            if not color_map_path.exists():
                self.logger.info(f"Creating default color map configuration at {color_map_path}")
                
                # Default color mapping for common behaviors
                default_colors = {
                    "Attack bites": "#FF4B00",
                    "Sideways threats": "#F6AA00", 
                    "Tail rattles": "#C9ACE6",
                    "Chasing": "#FF8082",
                    "Social contact": "#4DC4FF",
                    "Self-grooming": "#03AF7A",
                    "Locomotion": "#FFFFB2",
                    "Rearing": "#FFCABF"
                }
                
                # Create the file
                with open(color_map_path, 'w') as f:
                    json.dump(default_colors, f, indent=4)
            
            return True
        except Exception as e:
            self.logger.error(f"Error ensuring default configs: {str(e)}")
            return False