# utils/in_memory_log_handler.py
import logging
import time
from collections import deque

class InMemoryLogHandler(logging.Handler):
    """
    A logging handler that keeps logs in memory instead of writing to files.
    
    This handler is designed for distribution versions of the application where
    persistent log files are not needed, but logs still need to be viewable from
    the GUI for troubleshooting purposes.
    """
    
    def __init__(self, max_entries=10000):
        """
        Initialize the in-memory log handler.
        
        Args:
            max_entries (int): Maximum number of log entries to keep in memory
        """
        super().__init__()
        self.log_entries = deque(maxlen=max_entries)
        self.max_entries = max_entries
        
        # Create formatter
        self.formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    def emit(self, record):
        """
        Store the log record in memory.
        
        Args:
            record: Log record to store
        """
        try:
            # Format the record
            formatted_record = self.formatter.format(record)
            
            # Add to the deque
            self.log_entries.append(formatted_record)
        except Exception:
            self.handleError(record)
    
    def get_logs(self, max_lines=None, filter_text=None):
        """
        Get logs from memory.
        
        Args:
            max_lines (int, optional): Maximum number of lines to return
                                      If None, returns all lines
            filter_text (str, optional): Text to filter logs by
                                        If None, returns all logs
        
        Returns:
            list: List of log entries
        """
        # Apply filtering if needed
        if filter_text:
            filter_text = filter_text.lower()
            filtered_logs = [log for log in self.log_entries if filter_text in log.lower()]
        else:
            filtered_logs = list(self.log_entries)
        
        # Apply line limit if needed
        if max_lines and max_lines > 0:
            return filtered_logs[-max_lines:]
        
        return filtered_logs
    
    def get_logs_as_text(self, max_lines=None, filter_text=None):
        """
        Get logs as a single text string.
        
        Args:
            max_lines (int, optional): Maximum number of lines to return
            filter_text (str, optional): Text to filter logs by
        
        Returns:
            str: Log entries as a string, with each entry on a new line
        """
        logs = self.get_logs(max_lines, filter_text)
        return '\n'.join(logs)
    
    def clear(self):
        """Clear all log entries."""
        self.log_entries.clear()