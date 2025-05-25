# views/visualization_view.py - Visualization tools for annotation data
import logging
import os
import colorsys
import warnings
import numpy as np
import matplotlib
matplotlib.use('Qt5Agg')  # Use Qt5 backend
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.colors as mcolors
import matplotlib.gridspec as gridspec
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QScrollArea, QPushButton, QFileDialog, 
    QGridLayout, QGroupBox, QCheckBox, QColorDialog, 
    QListWidget, QListWidgetItem, QMessageBox, QSplitter,
    QSizePolicy, QSpinBox
)
from PySide6.QtCore import Qt, Signal, Slot, QCoreApplication, QTimer
from PySide6.QtGui import QColor
import json

# Custom reorderable list widget
class ReorderableListWidget(QListWidget):
    """List widget that supports drag and drop reordering."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)


class MatplotlibCanvas(FigureCanvas):
    """Matplotlib canvas for embedding in Qt applications."""
    
    def __init__(self, parent=None, width=10, height=6, dpi=100):
        """
        Initialize the canvas.
        
        Args:
            parent: Parent widget
            width: Figure width in inches
            height: Figure height in inches
            dpi: DPI for the figure
        """
        # Create figure WITHOUT tight_layout to avoid warnings with manual axis positioning
        self.fig = Figure(figsize=(width, height), dpi=dpi, tight_layout=False)
        self.axes = self.fig.add_subplot(111)
        
        super().__init__(self.fig)
        self.setParent(parent)
        
        # Don't set size policy here - let the parent widget control it
        FigureCanvas.updateGeometry(self)


class RasterPlotWidget(QWidget):
    """Widget for displaying raster plots of behavioral events."""
    
    # Default custom color mapping for common behaviors
    DEFAULT_COLOR_MAP = {
        "Attack bites": "#FF4B00",
        "Sideways threats": "#F6AA00",
        "Tail rattles": "#C9ACE6",
        "Chasing": "#FF8082",
        "Social contact": "#4DC4FF",
        "Self-grooming": "#03AF7A",
        "Locomotion": "#FFFFB2",
        "Rearing": "#FFCABF"
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing RasterPlotWidget")
        
        # Data storage
        self._data = {}  # Dictionary to store annotation data
        self._behavior_colors = {}  # Dictionary to store behavior colors
        self._behavior_visibility = {}  # Dictionary to store behavior visibility
        self._file_visibility = {}  # Dictionary to store file visibility (for overlay mode)
        self._default_colormap = 'Set1'  # Default colormap
        self._custom_color_map = self.DEFAULT_COLOR_MAP.copy()  # Initialize with default mapping
        
        # Available custom color maps (discovered from configs folder)
        self._available_custom_colormaps = {}
        
        # Display settings
        self._time_unit = "Seconds"  # Time unit (Seconds or Minutes)
        self._tick_interval = 60     # Tick interval in seconds (default 1 minute)
        self._x_range_max = 300      # X-axis maximum in seconds (default 5 minutes)
        self._bar_height = 15        # Height of raster plot bars (line width)
        self._display_mode = "Separate Behaviors"  # Display mode setting
        
        # Track custom ordering
        self._custom_behavior_order = []
        self._custom_file_order = []
        
        # Individual frames setting for overlay mode
        self._individual_frames = False
        
        # Matplotlib warning context manager
        self._mpl_warning_filter = warnings.catch_warnings()
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface."""
        # Main layout with reduced spacing
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(3)
        self.layout.setContentsMargins(5, 5, 5, 0)
        
        # Control panel
        self._create_control_panel()
        
        # Buttons
        self._create_button_panel()
        
        # Create main content area with splitter
        self._create_main_content()
        
        # Status label
        self.status_label = QLabel("No data loaded")
        self.status_label.setMaximumHeight(25)
        self.status_label.setContentsMargins(0, 2, 0, 2)
        self.status_label.setWordWrap(False)
        self.layout.addWidget(self.status_label, 0)
        
        # Initialize display settings
        self._time_unit = "Seconds"
        self._tick_interval = 60
        self._x_range_max = 300
        self._bar_height = 20
    
    def _create_control_panel(self):
        """Create the control panel for plot settings."""
        self.controls_group = QGroupBox("Plot Controls")
        self.controls_group.setMaximumHeight(100)
        self.controls_layout = QGridLayout(self.controls_group)
        self.controls_layout.setContentsMargins(5, 5, 5, 5)
        self.controls_layout.setSpacing(3)
        self.controls_layout.setVerticalSpacing(2)
        
        # Row 0: Display mode, Color map, Display unit
        row = 0
        
        # Display mode selection
        self.display_mode_label = QLabel("Display Mode:")
        self.display_mode_combo = QComboBox()
        self.display_mode_combo.addItems(["Separate Behaviors", "Overlay Behaviors"])
        self.display_mode_combo.setCurrentText(self._display_mode)
        self.display_mode_combo.currentTextChanged.connect(self.on_display_mode_changed)
        
        self.controls_layout.addWidget(self.display_mode_label, row, 0)
        self.controls_layout.addWidget(self.display_mode_combo, row, 1)
        
        # Colormap selection
        self.colormap_label = QLabel("Color Map:")
        self.colormap_combo = QComboBox()
        self.builtin_colormaps = [
            'Set1', 'Set2', 'Set3', 'Accent',
            'Dark2', 'viridis', 'plasma', 'inferno'
        ]
        self.colormap_combo.addItems(self.builtin_colormaps)
        self.colormap_combo.setCurrentText(self._default_colormap)
        self.colormap_combo.currentTextChanged.connect(self.on_colormap_changed)
        
        self.controls_layout.addWidget(self.colormap_label, row, 2)
        self.controls_layout.addWidget(self.colormap_combo, row, 3)
        
        # Time unit
        self.time_unit_label = QLabel("Display Unit:")
        self.time_unit_combo = QComboBox()
        self.time_unit_combo.addItems(["Seconds", "Minutes"])
        self.time_unit_combo.setCurrentText("Seconds")
        self.time_unit_combo.currentTextChanged.connect(self.on_time_unit_changed)
        
        self.controls_layout.addWidget(self.time_unit_label, row, 4)
        self.controls_layout.addWidget(self.time_unit_combo, row, 5)
        
        # Row 1: Tick interval, X-axis range, Bar height
        row = 1
        
        # Tick interval
        self.tick_interval_label = QLabel("Tick Interval (sec):")
        self.tick_interval_spinbox = QSpinBox()
        self.tick_interval_spinbox.setMinimum(1)
        self.tick_interval_spinbox.setMaximum(600)
        self.tick_interval_spinbox.setValue(60)
        self.tick_interval_spinbox.valueChanged.connect(self.on_tick_interval_changed)
        
        self.controls_layout.addWidget(self.tick_interval_label, row, 0)
        self.controls_layout.addWidget(self.tick_interval_spinbox, row, 1)
        
        # X-axis range
        self.x_range_label = QLabel("Max Range (sec):")
        self.x_range_spinbox = QSpinBox()
        self.x_range_spinbox.setMinimum(60)
        self.x_range_spinbox.setMaximum(7200)
        self.x_range_spinbox.setValue(300)
        self.x_range_spinbox.valueChanged.connect(self.on_x_range_changed)
        
        self.controls_layout.addWidget(self.x_range_label, row, 2)
        self.controls_layout.addWidget(self.x_range_spinbox, row, 3)
        
        # Bar height control
        self.bar_height_label = QLabel("Bar Height:")
        self.bar_height_spinbox = QSpinBox()
        self.bar_height_spinbox.setMinimum(1)
        self.bar_height_spinbox.setMaximum(100)
        self.bar_height_spinbox.setValue(20)
        self.bar_height_spinbox.valueChanged.connect(self.on_bar_height_changed)
        
        self.controls_layout.addWidget(self.bar_height_label, row, 4)
        self.controls_layout.addWidget(self.bar_height_spinbox, row, 5)
        
        # Add controls to main layout
        self.layout.addWidget(self.controls_group, 0)
    
    def _create_button_panel(self):
        """Create the button panel."""
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 2, 0, 2)
        button_layout.setSpacing(5)
        
        # Refresh button
        self.refresh_button = QPushButton("Refresh Plot")
        self.refresh_button.clicked.connect(self.update_plot)
        self.refresh_button.setMaximumWidth(150)
        self.refresh_button.setMaximumHeight(30)
        
        # Save button
        self.save_button = QPushButton("Save Plot")
        self.save_button.clicked.connect(self.save_plot)
        self.save_button.setMaximumWidth(150)
        self.save_button.setMaximumHeight(30)
        
        # Clear button
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_data)
        self.clear_button.setMaximumWidth(100)
        self.clear_button.setMaximumHeight(30)
        
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.save_button)
        button_layout.addSpacing(15)
        button_layout.addWidget(self.clear_button)
        button_layout.addStretch()
        
        self.layout.addLayout(button_layout, 0)
    
    def _create_main_content(self):
        """Create the main content area with splitter."""
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side container
        self._create_left_panel()
        
        # Right side plot area
        self._create_plot_area()
        
        # Set splitter sizes (30% for list, 70% for plot)
        self.splitter.setSizes([300, 700])
        
        # Add splitter to main layout
        self.layout.addWidget(self.splitter, 10)
    
    def _create_left_panel(self):
        """Create the left panel with behavior and file lists."""
        self.left_container = QWidget()
        self.left_layout = QVBoxLayout(self.left_container)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(5)
        
        # Behavior list
        self.behavior_group = QGroupBox("Behaviors (drag to reorder)")
        self.behavior_layout = QVBoxLayout(self.behavior_group)
        self.behavior_layout.setContentsMargins(5, 10, 5, 5)
        self.behavior_layout.setSpacing(2)
        
        self.behavior_list = ReorderableListWidget()
        self.behavior_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.behavior_list.itemDoubleClicked.connect(self.on_behavior_double_clicked)
        self.behavior_list.itemChanged.connect(self.on_behavior_selection_changed)
        self.behavior_list.model().rowsMoved.connect(self.on_behaviors_reordered)
        self.behavior_layout.addWidget(self.behavior_list)
        
        self.left_layout.addWidget(self.behavior_group, 1)
        
        # File selection list (only visible in overlay mode)
        self.file_group = QGroupBox("Files / Individuals (drag to reorder)")
        self.file_layout = QVBoxLayout(self.file_group)
        self.file_layout.setContentsMargins(5, 10, 5, 5)
        self.file_layout.setSpacing(2)
        
        self.file_list = ReorderableListWidget()
        self.file_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.file_list.itemChanged.connect(self.on_file_selection_changed)
        self.file_list.model().rowsMoved.connect(self.on_files_reordered)
        self.file_layout.addWidget(self.file_list)
        
        self.file_group.setVisible(False)
        self.left_layout.addWidget(self.file_group, 1)
        
        self.left_layout.addStretch(1)
        self.splitter.addWidget(self.left_container)
    
    def _create_plot_area(self):
        """Create the plot area with canvas and controls."""
        self.plot_widget = QWidget()
        self.plot_layout = QVBoxLayout(self.plot_widget)
        self.plot_layout.setContentsMargins(0, 0, 0, 0)
        self.plot_layout.setSpacing(5)
        
        # Plot size controls
        self._create_plot_size_controls()
        
        # Create scroll area for canvas
        self.canvas_scroll = QScrollArea()
        self.canvas_scroll.setWidgetResizable(True)
        
        # Create matplotlib canvas
        self.canvas = MatplotlibCanvas(self, width=8, height=6, dpi=100)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.canvas_scroll.setWidget(self.canvas)
        self.plot_layout.addWidget(self.canvas_scroll, 10)
        
        self.splitter.addWidget(self.plot_widget)
    
    def _create_plot_size_controls(self):
        """Create plot size control widgets."""
        self.plot_controls_layout = QHBoxLayout()
        self.plot_controls_layout.setContentsMargins(0, 0, 0, 5)
        self.plot_controls_layout.setSpacing(10)
        
        # Width control
        self.width_label = QLabel("Width:")
        self.width_spinbox = QSpinBox()
        self.width_spinbox.setMinimum(400)
        self.width_spinbox.setMaximum(2000)
        self.width_spinbox.setValue(800)
        self.width_spinbox.setSuffix(" px")
        self.width_spinbox.setMaximumHeight(25)
        self.width_spinbox.valueChanged.connect(self.on_plot_size_changed)
        
        # Height control
        self.height_label = QLabel("Height:")
        self.height_spinbox = QSpinBox()
        self.height_spinbox.setMinimum(100)
        self.height_spinbox.setMaximum(2000)
        self.height_spinbox.setValue(600)
        self.height_spinbox.setSuffix(" px")
        self.height_spinbox.setMaximumHeight(25)
        self.height_spinbox.valueChanged.connect(self.on_plot_size_changed)
        
        # Auto-size checkbox
        self.auto_size_checkbox = QCheckBox("Auto-fit")
        self.auto_size_checkbox.setChecked(True)
        self.auto_size_checkbox.stateChanged.connect(self.on_auto_size_changed)
        
        # Individual frames checkbox (only for overlay mode)
        self.individual_frames_checkbox = QCheckBox("Individual frames")
        self.individual_frames_checkbox.setChecked(False)
        self.individual_frames_checkbox.stateChanged.connect(self.on_individual_frames_changed)
        self.individual_frames_checkbox.setVisible(False)
        
        # Frame height control
        self.frame_height_label = QLabel("Frame height:")
        self.frame_height_spinbox = QSpinBox()
        self.frame_height_spinbox.setMinimum(5)
        self.frame_height_spinbox.setMaximum(200)
        self.frame_height_spinbox.setValue(30)
        self.frame_height_spinbox.setSuffix(" px")
        self.frame_height_spinbox.setToolTip(
            "Height of each individual frame in pixels.\n"
            "Auto-fit mode: Use smaller values (1.5x bar height)\n"
            "Fixed size mode: Use larger values (3x bar height)\n"
            "Adjusts automatically when switching modes."
        )
        self.frame_height_spinbox.valueChanged.connect(self.on_frame_height_changed)
        self.frame_height_label.setVisible(False)
        self.frame_height_spinbox.setVisible(False)
        
        # Add controls to layout
        self.plot_controls_layout.addWidget(self.width_label)
        self.plot_controls_layout.addWidget(self.width_spinbox)
        self.plot_controls_layout.addSpacing(15)
        self.plot_controls_layout.addWidget(self.height_label)
        self.plot_controls_layout.addWidget(self.height_spinbox)
        self.plot_controls_layout.addSpacing(15)
        self.plot_controls_layout.addWidget(self.auto_size_checkbox)
        self.plot_controls_layout.addSpacing(15)
        self.plot_controls_layout.addWidget(self.individual_frames_checkbox)
        self.plot_controls_layout.addSpacing(8)
        self.plot_controls_layout.addWidget(self.frame_height_label)
        self.plot_controls_layout.addWidget(self.frame_height_spinbox)
        self.plot_controls_layout.addStretch()
        
        # Initially disable size controls when auto-fit is checked
        self.width_spinbox.setEnabled(False)
        self.height_spinbox.setEnabled(False)
        
        self.plot_layout.addLayout(self.plot_controls_layout, 0)
    
    # Utility methods
    def _suppress_matplotlib_warnings(self):
        """Context manager to suppress matplotlib tight_layout warnings."""
        return warnings.catch_warnings()
    
    def _get_recording_start(self, df, file_name=""):
        """
        Extract recording start time from dataframe.
        
        Args:
            df: Pandas DataFrame with annotation data
            file_name: Name of file for logging
            
        Returns:
            float: Recording start time in seconds
        """
        recording_start = 0.0
        if 'Event' in df.columns:
            recording_start_events = df[df['Event'] == 'RecordingStart']
            if not recording_start_events.empty and 'Onset' in recording_start_events.columns:
                recording_start = float(recording_start_events['Onset'].iloc[0])
                if file_name:
                    self.logger.info(f"Found RecordingStart at {recording_start}s in {file_name}")
        return recording_start
    
    def _update_canvas_display(self):
        """Ensure canvas is properly displayed after updates."""
        if self.auto_size_checkbox.isChecked():
            self.canvas.updateGeometry()
            # Only call processEvents once
            QCoreApplication.processEvents()
    
    def _draw_canvas_safe(self):
        """Draw canvas with warning suppression."""
        with self._suppress_matplotlib_warnings():
            warnings.filterwarnings("ignore", message="This figure includes Axes that are not compatible")
            self.canvas.draw()
        
        # Update display after drawing
        self._update_canvas_display()

        # Event handlers
    def on_display_mode_changed(self, mode):
        """Handle display mode change."""
        self._display_mode = mode
        self.logger.info(f"Display mode changed to: {mode}")
        
        # Show/hide UI elements based on mode
        is_overlay = (mode == "Overlay Behaviors")
        self.file_group.setVisible(is_overlay)
        self.individual_frames_checkbox.setVisible(is_overlay)
        
        # Show frame height controls if needed
        if is_overlay and self._individual_frames:
            self.frame_height_label.setVisible(True)
            self.frame_height_spinbox.setVisible(True)
        else:
            self.frame_height_label.setVisible(False)
            self.frame_height_spinbox.setVisible(False)
        
        # Update file list if in overlay mode
        if is_overlay and self._data:
            self.update_file_list()
        
        # Update the plot
        self.update_plot()
    
    def on_colormap_changed(self, colormap_name):
        """Handle colormap selection change."""
        if not colormap_name:
            self.logger.warning("Empty colormap name received, ignoring")
            return
        
        # Check if this is a custom colormap or built-in
        if colormap_name in self._available_custom_colormaps:
            self._custom_color_map = self._available_custom_colormaps[colormap_name].copy()
            self.logger.info(f"Selected custom colormap: {colormap_name}")
        else:
            if colormap_name:
                self._default_colormap = colormap_name
            self._custom_color_map = {}
            self.logger.info(f"Selected built-in colormap: {colormap_name}")
        
        # Reset behavior colors to force regeneration
        self._behavior_colors = {}
        
        # Update behavior list and plot
        self.update_behavior_list()
        self.update_plot()
    
    def on_time_unit_changed(self, unit):
        """Handle time unit change."""
        self._time_unit = unit
        self.update_plot()
    
    def on_tick_interval_changed(self, value):
        """Handle tick interval change."""
        self._tick_interval = value
        self.update_plot()
    
    def on_x_range_changed(self, value):
        """Handle x-axis range change."""
        self._x_range_max = value
        self.update_plot()
    
    def on_bar_height_changed(self, value):
        """Handle bar height change."""
        self._bar_height = value
        self.logger.debug(f"Bar height changed to: {value}")
        self.update_plot()
    
    def on_plot_size_changed(self, value):
        """Handle plot size change."""
        if not self.auto_size_checkbox.isChecked():
            width_pixels = self.width_spinbox.value()
            height_pixels = self.height_spinbox.value()
            
            # Set fixed size for the canvas widget
            self.canvas.setFixedSize(width_pixels, height_pixels)
            
            # Update figure size
            width_inches = width_pixels / 100
            height_inches = height_pixels / 100
            self.canvas.fig.set_size_inches(width_inches, height_inches)
            
            # Update canvas
            self.canvas.updateGeometry()
            self.update_plot()
    
    def on_auto_size_changed(self, state):
        """Handle auto-size checkbox change."""
        is_checked = (state == Qt.CheckState.Checked.value)
        
        # Enable/disable size controls
        self.width_spinbox.setEnabled(not is_checked)
        self.height_spinbox.setEnabled(not is_checked)
        
        if is_checked:
            # Enable auto-fit mode
            self.canvas_scroll.setWidgetResizable(True)
            self.canvas.setMinimumSize(0, 0)
            self.canvas.setMaximumSize(16777215, 16777215)  # Qt's QWIDGETSIZE_MAX
            self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            
            # Adjust frame height for auto-fit mode
            if self._individual_frames and self._display_mode == "Overlay Behaviors":
                suggested_height = int(self._bar_height * 1.5)
                self.frame_height_spinbox.setValue(min(max(suggested_height, 20), 50))
        else:
            # Disable auto-fit mode
            self.canvas_scroll.setWidgetResizable(False)
            self.canvas.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            
            # Apply fixed size
            width_pixels = self.width_spinbox.value()
            height_pixels = self.height_spinbox.value()
            self.canvas.setFixedSize(width_pixels, height_pixels)
            
            # Update figure size
            self.canvas.fig.set_size_inches(width_pixels / 100, height_pixels / 100)
            
            # Adjust frame height for fixed size mode
            if self._individual_frames and self._display_mode == "Overlay Behaviors":
                suggested_height = int(self._bar_height * 3)
                self.frame_height_spinbox.setValue(min(max(suggested_height, 40), 100))
        
        self.canvas.updateGeometry()
        self.update_plot()
    
    def on_individual_frames_changed(self, state):
        """Handle individual frames checkbox change."""
        self._individual_frames = (state == Qt.CheckState.Checked.value)
        
        # Show/hide frame height controls
        show_controls = self._individual_frames and self._display_mode == "Overlay Behaviors"
        self.frame_height_label.setVisible(show_controls)
        self.frame_height_spinbox.setVisible(show_controls)
        
        # Adjust frame height default
        if show_controls:
            if self.auto_size_checkbox.isChecked():
                suggested_height = int(self._bar_height * 1.5)
                self.frame_height_spinbox.setValue(min(max(suggested_height, 20), 50))
            else:
                suggested_height = int(self._bar_height * 3)
                self.frame_height_spinbox.setValue(min(max(suggested_height, 40), 100))
        
        self.update_plot()
    
    def on_frame_height_changed(self, value):
        """Handle frame height change."""
        self.update_plot()
    
    def on_behavior_selection_changed(self, item):
        """Handle behavior checkbox state change."""
        behavior = item.text()
        self._behavior_visibility[behavior] = (item.checkState() == Qt.CheckState.Checked)
        self.update_plot()
    
    def on_file_selection_changed(self, item):
        """Handle file selection change in overlay mode."""
        file_path = item.data(Qt.ItemDataRole.UserRole)
        self._file_visibility[file_path] = (item.checkState() == Qt.CheckState.Checked)
        self.update_plot()
    
    def on_behavior_double_clicked(self, item):
        """Handle double click on a behavior item - change color."""
        behavior = item.text()
        current_color = self._behavior_colors.get(behavior, (255, 255, 255))
        
        # Open color dialog
        color = QColorDialog.getColor(QColor(*current_color), self, f"Select Color for {behavior}")
        
        if color.isValid():
            # Update color
            rgb = (color.red(), color.green(), color.blue())
            self._behavior_colors[behavior] = rgb
            
            # Update item background
            item.setBackground(color)
            
            # Update plot
            self.update_plot()
    
    def on_behaviors_reordered(self):
        """Handle behaviors being reordered in the list."""
        self._custom_behavior_order = []
        for i in range(self.behavior_list.count()):
            item = self.behavior_list.item(i)
            self._custom_behavior_order.append(item.text())
        
        self.logger.debug(f"Behaviors reordered: {self._custom_behavior_order}")
        self.update_plot()
    
    def on_files_reordered(self):
        """Handle files being reordered in the list."""
        self._custom_file_order = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            file_path = item.data(Qt.ItemDataRole.UserRole)
            self._custom_file_order.append(file_path)
        
        self.logger.debug(f"Files reordered: {[os.path.basename(f) for f in self._custom_file_order]}")
        
        # Update the file list to renumber items
        self.update_file_list()
        self.update_plot()
    
    # Data management methods
    def set_data(self, data_dict):
        """Set the annotation data for visualization."""
        self._data = data_dict
        self.logger.info(f"Visualization data set: {len(data_dict)} files")
        
        # Clear existing behavior colors
        self._behavior_colors = {}
        self._behavior_visibility = {}
        
        # Initialize file visibility
        self._file_visibility = {path: True for path in data_dict.keys()}
        
        # Initialize custom file order if not already set
        if not self._custom_file_order:
            self._custom_file_order = list(data_dict.keys())
        
        # Update the behavior list
        self.update_behavior_list()
        
        # Update file list if in overlay mode
        if self._display_mode == "Overlay Behaviors":
            self.update_file_list()
        
        # Update the plot
        self.update_plot()
        
        # Schedule deferred updates to ensure proper display
        for delay in [50, 100, 200]:
            QTimer.singleShot(delay, self._ensure_proper_display)
        
        # Update status
        self.status_label.setText(f"Loaded {len(data_dict)} file(s)")
    
    def _ensure_proper_display(self):
        """Ensure the canvas is properly displayed after data is loaded."""
        if self.auto_size_checkbox.isChecked():
            viewport = self.canvas_scroll.viewport()
            if viewport and viewport.width() > 50 and viewport.height() > 50:
                self.canvas.resize(viewport.size())
                self.canvas.updateGeometry()
                self.canvas.draw_idle()
    
    def set_custom_color_map(self, color_map):
        """Set a custom color mapping for behaviors."""
        if color_map and isinstance(color_map, dict):
            self._custom_color_map = color_map.copy()
            self.logger.info(f"Custom color map set with {len(color_map)} behaviors")
            
            # Update behavior list to apply new colors
            self.update_behavior_list()
            self.update_plot()
    
    def add_custom_colormaps_to_dropdown(self, custom_colormaps):
        """Add custom colormaps to the main colormap dropdown."""
        self.logger.info(f"Adding {len(custom_colormaps)} custom colormaps to dropdown")
        self.logger.debug(f"Custom colormaps: {list(custom_colormaps.keys())}")
        
        # Store the custom colormaps
        self._available_custom_colormaps = custom_colormaps
        
        # Remember current selection
        current_selection = self.colormap_combo.currentText()
        
        # Clear and rebuild the dropdown
        self.colormap_combo.clear()
        
        # Add built-in colormaps first
        self.colormap_combo.addItems(self.builtin_colormaps)
        
        # Add separator if we have custom colormaps
        if custom_colormaps:
            self.colormap_combo.insertSeparator(self.colormap_combo.count())
        
        # Add custom colormaps
        custom_names = sorted(custom_colormaps.keys())
        for name in custom_names:
            self.colormap_combo.addItem(name)
        
        # Restore selection if it still exists
        index = self.colormap_combo.findText(current_selection)
        if index >= 0:
            self.colormap_combo.setCurrentIndex(index)
        else:
            self.colormap_combo.setCurrentText(self._default_colormap)
        
        self.logger.info(f"Successfully added {len(custom_colormaps)} custom colormaps to dropdown")
    
    def clear_data(self):
        """Clear all loaded data and reset the plot."""
        # Clear data
        self._data = {}
        self._behavior_colors = {}
        self._behavior_visibility = {}
        self._file_visibility = {}
        self._custom_behavior_order = []
        self._custom_file_order = []
        
        # Clear lists
        self.behavior_list.clear()
        self.file_list.clear()
        
        # Clear the plot
        self.canvas.fig.clear()
        self.canvas.axes = self.canvas.fig.add_subplot(111)
        self.canvas.axes.clear()
        
        # Update status
        self.status_label.setText("No data loaded")
        
        # Draw the empty canvas
        self._draw_canvas_safe()
        
        self.logger.info("Cleared all data and reset plot")
    
    def save_plot(self):
        """Save the current plot to a file."""
        if not hasattr(self, 'canvas') or not self._data:
            QMessageBox.warning(self, "Warning", "No plot to save.")
            return
        
        # Open file dialog
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getSaveFileName(
            self,
            "Save Plot",
            "behavioral_raster_plot.svg",
            "SVG Files (*.svg);;PNG Files (*.png);;PDF Files (*.pdf);;All Files (*)"
        )
        
        if file_path:
            try:
                # Save the figure
                self.canvas.fig.savefig(file_path, bbox_inches='tight', dpi=300)
                self.logger.info(f"Plot saved to: {file_path}")
                QMessageBox.information(self, "Success", f"Plot saved to:\n{file_path}")
            except Exception as e:
                self.logger.error(f"Error saving plot: {str(e)}")
                QMessageBox.critical(self, "Error", f"Failed to save plot:\n{str(e)}")
    
    # List update methods
    def update_behavior_list(self):
        """Update the behavior list with available behaviors and colors."""
        # Remember checkbox states
        checkbox_states = {}
        for i in range(self.behavior_list.count()):
            item = self.behavior_list.item(i)
            behavior = item.text()
            checkbox_states[behavior] = item.checkState()
        
        # Clear existing items
        self.behavior_list.clear()
        
        # Get all unique behaviors from the data
        all_behaviors = set()
        for file_path, df in self._data.items():
            if 'Event' in df.columns:
                for behavior in df['Event'].dropna().unique():
                    # Skip invalid or system events
                    if behavior is None or behavior == "" or behavior == "nan" or behavior == "RecordingStart":
                        continue
                    
                    behavior_str = str(behavior).strip()
                    if behavior_str and behavior_str != "nan":
                        all_behaviors.add(behavior_str)
        
        # Order behaviors
        if self._custom_behavior_order:
            existing_behaviors = set(all_behaviors)
            ordered_behaviors = [b for b in self._custom_behavior_order if b in existing_behaviors]
            new_behaviors = sorted(list(existing_behaviors - set(ordered_behaviors)))
            behaviors = ordered_behaviors + new_behaviors
        else:
            behaviors = sorted(list(all_behaviors))
        
        # Generate colors
        self._generate_behavior_colors(behaviors)
        
        # Create list items
        for behavior in behaviors:
            item = QListWidgetItem(behavior)
            
            # Set checkbox
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if behavior in checkbox_states:
                item.setCheckState(checkbox_states[behavior])
            else:
                item.setCheckState(Qt.CheckState.Checked if self._behavior_visibility.get(behavior, True) else Qt.CheckState.Unchecked)
            
            # Set background color
            color = self._behavior_colors[behavior]
            item.setBackground(QColor(*color))
            
            self.behavior_list.addItem(item)
        
        # Update custom order
        if behaviors:
            self._custom_behavior_order = behaviors
    
    def _generate_behavior_colors(self, behaviors):
        """Generate colors for behaviors using current colormap settings."""
        # Get colormap
        if self._custom_color_map:
            cmap = None
        else:
            if not self._default_colormap or self._default_colormap not in matplotlib.colormaps:
                self._default_colormap = 'Set1'
            cmap = matplotlib.colormaps[self._default_colormap]
        
        # Determine if gradient colormap
        is_gradient = False
        if cmap:
            is_gradient = cmap.name in ['viridis', 'plasma', 'inferno', 'cividis']
        
        # Generate colors
        for i, behavior in enumerate(behaviors):
            if self._custom_color_map and behavior in self._custom_color_map:
                # Use custom color
                hex_color = self._custom_color_map[behavior]
                color = mcolors.hex2color(hex_color)
                color = tuple(int(c * 255) for c in color)
                self._behavior_colors[behavior] = color
            else:
                # Generate from colormap
                if cmap:
                    if is_gradient and len(behaviors) > 1:
                        norm_index = i / (len(behaviors) - 1) if len(behaviors) > 1 else 0.5
                        color_rgba = cmap(norm_index)
                    else:
                        color_rgba = cmap(i % cmap.N)
                    
                    color = (int(color_rgba[0]*255), int(color_rgba[1]*255), int(color_rgba[2]*255))
                else:
                    # Fallback color
                    hue = (i * 360 / len(behaviors)) % 360
                    rgb = colorsys.hsv_to_rgb(hue/360, 0.7, 0.9)
                    color = tuple(int(c * 255) for c in rgb)
                
                self._behavior_colors[behavior] = color
            
            # Set default visibility
            if behavior not in self._behavior_visibility:
                self._behavior_visibility[behavior] = True

    def update_file_list(self):
        """Update the file list widget for overlay mode."""
        # Remember checkbox states
        checkbox_states = {}
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            file_path = item.data(Qt.ItemDataRole.UserRole)
            checkbox_states[file_path] = item.checkState()
        
        # Clear existing items
        self.file_list.clear()
        
        # Get list of files
        file_paths = list(self._data.keys())
        
        # Use custom order if available
        if self._custom_file_order:
            existing_files = set(file_paths)
            ordered_files = [f for f in self._custom_file_order if f in existing_files]
            new_files = [f for f in file_paths if f not in ordered_files]
            file_paths = ordered_files + new_files
        
        # Update custom file order
        self._custom_file_order = file_paths
        
        # Create items for each file
        for i, file_path in enumerate(file_paths):
            # Create display name with number
            display_name = f"{i + 1}: {os.path.basename(file_path)}"
            
            # Create list item
            item = QListWidgetItem(display_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            
            # Set check state
            if file_path in checkbox_states:
                item.setCheckState(checkbox_states[file_path])
            else:
                is_visible = self._file_visibility.get(file_path, True)
                item.setCheckState(Qt.CheckState.Checked if is_visible else Qt.CheckState.Unchecked)
            
            # Store the full file path as data
            item.setData(Qt.ItemDataRole.UserRole, file_path)
            
            self.file_list.addItem(item)
    
    # Main plotting methods
    def update_plot(self):
        """Update the raster plot with current data and settings."""
        # Check if data is available
        if not self._data:
            self.status_label.setText("No data loaded")
            self.canvas.fig.clear()
            self.canvas.axes = self.canvas.fig.add_subplot(111)
            self.canvas.axes.clear()
            self._draw_canvas_safe()
            return
        
        # Clear the current plot
        self.canvas.fig.clear()
        
        # Branch based on display mode
        if self._display_mode == "Overlay Behaviors":
            self.update_plot_overlay_mode()
        else:
            # For separate behaviors mode, recreate single axes
            self.canvas.axes = self.canvas.fig.add_subplot(111)
            self.update_plot_separate_mode()
        
        # Ensure canvas fills available space in auto-fit mode
        if self.auto_size_checkbox.isChecked():
            viewport = self.canvas_scroll.viewport()
            if viewport and viewport.width() > 0 and viewport.height() > 0:
                self.canvas.resize(viewport.size())
    
    def update_plot_separate_mode(self):
        """Update the plot in separate behaviors mode."""
        # Update behavior visibility from list
        for i in range(self.behavior_list.count()):
            item = self.behavior_list.item(i)
            behavior = item.text()
            self._behavior_visibility[behavior] = (item.checkState() == Qt.CheckState.Checked)
        
        # Get visible behaviors in order
        visible_behaviors = []
        for i in range(self.behavior_list.count()):
            item = self.behavior_list.item(i)
            behavior = item.text()
            if self._behavior_visibility[behavior]:
                visible_behaviors.append(behavior)
        
        if not visible_behaviors:
            self.status_label.setText("No behaviors selected")
            self._draw_canvas_safe()
            return
        
        # Create behavior positions
        behavior_positions = {b: i for i, b in enumerate(reversed(visible_behaviors))}
        
        # Track plot statistics
        max_time = 0
        file_count = 0
        event_count = 0
        
        # Collect recording starts for all files
        file_recording_starts = {}
        for file_path, df in self._data.items():
            file_name = os.path.basename(file_path)
            recording_start = self._get_recording_start(df, file_name)
            file_recording_starts[file_path] = recording_start
            
            # Get maximum time
            if 'Offset' in df.columns:
                file_max_time = df['Offset'].max() - recording_start
                max_time = max(max_time, file_max_time)
        
        # Plot events
        for file_path, df in self._data.items():
            recording_start = file_recording_starts[file_path]
            
            for behavior in visible_behaviors:
                if 'Event' not in df.columns:
                    continue
                
                # Get events for this behavior
                behavior_events = df[df['Event'].astype(str) == behavior]
                
                if behavior_events.empty:
                    continue
                
                # Get color for this behavior
                color_rgb = self._behavior_colors.get(behavior, (0, 0, 0))
                color = [c/255 for c in color_rgb]
                
                # Calculate y position
                y_pos = behavior_positions[behavior]
                
                # Plot each event
                for _, event in behavior_events.iterrows():
                    if 'Onset' in event and 'Offset' in event:
                        try:
                            onset = float(event['Onset']) - recording_start
                            offset = float(event['Offset']) - recording_start
                            
                            if onset >= 0:
                                self.canvas.axes.plot(
                                    [onset, offset], [y_pos, y_pos], 
                                    linewidth=self._bar_height, solid_capstyle='butt',
                                    color=color, alpha=0.8, zorder=10
                                )
                                event_count += 1
                        except (ValueError, TypeError) as e:
                            self.logger.warning(f"Invalid timestamp in event: {event}, error: {str(e)}")
            
            file_count += 1
        
        # Set y-axis
        y_ticks = [behavior_positions[b] for b in visible_behaviors]
        y_labels = list(visible_behaviors)
        self.canvas.axes.set_yticks(y_ticks)
        self.canvas.axes.set_yticklabels(y_labels)
        
        # Configure plot
        self._configure_plot_axes(max_time, len(visible_behaviors))
        
        # Update status
        self.status_label.setText(
            f"Displaying {event_count} events across {file_count} file(s) and {len(visible_behaviors)} behaviors"
        )
        
        # Draw the canvas
        self._draw_canvas_safe()
    
    def update_plot_overlay_mode(self):
        """Update the plot in overlay mode."""
        # Update visibility from lists
        for i in range(self.behavior_list.count()):
            item = self.behavior_list.item(i)
            behavior = item.text()
            self._behavior_visibility[behavior] = (item.checkState() == Qt.CheckState.Checked)
        
        # Get visible behaviors
        visible_behaviors = []
        for i in range(self.behavior_list.count()):
            item = self.behavior_list.item(i)
            behavior = item.text()
            if self._behavior_visibility.get(behavior, False):
                visible_behaviors.append(behavior)
        
        # Get selected files
        selected_files = []
        if self._custom_file_order:
            for file_path in self._custom_file_order:
                if file_path in self._file_visibility and self._file_visibility[file_path]:
                    selected_files.append(file_path)
        else:
            selected_files = [f for f, vis in self._file_visibility.items() if vis]
        
        if not selected_files:
            self.status_label.setText("No files selected")
            self._draw_canvas_safe()
            return
        
        if not visible_behaviors:
            self.status_label.setText("No behaviors selected")
            self._draw_canvas_safe()
            return
        
        # Clear the figure
        self.canvas.fig.clear()
        
        if self._individual_frames:
            self._plot_overlay_individual_frames(selected_files, visible_behaviors)
        else:
            self.canvas.axes = self.canvas.fig.add_subplot(111)
            self._plot_overlay_single_frame(selected_files, visible_behaviors)
    
    def _plot_overlay_single_frame(self, selected_files, visible_behaviors):
        """Plot overlay mode with a single shared frame."""
        # Create file positions
        file_positions = {f: len(selected_files) - i - 1 for i, f in enumerate(selected_files)}
        
        # Track statistics
        max_time = 0
        event_count = 0
        
        # Calculate recording starts and max time
        file_recording_starts = {}
        for file_path in selected_files:
            df = self._data[file_path]
            recording_start = self._get_recording_start(df, os.path.basename(file_path))
            file_recording_starts[file_path] = recording_start
            
            if 'Offset' in df.columns:
                file_max_time = df['Offset'].max() - recording_start
                max_time = max(max_time, file_max_time)
        
        # Plot behaviors in reverse order for proper stacking
        for behavior_idx, behavior in enumerate(reversed(visible_behaviors)):
            z_order = behavior_idx + 1
            
            for file_path in selected_files:
                df = self._data[file_path]
                recording_start = file_recording_starts[file_path]
                y_pos = file_positions[file_path]
                
                if 'Event' in df.columns:
                    behavior_events = df[df['Event'].astype(str) == behavior]
                    
                    if behavior_events.empty:
                        continue
                    
                    color_rgb = self._behavior_colors.get(behavior, (0, 0, 0))
                    color = [c/255 for c in color_rgb]
                    
                    for _, event in behavior_events.iterrows():
                        if 'Onset' in event and 'Offset' in event:
                            try:
                                onset = float(event['Onset']) - recording_start
                                offset = float(event['Offset']) - recording_start
                                
                                if onset >= 0:
                                    self.canvas.axes.plot(
                                        [onset, offset], [y_pos, y_pos], 
                                        linewidth=self._bar_height, solid_capstyle='butt',
                                        color=color, alpha=0.9,
                                        zorder=10 + z_order
                                    )
                                    event_count += 1
                            except (ValueError, TypeError) as e:
                                self.logger.warning(f"Invalid timestamp in event: {event}, error: {str(e)}")
        
        # Set y-axis
        y_ticks = sorted(file_positions.values())
        y_labels = [str(i + 1) for i in range(len(selected_files))]
        self.canvas.axes.set_yticks(y_ticks)
        self.canvas.axes.set_yticklabels(y_labels)
        
        # Configure plot
        self._configure_plot_axes(max_time, len(selected_files))
        
        # Update status
        self.status_label.setText(
            f"Overlay mode: {event_count} events across {len(selected_files)} file(s) with {len(visible_behaviors)} behavior(s)"
        )
        
        # Draw the canvas
        self._draw_canvas_safe()
    
    def _plot_overlay_individual_frames(self, selected_files, visible_behaviors):
        """Plot overlay mode with individual frames for each file."""
        num_files = len(selected_files)
        frame_height_pixels = self.frame_height_spinbox.value()
        
        # Define spacing in pixels
        top_margin_pixels = 20
        bottom_margin_pixels = 50
        between_plots_pixels = 40
        
        # Calculate total height needed
        total_height_pixels = (
            top_margin_pixels + 
            (frame_height_pixels * num_files) + 
            (between_plots_pixels * (num_files - 1)) + 
            bottom_margin_pixels
        )
        
        # Get current figure properties
        current_width_inches = self.canvas.fig.get_figwidth()
        current_dpi = self.canvas.fig.dpi if self.canvas.fig.dpi else 100
        
        # Convert to inches
        total_height_inches = total_height_pixels / current_dpi
        frame_height_inches = frame_height_pixels / current_dpi
        top_margin_inches = top_margin_pixels / current_dpi
        between_plots_inches = between_plots_pixels / current_dpi
        
        # Update figure size if auto-fit is enabled
        if self.auto_size_checkbox.isChecked():
            self.canvas.fig.set_size_inches(current_width_inches, total_height_inches)
            fig_height_inches = total_height_inches
        else:
            fig_height_inches = self.canvas.fig.get_figheight()
        
        # Clear any existing subplots
        self.canvas.fig.clear()
        
        # Create subplots with manual positioning
        axes_list = []
        
        for i in range(num_files):
            # Calculate position
            top_position = top_margin_inches + i * (frame_height_inches + between_plots_inches)
            bottom_position = fig_height_inches - top_position - frame_height_inches
            
            # Normalize positions
            left = 0.1
            right = 0.98
            bottom_norm = max(0, bottom_position / fig_height_inches)
            height_norm = min(1, frame_height_inches / fig_height_inches)
            width = right - left
            
            # Skip if outside visible area
            if bottom_norm + height_norm > 1.01 or bottom_norm < -0.01:
                continue
            
            # Create subplot
            ax = self.canvas.fig.add_axes([left, bottom_norm, width, height_norm])
            axes_list.append(ax)
        
        # Track statistics
        max_time = 0
        total_event_count = 0
        
        # Calculate recording starts
        file_recording_starts = {}
        for file_path in selected_files:
            df = self._data[file_path]
            recording_start = self._get_recording_start(df, os.path.basename(file_path))
            file_recording_starts[file_path] = recording_start
            
            if 'Offset' in df.columns:
                file_max_time = df['Offset'].max() - recording_start
                max_time = max(max_time, file_max_time)
        
        # Plot each file
        for file_idx, (file_path, ax) in enumerate(zip(selected_files, axes_list)):
            df = self._data[file_path]
            recording_start = file_recording_starts[file_path]
            event_count = 0
            
            # Plot behaviors in reverse order
            for behavior_idx, behavior in enumerate(reversed(visible_behaviors)):
                z_order = behavior_idx + 1
                
                if 'Event' in df.columns:
                    behavior_events = df[df['Event'].astype(str) == behavior]
                    
                    if behavior_events.empty:
                        continue
                    
                    color_rgb = self._behavior_colors.get(behavior, (0, 0, 0))
                    color = [c/255 for c in color_rgb]
                    
                    for _, event in behavior_events.iterrows():
                        if 'Onset' in event and 'Offset' in event:
                            try:
                                onset = float(event['Onset']) - recording_start
                                offset = float(event['Offset']) - recording_start
                                
                                if onset >= 0:
                                    ax.plot(
                                        [onset, offset], [0, 0], 
                                        linewidth=self._bar_height, solid_capstyle='butt',
                                        color=color, alpha=0.9,
                                        zorder=10 + z_order
                                    )
                                    event_count += 1
                            except (ValueError, TypeError) as e:
                                self.logger.warning(f"Invalid timestamp in event: {event}, error: {str(e)}")
            
            total_event_count += event_count
            
            # Configure this subplot
            self._configure_individual_frame(ax, file_idx, num_files, max_time)
            
            # Set y-axis label
            ax.set_ylabel(str(file_idx + 1), fontweight='bold', rotation=0, ha='right', va='center')
        
        # Draw with warning suppression
        self._draw_canvas_safe()
        
        # Update status
        self.status_label.setText(
            f"Overlay mode (individual frames): {total_event_count} events across {num_files} file(s) with {len(visible_behaviors)} behavior(s)"
        )
    
    def _configure_individual_frame(self, ax, file_idx, num_files, max_time):
        """Configure an individual subplot frame."""
        # Set x-axis limits
        display_max_time = max(max_time, self._x_range_max)
        ax.set_xlim(0, display_max_time)
        
        # Create x-tick intervals
        display_ticks = np.arange(0, display_max_time + self._tick_interval, self._tick_interval)
        ax.set_xticks(display_ticks)
        
        # Only show x-axis labels on the bottom subplot
        if file_idx == num_files - 1:
            if self._time_unit == "Minutes":
                display_tick_labels = [f"{int(tick/60)}" for tick in display_ticks]
                ax.set_xlabel('Time (minutes)', fontweight='bold')
            else:
                display_tick_labels = [f"{tick:.0f}" for tick in display_ticks]
                ax.set_xlabel('Time (seconds)', fontweight='bold')
            
            ax.set_xticklabels(display_tick_labels)
            
            for label in ax.get_xticklabels():
                label.set_fontweight('bold')
        else:
            ax.set_xticklabels([])
            ax.set_xlabel('')
        
        # Set y-axis limits
        y_range = 0.5
        ax.set_ylim(-y_range, y_range)
        ax.set_yticks([])
        
        # Style the frame
        for spine in ax.spines.values():
            spine.set_linewidth(2.5)
            spine.set_zorder(100)
        
        ax.tick_params(axis='both', which='major', 
                      length=6, width=2.5, labelsize=10, zorder=100)
        
        ax.grid(True, axis='x', linestyle='--', alpha=0.5, linewidth=1.8, zorder=0)
        ax.patch.set_alpha(0)
    
    def _configure_plot_axes(self, max_time, num_rows):
        """Configure plot axes, limits, and labels for single frame mode."""
        # Set plot limits
        display_max_time = max(max_time, self._x_range_max)
        
        # Create ticks
        display_ticks = np.arange(0, display_max_time + self._tick_interval, self._tick_interval)
        
        # Set labels based on time unit
        if self._time_unit == "Minutes":
            x_label = 'Time (minutes)'
            display_tick_labels = [f"{int(tick/60)}" for tick in display_ticks]
        else:
            x_label = 'Time (seconds)'
            display_tick_labels = [f"{tick:.0f}" for tick in display_ticks]
        
        # Configure axes
        self.canvas.axes.set_xlim(0, display_max_time)
        self.canvas.axes.set_xticks(display_ticks)
        self.canvas.axes.set_xticklabels(display_tick_labels)
        self.canvas.axes.set_ylim(-0.5, num_rows - 0.5)
        self.canvas.axes.set_xlabel(x_label, fontweight='bold')
        
        # Make text bold
        for label in self.canvas.axes.get_xticklabels():
            label.set_fontweight('bold')
        for label in self.canvas.axes.get_yticklabels():
            label.set_fontweight('bold')
        
        # Style the frame
        for spine in self.canvas.axes.spines.values():
            spine.set_linewidth(2.5)
            spine.set_zorder(100)
        
        self.canvas.axes.tick_params(axis='both', which='major', 
                                    length=6, width=2.5, labelsize=10, zorder=100)
        
        self.canvas.axes.grid(True, axis='x', linestyle='--', alpha=0.5, linewidth=1.8, zorder=0)
        
        # Draw with warning suppression
        self._draw_canvas_safe()
    
    # Override methods for proper event handling
    def resizeEvent(self, event):
        """Handle resize events to ensure proper canvas display."""
        super().resizeEvent(event)
        if hasattr(self, 'auto_size_checkbox') and hasattr(self, 'canvas'):
            if self.auto_size_checkbox.isChecked():
                self.canvas.updateGeometry()
    
    def showEvent(self, event):
        """Handle show events to ensure proper initial display."""
        super().showEvent(event)
        if hasattr(self, 'canvas'):
            self.canvas.updateGeometry()
            if hasattr(self, '_data') and self._data:
                QTimer.singleShot(100, self.update_plot)


class VisualizationView(QWidget):
    """
    View for visualization of annotation data.
    Includes raster plots and other visualization tools.
    
    Signals:
        files_dropped: Emitted when files are dropped (list of file paths)
    """
    
    files_dropped = Signal(list)
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing VisualizationView")
        
        # Enable drag and drop
        self.setAcceptDrops(True)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface."""
        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 0)
        self.layout.setSpacing(3)
        
        # Title
        self.title_label = QLabel("Drop CSV annotation files here for visualization")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setMaximumHeight(30)
        self.layout.addWidget(self.title_label, 0)
        
        # Add raster plot widget
        self.raster_plot = RasterPlotWidget()
        self.layout.addWidget(self.raster_plot, 10)
    
    def set_data(self, data_dict):
        """Set the annotation data for visualization."""
        self.raster_plot.set_data(data_dict)
    
    def set_custom_color_map(self, color_map):
        """Set a custom color mapping for behaviors."""
        self.raster_plot.set_custom_color_map(color_map)
    
    def add_custom_colormaps_to_dropdown(self, colormap_dict):
        """Add custom color maps to the main colormap dropdown."""
        self.raster_plot.add_custom_colormaps_to_dropdown(colormap_dict)
    
    def dragEnterEvent(self, event):
        """Handle drag enter events."""
        if event.mimeData().hasUrls():
            # Check if all URLs are CSV files
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if not file_path.lower().endswith('.csv'):
                    return
            
            event.acceptProposedAction()
            self.logger.debug("Drag enter event accepted for CSV files")
    
    def dropEvent(self, event):
        """Handle drop events."""
        # Check if this view is current
        from PySide6.QtWidgets import QApplication
        main_window = None
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, 'stacked_widget') and hasattr(widget, '_view_index'):
                main_window = widget
                break
        
        # Check if this view is the current view
        is_current = False
        if main_window and hasattr(main_window, 'stacked_widget'):
            current_widget = main_window.stacked_widget.currentWidget()
            if current_widget == self:
                is_current = True
        
        if not is_current:
            self.logger.warning("Drop event ignored - visualization view is not the current view")
            return
        
        # Get file paths from URLs
        file_paths = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            file_paths.append(file_path)
        
        if file_paths:
            self.logger.info(f"Received dropped files in visualization view: {file_paths}")
            self.files_dropped.emit(file_paths)
    
    def showEvent(self, event):
        """Handle show event for the visualization view."""
        super().showEvent(event)
        if hasattr(self, 'raster_plot'):
            self.raster_plot.canvas.updateGeometry()