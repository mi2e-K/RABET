# models/project_model.py - Updated for enhanced video management and annotation tracking
import hashlib
import logging
import os
import random
import shutil
import uuid
from pathlib import Path
from PySide6.QtCore import QObject, Signal

class ProjectModel(QObject):
    """
    Model for managing research projects containing related videos, 
    annotations, and analyses.
    
    A project organizes related files in a single directory structure with subdirectories
    for videos, annotations, action maps, and exports.
    
    Signals:
        project_created: Emitted when a new project is created
        project_loaded: Emitted when a project is loaded
        project_saved: Emitted when a project is saved
        project_closed: Emitted when a project is closed
        error_occurred: Emitted when an error occurs
    """
    
    project_created = Signal(str)  # Project path
    project_loaded = Signal(str)   # Project path
    project_saved = Signal()
    project_closed = Signal()
    error_occurred = Signal(str)   # Error message
    
    def __init__(self, file_manager):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing ProjectModel")
        
        self._file_manager = file_manager
        
        # Project properties
        self._project_path = None
        self._project_name = None
        self._project_config = {
            "name": "",
            "description": "",
            "created_date": "",
            "modified_date": "",
            "videos": [],
            "annotations": [],
            "action_maps": [],
            "analyses": [],
            "video_annotation_files": {},
        }
        # PR-S2: stored-path -> stable video id. Populated on load/add; the id
        # is persisted in the v2 manifest (entry.id) and reused rather than
        # recomputed from the path, so it survives moving the project folder
        # (BUG-006). _get_video_id reads this map; only add_video mints new ids.
        self._video_id_by_path = {}
        self._is_modified = False
    
    def create_project(self, project_path, project_name, description=""):
        """
        Create a new project at the specified path.
        
        Args:
            project_path (str): Directory path for the project
            project_name (str): Name of the project
            description (str, optional): Project description
            
        Returns:
            bool: True if project was created successfully, False otherwise
        """
        try:
            self.logger.info(f"Creating project: {project_name} at {project_path}")
            
            # Create project directory
            project_dir = Path(project_path) / project_name
            if project_dir.exists():
                error_msg = f"Project directory already exists: {project_dir}"
                self.logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return False
            
            # Create project structure
            project_dir.mkdir(parents=True)
            (project_dir / "videos").mkdir()
            (project_dir / "annotations").mkdir()
            (project_dir / "action_maps").mkdir()
            (project_dir / "analyses").mkdir()
            
            # Initialize project configuration
            from datetime import datetime
            current_date = datetime.now().isoformat()
            
            self._project_config = {
                "name": project_name,
                "description": description,
                "created_date": current_date,
                "modified_date": current_date,
                "videos": [],
                "annotations": [],
                "action_maps": [],
                "analyses": [],
                "video_annotation_status": {},  # New field to track annotation status
                "video_annotation_files": {},
            }
            self._video_id_by_path = {}

            # Save project configuration. If the manifest cannot be written we
            # must NOT report success or enter the "project open" state — doing
            # so left RABET pointing at a project with no project.json on disk
            # (BUG-007).
            if not self._save_project_config(project_dir):
                error_msg = (
                    f"Failed to write project manifest at {project_dir / 'project.json'}"
                )
                self.logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                # Roll back the freshly-created (and now empty/partial) project
                # directory so a retry to the same path is not blocked.
                try:
                    shutil.rmtree(project_dir)
                except OSError as exc:
                    self.logger.warning(
                        f"Could not clean up failed project dir {project_dir}: {exc}"
                    )
                return False

            # Update current project
            self._project_path = str(project_dir)
            self._project_name = project_name
            self._is_modified = False

            self.project_created.emit(self._project_path)
            return True

        except Exception as e:
            error_msg = f"Failed to create project: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def load_project(self, project_path):
        """
        Load a project from the specified path.
        
        Args:
            project_path (str): Path to the project directory
            
        Returns:
            bool: True if project was loaded successfully, False otherwise
        """
        try:
            self.logger.info(f"Loading project from: {project_path}")
            self._is_modified = False
            
            project_dir = Path(project_path)
            config_file = project_dir / "project.json"
            
            # Check if it's a valid project directory
            if not project_dir.is_dir() or not config_file.exists():
                error_msg = f"Invalid project directory: {project_path}"
                self.logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return False
            
            # Load project configuration
            self._project_config = self._file_manager.load_json(config_file)
            if not self._project_config:
                error_msg = f"Failed to load project configuration: {config_file}"
                self.logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return False

            # Set the project path/name early so video-id resolution works while
            # we normalise the manifest below.
            self._project_path = str(project_dir)
            self._project_name = self._project_config.get("name", project_dir.name)

            # Normalise the on-disk manifest (v1 string-list videos OR v2 object
            # videos) into the internal representation used by the rest of
            # ProjectModel (string-list videos + status/files maps). A v1 file
            # is flagged dirty so it is re-saved in v2 form below (migration).
            loaded_schema = self._project_config.get("schema_version")
            self._load_into_internal(self._project_config)
            if not isinstance(loaded_schema, int) or loaded_schema < 2:
                self._is_modified = True

            # Ensure the internal maps exist (older files / fresh conversion).
            if "video_annotation_status" not in self._project_config:
                self._project_config["video_annotation_status"] = {}
                self._is_modified = True
            if "video_annotation_files" not in self._project_config:
                self._project_config["video_annotation_files"] = {}
                self._is_modified = True

            self._migrate_video_annotation_status()
            
            # Update annotation status based on existing annotation files
            self._update_annotation_status()
            
            # Save if modifications were made (e.g., adding video_annotation_status field)
            if self._is_modified:
                self.save_project()
            else:
                self._is_modified = False
            
            self.project_loaded.emit(self._project_path)
            return True
            
        except Exception as e:
            error_msg = f"Failed to load project: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def _update_annotation_status(self):
        """
        Update annotation status for videos based on existing annotation files.
        This ensures backward compatibility with older projects.
        """
        try:
            status_map = self._project_config.setdefault("video_annotation_status", {})
            annotation_files = self._project_config.get("annotations", [])
            videos = self._project_config.get("videos", [])

            matched_videos = set()
            ambiguous_legacy_ids = set()

            for annotation_path in annotation_files:
                annotation_base = os.path.splitext(os.path.basename(annotation_path))[0]
                if annotation_base.endswith("_annotations"):
                    annotation_base = annotation_base[:-12]

                matches = self._find_video_matches_for_annotation_base_name(annotation_base)
                if len(matches) == 1:
                    matched_videos.add(matches[0])
                elif len(matches) > 1:
                    ambiguous_legacy_ids.add(annotation_base)
                    if status_map.get(annotation_base) != "annotated":
                        status_map[annotation_base] = "annotated"
                        self._is_modified = True
                    self.logger.warning(
                        "Annotation basename '%s' matches multiple videos; preserving legacy shared status",
                        annotation_base,
                    )

            valid_video_ids = {self._get_video_id(video_path) for video_path in videos}
            stale_ids = [key for key in list(status_map.keys()) if "__" in key and key not in valid_video_ids]
            for stale_id in stale_ids:
                del status_map[stale_id]
                self._is_modified = True

            for video_path in videos:
                video_id = self._get_video_id(video_path)
                legacy_id = self._get_legacy_video_id(video_path)

                if video_path in matched_videos:
                    desired_status = "annotated"
                elif legacy_id in ambiguous_legacy_ids and video_id not in status_map:
                    continue
                else:
                    desired_status = "not_annotated"

                if status_map.get(video_id) != desired_status:
                    status_map[video_id] = desired_status
                    self._is_modified = True
                    self.logger.info(
                        "Updated annotation status for video %s to '%s'",
                        video_id,
                        desired_status,
                    )

            if self._is_modified:
                self.logger.info("Updated annotation status based on existing files")
        except Exception as e:
            self.logger.error(f"Error updating annotation status: {str(e)}")

    def _migrate_video_annotation_status(self):
        """
        Migrate legacy basename-based status keys to stable per-video IDs when
        the mapping is unambiguous.
        """
        status_map = self._project_config.setdefault("video_annotation_status", {})
        videos = self._project_config.get("videos", [])
        legacy_counts = {}

        for video_path in videos:
            legacy_id = self._get_legacy_video_id(video_path)
            legacy_counts[legacy_id] = legacy_counts.get(legacy_id, 0) + 1

        duplicate_legacy_ids = {
            legacy_id for legacy_id, count in legacy_counts.items() if count > 1
        }

        migrated_status = {}
        for video_path in videos:
            video_id = self._get_video_id(video_path)
            legacy_id = self._get_legacy_video_id(video_path)

            if video_id in status_map:
                migrated_status[video_id] = status_map[video_id]
            elif legacy_id in status_map and legacy_id not in duplicate_legacy_ids:
                migrated_status[video_id] = status_map[legacy_id]

        for key, value in status_map.items():
            if "__" not in key and key in duplicate_legacy_ids:
                migrated_status[key] = value

        if migrated_status != status_map:
            self._project_config["video_annotation_status"] = migrated_status
            self._is_modified = True

    def _normalize_video_reference(self, video_path):
        """Normalize a stored or absolute video reference for stable hashing."""
        video_path = str(video_path)
        if self._project_path and not os.path.isabs(video_path):
            video_path = os.path.join(self._project_path, video_path)

        return os.path.normcase(os.path.normpath(os.path.abspath(video_path)))

    def _get_legacy_video_id(self, video_path):
        """Get the legacy basename-based identifier for a video."""
        return os.path.splitext(os.path.basename(str(video_path)))[0]

    def _get_video_by_exact_id(self, video_id):
        """Return the stored video path matching an exact internal ID."""
        for video_path in self._project_config.get("videos", []):
            if self._get_video_id(video_path) == video_id:
                return video_path
        return None

    def _resolve_video_reference(self, video_reference):
        """
        Resolve a stored path, absolute path, or legacy/current video ID to the
        stored project video reference.
        """
        if not self._project_path or video_reference is None:
            return None

        reference = str(video_reference)
        videos = self._project_config.get("videos", [])

        if reference in videos:
            return reference

        normalized_reference = self._normalize_video_reference(reference)
        for video_path in videos:
            if self._normalize_video_reference(video_path) == normalized_reference:
                return video_path

        exact_match = self._get_video_by_exact_id(reference)
        if exact_match:
            return exact_match

        legacy_matches = [
            video_path for video_path in videos
            if self._get_legacy_video_id(video_path) == reference
        ]
        if len(legacy_matches) == 1:
            return legacy_matches[0]
        if len(legacy_matches) > 1:
            self.logger.warning(
                "Ambiguous legacy video ID '%s' matches multiple project videos",
                reference,
            )

        return None

    def _find_video_matches_for_annotation_base_name(self, annotation_base_name):
        """Find project videos that match an annotation basename."""
        exact_match = self._get_video_by_exact_id(annotation_base_name)
        if exact_match:
            return [exact_match]

        return [
            video_path
            for video_path in self._project_config.get("videos", [])
            if self._get_legacy_video_id(video_path) == annotation_base_name
        ]

    def _legacy_hash_id(self, video_path):
        """Legacy id: basename + absolute-path hash.

        Deterministic but NOT move-stable (it embeds the absolute path, which
        is exactly BUG-006). Kept as a fallback for videos not yet registered
        in ``_video_id_by_path`` and to derive ids when migrating a v1 manifest.
        """
        legacy_id = self._get_legacy_video_id(video_path)
        normalized_path = self._normalize_video_reference(video_path)
        digest = hashlib.sha1(normalized_path.encode('utf-8')).hexdigest()[:12]
        return f"{legacy_id}__{digest}"

    def _mint_video_id(self, stored_path):
        """Mint a new move-stable id for a freshly-added video (PR-S2)."""
        legacy_id = self._get_legacy_video_id(stored_path)
        return f"{legacy_id}__{uuid.uuid4().hex[:12]}"

    def _stored_path_for(self, video_reference):
        """Resolve a reference to its stored path WITHOUT calling _get_video_id.

        Breaks the id<->path resolution recursion (PR-S2). Accepts a stored
        path, an absolute path, a persisted id, or an unambiguous legacy
        basename id; returns the reference unchanged if nothing matches.
        """
        if video_reference is None:
            return None
        reference = str(video_reference)
        videos = self._project_config.get("videos", [])
        if reference in videos:
            return reference
        if self._project_path:
            normalized_reference = self._normalize_video_reference(reference)
            for video_path in videos:
                if self._normalize_video_reference(video_path) == normalized_reference:
                    return video_path
        for path, vid in self._video_id_by_path.items():
            if vid == reference:
                return path
        legacy_matches = [
            v for v in videos if self._get_legacy_video_id(v) == reference
        ]
        if len(legacy_matches) == 1:
            return legacy_matches[0]
        return reference

    def _get_video_id(self, video_path):
        """
        Get a stable identifier for a video (PR-S2).

        Reads the persisted ``stored-path -> id`` map so the id survives moving
        the project folder. Falls back to the legacy absolute-path hash for a
        video not registered yet (e.g. a pre-add existence check). Pure: it
        never mints/registers an id — ``add_video`` does that.

        Args:
            video_path (str): Path / reference to the video file

        Returns:
            str: Stable video identifier
        """
        stored = self._stored_path_for(video_path)
        persisted = self._video_id_by_path.get(stored)
        if persisted:
            return persisted
        return self._legacy_hash_id(video_path)

    def get_video_id(self, video_path):
        """Get the internal video ID for a stored path, absolute path, or video ID."""
        resolved_reference = self._resolve_video_reference(video_path)
        target = resolved_reference if resolved_reference is not None else video_path
        return self._get_video_id(target)

    def _make_unique_annotation_relative_path(self, base_name, video_id):
        """Return a project-relative annotation path without exposing hashes."""
        mapping = self._project_config.setdefault("video_annotation_files", {})
        used_paths = {
            path for mapped_id, path in mapping.items()
            if mapped_id != video_id
        }

        suffix = "_annotations.csv"
        index = 1
        while True:
            if index == 1:
                filename = f"{base_name}{suffix}"
            else:
                filename = f"{base_name}_{index}{suffix}"

            rel_path = os.path.join("annotations", filename)
            if rel_path not in used_paths:
                return rel_path

            index += 1

    def get_annotation_relative_path_for_video(self, video_path):
        """
        Return the project-relative annotation CSV path for a video.

        The stable internal video ID remains in ``project.json`` only; the
        visible filename stays readable, e.g. ``mouse_annotations.csv``.
        """
        if not self._project_path:
            return None

        resolved_reference = self._resolve_video_reference(video_path)
        target = resolved_reference if resolved_reference is not None else video_path
        video_id = self._get_video_id(target)
        mapping = self._project_config.setdefault("video_annotation_files", {})

        if video_id in mapping:
            return mapping[video_id]

        base_name = self._get_legacy_video_id(target)
        rel_path = self._make_unique_annotation_relative_path(base_name, video_id)
        legacy_hashed_rel_path = os.path.join("annotations", f"{video_id}_annotations.csv")
        legacy_hashed_full_path = Path(self._project_path) / legacy_hashed_rel_path
        clean_full_path = Path(self._project_path) / rel_path

        if legacy_hashed_full_path.exists() and not clean_full_path.exists():
            try:
                shutil.copy2(legacy_hashed_full_path, clean_full_path)
                annotations = self._project_config.setdefault("annotations", [])
                if rel_path not in annotations:
                    annotations.append(rel_path)
                self.logger.info(
                    "Copied legacy hashed annotation file to readable name: %s -> %s",
                    legacy_hashed_rel_path,
                    rel_path,
                )
            except Exception as exc:
                self.logger.warning(
                    "Failed to copy legacy hashed annotation file %s: %s",
                    legacy_hashed_rel_path,
                    exc,
                )

        mapping[video_id] = rel_path
        self._is_modified = True
        return rel_path

    def find_same_name_video_conflict(self, video_path):
        """Return a stored project video with the same name but different path."""
        if not self._project_path or not video_path:
            return None

        target_name = os.path.basename(str(video_path)).lower()
        target_norm = self._normalize_video_reference(video_path)

        for stored_video in self._project_config.get("videos", []):
            if os.path.basename(str(stored_video)).lower() != target_name:
                continue

            resolved = self.resolve_path(stored_video)
            if not resolved:
                continue

            if self._normalize_video_reference(resolved) != target_norm:
                return stored_video, resolved

        return None
    
    def save_project(self):
        """
        Save the current project.
        
        Returns:
            bool: True if project was saved successfully, False otherwise
        """
        if not self._project_path:
            error_msg = "No project is currently open"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False
        
        try:
            self.logger.info(f"Saving project: {self._project_name}")
            
            # Update modified date
            from datetime import datetime
            self._project_config["modified_date"] = datetime.now().isoformat()
            
            # Save project configuration
            project_dir = Path(self._project_path)
            success = self._save_project_config(project_dir)
            
            if success:
                self._is_modified = False
                self.project_saved.emit()
            
            return success
            
        except Exception as e:
            error_msg = f"Failed to save project: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def close_project(self):
        """
        Close the current project.
        
        Returns:
            bool: True if project was closed successfully, False otherwise
        """
        if not self._project_path:
            return True  # No project to close
        
        try:
            self.logger.info(f"Closing project: {self._project_name}")
            
            # Reset project properties
            self._project_path = None
            self._project_name = None
            self._project_config = {
                "name": "",
                "description": "",
                "created_date": "",
                "modified_date": "",
                "videos": [],
                "annotations": [],
                "action_maps": [],
                "analyses": [],
                "video_annotation_status": {},
                "video_annotation_files": {},
            }
            self._video_id_by_path = {}
            self._is_modified = False

            self.project_closed.emit()
            return True
            
        except Exception as e:
            error_msg = f"Failed to close project: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def add_video(self, video_path, copy_to_project=False):
        """
        Add a video to the project.
        
        Args:
            video_path (str): Path to the video file
            copy_to_project (bool): Whether to copy the video to the project directory.
                                   Default is now False (changed from original implementation).
            
        Returns:
            bool: True if video was added successfully, False otherwise
        """
        if not self._project_path:
            error_msg = "No project is currently open"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False
        
        try:
            video_path = Path(video_path)
            
            if not video_path.exists():
                error_msg = f"Video file not found: {video_path}"
                self.logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return False
            
            # Generate a project-relative path for the video
            if copy_to_project:
                # Copy video to project directory
                project_videos_dir = Path(self._project_path) / "videos"
                target_path = project_videos_dir / video_path.name
                
                if not self._file_manager.copy_file(video_path, target_path):
                    error_msg = f"Failed to copy video to project: {video_path}"
                    self.logger.error(error_msg)
                    self.error_occurred.emit(error_msg)
                    return False
                
                # Use relative path for storage
                rel_path = os.path.join("videos", video_path.name)
            else:
                # Store absolute path
                rel_path = str(video_path)
            
            # Check if video is already in the project
            if rel_path in self._project_config["videos"]:
                return True  # Already added
            
            # Add video to project
            self._project_config["videos"].append(rel_path)

            # Mint and register a move-stable id (PR-S2), then initialise status.
            video_id = self._mint_video_id(rel_path)
            self._video_id_by_path[rel_path] = video_id
            if "video_annotation_status" not in self._project_config:
                self._project_config["video_annotation_status"] = {}
            self._project_config["video_annotation_status"][video_id] = "not_annotated"
            
            self._is_modified = True
            
            self.logger.debug(f"Added video to project: {rel_path}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to add video: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def add_annotation(self, annotation_path, copy_to_project=True, update_status=True):
        """
        Add an annotation file to the project.
        
        Args:
            annotation_path (str): Path to the annotation file (CSV)
            copy_to_project (bool): Whether to copy the file to the project directory
            update_status (bool): Whether to update the video annotation status
            
        Returns:
            bool: True if annotation was added successfully, False otherwise
        """
        if not self._project_path:
            error_msg = "No project is currently open"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False
        
        try:
            annotation_path = Path(annotation_path)
            
            if not annotation_path.exists():
                error_msg = f"Annotation file not found: {annotation_path}"
                self.logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return False
            
            # Generate a project-relative path for the annotation
            if copy_to_project:
                # Copy annotation to project directory
                project_annotations_dir = Path(self._project_path) / "annotations"
                target_path = project_annotations_dir / annotation_path.name
                
                if not self._file_manager.copy_file(annotation_path, target_path):
                    error_msg = f"Failed to copy annotation to project: {annotation_path}"
                    self.logger.error(error_msg)
                    self.error_occurred.emit(error_msg)
                    return False
                
                # Use relative path for storage
                rel_path = os.path.join("annotations", annotation_path.name)
            else:
                try:
                    project_root = Path(self._project_path).resolve()
                    resolved_annotation = annotation_path.resolve()
                    if os.path.commonpath([str(resolved_annotation), str(project_root)]) == str(project_root):
                        rel_path = os.path.relpath(resolved_annotation, project_root)
                    else:
                        rel_path = str(annotation_path)
                except ValueError:
                    rel_path = str(annotation_path)
            
            # Check if annotation is already in the project
            if rel_path in self._project_config["annotations"]:
                return True  # Already added
            
            # Add annotation to project
            self._project_config["annotations"].append(rel_path)
            self._is_modified = True
            
            # Update annotation status if requested
            if update_status:
                # Extract base filename without extension and remove "_annotations" suffix if present
                base_name = os.path.splitext(os.path.basename(annotation_path))[0]
                if base_name.endswith("_annotations"):
                    base_name = base_name[:-12]

                matching_videos = self._find_video_matches_for_annotation_base_name(base_name)
                if len(matching_videos) == 1:
                    self.set_video_annotation_status(matching_videos[0], "annotated")
                elif len(matching_videos) > 1:
                    self._project_config.setdefault("video_annotation_status", {})[base_name] = "annotated"
                    self._is_modified = True
                    self.logger.warning(
                        "Annotation '%s' matches multiple videos; preserving shared legacy status",
                        annotation_path.name,
                    )
                else:
                    self.logger.warning(
                        "Could not match annotation '%s' to a project video",
                        annotation_path.name,
                    )
             
            self.logger.debug(f"Added annotation to project: {rel_path}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to add annotation: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def add_action_map(self, action_map_path, copy_to_project=True):
        """
        Add an action map file to the project.
        
        Args:
            action_map_path (str): Path to the action map file (JSON)
            copy_to_project (bool): Whether to copy the file to the project directory
            
        Returns:
            bool: True if action map was added successfully, False otherwise
        """
        if not self._project_path:
            error_msg = "No project is currently open"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False
        
        try:
            action_map_path = Path(action_map_path)
            
            if not action_map_path.exists():
                error_msg = f"Action map file not found: {action_map_path}"
                self.logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return False
            
            # Generate a project-relative path for the action map
            if copy_to_project:
                # Copy action map to project directory
                project_maps_dir = Path(self._project_path) / "action_maps"
                target_path = project_maps_dir / action_map_path.name
                
                if not self._file_manager.copy_file(action_map_path, target_path):
                    error_msg = f"Failed to copy action map to project: {action_map_path}"
                    self.logger.error(error_msg)
                    self.error_occurred.emit(error_msg)
                    return False
                
                # Use relative path for storage
                rel_path = os.path.join("action_maps", action_map_path.name)
            else:
                # Store absolute path
                rel_path = str(action_map_path)
            
            # Check if action map is already in the project
            if rel_path in self._project_config["action_maps"]:
                return True  # Already added
            
            # Add action map to project
            self._project_config["action_maps"].append(rel_path)
            self._is_modified = True
            
            self.logger.debug(f"Added action map to project: {rel_path}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to add action map: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def add_analysis(self, analysis_path, copy_to_project=True):
        """
        Add an analysis file to the project.
        
        Args:
            analysis_path (str): Path to the analysis file (CSV)
            copy_to_project (bool): Whether to copy the file to the project directory
            
        Returns:
            bool: True if analysis was added successfully, False otherwise
        """
        if not self._project_path:
            error_msg = "No project is currently open"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False
        
        try:
            analysis_path = Path(analysis_path)
            
            if not analysis_path.exists():
                error_msg = f"Analysis file not found: {analysis_path}"
                self.logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return False
            
            # Generate a project-relative path for the analysis
            if copy_to_project:
                # Copy analysis to project directory
                project_analyses_dir = Path(self._project_path) / "analyses"
                target_path = project_analyses_dir / analysis_path.name
                
                if not self._file_manager.copy_file(analysis_path, target_path):
                    error_msg = f"Failed to copy analysis to project: {analysis_path}"
                    self.logger.error(error_msg)
                    self.error_occurred.emit(error_msg)
                    return False
                
                # Use relative path for storage
                rel_path = os.path.join("analyses", analysis_path.name)
            else:
                # Store absolute path
                rel_path = str(analysis_path)
            
            # Check if analysis is already in the project
            if rel_path in self._project_config["analyses"]:
                return True  # Already added
            
            # Add analysis to project
            self._project_config["analyses"].append(rel_path)
            self._is_modified = True
            
            self.logger.debug(f"Added analysis to project: {rel_path}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to add analysis: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def remove_file(self, file_path, file_type):
        """
        Remove a file from the project.
        
        Args:
            file_path (str): Path to the file
            file_type (str): Type of file (videos, annotations, action_maps, analyses)
            
        Returns:
            bool: True if file was removed successfully, False otherwise
        """
        if not self._project_path:
            error_msg = "No project is currently open"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False
        
        try:
            # Check if file type is valid
            if file_type not in ["videos", "annotations", "action_maps", "analyses"]:
                error_msg = f"Invalid file type: {file_type}"
                self.logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return False
            
            # Check if file is in project
            if file_path not in self._project_config[file_type]:
                error_msg = f"File not found in project: {file_path}"
                self.logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return False
            
            # Remove file from project
            self._project_config[file_type].remove(file_path)
            self._is_modified = True

            if file_type == "videos":
                video_id = self._get_video_id(file_path)
                self._project_config.setdefault("video_annotation_files", {}).pop(video_id, None)
            
            # If file is in project directory, delete it
            stored_path = Path(file_path)
            if stored_path.parts and stored_path.parts[0] == file_type:
                full_path = os.path.join(self._project_path, file_path)
                try:
                    Path(full_path).unlink()
                except Exception:
                    # Don't fail if file can't be deleted
                    self.logger.warning(f"Failed to delete file: {full_path}")

            if file_type in {"videos", "annotations"}:
                self._migrate_video_annotation_status()
                self._update_annotation_status()
             
            self.logger.debug(f"Removed {file_type} from project: {file_path}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to remove file: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def get_project_name(self):
        """
        Get the name of the current project.
        
        Returns:
            str: Project name or None if no project is open
        """
        return self._project_name
    
    def get_project_path(self):
        """
        Get the path of the current project.
        
        Returns:
            str: Project path or None if no project is open
        """
        return self._project_path
    
    def get_project_description(self):
        """
        Get the description of the current project.
        
        Returns:
            str: Project description or empty string if no project is open
        """
        if not self._project_path:
            return ""
        
        return self._project_config.get("description", "")
    
    def set_project_description(self, description):
        """
        Set the description of the current project.
        
        Args:
            description (str): Project description
            
        Returns:
            bool: True if description was set successfully, False otherwise
        """
        if not self._project_path:
            error_msg = "No project is currently open"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False
        
        self._project_config["description"] = description
        self._is_modified = True
        return True
    
    def get_project_creation_date(self):
        """
        Get the creation date of the current project.
        
        Returns:
            str: Creation date or empty string if no project is open
        """
        if not self._project_path:
            return ""
        
        return self._project_config.get("created_date", "")
    
    def get_project_modification_date(self):
        """
        Get the last modification date of the current project.
        
        Returns:
            str: Modification date or empty string if no project is open
        """
        if not self._project_path:
            return ""
        
        return self._project_config.get("modified_date", "")
    
    def get_videos(self):
        """
        Get the list of videos in the current project.
        
        Returns:
            list: List of video paths or empty list if no project is open
        """
        if not self._project_path:
            return []
        
        return self._project_config.get("videos", [])
    
    def get_annotations(self):
        """
        Get the list of annotations in the current project.
        
        Returns:
            list: List of annotation paths or empty list if no project is open
        """
        if not self._project_path:
            return []
        
        return self._project_config.get("annotations", [])
    
    def get_action_maps(self):
        """
        Get the list of action maps in the current project.
        
        Returns:
            list: List of action map paths or empty list if no project is open
        """
        if not self._project_path:
            return []
        
        return self._project_config.get("action_maps", [])
    
    def get_analyses(self):
        """
        Get the list of analyses in the current project.
        
        Returns:
            list: List of analysis paths or empty list if no project is open
        """
        if not self._project_path:
            return []
        
        return self._project_config.get("analyses", [])
    
    def get_video_annotation_status(self, video_path=None):
        """
        Get the annotation status for a specific video or all videos.
        
        Args:
            video_path (str, optional): Path to the video.
                                      If None, returns status for all videos.
        
        Returns:
            dict or str: If video_path is specified, returns the status string
                        ("annotated" or "not_annotated").
                        If video_path is None, returns a dictionary of
                        {stored_video_path: status}.
        """
        if not self._project_path:
            return {} if video_path is None else "not_annotated"
        
        # Ensure video_annotation_status exists
        if "video_annotation_status" not in self._project_config:
            self._project_config["video_annotation_status"] = {}
            self._is_modified = True
        
        # Return status for all videos
        if video_path is None:
            return {
                stored_video_path: self.get_video_annotation_status(stored_video_path)
                for stored_video_path in self._project_config.get("videos", [])
            }
        
        # Return status for specific video
        resolved_reference = self._resolve_video_reference(video_path)
        if resolved_reference is None:
            return "not_annotated"

        video_id = self._get_video_id(resolved_reference)
        if video_id in self._project_config["video_annotation_status"]:
            return self._project_config["video_annotation_status"][video_id]

        legacy_id = self._get_legacy_video_id(resolved_reference)
        return self._project_config["video_annotation_status"].get(legacy_id, "not_annotated")
    
    def set_video_annotation_status(self, video_path, status):
        """
        Set the annotation status for a specific video.
        
        Args:
            video_path (str): Path to the video
            status (str): Annotation status ("annotated" or "not_annotated")
            
        Returns:
            bool: True if status was set successfully, False otherwise
        """
        if not self._project_path:
            error_msg = "No project is currently open"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False
        
        # Validate status
        if status not in ["annotated", "not_annotated"]:
            error_msg = f"Invalid annotation status: {status}"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False
        
        # Ensure video_annotation_status exists
        if "video_annotation_status" not in self._project_config:
            self._project_config["video_annotation_status"] = {}
        
        resolved_reference = self._resolve_video_reference(video_path)
        if resolved_reference is None:
            error_msg = f"Video not found in project: {video_path}"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False

        # Set status
        video_id = self._get_video_id(resolved_reference)
        self._project_config["video_annotation_status"][video_id] = status
        legacy_id = self._get_legacy_video_id(resolved_reference)
        matching_legacy_videos = [
            candidate for candidate in self._project_config.get("videos", [])
            if self._get_legacy_video_id(candidate) == legacy_id
        ]
        if len(matching_legacy_videos) == 1:
            self._project_config["video_annotation_status"].pop(legacy_id, None)
        self._is_modified = True
        
        self.logger.debug(f"Set annotation status for video {video_id} to {status}")
        return True
    
    def get_video_by_id(self, video_id):
        """
        Get video path by its ID.
        
        Args:
            video_id (str): Video ID (basename without extension)
            
        Returns:
            str: Video path or None if not found
        """
        if not self._project_path:
            return None
        
        exact_match = self._get_video_by_exact_id(video_id)
        if exact_match:
            return exact_match

        legacy_matches = [
            video_path for video_path in self._project_config.get("videos", [])
            if self._get_legacy_video_id(video_path) == video_id
        ]
        if len(legacy_matches) == 1:
            return legacy_matches[0]

        if len(legacy_matches) > 1:
            self.logger.warning(
                "Ambiguous legacy video ID '%s' matches multiple project videos",
                video_id,
            )

        return None
    
    def select_random_unannotated_video(self):
        """
        Select a random video that has not been annotated yet.
        
        Returns:
            str: Path to the selected video, or None if all videos are annotated
        """
        if not self._project_path:
            return None
        
        # Get all videos
        videos = self._project_config.get("videos", [])
        if not videos:
            return None
        
        # Filter unannotated videos
        unannotated_videos = []
        for video_path in videos:
            if self.get_video_annotation_status(video_path) == "not_annotated":
                unannotated_videos.append(video_path)
        
        # Select random video from unannotated videos
        if unannotated_videos:
            return random.choice(unannotated_videos)
        else:
            return None
    
    def is_modified(self):
        """
        Check if the project has unsaved changes.
        
        Returns:
            bool: True if project has unsaved changes, False otherwise
        """
        return self._is_modified
    
    def is_project_open(self):
        """
        Check if a project is currently open.
        
        Returns:
            bool: True if a project is open, False otherwise
        """
        return self._project_path is not None
    
    def _save_project_config(self, project_dir):
        """
        Save the project configuration to the project directory.
        
        Args:
            project_dir (pathlib.Path): Project directory
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        config_file = project_dir / "project.json"
        # Serialize the internal representation to the v2 on-disk shape, then
        # write atomically (+ keep project.json.bak) so an interrupted save can
        # be recovered (BUG-019).
        manifest = self._serialize_to_v2()
        return self._file_manager.save_json(
            manifest, config_file, atomic=True, backup=True
        )

    # ------------------------------------------------------------------ #
    # Manifest schema v1 <-> v2 conversion (PR-S1)
    #
    # The rest of ProjectModel keeps the v1-era *internal* representation:
    #   videos:                  list[str] of stored paths
    #   video_annotation_status: {video_id: status}
    #   video_annotation_files:  {video_id: rel_path}
    # Only the on-disk form changes to v2 (schema_version + one object per
    # video that embeds id / storage / annotation status+path). This keeps the
    # ~17 video-id methods untouched; UUID-based ids are PR-S2.
    # ------------------------------------------------------------------ #

    def _serialize_to_v2(self):
        """Build the v2 on-disk manifest from the internal representation."""
        cfg = dict(self._project_config)
        status_map = self._project_config.get("video_annotation_status", {})
        files_map = self._project_config.get("video_annotation_files", {})

        video_objects = []
        for path in self._project_config.get("videos", []):
            video_id = self._get_video_id(path)
            entry = {
                "id": video_id,
                "path": str(path),
                "storage": "external" if os.path.isabs(str(path)) else "copied",
                "annotation_status": status_map.get(video_id, "not_annotated"),
            }
            ann_path = files_map.get(video_id)
            if ann_path:
                entry["annotation_path"] = ann_path
            video_objects.append(entry)

        cfg["schema_version"] = 2
        cfg["videos"] = video_objects
        # status/files now live inside each video entry on disk.
        cfg.pop("video_annotation_status", None)
        cfg.pop("video_annotation_files", None)
        return cfg

    def _load_into_internal(self, config):
        """Normalise a loaded manifest (v1 or v2) into the internal representation.

        v1: ``videos`` is a list of path strings with top-level
        ``video_annotation_status`` / ``video_annotation_files`` maps — left
        as-is. v2: ``videos`` is a list of objects; we flatten them back into
        the path list + maps the rest of the model expects. Mutates and returns
        ``config``.
        """
        if not isinstance(config, dict):
            return config

        # Rebuild the stored-path -> id map for this project (PR-S2).
        self._video_id_by_path = {}

        videos = config.get("videos", [])
        if videos and isinstance(videos[0], dict):
            # v2: object videos with embedded id / status / path.
            path_list = []
            status_map = {}
            files_map = {}
            for entry in videos:
                if not isinstance(entry, dict):
                    continue
                path = entry.get("path")
                if not path:
                    continue
                path_list.append(path)
                video_id = entry.get("id") or self._legacy_hash_id(path)
                self._video_id_by_path[path] = video_id
                status_map[video_id] = entry.get("annotation_status", "not_annotated")
                ann_path = entry.get("annotation_path")
                if ann_path:
                    files_map[video_id] = ann_path
            config["videos"] = path_list
            config["video_annotation_status"] = status_map
            config["video_annotation_files"] = files_map
        else:
            # v1: string-list videos. Adopt the legacy hash id as the persisted
            # id (the v1 status/files maps are keyed by it), so the next save
            # writes it into the v2 manifest and it stays stable thereafter.
            for path in videos:
                self._video_id_by_path[str(path)] = self._legacy_hash_id(path)
        return config

    def resolve_path(self, relative_path):
        """
        Resolve a project-relative path to an absolute path.
        
        Args:
            relative_path (str): Project-relative path
            
        Returns:
            str: Absolute path or None if path cannot be resolved
        """
        if not self._project_path:
            return None
        
        # If already absolute, return as is
        if os.path.isabs(relative_path):
            return relative_path
        
        # Resolve relative path
        return os.path.join(self._project_path, relative_path)
