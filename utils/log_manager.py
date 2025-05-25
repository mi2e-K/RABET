# utils/log_manager.py - Updated for in-memory logging
import os
import logging
import time
import datetime
import glob
from pathlib import Path
from utils.logger import get_in_memory_handler

class LogManager:
    """
    Manages application logs, providing log content for viewing within the application.
    For distribution builds, logs are kept in memory instead of writing to files.
    """
    
    def __init__(self):
        """Initialize the log manager."""
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing LogManager")
    
    def get_log_content(self, max_lines=1000, filter_text=None):
        """
        Get the content of the in-memory logs.
        
        Args:
            max_lines (int): Maximum number of lines to return
            filter_text (str, optional): Text to filter logs by
        
        Returns:
            str: Content of the logs (last max_lines)
        """
        in_memory_handler = get_in_memory_handler()
        if in_memory_handler:
            return in_memory_handler.get_logs_as_text(max_lines, filter_text)
        else:
            return "In-memory log handler not available."
    
    def get_log_files(self):
        """
        Get a list of available log sections.
        
        Since logs are now kept in memory, this returns a virtual structure
        representing time periods rather than actual files.
        
        Returns:
            list: List of dictionaries with log section information
        """
        # Create virtual log sections based on time periods
        current_time = datetime.datetime.now()
        
        # Create three time periods: Last hour, Last 24 hours, All logs
        result = [
            {
                'path': 'current',
                'name': 'Current Session',
                'size': 'In Memory',
                'date': current_time.strftime("%Y-%m-%d %H:%M:%S")
            },
            {
                'path': 'info',
                'name': 'Info+ Level Logs',
                'size': 'In Memory',
                'date': current_time.strftime("%Y-%m-%d %H:%M:%S")
            },
            {
                'path': 'debug',
                'name': 'Debug+ Level Logs',
                'size': 'In Memory',
                'date': current_time.strftime("%Y-%m-%d %H:%M:%S")
            }
        ]
        
        return result
    
    def clear_logs(self):
        """
        Clear in-memory logs.
        
        Returns:
            bool: True if logs were cleared successfully, False otherwise
        """
        try:
            in_memory_handler = get_in_memory_handler()
            if in_memory_handler:
                in_memory_handler.clear()
                self.logger.info("In-memory logs cleared")
                return True
            else:
                self.logger.warning("In-memory log handler not available")
                return False
        except Exception as e:
            self.logger.error(f"Error clearing logs: {str(e)}")
            return False
    
    def clean_up_old_logs(self):
        """
        No action needed for in-memory logs (compatibility method).
        
        Returns:
            tuple: (0, 0) - No files are deleted as none are created
        """
        # This method exists for backward compatibility
        # In-memory logs don't need cleanup as they're automatically managed
        return (0, 0)