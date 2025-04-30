# views/project_view.py
import logging
import os
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QTabWidget, QLabel, QLineEdit, QTextEdit, QFileDialog,
    QTreeWidget, QTreeWidgetItem, QMessageBox, QMenu, QHeaderView,
    QDialog, QDialogButtonBox, QFormLayout, QCheckBox
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QAction, QIcon, QCursor

class ProjectView(QWidget):
    """
    View for managing research projects containing related videos,
    annotations, action maps, and analyses.
    
    Signals:
        create_project_requested: Emitted when create project is requested
        load_project_requested: Emitted when load project is requested
        save_project_requested: Emitted when save project is requested
        close_project_requested: Emitted when close project is requested
        description_changed: Emitted when project description is changed
        add_file_requested: Emitted when add file is requested (file_type, path)
        remove_file_requested: Emitted when remove file is requested (file_type, path)
        open_file_requested: Emitted when open file is requested (file_type, path)
    """
    
    create_project_requested = Signal(str, str, str)  # directory, name, description
    load_project_requested = Signal(str)              # project path
    save_project_requested = Signal()
    close_project_requested = Signal()
    
    description_changed = Signal(str)
    
    add_file_requested = Signal(str, str)    # file_type, path
    remove_file_requested = Signal(str, str) # file_type, path
    open_file_requested = Signal(str, str)   # file_type, path
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing ProjectView")
        
        self.setup_ui()
        self.connect_signals()
    
    def setup_ui(self):
        """Set up user interface."""
        # Main layout
        self.layout = QVBoxLayout(self)
        
        # Project info section
        self.info_layout = QVBoxLayout()
        
        # Project name and path
        self.header_layout = QHBoxLayout()
        
        self.project_name_label = QLabel("No Project Open")
        self.project_name_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.header_layout.addWidget(self.project_name_label, 1)
        
        self.info_layout.addLayout(self.header_layout)
        
        # Project path
        self.project_path_label = QLabel("")
        self.project_path_label.setStyleSheet("font-style: italic; color: #666;")
        self.info_layout.addWidget(self.project_path_label)
        
        # Project buttons
        self.button_layout = QHBoxLayout()
        
        self.create_button = QPushButton("Create Project")
        self.button_layout.addWidget(self.create_button)
        
        self.load_button = QPushButton("Load Project")
        self.button_layout.addWidget(self.load_button)
        
        self.save_button = QPushButton("Save Project")
        self.save_button.setEnabled(False)
        self.button_layout.addWidget(self.save_button)
        
        self.close_button = QPushButton("Close Project")
        self.close_button.setEnabled(False)
        self.button_layout.addWidget(self.close_button)
        
        self.info_layout.addLayout(self.button_layout)
        
        # Project description
        self.description_label = QLabel("Description:")
        self.info_layout.addWidget(self.description_label)
        
        self.description_text = QTextEdit()
        self.description_text.setMaximumHeight(80)
        self.description_text.setEnabled(False)
        self.info_layout.addWidget(self.description_text)
        
        # Add info section to main layout
        self.layout.addLayout(self.info_layout)
        
        # Project content tabs
        self.content_tabs = QTabWidget()
        
        # Videos tab
        self.videos_widget = QWidget()
        self.videos_layout = QVBoxLayout(self.videos_widget)
        
        # Videos tree
        self.videos_tree = QTreeWidget()
        self.videos_tree.setHeaderLabels(["Name", "Path"])
        self.videos_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.videos_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.videos_layout.addWidget(self.videos_tree)
        
        # Videos buttons
        self.videos_button_layout = QHBoxLayout()
        
        self.add_video_button = QPushButton("Add Video")
        self.add_video_button.setEnabled(False)
        self.videos_button_layout.addWidget(self.add_video_button)
        
        self.videos_button_layout.addStretch()
        
        self.videos_layout.addLayout(self.videos_button_layout)
        
        # Add videos tab to content tabs
        self.content_tabs.addTab(self.videos_widget, "Videos")
        
        # Annotations tab
        self.annotations_widget = QWidget()
        self.annotations_layout = QVBoxLayout(self.annotations_widget)
        
        # Annotations tree
        self.annotations_tree = QTreeWidget()
        self.annotations_tree.setHeaderLabels(["Name", "Path"])
        self.annotations_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.annotations_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.annotations_layout.addWidget(self.annotations_tree)
        
        # Annotations buttons
        self.annotations_button_layout = QHBoxLayout()
        
        self.add_annotation_button = QPushButton("Add Annotation")
        self.add_annotation_button.setEnabled(False)
        self.annotations_button_layout.addWidget(self.add_annotation_button)
        
        self.annotations_button_layout.addStretch()
        
        self.annotations_layout.addLayout(self.annotations_button_layout)
        
        # Add annotations tab to content tabs
        self.content_tabs.addTab(self.annotations_widget, "Annotations")
        
        # Action Maps tab
        self.action_maps_widget = QWidget()
        self.action_maps_layout = QVBoxLayout(self.action_maps_widget)
        
        # Action Maps tree
        self.action_maps_tree = QTreeWidget()
        self.action_maps_tree.setHeaderLabels(["Name", "Path"])
        self.action_maps_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.action_maps_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.action_maps_layout.addWidget(self.action_maps_tree)
        
        # Action Maps buttons
        self.action_maps_button_layout = QHBoxLayout()
        
        self.add_action_map_button = QPushButton("Add Action Map")
        self.add_action_map_button.setEnabled(False)
        self.action_maps_button_layout.addWidget(self.add_action_map_button)
        
        self.action_maps_button_layout.addStretch()
        
        self.action_maps_layout.addLayout(self.action_maps_button_layout)
        
        # Add action maps tab to content tabs
        self.content_tabs.addTab(self.action_maps_widget, "Action Maps")
        
        # Analyses tab
        self.analyses_widget = QWidget()
        self.analyses_layout = QVBoxLayout(self.analyses_widget)
        
        # Analyses tree
        self.analyses_tree = QTreeWidget()
        self.analyses_tree.setHeaderLabels(["Name", "Path"])
        self.analyses_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.analyses_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.analyses_layout.addWidget(self.analyses_tree)
        
        # Analyses buttons
        self.analyses_button_layout = QHBoxLayout()
        
        self.add_analysis_button = QPushButton("Add Analysis")
        self.add_analysis_button.setEnabled(False)
        self.analyses_button_layout.addWidget(self.add_analysis_button)
        
        self.analyses_button_layout.addStretch()
        
        self.analyses_layout.addLayout(self.analyses_button_layout)
        
        # Add analyses tab to content tabs
        self.content_tabs.addTab(self.analyses_widget, "Analyses")
        
        # Add content tabs to main layout
        self.layout.addWidget(self.content_tabs)
        
        # Project stats
        self.stats_layout = QHBoxLayout()
        
        self.created_date_label = QLabel("Created: -")
        self.stats_layout.addWidget(self.created_date_label)
        
        self.modified_date_label = QLabel("Modified: -")
        self.stats_layout.addWidget(self.modified_date_label)
        
        self.stats_layout.addStretch()
        
        self.layout.addLayout(self.stats_layout)
    
    def connect_signals(self):
        """Connect widget signals to slots."""
        # Connect buttons
        self.create_button.clicked.connect(self.on_create_button_clicked)
        self.load_button.clicked.connect(self.on_load_button_clicked)
        self.save_button.clicked.connect(self.on_save_button_clicked)
        self.close_button.clicked.connect(self.on_close_button_clicked)
        
        # Connect description text
        self.description_text.textChanged.connect(self.on_description_changed)
        
        # Connect file buttons
        self.add_video_button.clicked.connect(self.on_add_video_clicked)
        self.add_annotation_button.clicked.connect(self.on_add_annotation_clicked)
        self.add_action_map_button.clicked.connect(self.on_add_action_map_clicked)
        self.add_analysis_button.clicked.connect(self.on_add_analysis_clicked)
        
        # Connect tree context menus
        self.videos_tree.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(pos, self.videos_tree, "videos"))
        self.annotations_tree.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(pos, self.annotations_tree, "annotations"))
        self.action_maps_tree.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(pos, self.action_maps_tree, "action_maps"))
        self.analyses_tree.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(pos, self.analyses_tree, "analyses"))
        
        # Connect double-click to open file
        self.videos_tree.itemDoubleClicked.connect(
            lambda item, column: self.on_item_double_clicked(item, "videos"))
        self.annotations_tree.itemDoubleClicked.connect(
            lambda item, column: self.on_item_double_clicked(item, "annotations"))
        self.action_maps_tree.itemDoubleClicked.connect(
            lambda item, column: self.on_item_double_clicked(item, "action_maps"))
        self.analyses_tree.itemDoubleClicked.connect(
            lambda item, column: self.on_item_double_clicked(item, "analyses"))
    
    def on_create_button_clicked(self):
        """Handle create project button clicked."""
        dialog = ProjectDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            directory = dialog.directory_edit.text()
            name = dialog.name_edit.text()
            description = dialog.description_edit.toPlainText()
            
            self.create_project_requested.emit(directory, name, description)
    
    def on_load_button_clicked(self):
        """Handle load project button clicked."""
        project_path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "Project File (project.json)"
        )
        
        if project_path:
            # Get parent directory of project.json
            project_dir = os.path.dirname(project_path)
            self.load_project_requested.emit(project_dir)
    
    def on_save_button_clicked(self):
        """Handle save project button clicked."""
        self.save_project_requested.emit()
    
    def on_close_button_clicked(self):
        """Handle close project button clicked."""
        if self.description_text.isEnabled():
            # Check for unsaved changes
            result = QMessageBox.question(
                self,
                "Close Project",
                "Close the current project? Any unsaved changes will be lost.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if result == QMessageBox.StandardButton.Yes:
                self.close_project_requested.emit()
        else:
            self.close_project_requested.emit()
    
    def on_description_changed(self):
        """Handle description text changed."""
        if self.description_text.isEnabled():
            self.description_changed.emit(self.description_text.toPlainText())
    
    def on_add_video_clicked(self):
        """Handle add video button clicked."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Videos", "", "Video Files (*.mp4 *.avi *.mkv *.mov *.wmv)"
        )
        
        if file_paths:
            # Ask if files should be copied to project
            dialog = CopyFilesDialog(self, "videos")
            if dialog.exec() == QDialog.DialogCode.Accepted:
                copy_to_project = dialog.copy_checkbox.isChecked()
                
                for file_path in file_paths:
                    self.add_file_requested.emit("videos", file_path)
    
    def on_add_annotation_clicked(self):
        """Handle add annotation button clicked."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Annotations", "", "CSV Files (*.csv)"
        )
        
        if file_paths:
            # Ask if files should be copied to project
            dialog = CopyFilesDialog(self, "annotations")
            if dialog.exec() == QDialog.DialogCode.Accepted:
                copy_to_project = dialog.copy_checkbox.isChecked()
                
                for file_path in file_paths:
                    self.add_file_requested.emit("annotations", file_path)
    
    def on_add_action_map_clicked(self):
        """Handle add action map button clicked."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Action Maps", "", "JSON Files (*.json)"
        )
        
        if file_paths:
            # Ask if files should be copied to project
            dialog = CopyFilesDialog(self, "action maps")
            if dialog.exec() == QDialog.DialogCode.Accepted:
                copy_to_project = dialog.copy_checkbox.isChecked()
                
                for file_path in file_paths:
                    self.add_file_requested.emit("action_maps", file_path)
    
    def on_add_analysis_clicked(self):
        """Handle add analysis button clicked."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Analyses", "", "CSV Files (*.csv)"
        )
        
        if file_paths:
            # Ask if files should be copied to project
            dialog = CopyFilesDialog(self, "analyses")
            if dialog.exec() == QDialog.DialogCode.Accepted:
                copy_to_project = dialog.copy_checkbox.isChecked()
                
                for file_path in file_paths:
                    self.add_file_requested.emit("analyses", file_path)
    
    def show_context_menu(self, position, tree, file_type):
        """
        Show context menu for tree items.
        
        Args:
            position: Position to show menu
            tree: Tree widget
            file_type: Type of files in tree (videos, annotations, action_maps, analyses)
        """
        item = tree.itemAt(position)
        if item is None:
            return
        
        # Create menu
        menu = QMenu()
        
        # Add actions
        open_action = QAction("Open", self)
        open_action.triggered.connect(lambda: self.on_open_file(item, file_type))
        menu.addAction(open_action)
        
        remove_action = QAction("Remove from Project", self)
        remove_action.triggered.connect(lambda: self.on_remove_file(item, file_type))
        menu.addAction(remove_action)
        
        # Show menu
        menu.exec(QCursor.pos())
    
    def on_open_file(self, item, file_type):
        """
        Handle open file menu action.
        
        Args:
            item: Tree item
            file_type: Type of file (videos, annotations, action_maps, analyses)
        """
        path = item.text(1)
        self.open_file_requested.emit(file_type, path)
    
    def on_remove_file(self, item, file_type):
        """
        Handle remove file menu action.
        
        Args:
            item: Tree item
            file_type: Type of file (videos, annotations, action_maps, analyses)
        """
        path = item.text(1)
        
        # Confirm removal
        result = QMessageBox.question(
            self,
            "Remove File",
            f"Remove this file from the project?\n\n{path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if result == QMessageBox.StandardButton.Yes:
            self.remove_file_requested.emit(file_type, path)
    
    def on_item_double_clicked(self, item, file_type):
        """
        Handle item double-clicked.
        
        Args:
            item: Tree item
            file_type: Type of file (videos, annotations, action_maps, analyses)
        """
        path = item.text(1)
        self.open_file_requested.emit(file_type, path)
    
    @Slot(str)
    def set_project_path(self, project_path):
        """
        Set project path in view.
        
        Args:
            project_path (str): Path to the project directory
        """
        if project_path:
            self.project_path_label.setText(project_path)
            self.enable_project_controls(True)
        else:
            self.project_path_label.setText("")
            self.enable_project_controls(False)
    
    @Slot(str)
    def set_project_name(self, project_name):
        """
        Set project name in view.
        
        Args:
            project_name (str): Name of the project
        """
        if project_name:
            self.project_name_label.setText(project_name)
        else:
            self.project_name_label.setText("No Project Open")
    
    @Slot(str)
    def set_project_description(self, description):
        """
        Set project description in view.
        
        Args:
            description (str): Project description
        """
        # Block signals to prevent recursion
        self.description_text.blockSignals(True)
        self.description_text.setPlainText(description)
        self.description_text.blockSignals(False)
    
    @Slot(str, str)
    def set_project_dates(self, created_date, modified_date):
        """
        Set project creation and modification dates in view.
        
        Args:
            created_date (str): Creation date
            modified_date (str): Modification date
        """
        # Format dates for display
        if created_date:
            # Convert ISO format to more readable format if needed
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(created_date)
                created_str = dt.strftime("%Y-%m-%d %H:%M")
            except:
                created_str = created_date
            
            self.created_date_label.setText(f"Created: {created_str}")
        else:
            self.created_date_label.setText("Created: -")
        
        if modified_date:
            # Convert ISO format to more readable format if needed
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(modified_date)
                modified_str = dt.strftime("%Y-%m-%d %H:%M")
            except:
                modified_str = modified_date
                
            self.modified_date_label.setText(f"Modified: {modified_str}")
        else:
            self.modified_date_label.setText("Modified: -")
    
    def enable_project_controls(self, enabled):
        """
        Enable or disable project-specific controls.
        
        Args:
            enabled (bool): Whether to enable or disable controls
        """
        self.save_button.setEnabled(enabled)
        self.close_button.setEnabled(enabled)
        self.description_text.setEnabled(enabled)
        
        self.add_video_button.setEnabled(enabled)
        self.add_annotation_button.setEnabled(enabled)
        self.add_action_map_button.setEnabled(enabled)
        self.add_analysis_button.setEnabled(enabled)
    
    @Slot(list)
    def update_videos(self, videos):
        """
        Update videos tree with current videos.
        
        Args:
            videos (list): List of video paths
        """
        self.videos_tree.clear()
        
        for video_path in videos:
            name = os.path.basename(video_path)
            item = QTreeWidgetItem([name, video_path])
            self.videos_tree.addTopLevelItem(item)
    
    @Slot(list)
    def update_annotations(self, annotations):
        """
        Update annotations tree with current annotations.
        
        Args:
            annotations (list): List of annotation paths
        """
        self.annotations_tree.clear()
        
        for annotation_path in annotations:
            name = os.path.basename(annotation_path)
            item = QTreeWidgetItem([name, annotation_path])
            self.annotations_tree.addTopLevelItem(item)
    
    @Slot(list)
    def update_action_maps(self, action_maps):
        """
        Update action maps tree with current action maps.
        
        Args:
            action_maps (list): List of action map paths
        """
        self.action_maps_tree.clear()
        
        for action_map_path in action_maps:
            name = os.path.basename(action_map_path)
            item = QTreeWidgetItem([name, action_map_path])
            self.action_maps_tree.addTopLevelItem(item)
    
    @Slot(list)
    def update_analyses(self, analyses):
        """
        Update analyses tree with current analyses.
        
        Args:
            analyses (list): List of analysis paths
        """
        self.analyses_tree.clear()
        
        for analysis_path in analyses:
            name = os.path.basename(analysis_path)
            item = QTreeWidgetItem([name, analysis_path])
            self.analyses_tree.addTopLevelItem(item)


class ProjectDialog(QDialog):
    """Dialog for creating a new project."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle("Create New Project")
        self.resize(500, 250)
        
        # Main layout
        self.layout = QVBoxLayout(self)
        
        # Form layout
        self.form_layout = QFormLayout()
        
        # Project directory
        self.directory_layout = QHBoxLayout()
        self.directory_edit = QLineEdit()
        self.directory_button = QPushButton("Browse...")
        self.directory_button.clicked.connect(self.browse_directory)
        self.directory_layout.addWidget(self.directory_edit)
        self.directory_layout.addWidget(self.directory_button)
        
        self.form_layout.addRow("Project Directory:", self.directory_layout)
        
        # Project name
        self.name_edit = QLineEdit()
        self.form_layout.addRow("Project Name:", self.name_edit)
        
        # Project description
        self.description_edit = QTextEdit()
        self.form_layout.addRow("Description:", self.description_edit)
        
        self.layout.addLayout(self.form_layout)
        
        # Buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)
    
    def browse_directory(self):
        """Open directory browser dialog."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Project Directory"
        )
        
        if directory:
            self.directory_edit.setText(directory)
    
    def validate_and_accept(self):
        """Validate inputs before accepting."""
        directory = self.directory_edit.text()
        name = self.name_edit.text()
        
        if not directory:
            QMessageBox.warning(self, "Missing Directory", "Please select a project directory.")
            return
        
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a project name.")
            return
        
        # Check if project directory already exists
        project_dir = Path(directory) / name
        if project_dir.exists():
            QMessageBox.warning(
                self, 
                "Directory Exists", 
                f"Project directory already exists:\n{project_dir}\n\nPlease choose a different name or directory."
            )
            return
        
        self.accept()


class CopyFilesDialog(QDialog):
    """Dialog for asking whether to copy files to project directory."""
    
    def __init__(self, parent=None, file_type="files"):
        super().__init__(parent)
        
        self.setWindowTitle(f"Add {file_type.title()}")
        self.resize(400, 150)
        
        # Main layout
        self.layout = QVBoxLayout(self)
        
        # Explanation label
        self.explanation_label = QLabel(
            f"Do you want to copy the {file_type} to the project directory?\n\n"
            "Copying ensures all project files are kept together, but uses more storage."
        )
        self.explanation_label.setWordWrap(True)
        self.layout.addWidget(self.explanation_label)
        
        # Copy checkbox
        self.copy_checkbox = QCheckBox(f"Copy {file_type} to project directory")
        self.copy_checkbox.setChecked(True)
        self.layout.addWidget(self.copy_checkbox)
        
        # Buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)