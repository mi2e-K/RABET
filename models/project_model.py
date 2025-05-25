# models/project_model.py - Updated for enhanced video management and annotation tracking
import json
import logging
import os
import random
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
            "analyses": []
        }
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
                "video_annotation_status": {}  # New field to track annotation status
            }
            
            # Save project configuration
            self._save_project_config(project_dir)
            
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
            
            # Ensure video_annotation_status exists (for backwards compatibility)
            if "video_annotation_status" not in self._project_config:
                self._project_config["video_annotation_status"] = {}
                self._is_modified = True
            
            # Update current project
            self._project_path = str(project_dir)
            self._project_name = self._project_config.get("name", 
                                                          project_dir.name)
            
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
            # Ensure the video_annotation_status field exists
            if "video_annotation_status" not in self._project_config:
                self._project_config["video_annotation_status"] = {}
                self._is_modified = True
            
            # Get all annotation files
            annotation_files = self._project_config.get("annotations", [])
            
            # Map to store base filenames of annotations
            annotation_basenames = set()
            for annotation_path in annotation_files:
                basename = os.path.splitext(os.path.basename(annotation_path))[0]
                # Remove '_annotations' suffix if present
                if basename.endswith("_annotations"):
                    basename = basename[:-12]
                annotation_basenames.add(basename)
            
            # Check each video
            for video_path in self._project_config.get("videos", []):
                video_id = self._get_video_id(video_path)
                
                # If video doesn't have a status yet or status is "not_annotated"
                current_status = self._project_config["video_annotation_status"].get(video_id, "not_annotated")
                if current_status == "not_annotated":
                    # Check if an annotation file with matching name exists
                    if video_id in annotation_basenames:
                        self._project_config["video_annotation_status"][video_id] = "annotated"
                        self._is_modified = True
                        self.logger.info(f"Updated annotation status for video {video_id} to 'annotated'")
            
            if self._is_modified:
                self.logger.info("Updated annotation status based on existing files")
        except Exception as e:
            self.logger.error(f"Error updating annotation status: {str(e)}")
    
    def _get_video_id(self, video_path):
        """
        Get a unique identifier for a video from its path.
        
        Args:
            video_path (str): Path to the video file
            
        Returns:
            str: Video identifier (basename without extension)
        """
        return os.path.splitext(os.path.basename(video_path))[0]
    
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
                "video_annotation_status": {}
            }
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
            
            # Initialize annotation status for this video
            video_id = self._get_video_id(video_path)
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
                # Store absolute path
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
                
                # Update annotation status for the corresponding video
                if "video_annotation_status" not in self._project_config:
                    self._project_config["video_annotation_status"] = {}
                
                # Mark the video as annotated
                self._project_config["video_annotation_status"][base_name] = "annotated"
                self._is_modified = True
                
                self.logger.debug(f"Updated annotation status for video: {base_name}")
            
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
            
            # If removing a video, update its annotation status
            if file_type == "videos":
                video_id = self._get_video_id(file_path)
                if "video_annotation_status" in self._project_config and video_id in self._project_config["video_annotation_status"]:
                    del self._project_config["video_annotation_status"][video_id]
            
            # If removing an annotation, update the corresponding video's annotation status
            elif file_type == "annotations":
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                if base_name.endswith("_annotations"):
                    base_name = base_name[:-12]
                
                if "video_annotation_status" in self._project_config and base_name in self._project_config["video_annotation_status"]:
                    self._project_config["video_annotation_status"][base_name] = "not_annotated"
            
            # Remove file from project
            self._project_config[file_type].remove(file_path)
            self._is_modified = True
            
            # If file is in project directory, delete it
            if file_path.startswith(file_type):
                full_path = os.path.join(self._project_path, file_path)
                try:
                    Path(full_path).unlink()
                except:
                    # Don't fail if file can't be deleted
                    self.logger.warning(f"Failed to delete file: {full_path}")
            
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
                        If video_path is None, returns a dictionary of all video
                        annotation statuses {video_id: status}.
        """
        if not self._project_path:
            return {} if video_path is None else "not_annotated"
        
        # Ensure video_annotation_status exists
        if "video_annotation_status" not in self._project_config:
            self._project_config["video_annotation_status"] = {}
            self._is_modified = True
        
        # Return status for all videos
        if video_path is None:
            return self._project_config["video_annotation_status"].copy()
        
        # Return status for specific video
        video_id = self._get_video_id(video_path)
        return self._project_config["video_annotation_status"].get(video_id, "not_annotated")
    
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
        
        # Set status
        video_id = self._get_video_id(video_path)
        self._project_config["video_annotation_status"][video_id] = status
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
        
        for video_path in self._project_config.get("videos", []):
            if self._get_video_id(video_path) == video_id:
                return video_path
        
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
        
        # Get annotation status
        status_dict = self.get_video_annotation_status()
        
        # Filter unannotated videos
        unannotated_videos = []
        for video_path in videos:
            video_id = self._get_video_id(video_path)
            if status_dict.get(video_id, "not_annotated") == "not_annotated":
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
        return self._file_manager.save_json(self._project_config, config_file)
    
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