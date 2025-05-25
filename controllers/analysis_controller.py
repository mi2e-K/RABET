# controllers/analysis_controller.py - Enhanced with file management, metrics configuration, and export options
import logging
import os
import sys
import time
from PySide6.QtCore import QObject, Slot, QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox
from utils.auto_close_message import AutoCloseMessageBox
from views.metrics_config_dialog import MetricsConfigDialog
from utils.config_path_manager import ConfigPathManager  # Import the new class

class AnalysisController(QObject):
    """
    Controller for CSV analysis operations with enhanced file management,
    customizable metrics, and interval-based analysis options.
    """
    
    def __init__(self, analysis_model, analysis_view):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing AnalysisController")
        
        self._model = analysis_model
        self._view = analysis_view
        
        # Initialize config path manager
        self._config_path_manager = ConfigPathManager()
        
        # Connect model signals
        self._connect_model_signals()
        
        # Connect view signals
        self._connect_view_signals()
        
        # Track current results for export
        self._current_results = {}
        
        # FIX: Track whether we should auto-export (only for new file loads, not settings changes)
        self._should_auto_export = False
        
        # NEW: Track which view initiated file loading
        self._source_view = None
        
        # Initialize interval analysis from view settings
        self._sync_interval_settings_from_view()
    
    def _connect_model_signals(self):
        """Connect signals from the model."""
        self._model.data_loaded.connect(self.on_data_loaded)
        self._model.analysis_complete.connect(self.on_analysis_complete)
        self._model.error_occurred.connect(self.on_error)
    
    def _connect_view_signals(self):
        """Connect signals from the view."""
        self._view.files_dropped.connect(self.on_files_dropped)
        self._view.load_files_requested.connect(self.on_load_files_requested)
        self._view.remove_files_requested.connect(self.on_remove_files_requested)
        self._view.clear_files_requested.connect(self.on_clear_files_requested)
        self._view.export_table_requested.connect(self.on_export_table_requested)
        self._view.interval_settings_changed.connect(self.on_interval_settings_changed)
        self._view.configure_metrics_requested.connect(self.on_configure_metrics_requested)
        self._view.export_metrics_config_requested.connect(self.export_metrics_config)
        self._view.import_metrics_config_requested.connect(self.import_metrics_config)
    
    def _sync_interval_settings_from_view(self):
        """Get interval settings from view and apply to model."""
        enabled, seconds = self._view.get_interval_settings()
        self._model.set_interval_analysis(enabled, seconds)
        self.logger.debug(f"Initialized interval analysis: enabled={enabled}, seconds={seconds}")
    
    @Slot()
    def on_configure_metrics_requested(self):
        """Show the metrics configuration dialog."""
        # Get the current configuration from the model
        config = self._model.get_metrics_config()
        
        # Get the list of behaviors from the model
        behaviors = self._model.get_behaviors_list()
        if not behaviors:
            # If no behaviors available yet, use defaults
            behaviors = [
                "Attack bites", "Sideways threats", "Tail rattles", "Chasing",
                "Social contact", "Self-grooming", "Locomotion", "Rearing"
            ]
        
        # Create and show the dialog
        dialog = MetricsConfigDialog(self._view, behaviors, config)
        if dialog.exec():
            # Get the updated configurations
            latency_metrics = dialog.get_latency_metrics()
            total_time_metrics = dialog.get_total_time_metrics()
            
            # Update the config object
            config._latency_metrics = latency_metrics
            config._total_time_metrics = total_time_metrics
            
            # Apply to the model
            self._model.set_metrics_config(config)
            
            # Log the update
            self.logger.info(f"Updated metrics configuration: {len(latency_metrics)} latency metrics, {len(total_time_metrics)} total time metrics")
            
            # Show user feedback
            metrics_summary = f"{len(latency_metrics)} latency metrics and {len(total_time_metrics)} total time metrics configured"
            self._view.set_status_message(f"Metrics configuration updated: {metrics_summary}")
            
            # If we have data loaded, trigger reanalysis
            if self._current_results:
                # FIX: Don't show progress bar for metrics changes - they're usually quick
                self._view.set_status_message(f"Reanalyzing data with updated metrics configuration...")
                # Don't auto-export when reanalyzing due to metrics changes
                self._should_auto_export = False
    
    @Slot()
    def export_metrics_config(self):
        """Export the current metrics configuration to a JSON file."""
        # Get the current configuration from the model
        config = self._model.get_metrics_config()
        
        # Get configs directory from the config path manager
        default_dir = str(self._config_path_manager.get_config_directory())
        
        # Show file dialog to get save path
        file_path, _ = QFileDialog.getSaveFileName(
            self._view,
            "Export Metrics Configuration",
            os.path.join(default_dir, "metrics_config.json"),
            "JSON Files (*.json)"
        )
        
        if not file_path:
            return
        
        # Add .json extension if not present
        if not file_path.lower().endswith('.json'):
            file_path += '.json'
        
        # Save configuration to file
        if config.save_to_json(file_path):
            self._view.set_status_message(f"Metrics configuration exported to {file_path}")
            
            # Show a success message
            QMessageBox.information(
                self._view,
                "Export Successful",
                f"Metrics configuration exported to:\n{file_path}"
            )
        else:
            self._view.set_status_message(f"Failed to export metrics configuration")
            
            # Show an error message
            QMessageBox.warning(
                self._view,
                "Export Failed",
                f"Failed to export metrics configuration to:\n{file_path}"
            )
    
    @Slot()
    def import_metrics_config(self):
        """Import metrics configuration from a JSON file."""
        # Get configs directory from the config path manager
        default_dir = str(self._config_path_manager.get_config_directory())
        
        # Show file dialog to get load path
        file_path, _ = QFileDialog.getOpenFileName(
            self._view,
            "Import Metrics Configuration",
            default_dir,
            "JSON Files (*.json)"
        )
        
        if not file_path:
            return
        
        # Get the current configuration from the model
        config = self._model.get_metrics_config()
        
        # Load configuration from file
        if config.load_from_json(file_path):
            # Apply to the model
            self._model.set_metrics_config(config)
            
            self._view.set_status_message(f"Metrics configuration imported from {file_path}")
            
            # Show a success message
            QMessageBox.information(
                self._view,
                "Import Successful",
                f"Metrics configuration imported from:\n{file_path}"
            )
            
            # If we have data loaded, trigger reanalysis
            if self._current_results:
                # FIX: Don't show progress bar for imported metrics - they're usually quick
                self._view.set_status_message(f"Reanalyzing data with imported metrics configuration...")
                # Don't auto-export when reanalyzing due to imported metrics
                self._should_auto_export = False
        else:
            self._view.set_status_message(f"Failed to import metrics configuration")
            
            # Show an error message
            QMessageBox.warning(
                self._view,
                "Import Failed",
                f"Failed to import metrics configuration from:\n{file_path}"
            )
            
    def _get_configs_directory(self):
        """
        Get the directory for metrics configurations.
        Attempts to find or create a 'configs' directory.
        
        Returns:
            str: Path to the configs directory
        """
        # Look in common locations
        possible_paths = [
            "configs",  # Current directory
            os.path.join("..", "configs"),  # Parent directory
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "configs")  # Relative to script
        ]
        
        # For packaged app, also check relative to executable
        if getattr(sys, 'frozen', False):
            # We're running in a bundle
            bundle_dir = os.path.dirname(sys.executable)
            possible_paths.append(os.path.join(bundle_dir, "configs"))
        
        # Find first existing configs directory
        for path in possible_paths:
            if os.path.exists(path) and os.path.isdir(path):
                return os.path.abspath(path)
        
        # If not found, create one in current directory
        os.makedirs("configs", exist_ok=True)
        return os.path.abspath("configs")
    
    @Slot(bool, int)
    def on_interval_settings_changed(self, enabled, seconds):
        """
        Handle interval analysis settings changes from the view.
        
        Args:
            enabled (bool): Whether interval analysis is enabled
            seconds (int): Interval size in seconds
        """
        self.logger.info(f"Interval settings changed: enabled={enabled}, seconds={seconds}")
        
        # Update model with new settings
        self._model.set_interval_analysis(enabled, seconds)
        
        # FIX: If we have data loaded, trigger reanalysis but don't show progress bar
        # Settings changes are usually quick, and a stuck progress bar is worse than no progress bar
        if self._current_results:
            self._view.set_status_message(f"Reanalyzing data with {'interval' if enabled else 'standard'} settings...")
            # Don't auto-export when reanalyzing due to settings changes
            self._should_auto_export = False
            # Note: The reanalysis is triggered automatically by set_interval_analysis
    
    @Slot(list)
    def on_data_loaded(self, file_paths):
        """
        Handle data loaded event.
        
        Args:
            file_paths (list): List of loaded file paths
        """
        # Update view with loaded files
        self._view.update_file_list(file_paths)
        self._view.show_progress(True, 50)
        
        self.logger.info(f"Loaded {len(file_paths)} file(s)")
        self._view.set_status_message(f"Loaded {len(file_paths)} file(s)")
        
        # FIX: Enable auto-export when files are loaded (not for settings changes)
        self._should_auto_export = True
        
        # IMPORTANT FIX: Only switch views if the files were explicitly loaded from the analysis view
        if self._source_view == "analysis":
            # Switch to analysis view if needed
            from PySide6.QtWidgets import QApplication
            main_window = None
            for widget in QApplication.topLevelWidgets():
                if hasattr(widget, 'switch_to_view'):
                    main_window = widget
                    break
                    
            if main_window:
                main_window.switch_to_view("Analysis")
                self.logger.debug("Switched to Analysis view after loading files from Analysis view")
        
        # Reset source view
        self._source_view = None
        
        # No need to manually trigger analysis - it's automatic in the model
    
    @Slot(dict)
    def on_analysis_complete(self, results):
        """
        Handle analysis complete event.
        
        Args:
            results (dict): Analysis results
        """
        # Store current results for export
        self._current_results = results
        
        # Hide progress bar
        self._view.show_progress(False)
        
        # Determine if interval analysis was used
        interval_enabled, interval_seconds = self._model.get_interval_settings()
        interval_results = self._model.get_interval_results()
        
        # Update status message
        if interval_enabled:
            # Count total intervals across all files
            total_intervals = sum(len(intervals) for intervals in interval_results.values())
            self.logger.info(f"Interval analysis complete: {len(results)} files, {total_intervals} intervals")
            self._view.set_status_message(
                f"Analysis complete. Processed {len(results)} file(s) with {interval_seconds}-second intervals "
                f"({total_intervals} total intervals)."
            )
        else:
            self.logger.info("Standard analysis complete")
            self._view.set_status_message(f"Analysis complete. Results processed for {len(results)} file(s).")
        
        # Auto-export the summary table only if this was triggered by file loading
        if self._should_auto_export:
            self._auto_export_results(results)
            # Reset the flag after auto-export
            self._should_auto_export = False
        else:
            self.logger.info("Skipping auto-export (analysis triggered by settings change)")
    
    @Slot(str)
    def on_error(self, error_message):
        """
        Handle error events from the model.
        
        Args:
            error_message (str): Error message
        """
        self._view.show_progress(False)
        self._view.set_status_message(f"Error: {error_message}")
        
        QMessageBox.warning(
            self._view,
            "Analysis Error",
            error_message
        )
    
    @Slot(list)
    def on_files_dropped(self, file_paths):
        """
        Handle files dropped event.
        
        Args:
            file_paths (list): List of dropped file paths
        """
        self.logger.debug(f"Files dropped on analysis view: {file_paths}")
        
        # Confirm they are annotation files
        csv_files = [path for path in file_paths if path.lower().endswith('.csv')]
        
        if csv_files:
            self._view.show_progress(True, 10)
            self._view.set_status_message("Loading files...")
            
            # Set the source view to "analysis" to indicate these files were dropped on the analysis view
            self._source_view = "analysis"
            
            # Process files in the model, which will automatically analyze them
            self._model.load_files(csv_files)
        else:
            QMessageBox.warning(
                self._view, 
                "Invalid Files", 
                "Please drop only CSV annotation files."
            )
    
    @Slot()
    def on_load_files_requested(self):
        """Handle load files button clicked."""
        # Use view's file dialog
        file_paths = self._view.select_files()
        
        if file_paths:
            self._view.show_progress(True, 10)
            self._view.set_status_message("Loading files...")
            
            # Set the source view to "analysis" to indicate these files were loaded from the analysis view
            self._source_view = "analysis"
            
            # Process files in the model, which will automatically analyze them
            self._model.load_files(file_paths)
    
    @Slot(list)
    def on_remove_files_requested(self, indices):
        """
        Handle request to remove selected files.
        
        Args:
            indices (list): List of selected row indices
        """
        if not indices or not self._view._file_paths:
            return
            
        # Get selected file paths in reverse order to avoid index shifting
        selected_paths = []
        for idx in sorted(indices, reverse=True):
            if 0 <= idx < len(self._view._file_paths):
                selected_paths.append(self._view._file_paths[idx])
        
        if not selected_paths:
            return
            
        # Remaining files
        remaining_files = [path for path in self._view._file_paths if path not in selected_paths]
        
        # Log the removal
        self.logger.info(f"Removing {len(selected_paths)} file(s), {len(remaining_files)} remaining")
        
        if remaining_files:
            # Re-process the remaining files
            self._view.show_progress(True, 10)
            self._view.set_status_message(f"Removing {len(selected_paths)} file(s) and reprocessing...")
            # FIX: Enable auto-export when reprocessing files
            self._should_auto_export = True
            
            # Set the source view to "analysis" since we're reprocessing files in the analysis view
            self._source_view = "analysis"
            
            self._model.load_files(remaining_files)
        else:
            # Clear everything if no files remain
            self._view.update_file_list([])
            self._current_results = {}
            self._view.set_status_message("All files removed")
    
    @Slot()
    def on_clear_files_requested(self):
        """Handle request to clear all files."""
        if not self._view._file_paths:
            return
            
        # Prompt for confirmation if files are loaded
        if self._view._file_paths:
            result = QMessageBox.question(
                self._view,
                "Clear All Files",
                "Are you sure you want to clear all loaded files?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if result != QMessageBox.StandardButton.Yes:
                return
                
        # Clear the file list and results
        self._view.update_file_list([])
        self._current_results = {}
        self._view.set_status_message("All files cleared")
        self.logger.info("All files cleared")
    
    @Slot()
    def on_export_table_requested(self):
        """Handle request to export the summary table."""
        # Check if there are results to export
        if not self._current_results:
            QMessageBox.information(
                self._view,
                "No Results",
                "There are no analysis results to export.",
                QMessageBox.StandardButton.Ok
            )
            return
            
        # Determine default export location
        default_dir = os.getcwd()  # Default to current working directory
        
        # If we have files loaded, use the directory of the first file
        if self._view._file_paths:
            first_file_dir = os.path.dirname(self._view._file_paths[0])
            if os.path.exists(first_file_dir):
                default_dir = first_file_dir
        
        # Default filename depends on interval settings
        interval_enabled, interval_seconds = self._model.get_interval_settings()
        if interval_enabled:
            default_filename = f"interval_{interval_seconds}s_summary.csv"
        else:
            default_filename = "summary_table.csv"
        
        # Show save dialog
        export_path = self._view.select_export_file(default_dir, default_filename)
        
        if not export_path:
            # User canceled
            return
            
        # Check if file exists and confirm overwrite
        if os.path.exists(export_path):
            result = QMessageBox.question(
                self._view,
                "File Exists",
                f"The file '{os.path.basename(export_path)}' already exists.\n\nDo you want to overwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if result != QMessageBox.StandardButton.Yes:
                # Let user try again with a different filename
                return self.on_export_table_requested()
        
        # Export the summary table
        if self.export_summary_to_file(export_path):
            # Update status message to reflect whether interval analysis was used
            if interval_enabled:
                self._view.set_status_message(
                    f"Summary table with {interval_seconds}-second intervals exported to: {export_path}"
                )
            else:
                self._view.set_status_message(f"Summary table exported to: {export_path}")
            
            # Show notification
            AutoCloseMessageBox.information(
                self._view,
                "Export Complete",
                f"Analysis results exported to:\n{export_path}",
                timeout=2000
            )
        else:
            QMessageBox.warning(
                self._view,
                "Export Error",
                f"Failed to export summary table to:\n{export_path}",
                QMessageBox.StandardButton.Ok
            )
    
    def _auto_export_results(self, results):
        """
        Automatically export results to CSV.
        
        Args:
            results (dict): Analysis results
        """
        if not results:
            return
            
        try:
            # Use the first file's path as the base directory for export
            if self._view._file_paths:
                # Get the path of the first file
                first_file = self._view._file_paths[0]
                # Use its directory as the export location
                export_dir = os.path.dirname(first_file)
                
                # Default filename depends on interval settings
                interval_enabled, interval_seconds = self._model.get_interval_settings()
                if interval_enabled:
                    export_filename = f"interval_{interval_seconds}s_summary.csv"
                else:
                    export_filename = "summary_table.csv"
                
                # Check if file already exists and add timestamp if needed
                export_path = os.path.join(export_dir, export_filename)
                if os.path.exists(export_path):
                    # Add timestamp to prevent overwriting
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    if interval_enabled:
                        export_filename = f"interval_{interval_seconds}s_summary_{timestamp}.csv"
                    else:
                        export_filename = f"summary_table_{timestamp}.csv"
                    export_path = os.path.join(export_dir, export_filename)
            else:
                # Fallback: Use current directory with default name
                interval_enabled, interval_seconds = self._model.get_interval_settings()
                if interval_enabled:
                    export_filename = f"interval_{interval_seconds}s_summary.csv"
                else:
                    export_filename = "summary_table.csv"
                    
                export_path = os.path.join(os.getcwd(), export_filename)
                
                # Check if file already exists and add timestamp if needed
                if os.path.exists(export_path):
                    # Add timestamp to prevent overwriting
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    if interval_enabled:
                        export_filename = f"interval_{interval_seconds}s_summary_{timestamp}.csv"
                    else:
                        export_filename = f"summary_table_{timestamp}.csv"
                    export_path = os.path.join(os.getcwd(), export_filename)
                
            # Export using the model
            if self._model.export_summary_csv(export_path):
                # Status message depends on interval settings
                if interval_enabled:
                    self.logger.info(f"Automatically exported interval results ({interval_seconds}-second intervals) to {export_path}")
                    self._view.set_status_message(f"Results with {interval_seconds}-second intervals exported to {export_path}")
                else:
                    self.logger.info(f"Automatically exported results to {export_path}")
                    self._view.set_status_message(f"Results exported to {export_path}")
                
                # Show notification
                auto_close_msg = f"Analysis results automatically exported to:\n{export_path}"
                if interval_enabled:
                    auto_close_msg = f"Analysis results with {interval_seconds}-second intervals automatically exported to:\n{export_path}"
                    
                AutoCloseMessageBox.information(
                    self._view,
                    "Export Complete",
                    auto_close_msg,
                    timeout=2000
                )
        except Exception as e:
            self.logger.error(f"Failed to auto-export results: {str(e)}")
            self._view.set_status_message(f"Failed to auto-export results: {str(e)}")
            
            QMessageBox.warning(
                self._view,
                "Export Error",
                f"Failed to automatically export results: {str(e)}"
            )
    
    def export_summary_to_file(self, export_path):
        """
        Export analysis results to the specified file.
        
        Args:
            export_path (str): Path to save the summary table
            
        Returns:
            bool: True if export was successful, False otherwise
        """
        try:
            # Use the model's export function
            result = self._model.export_summary_csv(export_path)
            
            # Log with interval details if enabled
            interval_enabled, interval_seconds = self._model.get_interval_settings()
            if result:
                if interval_enabled:
                    self.logger.info(f"Summary table with {interval_seconds}-second intervals exported to: {export_path}")
                else:
                    self.logger.info(f"Summary table exported to: {export_path}")
            else:
                self.logger.error(f"Failed to export summary table to: {export_path}")
            
            return result
        except Exception as e:
            self.logger.error(f"Error exporting summary table: {str(e)}")
            return False