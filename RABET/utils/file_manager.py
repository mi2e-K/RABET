# utils/file_manager.py
import os
import json
import csv
import logging
import shutil
from pathlib import Path

class FileManager:
    """
    Utility class for handling file operations throughout the application.
    Provides standardized methods for file operations with consistent error handling.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing FileManager")
        
        # Get application data directory
        self.app_data_dir = self._get_app_data_dir()
        
        # Ensure application directories exist
        self._ensure_app_directories()
    
    def _get_app_data_dir(self):
        """
        Get the application data directory based on the platform.
        
        Returns:
            pathlib.Path: Path to the application data directory
        """
        # Get the user's home directory
        home_dir = Path.home()
        
        # Determine platform-specific app data directory
        if os.name == 'nt':  # Windows
            app_data = home_dir / 'AppData' / 'Local' / 'BETA'
        elif os.name == 'posix':  # macOS / Linux
            # macOS
            if os.path.exists(home_dir / 'Library' / 'Application Support'):
                app_data = home_dir / 'Library' / 'Application Support' / 'BETA'
            # Linux
            else:
                app_data = home_dir / '.beta'
        else:
            # Fallback to a directory in the home folder
            app_data = home_dir / '.beta'
        
        return app_data
    
    def _ensure_app_directories(self):
        """Ensure that application directories exist."""
        # Create main app data directory
        self.app_data_dir.mkdir(exist_ok=True, parents=True)
        
        # Create subdirectories
        (self.app_data_dir / 'action_maps').mkdir(exist_ok=True)
        (self.app_data_dir / 'exports').mkdir(exist_ok=True)
        (self.app_data_dir / 'logs').mkdir(exist_ok=True)
        (self.app_data_dir / 'config').mkdir(exist_ok=True)
        
        self.logger.debug(f"Application directories initialized at {self.app_data_dir}")
    
    def get_default_action_map_path(self):
        """
        Get the path to the default action map file.
        
        Returns:
            pathlib.Path: Path to the default action map file
        """
        return self.app_data_dir / 'config' / 'default_action_map.json'
    
    def get_default_export_directory(self):
        """
        Get the default directory for exports.
        
        Returns:
            pathlib.Path: Path to the default export directory
        """
        return self.app_data_dir / 'exports'
    
    def get_app_log_directory(self):
        """
        Get the directory for application logs.
        
        Returns:
            pathlib.Path: Path to the log directory
        """
        return self.app_data_dir / 'logs'
    
    def ensure_file_exists(self, file_path):
        """
        Check if a file exists.
        
        Args:
            file_path (str or pathlib.Path): Path to the file
            
        Returns:
            bool: True if the file exists, False otherwise
        """
        file_path = Path(file_path)
        exists = file_path.exists() and file_path.is_file()
        
        if not exists:
            self.logger.warning(f"File not found: {file_path}")
        
        return exists
    
    def ensure_directory_exists(self, directory_path, create=False):
        """
        Check if a directory exists and optionally create it.
        
        Args:
            directory_path (str or pathlib.Path): Path to the directory
            create (bool): Whether to create the directory if it doesn't exist
            
        Returns:
            bool: True if the directory exists or was created, False otherwise
        """
        directory_path = Path(directory_path)
        
        if directory_path.exists() and directory_path.is_dir():
            return True
        
        if create:
            try:
                directory_path.mkdir(parents=True, exist_ok=True)
                self.logger.debug(f"Created directory: {directory_path}")
                return True
            except Exception as e:
                self.logger.error(f"Failed to create directory {directory_path}: {str(e)}")
                return False
        else:
            self.logger.warning(f"Directory not found: {directory_path}")
            return False
    
    def load_json(self, file_path):
        """
        Load data from a JSON file.
        
        Args:
            file_path (str or pathlib.Path): Path to the JSON file
            
        Returns:
            dict or None: Loaded JSON data or None if loading failed
        """
        file_path = Path(file_path)
        
        if not self.ensure_file_exists(file_path):
            return None
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            self.logger.debug(f"Loaded JSON from {file_path}")
            return data
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in {file_path}: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to load JSON from {file_path}: {str(e)}")
            return None
    
    def save_json(self, data, file_path):
        """
        Save data to a JSON file.
        
        Args:
            data (dict): Data to save
            file_path (str or pathlib.Path): Path to the JSON file
            
        Returns:
            bool: True if saving was successful, False otherwise
        """
        file_path = Path(file_path)
        
        # Ensure parent directory exists
        if not self.ensure_directory_exists(file_path.parent, create=True):
            return False
        
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            self.logger.debug(f"Saved JSON to {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save JSON to {file_path}: {str(e)}")
            return False
    
    def load_csv(self, file_path):
        """
        Load data from a CSV file.
        
        Args:
            file_path (str or pathlib.Path): Path to the CSV file
            
        Returns:
            list or None: List of dictionaries with CSV data or None if loading failed
        """
        file_path = Path(file_path)
        
        if not self.ensure_file_exists(file_path):
            return None
        
        try:
            data = []
            with open(file_path, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    data.append(row)
            self.logger.debug(f"Loaded CSV from {file_path}: {len(data)} rows")
            return data
        except csv.Error as e:
            self.logger.error(f"Invalid CSV in {file_path}: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to load CSV from {file_path}: {str(e)}")
            return None
    
    def save_csv(self, data, file_path, headers=None):
        """
        Save data to a CSV file.
        
        Args:
            data (list): List of dictionaries with data
            file_path (str or pathlib.Path): Path to the CSV file
            headers (list, optional): Column headers. If None, keys from the first dict are used.
            
        Returns:
            bool: True if saving was successful, False otherwise
        """
        file_path = Path(file_path)
        
        # Ensure parent directory exists
        if not self.ensure_directory_exists(file_path.parent, create=True):
            return False
        
        try:
            if not data:
                self.logger.warning(f"No data to save to {file_path}")
                return False
            
            # Determine headers if not provided
            if headers is None and data:
                headers = list(data[0].keys())
            
            with open(file_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(data)
            
            self.logger.debug(f"Saved CSV to {file_path}: {len(data)} rows")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save CSV to {file_path}: {str(e)}")
            return False
    
    def copy_file(self, src_path, dest_path, overwrite=False):
        """
        Copy a file from source to destination.
        
        Args:
            src_path (str or pathlib.Path): Source file path
            dest_path (str or pathlib.Path): Destination file path
            overwrite (bool): Whether to overwrite existing destination file
            
        Returns:
            bool: True if copy was successful, False otherwise
        """
        src_path = Path(src_path)
        dest_path = Path(dest_path)
        
        # Check source file
        if not self.ensure_file_exists(src_path):
            return False
        
        # Check if destination exists and overwrite is not allowed
        if dest_path.exists() and not overwrite:
            self.logger.warning(f"Destination file exists and overwrite not allowed: {dest_path}")
            return False
        
        # Ensure parent directory exists
        if not self.ensure_directory_exists(dest_path.parent, create=True):
            return False
        
        try:
            shutil.copy2(src_path, dest_path)
            self.logger.debug(f"Copied file from {src_path} to {dest_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to copy file from {src_path} to {dest_path}: {str(e)}")
            return False
    
    def delete_file(self, file_path):
        """
        Delete a file.
        
        Args:
            file_path (str or pathlib.Path): Path to the file
            
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        file_path = Path(file_path)
        
        if not self.ensure_file_exists(file_path):
            return False
        
        try:
            file_path.unlink()
            self.logger.debug(f"Deleted file: {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete file {file_path}: {str(e)}")
            return False