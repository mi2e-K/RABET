# utils/directory_init.py
import os
import logging
from pathlib import Path
from utils.config_path_manager import ConfigPathManager

def ensure_app_directories():
    """
    Ensure that all required application directories exist.
    This is called during application startup.
    
    Returns:
        bool: True if all directories were created successfully, False otherwise
    """
    logger = logging.getLogger(__name__)
    logger.info("Ensuring application directories exist")
    
    try:
        # Required directories
        required_dirs = [
            "resources",
            "logs",
            "projects"
        ]
        
        # Create each directory if it doesn't exist
        for dir_name in required_dirs:
            dir_path = Path(dir_name)
            if not dir_path.exists():
                dir_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created missing directory: {dir_path}")
        
        # Initialize config path manager to create configs directory
        config_manager = ConfigPathManager()
        
        # Get configs directory (will create if it doesn't exist)
        config_dir = config_manager.get_config_directory()
        
        # Ensure default configurations exist
        if config_manager.ensure_default_configs():
            logger.info("Created or validated default configuration files")
        
        return True
    except Exception as e:
        logger.error(f"Error ensuring application directories: {str(e)}", exc_info=True)
        return False