# models/video_model.py - Modified for threaded loading
import logging
import os
import time
import vlc
from PySide6.QtCore import QObject, Signal, Slot, QTimer

class VideoModel(QObject):
    """
    Model for managing video playback using python-vlc.
    
    Signals:
        playback_state_changed: Emitted when playback state changes (play/pause)
        position_changed: Emitted when playback position changes
        video_loaded: Emitted when a new video is loaded
        error_occurred: Emitted when an error occurs
    """
    
    playback_state_changed = Signal(bool)  # True for playing, False for paused
    position_changed = Signal(int)  # Current position in milliseconds
    duration_changed = Signal(int)  # Video duration in milliseconds
    video_loaded = Signal(str)  # Path to loaded video
    error_occurred = Signal(str)  # Error message
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing VideoModel")
        
        # Initialize VLC instance with minimal options
        try:
            # Force specific video output modules that work better for embedding
            # Different options work on different systems, so providing multiple
            vlc_options = [
                '--no-xlib',                  # No X11 dependency
                '--no-video-title-show',      # Don't show the video title
                '--no-osd',                   # No on-screen display
                '--no-snapshot-preview',      # Don't show snapshot previews
                '--no-stats',                 # Don't show stats
                '--no-sub-autodetect-file',   # Don't auto-detect subtitle files
                '--no-audio',                 # Disable audio temporarily
                '--vout=vdummy',              # First try dummy output to prevent sep window
                '--avcodec-hw=none',          # Disable hardware acceleration
                '--quiet',                    # Reduce VLC's own logging
            ]
            
            self.instance = vlc.Instance(' '.join(vlc_options))
            self.media_player = self.instance.media_player_new()
            
            # Set the media player to embed video
            self.media_player.set_fullscreen(False)
        except Exception as e:
            self.logger.error(f"Failed to initialize VLC: {str(e)}", exc_info=True)
            self.instance = None
            self.media_player = None
            self.error_occurred.emit(f"Failed to initialize video player: {str(e)}")
        
        # Video properties
        self._video_path = None
        self._duration = 0  # in milliseconds
        self._is_playing = False
        self._media = None
        self._window_handle_set = False
        
        # Tracking prev position for step operations
        self._last_seek_position = 0
        
        # Flag to prevent concurrent operations
        self._operation_in_progress = False
        
        # Frame rate info for better stepping
        self._frame_rate = 0
        self._frame_duration_ms = 40  # Default to 25fps (40ms per frame)
        
        # Setup position update timer
        self.position_timer = QTimer()
        self.position_timer.setInterval(100)  # Update every 100ms
        self.position_timer.timeout.connect(self._update_position)
        
        # Duration update timer
        self.duration_timer = QTimer()
        self.duration_timer.setInterval(500)  # Check every 500ms
        self.duration_timer.timeout.connect(self._update_duration)
        
        # Frame refresh timer to ensure refresh completes
        self._refresh_timer = QTimer()
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._delayed_refresh_frame)
        
        # Operation timer for coordinating VLC operations
        self._operation_timer = QTimer()
        self._operation_timer.setSingleShot(True)
        self._operation_timer.timeout.connect(self._release_operation_lock)
    
    def _release_operation_lock(self):
        """Release the operation lock after a delay."""
        self._operation_in_progress = False
        self.logger.debug("Operation lock released")
    
    def set_window_handle(self, handle):
        """
        Set the window handle for embedding the video.
        
        Args:
            handle: Window handle (varies by platform)
        
        Returns:
            bool: True if successful, False otherwise
        """
        if self.media_player is None:
            self.logger.error("Cannot set window handle: media player not initialized")
            return False
            
        try:
            self.logger.debug(f"Setting window handle: {handle}")
            
            # Give VLC some time to initialize
            time.sleep(0.1)
            
            # Different methods based on platform (handle already handled by controller)
            self.media_player.set_hwnd(handle)
            
            # Re-play media if it was already loaded to apply changes
            if self._media is not None:
                # Make sure audio is enabled
                self.media_player.audio_set_mute(False)
                self.media_player.audio_set_volume(80)
                
                # This ensures the video actually shows in the embedded window
                was_playing = self._is_playing
                self.media_player.stop()
                time.sleep(0.1)
                self.media_player.play()
                time.sleep(0.1)
                if not was_playing:
                    self.media_player.pause()
            
            self._window_handle_set = True
            return True
        except Exception as e:
            self.logger.error(f"Error setting window handle: {str(e)}", exc_info=True)
            self.error_occurred.emit(f"Failed to set video window: {str(e)}")
            return False
    
    def load_video(self, video_path):
        """
        Public method to load a video file.
        This is now just a wrapper around the internal method that can be called from a worker thread.
        
        Args:
            video_path (str): Path to the video file
            
        Returns:
            bool: True if video was loaded successfully, False otherwise
        """
        # This method should be called by the loader thread, not directly
        self.logger.info(f"Delegating video loading to threaded loader: {video_path}")
        return self._load_video_internal(video_path)
    
    def _load_video_internal(self, video_path):
        """
        Internal method to load a video file. Can be called from a worker thread.
        
        Args:
            video_path (str): Path to the video file
            
        Returns:
            bool: True if video was loaded successfully, False otherwise
        """
        if not os.path.exists(video_path):
            error_msg = f"Video file not found: {video_path}"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False
        
        if self.media_player is None:
            error_msg = "Video player not initialized properly"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return False
        
        try:
            self.logger.info(f"Loading video: {video_path}")
            
            # Stop any current playback
            if self._is_playing:
                self.stop()
            
            # Load media from file
            self._media = self.instance.media_new(video_path)
            
            # Force software decoding
            self._media.add_option(':avcodec-hw=none')
            
            # Set the media
            self.media_player.set_media(self._media)
            
            # Parse media in a separate thread
            self._media.parse_with_options(vlc.MediaParseFlag.network, 5000)
            
            # Start the media to initialize it, then pause
            time.sleep(0.2)  # Give VLC time to initialize
            self.media_player.play()
            time.sleep(0.5)  # Give VLC time to start playing
            self.media_player.pause()
            
            # Try to get duration
            self._duration = max(0, self.media_player.get_length())
            
            if self._duration <= 0:
                self.logger.debug("Duration not immediately available, will check periodically")
                self.duration_timer.start()
            else:
                self.duration_changed.emit(self._duration)
            
            # Get frame rate info for better stepping
            self._frame_rate = self.get_frame_rate()
            if self._frame_rate > 0:
                self._frame_duration_ms = int(1000 / self._frame_rate)
                self.logger.debug(f"Video frame rate: {self._frame_rate} fps (frame duration: {self._frame_duration_ms} ms)")
            else:
                self._frame_duration_ms = 40  # Default to 25fps (40ms per frame)
                self.logger.debug(f"Could not determine frame rate, using default frame duration: {self._frame_duration_ms} ms")
            
            self._video_path = video_path
            self._last_seek_position = 0
            
            # This is called from a worker thread, so we need to use invokeMethod or similar
            # to emit the signal safely. For simplicity in this example, we're emitting directly.
            self.video_loaded.emit(video_path)
            
            # Re-enable audio now that the video is loaded
            self.media_player.audio_set_mute(False)
            self.media_player.audio_set_volume(80)
            
            return True
        except Exception as e:
            error_msg = f"Failed to load video: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            return False
    
    def play(self):
        """Start or resume video playback."""
        if self.media_player is None:
            return
            
        self.logger.debug("Play command received")
        
        # Make sure window handle is set
        if not self._window_handle_set:
            self.logger.warning("Window handle not set, video may play in separate window")
        
        self.media_player.play()
        self._is_playing = True
        self.playback_state_changed.emit(True)
        self.position_timer.start()
    
    def pause(self):
        """Pause video playback."""
        if self.media_player is None:
            return
            
        self.logger.debug("Pause command received")
        self.media_player.pause()
        self._is_playing = False
        self.playback_state_changed.emit(False)
        self.position_timer.stop()
    
    def toggle_play(self):
        """Toggle between play and pause."""
        if self._is_playing:
            self.pause()
        else:
            self.play()
    
    def stop(self):
        """Stop video playback."""
        if self.media_player is None:
            return
            
        self.logger.debug("Stop command received")
        self.media_player.stop()
        self._is_playing = False
        self.playback_state_changed.emit(False)
        self.position_timer.stop()
    
    def seek(self, position_ms):
        """
        Seek to a specific position.
        
        Args:
            position_ms (int): Position in milliseconds
        """
        if self.media_player is None or self._duration <= 0 or self._operation_in_progress:
            return
        
        # Set the operation lock
        self._operation_in_progress = True
        
        try:
            position_ms = max(0, min(position_ms, self._duration))
            position_float = position_ms / max(1, self._duration)
            
            self.logger.debug(f"Seeking to position: {position_ms}ms ({position_float:.4f})")
            
            # Store the position for detecting movement direction
            self._last_seek_position = position_ms
            
            # Set the position in the media player
            self.media_player.set_position(position_float)
            self._update_position()
            
            # If paused, update the frame display after seeking
            if not self._is_playing:
                # Using a short delay helps ensure the seek completes first
                QTimer.singleShot(30, self.refresh_frame)
            
            # Release the operation lock after a delay
            self._operation_timer.start(100)
        except Exception as e:
            self.logger.error(f"Error in seek: {str(e)}")
            self._operation_in_progress = False
    
    def seek_with_retry(self, position_ms, retries=3):
        """
        Seek with multiple attempts to ensure precision.
        
        Args:
            position_ms (int): Position in milliseconds
            retries (int): Number of retries if position is not accurate
        """
        if self.media_player is None or self._duration <= 0:
            return
        
        initial_pos = self.get_position()
        self.logger.debug(f"Seek with retry from {initial_pos}ms to {position_ms}ms")
        
        # First attempt
        self.seek(position_ms)
        
        # Check result and retry if needed in a separate timer
        QTimer.singleShot(100, lambda: self._check_seek_result(position_ms, initial_pos, retries))
    
    def _check_seek_result(self, target_pos, initial_pos, retries_left):
        """
        Check if a seek operation was successful and retry if needed.
        
        Args:
            target_pos (int): Target position in milliseconds
            initial_pos (int): Initial position before seek
            retries_left (int): Number of retries remaining
        """
        if retries_left <= 0:
            self.logger.warning(f"Seek operation failed to reach target position after retries")
            return
        
        # Get current position
        current_pos = self.get_position()
        
        # Check if we're close enough to the target
        tolerance = max(10, self._frame_duration_ms // 2)  # Half frame tolerance
        if abs(current_pos - target_pos) <= tolerance:
            self.logger.debug(f"Seek successful: {initial_pos}ms → {current_pos}ms")
            return
        
        # If not close enough, retry
        self.logger.debug(f"Seek retry {retries_left}: current={current_pos}ms, target={target_pos}ms")
        
        # Try again with direct position setting
        self.media_player.set_position(target_pos / max(1, self._duration))
        
        # Check again after a delay
        QTimer.singleShot(100, lambda: self._check_seek_result(target_pos, initial_pos, retries_left - 1))
    
    def refresh_frame(self):
        """
        Force refresh of the current frame.
        This is especially useful when seeking while paused.
        """
        if self.media_player is None or self._is_playing or self._operation_in_progress:
            return
        
        self._operation_in_progress = True
        self.logger.debug("Starting frame refresh")
        
        try:
            # Get position before refresh
            pos_before = self.get_position()
            
            # Use next_frame to update the display
            self.media_player.next_frame()
            
            # Schedule second refresh with slight delay
            self._refresh_timer.start(50)
            
            # Log position for debugging
            QTimer.singleShot(80, lambda: self._check_position_after_refresh(pos_before))
        except Exception as e:
            self.logger.error(f"Error in frame refresh: {str(e)}")
            self._operation_in_progress = False
    
    def _delayed_refresh_frame(self):
        """Perform a secondary frame refresh after a short delay."""
        if self.media_player is None or self._is_playing:
            self._operation_in_progress = False
            return
            
        try:
            # Check if position changed significantly during refresh
            current_pos = self.get_position()
            
            # If refresh moved us forward too much, try to correct
            if self._last_seek_position > 0 and (current_pos - self._last_seek_position) > self._frame_duration_ms:
                self.logger.debug(f"Refresh moved position too far forward, correcting back to {self._last_seek_position}ms")
                self.media_player.set_position(self._last_seek_position / max(1, self._duration))
            
            # Make sure UI is updated
            QTimer.singleShot(30, self._update_position)
        except Exception as e:
            self.logger.error(f"Error in delayed frame refresh: {str(e)}")
        finally:
            self._operation_in_progress = False
    
    def _check_position_after_refresh(self, pos_before):
        """
        Check if position changed significantly after refresh and log it.
        
        Args:
            pos_before (int): Position before refresh in milliseconds
        """
        if self.media_player is None:
            return
            
        try:
            pos_after = self.get_position()
            if abs(pos_after - pos_before) > self._frame_duration_ms * 0.5:
                self.logger.debug(f"Frame refresh affected position: {pos_before}ms → {pos_after}ms (delta: {pos_after - pos_before}ms)")
        except Exception as e:
            self.logger.error(f"Error checking position after refresh: {str(e)}")
    
    def step_forward(self, time_ms=100):
        """
        Step forward by a specific time.
        
        Args:
            time_ms (int): Time to step forward in milliseconds
        
        Returns:
            bool: True if successful, False otherwise
        """
        if self.media_player is None or self._operation_in_progress:
            return False
        
        # Set operation lock
        self._operation_in_progress = True
        
        try:
            # Ensure step size is reasonable (use a minimum of one frame duration)
            min_step = max(10, self._frame_duration_ms)
            time_ms = max(min_step, min(time_ms, 5000))
            
            # Log current position
            current_pos = self.get_position()
            
            # Calculate target position more precisely (align to frame boundaries if possible)
            frames_to_move = max(1, round(time_ms / max(1, self._frame_duration_ms)))
            frame_aligned_step = frames_to_move * self._frame_duration_ms
            
            # Calculate a more precise target position
            target_pos = min(current_pos + frame_aligned_step, self._duration)
            
            self.logger.debug(f"Stepping forward from {current_pos}ms to {target_pos}ms "
                             f"({frames_to_move} frames, {frame_aligned_step}ms)")
            
            # Store position explicitly
            self._last_seek_position = target_pos
            
            # Use precision seeking
            self.seek_with_retry(target_pos)
            
            # Release lock after a delay
            self._operation_timer.start(200)
            
            return True
        except Exception as e:
            self.logger.error(f"Error in step_forward: {str(e)}")
            self._operation_in_progress = False
            return False
    
    def step_backward(self, time_ms=100):
        """
        Step backward by a specific time.
        
        Args:
            time_ms (int): Time to step backward in milliseconds
            
        Returns:
            bool: True if successful, False otherwise
        """
        if self.media_player is None or self._operation_in_progress:
            return False
        
        # Set operation lock
        self._operation_in_progress = True
        
        try:
            # Ensure step size is reasonable (use a minimum of one frame duration)
            min_step = max(10, self._frame_duration_ms)
            time_ms = max(min_step, min(time_ms, 5000))
            
            # Log current position
            current_pos = self.get_position()
            
            # Calculate target position more precisely (align to frame boundaries if possible)
            frames_to_move = max(1, round(time_ms / max(1, self._frame_duration_ms)))
            frame_aligned_step = frames_to_move * self._frame_duration_ms
            
            # Calculate a more precise target position
            target_pos = max(0, current_pos - frame_aligned_step)
            
            self.logger.debug(f"Stepping backward from {current_pos}ms to {target_pos}ms "
                             f"({frames_to_move} frames, {frame_aligned_step}ms)")
            
            # Store position explicitly
            self._last_seek_position = target_pos
            
            # Use precision seeking
            self.seek_with_retry(target_pos)
            
            # Release lock after a delay
            self._operation_timer.start(200)
            
            return True
        except Exception as e:
            self.logger.error(f"Error in step_backward: {str(e)}")
            self._operation_in_progress = False
            return False
    
    def set_playback_rate(self, rate):
        """
        Set playback rate.
        
        Args:
            rate (float): Playback rate (1.0 is normal speed)
        """
        if self.media_player is None:
            return
            
        self.logger.debug(f"Setting playback rate to {rate}")
        self.media_player.set_rate(rate)
    
    def get_position(self):
        """
        Get current playback position in milliseconds.
        
        Returns:
            int: Current position in milliseconds
        """
        if self.media_player is None or self._duration <= 0:
            return 0
        
        position_float = self.media_player.get_position()
        position_float = max(0.0, min(1.0, position_float))
        return int(position_float * self._duration)
    
    def get_duration(self):
        """
        Get video duration in milliseconds.
        
        Returns:
            int: Video duration in milliseconds
        """
        return max(0, self._duration)
    
    def is_playing(self):
        """
        Check if video is currently playing.
        
        Returns:
            bool: True if playing, False otherwise
        """
        return self._is_playing
    
    def set_volume(self, volume):
        """
        Set audio volume.
        
        Args:
            volume (int): Volume level (0-100)
        """
        if self.media_player is None:
            return
            
        self.logger.debug(f"Setting volume to {volume}")
        self.media_player.audio_set_volume(volume)
    
    def get_frame_rate(self):
        """
        Get video frame rate.
        
        Returns:
            float: Frame rate or 0 if not available
        """
        if self.media_player is None or not self.media_player.get_media():
            return 0
        
        try:
            return self.media_player.get_fps()
        except Exception as e:
            self.logger.warning(f"Failed to get frame rate: {str(e)}")
            return 0
    
    @Slot()
    def _update_position(self):
        """Update current position and emit signal."""
        position = self.get_position()
        self.position_changed.emit(position)
    
    @Slot()
    def _update_duration(self):
        """Periodically check if duration is available and update if needed."""
        if self.media_player is None:
            self.duration_timer.stop()
            return
            
        current_duration = self.media_player.get_length()
        
        if current_duration > 0:
            self._duration = current_duration
            self.logger.debug(f"Updated video duration: {self._duration}ms")
            self.duration_changed.emit(self._duration)
            self.duration_timer.stop()
        elif self.duration_timer.interval() * self.duration_timer.timerId() > 10000:
            # Fallback after 10 seconds
            self._duration = 60000  # Default to 1 minute
            self.logger.warning(f"Could not determine duration, using fallback: {self._duration}ms")
            self.duration_changed.emit(self._duration)
            self.duration_timer.stop()