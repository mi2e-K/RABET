# utils/directory_init.py
import os
import json
import logging
from pathlib import Path

def ensure_app_directories():
    """
    Ensure that all required application directories exist and contain 
    necessary default files. This is critical for both runtime and build processes.
    
    Returns:
        bool: True if all directories were created/verified successfully
    """
    logger = logging.getLogger(__name__)
    
    try:
        # List of required directories
        required_dirs = [
            "action_maps",
            "resources",
            "logs"
        ]
        
        # Create each directory if it doesn't exist
        for dir_name in required_dirs:
            if not os.path.exists(dir_name):
                os.makedirs(dir_name)
                logger.info(f"Created missing directory: {dir_name}")
        
        # Create default action map if none exists
        default_action_map_path = os.path.join("action_maps", "default.json")
        if not os.path.exists(default_action_map_path):
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
            with open(default_action_map_path, 'w') as f:
                json.dump(default_mappings, f, indent=2)
            
            logger.info(f"Created default action map: {default_action_map_path}")
        
        # Add other required files/directories initialization here if needed
        
        return True
    except Exception as e:
        logger.error(f"Failed to ensure app directories: {str(e)}")
        return False