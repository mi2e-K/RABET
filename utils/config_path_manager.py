# utils/config_path_manager.py
import os
import sys
import logging
import json
import platform
from pathlib import Path

_app_data_dir = None

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
        self._user_config_dir = None
        self._found_paths = {}
        
        # Initialize user config directory for runtime files
        self._init_user_config_dir()
    
    def _init_user_config_dir(self):
        """Initialize the user configuration directory for runtime-created files."""
        if platform.system() == 'Darwin':  # macOS
            # Use ~/Library/Application Support/RABET for user data
            app_support = Path.home() / "Library" / "Application Support" / "RABET"
            self._user_config_dir = app_support / "configs"
        elif platform.system() == 'Windows':
            # Use %APPDATA%/RABET for user data
            app_data = os.environ.get('APPDATA', Path.home() / "AppData" / "Roaming")
            self._user_config_dir = Path(app_data) / "RABET" / "configs"
        else:  # Linux and others
            # Use ~/.config/RABET for user data
            config_home = os.environ.get('XDG_CONFIG_HOME', Path.home() / ".config")
            self._user_config_dir = Path(config_home) / "RABET" / "configs"
        
        # Create user config directory if it doesn't exist
        try:
            self._user_config_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"User config directory: {self._user_config_dir}")
        except Exception as e:
            self.logger.error(f"Failed to create user config directory: {e}")
            # Fallback to temp directory
            import tempfile
            self._user_config_dir = Path(tempfile.gettempdir()) / "RABET" / "configs"
            self._user_config_dir.mkdir(parents=True, exist_ok=True)
            self.logger.warning(f"Using fallback config directory: {self._user_config_dir}")
    
    def get_config_directory(self):
        """
        Get the base configuration directory for read-only default configs.
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
        
        # For packaged app, also look in various locations
        if getattr(sys, 'frozen', False):
            # We're running in a bundle
            if platform.system() == 'Darwin':
                # macOS app bundle structure
                bundle_dir = Path(sys.executable).parent
                # Check multiple possible locations in the app bundle
                possible_paths.extend([
                    bundle_dir / "configs",
                    bundle_dir.parent / "Resources" / "configs",
                    bundle_dir.parent.parent / "Resources" / "configs",
                ])
            else:
                # Windows/Linux packaged app
                bundle_dir = Path(sys.executable).parent
                possible_paths.append(bundle_dir / "configs")
        
        # Try each possible path
        for path in possible_paths:
            if path.exists() and path.is_dir():
                self.logger.info(f"Found configs directory: {path}")
                self._config_dir = path
                return path
        
        # If not found in packaged locations, check user directory
        # This handles the case where defaults might have been copied there
        user_default_path = self._user_config_dir
        if user_default_path.exists():
            self.logger.info(f"Using user configs directory: {user_default_path}")
            self._config_dir = user_default_path
            return user_default_path
        
        # If still not found, create in user directory
        self.logger.info(f"Configs directory not found, using user directory: {self._user_config_dir}")
        self._config_dir = self._user_config_dir
        return self._user_config_dir
    
    def get_user_config_file_path(self, file_name):
        """
        Get the path for a user-specific configuration file (read/write).
        These files are stored in the user's application data directory.
        
        Args:
            file_name (str): Name of the configuration file
            
        Returns:
            Path: Path to the user configuration file
        """
        return self._user_config_dir / file_name
    
    def get_config_file_path(self, file_name, create_dir=True):
        """
        Get the path to a specific configuration file.
        For user-modifiable files (like user_action_map.json), uses user directory.
        For default files, searches in standard locations.
        
        Args:
            file_name (str): Name of the configuration file
            create_dir (bool): Whether to create the config directory if it doesn't exist
            
        Returns:
            Path: Path to the configuration file
        """
        # Special handling for user-specific files
        if file_name == "user_action_map.json":
            return self.get_user_config_file_path(file_name)
        
        # Check cache first
        if file_name in self._found_paths:
            return self._found_paths[file_name]
        
        # Get config directory for default files
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
                if platform.system() == 'Darwin':
                    bundle_dir = Path(sys.executable).parent
                    # Check multiple locations in macOS bundle
                    for base in [bundle_dir, bundle_dir.parent / "Resources", 
                               bundle_dir.parent.parent / "Resources"]:
                        bundle_path = base / "configs" / file_name
                        if bundle_path.exists():
                            self._found_paths[file_name] = bundle_path
                            return bundle_path
                else:
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
    
    def copy_defaults_to_user_dir(self):
        """
        Copy default configuration files from the app bundle to user directory.
        This is useful for first-time setup on macOS where the app bundle is read-only.
        """
        if not getattr(sys, 'frozen', False):
            # Not in a packaged app, no need to copy
            return
        
        # List of default files to copy
        default_files = [
            "default_action_map.json",
            "default_metrics.json",
            "custom_color_map.json",
            "custom_default_colormap.json"
        ]
        
        for file_name in default_files:
            # Skip user_action_map.json as it's created at runtime
            if file_name == "user_action_map.json":
                continue
                
            # Check if file already exists in user directory
            user_path = self._user_config_dir / file_name
            if user_path.exists():
                continue
            
            # Find the default file in the bundle
            default_path = None
            
            # Search in possible bundle locations
            if platform.system() == 'Darwin':
                bundle_dir = Path(sys.executable).parent
                search_paths = [
                    bundle_dir / "configs" / file_name,
                    bundle_dir.parent / "Resources" / "configs" / file_name,
                    bundle_dir.parent.parent / "Resources" / "configs" / file_name,
                ]
            else:
                search_paths = [
                    Path(sys.executable).parent / "configs" / file_name,
                ]
            
            for path in search_paths:
                if path.exists():
                    default_path = path
                    break
            
            if default_path:
                try:
                    # Copy the file to user directory
                    import shutil
                    shutil.copy2(default_path, user_path)
                    self.logger.info(f"Copied {file_name} to user directory")
                except Exception as e:
                    self.logger.error(f"Failed to copy {file_name}: {e}")
    
    def ensure_default_configs(self):
        """
        Ensure that default configuration files exist.
        Creates them if they don't exist.
        
        Returns:
            bool: True if all default configs exist or were created successfully
        """
        try:
            # For packaged apps, copy defaults from bundle to user directory
            if getattr(sys, 'frozen', False):
                self.copy_defaults_to_user_dir()
            
            # Make sure the config directory exists
            config_dir = self.get_config_directory()
            
            # All defaults flow from ``defaults.py`` so a future tweak only
            # needs to land in one place.
            from defaults import (
                default_action_map,
                default_latency_metrics,
                default_total_time_metrics,
                default_behavior_colors,
            )

            # Create default action map if it doesn't exist
            action_map_path = config_dir / "default_action_map.json"
            if not action_map_path.exists():
                self.logger.info(f"Creating default action map at {action_map_path}")
                with open(action_map_path, 'w') as f:
                    json.dump(default_action_map(), f, indent=2)

            # Create default metrics config if it doesn't exist
            metrics_path = config_dir / "default_metrics.json"
            if not metrics_path.exists():
                self.logger.info(f"Creating default metrics configuration at {metrics_path}")
                default_metrics = {
                    "latency_metrics": default_latency_metrics(),
                    "total_time_metrics": default_total_time_metrics(),
                }
                with open(metrics_path, 'w') as f:
                    json.dump(default_metrics, f, indent=2)

            # Create default color map config if it doesn't exist
            color_map_path = config_dir / "custom_color_map.json"
            if not color_map_path.exists():
                self.logger.info(f"Creating default color map configuration at {color_map_path}")
                with open(color_map_path, 'w') as f:
                    json.dump(default_behavior_colors(), f, indent=4)

            return True
        except Exception as e:
            self.logger.error(f"Error ensuring default configs: {str(e)}")
            return False