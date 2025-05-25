# utils/threaded_loader.py
import logging
import time
from PySide6.QtCore import QObject, QThread, Signal, Slot

class VideoLoadWorker(QObject):
    """
    Worker object that loads a video in a separate thread.
    
    Signals:
        finished: Emitted when loading completes (successfully or not)
        error: Emitted when an error occurs during loading
        progress: Emitted to report loading progress
    """
    
    finished = Signal(bool)  # Success status
    error = Signal(str)  # Error message
    progress = Signal(int)  # Progress percentage
    
    def __init__(self, video_model):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self._video_model = video_model
        self._video_path = None
        self._abort = False
    
    def set_video_path(self, path):
        """Set the path of the video to load."""
        self._video_path = path
    
    def abort(self):
        """Abort the loading operation."""
        self._abort = True
    
    @Slot()
    def load_video(self):
        """
        Load the video file. This method runs in a worker thread.
        """
        if not self._video_path:
            self.error.emit("No video path specified")
            self.finished.emit(False)
            return
        
        try:
            self.logger.info(f"Worker thread: Loading video {self._video_path}")
            
            # Report initial progress
            self.progress.emit(10)
            
            # Add more progress updates during different stages of loading
            # This simulates progress during the actual loading operation
            
            # Opening file stage
            self.progress.emit(20)
            time.sleep(0.1)  # Small delay to make progress visible
            
            # Media parsing stage
            self.progress.emit(40)
            time.sleep(0.1)  # Small delay to make progress visible
            
            # Perform the actual loading using the model's internal method
            # We're just moving the synchronous loading to a different thread
            self.progress.emit(60)
            success = self._video_model._load_video_internal(self._video_path)
            
            # Check for abort request
            if self._abort:
                self.logger.info("Video loading aborted")
                self.finished.emit(False)
                return
            
            # Report progress before finalizing
            self.progress.emit(80)
            time.sleep(0.1)  # Small delay to make progress visible
            
            # Finalization stage
            self.progress.emit(100)
            self.finished.emit(success)
            
        except Exception as e:
            self.logger.error(f"Error in worker thread: {str(e)}", exc_info=True)
            self.error.emit(f"Failed to load video: {str(e)}")
            self.finished.emit(False)


class ThreadedVideoLoader(QObject):
    """
    Manages threaded loading of video files.
    
    Signals:
        loading_started: Emitted when loading starts
        loading_finished: Emitted when loading finishes (success status)
        loading_error: Emitted when an error occurs during loading
        loading_progress: Emitted to report loading progress
    """
    
    loading_started = Signal()
    loading_finished = Signal(bool)  # Success status
    loading_error = Signal(str)  # Error message
    loading_progress = Signal(int)  # Progress percentage
    
    def __init__(self, video_model):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self._video_model = video_model
        
        # Thread and worker
        self._thread = None
        self._worker = None
        
        # Active loading flag
        self._is_loading = False
    
    def is_loading(self):
        """Check if a loading operation is in progress."""
        return self._is_loading
    
    def load_video(self, video_path):
        """
        Load a video file in a separate thread.
        
        Args:
            video_path (str): Path to the video file
            
        Returns:
            bool: True if loading started successfully, False otherwise
        """
        # Check if already loading
        if self._is_loading:
            self.logger.warning("Ignoring load request - already loading a video")
            return False
        
        self.logger.info(f"Starting threaded video loading: {video_path}")
        
        # Create thread and worker
        self._thread = QThread()
        self._worker = VideoLoadWorker(self._video_model)
        self._worker.moveToThread(self._thread)
        
        # Connect signals
        self._thread.started.connect(self._worker.load_video)
        self._worker.finished.connect(self._on_loading_finished)
        self._worker.error.connect(self.loading_error)
        self._worker.progress.connect(self.loading_progress)
        
        # Set video path
        self._worker.set_video_path(video_path)
        
        # Set loading flag
        self._is_loading = True
        
        # Emit started signal
        self.loading_started.emit()
        
        # Start thread
        self._thread.start()
        
        return True
    
    def abort_loading(self):
        """Abort the current loading operation."""
        if not self._is_loading or not self._worker:
            return
        
        self.logger.info("Aborting video loading")
        self._worker.abort()
    
    def _on_loading_finished(self, success):
        """
        Handle loading finished.
        
        Args:
            success (bool): Whether loading was successful
        """
        if not self._is_loading:
            return
        
        self.logger.info(f"Video loading finished (success: {success})")
        
        # Clean up thread and worker
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
        
        self._worker = None
        self._is_loading = False
        
        # Emit finished signal
        self.loading_finished.emit(success)