# models/analysis_model.py - Enhanced for automatic summary generation and correct behavior analysis
import csv
import logging
import os
import pandas as pd
import numpy as np
import re
from PySide6.QtCore import QObject, Signal, Slot

class AnalysisModel(QObject):
    """
    Model for analyzing multiple annotation files and generating summary statistics.
    
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
        
        # List of default behaviors to track (for consistent ordering)
        self._default_behaviors = [
            "Attack bites", "Sideways threats", "Tail rattles", "Chasing",
            "Social contact", "Self-grooming", "Locomotion", "Rearing"
        ]
        
        # List of aggressive behaviors for total aggression calculation
        self._aggressive_behaviors = [
            "Attack bites", "Sideways threats", "Tail rattles", "Chasing"
        ]
        
        # List of aggressive behaviors excluding tail rattles
        self._aggressive_behaviors_no_tail = [
            "Attack bites", "Sideways threats", "Chasing"
        ]
        
        # Initialize behaviors list with defaults (will be extended with custom behaviors)
        self._behaviors = self._default_behaviors.copy()
        
        # Dictionary to track all custom behaviors found across files
        self._custom_behaviors = set()

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
                
                # Skip RecordingStart events as they're not actual behaviors
                if 'RecordingStart' in unique_behaviors:
                    unique_behaviors.remove('RecordingStart')
                
                # Skip "Behavior" (it's likely from the summary header if it got included)
                if 'Behavior' in unique_behaviors:
                    unique_behaviors.remove('Behavior')
                    self.logger.warning("Found 'Behavior' as an event - this is likely an error in the CSV parsing")
                
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
                # Store duration and frequency directly from summary data
                results[f"{behavior}_duration"] = metrics['duration']
                results[f"{behavior}_count"] = metrics['frequency']
                
                self.logger.debug(f"Using summary data: {behavior} - Duration: {metrics['duration']}, Frequency: {metrics['frequency']}")
            
            # Fill in any missing behaviors with zeros
            for behavior in self._behaviors:
                if f"{behavior}_duration" not in results:
                    results[f"{behavior}_duration"] = 0.0
                    results[f"{behavior}_count"] = 0
            
            # If we have raw event data, calculate the special metrics (only need raw data for these)
            if not df.empty:
                # Calculate attack latency (time to first attack bite)
                attack_latency = self._calculate_attack_latency(df, test_duration)
                results["attack_latency"] = attack_latency
                self.logger.debug(f"Attack latency: {attack_latency:.2f}s")
                
                # Calculate total aggression (accounting for overlaps)
                total_aggression = self._calculate_total_aggression(df, self._aggressive_behaviors)
                results["total_aggression"] = total_aggression
                self.logger.debug(f"Total aggression: {total_aggression:.2f}s")
                
                # Calculate total aggression without tail rattles
                total_aggression_no_tail = self._calculate_total_aggression(df, self._aggressive_behaviors_no_tail)
                results["total_aggression_no_tail"] = total_aggression_no_tail
                self.logger.debug(f"Total aggression (no tail): {total_aggression_no_tail:.2f}s")
            else:
                # Use sensible defaults or try to derive from summary data
                # For attack latency: use test_duration if no Attack bites or use zero if Attack bites found
                if "Attack bites" in summary_data and summary_data["Attack bites"]["frequency"] > 0:
                    # We have attack bites but no raw data - use a sentinel value or estimate
                    results["attack_latency"] = 0.0
                else:
                    results["attack_latency"] = test_duration
                
                # For aggression metrics: sum durations of aggressive behaviors if possible
                total_aggression = 0.0
                total_aggression_no_tail = 0.0
                
                for behavior in self._aggressive_behaviors:
                    if behavior in summary_data:
                        total_aggression += summary_data[behavior]["duration"]
                
                for behavior in self._aggressive_behaviors_no_tail:
                    if behavior in summary_data:
                        total_aggression_no_tail += summary_data[behavior]["duration"]
                
                results["total_aggression"] = total_aggression
                results["total_aggression_no_tail"] = total_aggression_no_tail
            
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
            
            # Calculate attack latency (time to first attack bite)
            attack_latency = self._calculate_attack_latency(df, test_duration)
            results["attack_latency"] = attack_latency
            self.logger.info(f"Attack latency: {attack_latency:.2f}s")
            
            # Calculate total aggression (accounting for overlaps)
            total_aggression = self._calculate_total_aggression(df, self._aggressive_behaviors)
            results["total_aggression"] = total_aggression
            self.logger.debug(f"Total aggression: {total_aggression:.2f}s")
            
            # Calculate total aggression without tail rattles
            total_aggression_no_tail = self._calculate_total_aggression(df, self._aggressive_behaviors_no_tail)
            results["total_aggression_no_tail"] = total_aggression_no_tail
            self.logger.debug(f"Total aggression (no tail): {total_aggression_no_tail:.2f}s")
            
            # Store results
            self._results[file_path] = results
            
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
    
    def _calculate_attack_latency(self, df, test_duration):
        """
        Calculate the latency to first attack bite.
        If no attack bites are observed, returns the test duration.
        
        Args:
            df (pd.DataFrame): Annotation data
            test_duration (float): Test duration in seconds
            
        Returns:
            float: Attack latency in seconds
        """
        try:
            # Ensure df is not empty
            if df.empty:
                self.logger.debug(f"Empty dataframe, using test duration as attack latency: {test_duration}s")
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
            
            # Find Attack bites events and sort by onset time
            attack_bites = df[df['Event'] == 'Attack bites'].sort_values('Onset')
            
            # If no attack bites, return test duration
            if attack_bites.empty:
                self.logger.debug(f"No Attack bites found, using test duration: {test_duration}s")
                return test_duration
            
            # Log all RecordingStart events for debugging
            self.logger.info(f"ATTACK LATENCY CALCULATION DETAILS:")
            self.logger.info(f"  Found {len(attack_bites)} Attack bites events")
            self.logger.info(f"  Found {len(recording_starts)} RecordingStart events")
            
            if not recording_starts.empty:
                for i, rs in recording_starts.iterrows():
                    self.logger.info(f"  RecordingStart #{i}: {rs['Onset']}s")
            
            if not attack_bites.empty:
                self.logger.info(f"  All Attack bites onsets: {list(attack_bites['Onset'])}")
                min_attack_time = attack_bites['Onset'].min()
                self.logger.info(f"  First Attack bites onset: {min_attack_time}s (type: {type(min_attack_time)})")
            
            # Handle the case with multiple RecordingStart events
            if len(recording_starts) > 1:
                self.logger.info(f"  Multiple RecordingStart events detected - determining best match")
                
                # Get first Attack bite time
                first_attack_time = float(attack_bites['Onset'].min())
                
                # Find the RecordingStart that comes before this attack bite
                # Sort RecordingStarts by time and find the last one that's before the first attack
                valid_starts = recording_starts[recording_starts['Onset'] < first_attack_time]
                
                if not valid_starts.empty:
                    # Use the latest RecordingStart before the first attack
                    start_time = float(valid_starts['Onset'].max())
                    self.logger.info(f"  Using RecordingStart at {start_time}s (latest before first attack)")
                else:
                    # If no RecordingStart is before the first attack, use the earliest RecordingStart
                    # This is a fallback that shouldn't normally happen with valid data
                    start_time = float(recording_starts['Onset'].min())
                    self.logger.info(f"  No RecordingStart before first attack! Using earliest at {start_time}s")
            elif not recording_starts.empty:
                # Just one RecordingStart - use it directly
                start_time = float(recording_starts['Onset'].iloc[0])
                self.logger.info(f"  Using single RecordingStart at {start_time}s")
            else:
                # No RecordingStart found - fall back to earliest event time
                start_time = float(df['Onset'].min())
                self.logger.info(f"  No RecordingStart events! Using earliest event time: {start_time}s")
            
            # Calculate latency with explicit float conversion
            first_attack_time = float(attack_bites['Onset'].min())
            latency = first_attack_time - start_time
            
            # Log the exact calculation
            self.logger.info(f"  Calculation: {first_attack_time} - {start_time} = {latency}")
            
            # Ensure non-negative value (should not happen with proper data)
            if latency < 0:
                self.logger.warning(f"  Calculated negative latency ({latency}s)! This suggests data ordering issues.")
                latency = max(0, latency)
            
            self.logger.info(f"FINAL ATTACK LATENCY: {latency}s")
            return latency
                
        except Exception as e:
            self.logger.warning(f"Error in attack latency calculation: {str(e)}", exc_info=True)
            return test_duration
    
    def _calculate_total_aggression(self, df, aggression_behaviors):
        """
        Calculate the total aggression time, accounting for overlaps.
        Uses a timeline approach to handle overlapping behaviors.
        
        Args:
            df (pd.DataFrame): Annotation data
            aggression_behaviors (list): List of behaviors to include
            
        Returns:
            float: Total aggression duration in seconds
        """
        try:
            # Ensure the dataframe is not empty
            if df.empty:
                return 0
            
            # Filter for aggressive behaviors
            aggression_df = df[df['Event'].isin(aggression_behaviors)].copy()
            
            # If no aggressive behaviors found, return 0
            if aggression_df.empty:
                return 0
            
            # Convert onset/offset to numeric to ensure proper calculations
            try:
                # Use .loc to avoid SettingWithCopyWarning
                aggression_df.loc[:, 'Onset'] = pd.to_numeric(aggression_df['Onset'], errors='coerce')
                aggression_df.loc[:, 'Offset'] = pd.to_numeric(aggression_df['Offset'], errors='coerce')
                
                # Drop any rows with NaN values after conversion
                aggression_df = aggression_df.dropna(subset=['Onset', 'Offset'])
                
                # Validate that Offset >= Onset for each row
                invalid_rows = aggression_df[aggression_df['Offset'] < aggression_df['Onset']]
                if not invalid_rows.empty:
                    self.logger.warning(f"Found {len(invalid_rows)} aggressive behavior events with Offset < Onset")
                    # Remove invalid rows
                    aggression_df = aggression_df[aggression_df['Offset'] >= aggression_df['Onset']]
            except Exception as e:
                self.logger.warning(f"Error converting aggression times to numeric: {str(e)}")
                return 0
            
            # If after cleaning we have no valid rows, return 0
            if aggression_df.empty:
                return 0
            
            # Timeline approach to account for overlaps
            # Create a list of events (start and end points)
            events = []
            for _, row in aggression_df.iterrows():
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
            self.logger.warning(f"Error calculating total aggression: {str(e)}")
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
                
                # Log special metrics
                self.logger.info(f"  Attack Latency: {metrics.get('attack_latency', 0):.2f}s")
                self.logger.info(f"  Total Aggression: {metrics.get('total_aggression', 0):.2f}s")
                self.logger.info(f"  Total Aggression (no tail): {metrics.get('total_aggression_no_tail', 0):.2f}s")
            
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
            dict: Analysis results
        """
        return self._results
    
    def export_summary_csv(self, file_path):
        """
        Export the summary table to CSV.
        
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
                header_row = [''] + ['Duration'] + [''] * num_behaviors + ['Frequency'] + [''] * num_behaviors + [''] * 3
                writer.writerow(header_row)
                
                # Write column headers
                column_headers = ['animal_id']
                
                # All behaviors plus an empty spacer at the end
                behaviors_with_spacer = behaviors_list + ['']
                
                # Add duration behavior headers
                column_headers.extend(behaviors_with_spacer)
                
                # Add frequency behavior headers
                column_headers.extend(behaviors_with_spacer)
                
                # Add special metrics
                column_headers.extend(["Attack Latency", "Total Aggression", "Total Aggression(without tail-rattles)"])
                
                writer.writerow(column_headers)
                
                # Log the structure of the summary table
                self.logger.info(f"Summary table structure: {len(behaviors_list)} behaviors + 3 special metrics")
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
                    
                    # Add empty spacer cell
                    row.append("")
                    
                    # Add frequency values for each behavior
                    for behavior in behaviors_list:
                        # Get count and ensure it's an integer
                        count = int(metrics.get(f"{behavior}_count", 0))
                        self.logger.debug(f"  {behavior} count: {count}")
                        row.append(str(count))
                    
                    # Add empty spacer cell
                    row.append("")
                    
                    # Add special metrics
                    attack_latency = float(metrics.get('attack_latency', metrics.get('test_duration', 300)))
                    total_aggression = float(metrics.get('total_aggression', 0))
                    total_aggression_no_tail = float(metrics.get('total_aggression_no_tail', 0))
                    
                    # Log special metrics for validation
                    self.logger.info(f"  Attack Latency: {attack_latency:.2f}s")
                    self.logger.info(f"  Total Aggression: {total_aggression:.2f}s")
                    self.logger.info(f"  Total Aggression (no tail): {total_aggression_no_tail:.2f}s")
                    
                    row.append(f"{attack_latency:.2f}")
                    row.append(f"{total_aggression:.2f}")
                    row.append(f"{total_aggression_no_tail:.2f}")
                    
                    writer.writerow(row)
            
            self.logger.info(f"Successfully exported summary table to {file_path}")
            return True
        except Exception as e:
            error_msg = f"Failed to export summary: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False