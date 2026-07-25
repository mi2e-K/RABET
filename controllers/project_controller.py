# controllers/project_controller.py - Updated for enhanced video management and annotation workflow
import logging
import os
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox

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
        self._suppress_next_saved_message = False
        
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

        # Freeze the ethogram in use right now into the project, so every
        # video in it is annotated with the same key->behaviour mapping
        # regardless of what the global map is changed to later (1.4.2).
        bound = self._bind_current_action_map_to_project()

        # Update view with project information
        self._update_view_with_project_info()

        # Show success message
        extra = (
            "\n\nThe current action map has been saved into this project and "
            "will be used whenever it is open."
            if bound else ""
        )
        QMessageBox.information(
            self._view,
            "Project Created",
            f"Project created successfully at:\n{project_path}{extra}"
        )

    def _bind_current_action_map_to_project(self):
        """Snapshot the active action map into the project and bind it.

        Returns:
            bool: True if the project now has its own action map.
        """
        if not self._model.is_project_open():
            return False

        rel_path = self._model.get_default_action_map_rel_path()
        abs_path = self._model.resolve_path(rel_path)

        try:
            # snapshot_always: bind the map the user is actually looking at.
            # A leftover project_action_map.json at that path must not be
            # adopted silently in its place.
            if not self._action_map_controller.enter_project_scope(
                abs_path, snapshot_always=True
            ):
                self.logger.warning("Could not bind action map to project")
                return False
        except Exception as exc:
            self.logger.warning("Failed to bind project action map: %s", exc)
            return False

        if not self._model.set_action_map(rel_path):
            return False
        self._save_project_silently()
        return True

    @Slot()
    def bind_current_action_map_dialog(self):
        """Bind the currently active action map to the open project.

        The opt-in path for projects created before 1.4.2, which have no bound
        map. Deliberately explicit: RABET cannot know whether the map loaded
        right now is the one those videos were annotated with, so it must not
        guess on the user's behalf.
        """
        if not self._model.is_project_open():
            QMessageBox.information(
                self._view,
                "No Project Open",
                "Open a project first to give it its own action map.",
            )
            return

        if self._action_map_controller.is_project_scoped():
            QMessageBox.information(
                self._view,
                "Already Using a Project Action Map",
                "This project already has its own action map. Edits you make "
                "while it is open are saved into the project.",
            )
            return

        # Naming the count makes the risk concrete: the more annotations are
        # already in the project, the more there is to be inconsistent with.
        annotated = self._model.get_annotated_video_count()
        if annotated:
            videos = "1 video" if annotated == 1 else f"{annotated} videos"
            stakes = (
                f"\n\nThis project already has {videos} annotated. Existing "
                "annotation files are not changed, but make sure the mappings "
                "shown now are the ones those recordings were made with."
            )
        else:
            stakes = (
                "\n\nMake sure the mappings shown now are the ones you want "
                "this project annotated with."
            )

        result = QMessageBox.question(
            self._view,
            "Use Current Action Map for This Project",
            "Save the current action map into this project and use it "
            f"whenever the project is open?{stakes}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        if self._bind_current_action_map_to_project():
            self._update_view_with_project_info()
            QMessageBox.information(
                self._view,
                "Project Action Map Set",
                "This project now has its own action map.",
            )
        else:
            QMessageBox.warning(
                self._view,
                "Could Not Set Project Action Map",
                "Failed to save the action map into the project.",
            )

    def _apply_project_action_map(self):
        """Enter the open project's action map scope, if it has one.

        Projects created before 1.4.2 have no bound map; they keep using the
        global user map so their behaviour is unchanged.
        """
        map_path = self._model.get_action_map_path()
        if not map_path:
            self.logger.info(
                "Project has no bound action map; using the global user map."
            )
            return False

        if not os.path.exists(map_path):
            self.logger.warning(
                "Project action map is missing: %s; using the global user map.",
                map_path,
            )
            QMessageBox.warning(
                self._view,
                "Project Action Map Missing",
                f"This project's action map could not be found:\n{map_path}\n\n"
                "The global action map will be used instead. Check the key "
                "mappings before annotating.",
            )
            return False

        if not self._action_map_controller.enter_project_scope(
            map_path, snapshot_if_missing=False
        ):
            QMessageBox.warning(
                self._view,
                "Project Action Map Not Loaded",
                f"This project's action map could not be loaded:\n{map_path}\n\n"
                "The global action map will be used instead. Check the key "
                "mappings before annotating.",
            )
            return False

        self.logger.info("Applied project action map: %s", map_path)
        return True

    def _notify_if_action_map_changed(self, before_map, before_kinds):
        """Tell the user when opening this project changed what the keys mean.

        Deliberately silent when the map is identical to the one already in
        use: a notice on every project open would be dismissed unread, and
        then missed on the one switch that mattered. Firing only on a real
        change keeps the interruption meaningful.
        """
        after_map, after_kinds = self._action_map_controller.get_mappings_snapshot()
        if after_map == before_map and after_kinds == before_kinds:
            return

        changed = []
        for key in sorted(set(before_map) | set(after_map)):
            was = before_map.get(key)
            now = after_map.get(key)
            if was == now and before_kinds.get(key) == after_kinds.get(key):
                continue
            if was is None:
                changed.append(f"  '{key}': (unused) -> {now}")
            elif now is None:
                changed.append(f"  '{key}': {was} -> (unused)")
            else:
                changed.append(f"  '{key}': {was} -> {now}")

        # Keep the dialog readable; the panel holds the authoritative list.
        shown = changed[:8]
        if len(changed) > len(shown):
            shown.append(f"  ...and {len(changed) - len(shown)} more")

        project_name = self._model.get_project_name() or "this project"
        if self._action_map_controller.is_project_scoped():
            lead = (
                f"Opening '{project_name}' switched the action map to the one "
                "saved in it, so some keys now record different behaviours:"
            )
        else:
            # Reached when the previous project was bound and this one is not:
            # the map reverted to the global one on the way in.
            lead = (
                f"'{project_name}' has no action map of its own, so the global "
                "one is now in use and some keys record different behaviours:"
            )

        QMessageBox.information(
            self._view,
            "Action Map Changed",
            lead
            + "\n\n"
            + "\n".join(shown)
            + "\n\nCheck the Action Map panel before recording.",
        )
        self.logger.info("Notified user of %d action map changes", len(changed))
    
    @Slot(str)
    def on_project_loaded(self, project_path):
        """
        Handle project loaded event.
        
        Args:
            project_path (str): Path to the loaded project
        """
        self.logger.info(f"Project loaded: {project_path}")

        # Switch to the project's own action map before anything can be
        # annotated, so the keys mean what this project says they mean (1.4.2).
        # Snapshot around the whole switch, not just the bound-map branch:
        # going from a bound project back to an unbound one also changes what
        # the keys mean, and that path would otherwise stay silent.
        before_map, before_kinds = self._action_map_controller.get_mappings_snapshot()
        self._apply_project_action_map()
        self._notify_if_action_map_changed(before_map, before_kinds)

        # Update view with project information
        self._update_view_with_project_info()

        # Offer to relink any videos whose files could not be located (PR-S3).
        self._check_and_offer_relink()

    def _check_and_offer_relink(self):
        """After load, ask the user to locate any missing video files.

        Relink keeps each video's id, so annotation status/links are preserved.
        A partial content hash guards against picking the wrong file.
        """
        try:
            missing = self._model.get_missing_videos()
        except Exception:
            return
        if not missing:
            return

        reply = QMessageBox.question(
            self._view,
            "Missing videos",
            f"{len(missing)} video(s) referenced by this project could not be "
            "found (they may have been moved or renamed).\n\n"
            "Locate them now?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        relinked = 0
        for stored in missing:
            if self._prompt_relink_single(stored):
                relinked += 1
        if relinked:
            self._model.save_project()
            self._update_view_with_project_info()

    def _prompt_relink_single(self, stored_path):
        """Prompt for a replacement file for one missing video; relink if given.

        Returns True if the video was relinked. Honours the content-hash check:
        a mismatch asks for explicit confirmation before forcing the relink.
        """
        name = os.path.basename(stored_path)
        new_path, _ = QFileDialog.getOpenFileName(
            self._view,
            f"Locate '{name}'",
            "",
            "Video files (*.mp4 *.avi *.mov *.mkv *.wmv *.flv);;All files (*.*)",
        )
        if not new_path:
            return False

        match = self._model.content_hash_matches(stored_path, new_path)
        if match is False:
            proceed = QMessageBox.warning(
                self._view,
                "Content mismatch",
                f"The selected file does not look like the same video as "
                f"'{name}'.\n\nRelink anyway?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if proceed != QMessageBox.Yes:
                return False
            return self._model.relink_video(stored_path, new_path, verify_hash=False)
        return self._model.relink_video(stored_path, new_path, verify_hash=True)

    @Slot()
    def on_project_saved(self):
        """Handle project saved event."""
        self.logger.info("Project saved")
        
        # Update view with project information
        self._update_view_with_project_info()

        if self._suppress_next_saved_message:
            self._suppress_next_saved_message = False
            return
        
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

        # Hand the action map back to global scope so the next non-project
        # session uses the user's own map, not this project's (1.4.2).
        try:
            self._action_map_controller.exit_project_scope()
        except Exception as exc:
            self.logger.warning("Failed to leave project action map scope: %s", exc)
        # Drop the project name from the panel heading now that the global
        # map is back in use.
        self._refresh_action_map_scope_display()

        if hasattr(self._video_controller, 'close_video'):
            self._video_controller.close_video()
        if hasattr(self._annotation_controller, 'clear_project_context'):
            self._annotation_controller.clear_project_context()
        
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

    def _save_project_silently(self):
        """Persist project changes without showing a transient success popup."""
        self._suppress_next_saved_message = True
        success = self._model.save_project()
        if not success:
            self._suppress_next_saved_message = False
        return success
    
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
            self._save_project_silently()
    
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
            self._save_project_silently()
    
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
        self.annotate_video(resolved_path, video_path)
    
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
        self.annotate_video(resolved_path, video_path)
    
    def annotate_video(self, video_path, project_video_ref=None):
        """
        Load a video for annotation.
        
        Args:
            video_path (str): Resolved absolute path to the video
            project_video_ref (str, optional): Stored project reference for the video
        """
        # Prepare for annotation
        project_video_ref = project_video_ref or video_path
        
        # Tell the annotation controller this is a project video being annotated
        self._annotation_controller.set_project_mode(True)
        self._annotation_controller.set_current_video_id(project_video_ref)
        
        # Set annotation export path in the project directory
        if self._model.is_project_open():
            project_path = self._model.get_project_path()
            annotation_rel_path = self._model.get_annotation_relative_path_for_video(
                project_video_ref
            )
            export_path = os.path.join(project_path, annotation_rel_path)
            self._annotation_controller.set_auto_export_path(export_path)
            if self._model.is_modified():
                self._save_project_silently()
            
            # Tell annotation controller about the project model for status updates
            self._annotation_controller.set_project_model(self._model)

        # Switch to the annotation page before loading. Under the legacy
        # VLC backend this was necessary so libvlc could bind to a
        # visible window handle; under 1.3.1's PyAV backend the only
        # reason left is UX (the user should already be on the
        # annotation view by the time the first frame paints).
        main_window = self._view.window()
        if hasattr(main_window, 'switch_to_video_mode'):
            main_window.switch_to_video_mode()
        elif hasattr(main_window, 'switch_to_view'):
            main_window.switch_to_view("Annotation")
        
        # Load the video using video controller
        if not self._video_controller.load_video(video_path, preserve_project_context=True):
            QMessageBox.warning(
                self._view,
                "Cannot Annotate Video",
                f"Failed to load video for annotation:\n{video_path}"
            )
            return

        video_name = os.path.basename(video_path)
        if hasattr(main_window, 'set_status_message'):
            main_window.set_status_message(f"Ready to annotate: {video_name}")
    
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
        
        # Name the active action map scope in the annotation panel (1.4.2).
        self._refresh_action_map_scope_display()

        # Update file lists
        self._update_file_lists()

    def _refresh_action_map_scope_display(self):
        """Keep the Action Map panel heading in step with the open project."""
        try:
            self._action_map_controller.refresh_scope_display(
                self._model.get_project_name() or ""
            )
        except Exception as exc:
            self.logger.debug("Could not refresh action map scope display: %s", exc)
    
    def _update_file_lists(self):
        """Update view with current file lists."""
        # Get annotation status for videos
        annotation_status = self._model.get_video_annotation_status()
        
        # Update file lists
        self._view.update_videos(self._model.get_videos(), annotation_status)
        self._view.update_annotations(self._model.get_annotations())
        self._view.update_action_maps(self._model.get_action_maps())
        self._view.update_analyses(self._model.get_analyses())
