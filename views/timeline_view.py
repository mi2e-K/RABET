# views/timeline_view.py - Updated RecordingStart marker display
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QScrollArea, QSlider, QSpinBox, QSizePolicy
)
from PySide6.QtCore import Qt, QRect, QPoint, Signal, Slot
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QLinearGradient, QFontMetrics

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
        
        # Set special color for RecordingStart events - match the record button color
        self._recording_start_color = QColor(0x2e, 0xcc, 0x71)  # Match the green of the record button
        
        # Define default behavior order for consistent color assignment
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
        
        # Store the ordered colors
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
            QColor(128, 64, 0, 180)     # Brown with transparency
        ]
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up user interface."""
        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        
        # Timeline canvas scrollable area
        self.timeline_area = QScrollArea()
        self.timeline_area.setWidgetResizable(True)
        
        # Timeline canvas
        self.timeline_canvas = TimelineCanvas(self)
        self.timeline_area.setWidget(self.timeline_canvas)
        
        # Set fixed height for the timeline area (REDUCED HEIGHT)
        self.timeline_area.setMinimumHeight(30)
        self.timeline_area.setMaximumHeight(70)
        
        # Set size policy to prevent vertical expansion
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(70)  # Set fixed height for the whole timeline view
        
        self.layout.addWidget(self.timeline_area)
        
        # Controls layout
        self.controls_layout = QHBoxLayout()
        self.controls_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        
        # Zoom control
        self.zoom_label = QLabel("Zoom:")
        self.controls_layout.addWidget(self.zoom_label)
        
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setMinimum(10)
        self.zoom_slider.setMaximum(500)
        self.zoom_slider.setValue(self._zoom_level)
        self.zoom_slider.setFixedWidth(150)
        self.controls_layout.addWidget(self.zoom_slider)
        
        self.zoom_value = QLabel(f"{self._zoom_level} px/s")
        self.controls_layout.addWidget(self.zoom_value)
        
        # Time display
        self.time_label = QLabel("Position:")
        self.controls_layout.addWidget(self.time_label)
        
        self.time_display = QLabel("00:00:00")
        self.controls_layout.addWidget(self.time_display)
        
        # Add controls to main layout
        self.layout.addLayout(self.controls_layout)
        
        # Connect signals
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
    
    def on_zoom_changed(self, value):
        """
        Handle zoom slider change.
        
        Args:
            value (int): New zoom level
        """
        self._zoom_level = value
        self.zoom_value.setText(f"{value} px/s")
        self.zoom_changed.emit(value)
        self.timeline_canvas.update_size()
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
        self.timeline_canvas.update_size()
        self.timeline_canvas.update()
    
    @Slot(int)
    def set_duration(self, duration_ms):
        """
        Set timeline duration.
        
        Args:
            duration_ms (int): Duration in milliseconds
        """
        self._duration = duration_ms
        self.timeline_canvas.update_size()
        self.timeline_canvas.update()
    
    @Slot(int)
    def set_position(self, position_ms):
        """
        Set current position.
        
        Args:
            position_ms (int): Position in milliseconds
        """
        self._current_position = position_ms
        
        # Update position display
        hours, remainder = divmod(position_ms / 1000, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.time_display.setText(f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}")
        
        # Update canvas
        self.timeline_canvas.update()
        
        # Auto-scroll to keep position in view
        self._auto_scroll()
    
    def _update_colors(self):
        """
        Assign colors to behaviors based on their order in the predefined list.
        This ensures consistent color assignment.
        """
        # Get all unique behaviors
        behaviors = set()
        for event in self._events:
            # Skip RecordingStart events as they'll use a special color
            if event.behavior != "RecordingStart":
                behaviors.add(event.behavior)
        
        # Clear existing colors
        self._colors = {}
        
        # First, assign colors to behaviors in the predefined order
        color_index = 0
        for behavior in self._behavior_order:
            if behavior in behaviors:
                self._colors[behavior] = self._ordered_colors[color_index]
                color_index = (color_index + 1) % len(self._ordered_colors)
                behaviors.remove(behavior)  # Remove from set to avoid duplicate assignment
        
        # Then assign colors to any remaining behaviors not in the predefined list
        for behavior in behaviors:
            self._colors[behavior] = self._ordered_colors[color_index]
            color_index = (color_index + 1) % len(self._ordered_colors)
    
    def get_color(self, behavior):
        """
        Get color for a behavior.
        
        Args:
            behavior (str): Behavior label
            
        Returns:
            QColor: Color for the behavior
        """
        # Use special color for RecordingStart events
        if behavior == "RecordingStart":
            return self._recording_start_color
            
        if behavior not in self._colors:
            self._update_colors()
        
        return self._colors.get(behavior, QColor(127, 127, 127, 180))
    
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


class TimelineCanvas(QWidget):
    """Canvas for drawing timeline events."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.timeline_view = parent
        self.setMinimumHeight(30)  # Reduced height for small timeline
        
        # Single track height in pixels for all events - REDUCED HEIGHT
        self._track_height = 16  # Reduced from 25 to 16 pixels
        
        # Update size based on initial settings
        self.update_size()
    
    def update_size(self):
        """Update canvas size based on duration and zoom level."""
        if self.timeline_view._duration > 0:
            # Calculate width based on duration and zoom level
            width = int(self.timeline_view._duration / 1000 * self.timeline_view._zoom_level)
            
            # Use fixed height of 50px for the timeline canvas
            height = 50
            
            # Set fixed size
            self.setFixedSize(width, height)
    
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
        painter.fillRect(event.rect(), QColor(240, 240, 240))
        
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
            painter.drawText(x + 2, 10, time_text)
    
    def _draw_events(self, painter):
        """
        Draw behavior events on the timeline.
        
        Args:
            painter (QPainter): Painter object
        """
        if not self.timeline_view._events:
            return
        
        # Use a single track for all events, centered in the canvas
        y_position = 15  # Adjust position
        
        # Create a font for the "REC start" label
        rec_font = QFont()
        rec_font.setPointSize(7)
        rec_font.setBold(True)
        font_metrics = QFontMetrics(rec_font)
        
        # Draw all events on a single line with transparent colors
        for event in self.timeline_view._events:
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
                text_y1 = y_position + 5  # Position for "REC"
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
            
            # Check if this event is selected
            is_selected = (self.timeline_view._events.index(event) == self.timeline_view._selected_event)
            
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
                    text_color = QColor(255, 255, 255, 220)  # White, semi-transparent
                    painter.setPen(QPen(text_color))
                    font = QFont()
                    font.setPointSize(7)
                    font.setBold(True)
                    painter.setFont(font)
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, key_text)
    
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
        y_position = 20  # Same position used for drawing
        
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