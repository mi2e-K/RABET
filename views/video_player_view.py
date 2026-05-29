# views/video_player_view.py - Enhanced loading overlay handling
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QFrame, QSpinBox, QSizePolicy,
    QCheckBox, QScrollArea
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QDateTime
from PySide6.QtGui import (
    QDragEnterEvent, QDropEvent, QGuiApplication, QImage, QPixmap,
)

from utils.app_icon import find_resource_path
from utils.loading_overlay import LoadingOverlay
from utils.video_detection import is_video_file

class VideoPlayerView(QWidget):
    """
    View for video playback and controls.
    
    Signals:
        play_clicked: Emitted when play button is clicked
        pause_clicked: Emitted when pause button is clicked
        seek_requested: Emitted when seek is requested (position in milliseconds)
        step_forward_clicked: Emitted when step forward button is clicked
        step_backward_clicked: Emitted when step backward button is clicked
        rate_changed: Emitted when playback rate is changed (float)
        volume_changed: Emitted when volume is changed (int 0-100)
        video_dropped: Emitted when video file is dropped (file path)
        frame_by_frame_mode_changed: Emitted when frame-by-frame mode is toggled (bool)
    """
    
    play_clicked = Signal()
    pause_clicked = Signal()
    seek_requested = Signal(int)
    step_forward_clicked = Signal(int)
    step_backward_clicked = Signal(int)
    rate_changed = Signal(float)
    volume_changed = Signal(int)
    video_dropped = Signal(str)  # New signal for drag and drop
    frame_by_frame_mode_changed = Signal(bool)  # New signal for frame-by-frame mode
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing VideoPlayerView")
        
        # Enable drag and drop
        self.setAcceptDrops(True)
        
        # CRITICAL FIX: Set minimum size to prevent collapse
        self.setMinimumHeight(300)
        
        self.setup_ui()
        self.connect_signals()
        
        # Set initial state
        self._is_playing = False
        self._has_video = False
        self._duration = 1  # Avoid division by zero
        
        # Add throttling for slider updates
        self._last_seek_time = 0
        self._slider_throttle_ms = 100  # Limit seek rate to every 100ms
        
        # Flag to prevent button rapid-fire issues
        self._step_in_progress = False
        self._step_cooldown_ms = 300  # Longer cooldown to ensure proper refresh
        self._step_timer = QTimer()
        self._step_timer.setSingleShot(True)
        self._step_timer.timeout.connect(self._reset_step_flag)
        
        # Flag to track if controls are disabled
        self._controls_disabled = False
        
        # Add visual feedback for step buttons
        self._forward_button_timer = QTimer()
        self._forward_button_timer.setSingleShot(True)
        self._forward_button_timer.timeout.connect(self._reset_forward_button)
        
        self._backward_button_timer = QTimer()
        self._backward_button_timer.setSingleShot(True) 
        self._backward_button_timer.timeout.connect(self._reset_backward_button)
        
        # Original button styles
        self._original_button_style = ""
        
        # Create loading overlay
        self._loading_overlay = LoadingOverlay(self)
        self.loading_overlay = self._loading_overlay  # Public access for other components

        # Frame-by-frame mode state
        self._frame_by_frame_mode = False
    
    def setup_ui(self):
        """Set up user interface."""
        # Main layout
        self.layout = QVBoxLayout(self)
        # Reduce margins and spacing
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(1)

        # Video display area.
        #
        # 1.3.1 migration note: under the old VLC backend, ``video_frame``
        # was the native surface that libVLC drew into via set_hwnd /
        # set_xwindow / set_nsobject. With the new PyAV backend we render
        # frames ourselves into a QImage and push them to a QLabel, so
        # the QFrame is reduced to a cosmetic container (border + black
        # background from theme_manager's ``QFrame#video_frame`` rule).
        # The actual frame display happens in ``self.video_display_label``
        # which the controller wires up to ``VideoModel.frame_ready``.
        self.video_frame = QFrame()
        self.video_frame.setFrameShape(QFrame.Shape.Panel)
        self.video_frame.setFrameShadow(QFrame.Shadow.Sunken)
        self.video_frame.setObjectName("video_frame")
        self.video_frame.setMinimumHeight(200)

        # Keep the explicit expanding policy: nothing in the new render
        # path resizes this for us, so without it the frame collapses
        # when the surrounding splitter shrinks.
        self.video_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.placeholder_background = QWidget(self.video_frame)
        self.placeholder_background.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.placeholder_background.setObjectName("videoPlaceholderBackground")
        self._apply_placeholder_background_style()

        # NEW: dedicated QLabel that holds the decoded frame as a QPixmap.
        # It sits inside the QFrame's vertical layout and gets a freshly
        # scaled pixmap from ``display_frame`` every time the model emits
        # ``frame_ready``. Aspect ratio is preserved manually because we
        # do the scaling ourselves (setScaledContents would stretch).
        self.video_display_label = QLabel()
        self.video_display_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_display_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.video_display_label.setStyleSheet(
            "background-color: #000000;"
        )
        self.video_display_label.setMinimumSize(1, 1)
        self.video_display_label.setScaledContents(False)

        # Add drop indicator label
        self.drop_label = QLabel("Drop Video File Here")
        self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_label.setStyleSheet("""
            color: white;
            font-size: 24px;
            font-weight: bold;
            background-color: rgba(0, 0, 0, 0.5);
            padding: 10px;
            border-radius: 5px;
        """)

        # Layout: stack the display label, drop hint, and placeholder
        # background inside the QFrame. The display label lives in the
        # main layout so it stretches with the frame; the drop hint
        # overlays via stacking order (raise_).
        self.video_layout = QVBoxLayout(self.video_frame)
        self.video_layout.setContentsMargins(0, 0, 0, 0)
        self.video_layout.setSpacing(0)
        self.video_layout.addWidget(self.video_display_label)
        self.placeholder_background.lower()

        # Drop label as a free-floating child so it can sit centered over
        # the display label regardless of the pixmap inside.
        self.drop_label.setParent(self.video_frame)
        self.drop_label.raise_()

        # Drop-zone icon, stacked above the "Drop Video File Here" text.
        # Also a free-floating child of the video frame; its geometry is
        # managed alongside drop_label in _sync_video_placeholder_geometry.
        self.drop_icon = QLabel(self.video_frame)
        self.drop_icon.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.drop_icon.setStyleSheet("background-color: transparent;")
        self.drop_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_icon_height = 120  # logical px
        self._drop_icon_source = QPixmap()
        _drop_icon_path = find_resource_path("drop_video_file.png")
        if _drop_icon_path:
            self._drop_icon_source = QPixmap(_drop_icon_path)
        self._update_drop_icon_pixmap()
        self.drop_icon.raise_()

        # Cache of the most recently decoded QImage, so resizeEvent can
        # re-scale it without forcing the model to re-decode.
        self._last_qimage: QImage | None = None

        # Let Qt repaint the empty placeholder surface when no video is loaded.
        self.video_frame.setAttribute(Qt.WA_OpaquePaintEvent)

        # Ensure it's visible
        self.video_frame.setVisible(True)

        self.layout.addWidget(self.video_frame)
        
        # Create a container for controls to ensure they don't collapse
        self.controls_container = QWidget()
        self.controls_container.setMinimumHeight(80)
        self.controls_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.controls_container_layout = QVBoxLayout(self.controls_container)
        self.controls_container_layout.setContentsMargins(0, 0, 0, 0)
        self.controls_container_layout.setSpacing(2)
        
        # Time display
        self.time_layout = QHBoxLayout()
        self.time_layout.setContentsMargins(2, 0, 2, 0)
        self.current_time_label = QLabel("00:00:00")
        self.duration_label = QLabel("00:00:00")
        self.time_layout.addWidget(self.current_time_label)
        self.time_layout.addStretch()
        self.time_layout.addWidget(self.duration_label)
        self.controls_container_layout.addLayout(self.time_layout)
        
        # Position slider
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setMinimum(0)
        self.position_slider.setMaximum(1000)
        self.position_slider.setValue(0)
        self.controls_container_layout.addWidget(self.position_slider)
        
        # Control buttons layout
        self.controls_layout = QHBoxLayout()
        self.controls_layout.setContentsMargins(2, 0, 2, 0)
        # Reduce spacing between elements
        self.controls_layout.setSpacing(4)
        
        # Combined Play/Pause button
        self.play_pause_button = QPushButton("Play")
        self.play_pause_button.setMinimumWidth(96)
        # Prevent space key from activating button when it has focus, to avoid duplicate actions
        self.play_pause_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.controls_layout.addWidget(self.play_pause_button)
        
        # Step backward button
        self.step_backward_button = QPushButton("<<")
        self.step_backward_button.setObjectName("stepBackwardButton")
        self.step_backward_button.setMinimumWidth(56)
        # Prevent from stealing focus
        self.step_backward_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        # Save original style
        self._original_button_style = self.step_backward_button.styleSheet()
        self.controls_layout.addWidget(self.step_backward_button)
        
        # Step forward button
        self.step_forward_button = QPushButton(">>")
        self.step_forward_button.setObjectName("stepForwardButton")
        self.step_forward_button.setMinimumWidth(56)
        # Prevent from stealing focus
        self.step_forward_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.controls_layout.addWidget(self.step_forward_button)
        
        # Step size control - REDUCED SPACING
        self.step_size_label = QLabel("Step (ms):")
        # Make label more compact
        self.step_size_label.setStyleSheet("margin-right: 1px;")
        self.controls_layout.addWidget(self.step_size_label)
        
        self.step_size_spin = QSpinBox()
        self.step_size_spin.setMinimum(10)
        self.step_size_spin.setMaximum(1000)
        self.step_size_spin.setValue(100)
        self.step_size_spin.setSingleStep(10)
        # Make the spinbox more compact
        self.step_size_spin.setFixedWidth(90)  # Increased width from 60 to 90 pixels
        self.controls_layout.addWidget(self.step_size_spin)
        
        # Add frame-by-frame mode checkbox
        self.frame_by_frame_checkbox = QCheckBox("Frame-by-Frame Mode")
        self.frame_by_frame_checkbox.setToolTip("When enabled, arrow keys will move exactly one frame at a time")
        self.frame_by_frame_checkbox.setChecked(False)
        # CRITICAL FIX: Set focus policy to prevent space key from toggling the checkbox
        self.frame_by_frame_checkbox.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.controls_layout.addWidget(self.frame_by_frame_checkbox)
        
        # Add a little spacing
        self.controls_layout.addSpacing(4)
        
        self.rate_label = QLabel("Speed:")
        self.controls_layout.addWidget(self.rate_label)
        
        # Use slider instead of dropdown for playback rate
        self.rate_slider = QSlider(Qt.Orientation.Horizontal)
        self.rate_slider.setMinimum(25)  # 0.25x
        self.rate_slider.setMaximum(200) # 2.00x
        self.rate_slider.setValue(100)   # 1.00x
        self.rate_slider.setFixedWidth(130)
        self.controls_layout.addWidget(self.rate_slider)
        
        self.rate_value_label = QLabel("1.00x")
        self.rate_value_label.setFixedWidth(38)
        self.controls_layout.addWidget(self.rate_value_label)
        
        # Add reset button for playback rate
        self.rate_reset_button = QPushButton("Reset")
        self.rate_reset_button.setToolTip("Reset playback speed to 1x")
        self.rate_reset_button.setFixedWidth(56)
        self.rate_reset_button.clicked.connect(self.reset_playback_rate)
        # Prevent button from capturing focus, so space key will still work for play/pause
        self.rate_reset_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.controls_layout.addWidget(self.rate_reset_button)
        
        # Volume control: fully removed in 1.3.1 along with the VLC
        # backend. Audio is not played at all under the PyAV backend, so
        # the slider/label and their ``volume_changed`` signal have no
        # consumer. The ``volume_changed`` Signal declaration above is
        # kept harmless for binary compatibility with any external code
        # that still listens to it, but nothing in the app emits it.
        
        # Put the playback controls row inside a horizontal scroll area.
        # The row packs many fixed-width controls (play / step / speed /
        # zoom / relocated timeline aux) that do NOT wrap. Left as a raw
        # layout it forces a ~1600 px minimum width on the whole window,
        # which clips the UI on laptops and 1080p displays (it only ever
        # "fit" on very wide monitors). Wrapping it lets the window shrink
        # to the screen; on a narrow window a thin horizontal scrollbar
        # appears instead of pushing controls off-screen.
        self.controls_row_widget = QWidget()
        self.controls_row_widget.setLayout(self.controls_layout)
        self.controls_scroll = QScrollArea()
        self.controls_scroll.setObjectName("controlsScroll")
        self.controls_scroll.setWidget(self.controls_row_widget)
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.controls_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.controls_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.controls_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        # Fixed height = one control row + room for the horizontal
        # scrollbar so the row is never clipped vertically.
        _row_height = max(34, self.controls_row_widget.sizeHint().height())
        self.controls_scroll.setFixedHeight(_row_height + 16)
        self.controls_container_layout.addWidget(self.controls_scroll)

        # Add controls container to main layout
        self.layout.addWidget(self.controls_container)
        
        # CRITICAL FIX: Force layout update
        self.layout.activate()

    def add_widgets_to_controls_row(self, widgets, leading_spacing=10):
        """
        Add external widgets to the playback controls row.

        Args:
            widgets (list[QWidget]): Widgets to append to the row
            leading_spacing (int): Spacing before the inserted widget group
        """
        widgets = [widget for widget in widgets if widget is not None]
        if not widgets:
            return

        self.controls_layout.addSpacing(leading_spacing)
        for widget in widgets:
            self.controls_layout.addWidget(widget)

    # NOTE (1.3.1): ``ensure_native_video_surface`` was removed along with
    # the VLC backend. There is no longer a native child window to
    # promote — the decoded frame is painted by ``video_display_label``,
    # which is just a regular non-native QLabel.

    def _apply_placeholder_background_style(self, drag_active=False):
        """Style the idle placeholder surface independently of the VLC frame."""
        if drag_active:
            self.placeholder_background.setStyleSheet(
                "background-color: #2a3f5f; border: 2px dashed #ffffff;"
            )
        else:
            self.placeholder_background.setStyleSheet(
                "background-color: #000000; border: none;"
            )

    def _update_drop_icon_pixmap(self):
        """Render the drop-zone icon crisply on High-DPI screens.

        The source PNG is high resolution; we scale it to the *physical*
        pixel height (logical height x devicePixelRatio) and tag the
        pixmap with that ratio so Qt doesn't stretch a low-res bitmap
        across the screen's physical pixels (which looks blurry at 150%
        / 200% display scaling)."""
        source = getattr(self, "_drop_icon_source", None)
        if source is None or source.isNull():
            return
        screen = self.screen() or QGuiApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen is not None else 1.0
        target_h = max(1, round(self._drop_icon_height * dpr))
        scaled = source.scaledToHeight(
            target_h, Qt.TransformationMode.SmoothTransformation
        )
        scaled.setDevicePixelRatio(dpr)
        self.drop_icon.setPixmap(scaled)
        self.drop_icon.adjustSize()

    def _has_drop_icon(self):
        pixmap = self.drop_icon.pixmap() if hasattr(self, "drop_icon") else None
        return pixmap is not None and not pixmap.isNull()

    def _sync_video_placeholder_geometry(self):
        """Keep the idle placeholder surface aligned to the full video frame
        and center the drop hint (icon stacked above text) inside it."""
        self.placeholder_background.setGeometry(self.video_frame.rect())

        frame_rect = self.video_frame.rect()
        self.drop_label.adjustSize()
        label_size = self.drop_label.size()

        if self._has_drop_icon():
            # Stack icon above text as a vertically-centred group.
            self.drop_icon.adjustSize()
            icon_size = self.drop_icon.size()
            gap = 8
            total_h = icon_size.height() + gap + label_size.height()
            top = max(0, (frame_rect.height() - total_h) // 2)
            icon_x = max(0, (frame_rect.width() - icon_size.width()) // 2)
            self.drop_icon.move(icon_x, top)
            label_y = top + icon_size.height() + gap
            self.drop_icon.raise_()
        else:
            label_y = max(0, (frame_rect.height() - label_size.height()) // 2)

        label_x = max(0, (frame_rect.width() - label_size.width()) // 2)
        self.drop_label.move(label_x, label_y)
        self.drop_label.raise_()

    def _update_empty_state_visibility(self):
        """Show the drop placeholder only when no video is currently loaded."""
        show_placeholder = not self._has_video
        self.placeholder_background.setVisible(show_placeholder)
        self.drop_label.setVisible(show_placeholder)
        if hasattr(self, "drop_icon"):
            self.drop_icon.setVisible(show_placeholder and self._has_drop_icon())
        if show_placeholder:
            self._sync_video_placeholder_geometry()

    def refresh_empty_placeholder(self):
        """Repaint the idle black drop area after page/view switches."""
        if self._has_video:
            return

        self._apply_placeholder_background_style(drag_active=False)
        self._update_empty_state_visibility()
        self.placeholder_background.update()
        self.placeholder_background.repaint()
        self.update()
    
    def _reset_step_flag(self):
        """Reset the step in progress flag after a delay."""
        self._step_in_progress = False
        self.logger.debug("Step button cooldown complete")
    
    def _reset_forward_button(self):
        """Reset the forward button styling after visual feedback."""
        self.step_forward_button.setStyleSheet(self._original_button_style)
    
    def _reset_backward_button(self):
        """Reset the backward button styling after visual feedback."""
        self.step_backward_button.setStyleSheet(self._original_button_style)
    
    def connect_signals(self):
        """Connect widget signals to slots."""
        self.play_pause_button.clicked.connect(self.toggle_play)
        self.step_forward_button.clicked.connect(self.on_step_forward)
        self.step_backward_button.clicked.connect(self.on_step_backward)
        
        self.position_slider.sliderMoved.connect(self.on_position_moved)
        self.position_slider.sliderReleased.connect(self.on_position_released)
        
        self.rate_slider.valueChanged.connect(self.on_rate_slider_changed)
        # NOTE (1.3.1): the ``volume_slider`` widget has been removed
        # along with audio playback (see setup_ui). The ``volume_changed``
        # Signal declaration is kept so external connect()s don't blow up
        # but nothing emits it anymore.

        # Connect frame-by-frame checkbox
        self.frame_by_frame_checkbox.stateChanged.connect(self.on_frame_by_frame_changed)
        # Note: Reset button signal is connected in setup_ui
    
    def on_frame_by_frame_changed(self, state):
        """
        Handle frame-by-frame mode checkbox state change.
        
        Args:
            state: Qt.CheckState value
        """
        self._frame_by_frame_mode = (state == Qt.CheckState.Checked.value)
        self.logger.debug(f"Frame-by-frame mode {'enabled' if self._frame_by_frame_mode else 'disabled'}")
        
        # Emit signal for controllers to handle
        self.frame_by_frame_mode_changed.emit(self._frame_by_frame_mode)
    
    def is_frame_by_frame_mode(self):
        """
        Check if frame-by-frame mode is enabled.
        
        Returns:
            bool: True if frame-by-frame mode is enabled, False otherwise
        """
        return self._frame_by_frame_mode
    
    def show_loading_overlay(self, show=True):
        """
        Show or hide the loading overlay.
        
        Args:
            show (bool): Whether to show or hide the overlay
        """
        if show:
            self._loading_overlay.show_loading()
            # Disable all controls
            self._disable_controls()
        else:
            # Small delay before hiding to allow final UI updates
            QTimer.singleShot(100, self._loading_overlay.hide_loading)
            # Re-enable controls after a short delay to ensure overlay is fully gone
            QTimer.singleShot(200, self._enable_controls)
    
    def set_loading_progress(self, progress):
        """
        Set the loading progress.
        
        Args:
            progress (int): Progress percentage (0-100)
        """
        self._loading_overlay.set_progress(progress)
    
    def _disable_controls(self):
        """Disable all controls during loading."""
        if self._controls_disabled:
            return
            
        self._controls_disabled = True
        self.play_pause_button.setEnabled(False)
        self.step_forward_button.setEnabled(False)
        self.step_backward_button.setEnabled(False)
        self.position_slider.setEnabled(False)
        self.rate_slider.setEnabled(False)
        self.step_size_spin.setEnabled(False)
        self.frame_by_frame_checkbox.setEnabled(False)
    
    def _enable_controls(self):
        """Re-enable all controls after loading."""
        if not self._controls_disabled:
            return
            
        self._controls_disabled = False
        self.play_pause_button.setEnabled(True)
        self.step_forward_button.setEnabled(True)
        self.step_backward_button.setEnabled(True)
        self.position_slider.setEnabled(True)
        self.rate_slider.setEnabled(True)
        self.step_size_spin.setEnabled(True)
        self.frame_by_frame_checkbox.setEnabled(True)
    
    # Drag and Drop event handlers
    def dragEnterEvent(self, event: QDragEnterEvent):
        """
        Handle drag enter events.
        
        Args:
            event (QDragEnterEvent): The drag enter event
        """
        # Skip if loading overlay is visible
        if hasattr(self, '_loading_overlay') and self._loading_overlay.isVisible():
            event.ignore()
            return
            
        # Check if the drag has URLs and they are video files
        if event.mimeData().hasUrls():
            # Check first URL only
            url = event.mimeData().urls()[0]
            file_path = url.toLocalFile()

            # Accept via extension whitelist -> magic-number sniff -> PyAV
            # trial-open. This lets RABET also accept files whose extension
            # is unusual but whose bytes are a standard container.
            if is_video_file(file_path):
                self.logger.debug(f"Accepting drag enter for video: {file_path}")
                event.acceptProposedAction()
                
                # Highlight drop area
                self._apply_placeholder_background_style(drag_active=True)
                self.drop_label.setStyleSheet("""
                    color: white; 
                    font-size: 18px; 
                    font-weight: bold;
                    background-color: rgba(42, 63, 95, 0.7);
                    padding: 10px;
                    border-radius: 5px;
                """)
                return
        
        # If we get here, the drag is not acceptable
        event.ignore()
    
    def dragLeaveEvent(self, event):
        """Handle drag leave events."""
        # Reset styling when drag leaves
        self._apply_placeholder_background_style(drag_active=False)
        self.drop_label.setStyleSheet("""
            color: white; 
            font-size: 18px; 
            font-weight: bold;
            background-color: rgba(0, 0, 0, 0.5);
            padding: 10px;
            border-radius: 5px;
        """)
    
    def dropEvent(self, event: QDropEvent):
        """
        Handle drop events.
        
        Args:
            event (QDropEvent): The drop event
        """
        # Skip if loading overlay is visible
        if hasattr(self, '_loading_overlay') and self._loading_overlay.isVisible():
            event.ignore()
            return
            
        # Reset styling
        self._apply_placeholder_background_style(drag_active=False)
        self.drop_label.setStyleSheet("""
            color: white; 
            font-size: 18px; 
            font-weight: bold;
            background-color: rgba(0, 0, 0, 0.5);
            padding: 10px;
            border-radius: 5px;
        """)
        
        # Process the dropped file
        if event.mimeData().hasUrls():
            # Get the first URL only (we'll only load one video at a time)
            url = event.mimeData().urls()[0]
            file_path = url.toLocalFile()
            
            self.logger.info(f"Video file dropped: {file_path}")
            
            # Emit signal with file path
            self.video_dropped.emit(file_path)
            
            # Accept the drop
            event.acceptProposedAction()
            
            # Show loading overlay
            self.show_loading_overlay(True)
    
    def toggle_play(self):
        """Toggle between play and pause states."""
        # Skip if controls are disabled
        if self._controls_disabled:
            return
            
        if self._is_playing:
            self.pause_clicked.emit()
        else:
            self.play_clicked.emit()
    
    def get_video_frame(self):
        """
        Return the video frame container.

        Historically this was the QFrame whose native window handle was
        passed to libVLC via ``set_hwnd``/``set_xwindow``/``set_nsobject``.
        Under the PyAV backend nothing external needs the surface — the
        view paints frames itself into ``video_display_label`` — but the
        method is kept so any leftover caller (e.g. tests or a stale
        worktree) still works.
        """
        return self.video_frame
    
    def on_position_moved(self, position):
        """
        Handle position slider moved.
        
        Args:
            position (int): Slider position
        """
        # Skip if controls are disabled
        if self._controls_disabled:
            return
            
        # Update the time label
        self.update_time_label(position)
        
        # Apply throttling to seek requests to avoid overwhelming the player
        current_time = QDateTime.currentMSecsSinceEpoch()
        if current_time - self._last_seek_time >= self._slider_throttle_ms:
            # Convert to milliseconds based on slider range and emit seek request
            position_ms = int(position / 1000.0 * max(1, self._duration))
            self.seek_requested.emit(position_ms)
            self._last_seek_time = current_time
    
    def on_position_released(self):
        """Handle position slider released."""
        # Skip if controls are disabled
        if self._controls_disabled:
            return
            
        position = self.position_slider.value()
        # Convert to milliseconds based on slider range
        position_ms = int(position / 1000.0 * max(1, self._duration))
        self.seek_requested.emit(position_ms)
    
    def on_step_forward(self):
        """Handle step forward button clicked."""
        # Skip if controls are disabled
        if self._controls_disabled:
            return
            
        # Guard against rapid clicking
        if self._step_in_progress:
            self.logger.debug("Step forward ignored - previous step still in progress")
            return
            
        self._step_in_progress = True
        
        # Visual feedback - highlight the button
        self.step_forward_button.setStyleSheet("background-color: #2ecc71; color: white;")
        self._forward_button_timer.start(300)  # Reset after 300ms
        
        # Check if frame-by-frame mode is enabled
        if self._frame_by_frame_mode:
            # In frame-by-frame mode, use a single frame duration
            # We'll use an approximation based on common frame rates
            frame_duration = 33  # ~30fps (33ms per frame)
            
            # If video model has provided a frame duration, use that
            if hasattr(self, '_frame_duration_ms') and self._frame_duration_ms > 0:
                frame_duration = self._frame_duration_ms
                
            self.logger.debug(f"Step forward in frame-by-frame mode (using {frame_duration}ms)")
            
            # Emit signal with the frame duration
            self.step_forward_clicked.emit(frame_duration)
        else:
            # Get exact step size from spinner
            step_size = self.step_size_spin.value()
            
            # Log with exact step size
            self.logger.debug(f"Step forward button clicked with exact step size: {step_size}ms")
            
            # Emit signal with the exact step size
            self.step_forward_clicked.emit(step_size)
        
        # Start cooldown timer to prevent rapid clicking issues
        self._step_timer.start(self._step_cooldown_ms)
    
    def on_step_backward(self):
        """Handle step backward button clicked."""
        # Skip if controls are disabled
        if self._controls_disabled:
            return

        # Guard against rapid clicking
        if self._step_in_progress:
            self.logger.debug("Step backward ignored - previous step still in progress")
            return

        self._step_in_progress = True

        # Visual feedback - highlight the button
        self.step_backward_button.setStyleSheet("background-color: #3498db; color: white;")
        self._backward_button_timer.start(300)  # Reset after 300ms

        # Mirror on_step_forward's FBF handling so the UI's "<" button
        # behaves symmetrically with ">" — i.e. one click = one frame
        # while frame-by-frame mode is on, regardless of the spinbox value.
        # This is what makes FBF annotation usable: the user is supposed
        # to be able to nudge by exactly one frame in either direction.
        if self._frame_by_frame_mode:
            frame_duration = 33  # ~30fps fallback
            if hasattr(self, '_frame_duration_ms') and self._frame_duration_ms > 0:
                frame_duration = self._frame_duration_ms

            self.logger.debug(
                f"Step backward in frame-by-frame mode (using {frame_duration}ms)"
            )
            self.step_backward_clicked.emit(frame_duration)
        else:
            # Get exact step size from spinner
            step_size = self.step_size_spin.value()
            self.logger.debug(
                f"Step backward button clicked with exact step size: {step_size}ms"
            )
            self.step_backward_clicked.emit(step_size)

        # Start cooldown timer to prevent rapid clicking issues
        self._step_timer.start(self._step_cooldown_ms)
    
    def on_rate_slider_changed(self, value):
        """
        Handle playback rate slider changed.
        
        Args:
            value (int): Slider value (25-200)
        """
        # Skip if controls are disabled
        if self._controls_disabled:
            return
            
        # Convert slider value to playback rate (0.25-2.00)
        rate = value / 100.0
        
        # Update label
        self.rate_value_label.setText(f"{rate:.2f}x")
        
        # Emit signal
        self.rate_changed.emit(rate)
    
    @Slot(int)
    def set_position(self, position_ms):
        """
        Set position slider and time label.
        
        Args:
            position_ms (int): Position in milliseconds
        """
        # Only update if we have a valid duration
        if self._duration > 0:
            # Normalize position to slider range (0-1000)
            position_normalized = int((position_ms / max(1, self._duration)) * 1000.0)
            position_normalized = max(0, min(1000, position_normalized))
            
            # Avoid recursive updates by blocking signals
            self.position_slider.blockSignals(True)
            self.position_slider.setValue(position_normalized)
            self.position_slider.blockSignals(False)
            
            self.update_time_label(position_normalized)
    
    @Slot(int)
    def set_duration(self, duration_ms):
        """
        Set video duration.
        
        Args:
            duration_ms (int): Duration in milliseconds
        """
        # Ensure duration is positive
        self._duration = max(1, duration_ms)
        self._has_video = duration_ms > 1
        self._update_empty_state_visibility()
        
        # Format duration label
        self.format_time_label(self.duration_label, self._duration)
        
        self.logger.debug(f"Set duration: {self._duration}ms")
    
    def update_time_label(self, position_normalized):
        """
        Update current time label.
        
        Args:
            position_normalized (int): Normalized position (0-1000)
        """
        if self._duration > 0:
            # Calculate time in milliseconds
            current_time_ms = int((position_normalized / 1000.0) * self._duration)
            self.format_time_label(self.current_time_label, current_time_ms)
    
    def format_time_label(self, label, time_ms):
        """
        Format a time label with hours, minutes, seconds.
        
        Args:
            label (QLabel): Label to update
            time_ms (int): Time in milliseconds
        """
        # Ensure time is positive
        time_ms = max(0, time_ms)
        
        # Calculate hours, minutes, seconds
        total_seconds = time_ms / 1000
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        
        # Format and set the label
        label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
    
    @Slot(bool)
    def set_playing_state(self, is_playing):
        """
        Update UI based on playback state.
        
        Args:
            is_playing (bool): True if playing, False if paused
        """
        self._is_playing = is_playing
        
        # Update play/pause button text
        self.play_pause_button.setText("Pause" if is_playing else "Play")
        
        self._update_empty_state_visibility()
        
        # CRITICAL FIX: Force layout update after state change
        # This ensures that all widgets maintain their proper positions
        self.layout.activate()
        self.controls_container.update()
        
        # Force the parent widget to update its geometry
        parent = self.parent()
        if parent:
            parent.updateGeometry()
        
    def reset_playback_rate(self):
        """Reset playback rate to 1x."""
        # Skip if controls are disabled
        if self._controls_disabled:
            return
            
        # Set slider to 100 (1.00x)
        self.rate_slider.setValue(100)
        
        # Update label
        self.rate_value_label.setText("1.00x")
        
        # Emit signal with 1.0 playback rate
        self.rate_changed.emit(1.0)
        
        self.logger.debug("Playback rate reset to 1.00x")

    # ------------------------------------------------------------------ #
    # PyAV frame display (1.3.1)
    # ------------------------------------------------------------------ #

    @Slot(QImage)
    def display_frame(self, qimg: QImage) -> None:
        """Receive a decoded frame from the model and show it.

        Connected to ``VideoModel.frame_ready`` by ``VideoController``.
        Caches the QImage so resize / re-show can re-scale without a
        round-trip back to the decoder.
        """
        if qimg is None or qimg.isNull():
            return
        self._last_qimage = qimg
        # Once we have a real frame the "Drop Video File Here" hint must
        # disappear, otherwise it sits on top of the video. We hide it
        # here (rather than in load_video) because the model is the one
        # that confirms a frame actually decoded.
        # Hide the drop hint unconditionally (hide() is a no-op if it's
        # already hidden). Guarding on isVisible() was unreliable when a
        # frame decodes before the view is shown — isVisible() is False
        # then, so the hint never got hidden and could flash over the
        # first frame.
        self.drop_label.hide()
        if hasattr(self, "drop_icon"):
            self.drop_icon.hide()
        self.placeholder_background.hide()
        self._render_frame()

    def _render_frame(self) -> None:
        """Re-scale the cached frame to the current label size and paint."""
        if self._last_qimage is None or self._last_qimage.isNull():
            return
        target_size = self.video_display_label.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            return
        # SmoothTransformation gives much nicer downscaling for 1080p
        # videos shown in smaller panes; on modern CPUs it's still a
        # 2-4 ms operation per frame so the playback timer can keep up.
        scaled = self._last_qimage.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.video_display_label.setPixmap(QPixmap.fromImage(scaled))

    def resizeEvent(self, event):
        """Handle resize events to ensure overlay is properly sized."""
        super().resizeEvent(event)

        # CRITICAL FIX: Ensure minimum size is maintained
        if self.height() < 300:
            self.setMinimumHeight(300)

        # Update loading overlay if visible
        if hasattr(self, '_loading_overlay') and self._loading_overlay.isVisible():
            self._loading_overlay.resize(self.size())

        self._sync_video_placeholder_geometry()

        # Re-paint the cached frame at the new size so the image scales
        # to fit the resized label. Without this the pixmap stays at its
        # old dimensions and either leaves blank bars or gets clipped.
        if getattr(self, "_last_qimage", None) is not None:
            self._render_frame()

        # Force layout update
        self.layout.activate()

        # Log resize event for debugging
        self.logger.debug(f"VideoPlayerView resized to: {self.size()}")
    
    def showEvent(self, event):
        """Handle show event to ensure layout stability."""
        super().showEvent(event)
        
        # Force layout update when widget becomes visible
        self.layout.activate()
        self.updateGeometry()
        
        # Ensure controls container is visible
        if hasattr(self, 'controls_container'):
            self.controls_container.show()
            self.controls_container.updateGeometry()

        # Re-render the drop icon now that the widget is on its final
        # screen, so the devicePixelRatio matches (crisp on High-DPI).
        self._update_drop_icon_pixmap()
        self._sync_video_placeholder_geometry()
        QTimer.singleShot(0, self.refresh_empty_placeholder)
