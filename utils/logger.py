# utils/logger.py - Updated for in-memory logging
import logging
import os
import sys
import time
from pathlib import Path
from utils.in_memory_log_handler import InMemoryLogHandler

# Global reference to in-memory log handler for access throughout the application
in_memory_handler = None

def setup_logger(use_file_logging=False):
    """
    Set up application logging with in-memory storage.
    
    Args:
        use_file_logging (bool): Whether to also log to files (for development)
    
    Returns:
        logging.Logger: Configured root logger
    """
    global in_memory_handler
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatter with detailed information
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create console handler (INFO level)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Create in-memory handler (DEBUG level)
    in_memory_handler = InMemoryLogHandler(max_entries=5000)
    in_memory_handler.setLevel(logging.DEBUG)
    in_memory_handler.setFormatter(formatter)
    root_logger.addHandler(in_memory_handler)
    
    # Optionally add file logging (for development mode)
    if use_file_logging:
        # Create logs directory if it doesn't exist
        logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        
        # Create file handler with enhanced rotation (DEBUG level)
        from logging.handlers import RotatingFileHandler
        log_filename = os.path.join(logs_dir, 'rabet.log')
        file_handler = RotatingFileHandler(
            log_filename,
            maxBytes=1 * 1024 * 1024,  # 1MB
            backupCount=3
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Add a startup message with application version and time
    logger = logging.getLogger(__name__)
    logger.info(f"===== Application started at {time.strftime('%Y-%m-%d %H:%M:%S')} =====")
    
    return root_logger

def get_in_memory_handler():
    """
    Get the global in-memory log handler.
    
    Returns:
        InMemoryLogHandler: The in-memory log handler
    """
    global in_memory_handler
    return in_memory_handler