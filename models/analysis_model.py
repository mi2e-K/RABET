# models/analysis_model.py - Enhanced for automatic summary generation, correct behavior analysis, and configurable metrics
import csv
import logging
import os
import pandas as pd
import numpy as np
import re
from PySide6.QtCore import QObject, Signal, Slot
from models.analysis_config import AnalysisMetricsConfig

class AnalysisModel(QObject):
    """
    Model for analyzing multiple annotation files and generating summary statistics.
    Now supports interval-based analysis for breaking down behaviors by time periods
    and configurable metrics for customized analysis.
    
    Signals:
        data_loaded: Emitted when data is loaded
        analysis_complete: Emitted when analysis is complete
        error_occurred: Emitted when an error occurs
    """
    
    data_loaded = Signal(list)  # List of file paths
    analysis_complete = Signal(dict)  # Analysis results
    error_occurred = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing AnalysisModel")
        
        self._file_paths = []
        self._raw_data = {}  # File path -> data
        self._results = {}  # File path -> metrics
        
        # Interval analysis settings
        self._interval_enabled = False  # Whether to use time intervals for analysis
        self._interval_seconds = 60     # Default interval size (in seconds) - changed from minutes
        self._interval_results = {}     # File path -> interval results
        
        # List of default behaviors to track (for consistent ordering)
        self._default_behaviors = [
            "Attack bites", "Sideways threats", "Tail rattles", "Chasing",
            "Social contact", "Self-grooming", "Locomotion", "Rearing"
        ]
        
        # Initialize behaviors list with defaults (will be extended with custom behaviors)
        self._behaviors = self._default_behaviors.copy()
        
        # Dictionary to track all custom behaviors found across files
        self._custom_behaviors = set()
        
        # Initialize metrics configuration with defaults
        self._metrics_config = AnalysisMetricsConfig()
        
        # Track which view initiated the file load
        self._source_view_for_next_load = None

    def get_metrics_config(self):
        """
        Get the metrics configuration.
        
        Returns:
            AnalysisMetricsConfig: The metrics configuration
        """
        return self._metrics_config
    
    def set_metrics_config(self, config):
        """
        Set the metrics configuration.
        
        Args:
            config (AnalysisMetricsConfig): The metrics configuration to set
        """
        self._metrics_config = config
        self.logger.info("Updated metrics configuration")
        
        # Re-analyze with new metrics if we have data
        if self._raw_data:
            self.analyze_all_files()

    def set_interval_analysis(self, enabled, interval_seconds=60):
        """
        Configure interval-based analysis.
        
        Args:
            enabled (bool): Whether to enable interval-based analysis
            interval_seconds (int, optional): Size of each interval in seconds
        """
        self.logger.info(f"Setting interval analysis: enabled={enabled}, interval={interval_seconds} seconds")
        self._interval_enabled = enabled
        self._interval_seconds = max(1, interval_seconds)  # Ensure minimum 1 second
        
        # FIX: Re-analyze existing data with new settings if we have files loaded
        # We need to actually reprocess each file, not just emit existing results
        if self._raw_data:
            self.logger.info("Reanalyzing existing files with new interval settings")
            
            # Clear existing results and interval results
            old_results = self._results.copy()
            self._results = {}
            self._interval_results = {}
            
            # Reanalyze each file with the new interval settings
            for file_path, df in self._raw_data.items():
                # Get test duration from existing results if available
                test_duration = old_results.get(file_path, {}).get('test_duration', 300)
                
                # Re-run the analysis for this file
                self._analyze_file(file_path, df, test_duration)
            
            # After all files are reanalyzed, emit the complete signal
            self.analyze_all_files()

    def get_interval_settings(self):
        """
        Get current interval analysis settings.
        
        Returns:
            tuple: (enabled, interval_seconds)
        """
        return (self._interval_enabled, self._interval_seconds)

    def load_files(self, file_paths):
        """
        Load multiple CSV files and automatically analyze them.
        
        Args:
            file_paths (list): List of file paths
            
        Returns:
            bool: True if files were loaded successfully, False otherwise
        """
        self.logger.info(f"Loading {len(file_paths)} file(s)")
        
        # Reset data
        self._file_paths = []
        self._raw_data = {}
        self._results = {}
        self._interval_results = {}
        successful_loads = 0
        
        # Reset behaviors to defaults and clear custom behaviors
        self._behaviors = self._default_behaviors.copy()
        self._custom_behaviors = set()
        
        for file_path in file_paths:
            if self.load_file(file_path):
                successful_loads += 1
                self._file_paths.append(file_path)
        
        if successful_loads > 0:
            # Update behaviors list with any custom behaviors found
            self._update_behaviors_list()
            
            # Pass source view info to the data_loaded signal
            source_view = self._source_view_for_next_load
            self._source_view_for_next_load = None  # Reset for next time
            
            # Emit the signal with source information
            self.data_loaded.emit(self._file_paths)
            
            # Automatically analyze data after loading
            self.analyze_all_files()
            
            return True
        else:
            return False
    
    def load_file(self, file_path):
        """
        Load a single CSV file.
        
        Args:
            file_path (str): Path to the CSV file
            
        Returns:
            bool: True if file was loaded successfully, False otherwise
        """
        try:
            self.logger.debug(f"Loading file: {file_path}")
            
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            
            # First read the file as text to inspect its structure
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Extract test duration from metadata section if present
            test_duration = 300  # Default 5 minutes (300 seconds)
            metadata_match = re.search(r'Test Duration \(seconds\),\s*(\d+\.?\d*)', content)
            if metadata_match:
                try:
                    test_duration = float(metadata_match.group(1))
                    self.logger.debug(f"Extracted test duration from metadata: {test_duration} seconds")
                except ValueError:
                    self.logger.warning(f"Failed to parse test duration from metadata: {metadata_match.group(1)}")
            
            # Check if this file contains pre-calculated summary data
            summary_data = {}
            has_summary = "Behavior,Duration,Frequency" in content
            if has_summary:
                self.logger.info(f"Detected summary section in file: {file_path}")
                summary_data = self._extract_summary_data(content)
                
                # Log the extracted summary data
                for behavior, metrics in summary_data.items():
                    self.logger.debug(f"Summary data: {behavior} - Duration: {metrics['duration']}, Frequency: {metrics['frequency']}")
            
            # Check if this file contains raw event data
            has_raw_events = "Event,Onset,Offset" in content
            if has_raw_events:
                self.logger.info(f"Detected raw event data in file: {file_path}")
                
                # Process the raw event data
                df = self._extract_raw_event_data(content)
                
                # Store raw data
                self._raw_data[file_path] = df
                
                # Extract all unique behaviors from the file and add to custom behaviors set
                self._extract_behaviors_from_data(df)
                
                # If we have summary data, use it directly instead of recalculating
                if summary_data:
                    self._analyze_file_with_summary(file_path, df, summary_data, test_duration)
                else:
                    # Otherwise analyze from raw events
                    self._analyze_file(file_path, df, test_duration)
                
                return True
            elif summary_data:
                # If we only have summary data (no raw events), process it directly
                self.logger.info(f"Processing file with only summary data: {file_path}")
                
                # Also extract behavior names from summary data
                for behavior in summary_data.keys():
                    if behavior not in self._default_behaviors:
                        self._custom_behaviors.add(behavior)
                
                # Create placeholder dataframe for consistency
                df = pd.DataFrame(columns=['Event', 'Onset', 'Offset'])
                self._raw_data[file_path] = df
                
                # Process the summary data directly
                self._analyze_file_with_summary(file_path, df, summary_data, test_duration)
                
                return True
            else:
                raise ValueError(f"Unrecognized file format in {file_path} - no event data or summary found")
            
        except Exception as e:
            error_msg = f"Failed to load file {file_path}: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def _extract_raw_event_data(self, content):
        """
        Extract raw event data from file content.
        
        Args:
            content (str): File content as string
            
        Returns:
            pd.DataFrame: Dataframe containing event data
        """
        try:
            # Find the line where the actual CSV data starts
            lines = content.split('\n')
            start_line = 0
            end_line = len(lines)
            
            # Look for the 'Event,Onset,Offset' line
            for i, line in enumerate(lines):
                if line.startswith('Event,Onset,Offset'):
                    start_line = i
                    break
            
            # Look for the end of the event data section
            # This could be an empty line or the start of the summary section
            for i in range(start_line + 1, len(lines)):
                # Check for empty line or summary section header
                if not lines[i].strip() or lines[i].startswith('Behavior,'):
                    end_line = i
                    self.logger.debug(f"Found end of event data at line {i}")
                    break
            
            # If we found the header, read CSV data from start line to end line
            if start_line > 0:
                # Create a new file-like object with just the CSV part
                csv_content = '\n'.join(lines[start_line:end_line])
                
                # CRITICAL FIX: Use dtype=str to prevent automatic type conversion on import
                # This ensures all values are kept as strings initially to avoid decimal/float parsing issues
                df = pd.read_csv(pd.io.common.StringIO(csv_content), dtype=str)
                
                # Now manually convert to proper types
                # This is the key fix - we need to explicitly convert time values to float
                if 'Onset' in df.columns:
                    df['Onset'] = pd.to_numeric(df['Onset'], errors='coerce')
                if 'Offset' in df.columns:
                    df['Offset'] = pd.to_numeric(df['Offset'], errors='coerce')
                    
                # Log extracted data for debugging
                self.logger.debug(f"Extracted raw event data - {len(df)} rows")
                
                # Check for RecordingStart and Attack bites
                rs_events = df[df['Event'] == 'RecordingStart']
                if not rs_events.empty:
                    self.logger.debug(f"Found RecordingStart at {rs_events['Onset'].iloc[0]}s")
                
                attack_events = df[df['Event'] == 'Attack bites']
                if not attack_events.empty:
                    self.logger.debug(f"Found first Attack bites at {attack_events['Onset'].min()}s")
                    
                return df
            else:
                # Otherwise, try to read the whole file and let pandas handle it
                df = pd.read_csv(pd.io.common.StringIO(content), dtype=str)
                # Convert numeric columns
                if 'Onset' in df.columns:
                    df['Onset'] = pd.to_numeric(df['Onset'], errors='coerce')
                if 'Offset' in df.columns:
                    df['Offset'] = pd.to_numeric(df['Offset'], errors='coerce')
                    
                return df
        except Exception as e:
            self.logger.warning(f"Error extracting raw event data: {str(e)}")
            # Fallback to standard CSV reading with explicit dtype settings
            df = pd.read_csv(pd.io.common.StringIO(content), dtype=str)
            # Convert numeric columns
            if 'Onset' in df.columns:
                df['Onset'] = pd.to_numeric(df['Onset'], errors='coerce')
            if 'Offset' in df.columns:
                df['Offset'] = pd.to_numeric(df['Offset'], errors='coerce')
                
            return df
    
    def _extract_summary_data(self, content):
        """
        Extract summary data (behavior duration and frequency) from file content.
        
        Args:
            content (str): File content as string
            
        Returns:
            dict: Dictionary of behavior -> {'duration': float, 'frequency': int}
        """
        summary_data = {}
        
        try:
            # Find the line with the summary header
            lines = content.split('\n')
            summary_start = -1
            
            for i, line in enumerate(lines):
                if line.startswith('Behavior,Duration,Frequency'):
                    summary_start = i
                    break
            
            if summary_start < 0:
                self.logger.warning("Could not find summary section header")
                return summary_data
            
            # Process the summary data lines
            for i in range(summary_start + 1, len(lines)):
                line = lines[i].strip()
                if not line:
                    break  # End of summary section
                
                parts = line.split(',')
                if len(parts) >= 3:
                    behavior = parts[0].strip()
                    
                    # FIX: Skip empty behavior names to prevent "nan" columns
                    if not behavior:
                        self.logger.warning(f"Skipping empty behavior name in summary data line: {line}")
                        continue
                    
                    try:
                        # Parse duration and frequency, handling potential format issues
                        duration_str = parts[1].strip()
                        frequency_str = parts[2].strip()
                        
                        # Convert duration to float
                        duration = float(duration_str) if duration_str else 0.0
                        
                        # Convert frequency to int
                        frequency = int(frequency_str) if frequency_str else 0
                        
                        # Store in summary data dictionary
                        summary_data[behavior] = {
                            'duration': duration,
                            'frequency': frequency
                        }
                        
                        self.logger.debug(f"Extracted summary: {behavior} - Duration: {duration}, Frequency: {frequency}")
                    except (ValueError, IndexError) as e:
                        self.logger.warning(f"Error parsing summary line: {line}, error: {e}")
                        continue
            
            return summary_data
        except Exception as e:
            self.logger.warning(f"Error extracting summary data: {str(e)}")
            return summary_data
    
    def _extract_behaviors_from_data(self, df):
        """
        Extract all unique behaviors from a dataframe and add them to the custom behaviors set.
        
        Args:
            df (pd.DataFrame): Dataframe containing annotation data
        """
        try:
            if 'Event' in df.columns:
                # Get all unique behaviors from the Event column
                unique_behaviors = set(df['Event'].unique())
                
                # FIX: Filter out invalid behavior names
                invalid_behaviors = {'RecordingStart', 'Behavior', '', None}
                
                # Remove invalid behaviors and log them
                for invalid in invalid_behaviors:
                    if invalid in unique_behaviors:
                        unique_behaviors.remove(invalid)
                        if invalid and invalid != 'RecordingStart':
                            self.logger.warning(f"Found invalid behavior '{invalid}' - this is likely an error in the CSV parsing")
                
                # Additional check for NaN values
                unique_behaviors = {b for b in unique_behaviors if pd.notna(b) and str(b).strip()}
                
                # Add any behaviors not in the default list to the custom behaviors set
                for behavior in unique_behaviors:
                    if behavior not in self._default_behaviors:
                        self._custom_behaviors.add(behavior)
                        self.logger.debug(f"Found custom behavior: {behavior}")
        except Exception as e:
            self.logger.warning(f"Error extracting behaviors from data: {str(e)}")
    
    def _update_behaviors_list(self):
        """
        Update the behaviors list to include all custom behaviors found across files.
        """
        # Start with default behaviors
        self._behaviors = self._default_behaviors.copy()
        
        # Add any custom behaviors
        if self._custom_behaviors:
            # Sort custom behaviors alphabetically for consistency
            sorted_custom_behaviors = sorted(self._custom_behaviors)
            self._behaviors.extend(sorted_custom_behaviors)
            
            self.logger.info(f"Added {len(self._custom_behaviors)} custom behaviors to analysis: {sorted_custom_behaviors}")
    
    def _analyze_file_with_summary(self, file_path, df, summary_data, test_duration=300):
        """
        Analyze a file using pre-calculated summary data and, if available, raw event data.
        
        Args:
            file_path (str): Path to the source file
            df (pd.DataFrame): Raw event data (may be empty)
            summary_data (dict): Pre-calculated behavior metrics
            test_duration (float, optional): Test duration in seconds
        """
        try:
            self.logger.info(f"Analyzing file with summary data: {file_path}")
            
            # Initialize results dictionary
            results = {
                "test_duration": test_duration,
            }
            
            # First, use the pre-calculated values from the summary section
            for behavior, metrics in summary_data.items():
                # FIX: Skip empty behavior names to prevent "nan" columns
                if not behavior or not behavior.strip():
                    self.logger.warning(f"Skipping empty behavior name in summary data")
                    continue
                    
                # Store duration and frequency directly from summary data
                results[f"{behavior}_duration"] = metrics['duration']
                results[f"{behavior}_count"] = metrics['frequency']
                
                self.logger.debug(f"Using summary data: {behavior} - Duration: {metrics['duration']}, Frequency: {metrics['frequency']}")
            
            # Fill in any missing behaviors with zeros
            for behavior in self._behaviors:
                if f"{behavior}_duration" not in results:
                    results[f"{behavior}_duration"] = 0.0
                    results[f"{behavior}_count"] = 0
            
            # If we have raw event data, calculate the custom metrics
            if not df.empty:
                # Get enabled latency metrics from configuration
                latency_metrics = self._metrics_config.get_enabled_latency_metrics()
                
                # Calculate each configured latency metric
                for metric in latency_metrics:
                    metric_name = metric["name"]
                    behavior = metric["behavior"]
                    
                    # Calculate latency for this behavior
                    latency = self._calculate_behavior_latency(df, behavior, test_duration)
                    results[f"{metric_name.lower().replace(' ', '_')}"] = latency
                    self.logger.debug(f"{metric_name}: {latency:.2f}s")
                
                # Get enabled total time metrics from configuration
                total_time_metrics = self._metrics_config.get_enabled_total_time_metrics()
                
                # Calculate each configured total time metric
                for metric in total_time_metrics:
                    metric_name = metric["name"]
                    behaviors = metric["behaviors"]
                    
                    # Calculate total time for these behaviors
                    total_time = self._calculate_total_aggression(df, behaviors)
                    results[f"{metric_name.lower().replace(' ', '_')}"] = total_time
                    self.logger.debug(f"{metric_name}: {total_time:.2f}s")
                
                # If interval analysis is enabled, perform interval-based analysis
                if self._interval_enabled and not df.empty:
                    interval_results = self._analyze_intervals(df, test_duration)
                    self._interval_results[file_path] = interval_results
                    self.logger.info(f"Completed interval analysis with {len(interval_results)} intervals")
            else:
                # No raw event data, try to derive from summary data for compatibility
                
                # Handle latency metrics
                latency_metrics = self._metrics_config.get_enabled_latency_metrics()
                for metric in latency_metrics:
                    metric_name = metric["name"]
                    behavior = metric["behavior"]
                    
                    # If behavior exists in summary and has occurrences, use 0 as placeholder
                    # Otherwise use test duration (indicating no occurrences)
                    if behavior in summary_data and summary_data[behavior]["frequency"] > 0:
                        results[f"{metric_name.lower().replace(' ', '_')}"] = 0.0
                    else:
                        results[f"{metric_name.lower().replace(' ', '_')}"] = test_duration
                
                # Handle total time metrics - try to sum the durations from summary
                total_time_metrics = self._metrics_config.get_enabled_total_time_metrics()
                for metric in total_time_metrics:
                    metric_name = metric["name"]
                    behaviors = metric["behaviors"]
                    
                    # Sum the durations for the behaviors in this metric
                    total_time = 0.0
                    for behavior in behaviors:
                        if behavior in summary_data:
                            total_time += summary_data[behavior]["duration"]
                    
                    results[f"{metric_name.lower().replace(' ', '_')}"] = total_time
                
                # We can't do interval analysis without raw event data
                if self._interval_enabled:
                    self.logger.warning(f"Interval analysis requested but no raw event data available for {file_path}")
                    # Create empty interval results to maintain consistency
                    self._interval_results[file_path] = []
            
            # Store results
            self._results[file_path] = results
            
            # Log all calculated metrics for validation
            self.logger.info(f"Analysis summary for {file_path}:")
            for k, v in sorted(results.items()):
                self.logger.info(f"  {k}: {v}")
            
            return True
        except Exception as e:
            error_msg = f"Failed to analyze file with summary data {file_path}: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def _analyze_file(self, file_path, df, test_duration=300):
        """
        Analyze a single annotation file and generate metrics.
        
        Args:
            file_path (str): Path to the source file
            df (pd.DataFrame): Loaded annotation data
            test_duration (float, optional): Test duration in seconds, default is 300 (5 minutes)
        """
        try:
            self.logger.info(f"Analyzing file from raw event data: {file_path}")
            
            # Log detailed information about the dataset
            self.logger.info(f"DataFrame info for {file_path}:")
            self.logger.info(f"  Shape: {df.shape}")
            self.logger.info(f"  Columns: {df.columns.tolist()}")
            self.logger.info(f"  Data types: {df.dtypes}")
            
            # Check for RecordingStart and Attack bites events
            rs_events = df[df['Event'] == 'RecordingStart']
            attack_events = df[df['Event'] == 'Attack bites']
            
            self.logger.info(f"Data validation:")
            self.logger.info(f"  Found {len(rs_events)} RecordingStart events")
            self.logger.info(f"  Found {len(attack_events)} Attack bites events")
            
            if not rs_events.empty:
                self.logger.info(f"  RecordingStart time: {rs_events['Onset'].iloc[0]}")
            if not attack_events.empty:
                self.logger.info(f"  First Attack bites time: {attack_events['Onset'].min()}")
            
            # First, ensure all values are properly converted to numeric
            try:
                # Explicitly convert to float type for precise calculations
                df['Onset'] = df['Onset'].astype(float)
                df['Offset'] = df['Offset'].astype(float)
                
                # Log column types after conversion
                self.logger.info(f"  Column types after conversion: {df.dtypes}")
                
                # Check for invalid values
                nan_rows = df[df['Onset'].isna() | df['Offset'].isna()]
                if not nan_rows.empty:
                    self.logger.warning(f"Found {len(nan_rows)} rows with non-numeric values in Onset/Offset columns")
                    # Drop these rows to prevent calculation errors
                    df = df.dropna(subset=['Onset', 'Offset'])
            except Exception as e:
                self.logger.warning(f"Error converting timestamp columns to numeric: {str(e)}")
                # Fall back to pandas to_numeric with coercion
                df['Onset'] = pd.to_numeric(df['Onset'], errors='coerce')
                df['Offset'] = pd.to_numeric(df['Offset'], errors='coerce')
                df = df.dropna(subset=['Onset', 'Offset'])
            
            # Determine the test duration from the data or use provided value
            file_test_duration = self._get_test_duration(df)
            if file_test_duration > 0:
                # Use the detected test duration from the file
                test_duration = file_test_duration
                self.logger.debug(f"Using detected test duration: {test_duration} seconds")
            else:
                self.logger.debug(f"Using provided test duration: {test_duration} seconds")
            
            # Initialize results dictionary
            results = {
                "test_duration": test_duration,
            }
            
            # For each behavior, calculate duration and count
            # Use the combined list of default and custom behaviors
            for behavior in self._behaviors:
                behavior_df = df[df['Event'] == behavior]
                
                # Calculate total duration in seconds
                if not behavior_df.empty:
                    # Explicitly convert to float to ensure proper calculations
                    durations = behavior_df['Offset'].astype(float) - behavior_df['Onset'].astype(float)
                    duration = durations.sum()
                    count = len(behavior_df)
                    
                    self.logger.debug(f"Behavior '{behavior}': {count} occurrences, {duration:.2f}s total duration")
                else:
                    duration = 0
                    count = 0
                    self.logger.debug(f"Behavior '{behavior}': No occurrences")
                
                # Store in results - ensure both duration and count are correctly stored
                results[f"{behavior}_duration"] = float(duration)  # Ensure it's a float
                results[f"{behavior}_count"] = int(count)  # Ensure it's an integer
            
            # Get enabled latency metrics from configuration
            latency_metrics = self._metrics_config.get_enabled_latency_metrics()
            
            # Calculate each configured latency metric
            for metric in latency_metrics:
                metric_name = metric["name"]
                behavior = metric["behavior"]
                
                # Calculate latency for this behavior
                latency = self._calculate_behavior_latency(df, behavior, test_duration)
                results[f"{metric_name.lower().replace(' ', '_')}"] = latency
                self.logger.debug(f"{metric_name}: {latency:.2f}s")
            
            # Get enabled total time metrics from configuration
            total_time_metrics = self._metrics_config.get_enabled_total_time_metrics()
            
            # Calculate each configured total time metric
            for metric in total_time_metrics:
                metric_name = metric["name"]
                behaviors = metric["behaviors"]
                
                # Calculate total time for these behaviors
                total_time = self._calculate_total_aggression(df, behaviors)
                results[f"{metric_name.lower().replace(' ', '_')}"] = total_time
                self.logger.debug(f"{metric_name}: {total_time:.2f}s")
            
            # Store results
            self._results[file_path] = results
            
            # If interval analysis is enabled, perform interval-based analysis
            if self._interval_enabled:
                interval_results = self._analyze_intervals(df, test_duration)
                self._interval_results[file_path] = interval_results
                self.logger.info(f"Completed interval analysis with {len(interval_results)} intervals")
            
            # Log all calculated metrics for validation
            self.logger.info(f"Analysis summary for {file_path}:")
            for k, v in sorted(results.items()):
                self.logger.info(f"  {k}: {v}")
            
            return True
            
        except Exception as e:
            error_msg = f"Failed to analyze file {file_path}: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def _analyze_intervals(self, df, test_duration):
        """
        Analyze behavior data in time intervals.
        
        Args:
            df (pd.DataFrame): Raw event data
            test_duration (float): Test duration in seconds
            
        Returns:
            list: List of dictionaries with interval metrics
        """
        self.logger.info(f"Performing interval analysis with {self._interval_seconds} second intervals")
        
        # FIX: Find the RecordingStart time - intervals should start from here, not from 0
        recording_start_time = 0
        recording_starts = df[df['Event'] == 'RecordingStart'].sort_values('Onset')
        
        if not recording_starts.empty:
            # Use the first RecordingStart as the analysis start point
            recording_start_time = float(recording_starts['Onset'].iloc[0])
            self.logger.info(f"Found RecordingStart at {recording_start_time}s - intervals will start from this time")
        else:
            # Fallback: use the earliest event time
            if not df.empty:
                recording_start_time = float(df['Onset'].min())
                self.logger.warning(f"No RecordingStart found - using earliest event time: {recording_start_time}s")
            else:
                recording_start_time = 0
                self.logger.warning("Empty dataframe - using time 0 as start")
        
        # Calculate the analysis end time
        analysis_end_time = recording_start_time + test_duration
        
        # Calculate the number of intervals from RecordingStart
        num_intervals = int(np.ceil(test_duration / self._interval_seconds))
        
        self.logger.info(f"Analysis period: {recording_start_time}s to {analysis_end_time}s ({test_duration}s duration)")
        self.logger.info(f"Will create {num_intervals} intervals of {self._interval_seconds}s each")
        
        # Initialize results for each interval
        interval_results = []
        
        # Process each interval starting from RecordingStart
        for i in range(num_intervals):
            # FIX: Calculate interval boundaries relative to RecordingStart
            start_time = recording_start_time + (i * self._interval_seconds)
            end_time = min(recording_start_time + ((i + 1) * self._interval_seconds), analysis_end_time)
            
            self.logger.debug(f"Interval {i+1}: {start_time}s to {end_time}s")
            
            # Initialize metrics for this interval
            interval_metrics = {
                "interval_number": i + 1,
                "start_time": start_time,
                "end_time": end_time,
                "duration": end_time - start_time
            }
            
            # For each behavior, calculate metrics within this interval
            for behavior in self._behaviors:
                behavior_df = df[df['Event'] == behavior]
                
                if not behavior_df.empty:
                    # Calculate duration and count within this interval
                    interval_duration = 0
                    interval_count = 0
                    
                    for _, event in behavior_df.iterrows():
                        onset = float(event['Onset'])
                        offset = float(event['Offset'])
                        
                        # Check how the event overlaps with the interval
                        if onset >= end_time or offset <= start_time:
                            # Event is completely outside the interval
                            continue
                        
                        # Calculate the overlapping portion
                        overlap_start = max(onset, start_time)
                        overlap_end = min(offset, end_time)
                        overlap_duration = overlap_end - overlap_start
                        
                        if overlap_duration > 0:
                            interval_duration += overlap_duration
                            # FIX: Count each event only once per interval
                            # An event should be counted in an interval if it has ANY overlap with that interval
                            interval_count += 1
                            
                            self.logger.debug(f"  {behavior} event {onset}-{offset}s overlaps with interval {start_time}-{end_time}s by {overlap_duration:.2f}s")
                    
                    # Store metrics for this behavior in this interval
                    interval_metrics[f"{behavior}_duration"] = float(interval_duration)
                    interval_metrics[f"{behavior}_count"] = int(interval_count)
                else:
                    # No events for this behavior in the dataset
                    interval_metrics[f"{behavior}_duration"] = 0.0
                    interval_metrics[f"{behavior}_count"] = 0
            
            # Calculate custom metrics for this interval
            interval_df = self._filter_events_for_interval(df, start_time, end_time)
            
            # Get total time metrics from configuration
            total_time_metrics = self._metrics_config.get_enabled_total_time_metrics()
            
            # Calculate each configured total time metric for this interval
            for metric in total_time_metrics:
                metric_name = metric["name"]
                behaviors = metric["behaviors"]
                
                # Calculate total time for these behaviors in this interval
                total_time = self._calculate_total_aggression(interval_df, behaviors)
                interval_metrics[f"{metric_name.lower().replace(' ', '_')}"] = total_time
            
            # Add to interval results
            interval_results.append(interval_metrics)
            
            self.logger.debug(f"Interval {i+1}: {start_time}s - {end_time}s processed")
        
        # Log total intervals for verification
        self.logger.info(f"Created {len(interval_results)} intervals covering {recording_start_time}s to {analysis_end_time}s")
        
        return interval_results
    
    def _filter_events_for_interval(self, df, start_time, end_time):
        """
        Filter events that overlap with a specific time interval.
        
        Args:
            df (pd.DataFrame): Raw event data
            start_time (float): Interval start time in seconds
            end_time (float): Interval end time in seconds
            
        Returns:
            pd.DataFrame: Filtered dataframe with events that overlap with the interval
        """
        # Make a copy to avoid SettingWithCopyWarning
        filtered_df = df.copy()
        
        # For our calculation, we need to clip event boundaries to the interval
        # But first, filter to only events that overlap with the interval
        mask = ((filtered_df['Onset'] < end_time) & (filtered_df['Offset'] > start_time))
        interval_df = filtered_df[mask].copy()
        
        # Adjust onset and offset times to fit within the interval
        interval_df.loc[:, 'Original_Onset'] = interval_df['Onset'].copy()
        interval_df.loc[:, 'Original_Offset'] = interval_df['Offset'].copy()
        interval_df.loc[:, 'Onset'] = interval_df['Onset'].clip(lower=start_time)
        interval_df.loc[:, 'Offset'] = interval_df['Offset'].clip(upper=end_time)
        
        return interval_df
    
    def _get_test_duration(self, df):
        """
        Determine the test duration from the annotation data.
        
        Args:
            df (pd.DataFrame): Annotation data
            
        Returns:
            float: Test duration in seconds
        """
        try:
            # First, look for a RecordingStart event
            recording_start = df[df['Event'] == 'RecordingStart']
            
            if not recording_start.empty:
                # Convert to float explicitly and ensure no NaN values
                onset_value = recording_start['Onset'].iloc[0]
                if pd.notnull(onset_value):
                    start_time = float(onset_value)
                    self.logger.debug(f"Found RecordingStart event at time: {start_time}")
                    
                    # Get the last offset time of any event
                    offset_values = df['Offset'].dropna()
                    if not offset_values.empty:
                        last_time = float(offset_values.max())
                        duration = last_time - start_time
                        self.logger.debug(f"Test duration from RecordingStart to last offset: {duration}s")
                        return duration
            
            # Fallback: Use the range from the first Onset to the last Offset
            if not df.empty and 'Onset' in df.columns and 'Offset' in df.columns:
                onset_values = df['Onset'].dropna()
                offset_values = df['Offset'].dropna()
                
                if not onset_values.empty and not offset_values.empty:
                    min_time = float(onset_values.min())
                    max_time = float(offset_values.max())
                    duration = max_time - min_time
                    self.logger.debug(f"Test duration from first onset to last offset: {duration}s")
                    return duration
            
            # Default assumption: 5 minutes (300 seconds)
            self.logger.debug("Could not determine test duration from data, using default: 300 seconds")
            return 300
            
        except Exception as e:
            self.logger.warning(f"Exception in _get_test_duration: {str(e)}")
            return 300  # Default to 5 minutes
    
    def _calculate_behavior_latency(self, df, target_behavior, test_duration):
        """
        Calculate the latency to first occurrence of a specific behavior.
        If the behavior is not observed, returns the test duration.
        
        Args:
            df (pd.DataFrame): Annotation data
            target_behavior (str): Target behavior to measure latency for
            test_duration (float): Test duration in seconds
            
        Returns:
            float: Behavior latency in seconds
        """
        try:
            # Ensure df is not empty
            if df.empty:
                self.logger.debug(f"Empty dataframe, using test duration as {target_behavior} latency: {test_duration}s")
                return test_duration
            
            # Verify data types of time columns - critical for accurate calculation
            try:
                # Log column types for debugging
                self.logger.debug(f"Column dtypes before numeric conversion: {df.dtypes}")
                
                # Ensure Onset and Offset are numeric
                if pd.api.types.is_object_dtype(df['Onset']):
                    df['Onset'] = pd.to_numeric(df['Onset'], errors='coerce')
                    self.logger.debug("Converted Onset to numeric")
                if pd.api.types.is_object_dtype(df['Offset']):
                    df['Offset'] = pd.to_numeric(df['Offset'], errors='coerce')
                    self.logger.debug("Converted Offset to numeric")
                
                # Log column types after conversion
                self.logger.debug(f"Column dtypes after numeric conversion: {df.dtypes}")
            except Exception as e:
                self.logger.warning(f"Error converting time columns to numeric: {str(e)}")
            
            # Find all RecordingStart events and sort by onset time
            recording_starts = df[df['Event'] == 'RecordingStart'].sort_values('Onset')
            
            # Find target behavior events and sort by onset time
            behavior_events = df[df['Event'] == target_behavior].sort_values('Onset')
            
            # If the behavior is not found, return test duration
            if behavior_events.empty:
                self.logger.debug(f"No {target_behavior} found, using test duration: {test_duration}s")
                return test_duration
            
            # Log all RecordingStart events for debugging
            self.logger.info(f"LATENCY CALCULATION DETAILS for {target_behavior}:")
            self.logger.info(f"  Found {len(behavior_events)} {target_behavior} events")
            self.logger.info(f"  Found {len(recording_starts)} RecordingStart events")
            
            if not recording_starts.empty:
                for i, rs in recording_starts.iterrows():
                    self.logger.info(f"  RecordingStart #{i}: {rs['Onset']}s")
            
            if not behavior_events.empty:
                self.logger.info(f"  All {target_behavior} onsets: {list(behavior_events['Onset'])}")
                min_behavior_time = behavior_events['Onset'].min()
                self.logger.info(f"  First {target_behavior} onset: {min_behavior_time}s (type: {type(min_behavior_time)})")
            
            # Handle the case with multiple RecordingStart events
            if len(recording_starts) > 1:
                self.logger.info(f"  Multiple RecordingStart events detected - determining best match")
                
                # Get first behavior time
                first_behavior_time = float(behavior_events['Onset'].min())
                
                # Find the RecordingStart that comes before this behavior
                # Sort RecordingStarts by time and find the last one that's before the first occurrence
                valid_starts = recording_starts[recording_starts['Onset'] < first_behavior_time]
                
                if not valid_starts.empty:
                    # Use the latest RecordingStart before the first behavior
                    start_time = float(valid_starts['Onset'].max())
                    self.logger.info(f"  Using RecordingStart at {start_time}s (latest before first {target_behavior})")
                else:
                    # If no RecordingStart is before the first behavior, use the earliest RecordingStart
                    # This is a fallback that shouldn't normally happen with valid data
                    start_time = float(recording_starts['Onset'].min())
                    self.logger.info(f"  No RecordingStart before first {target_behavior}! Using earliest at {start_time}s")
            elif not recording_starts.empty:
                # Just one RecordingStart - use it directly
                start_time = float(recording_starts['Onset'].iloc[0])
                self.logger.info(f"  Using single RecordingStart at {start_time}s")
            else:
                # No RecordingStart found - fall back to earliest event time
                start_time = float(df['Onset'].min())
                self.logger.info(f"  No RecordingStart events! Using earliest event time: {start_time}s")
            
            # Calculate latency with explicit float conversion
            first_behavior_time = float(behavior_events['Onset'].min())
            latency = first_behavior_time - start_time
            
            # Log the exact calculation
            self.logger.info(f"  Calculation: {first_behavior_time} - {start_time} = {latency}")
            
            # Ensure non-negative value (should not happen with proper data)
            if latency < 0:
                self.logger.warning(f"  Calculated negative latency ({latency}s)! This suggests data ordering issues.")
                latency = max(0, latency)
            
            self.logger.info(f"FINAL {target_behavior} LATENCY: {latency}s")
            return latency
                
        except Exception as e:
            self.logger.warning(f"Error in latency calculation for {target_behavior}: {str(e)}", exc_info=True)
            return test_duration
    
    def _calculate_total_aggression(self, df, behaviors):
        """
        Calculate the total time for a set of behaviors, accounting for overlaps.
        Uses a timeline approach to handle overlapping behaviors.
        
        Args:
            df (pd.DataFrame): Annotation data
            behaviors (list): List of behaviors to include
            
        Returns:
            float: Total duration in seconds
        """
        try:
            # Ensure the dataframe is not empty
            if df.empty:
                return 0
            
            # Filter for specified behaviors
            behaviors_df = df[df['Event'].isin(behaviors)].copy()
            
            # If no specified behaviors found, return 0
            if behaviors_df.empty:
                return 0
            
            # Convert onset/offset to numeric to ensure proper calculations
            try:
                # Use .loc to avoid SettingWithCopyWarning
                behaviors_df.loc[:, 'Onset'] = pd.to_numeric(behaviors_df['Onset'], errors='coerce')
                behaviors_df.loc[:, 'Offset'] = pd.to_numeric(behaviors_df['Offset'], errors='coerce')
                
                # Drop any rows with NaN values after conversion
                behaviors_df = behaviors_df.dropna(subset=['Onset', 'Offset'])
                
                # Validate that Offset >= Onset for each row
                invalid_rows = behaviors_df[behaviors_df['Offset'] < behaviors_df['Onset']]
                if not invalid_rows.empty:
                    self.logger.warning(f"Found {len(invalid_rows)} behavior events with Offset < Onset")
                    # Remove invalid rows
                    behaviors_df = behaviors_df[behaviors_df['Offset'] >= behaviors_df['Onset']]
            except Exception as e:
                self.logger.warning(f"Error converting behavior times to numeric: {str(e)}")
                return 0
            
            # If after cleaning we have no valid rows, return 0
            if behaviors_df.empty:
                return 0
            
            # Timeline approach to account for overlaps
            # Create a list of events (start and end points)
            events = []
            for _, row in behaviors_df.iterrows():
                # Ensure the values are float for consistency
                onset = float(row['Onset'])
                offset = float(row['Offset'])
                
                # Add start and end events to the timeline
                events.append((onset, 1))    # 1 = onset (start of behavior)
                events.append((offset, -1))  # -1 = offset (end of behavior)
            
            # Sort events chronologically
            events.sort(key=lambda x: (x[0], -x[1]))  # Sort by time, then event type (starts before ends)
            
            if not events:
                return 0
            
            # Traverse the timeline, tracking active behaviors
            active_count = 0
            last_time = events[0][0]  # Start with the first event time
            total_time = 0
            
            for time, event_type in events:
                # If we have at least one active behavior, add the elapsed time
                if active_count > 0:
                    elapsed = time - last_time
                    if elapsed > 0:  # Only add positive durations
                        total_time += elapsed
                
                # Update the count of active behaviors
                active_count += event_type
                # Update the last time point
                last_time = time
            
            return total_time
            
        except Exception as e:
            self.logger.warning(f"Error calculating total time for behaviors {behaviors}: {str(e)}")
            return 0
    
    def analyze_all_files(self):
        """
        Process all loaded files and emit results.
        
        Returns:
            bool: True if analysis was successful, False otherwise
        """
        if not self._raw_data:
            self.logger.warning("No data to analyze")
            return False
        
        try:
            # Log summary of analysis results
            for file_path, metrics in self._results.items():
                file_name = os.path.basename(file_path)
                self.logger.info(f"Analysis results for {file_name}:")
                
                # Log durations and counts for each behavior
                for behavior in self._behaviors:
                    duration = metrics.get(f"{behavior}_duration", 0)
                    count = metrics.get(f"{behavior}_count", 0)
                    self.logger.info(f"  {behavior}: {count} occurrences, {duration:.2f}s total")
                
                # Log custom metrics (latency)
                latency_metrics = self._metrics_config.get_enabled_latency_metrics()
                for metric in latency_metrics:
                    metric_name = metric["name"]
                    key = f"{metric_name.lower().replace(' ', '_')}"
                    if key in metrics:
                        self.logger.info(f"  {metric_name}: {metrics[key]:.2f}s")
                
                # Log custom metrics (total time)
                total_time_metrics = self._metrics_config.get_enabled_total_time_metrics()
                for metric in total_time_metrics:
                    metric_name = metric["name"]
                    key = f"{metric_name.lower().replace(' ', '_')}"
                    if key in metrics:
                        self.logger.info(f"  {metric_name}: {metrics[key]:.2f}s")
                
                # Log interval results if available
                if self._interval_enabled and file_path in self._interval_results:
                    intervals = self._interval_results[file_path]
                    self.logger.info(f"  Interval analysis: {len(intervals)} intervals of {self._interval_seconds} seconds each")
            
            # Emit the results for UI update
            self.analysis_complete.emit(self._results)
            return True
            
        except Exception as e:
            error_msg = f"Failed to analyze data: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def get_results(self):
        """
        Get all analysis results.
        
        Returns:
            dict: Analysis results for whole sessions
        """
        return self._results
    
    def get_interval_results(self):
        """
        Get interval-based analysis results.
        
        Returns:
            dict: Interval analysis results
        """
        return self._interval_results
    
    def get_behaviors_list(self):
        """
        Get the list of all behaviors found in the loaded data.
        
        Returns:
            list: List of behavior names
        """
        return self._behaviors.copy()
    
    def export_summary_csv(self, file_path):
        """
        Export the summary table to CSV.
        
        Args:
            file_path (str): Path to save the CSV file
            
        Returns:
            bool: True if exported successfully, False otherwise
        """
        try:
            # FIX: Improved logic for determining export format
            # Check if interval analysis was enabled AND we have interval results
            if self._interval_enabled and self._interval_results:
                return self._export_interval_summary(file_path)
            else:
                return self._export_standard_summary(file_path)
        except Exception as e:
            error_msg = f"Failed to export summary: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def _export_standard_summary(self, file_path):
        """
        Export the standard summary table (whole-session analysis).
        
        Args:
            file_path (str): Path to save the CSV file
            
        Returns:
            bool: True if exported successfully, False otherwise
        """
        try:
            # Create a specialized CSV writer that preserves the exact format we want
            with open(file_path, 'w', newline='') as f:
                writer = csv.writer(f)
                
                # Get all behaviors for the header (both default and custom)
                behaviors_list = self._behaviors
                
                # Calculate the number of behaviors for the header row formatting
                num_behaviors = len(behaviors_list)
                
                # Write the header row with Duration and Frequency sections
                # Each section needs entries for each behavior plus one empty spacer
                header_row = [''] + ['Duration'] + [''] * num_behaviors + ['Frequency'] + [''] * num_behaviors + [''] * len(self._metrics_config.get_enabled_latency_metrics() + self._metrics_config.get_enabled_total_time_metrics())
                writer.writerow(header_row)
                
                # Write column headers
                column_headers = ['animal_id']
                
                # Add duration behavior headers (no empty spacer at the end)
                column_headers.extend(behaviors_list)
                
                # Add empty spacer between Duration and Frequency sections
                column_headers.append('')
                
                # Add frequency behavior headers (no empty spacer at the end)
                column_headers.extend(behaviors_list)
                
                # Add empty spacer between Frequency and custom metrics
                column_headers.append('')
                
                # Add custom metrics headers
                latency_metrics = self._metrics_config.get_enabled_latency_metrics()
                total_time_metrics = self._metrics_config.get_enabled_total_time_metrics()
                
                for metric in latency_metrics:
                    column_headers.append(metric["name"])
                
                for metric in total_time_metrics:
                    column_headers.append(metric["name"])
                
                writer.writerow(column_headers)
                
                # Log the structure of the summary table
                self.logger.info(f"Summary table structure: {len(behaviors_list)} behaviors + {len(latency_metrics)} latency metrics + {len(total_time_metrics)} total time metrics")
                self.logger.info(f"Behaviors included: {behaviors_list}")
                
                # Write data rows and validate metrics for each file
                for file_path, metrics in self._results.items():
                    # Get animal ID from filename without _annotations suffix
                    animal_id = os.path.splitext(os.path.basename(file_path))[0]
                    if animal_id.endswith("_annotations"):
                        animal_id = animal_id[:-12]  # Remove "_annotations"
                    
                    # Start with animal_id
                    row = [animal_id]
                    
                    # Log individual file metrics for validation
                    self.logger.info(f"Metrics for {animal_id}:")
                    
                    # Add duration values for each behavior
                    for behavior in behaviors_list:
                        # Get duration and ensure it's a float
                        duration = float(metrics.get(f"{behavior}_duration", 0))
                        self.logger.debug(f"  {behavior} duration: {duration:.2f}s")
                        row.append(f"{duration:.2f}")
                    
                    # Add empty spacer cell between Duration and Frequency
                    row.append("")
                    
                    # Add frequency values for each behavior
                    for behavior in behaviors_list:
                        # Get count and ensure it's an integer
                        count = int(metrics.get(f"{behavior}_count", 0))
                        self.logger.debug(f"  {behavior} count: {count}")
                        row.append(str(count))
                    
                    # Add empty spacer cell between Frequency and custom metrics
                    row.append("")
                    
                    # Add latency metrics
                    for metric in latency_metrics:
                        metric_name = metric["name"]
                        key = f"{metric_name.lower().replace(' ', '_')}"
                        value = float(metrics.get(key, metrics.get('test_duration', 300)))
                        self.logger.info(f"  {metric_name}: {value:.2f}s")
                        row.append(f"{value:.2f}")
                    
                    # Add total time metrics
                    for metric in total_time_metrics:
                        metric_name = metric["name"]
                        key = f"{metric_name.lower().replace(' ', '_')}"
                        value = float(metrics.get(key, 0))
                        self.logger.info(f"  {metric_name}: {value:.2f}s")
                        row.append(f"{value:.2f}")
                    
                    writer.writerow(row)
            
            self.logger.info(f"Successfully exported standard summary table to {file_path}")
            return True
        except Exception as e:
            error_msg = f"Failed to export standard summary: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def _export_interval_summary(self, file_path):
        """
        Export the interval-based summary table.
        
        Args:
            file_path (str): Path to save the CSV file
            
        Returns:
            bool: True if exported successfully, False otherwise
        """
        try:
            # Create a specialized CSV writer that preserves the exact format we want
            with open(file_path, 'w', newline='') as f:
                writer = csv.writer(f)
                
                # Get all behaviors for the header (both default and custom)
                behaviors_list = self._behaviors
                
                # Write a title row indicating this is an interval-based analysis
                writer.writerow([f"Interval analysis ({self._interval_seconds}-second intervals)"])
                # FIX: Remove the unnecessary blank line on the second row
                
                # Write structured headers with Duration/Frequency sections
                # First header row - spanning headers
                header_row1 = ['', '', '', '']  # animal_id, Interval, Time (min), blank column
                header_row1.extend(['Duration'] + [''] * (len(behaviors_list) - 1))  # Duration section
                header_row1.append('')  # Blank column between sections
                header_row1.extend(['Frequency'] + [''] * (len(behaviors_list) - 1))  # Frequency section
                # FIX: Add blank column before additional metrics
                total_time_metrics = self._metrics_config.get_enabled_total_time_metrics()
                if total_time_metrics:
                    header_row1.append('')  # Blank column before metrics
                    header_row1.extend([''] * len(total_time_metrics))
                writer.writerow(header_row1)
                
                # Second header row - column headers
                # Change 'Animal ID' to 'animal_id' and change 'Time (min)' to 'Time (sec)'
                column_headers = ['animal_id', 'Interval', 'Time (sec)', '']  # Added blank column after Time (sec)
                
                # Add behavior names for duration section
                column_headers.extend(behaviors_list)
                
                # Add blank column between Duration and Frequency sections
                column_headers.append('')
                
                # Add behavior names for frequency section
                column_headers.extend(behaviors_list)
                
                # FIX: Add blank column before additional metrics
                if total_time_metrics:
                    column_headers.append('')  # Blank column before metrics
                    
                    # Add custom metric headers
                    for metric in total_time_metrics:
                        column_headers.append(metric["name"])
                
                writer.writerow(column_headers)
                
                # Write data rows for each file and each interval
                for file_path, intervals in self._interval_results.items():
                    # Get animal ID from filename
                    animal_id = os.path.splitext(os.path.basename(file_path))[0]
                    if animal_id.endswith("_annotations"):
                        animal_id = animal_id[:-12]  # Remove "_annotations"
                    
                    # Write rows for each interval
                    for interval in intervals:
                        # Start with animal_id, interval number, and time range
                        interval_num = interval['interval_number']
                        start_sec = interval['start_time']  # Keep in seconds
                        end_sec = interval['end_time']      # Keep in seconds
                        time_range = f"{start_sec:.1f}-{end_sec:.1f}"
                        
                        # Include blank column after Time (sec)
                        row = [animal_id, str(interval_num), time_range, '']
                        
                        # Add duration values for each behavior
                        for behavior in behaviors_list:
                            # Get duration and ensure it's a float
                            duration = float(interval.get(f"{behavior}_duration", 0))
                            row.append(f"{duration:.2f}")
                        
                        # Add blank column between Duration and Frequency sections
                        row.append('')
                        
                        # Add frequency values for each behavior
                        for behavior in behaviors_list:
                            # Get count and ensure it's an integer
                            count = int(interval.get(f"{behavior}_count", 0))
                            row.append(str(count))
                        
                        # FIX: Add blank column before additional metrics
                        if total_time_metrics:
                            row.append('')  # Blank column before metrics
                            
                            # Add total time metrics
                            for metric in total_time_metrics:
                                metric_name = metric["name"]
                                key = f"{metric_name.lower().replace(' ', '_')}"
                                value = float(interval.get(key, 0))
                                row.append(f"{value:.2f}")
                        
                        writer.writerow(row)
                    
                    # Add an empty row between animals for readability
                    writer.writerow([])
            
            self.logger.info(f"Successfully exported interval-based summary table to {file_path}")
            return True
        except Exception as e:
            error_msg = f"Failed to export interval summary: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False