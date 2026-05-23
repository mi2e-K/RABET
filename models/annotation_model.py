# models/annotation_model.py - Enhanced with high time accuracy for keypresses
import csv
import logging
import time
from PySide6.QtCore import QObject, Signal

from version import __version__ as RABET_VERSION

# Schema version stamped into exported CSV files. Bump this when the file
# layout changes in a way that breaks older readers.
ANNOTATION_CSV_SCHEMA = "v1"

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

        Design note: ``_active_events`` is intentionally a flat
        ``Dict[str, BehaviorEvent]`` rather than a stack of events per key.
        Behavioural coding workflows tag at most one event per key at a
        time (one mouse cannot be "attacking" twice simultaneously) and the
        flat dict keeps the timeline-rendering / rewind-handling code
        substantially simpler. A duplicate press while the same key is
        still active is therefore silently ignored after a debug-level
        log line.

        Args:
            key (str): Key character
            timestamp (int): Onset timestamp in milliseconds

        Returns:
            bool: True if event was started successfully, False otherwise
        """
        # Check if key is mapped
        behavior = self._action_map_model.get_behavior(key)
        if not behavior:
            self.logger.debug(f"Ignoring keypress: '{key}' is not mapped to a behavior")
            return False

        # Reject a duplicate press for an already-active key. ``debug`` level
        # so the log file is not flooded by accidental retriggers.
        if key in self._active_events:
            # Promoted to WARNING (1.3.3+) so the log line is visible in
            # release builds. Hitting this branch in real-time mode means
            # the OS released-and-re-pressed the key without the in-between
            # key-up reaching RABET; in FBF mode the press is supposed to
            # land in end_event instead, so we should never get here.
            self.logger.warning(
                f"start_event: key '{key}' already has an active event "
                f"(behavior='{self._active_events[key].behavior}', "
                f"onset={self._active_events[key].onset}ms); ignoring duplicate press"
            )
            return False

        # Get monotonic high-precision time (immune to wall-clock jumps / NTP)
        system_time = time.monotonic()
        
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

        Structurally fail-safe (1.3.3+): the active-events dict is cleared
        inside a ``finally`` block so any exception during offset / duration
        calculation cannot leave a "stuck" entry behind. Bugs that used to
        manifest as "FBF keeps not ending the event no matter how many
        times I press" are now contained — at worst the event is finalised
        with a best-effort offset rather than stranded in the active dict.

        Args:
            key (str): Key character
            timestamp (int): Offset timestamp in milliseconds

        Returns:
            bool: True if event was ended successfully (or finalised on a
                  best-effort basis), False if no active event existed.
        """
        if key not in self._active_events:
            self.logger.debug(f"No active event for key '{key}'; nothing to end")
            return False

        event = self._active_events[key]
        finalised = False
        try:
            # Get monotonic high-precision time (immune to wall-clock
            # jumps / NTP).
            system_time = time.monotonic()
            event.system_offset_time = system_time

            # Calculate actual duration using high-precision system time.
            # system_onset_time should always be set by start_event but the
            # try/except keeps a stale event from blocking the dict cleanup
            # below.
            try:
                system_duration_ms = int(
                    (event.system_offset_time - event.system_onset_time) * 1000
                )
            except (TypeError, AttributeError):
                self.logger.exception(
                    f"end_event: could not compute system duration for key '{key}'"
                )
                system_duration_ms = 0

            frame_duration_ms = self.get_frame_duration() or 33

            # Use system time to calculate minimum duration - ensure at
            # least one frame.
            if system_duration_ms < frame_duration_ms:
                event.offset = event.onset + frame_duration_ms
                self.logger.debug(
                    f"Adjusting duration from {system_duration_ms}ms to "
                    f"{frame_duration_ms}ms for key {key}"
                )
            else:
                event.offset = timestamp

            # Last-resort sanity: offset must be a finite, non-decreasing
            # number; if anything upstream produced rubbish, fall back to
            # onset + 1 frame so the event is at least exportable.
            if (
                event.offset is None
                or not isinstance(event.offset, (int, float))
                or event.offset < event.onset
            ):
                self.logger.warning(
                    f"end_event: invalid offset for key '{key}' "
                    f"(onset={event.onset}, offset={event.offset}); "
                    f"clamping to onset + frame_duration"
                )
                event.offset = event.onset + frame_duration_ms

            self._events.append(event)
            self.annotation_added.emit(event)
            finalised = True
            self.logger.debug(
                f"Ended event: {key} -> {event.behavior} at {timestamp}ms "
                f"(system time: {system_time:.6f}, duration: {event.duration}ms)"
            )
        except Exception:
            # Final safety net. Log with full traceback and try a
            # best-effort finalisation so the user does not lose the
            # event entirely.
            self.logger.exception(
                f"end_event: unexpected error finalising key '{key}'; "
                f"attempting best-effort recovery"
            )
            try:
                frame_duration_ms = self.get_frame_duration() or 33
                if event.offset is None or event.offset < event.onset:
                    event.offset = event.onset + frame_duration_ms
                if event not in self._events:
                    self._events.append(event)
                    self.annotation_added.emit(event)
                finalised = True
            except Exception:
                self.logger.exception(
                    f"end_event: best-effort recovery failed for key '{key}'; "
                    f"event will be dropped from the active dict but lost"
                )
        finally:
            # CRITICAL: always remove from active events, even if
            # finalisation raised. This is what prevents the
            # "FBF won't stop" class of bugs.
            self._active_events.pop(key, None)
            try:
                self._action_map_model.set_behavior_active(key, False)
            except Exception:
                self.logger.exception(
                    f"end_event: action_map.set_behavior_active failed for '{key}'"
                )
            self.active_events_changed.emit()

        return finalised
    
    def discard_active_event(self, key):
        """
        Discard an active (still-pressed) behavior event without recording it.

        Used when the user rewinds past the active event's onset during a
        recording session - the event is no longer meaningful and must not
        appear in the timeline or exports.

        Args:
            key (str): Key character of the active event

        Returns:
            bool: True if an active event was removed, False otherwise
        """
        if key not in self._active_events:
            return False

        discarded = self._active_events.pop(key)
        self._action_map_model.set_behavior_active(key, False)
        self.active_events_changed.emit()
        self.logger.debug(
            f"Discarded active event: {key} -> {discarded.behavior} "
            f"(onset {discarded.onset}ms)"
        )
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

        Accepts indices that address either the completed events list
        (``self._events``) or the active-events tail used by
        ``get_all_events_with_active`` (1.3.3+). When the index falls in
        the active range the in-progress event is *discarded* (same
        semantics as ``discard_active_event``) — useful for letting the
        Timeline delete an event that was never finished, e.g. after the
        FBF bug investigated in v1.3.2.

        Args:
            index (int): Index of the event to remove, in the combined
                ``_events + _active_events.values()`` layout.

        Returns:
            bool: True if removed successfully, False otherwise
        """
        if 0 <= index < len(self._events):
            event = self._events.pop(index)
            self.annotation_removed.emit(index)
            self.logger.debug(f"Removed event at index {index}: {event.behavior}")
            return True

        # 1.3.3+: index points into the active-events tail. The order is
        # ``list(self._active_events.values())`` as produced by
        # get_all_events_with_active.
        active_index = index - len(self._events)
        if 0 <= active_index < len(self._active_events):
            active_keys = list(self._active_events.keys())
            try:
                key = active_keys[active_index]
            except IndexError:
                return False
            discarded = self._active_events.pop(key, None)
            if discarded is None:
                return False
            try:
                self._action_map_model.set_behavior_active(key, False)
            except Exception:
                self.logger.exception(
                    f"remove_event: action_map.set_behavior_active failed for '{key}'"
                )
            self.annotation_removed.emit(index)
            self.active_events_changed.emit()
            self.logger.info(
                f"Discarded active event at index {index} (key={key}, "
                f"behavior={discarded.behavior}, onset={discarded.onset}ms) "
                f"via Timeline delete"
            )
            return True

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
            all_behaviors = []
            seen_behaviors = set()
            action_map = self._action_map_model.get_all_mappings()
            for key, behavior in action_map.items():
                if behavior not in seen_behaviors:
                    all_behaviors.append(behavior)
                    seen_behaviors.add(behavior)
            
            with open(csv_path, 'w', newline='') as f:
                writer = csv.writer(f)

                # Part 1: Metadata section with provenance and schema info so
                # third-party tools can detect the producing application's
                # version and the file layout.
                writer.writerow(['Metadata'])
                writer.writerow(['RABET Version', RABET_VERSION])
                writer.writerow(['Format Schema', ANNOTATION_CSV_SCHEMA])

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
        Import annotations from CSV with improved format handling.
        
        Args:
            csv_path (str): Path to the CSV file
            
        Returns:
            bool: True if imported successfully, False otherwise
        """
        try:
            self.logger.info(f"Importing annotations from: {csv_path}")
            
            # Clear existing events
            self.clear_events()
            
            imported_count = 0
            skipped_count = 0
            in_metadata = True  # Assume file might start with metadata
            
            with open(csv_path, 'r', newline='') as f:
                reader = csv.reader(f)
                
                # Track if we've found the header row
                header_found = False
                header_format = None  # 'simple' or 'detailed'
                
                for row_num, row in enumerate(reader):
                    # Skip completely empty rows
                    if not row or all(cell.strip() == '' for cell in row):
                        continue
                    
                    # Skip rows with insufficient data
                    if len(row) < 2:
                        self.logger.debug(f"Skipping row {row_num + 1}: insufficient columns")
                        continue
                    
                    # Check if this is a metadata row (single value rows or special markers)
                    if len(row) == 1 or row[0].lower() in ['metadata', 'test duration', 'events']:
                        in_metadata = True
                        continue
                    
                    # Detect header row
                    if not header_found:
                        # Check for header patterns
                        first_col = row[0].lower()
                        if first_col in ['event', 'behavior', 'key']:
                            header_found = True
                            in_metadata = False
                            
                            # Determine format based on number of columns
                            if len(row) >= 5:
                                header_format = 'detailed'  # [Key, Behavior, Onset, Offset, Duration]
                                self.logger.info("Detected detailed format (5+ columns)")
                            else:
                                header_format = 'simple'  # [Event/Behavior, Onset, Offset]
                                self.logger.info("Detected simple format (3 columns)")
                            continue
                    
                    # Check if we've reached the summary section
                    if row[0].lower() == 'behavior' and len(row) >= 2 and any('duration' in str(x).lower() for x in row):
                        self.logger.info(f"Reached summary section at row {row_num + 1}, stopping data import")
                        break
                    
                    # If we haven't found a header yet, try to parse as data
                    if not header_found and not in_metadata:
                        # Try to detect if this looks like data
                        try:
                            # Check if the second or third column could be a timestamp
                            if len(row) >= 2:
                                float(row[1])  # Try to parse as number
                                header_found = True  # Assume we're in data section
                                header_format = 'simple' if len(row) < 5 else 'detailed'
                                self.logger.info(f"No header found, assuming data starts at row {row_num + 1}")
                        except ValueError:
                            continue
                    
                    # Parse data row
                    try:
                        # Skip if still in metadata or no header found
                        if in_metadata or not header_found:
                            continue
                        
                        # Parse based on detected or assumed format
                        if header_format == 'detailed' and len(row) >= 5:
                            # Format: [Key, Behavior, Onset, Offset, Duration]
                            key = row[0].strip()
                            behavior = row[1].strip()
                            
                            # Convert timestamps
                            onset_text = row[2].strip()
                            onset = self._parse_timestamp(onset_text)
                            
                            offset_text = row[3].strip() if row[3].strip() else None
                            offset = self._parse_timestamp(offset_text) if offset_text else None
                            
                        else:
                            # Format: [Event/Behavior, Onset, Offset]
                            behavior = row[0].strip()
                            # Look up the key from the action map instead of using 'I'
                            key = self._find_key_for_behavior(behavior)
                            
                            # Convert timestamps
                            onset_text = row[1].strip()
                            onset = self._parse_timestamp(onset_text)
                            
                            offset_text = row[2].strip() if len(row) > 2 and row[2].strip() else None
                            offset = self._parse_timestamp(offset_text) if offset_text else None
                        
                        # Validate timestamps
                        if onset is None:
                            self.logger.warning(f"Row {row_num + 1}: Invalid onset timestamp: {onset_text}")
                            skipped_count += 1
                            continue
                        
                        # Ensure minimum duration if offset exists
                        if offset is not None and offset <= onset:
                            offset = onset + self.get_frame_duration()
                            self.logger.debug(f"Row {row_num + 1}: Adjusted offset to ensure minimum duration")
                        
                        # Create and add event
                        event = BehaviorEvent(key, behavior, onset, offset)
                        self._events.append(event)
                        self.annotation_added.emit(event)
                        imported_count += 1
                        
                        self.logger.debug(f"Imported: {behavior} (key={key}) at {onset}ms" + 
                                        (f" - {offset}ms" if offset else " (no offset)"))
                        
                    except (ValueError, IndexError) as e:
                        self.logger.warning(f"Row {row_num + 1}: Failed to parse - {str(e)}")
                        self.logger.debug(f"Row content: {row}")
                        skipped_count += 1
                        continue
            
            # Log import summary
            self.logger.info(f"Import complete: {imported_count} events imported, {skipped_count} rows skipped")
            
            if imported_count == 0:
                self.logger.warning("No events were imported. Check CSV format.")
                self.error_occurred.emit("No valid events found in CSV file. Please check the file format.")
                return False
                
            return True
            
        except Exception as e:
            error_msg = f"Failed to import annotations: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False

    def _parse_timestamp(self, timestamp_text):
        """
        Parse timestamp from various formats.
        
        Args:
            timestamp_text (str): Timestamp as string
            
        Returns:
            int: Timestamp in milliseconds or None if invalid
        """
        if not timestamp_text:
            return None
            
        try:
            # Remove any whitespace
            timestamp_text = timestamp_text.strip()
            
            # Check if it contains a decimal (likely seconds)
            if '.' in timestamp_text:
                # Parse as seconds with decimal
                return int(float(timestamp_text) * 1000)
            else:
                # Parse as milliseconds
                return int(timestamp_text)
        except (ValueError, TypeError):
            return None

    # Add this method to the AnnotationModel class in annotation_model.py

    def _find_key_for_behavior(self, behavior):
        """
        Find the key associated with a behavior name in the action map.

        Args:
            behavior (str): Behavior name

        Returns:
            str: Key associated with the behavior, or an empty string if no
                mapping exists. Empty-key events are still tracked and
                exported correctly; only the on-timeline key glyph is
                suppressed. Returning an empty string (instead of the old
                hardcoded ``'I'``) avoids accidental collisions when the
                user later maps ``'I'`` to a real behaviour.
        """
        mappings = self._action_map_model.get_all_mappings()

        for key, mapped_behavior in mappings.items():
            if mapped_behavior.lower() == behavior.lower():
                return key

        self.logger.debug(
            f"No key mapping found for behavior '{behavior}', importing with empty key"
        )
        return ''
