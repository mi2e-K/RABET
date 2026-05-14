# views/timeline_view.py - Updated RecordingStart marker display
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QScrollArea, QSlider, QSpinBox, QSizePolicy,
    QCheckBox, QFrame
)
from PySide6.QtCore import Qt, QRect, Signal, Slot, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontMetrics

class TimelineView(QWidget):
    """
    View for visualizing behavior events on a timeline.
    
    Signals:
        zoom_changed: Emitted when zoom level changes
        event_selected: Emitted when an event is selected (index)
    """
    
    zoom_changed = Signal(int)
    event_selected = Signal(int)
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing TimelineView")
        
        # Timeline data
        self._events = []
        self._duration = 0
        self._current_position = 0
        self._selected_event = -1
        
        # Display settings
        self._zoom_level = 100  # pixels per second
        self._colors = {}  # behavior -> color
        
        # Set special color for RecordingStart events
        self._recording_start_color = QColor(0x2e, 0xcc, 0x71)
        
        # Define default behavior order for consistent color assignment
        # These are "reserved" colors - like retired jersey numbers
        self._behavior_order = [
            'Attack bites',      # o - Red
            'Sideways threats',  # j - Orange
            'Tail rattles',      # p - Light-purple
            'Chasing',           # q - Pink
            'Social contact',    # a - Sky-blue
            'Self-grooming',     # e - Green
            'Locomotion',        # t - Light-yellow
            'Rearing'            # r - Light-pink
        ]
        
        # Store all available colors
        self._ordered_colors = [
            QColor(255, 75, 0, 180),    # Red with transparency
            QColor(246, 170, 0, 180),   # Orange with transparency
            QColor(201, 172, 230, 200), # Light-purple with transparency
            QColor(255, 128, 130, 180), # Pink with transparency
            QColor(77, 196, 255, 180),  # Sky-blue with transparency
            QColor(3, 175, 122, 180),   # Green with transparency
            QColor(255, 255, 128, 200), # Light-yellow with transparency
            QColor(255, 202, 191, 200), # Light-pink with transparency
            QColor(119, 217, 168, 200), # Light-green1 with transparency
            QColor(216, 242, 85, 200),  # Light-green2 with transparency
            QColor(132, 145, 158, 180), # Gray with transparency
            QColor(128, 64, 0, 180),    # Brown with transparency
            QColor(83, 59, 77, 180),    # Dark-purple with transparency
            QColor(19, 29, 79, 180)     # Navy with transparency
        ]
        
        # Color pool for custom behaviors (indices 8-13 of _ordered_colors).
        # The pool size determines how many distinct colors are cycled when
        # more than that many custom behaviors are introduced.
        self._custom_color_pool_start = 8
        self._custom_color_pool_size = 6  # indices 8, 9, 10, 11, 12, 13
        self._custom_color_pool = list(range(
            self._custom_color_pool_start,
            self._custom_color_pool_start + self._custom_color_pool_size,
        ))
        self._custom_behavior_colors = {}  # Track which custom behaviors have which colors
        
        # Initialize default behavior colors
        self._initialize_default_colors()
        
        # Track next available color index for new behaviors
        self._next_color_index = len(self._behavior_order)
        
        # Connect to action map model changes
        self._setup_action_map_connection()
        
        # Performance settings
        self._timeline_visible = True
        self._update_frequency = 1
        self._frame_counter = 0
        self._performance_mode = False
        self._timeline_scrollbar_height = 12
        self._timeline_canvas_height = 50
        self._timeline_row_height = 74
        
        # Create status labels that will be added to controls
        self.status_message = QLabel("Ready")
        self.video_info = QLabel("")
        self.video_info.setToolTip("")
        self._toolbar_context = "Annotation"
        self.toolbar_info_label = QLabel("Ready")
        self.toolbar_info_label.setToolTip("Ready")
        self._refresh_toolbar_info_label()
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up user interface."""
        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        self.layout.setSpacing(0)
        
        # Timeline canvas scrollable area
        self.timeline_area = QScrollArea()
        self.timeline_area.setFrameShape(QFrame.Shape.NoFrame)
        self.timeline_area.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.timeline_area.setWidgetResizable(False)
        self.timeline_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.timeline_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.timeline_area.horizontalScrollBar().setMinimumHeight(self._timeline_scrollbar_height)
        self.timeline_area.horizontalScrollBar().setMaximumHeight(self._timeline_scrollbar_height)
        self.timeline_area.horizontalScrollBar().show()
        
        # Timeline canvas
        self.timeline_canvas = TimelineCanvas(self)
        self.timeline_canvas.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.timeline_area.setWidget(self.timeline_canvas)
        
        # Reserve enough height for the canvas and the horizontal scrollbar.
        self.timeline_area.setFixedHeight(self._timeline_row_height)
        
        # Set size policy to prevent vertical expansion
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(self._timeline_row_height)
        self.setMaximumHeight(self._timeline_row_height)
        
        self.layout.addWidget(self.timeline_area)
        
        # CRITICAL FIX: Create a container widget for controls to ensure stability
        self.controls_container = QWidget()
        self.controls_container.setMinimumHeight(25)
        self.controls_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        # Controls layout - single horizontal layout for all controls
        self.controls_layout = QHBoxLayout(self.controls_container)
        self.controls_layout.setContentsMargins(10, 2, 10, 2)  # Horizontal margins for better alignment
        self.controls_layout.setSpacing(5)  # Consistent spacing between elements
        
        # Zoom control
        self.zoom_label = QLabel("Zoom:")
        self.controls_layout.addWidget(self.zoom_label)
        
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setMinimum(10)
        self.zoom_slider.setMaximum(500)
        self.zoom_slider.setValue(self._zoom_level)
        self.zoom_slider.setFixedWidth(110)
        self.controls_layout.addWidget(self.zoom_slider)
        
        self.zoom_value = QLabel(str(self._zoom_level))
        self.zoom_value.setToolTip(f"{self._zoom_level} px/s")
        self.controls_layout.addWidget(self.zoom_value)
        
        # Add some spacing
        self.controls_layout.addSpacing(15)
        
        # Timeline visibility checkbox
        self.timeline_visible_checkbox = QCheckBox("Show Timeline")
        self.timeline_visible_checkbox.setChecked(True)
        self.timeline_visible_checkbox.setToolTip("Toggle timeline visibility to improve performance")
        # Prevent spacebar from toggling checkbox
        self.timeline_visible_checkbox.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.timeline_visible_checkbox.stateChanged.connect(self.on_timeline_visibility_changed)
        self.controls_layout.addWidget(self.timeline_visible_checkbox)
        
        # Add some spacing
        self.controls_layout.addSpacing(8)
        
        # Update frequency control with spinbox
        self.update_freq_label = QLabel("Update Rate:")
        self.controls_layout.addWidget(self.update_freq_label)
        
        self.update_freq_spin = QSpinBox()
        self.update_freq_spin.setMinimum(1)
        self.update_freq_spin.setMaximum(20)
        self.update_freq_spin.setValue(1)  # Default: every frame
        self.update_freq_spin.setSingleStep(1)
        self.update_freq_spin.setFixedWidth(50)
        self.update_freq_spin.setToolTip("Update timeline every N frames (1 = smoothest, higher = better performance)")
        self.update_freq_spin.valueChanged.connect(self.on_update_frequency_changed)
        self.controls_layout.addWidget(self.update_freq_spin)
        
        # Add stretch to push status messages to the right
        self.controls_layout.addStretch()
        
        # Add separator before status messages
        separator = QLabel("|")
        separator.setStyleSheet("color: #ccc;")
        self.controls_layout.addWidget(separator)
        self.controls_layout.addSpacing(8)
        
        # Add status message
        self.status_message.setStyleSheet("font-weight: normal;")
        self.controls_layout.addWidget(self.status_message)
        
        # Add another separator
        self.controls_layout.addSpacing(8)
        separator2 = QLabel("|")
        separator2.setStyleSheet("color: #ccc;")
        self.controls_layout.addWidget(separator2)
        self.controls_layout.addSpacing(8)
        
        # Add video info
        self.video_info.setStyleSheet("font-weight: normal;")
        self.controls_layout.addWidget(self.video_info)
        
        # Add some margin at the end
        self.controls_layout.addSpacing(10)
        
        # Add controls container to main layout
        self.layout.addWidget(self.controls_container)
        
        # Connect signals
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
    
    def set_status_message(self, message):
        """
        Set status message.
        
        Args:
            message (str): Status message
        """
        self.status_message.setText(message)
        self.status_message.setToolTip(message)
        self._refresh_toolbar_info_label()
    
    def set_video_info(self, info):
        """
        Set video information.
        
        Args:
            info (str): Video information
        """
        self.video_info.setText(info)
        self.video_info.setToolTip(info)
        self._refresh_toolbar_info_label()

    def set_toolbar_context(self, context):
        """
        Set which view currently owns the compact toolbar summary.

        Args:
            context (str): Active top-level view name
        """
        self._toolbar_context = context
        self._refresh_toolbar_info_label()

    def _refresh_toolbar_info_label(self):
        """Refresh the compact one-line toolbar info label."""
        parts = []
        status_text = self.status_message.text().strip()
        video_text = self.video_info.text().strip()

        if self._toolbar_context == "Annotation":
            if status_text:
                parts.append(status_text)
            if video_text:
                parts.append(video_text)
            summary = " | ".join(parts) if parts else "Ready"
        else:
            if status_text and status_text != "Ready":
                parts.append(status_text)
            summary = " | ".join(parts)

        self.toolbar_info_label.setText(summary)
        self.toolbar_info_label.setToolTip(summary)

    def get_controls_for_playback_row(self):
        """Return timeline controls that should live on the playback row."""
        return [
            self.zoom_label,
            self.zoom_slider,
            self.zoom_value,
            self.timeline_visible_checkbox,
            self.update_freq_label,
            self.update_freq_spin,
        ]

    def get_toolbar_info_widget(self):
        """Return the compact right-aligned toolbar info label."""
        return self.toolbar_info_label

    def use_external_auxiliary_controls(self):
        """
        Hide the legacy control container once the widgets are moved elsewhere.
        """
        self.controls_container.hide()
        self.controls_container.setMinimumHeight(0)
        self.controls_container.setMaximumHeight(0)
        self.layout.setSpacing(0)
        QTimer.singleShot(0, self._refresh_timeline_geometry)

    def _apply_timeline_visibility_height(self):
        """Keep the timeline row height stable when shown and collapsed when hidden."""
        if self._timeline_visible:
            self.timeline_area.setFixedHeight(self._timeline_row_height)
            self.setMinimumHeight(self._timeline_row_height)
            self.setMaximumHeight(self._timeline_row_height)
            self.timeline_area.horizontalScrollBar().show()
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(0)

        self.updateGeometry()

    def _refresh_timeline_geometry(self, preserve_scroll=True):
        """Recompute timeline sizes after layout changes so the canvas and seek bar stay visible."""
        scroll_bar = self.timeline_area.horizontalScrollBar()
        scroll_value = scroll_bar.value() if preserve_scroll else 0

        self._apply_timeline_visibility_height()

        if self._timeline_visible:
            self.timeline_canvas.update_size()
            scroll_bar.show()
            scroll_bar.setValue(min(scroll_value, scroll_bar.maximum()))

        self.timeline_area.updateGeometry()
        self.layout.activate()
        self.update()
    
    def on_zoom_changed(self, value):
        """
        Handle zoom slider change.
        
        Args:
            value (int): New zoom level
        """
        self._zoom_level = value
        self.zoom_value.setText(str(value))
        self.zoom_value.setToolTip(f"{value} px/s")
        self.zoom_changed.emit(value)
        self._refresh_timeline_geometry()
        self.timeline_canvas.update()
    
    @Slot(list)
    def set_events(self, events):
        """
        Set timeline events.
        
        Args:
            events (list): List of BehaviorEvent objects
        """
        self._events = events
        self._update_colors()
        self._refresh_timeline_geometry()
        self.timeline_canvas.update()
    
    @Slot(int)
    def set_duration(self, duration_ms):
        """
        Set timeline duration.
        
        Args:
            duration_ms (int): Duration in milliseconds
        """
        self._duration = duration_ms
        self._refresh_timeline_geometry()
        self.timeline_canvas.update()
    
    @Slot(int)
    def set_position(self, position_ms):
        """
        Set current position.
        
        Args:
            position_ms (int): Position in milliseconds
        """
        self._current_position = position_ms
        
        # Only update canvas if visible and performance settings allow
        if self._timeline_visible and self.should_update():
            self.timeline_canvas.update()
        
        # Auto-scroll to keep position in view (only if visible)
        if self._timeline_visible:
            self._auto_scroll()
        
        # CRITICAL FIX: Ensure controls remain visible during updates
        # Force a layout update to prevent control row from collapsing
        self.controls_layout.update()
        self.update()
    
    def _update_colors(self):
        """
        Update colors only for new behaviors not already in the color map.
        This maintains color consistency throughout the session.
        """
        # Get all unique behaviors from current events
        behaviors = set()
        for event in self._events:
            # Skip RecordingStart events as they use a special color
            if event.behavior != "RecordingStart":
                behaviors.add(event.behavior)
        
        # Only assign colors to behaviors that don't already have one
        for behavior in behaviors:
            if behavior not in self._colors:
                # Assign the next available color
                if self._next_color_index < len(self._ordered_colors):
                    self._colors[behavior] = self._ordered_colors[self._next_color_index]
                    self.logger.debug(f"Assigned new color to '{behavior}': index {self._next_color_index}")
                    self._next_color_index += 1
                else:
                    # If we run out of predefined colors, cycle back
                    color_index = self._next_color_index % len(self._ordered_colors)
                    self._colors[behavior] = self._ordered_colors[color_index]
                    self.logger.warning(f"Cycling colors - assigned color index {color_index} to '{behavior}'")
                    self._next_color_index += 1
    
    def _setup_action_map_connection(self):
        """
        Connect to action map model to track when behaviors are added/removed.
        """
        # This would need to be connected in the main controller
        # For now, we'll add a method that can be called when behaviors change
        pass

    def _initialize_default_colors(self):
        """
        Initialize colors for all predefined behaviors at startup.
        """
        for i, behavior in enumerate(self._behavior_order):
            if i < len(self._ordered_colors):
                self._colors[behavior] = self._ordered_colors[i]
                self.logger.debug(f"Reserved color for '{behavior}': {self._ordered_colors[i].name()}")
        
        self.logger.info(f"Initialized {len(self._colors)} reserved behavior colors")

    def on_behavior_removed(self, behavior):
        """
        Called when a behavior is removed from the action map.
        
        Args:
            behavior (str): The behavior that was removed
        """
        # Check if it's a predefined behavior
        if behavior in self._behavior_order:
            # Predefined behaviors keep their color reservation
            self.logger.info(f"Behavior '{behavior}' removed but color remains reserved")
        else:
            # Custom behavior - release its color back to the pool
            if behavior in self._custom_behavior_colors:
                color_index = self._custom_behavior_colors[behavior]
                self._custom_color_pool.append(color_index)
                self._custom_color_pool.sort()  # Keep pool sorted
                
                del self._custom_behavior_colors[behavior]
                if behavior in self._colors:
                    del self._colors[behavior]
                
                self.logger.info(f"Released color index {color_index} from behavior '{behavior}'")

    def get_color(self, behavior):
        """
        Get color for a behavior with smart assignment.
        
        Args:
            behavior (str): Behavior label
            
        Returns:
            QColor: Color for the behavior
        """
        # Use special color for RecordingStart events
        if behavior == "RecordingStart":
            return self._recording_start_color
        
        # Check if behavior already has a color assigned
        if behavior in self._colors:
            return self._colors[behavior]
        
        # Check if it's a predefined behavior that should have a reserved color
        if behavior in self._behavior_order:
            index = self._behavior_order.index(behavior)
            self._colors[behavior] = self._ordered_colors[index]
            return self._colors[behavior]
        
        # It's a custom behavior - assign from the pool
        if self._custom_color_pool:
            color_index = self._custom_color_pool.pop(0)
            self._colors[behavior] = self._ordered_colors[color_index]
            self._custom_behavior_colors[behavior] = color_index
            
            self.logger.info(f"Assigned color index {color_index} to custom behavior '{behavior}'")
            return self._colors[behavior]
        else:
            # No colors left in pool - cycle through the full custom-color
            # range. Previous releases (<=1.2.0) had a bug here that only
            # cycled through 4 indices instead of the full 6, so 5th+
            # overflow behaviours collapsed onto the same colour. We now
            # use the actual pool size as the modulus.
            already_assigned = len(self._custom_behavior_colors)
            overflow_index = (
                (already_assigned - self._custom_color_pool_size)
                % self._custom_color_pool_size
            ) + self._custom_color_pool_start
            color = self._ordered_colors[overflow_index]

            self.logger.warning(
                f"Color pool exhausted, reusing color index {overflow_index} "
                f"for '{behavior}'"
            )
            self._colors[behavior] = color
            return color

    def get_color_status(self):
        """
        Get current color assignment status for debugging/UI.
        
        Returns:
            dict: Status information about color assignments
        """
        return {
            'reserved_colors': len([b for b in self._behavior_order if b in self._colors]),
            'custom_colors_used': len(self._custom_behavior_colors),
            'colors_available': len(self._custom_color_pool),
            'total_behaviors': len(self._colors)
        }
    
    def reset_colors_to_defaults(self):
        """
        Reset all colors to default assignments.
        Useful for testing or when user wants to reset color scheme.
        """
        self._colors = {}
        self._next_color_index = len(self._behavior_order)
        self._initialize_default_colors()
        self.logger.info("Reset all behavior colors to defaults")
        
        # Trigger a repaint
        self.timeline_canvas.update()
    
    def _auto_scroll(self):
        """Auto-scroll to keep current position in view."""
        # Convert position to pixels
        position_px = int(self._current_position / 1000 * self._zoom_level)
        
        # Get viewport width
        viewport_width = self.timeline_area.viewport().width()
        
        # Calculate scroll position to keep current position in view
        scroll_pos = max(0, position_px - viewport_width // 2)
        
        # Set horizontal scroll position
        self.timeline_area.horizontalScrollBar().setValue(scroll_pos)
    
    @Slot(int)
    def select_event(self, index):
        """
        Select an event.
        
        Args:
            index (int): Index of the event
        """
        if 0 <= index < len(self._events):
            self._selected_event = index
            self.timeline_canvas.update()
            self.event_selected.emit(index)

    def on_timeline_visibility_changed(self, state):
        """
        Handle timeline visibility checkbox state change.
        
        Args:
            state: Qt.CheckState value
        """
        self._timeline_visible = (state == Qt.CheckState.Checked.value)
        self.timeline_area.setVisible(self._timeline_visible)
        
        # Update zoom controls visibility based on timeline visibility
        self.zoom_label.setVisible(self._timeline_visible)
        self.zoom_slider.setVisible(self._timeline_visible)
        self.zoom_value.setVisible(self._timeline_visible)
        self._refresh_timeline_geometry(preserve_scroll=False)
        
        if self.controls_container.isVisible():
            self.controls_container.update()
        
        self.logger.debug(f"Timeline visibility set to: {self._timeline_visible}")
    
    def ensure_controls_visible(self):
        """
        Ensure timeline controls remain visible.
        This method can be called during video state changes.
        """
        widgets = [
            self.zoom_label,
            self.zoom_slider,
            self.zoom_value,
            self.timeline_visible_checkbox,
            self.update_freq_label,
            self.update_freq_spin,
            self.status_message,
            self.video_info,
            self.toolbar_info_label,
        ]

        for widget in widgets:
            widget.update()

        self._refresh_timeline_geometry()

        parent = self.parent()
        if parent:
            parent.updateGeometry()
            parent.update()

    def showEvent(self, event):
        """Refresh the timeline after the widget is first laid out."""
        super().showEvent(event)
        QTimer.singleShot(0, self._refresh_timeline_geometry)

    def resizeEvent(self, event):
        """Keep the canvas and scrollbar aligned to the available viewport size."""
        super().resizeEvent(event)
        QTimer.singleShot(0, self._refresh_timeline_geometry)

    def on_update_frequency_changed(self, value):
        """
        Handle update frequency spinbox change.
        
        Args:
            value (int): Update frequency (1-10)
        """
        self._update_frequency = value
        self.logger.debug(f"Timeline update frequency set to: every {self._update_frequency} frame(s)")

    def should_update(self):
        """
        Check if timeline should be updated based on performance settings.
        
        Returns:
            bool: True if timeline should be updated, False otherwise
        """
        if not self._timeline_visible:
            return False
        
        # Increment frame counter
        self._frame_counter += 1
        
        # Check if we should update based on frequency setting
        if self._frame_counter >= self._update_frequency:
            self._frame_counter = 0
            return True
        
        return False

class TimelineCanvas(QWidget):
    """Canvas for drawing timeline events."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.timeline_view = parent
        self.setMinimumHeight(self.timeline_view._timeline_canvas_height)
        
        # Single track height in pixels for all events
        self._track_height = 18  # Slightly increased from 16 pixels
        
        # Performance mode flag
        self._performance_mode = False
        
        # Update size based on initial settings
        self.update_size()
    
    def update_size(self):
        """Update canvas size based on duration and zoom level."""
        viewport = self.timeline_view.timeline_area.viewport()
        viewport_width = max(1, viewport.width())
        if self.timeline_view._duration > 0:
            width = int(self.timeline_view._duration / 1000 * self.timeline_view._zoom_level)
            width = max(width, viewport_width + 1)
        else:
            width = viewport_width + 1

        height = max(1, viewport.height())
        self.setFixedSize(width, height)

    def _track_y_position(self):
        """Return a stable vertical position for the single event track."""
        available_vertical_space = max(0, self.height() - self._track_height - 4)
        return min(20, max(10, available_vertical_space // 2))
    
    def paintEvent(self, event):
        """
        Paint the timeline canvas.
        
        Args:
            event: Paint event
        """
        painter = QPainter(self)
        
        # Enable antialiasing
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw background
        painter.fillRect(self.rect(), QColor(240, 240, 240))
        
        # Draw time markers
        self._draw_time_markers(painter)
        
        # Draw events
        self._draw_events(painter)
        
        # Draw current position
        self._draw_position_marker(painter)
    
    def _draw_time_markers(self, painter):
        """
        Draw time markers on the timeline.
        
        Args:
            painter (QPainter): Painter object
        """
        if self.timeline_view._duration == 0:
            return
        
        # Set text font - LARGER SIZE and DARKER COLOR
        font = QFont()
        font.setPointSize(8)  # Increased from 6 to 8
        painter.setFont(font)
        
        # Set darker gray color for text
        text_color = QColor(60, 60, 60)  # Dark gray
        
        # Set pen for lines
        line_pen = QPen(QColor(200, 200, 200))
        line_pen.setWidth(1)
        
        # Calculate marker interval based on zoom level
        # Aim for markers approximately every 100 pixels
        seconds_per_marker = max(1, int(100 / self.timeline_view._zoom_level))
        
        # Draw markers
        for seconds in range(0, int(self.timeline_view._duration / 1000) + 1, seconds_per_marker):
            # Calculate x position
            x = int(seconds * self.timeline_view._zoom_level)
            
            # Draw vertical line
            painter.setPen(line_pen)
            painter.drawLine(x, 0, x, self.height())
            
            # Format time - simplified for small display
            minutes, seconds = divmod(seconds, 60)
            time_text = f"{int(minutes):02d}:{int(seconds):02d}"
            
            # Draw time text at the top with darker color
            painter.setPen(QPen(text_color))
            painter.drawText(x + 2, 12, time_text)
    
    def _draw_events(self, painter):
        """
        Draw behavior events on the timeline.
        
        Args:
            painter (QPainter): Painter object
        """
        if not self.timeline_view._events:
            return
        
        # Use a single track for all events, centered in the canvas
        y_position = self._track_y_position()
        
        # Create a font for the "REC start" label
        rec_font = QFont()
        rec_font.setPointSize(7)
        rec_font.setBold(True)
        font_metrics = QFontMetrics(rec_font)
        
        # Draw all events on a single line with transparent colors. Enumerate
        # so we can compare ``i`` against the selected index in O(1) instead
        # of calling ``list.index`` on every iteration (which was O(N^2)).
        selected_index = self.timeline_view._selected_event
        for i, event in enumerate(self.timeline_view._events):
            # Calculate coordinates
            x1 = int(event.onset / 1000 * self.timeline_view._zoom_level)

            # Special case for RecordingStart events - draw as vertical line with text
            if event.behavior == "RecordingStart":
                # Draw a vertical dashed line
                rec_pen = QPen(self.timeline_view._recording_start_color)
                rec_pen.setWidth(2)  # Thicker line
                rec_pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(rec_pen)
                
                # Draw vertical line at the start position
                painter.drawLine(x1, 0, x1, self.height())
                
                # Set up text for "REC" on one line and "start" on another
                painter.setFont(rec_font)
                painter.setPen(QPen(Qt.black))  # Black text
                
                # Calculate text position (to the left of the line)
                text_x = max(5, x1 - font_metrics.horizontalAdvance("REC") - 5)
                text_y1 = y_position  # Position for "REC"
                text_y2 = text_y1 + font_metrics.height()  # Position for "start"
                
                # Draw the text
                painter.drawText(text_x, text_y1, "REC")
                painter.drawText(text_x, text_y2, "start")
                
                # Skip the rest of the loop for RecordingStart events
                continue
            
            # Use event duration or extend to current position if ongoing
            if event.offset is not None:
                x2 = int(event.offset / 1000 * self.timeline_view._zoom_level)
            else:
                x2 = int(self.timeline_view._current_position / 1000 * self.timeline_view._zoom_level)
            
            width = max(2, x2 - x1)  # Ensure minimum width

            # O(1) selection check using enumerate index instead of list.index
            is_selected = (i == selected_index)
            
            # Get transparent color for behavior
            color = self.timeline_view.get_color(event.behavior)
            
            # Draw event block
            rect = QRect(x1, y_position, width, self._track_height)
            
            # Set brush and pen
            if is_selected:
                # For selected events, use a solid border
                pen = QPen(Qt.black)
                pen.setWidth(2)
                painter.setPen(pen)
            else:
                # For non-selected events, use a lighter border
                painter.setPen(QPen(color.darker()))
            
            # Use transparent color for fill
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(rect, 3, 3)
            
            # Draw the key instead of the behavior initial if there's enough space
            if width > 10:
                # Use the key associated with the event
                key_text = event.key
                
                # Make sure we have a valid key
                if key_text:
                    # Determine text color based on background brightness
                    text_color = self._get_text_color_for_background(color)
                    
                    painter.setPen(QPen(text_color))
                    font = QFont()
                    font.setPointSize(7)
                    font.setBold(True)
                    painter.setFont(font)
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, key_text)

    def _get_text_color_for_background(self, bg_color):
        """
        Determine appropriate text color (black or white) based on background color brightness.
        
        Args:
            bg_color (QColor): Background color
            
        Returns:
            QColor: Text color (black for light backgrounds, white for dark)
        """
        # Calculate perceived brightness using standard formula
        # Human perception weights: Red=0.299, Green=0.587, Blue=0.114
        brightness = (bg_color.red() * 0.299 + 
                     bg_color.green() * 0.587 + 
                     bg_color.blue() * 0.114)
        
        # If brightness is high (light color), use black text; otherwise use white
        if brightness > 170:  # Threshold for determining light vs dark
            return QColor(0, 0, 0, 255)  # Black
        else:
            return QColor(255, 255, 255, 255)  # White
    
    def _draw_position_marker(self, painter):
        """
        Draw current position marker.
        
        Args:
            painter (QPainter): Painter object
        """
        if self.timeline_view._duration == 0:
            return
        
        # Calculate x position
        x = int(self.timeline_view._current_position / 1000 * self.timeline_view._zoom_level)
        
        # Draw vertical line
        pen = QPen(QColor(255, 0, 0))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawLine(x, 0, x, self.height())
    
    def mousePressEvent(self, event):
        """
        Handle mouse press events.
        
        Args:
            event: Mouse event
        """
        # Check if clicked on an event
        y_position = self._track_y_position()
        
        for i, event_obj in enumerate(self.timeline_view._events):
            # For RecordingStart events, check for click near the vertical line
            if event_obj.behavior == "RecordingStart":
                x = int(event_obj.onset / 1000 * self.timeline_view._zoom_level)
                # Create a narrow click area around the line
                if abs(event.position().x() - x) <= 5:  # 5 pixels tolerance
                    self.timeline_view.select_event(i)
                    break
                continue
                
            # For regular events
            x1 = int(event_obj.onset / 1000 * self.timeline_view._zoom_level)
            
            if event_obj.offset is not None:
                x2 = int(event_obj.offset / 1000 * self.timeline_view._zoom_level)
            else:
                x2 = int(self.timeline_view._current_position / 1000 * self.timeline_view._zoom_level)
            
            width = max(2, x2 - x1)
            
            # Check if click is within event rectangle
            if (x1 <= event.position().x() <= x1 + width and 
                y_position <= event.position().y() <= y_position + self._track_height):
                self.timeline_view.select_event(i)
                break

    def set_performance_mode(self, enabled):
        """
        Set performance mode for simplified rendering.
        
        Args:
            enabled (bool): Whether to enable performance mode
        """
        self._performance_mode = enabled
        self.update()
