# controllers/project_controller.py - Updated for enhanced video management and annotation workflow
import logging
import os
from pathlib import Path
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QMessageBox

class ProjectController(QObject):
    """
    Controller for managing research projects.
    
    Coordinates between ProjectModel and ProjectView.
    Handles video annotation workflow and project file management.
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
        
        # Connect new annotation workflow signals
        self._view.annotate_video_requested.connect(self.on_annotate_video_requested)
        self._view.annotate_random_requested.connect(self.on_annotate_random_requested)
    
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
        
        # Show auto-closing success message
        from utils.auto_close_message import AutoCloseMessageBox
        AutoCloseMessageBox.information(
            self._view,
            "Project Saved",
            "Project saved successfully.",
            timeout=1000  # 1 second timeout
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
    
    @Slot(str, str, bool)
    def on_add_file_requested(self, file_type, file_path, copy_to_project=False):
        """
        Handle add file requested event.
        
        Args:
            file_type (str): Type of file (videos, annotations, action_maps, analyses)
            file_path (str): Path to the file
            copy_to_project (bool): Whether to copy the file to the project directory
        """
        self.logger.debug(f"Add {file_type} requested: {file_path} (copy={copy_to_project})")
        
        # Add file based on type
        if file_type == "videos":
            success = self._model.add_video(file_path, copy_to_project)
        elif file_type == "annotations":
            success = self._model.add_annotation(file_path, copy_to_project)
        elif file_type == "action_maps":
            success = self._model.add_action_map(file_path, copy_to_project)
        elif file_type == "analyses":
            success = self._model.add_analysis(file_path, copy_to_project)
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
    
    @Slot(str)
    def on_annotate_video_requested(self, video_path):
        """
        Handle annotate video requested event.
        
        Args:
            video_path (str): Path to the video to annotate
        """
        self.logger.info(f"Annotate video requested: {video_path}")
        
        # Resolve path if it's relative
        resolved_path = self._model.resolve_path(video_path)
        
        if not resolved_path:
            QMessageBox.warning(
                self._view,
                "Cannot Annotate Video",
                f"Failed to resolve video path:\n{video_path}"
            )
            return
        
        # Load the video for annotation
        self.annotate_video(resolved_path)
    
    @Slot()
    def on_annotate_random_requested(self):
        """Handle annotate random video requested event."""
        self.logger.info("Annotate random video requested")
        
        # Get a random unannotated video
        video_path = self._model.select_random_unannotated_video()
        
        if not video_path:
            QMessageBox.information(
                self._view,
                "No Unannotated Videos",
                "There are no unannotated videos in the project.\n\n"
                "To annotate a specific video, select it from the video list."
            )
            return
        
        # Resolve path if it's relative
        resolved_path = self._model.resolve_path(video_path)
        
        if not resolved_path:
            QMessageBox.warning(
                self._view,
                "Cannot Annotate Video",
                f"Failed to resolve video path:\n{video_path}"
            )
            return
        
        # Let the user know which video was selected
        video_name = os.path.basename(video_path)
        QMessageBox.information(
            self._view,
            "Random Video Selected",
            f"Selected video: {video_name}\n\nYou will now enter annotation mode."
        )
        
        # Load the video for annotation
        self.annotate_video(resolved_path)
    
    def annotate_video(self, video_path):
        """
        Load a video for annotation.
        
        Args:
            video_path (str): Path to the video
        """
        # Prepare for annotation
        # Get video ID (basename without extension)
        video_id = os.path.splitext(os.path.basename(video_path))[0]
        
        # Tell the annotation controller this is a project video being annotated
        self._annotation_controller.set_project_mode(True)
        self._annotation_controller.set_current_video_id(video_id)
        
        # Set annotation export path in the project directory
        if self._model.is_project_open():
            project_path = self._model.get_project_path()
            annotations_dir = os.path.join(project_path, "annotations")
            export_path = os.path.join(annotations_dir, f"{video_id}_annotations.csv")
            self._annotation_controller.set_auto_export_path(export_path)
            
            # Tell annotation controller about the project model for status updates
            self._annotation_controller.set_project_model(self._model)
        
        # Load the video using video controller
        if not self._video_controller.load_video(video_path):
            QMessageBox.warning(
                self._view,
                "Cannot Annotate Video",
                f"Failed to load video for annotation:\n{video_path}"
            )
            return

        # Since automatic switching is not working reliably, show an instruction dialog
        main_window = self._view.parent()
        video_name = os.path.basename(video_path)
        
        # Create a more helpful message box
        switch_msg = QMessageBox(self._view)
        switch_msg.setWindowTitle("Switch to Annotation Mode")
        switch_msg.setIcon(QMessageBox.Icon.Information)
        
        switch_msg.setText(f"<b>Video '{video_name}' is ready for annotation!</b>")
        switch_msg.setInformativeText(
            "Please click the <b>Annotation Mode</b> button in the toolbar to begin annotating.<br><br>"
            "<span style='color: #FF9900; font-weight: bold;'>→ Look for 'Annotation Mode' in the toolbar at the top ←</span><br><br>"
            "The video has been loaded and is waiting for you."
        )
        
        # Use a more helpful button
        switch_msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        switch_msg.button(QMessageBox.StandardButton.Ok).setText("Got it")
        
        # Momentarily highlight the annotation mode button in the toolbar
        if hasattr(main_window, 'annotation_mode_toolbar_action'):
            try:
                # Save original style
                original_style = main_window.annotation_mode_toolbar_action.text()
                
                # Set highlighted style
                main_window.annotation_mode_toolbar_action.setText("➡️ ANNOTATION MODE ⬅️")
                main_window.annotation_mode_toolbar_action.setStyleSheet("background-color: #FFFF00; font-weight: bold;")
                
                # Process events to update the UI
                from PySide6.QtCore import QCoreApplication
                QCoreApplication.processEvents()
                
                # Show the message
                switch_msg.exec()
                
                # Restore original style after dialog is closed
                main_window.annotation_mode_toolbar_action.setText(original_style)
                main_window.annotation_mode_toolbar_action.setStyleSheet("")
                
                return
            except Exception as e:
                self.logger.error(f"Error highlighting annotation button: {str(e)}")
        
        # Fallback if highlighting doesn't work
        switch_msg.exec()
    
    def _open_video(self, video_path):
        """
        Open a video file with the system's default video player.
        
        Args:
            video_path (str): Path to the video file
        """
        # Use system's default video player instead of the app's player
        self._open_with_default_application(video_path)
    
    def _open_annotation(self, annotation_path):
        """
        Open an annotation file.
        
        Args:
            annotation_path (str): Path to the annotation file
        """
        # Let the OS open the file with default application
        self._open_with_default_application(annotation_path)
    
    def _open_action_map(self, action_map_path):
        """
        Open an action map file.
        
        Args:
            action_map_path (str): Path to the action map file
        """
        # Let the OS open the file with default application
        self._open_with_default_application(action_map_path)
    
    def _open_analysis(self, analysis_path):
        """
        Open an analysis file.
        
        Args:
            analysis_path (str): Path to the analysis file
        """
        # Let the OS open the file with default application
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
        # Get annotation status for videos
        annotation_status = self._model.get_video_annotation_status()
        
        # Update file lists
        self._view.update_videos(self._model.get_videos(), annotation_status)
        self._view.update_annotations(self._model.get_annotations())
        self._view.update_action_maps(self._model.get_action_maps())
        self._view.update_analyses(self._model.get_analyses())