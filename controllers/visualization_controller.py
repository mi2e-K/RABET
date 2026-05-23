# controllers/visualization_controller.py - Completely independent controller for visualization features
import logging
import os
import json
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QMessageBox
from utils.annotation_csv_parser import load_event_dataframe

class VisualizationController(QObject):
    """
    Controller for visualization operations.
    Completely independent from the analysis model/controller.
    """
    
    def __init__(self, visualization_view, config_path_manager=None):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing VisualizationController")
        
        # Store references
        self._view = visualization_view
        self._config_path_manager = config_path_manager
        
        # Local storage for visualization data
        self._visualization_data = {}
        
        # Custom color map storage
        self._custom_color_map = {}
        self._available_custom_colormaps = {}
        
        # Initialize config path manager if not provided
        if not self._config_path_manager:
            self.logger.info("No config path manager provided, creating local default")
            try:
                from utils.config_path_manager import ConfigPathManager
                self._config_path_manager = ConfigPathManager()
                self.logger.info("Created fallback config path manager")
            except Exception as e:
                self.logger.error(f"Failed to create config path manager: {e}")
                self._config_path_manager = None
        
        # Initialize custom colormaps if config manager is available
        if self._config_path_manager:
            self._initialize_custom_colormaps()
        
        # Connect signals
        self._connect_signals()
    
    def _initialize_custom_colormaps(self):
        """Initialize custom colormaps from config directory."""
        try:
            self.logger.info("Initializing custom colormaps...")
            
            # Ensure default configs exist
            self._config_path_manager.ensure_default_configs()
            
            # Discover custom colormaps
            self._discover_custom_colormaps()
            
        except Exception as e:
            self.logger.error(f"Error initializing custom colormaps: {e}")
    
    def _connect_signals(self):
        """Connect signals from view."""
        if self._view:
            self._view.files_dropped.connect(self.on_files_dropped)
            # 1.3.3+: the Clear button now tells us to drop the cached
            # data. Without this hook a subsequent re-drop of the same
            # CSVs revives the previously-cleared session.
            if hasattr(self._view, "clear_data_requested"):
                self._view.clear_data_requested.connect(
                    self.on_clear_data_requested
                )

    @Slot()
    def on_clear_data_requested(self):
        """Drop the in-memory cache when the user clicks Clear.

        Intentionally does NOT touch the view (the view already cleared
        itself before emitting this signal). Calling
        ``self._view.set_data({})`` here would re-trigger the view's
        clear path and risk a redundant re-render.
        """
        if not self._visualization_data:
            return
        n = len(self._visualization_data)
        self._visualization_data = {}
        self.logger.info(
            f"Cleared {n} cached file(s) from the visualization controller"
        )
    
    def _discover_custom_colormaps(self):
        """
        Discover custom color map files in the configs directory.
        Only recognizes JSON files with 'custom_' in the filename.
        """
        try:
            if not self._config_path_manager:
                self.logger.warning("No config path manager available")
                return
            
            # Get configs directory
            config_dir = self._config_path_manager.get_config_directory()
            self.logger.info(f"Searching for custom colormaps in: {config_dir}")
            
            if not config_dir.exists():
                self.logger.warning(f"Config directory does not exist: {config_dir}")
                return
            
            # Find files matching pattern
            pattern = "*custom_*.json"
            matching_files = list(config_dir.glob(pattern))
            self.logger.info(f"Found {len(matching_files)} files matching '{pattern}'")
            
            available_colormaps = {}
            
            for file_path in matching_files:
                self.logger.debug(f"Processing file: {file_path.name}")
                
                try:
                    # Load JSON file
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Validate colormap data
                    if self._validate_colormap_data(data):
                        colormap_name = file_path.stem
                        available_colormaps[colormap_name] = data
                        self.logger.info(f"Loaded custom colormap: {colormap_name}")
                    else:
                        self.logger.warning(f"Invalid colormap data in: {file_path.name}")
                
                except json.JSONDecodeError as e:
                    self.logger.warning(f"JSON error in {file_path.name}: {e}")
                except Exception as e:
                    self.logger.warning(f"Error loading {file_path.name}: {e}")
            
            # Store discovered colormaps
            self._available_custom_colormaps = available_colormaps
            self.logger.info(f"Discovered {len(available_colormaps)} custom colormaps")
            
            # Update view if colormaps were found
            if available_colormaps and self._view:
                self._view.add_custom_colormaps_to_dropdown(available_colormaps)
            
        except Exception as e:
            self.logger.error(f"Error discovering custom colormaps: {e}")
    
    def _validate_colormap_data(self, data):
        """
        Validate that data represents a valid colormap.
        
        Args:
            data: Data to validate
            
        Returns:
            bool: True if valid colormap data
        """
        if not isinstance(data, dict) or len(data) == 0:
            return False
        
        for key, value in data.items():
            if not isinstance(key, str) or not isinstance(value, str):
                return False
            if not value.startswith('#') or len(value) != 7:
                return False
            
            # Try to validate hex color
            try:
                int(value[1:], 16)
            except ValueError:
                return False
        
        return True
    
    @Slot(list)
    def on_files_dropped(self, file_paths):
        """
        Handle files dropped directly onto the visualization view.
        
        Args:
            file_paths (list): List of dropped file paths
        """
        self.logger.info(f"Processing {len(file_paths)} dropped files")
        
        # Filter for CSV files
        csv_files = [path for path in file_paths if path.lower().endswith('.csv')]
        
        if not csv_files:
            QMessageBox.warning(
                self._view,
                "Invalid Files",
                "Please drop only CSV annotation files."
            )
            return
        
        # Load files
        self._load_csv_files(csv_files)
    
    def _load_csv_files(self, file_paths):
        """
        Load CSV files for visualization.
        
        Args:
            file_paths (list): List of CSV file paths
        """
        loaded_data = {}
        
        for file_path in file_paths:
            try:
                df = self._load_single_csv(file_path)
                if df is not None:
                    loaded_data[file_path] = df
                    self.logger.info(f"Loaded file: {file_path}")
                else:
                    self.logger.warning(f"Failed to load file: {file_path}")
            
            except Exception as e:
                self.logger.error(f"Error loading {file_path}: {e}")
                QMessageBox.warning(
                    self._view,
                    "File Loading Error",
                    f"Error loading {os.path.basename(file_path)}: {str(e)}"
                )
        
        # Update visualization data
        if loaded_data:
            self._visualization_data.update(loaded_data)
            self._view.set_data(self._visualization_data)
            self.logger.info(f"Updated visualization with {len(loaded_data)} files")
    
    def _load_single_csv(self, file_path):
        """
        Load a single CSV file for visualization.
        
        Args:
            file_path (str): Path to CSV file
            
        Returns:
            pd.DataFrame or None: Loaded data or None if failed
        """
        try:
            return load_event_dataframe(file_path, logger=self.logger)
        
        except Exception as e:
            self.logger.error(f"Error loading CSV {file_path}: {e}")
            return None
    
    def load_files(self, file_paths):
        """
        Load files for visualization (external API).
        
        Args:
            file_paths (list): List of file paths
        """
        self.on_files_dropped(file_paths)
    
    def import_from_analysis_model(self, analysis_model):
        """
        Import data from analysis model.
        
        Args:
            analysis_model: Analysis model to import from
        """
        self.logger.info("Importing data from analysis model")
        
        try:
            raw_data = {}
            if hasattr(analysis_model, '_raw_data'):
                for file_path, df in analysis_model._raw_data.items():
                    raw_data[file_path] = df.copy()
            
            if raw_data:
                self._visualization_data.update(raw_data)
                self._view.set_data(self._visualization_data)
                self.logger.info(f"Imported {len(raw_data)} files from analysis model")
        
        except Exception as e:
            self.logger.error(f"Error importing from analysis model: {e}")
    
    def refresh_custom_colormaps(self):
        """Manually refresh custom colormaps from config directory."""
        self.logger.info("Refreshing custom colormaps")
        self._discover_custom_colormaps()
    
    def save_custom_colormap(self, colormap_name, colormap_data, file_path=None):
        """
        Save a custom colormap to file.
        
        Args:
            colormap_name (str): Name of the colormap
            colormap_data (dict): Colormap data
            file_path (str, optional): File path to save to
            
        Returns:
            bool: True if successful
        """
        try:
            if not file_path and self._config_path_manager:
                config_dir = self._config_path_manager.get_config_directory()
                file_path = config_dir / f"custom_{colormap_name}.json"
            
            if not file_path:
                self.logger.error("No file path specified for saving colormap")
                return False
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Save colormap
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(colormap_data, f, indent=4)
            
            self.logger.info(f"Saved custom colormap to: {file_path}")
            
            # Refresh colormaps
            self._discover_custom_colormaps()
            
            return True
        
        except Exception as e:
            self.logger.error(f"Error saving custom colormap: {e}")
            return False
    
    def clear_data(self):
        """Clear all visualization data."""
        self._visualization_data = {}
        if self._view:
            self._view.set_data({})
        self.logger.info("Visualization data cleared")
    
    def get_debug_info(self):
        """
        Get debug information about the visualization controller.
        
        Returns:
            dict: Debug information
        """
        info = {
            "has_config_manager": self._config_path_manager is not None,
            "config_directory": None,
            "discovered_colormaps": list(self._available_custom_colormaps.keys()),
            "loaded_files": len(self._visualization_data),
            "view_connected": self._view is not None
        }
        
        if self._config_path_manager:
            try:
                config_dir = self._config_path_manager.get_config_directory()
                info["config_directory"] = {
                    "path": str(config_dir),
                    "exists": config_dir.exists(),
                    "files": [f.name for f in config_dir.glob("*custom_*.json")] if config_dir.exists() else []
                }
            except Exception as e:
                info["config_directory"] = {"error": str(e)}
        
        return info
