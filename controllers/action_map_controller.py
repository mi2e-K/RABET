# controllers/action_map_controller.py
import logging
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox, QMenu
from PySide6.QtGui import QAction

class ActionMapController(QObject):
    """
    Controller for managing key-to-behavior mappings.
    """
    
    def __init__(self, action_map_model, action_map_view):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing ActionMapController")
        
        self._model = action_map_model
        self._view = action_map_view

        # Optional ProjectModel reference used by the action-map change guard.
        # AppController assigns it once construction is done.
        self.project_model = None

        # Connect model signals
        self._connect_model_signals()
        
        # Connect view signals
        self._connect_view_signals()
        
        # Trigger initial view update now that connections are established
        self._model.initialize_view()
    
    def _connect_model_signals(self):
        """Connect signals from the model."""
        self._model.map_changed.connect(self.on_map_changed)
        # Add connection for active behaviors changed signal
        self._model.active_behaviors_changed.connect(self.on_active_behaviors_changed)
    
    def _connect_view_signals(self):
        """Connect signals from the view."""
        self._view.edit_mapping_requested.connect(self.on_edit_mapping_requested)
        self._view.remove_mapping_requested.connect(self.on_remove_mapping_requested)
    
    @Slot()
    def on_map_changed(self):
        """Handle action map changes."""
        # Update action map view with current mappings (+ per-key kind, 1.4.0)
        self._view.update_mappings(
            self._model.get_all_mappings(), self._model.get_all_kinds()
        )
        
        # Also update active behaviors display
        self._view.update_active_behaviors(self._model.get_active_behaviors())
        
        self.logger.debug("Action map view updated")
    
    @Slot()
    def on_active_behaviors_changed(self):
        """Handle changes to active behaviors."""
        # Update active behaviors display
        active_behaviors = self._model.get_active_behaviors()
        self._view.update_active_behaviors(active_behaviors)
        self.logger.debug(f"Active behaviors updated: {active_behaviors}")
    
    @Slot(str, str, str)
    def on_edit_mapping_requested(self, key, behavior, kind="state"):
        """
        Handle request to add or edit a mapping.

        Args:
            key (str): Key character
            behavior (str): Behavior label
            kind (str): "state" or "point" (1.4.0)
        """
        # Warn only when this redefines a key that already means something
        # else; mapping a new key is additive and safe.
        if self._edit_changes_meaning(key, behavior, kind):
            previous = self._model.get_behavior(key)
            if not self._confirm_map_change(
                f"Key '{key}' will change from '{previous}' to '{behavior}'."
            ):
                # Put the view back in sync with the unchanged model.
                self.on_map_changed()
                return

        # Add or update the mapping in the model
        if self._model.add_mapping(key, behavior, kind=kind):
            self.logger.info(f"Mapping added/updated: {key} -> {behavior} ({kind})")
    
    @Slot(str)
    def on_remove_mapping_requested(self, key):
        """
        Handle request to remove a mapping.
        
        Args:
            key (str): Key character
        """
        behavior = self._model.get_behavior(key)
        if behavior and not self._confirm_map_change(
            f"Key '{key}' ('{behavior}') will no longer be recordable."
        ):
            self.on_map_changed()  # Re-sync the view with the unchanged model.
            return

        # Remove the mapping from the model
        if self._model.remove_mapping(key):
            self.logger.info(f"Mapping removed: {key}")
    
    # --- Change guard (1.4.2) ---------------------------------------------
    #
    # Once a project holds annotations, changing what a key means splits the
    # dataset: recordings made afterwards are no longer directly comparable
    # with the ones already collected. The guard warns but never blocks —
    # fixing a typo or adding a behaviour mid-study is legitimate, and the
    # researcher is the one who can judge.

    def annotated_video_count(self):
        """Return the open project's annotated-video count (0 if none/no project)."""
        project_model = self.project_model
        if project_model is None:
            return 0
        try:
            if not project_model.is_project_open():
                return 0
            return project_model.get_annotated_video_count()
        except Exception as exc:
            self.logger.warning("Could not read annotation status: %s", exc)
            return 0

    def _edit_changes_meaning(self, key, behavior, kind):
        """Return whether an add/edit changes what an existing key means.

        Mapping a brand-new key is purely additive and never warned about;
        warning on it would train the user to dismiss the dialog.
        """
        current = self._model.get_behavior(key)
        if not current:
            return False  # New key: additive.
        if current != behavior:
            return True  # The key now records a different behaviour.
        current_kind = self._model.get_all_kinds().get(key, "state")
        return current_kind != kind  # state <-> point changes what is recorded.

    def _confirm_map_change(self, summary):
        """Confirm a change that could desynchronise a project's annotations.

        Args:
            summary (str): One line naming the specific change being made.

        Returns:
            bool: True to proceed (also when no project data is at risk).
        """
        count = self.annotated_video_count()
        if count == 0:
            return True

        videos = "1 video" if count == 1 else f"{count} videos"
        result = QMessageBox.question(
            self._view,
            "Project Already Has Annotations",
            f"{summary}\n\n"
            f"This project already has {videos} annotated. Existing annotation "
            "files are not changed, but recordings made from now on may use "
            "different key meanings, so they may not be comparable with the "
            "annotations already collected.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        proceed = result == QMessageBox.StandardButton.Yes
        if not proceed:
            self.logger.info("Action map change cancelled by guard: %s", summary)
        return proceed

    # --- Project scope (1.4.2) -------------------------------------------

    def enter_project_scope(self, map_path, snapshot_if_missing=True,
                            snapshot_always=False):
        """Bind the action map to a project's own map file.

        Delegates to the model; see ``ActionMapModel.enter_project_scope``.
        """
        return self._model.enter_project_scope(
            map_path,
            snapshot_if_missing=snapshot_if_missing,
            snapshot_always=snapshot_always,
        )

    def exit_project_scope(self):
        """Restore the global user action map after a project closes."""
        return self._model.exit_project_scope()

    def is_project_scoped(self):
        """Return whether the active map belongs to the open project."""
        return self._model.is_project_scoped()

    def get_mappings_snapshot(self):
        """Return (mappings, kinds) for comparing the map across a switch."""
        return (self._model.get_all_mappings(), self._model.get_all_kinds())

    def refresh_scope_display(self, project_name=""):
        """Update the panel heading to name the scope currently in use."""
        try:
            self._view.set_scope(
                project_name=project_name,
                project_scoped=self._model.is_project_scoped(),
            )
        except AttributeError:
            # Older/stub views without the heading; not worth failing over.
            self.logger.debug("View does not support scope display")

    @Slot()
    def load_action_map_dialog(self):
        """Open a dialog to load an action map from JSON."""
        file_path, _ = QFileDialog.getOpenFileName(
            self._view, "Load Action Map", "", "JSON Files (*.json)"
        )
        
        if file_path:
            # Confirm if there are existing mappings. When the open project
            # already holds annotations the guard's message supersedes this
            # one, so the user gets a single, more specific dialog.
            if self._model.get_all_mappings():
                if self.annotated_video_count():
                    if not self._confirm_map_change(
                        "Loading this file replaces every current key mapping."
                    ):
                        return
                else:
                    result = QMessageBox.question(
                        self._view,
                        "Existing Mappings",
                        "Loading will replace existing mappings. Continue?",
                        QMessageBox.Yes | QMessageBox.No
                    )

                    if result != QMessageBox.Yes:
                        return

            # Load the action map. auto_save=True persists it into whichever
            # scope is active: the open project's own map, or the global user
            # map when no project is bound (1.4.2).
            if self._model.load_from_json(file_path, auto_save=True):
                self.logger.info(f"Action map loaded from: {file_path}")
                if self._model.is_project_scoped():
                    scope_note = (
                        "\n\nThis becomes the open project's action map. "
                        "Your global action map is unchanged."
                    )
                else:
                    scope_note = ""
                QMessageBox.information(
                    self._view,
                    "Action Map Loaded",
                    f"Action map loaded successfully from {file_path}.{scope_note}"
                )
            else:
                self.logger.error(f"Failed to load action map from: {file_path}")
    
    @Slot()
    def save_action_map_dialog(self):
        """Open a dialog to save the action map to JSON."""
        # Check if there are any mappings to save
        if not self._model.get_all_mappings():
            QMessageBox.information(
                self._view,
                "No Mappings",
                "There are no mappings to save."
            )
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self._view, "Save Action Map", "", "JSON Files (*.json)"
        )
        
        if file_path:
            # Add .json extension if not present
            if not file_path.lower().endswith('.json'):
                file_path += '.json'
                
            # Save the action map
            if self._model.save_to_json(file_path):
                self.logger.info(f"Action map saved to: {file_path}")
                QMessageBox.information(
                    self._view,
                    "Action Map Saved",
                    f"Action map saved to {file_path}."
                )
            else:
                self.logger.error(f"Failed to save action map to: {file_path}")
    
    @Slot()
    def reset_to_default(self):
        """Reset action map to default configuration."""
        # With project annotations at stake the guard's message is the more
        # specific of the two, so it replaces the generic confirmation.
        if self.annotated_video_count():
            if not self._confirm_map_change(
                "Resetting replaces every current key mapping with the defaults."
            ):
                return
            result = QMessageBox.StandardButton.Yes
        else:
            # Confirm reset
            result = QMessageBox.question(
                self._view,
                "Reset to Default",
                "Are you sure you want to reset the action map to default settings?\n"
                "This will replace all current mappings.",
                QMessageBox.Yes | QMessageBox.No
            )

        if result == QMessageBox.Yes:
            if self._model.reset_to_default():
                QMessageBox.information(
                    self._view,
                    "Reset Complete",
                    "Action map has been reset to default settings."
                )
            else:
                QMessageBox.warning(
                    self._view,
                    "Reset Failed",
                    "Failed to reset action map to default settings."
                )
    
    def create_action_map_menu(self):
        """
        Create a menu with action map operations.
        
        Returns:
            QMenu: Menu with action map operations
        """
        menu = QMenu("Action Map", self._view)
        
        # Load action
        load_action = QAction("Load from file...", self._view)
        load_action.triggered.connect(self.load_action_map_dialog)
        menu.addAction(load_action)
        
        # Save action
        save_action = QAction("Save to file...", self._view)
        save_action.triggered.connect(self.save_action_map_dialog)
        menu.addAction(save_action)
        
        menu.addSeparator()
        
        # Reset to default action
        reset_action = QAction("Reset to default", self._view)
        reset_action.triggered.connect(self.reset_to_default)
        menu.addAction(reset_action)
        
        return menu