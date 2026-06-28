# models/action_map_model.py
import json
import logging
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QTimer
from utils.config_path_manager import ConfigPathManager  # Import the new class
from utils.defaults import default_action_map

class ActionMapModel(QObject):
    """
    Model for managing key-to-behavior mappings.
    
    Signals:
        map_changed: Emitted when the action map changes
        active_behaviors_changed: Emitted when active behaviors change
        error_occurred: Emitted when an error occurs
    """
    
    map_changed = Signal()
    active_behaviors_changed = Signal()  # New signal for active behavior changes
    error_occurred = Signal(str)

    mapping_added = Signal(str, str)
    mapping_updated = Signal(str, str)
    mapping_removed = Signal(str)  # Emits the behavior name
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing ActionMapModel")
        
        # Initialize config path manager
        self._config_path_manager = ConfigPathManager()
        
        # Initialize empty action map
        self._action_map = {}
        # Per-key behaviour kind: "state" (default, onset/offset duration) or
        # "point" (instantaneous, zero-duration). Stored separately from
        # ``_action_map`` so that ``get_behavior`` / ``get_all_mappings`` keep
        # returning a plain ``{key: name}`` dict — every existing reader stays
        # untouched. On disk the two are merged back into a union form (a bare
        # string for state, an object for point) by ``_serialize_map`` (1.4.0).
        self._behavior_kinds = {}
        self._active_behaviors = set()  # Currently active behaviors
        
        # Setup auto-save timer
        self._auto_save_timer = QTimer()
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.timeout.connect(self._auto_save)
        self._auto_save_pending = False
        
        # Flag to track if we've loaded successfully
        self._loaded_successfully = False
        
        # Try to load user's action map or default
        self._load_action_map()
        
        # Don't emit signals during initialization - the view will be updated
        # when the controller connects the signals
    
    def _load_action_map(self):
        """
        Load the action map. Priority:
        1. User's saved action map
        2. Default action map
        3. Create new default if nothing exists
        """
        # First, try to load user's action map
        user_map_path = self._config_path_manager.get_action_map_config_path("user_action_map.json")
        
        if user_map_path and user_map_path.exists():
            self.logger.info(f"Loading user action map from {user_map_path}")
            if self.load_from_json(user_map_path, auto_save=False, emit_signal=False):
                self.logger.info("Successfully loaded user action map")
                self._loaded_successfully = True
                return
            else:
                self.logger.warning("Failed to load user action map, trying default")
        
        # If no user map, try default
        self._try_load_default_map()
    
    def _try_load_default_map(self):
        """
        Try to load the default action map from the configs directory.
        """
        try:
            # Get path to default action map
            config_path = self._config_path_manager.get_action_map_config_path("default_action_map.json")
            
            if config_path and config_path.exists():
                self.logger.info(f"Found default action map: {config_path}")
                if self.load_from_json(config_path, auto_save=False, emit_signal=False):
                    self.logger.info(f"Loaded default action map from {config_path}")
                    self._loaded_successfully = True
                    # Save as user map for future sessions
                    self._schedule_auto_save()
                    return
                else:
                    self.logger.warning(f"Failed to load default action map from {config_path}")
            else:
                self.logger.info("Default action map not found")
                
                # Ensure default config exists for next time
                self._config_path_manager.ensure_default_configs()
        except Exception as e:
            self.logger.warning(f"Error loading default action map: {str(e)}")
            
        # If we get here, no valid action map was found
        # Create a default action map
        self.logger.info("Creating default action map")
        try:
            # Single source of truth: ``defaults.DEFAULT_ACTION_MAP``.
            default_map = default_action_map()

            self._action_map = default_map
            self._behavior_kinds = {}  # bundled defaults are all state
            self._loaded_successfully = True

            # Don't emit signal during initialization
            
            # Save both as default and user map
            default_path = self._config_path_manager.get_action_map_config_path("default_action_map.json")
            if default_path:
                default_path.parent.mkdir(parents=True, exist_ok=True)
                with open(default_path, 'w') as f:
                    json.dump(default_map, f, indent=2)
                self.logger.info(f"Created default action map at {default_path}")
            
            # Also save as user map
            self._schedule_auto_save()
            
        except Exception as e:
            self.logger.error(f"Failed to create default action map: {str(e)}")
    
    def load_from_json(self, json_path, auto_save=True, emit_signal=True):
        """
        Load action map from a JSON file.
        
        Args:
            json_path (str): Path to the JSON file
            auto_save (bool): Whether to trigger auto-save after loading
            emit_signal (bool): Whether to emit map_changed signal
            
        Returns:
            bool: True if loaded successfully, False otherwise
        """
        try:
            self.logger.info(f"Loading action map from: {json_path}")
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            # Validate format
            if not isinstance(data, dict):
                raise ValueError("Action map must be a dictionary")

            # Parse the union value form (1.4.0): a value is either a bare
            # behaviour-name string (kind "state") or an object
            # ``{"behavior": <name>, "kind": "state"|"point"}``. Names land in
            # ``_action_map`` and kinds in ``_behavior_kinds`` so the rest of
            # the model still sees a plain ``{key: name}`` map.
            parsed_map = {}
            parsed_kinds = {}
            for key, value in data.items():
                if not isinstance(key, str) or len(key) != 1:
                    raise ValueError(f"Invalid key format: {key}")
                if isinstance(value, dict):
                    name = value.get("behavior")
                    kind = value.get("kind", "state")
                else:
                    name = value
                    kind = "state"
                if not isinstance(name, str) or not name.strip():
                    raise ValueError(f"Invalid behavior label for key {key}: {value}")
                if kind not in ("state", "point"):
                    self.logger.warning(
                        "Unknown behaviour kind %r for key '%s'; defaulting to 'state'",
                        kind, key,
                    )
                    kind = "state"
                parsed_map[key] = name
                parsed_kinds[key] = kind

            self._action_map = parsed_map
            self._behavior_kinds = parsed_kinds

            # Tolerate (but warn about) duplicate behaviour names on load for
            # backward compatibility (§16-2): older maps may map two keys to
            # the same behaviour. New add/edit operations reject duplicates.
            self._warn_duplicate_behaviors()

            if emit_signal:
                self.map_changed.emit()
            
            # Save as user map if auto_save is enabled (for manual loads)
            if auto_save:
                self._schedule_auto_save()
            
            return True
        except Exception as e:
            error_msg = f"Failed to load action map: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def save_to_json(self, json_path):
        """
        Save action map to a JSON file.
        
        Args:
            json_path (str): Path to the JSON file
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            self.logger.info(f"Saving action map to: {json_path}")
            # Ensure parent directory exists
            Path(json_path).parent.mkdir(parents=True, exist_ok=True)
            
            with open(json_path, 'w') as f:
                json.dump(self._serialize_map(), f, indent=2)
            return True
        except Exception as e:
            error_msg = f"Failed to save action map: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False

    def _serialize_map(self):
        """Build the on-disk union form from the internal name/kind maps.

        A ``state`` behaviour is written as a bare string (identical to the
        pre-1.4.0 format), so an all-state map round-trips byte-for-byte. Only
        ``point`` behaviours use the object form, keeping older files and the
        bundled defaults unchanged.
        """
        out = {}
        for key, name in self._action_map.items():
            if self._behavior_kinds.get(key, "state") == "point":
                out[key] = {"behavior": name, "kind": "point"}
            else:
                out[key] = name
        return out

    def _schedule_auto_save(self):
        """Schedule an auto-save operation."""
        if not self._auto_save_pending:
            self._auto_save_pending = True
            self._auto_save_timer.stop()
            self._auto_save_timer.start(500)  # Save after 500ms of inactivity
    
    def _auto_save(self):
        """Automatically save the current action map to user storage."""
        self._auto_save_pending = False
        user_map_path = self._config_path_manager.get_action_map_config_path("user_action_map.json")
        
        if user_map_path:
            if self.save_to_json(user_map_path):
                self.logger.debug("Auto-saved user action map")
            else:
                self.logger.error("Failed to auto-save user action map")
    
    def add_mapping(self, key, behavior, kind=None):
        """
        Add a new key-to-behavior mapping.

        Args:
            key (str): Key character
            behavior (str): Behavior label
            kind (str, optional): "state" or "point". ``None`` (default)
                preserves the key's existing kind if it has one, else "state",
                so existing callers and re-confirmations never clobber a point.

        Returns:
            bool: True if added successfully, False otherwise
        """
        # Validate key
        if not isinstance(key, str) or len(key) != 1:
            error_msg = f"Invalid key format: {key}"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False
        
        # Validate behavior
        if not isinstance(behavior, str) or not behavior.strip():
            error_msg = f"Invalid behavior label: {behavior}"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False

        # Reject a behaviour name already mapped to a DIFFERENT key (§16-2 /
        # BUG-011). Each behaviour must have a single key so CSV import can
        # resolve the key unambiguously. Re-assigning the same key (an edit) or
        # re-confirming the same pair is allowed.
        behavior_cf = behavior.strip().casefold()
        for existing_key, existing_behavior in self._action_map.items():
            if existing_key != key and str(existing_behavior).strip().casefold() == behavior_cf:
                error_msg = (
                    f"Behavior '{behavior}' is already mapped to key "
                    f"'{existing_key}'. Each behaviour must have a unique name."
                )
                self.logger.warning(error_msg)
                self.error_occurred.emit(error_msg)
                return False

        # Resolve the kind: explicit value wins; otherwise keep the key's
        # current kind (preserves a point on a same-key edit / re-confirm),
        # falling back to "state".
        if kind is None:
            resolved_kind = self._behavior_kinds.get(key, "state")
        elif kind in ("state", "point"):
            resolved_kind = kind
        else:
            self.logger.warning("Unknown behaviour kind %r; using 'state'", kind)
            resolved_kind = "state"

        self.logger.debug(f"Adding mapping: {key} -> {behavior} ({resolved_kind})")
        self._action_map[key] = behavior
        self._behavior_kinds[key] = resolved_kind
        self.map_changed.emit()
        self.mapping_added.emit(key, behavior)
        
        # Schedule auto-save
        self._schedule_auto_save()
        
        return True
    
    def remove_mapping(self, key):
        """
        Remove a key-to-behavior mapping.
        
        Args:
            key (str): Key character
            
        Returns:
            bool: True if removed successfully, False otherwise
        """
        if key in self._action_map:  # Use correct attribute name
            behavior = self._action_map[key]  # Get behavior before deletion
            self.logger.debug(f"Removing mapping for key: {key} -> {behavior}")
            was_active = key in self._active_behaviors
            
            del self._action_map[key]
            self._behavior_kinds.pop(key, None)
            self._active_behaviors.discard(key)
            
            # Emit both signals for compatibility
            self.map_changed.emit()  # Keep existing signal
            self.mapping_removed.emit(behavior)  # Add new signal for timeline
            if was_active:
                self.active_behaviors_changed.emit()
            
            # Schedule auto-save
            self._schedule_auto_save()
            
            self.logger.info(f"Removed mapping: {key} -> {behavior}")
            return True
        else:
            self.logger.warning(f"Key not found in action map: {key}")
            return False
    
    def _warn_duplicate_behaviors(self):
        """Log a warning if any behaviour name is mapped to more than one key.

        Does not modify the map — purely diagnostic for legacy files. New
        add/edit operations prevent duplicates going forward (§16-2).
        """
        seen = {}
        duplicates = {}
        for key, behavior in self._action_map.items():
            cf = str(behavior).strip().casefold()
            if cf in seen:
                duplicates.setdefault(behavior, [seen[cf]]).append(key)
            else:
                seen[cf] = key
        if duplicates:
            for behavior, keys in duplicates.items():
                self.logger.warning(
                    "Behavior '%s' is mapped to multiple keys %s; CSV import "
                    "will resolve to the first key in sorted order. Consider "
                    "removing the duplicates.",
                    behavior, sorted(keys),
                )

    def has_behavior(self, behavior, ignore_key=None):
        """Return True if ``behavior`` (case-insensitive) is already mapped.

        ``ignore_key`` lets an edit of an existing key skip its own row.
        """
        target = str(behavior).strip().casefold()
        for key, mapped in self._action_map.items():
            if key == ignore_key:
                continue
            if str(mapped).strip().casefold() == target:
                return True
        return False

    def get_behavior(self, key):
        """
        Get behavior label for a key.
        
        Args:
            key (str): Key character
            
        Returns:
            str: Behavior label or None if key not found
        """
        return self._action_map.get(key)

    def get_kind(self, key):
        """Return the behaviour kind for a key: "state" (default) or "point"."""
        return self._behavior_kinds.get(key, "state")

    def get_all_kinds(self):
        """Return ``{key: "state"|"point"}`` for every mapped key."""
        return {key: self._behavior_kinds.get(key, "state") for key in self._action_map}

    def get_all_mappings(self):
        """
        Get all key-to-behavior mappings.
        
        Returns:
            dict: Dictionary of key-to-behavior mappings
        """
        return self._action_map.copy()
    
    def set_behavior_active(self, key, active=True):
        """
        Set a behavior as active or inactive.
        
        Args:
            key (str): Key character
            active (bool): True to set active, False to set inactive
        """
        behavior = self.get_behavior(key)
        if behavior:
            # Track the previous state to detect changes
            was_active = key in self._active_behaviors
            
            if active:
                self._active_behaviors.add(key)
                # Only emit if the state actually changed
                if not was_active:
                    self.logger.debug(f"Behavior '{behavior}' activated")
                    self.active_behaviors_changed.emit()
            else:
                self._active_behaviors.discard(key)
                # Only emit if the state actually changed
                if was_active:
                    self.logger.debug(f"Behavior '{behavior}' deactivated")
                    self.active_behaviors_changed.emit()
    
    def is_behavior_active(self, key):
        """
        Check if a behavior is currently active.
        
        Args:
            key (str): Key character
            
        Returns:
            bool: True if active, False otherwise
        """
        return key in self._active_behaviors
    
    def get_active_behaviors(self):
        """
        Get all currently active behaviors.
        
        Returns:
            dict: Dictionary of active key-to-behavior mappings
        """
        return {k: self._action_map[k] for k in self._active_behaviors if k in self._action_map}
    
    def clear_active_behaviors(self):
        """Clear all active behaviors."""
        if self._active_behaviors:
            self._active_behaviors.clear()
            self.active_behaviors_changed.emit()
    
    def is_loaded(self):
        """
        Check if action map has been loaded successfully.
        
        Returns:
            bool: True if action map was loaded, False otherwise
        """
        return self._loaded_successfully and bool(self._action_map)
    
    def initialize_view(self):
        """
        Trigger initial view update after controller is connected.
        This should be called after all signal connections are established.
        """
        if self._action_map:
            self.map_changed.emit()
            self.logger.debug("Triggered initial view update")
    
    def reset_to_default(self):
        """
        Reset action map to default configuration.
        
        Returns:
            bool: True if reset successfully, False otherwise
        """
        try:
            # Load default action map
            default_path = self._config_path_manager.get_action_map_config_path("default_action_map.json")
            
            if default_path and default_path.exists():
                if self.load_from_json(default_path, auto_save=True):
                    self.logger.info("Reset action map to default")
                    return True
                    
            # If default doesn't exist, use the centralised fallback.
            self._action_map = default_action_map()
            self._behavior_kinds = {}  # all state

            self.map_changed.emit()
            self._schedule_auto_save()
            
            self.logger.info("Reset action map to hardcoded default")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to reset to default: {str(e)}")
            return False
