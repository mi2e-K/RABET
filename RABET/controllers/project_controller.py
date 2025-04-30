# controllers/project_controller.py
import logging
import os
from pathlib import Path
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QMessageBox

class ProjectController(QObject):
    """
    Controller for managing research projects.
    
    Coordinates between ProjectModel and ProjectView.
    """
    
    def __init__(self, project_model, project_view, video_controller, 
                 action_map_controller, annotation_controller, analysis_controller):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing ProjectController")
        
        self._model = project_model
        self._view = project_view
        
        # Store references to other controllers
        self._video_controller = video_controller
        self._action_map_controller = action_map_controller
        self._annotation_controller = annotation_controller
        self._analysis_controller = analysis_controller
        
        # Connect model signals
        self._connect_model_signals()
        
        # Connect view signals
        self._connect_view_signals()
    
    def _connect_model_signals(self):
        """Connect signals from the model."""
        self._model.project_created.connect(self.on_project_created)
        self._model.project_loaded.connect(self.on_project_loaded)
        self._model.project_saved.connect(self.on_project_saved)
        self._model.project_closed.connect(self.on_project_closed)
        self._model.error_occurred.connect(self.on_error)
    
    def _connect_view_signals(self):
        """Connect signals from the view."""
        self._view.create_project_requested.connect(self.on_create_project_requested)
        self._view.load_project_requested.connect(self.on_load_project_requested)
        self._view.save_project_requested.connect(self.on_save_project_requested)
        self._view.close_project_requested.connect(self.on_close_project_requested)
        
        self._view.description_changed.connect(self.on_description_changed)
        
        self._view.add_file_requested.connect(self.on_add_file_requested)
        self._view.remove_file_requested.connect(self.on_remove_file_requested)
        self._view.open_file_requested.connect(self.on_open_file_requested)
    
    @Slot(str)
    def on_project_created(self, project_path):
        """
        Handle project created event.
        
        Args:
            project_path (str): Path to the created project
        """
        self.logger.info(f"Project created: {project_path}")
        
        # Update view with project information
        self._update_view_with_project_info()
        
        # Show success message
        QMessageBox.information(
            self._view,
            "Project Created",
            f"Project created successfully at:\n{project_path}"
        )
    
    @Slot(str)
    def on_project_loaded(self, project_path):
        """
        Handle project loaded event.
        
        Args:
            project_path (str): Path to the loaded project
        """
        self.logger.info(f"Project loaded: {project_path}")
        
        # Update view with project information
        self._update_view_with_project_info()
    
    @Slot()
    def on_project_saved(self):
        """Handle project saved event."""
        self.logger.info("Project saved")
        
        # Update view with project information
        self._update_view_with_project_info()
        
        # Show success message
        QMessageBox.information(
            self._view,
            "Project Saved",
            "Project saved successfully."
        )
    
    @Slot()
    def on_project_closed(self):
        """Handle project closed event."""
        self.logger.info("Project closed")
        
        # Update view to show no project
        self._view.set_project_name("")
        self._view.set_project_path("")
        self._view.set_project_description("")
        self._view.set_project_dates("", "")
        
        # Clear file lists
        self._view.update_videos([])
        self._view.update_annotations([])
        self._view.update_action_maps([])
        self._view.update_analyses([])
    
    @Slot(str)
    def on_error(self, error_message):
        """
        Handle error event.
        
        Args:
            error_message (str): Error message
        """
        self.logger.error(f"Error: {error_message}")
        
        # Show error message
        QMessageBox.critical(
            self._view,
            "Error",
            error_message
        )
    
    @Slot(str, str, str)
    def on_create_project_requested(self, directory, name, description):
        """
        Handle create project requested event.
        
        Args:
            directory (str): Directory for the project
            name (str): Project name
            description (str): Project description
        """
        self.logger.debug(f"Create project requested: {name} at {directory}")
        
        # Check if we should close current project first
        if self._model.is_project_open():
            result = QMessageBox.question(
                self._view,
                "Close Current Project",
                "A project is currently open. Close it and create a new one?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if result != QMessageBox.StandardButton.Yes:
                return
            
            # Close current project
            self._model.close_project()
        
        # Create new project
        self._model.create_project(directory, name, description)
    
    @Slot(str)
    def on_load_project_requested(self, project_path):
        """
        Handle load project requested event.
        
        Args:
            project_path (str): Path to the project to load
        """
        self.logger.debug(f"Load project requested: {project_path}")
        
        # Check if we should close current project first
        if self._model.is_project_open():
            result = QMessageBox.question(
                self._view,
                "Close Current Project",
                "A project is currently open. Close it and load another one?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if result != QMessageBox.StandardButton.Yes:
                return
            
            # Close current project
            self._model.close_project()
        
        # Load project
        self._model.load_project(project_path)
    
    @Slot()
    def on_save_project_requested(self):
        """Handle save project requested event."""
        self.logger.debug("Save project requested")
        
        # Save project
        self._model.save_project()
    
    @Slot()
    def on_close_project_requested(self):
        """Handle close project requested event."""
        self.logger.debug("Close project requested")
        
        # Check if project has unsaved changes
        if self._model.is_modified():
            result = QMessageBox.question(
                self._view,
                "Save Changes",
                "The project has unsaved changes. Save before closing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            
            if result == QMessageBox.StandardButton.Cancel:
                return
            
            if result == QMessageBox.StandardButton.Yes:
                if not self._model.save_project():
                    # Save failed, don't close
                    return
        
        # Close project
        self._model.close_project()
    
    @Slot(str)
    def on_description_changed(self, description):
        """
        Handle description changed event.
        
        Args:
            description (str): New project description
        """
        self.logger.debug("Project description changed")
        
        # Update model
        self._model.set_project_description(description)
    
    @Slot(str, str)
    def on_add_file_requested(self, file_type, file_path):
        """
        Handle add file requested event.
        
        Args:
            file_type (str): Type of file (videos, annotations, action_maps, analyses)
            file_path (str): Path to the file
        """
        self.logger.debug(f"Add {file_type} requested: {file_path}")
        
        # Add file based on type
        if file_type == "videos":
            success = self._model.add_video(file_path)
        elif file_type == "annotations":
            success = self._model.add_annotation(file_path)
        elif file_type == "action_maps":
            success = self._model.add_action_map(file_path)
        elif file_type == "analyses":
            success = self._model.add_analysis(file_path)
        else:
            self.logger.error(f"Invalid file type: {file_type}")
            return
        
        if success:
            # Update view with new file lists
            self._update_file_lists()
            
            # Save project to persist changes
            self._model.save_project()
    
    @Slot(str, str)
    def on_remove_file_requested(self, file_type, file_path):
        """
        Handle remove file requested event.
        
        Args:
            file_type (str): Type of file (videos, annotations, action_maps, analyses)
            file_path (str): Path to the file
        """
        self.logger.debug(f"Remove {file_type} requested: {file_path}")
        
        # Remove file
        if self._model.remove_file(file_path, file_type):
            # Update view with new file lists
            self._update_file_lists()
            
            # Save project to persist changes
            self._model.save_project()
    
    @Slot(str, str)
    def on_open_file_requested(self, file_type, file_path):
        """
        Handle open file requested event.
        
        Args:
            file_type (str): Type of file (videos, annotations, action_maps, analyses)
            file_path (str): Path to the file
        """
        self.logger.debug(f"Open {file_type} requested: {file_path}")
        
        # Resolve path if it's relative
        resolved_path = self._model.resolve_path(file_path)
        
        if not resolved_path:
            QMessageBox.warning(
                self._view,
                "Cannot Open File",
                f"Failed to resolve file path:\n{file_path}"
            )
            return
        
        # Open file based on type
        if file_type == "videos":
            self._open_video(resolved_path)
        elif file_type == "annotations":
            self._open_annotation(resolved_path)
        elif file_type == "action_maps":
            self._open_action_map(resolved_path)
        elif file_type == "analyses":
            self._open_analysis(resolved_path)
        else:
            self.logger.error(f"Invalid file type: {file_type}")
    
    def _open_video(self, video_path):
        """
        Open a video file.
        
        Args:
            video_path (str): Path to the video file
        """
        # Use video controller to load the video
        if not self._video_controller.load_video(video_path):
            QMessageBox.warning(
                self._view,
                "Cannot Open Video",
                f"Failed to open video file:\n{video_path}"
            )
    
    def _open_annotation(self, annotation_path):
        """
        Open an annotation file.
        
        Args:
            annotation_path (str): Path to the annotation file
        """
        # Use annotation controller to import the annotation
        if not self._annotation_controller:
            QMessageBox.warning(
                self._view,
                "Not Implemented",
                "Opening annotation files directly is not yet implemented."
            )
            return
        
        # Alternative: Let the OS open the file with default application
        self._open_with_default_application(annotation_path)
    
    def _open_action_map(self, action_map_path):
        """
        Open an action map file.
        
        Args:
            action_map_path (str): Path to the action map file
        """
        # Use action map controller to load the action map
        if not self._action_map_controller:
            QMessageBox.warning(
                self._view,
                "Not Implemented",
                "Opening action map files directly is not yet implemented."
            )
            return
        
        # Alternative: Let the OS open the file with default application
        self._open_with_default_application(action_map_path)
    
    def _open_analysis(self, analysis_path):
        """
        Open an analysis file.
        
        Args:
            analysis_path (str): Path to the analysis file
        """
        # Use analysis controller to load the analysis
        if not self._analysis_controller:
            QMessageBox.warning(
                self._view,
                "Not Implemented",
                "Opening analysis files directly is not yet implemented."
            )
            return
        
        # Alternative: Let the OS open the file with default application
        self._open_with_default_application(analysis_path)
    
    def _open_with_default_application(self, file_path):
        """
        Open a file with the default application.
        
        Args:
            file_path (str): Path to the file
        """
        import subprocess
        import platform
        
        try:
            if platform.system() == 'Windows':
                os.startfile(file_path)
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', file_path], check=True)
            else:  # Linux
                subprocess.run(['xdg-open', file_path], check=True)
        except Exception as e:
            self.logger.error(f"Failed to open file with default application: {str(e)}")
            QMessageBox.warning(
                self._view,
                "Cannot Open File",
                f"Failed to open file with default application:\n{file_path}\n\nError: {str(e)}"
            )
    
    def _update_view_with_project_info(self):
        """Update view with current project information."""
        # Update project info
        self._view.set_project_name(self._model.get_project_name())
        self._view.set_project_path(self._model.get_project_path())
        self._view.set_project_description(self._model.get_project_description())
        
        # Update dates
        self._view.set_project_dates(
            self._model.get_project_creation_date(),
            self._model.get_project_modification_date()
        )
        
        # Update file lists
        self._update_file_lists()
    
    def _update_file_lists(self):
        """Update view with current file lists."""
        self._view.update_videos(self._model.get_videos())
        self._view.update_annotations(self._model.get_annotations())
        self._view.update_action_maps(self._model.get_action_maps())
        self._view.update_analyses(self._model.get_analyses())