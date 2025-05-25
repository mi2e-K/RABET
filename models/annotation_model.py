# models/annotation_model.py - Enhanced with high time accuracy for keypresses
import csv
import logging
import json
import time
from PySide6.QtCore import QObject, Signal, Slot

class BehaviorEvent:
    """
    Represents a single behavior event with onset, offset and duration.
    """
    
    def __init__(self, key, behavior, onset, offset=None, system_onset_time=None, system_offset_time=None):
        """
        Initialize a behavior event.
        
        Args:
            key (str): Key character
            behavior (str): Behavior label
            onset (int): Onset timestamp in milliseconds
            offset (int, optional): Offset timestamp in milliseconds
            system_onset_time (float, optional): System time of onset (high precision)
            system_offset_time (float, optional): System time of offset (high precision)
        """
        self.key = key
        self.behavior = behavior
        self.onset = onset
        self.offset = offset
        
        # Store high-precision system times for calculating minimum durations
        self.system_onset_time = system_onset_time
        self.system_offset_time = system_offset_time
        
    @property
    def duration(self):
        """
        Calculate duration of the event.
        
        Returns:
            int: Duration in milliseconds or 0 if offset is not set
        """
        if self.offset is None:
            return 0
        return self.offset - self.onset
    
    @property
    def system_duration(self):
        """
        Calculate high-precision duration using system time.
        
        Returns:
            float: Duration in seconds based on system time or 0 if not available
        """
        if self.system_onset_time is None or self.system_offset_time is None:
            return 0
        return self.system_offset_time - self.system_onset_time
    
    def to_dict(self):
        """
        Convert event to dictionary.
        
        Returns:
            dict: Dictionary representation of the event
        """
        return {
            'key': self.key,
            'behavior': self.behavior,
            'onset': self.onset,
            'offset': self.offset,
            'duration': self.duration,
            'system_onset_time': self.system_onset_time,
            'system_offset_time': self.system_offset_time
        }

class AnnotationModel(QObject):
    """
    Model for managing behavior annotations.
    
    Signals:
        annotation_added: Emitted when a new annotation is added
        annotation_updated: Emitted when an annotation is updated
        annotation_removed: Emitted when an annotation is removed
        annotations_cleared: Emitted when all annotations are cleared
        active_events_changed: Emitted when active events change
        error_occurred: Emitted when an error occurs
    """
    
    annotation_added = Signal(object)  # BehaviorEvent object
    annotation_updated = Signal(object)  # BehaviorEvent object
    annotation_removed = Signal(int)  # Index of removed event
    annotations_cleared = Signal()
    active_events_changed = Signal()  # New signal for active events changes
    error_occurred = Signal(str)
    
    def __init__(self, action_map_model, video_model=None):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing AnnotationModel")
        
        self._action_map_model = action_map_model
        self._video_model = video_model  # Reference to video model for frame rate info
        self._events = []  # List of BehaviorEvent objects
        self._active_events = {}  # Key -> event mapping for currently active events
        
        # Default frame duration if we can't get it from video model
        self._default_frame_duration_ms = 33  # ~30fps (33ms per frame)
        
        # Store test duration information for recording sessions
        self._test_duration = None  # Duration in seconds
    
    def set_video_model(self, video_model):
        """
        Set reference to video model for frame rate information.
        
        Args:
            video_model: VideoModel object
        """
        self._video_model = video_model
        
    def get_frame_duration(self):
        """
        Get the duration of a single frame in milliseconds.
        
        Returns:
            int: Frame duration in milliseconds
        """
        if self._video_model and hasattr(self._video_model, '_frame_duration_ms'):
            return self._video_model._frame_duration_ms
        return self._default_frame_duration_ms
        
    def start_event(self, key, timestamp):
        """
        Start a new behavior event.
        
        Args:
            key (str): Key character
            timestamp (int): Onset timestamp in milliseconds
            
        Returns:
            bool: True if event was started successfully, False otherwise
        """
        # Check if key is mapped
        behavior = self._action_map_model.get_behavior(key)
        if not behavior:
            self.logger.warning(f"Key not mapped: {key}")
            return False
        
        # Check if event is already active
        if key in self._active_events:
            self.logger.warning(f"Event already active for key: {key}")
            return False
        
        # Get high-precision system time
        system_time = time.time()
        
        # Create and store new event
        self.logger.debug(f"Starting event: {key} -> {behavior} at {timestamp}ms (system time: {system_time:.6f})")
        event = BehaviorEvent(key, behavior, timestamp, system_onset_time=system_time)
        self._active_events[key] = event
        
        # Set behavior as active in action map
        self._action_map_model.set_behavior_active(key, True)
        
        # Emit signal for active event changes
        self.active_events_changed.emit()
        
        return True
    
    def end_event(self, key, timestamp):
        """
        End an active behavior event.
        
        Args:
            key (str): Key character
            timestamp (int): Offset timestamp in milliseconds
            
        Returns:
            bool: True if event was ended successfully, False otherwise
        """
        # Check if event is active
        if key not in self._active_events:
            self.logger.warning(f"No active event for key: {key}")
            return False
        
        # Get high-precision system time
        system_time = time.time()
        
        # Update event with offset time
        event = self._active_events[key]
        event.system_offset_time = system_time
        
        # Calculate actual duration using high-precision system time
        system_duration_ms = int((event.system_offset_time - event.system_onset_time) * 1000)
        
        # Get frame duration for minimum duration enforcement
        frame_duration_ms = self.get_frame_duration()
        
        # Use system time to calculate minimum duration - ensure at least one frame
        if system_duration_ms < frame_duration_ms:
            # Use at least one frame duration
            adjusted_timestamp = event.onset + frame_duration_ms
            self.logger.debug(f"Adjusting duration from {system_duration_ms}ms to {frame_duration_ms}ms for key {key}")
            event.offset = adjusted_timestamp
        else:
            # Use the provided timestamp if the duration is already sufficient
            event.offset = timestamp
            
        # Add to events list and emit signal
        self._events.append(event)
        self.annotation_added.emit(event)
        
        # Remove from active events
        del self._active_events[key]
        
        # Set behavior as inactive in action map
        self._action_map_model.set_behavior_active(key, False)
        
        # Emit signal for active event changes
        self.active_events_changed.emit()
        
        self.logger.debug(f"Ended event: {key} -> {event.behavior} at {timestamp}ms (system time: {system_time:.6f}, duration: {event.duration}ms)")
        
        return True
    
    def add_recording_start_event(self, event):
        """
        Add a RecordingStart event.
        
        Args:
            event (BehaviorEvent): RecordingStart event
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Ensure it's a RecordingStart event
            if event.behavior != "RecordingStart":
                return False
                
            # Add to events list and emit signal
            self._events.append(event)
            self.annotation_added.emit(event)
            
            self.logger.debug(f"Added RecordingStart event at {event.onset}ms")
            return True
        except Exception as e:
            self.logger.error(f"Failed to add RecordingStart event: {str(e)}", exc_info=True)
            return False
    
    def update_event(self, index, onset=None, offset=None):
        """
        Update an existing event.
        
        Args:
            index (int): Index of the event to update
            onset (int, optional): New onset timestamp
            offset (int, optional): New offset timestamp
            
        Returns:
            bool: True if updated successfully, False otherwise
        """
        if 0 <= index < len(self._events):
            event = self._events[index]
            
            if onset is not None:
                event.onset = onset
            if offset is not None:
                event.offset = offset
                
            self.annotation_updated.emit(event)
            self.logger.debug(f"Updated event at index {index}: {event.behavior} ({event.onset}ms - {event.offset}ms)")
            return True
        else:
            self.logger.warning(f"Invalid event index: {index}")
            return False
    
    def remove_event(self, index):
        """
        Remove an event.
        
        Args:
            index (int): Index of the event to remove
            
        Returns:
            bool: True if removed successfully, False otherwise
        """
        if 0 <= index < len(self._events):
            event = self._events.pop(index)
            self.annotation_removed.emit(index)
            self.logger.debug(f"Removed event at index {index}: {event.behavior}")
            return True
        else:
            self.logger.warning(f"Invalid event index: {index}")
            return False
    
    def get_event(self, index):
        """
        Get event at index.
        
        Args:
            index (int): Index of the event
            
        Returns:
            BehaviorEvent: Event object or None if index is invalid
        """
        if 0 <= index < len(self._events):
            return self._events[index]
        return None
    
    def get_all_events(self):
        """
        Get all events.
        
        Returns:
            list: List of BehaviorEvent objects
        """
        return self._events.copy()
    
    def get_all_events_with_active(self):
        """
        Get all events including active (ongoing) ones.
        
        Returns:
            list: List of all BehaviorEvent objects including active ones
        """
        all_events = self._events.copy()
        all_events.extend(self._active_events.values())
        return all_events
    
    def get_active_events(self):
        """
        Get all active events.
        
        Returns:
            dict: Dictionary of key -> BehaviorEvent mappings
        """
        return self._active_events.copy()
    
    def get_behavior_statistics(self):
        """
        Calculate statistics for each behavior.
        
        Returns:
            dict: Dictionary of behavior -> statistics
        """
        stats = {}
        
        for event in self._events:
            behavior = event.behavior
            
            if behavior not in stats:
                stats[behavior] = {
                    'count': 0,
                    'total_duration': 0,
                    'durations': []
                }
            
            stats[behavior]['count'] += 1
            stats[behavior]['total_duration'] += event.duration
            stats[behavior]['durations'].append(event.duration)
        
        # Calculate mean durations
        for behavior, data in stats.items():
            if data['count'] > 0:
                data['mean_duration'] = data['total_duration'] / data['count']
            else:
                data['mean_duration'] = 0
        
        return stats
    
    def clear_events(self):
        """Clear all events."""
        self._events = []
        self._active_events = {}
        self._action_map_model.clear_active_behaviors()
        self.annotations_cleared.emit()
        self.logger.info("All annotations cleared")
    
    def set_test_duration(self, duration_seconds):
        """
        Set the test duration for the current recording session.
        
        Args:
            duration_seconds (int): Duration in seconds
        """
        self._test_duration = duration_seconds
        self.logger.debug(f"Test duration set to {duration_seconds} seconds")


    def export_to_csv(self, csv_path, include_header=True):
        """
        Export annotations to CSV with a summary table and metadata.
        
        Args:
            csv_path (str): Path to save the CSV file
            include_header (bool, optional): Whether to include header row
            
        Returns:
            bool: True if exported successfully, False otherwise
        """
        try:
            self.logger.info(f"Exporting annotations to: {csv_path}")
            
            # Generate behavior statistics
            behavior_stats = self.get_behavior_statistics()
            
            # Get all behaviors from action map (including ones with zero occurrences)
            all_behaviors = set()
            action_map = self._action_map_model.get_all_mappings()
            for key, behavior in action_map.items():
                all_behaviors.add(behavior)
            
            with open(csv_path, 'w', newline='') as f:
                writer = csv.writer(f)
                
                # Part 1: Metadata section with only essential information
                writer.writerow(['Metadata'])
                
                # Include test duration if available
                test_duration_secs = self._test_duration if self._test_duration is not None else 0
                writer.writerow(['Test Duration (seconds)', f"{test_duration_secs}"])
                
                # Empty row as separator
                writer.writerow([])
                
                # Part 2: Write event log (without redundant "Events" section header)
                # Write header row
                if include_header:
                    writer.writerow(['Event', 'Onset', 'Offset'])
                
                # Write data rows - convert milliseconds to seconds with 4 decimal places
                for event in self._events:
                    onset_sec = event.onset / 1000
                    offset_sec = event.offset / 1000 if event.offset is not None else None
                    
                    writer.writerow([
                        event.behavior,
                        f"{onset_sec:.4f}",
                        f"{offset_sec:.4f}" if offset_sec is not None else ""
                    ])
                
                # Part 3: Empty row as separator
                writer.writerow([])
                
                # Part 4: Summary table
                # Write summary header
                writer.writerow(['Behavior', 'Duration', 'Frequency'])
                
                # Write summary data for each behavior, ordered by the action map
                for behavior in all_behaviors:
                    if behavior == "RecordingStart":
                        continue  # Skip RecordingStart in the summary
                        
                    stats = behavior_stats.get(behavior, {})
                    count = stats.get('count', 0)
                    # Convert milliseconds to seconds for duration
                    duration = stats.get('total_duration', 0) / 1000 if stats else 0
                    
                    writer.writerow([
                        behavior,
                        f"{duration:.2f}",
                        count
                    ])
                        
            return True
        except Exception as e:
            error_msg = f"Failed to export annotations: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def import_from_csv(self, csv_path):
        """
        Import annotations from CSV.
        
        Args:
            csv_path (str): Path to the CSV file
            
        Returns:
            bool: True if imported successfully, False otherwise
        """
        try:
            self.logger.info(f"Importing annotations from: {csv_path}")
            
            # Clear existing events
            self.clear_events()
            
            with open(csv_path, 'r', newline='') as f:
                reader = csv.reader(f)
                
                # Detect header row
                first_row = next(reader)
                if first_row[0].lower() == 'event' or first_row[0].lower() == 'behavior' or first_row[0].lower() == 'key':
                    # First row was header, continue with data
                    pass
                else:
                    # First row was data, rewind and process it
                    f.seek(0)
                    reader = csv.reader(f)
                
                # Process data rows
                for row in reader:
                    # Skip empty rows or rows with less than 2 values (might be separators or summary)
                    if not row or len(row) < 2:
                        break  # Stop when we hit the separator row between events and summary
                        
                    # Check remaining rows for expected column headers for summary section
                    if row[0].lower() == 'behavior' and 'duration' in [x.lower() for x in row]:
                        break  # Stop when we hit the summary header
                    
                    try:
                        # Format may be [Event/Behavior, Onset, Offset] or [Key, Behavior, Onset, Offset, Duration]
                        # Handle both formats
                        if len(row) >= 5:  # [Key, Behavior, Onset, Offset, Duration]
                            key = row[0]
                            behavior = row[1]
                            
                            # Convert timestamp format
                            onset_text = row[2]
                            if '.' in onset_text:  # Assume seconds with decimal
                                onset = int(float(onset_text) * 1000)
                            else:  # Assume milliseconds
                                onset = int(onset_text)
                                
                            offset_text = row[3] if row[3] else None
                            if offset_text:
                                if '.' in offset_text:  # Assume seconds with decimal
                                    offset = int(float(offset_text) * 1000)
                                else:  # Assume milliseconds
                                    offset = int(offset_text)
                            else:
                                offset = None
                        else:  # [Event/Behavior, Onset, Offset]
                            behavior = row[0]
                            # Use special key for imported events
                            key = "I"
                            
                            # Convert timestamp format
                            onset_text = row[1]
                            if '.' in onset_text:  # Assume seconds with decimal
                                onset = int(float(onset_text) * 1000)
                            else:  # Assume milliseconds
                                onset = int(onset_text)
                                
                            offset_text = row[2] if len(row) > 2 and row[2] else None
                            if offset_text:
                                if '.' in offset_text:  # Assume seconds with decimal
                                    offset = int(float(offset_text) * 1000)
                                else:  # Assume milliseconds
                                    offset = int(offset_text)
                            else:
                                offset = None
                        
                        # Ensure we have a minimum duration (1 frame) for imported events
                        if offset is not None and offset <= onset:
                            offset = onset + self.get_frame_duration()
                        
                        # Create and add event
                        event = BehaviorEvent(key, behavior, onset, offset)
                        self._events.append(event)
                        self.annotation_added.emit(event)
                    except (ValueError, IndexError) as e:
                        self.logger.warning(f"Skipping row due to format error: {row}, error: {e}")
                        continue
                    
            return True
        except Exception as e:
            error_msg = f"Failed to import annotations: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False