# views/analysis_view.py - Enhanced with metrics configuration, file management, and export options
import logging
import os
import math
import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QProgressBar, QPushButton,
    QGroupBox, QSpinBox, QCheckBox, QTabWidget, QApplication,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication, QPixmap

from utils.app_icon import find_resource_path

class AnalysisView(QWidget):
    """
    View for CSV analysis and automatic summary statistics.
    Now includes metrics configuration and interval-based analysis.
    
    Signals:
        files_dropped: Emitted when files are dropped (list of file paths)
        load_files_requested: Emitted when load files button is clicked
        remove_files_requested: Emitted when remove files button is clicked (list of indices)
        clear_files_requested: Emitted when clear files button is clicked
        export_table_requested: Emitted when export button is clicked
        interval_settings_changed: Emitted when interval settings are changed (enabled, seconds)
        configure_metrics_requested: Emitted when configure metrics button is clicked
        export_metrics_config_requested: Emitted when export metrics config button is clicked
        import_metrics_config_requested: Emitted when import metrics config button is clicked
        visualize_files_requested: Emitted when loaded files should open in Visualization
    """
    
    files_dropped = Signal(list)
    load_files_requested = Signal()
    remove_files_requested = Signal(list)
    clear_files_requested = Signal()
    export_table_requested = Signal()
    interval_settings_changed = Signal(bool, int)  # enabled, interval_seconds
    configure_metrics_requested = Signal()
    export_metrics_config_requested = Signal()
    import_metrics_config_requested = Signal()
    visualize_files_requested = Signal()
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing AnalysisView")
        
        # Enable drag and drop
        self.setAcceptDrops(True)
        
        # Store loaded file paths
        self._file_paths = []
        
        self.setup_ui()
        self.connect_signals()

    @staticmethod
    def _animal_id_from_path(file_path):
        """Return the display animal_id for an annotation path."""
        animal_id = os.path.splitext(os.path.basename(file_path))[0]
        if animal_id.endswith('_annotations'):
            animal_id = animal_id[: -len('_annotations')]
        return animal_id

    @staticmethod
    def _animal_sort_key(animal_id):
        """Natural-sort key so RI_001 precedes RI_002 and RI_010."""
        key_parts = []
        for part in re.split(r'(\d+)', str(animal_id)):
            if part.isdigit():
                key_parts.append((1, int(part)))
            else:
                key_parts.append((0, part.casefold()))
        return key_parts

    @classmethod
    def _sorted_result_items(cls, results):
        """Return analysis result items ordered by animal_id."""
        return sorted(
            results.items(),
            key=lambda item: cls._animal_sort_key(cls._animal_id_from_path(item[0])),
        )

    @staticmethod
    def _mean_sem_strings(values):
        """Return formatted mean and SEM for a list of numeric values."""
        values = [value for value in values if math.isfinite(value)]
        if not values:
            return "", ""

        mean_value = sum(values) / len(values)
        sem_value = 0.0
        if len(values) > 1:
            variance = sum((value - mean_value) ** 2 for value in values) / (len(values) - 1)
            sem_value = math.sqrt(variance) / math.sqrt(len(values))

        return f"{mean_value:.2f}", f"{sem_value:.2f}"

    def _update_dropzone_icon(self):
        """Render the CSV drop-zone icon crisply on High-DPI screens.

        The source PNG is high resolution (743x970). We scale it to the
        *physical* pixel height (logical height x devicePixelRatio) and
        tag the resulting pixmap with that ratio. Without this, Qt draws
        a 64-logical-px pixmap stretched across the screen's physical
        pixels (e.g. 96 px at 150% scaling), which looks blurry.
        """
        source = getattr(self, "_dropzone_pixmap_source", None)
        if source is None or source.isNull():
            return
        screen = self.screen() or QGuiApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen is not None else 1.0
        target_h = max(1, round(self._dropzone_icon_height * dpr))
        scaled = source.scaledToHeight(
            target_h, Qt.TransformationMode.SmoothTransformation
        )
        scaled.setDevicePixelRatio(dpr)
        self.dropzone_icon.setPixmap(scaled)

    def showEvent(self, event):
        # Re-render the icon once the widget is mapped: at construction
        # time the window may not yet be on its final screen, so the
        # devicePixelRatio could differ from the primary screen used
        # during setup_ui.
        super().showEvent(event)
        self._update_dropzone_icon()

    def setup_ui(self):
        """Set up simplified user interface for automatic analysis."""
        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(4)
        
        # Drop-zone header: CSV icon stacked above the instruction text.
        # Built here, but added to the shared top row alongside the
        # Analysis Settings group further below.
        self.dropzone_group = QVBoxLayout()
        self.dropzone_group.setSpacing(4)

        self.dropzone_icon = QLabel()
        self.dropzone_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Logical display height of the icon in device-independent px.
        self._dropzone_icon_height = 64
        self._dropzone_pixmap_source = QPixmap()
        _csv_icon_path = find_resource_path("csvicon.png")
        if _csv_icon_path:
            self._dropzone_pixmap_source = QPixmap(_csv_icon_path)
        self._update_dropzone_icon()
        self.dropzone_group.addWidget(
            self.dropzone_icon, alignment=Qt.AlignmentFlag.AlignHCenter
        )

        # Make instructions text much larger and position it lower
        self.instructions = QLabel("Drop CSV annotation files here")
        self.instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.instructions.setStyleSheet("font-size: 20px; font-weight: bold; margin-top: 4px;")
        self.dropzone_group.addWidget(self.instructions)

        # Analysis Settings Group
        self.settings_group = QGroupBox("Analysis Settings")
        self.settings_group.setMinimumHeight(110)
        self.settings_group.setMaximumHeight(150)
        self.settings_group.setMaximumWidth(400)  # Set maximum height
        self.settings_layout = QVBoxLayout(self.settings_group)
        self.settings_layout.setContentsMargins(8, 8, 8, 8)
        self.settings_layout.setSpacing(4)
        
        # Interval analysis option
        self.interval_layout = QHBoxLayout()
        self.interval_checkbox = QCheckBox("Enable interval analysis")
        self.interval_checkbox.setToolTip("Break down analysis into fixed time intervals")
        self.interval_layout.addWidget(self.interval_checkbox)
        
        # Interval seconds setting
        self.interval_seconds_label = QLabel("Interval size (seconds):")
        self.interval_layout.addWidget(self.interval_seconds_label)
        
        self.interval_seconds_spinner = QSpinBox()
        self.interval_seconds_spinner.setMinimum(1)
        self.interval_seconds_spinner.setMaximum(3600)  # Max 1 hour
        self.interval_seconds_spinner.setValue(60)  # Default 60 seconds
        self.interval_seconds_spinner.setToolTip("Size of each time interval for analysis")
        self.interval_layout.addWidget(self.interval_seconds_spinner)
        
        # Add interval layout to settings group
        self.settings_layout.addLayout(self.interval_layout)
        
        # Add metrics configuration buttons
        self.metrics_button_layout = QHBoxLayout()
        
        # Configure Metrics button
        self.configure_metrics_button = QPushButton("Configure Metrics...")
        self.configure_metrics_button.setToolTip("Configure custom latency and total time metrics")
        self.metrics_button_layout.addWidget(self.configure_metrics_button)
        
        # Export Metrics Config button
        self.export_metrics_button = QPushButton("Export Config...")
        self.export_metrics_button.setToolTip("Export metrics configuration to JSON file")
        self.metrics_button_layout.addWidget(self.export_metrics_button)
        
        # Import Metrics Config button
        self.import_metrics_button = QPushButton("Import Config...")
        self.import_metrics_button.setToolTip("Import metrics configuration from JSON file")
        self.metrics_button_layout.addWidget(self.import_metrics_button)
        
        self.metrics_button_layout.addStretch()
        
        # Add metrics buttons to settings group
        self.settings_layout.addLayout(self.metrics_button_layout)

        # Top row: Analysis Settings on the left, the CSV drop-zone
        # (icon above text) centred in the space to its right. Equal
        # stretches on either side of the drop-zone keep it centred;
        # the settings group is pinned top-left so the two line up.
        self.top_row = QHBoxLayout()
        self.top_row.setContentsMargins(0, 0, 0, 0)
        self.top_row.addWidget(
            self.settings_group, alignment=Qt.AlignmentFlag.AlignTop
        )
        self.top_row.addStretch()
        self.top_row.addLayout(self.dropzone_group)
        self.top_row.addStretch()
        self.layout.addLayout(self.top_row)

        # Tabbed area: Files / Summary / Intervals
        self.tab_widget = QTabWidget()
        self.tab_widget.setMinimumHeight(260)
        self.tab_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        # --- Files tab ---------------------------------------------------
        self.files_tab = QWidget()
        files_layout = QVBoxLayout(self.files_tab)
        files_layout.setContentsMargins(6, 6, 6, 6)
        files_layout.setSpacing(4)

        self.files_label = QLabel("Loaded Files:")
        self.files_label.setStyleSheet("font-weight: bold;")
        files_layout.addWidget(self.files_label)

        self.files_table = QTableWidget()
        self.files_table.setColumnCount(2)
        self.files_table.setHorizontalHeaderLabels(["File Name", "Path"])
        self.files_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.files_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        files_layout.addWidget(self.files_table)

        self.tab_widget.addTab(self.files_tab, "Files")

        # --- Summary tab -------------------------------------------------
        self.summary_tab = QWidget()
        summary_layout = QVBoxLayout(self.summary_tab)
        summary_layout.setContentsMargins(6, 6, 6, 6)
        summary_layout.setSpacing(4)

        summary_header = QHBoxLayout()
        summary_title = QLabel("Whole-session summary:")
        summary_title.setStyleSheet("font-weight: bold;")
        summary_header.addWidget(summary_title)
        summary_header.addStretch()

        self.copy_summary_button = QPushButton("Copy to Clipboard")
        self.copy_summary_button.setToolTip("Copy the summary table to the clipboard as TSV")
        summary_header.addWidget(self.copy_summary_button)
        summary_layout.addLayout(summary_header)

        self.summary_table = QTableWidget()
        self.summary_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.summary_table.setAlternatingRowColors(True)
        summary_layout.addWidget(self.summary_table)

        self.tab_widget.addTab(self.summary_tab, "Summary")

        # --- Intervals tab ----------------------------------------------
        self.intervals_tab = QWidget()
        intervals_layout = QVBoxLayout(self.intervals_tab)
        intervals_layout.setContentsMargins(6, 6, 6, 6)
        intervals_layout.setSpacing(4)

        intervals_header = QHBoxLayout()
        intervals_title = QLabel("Per-interval summary:")
        intervals_title.setStyleSheet("font-weight: bold;")
        intervals_header.addWidget(intervals_title)
        intervals_header.addStretch()

        self.copy_intervals_button = QPushButton("Copy to Clipboard")
        self.copy_intervals_button.setToolTip("Copy the interval table to the clipboard as TSV")
        intervals_header.addWidget(self.copy_intervals_button)
        intervals_layout.addLayout(intervals_header)

        self.intervals_table = QTableWidget()
        self.intervals_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.intervals_table.setAlternatingRowColors(True)
        intervals_layout.addWidget(self.intervals_table)

        self.tab_widget.addTab(self.intervals_tab, "Intervals")
        # Intervals tab is only meaningful when interval analysis is enabled.
        self._set_intervals_tab_enabled(False)

        self.layout.addWidget(self.tab_widget, 1)

        # File management buttons layout
        self.buttons_layout = QHBoxLayout()
        
        # Load files button
        self.load_button = QPushButton("Load Files")
        self.buttons_layout.addWidget(self.load_button)
        
        # Remove selected files button
        self.remove_button = QPushButton("Remove Selected")
        self.buttons_layout.addWidget(self.remove_button)
        
        # Clear all files button
        self.clear_button = QPushButton("Clear All")
        self.buttons_layout.addWidget(self.clear_button)

        self.visualize_button = QPushButton("Visualize")
        self.visualize_button.setToolTip("Open the loaded annotation files in Visualization")
        self.visualize_button.setEnabled(False)
        self.buttons_layout.addWidget(self.visualize_button)
        
        # Add spacer to push buttons to the left
        self.buttons_layout.addStretch()
        
        self.layout.addLayout(self.buttons_layout)
        
        # Progress indicator
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)
        
        # Export button layout
        self.export_layout = QHBoxLayout()
        self.export_button = QPushButton("Export Summary Table")
        self.export_button.setMinimumHeight(28)
        self.export_button.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.export_button.setStyleSheet("font-weight: bold;")
        self.export_layout.addWidget(self.export_button)
        self.export_layout.addStretch()
        self.layout.addLayout(self.export_layout)
        
        # Status message area. We avoid a hard-coded text color so the
        # label remains readable under both light and dark Qt palettes;
        # only the font weight is forced for emphasis. Themed colours come
        # from the application's QPalette.
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-weight: bold;")
        self.layout.addWidget(self.status_label)
        
        # Set initial state for interval controls
        self.update_interval_controls_state()
    
    def update_interval_controls_state(self):
        """Update the state of interval analysis controls based on checkbox."""
        is_enabled = self.interval_checkbox.isChecked()
        self.interval_seconds_spinner.setEnabled(is_enabled)
        self.interval_seconds_label.setEnabled(is_enabled)
        # Mirror the same state on the Intervals tab; an empty/disabled tab
        # gives the user a clear hint about why interval data is missing.
        self._set_intervals_tab_enabled(is_enabled)

    def _set_intervals_tab_enabled(self, enabled):
        """Enable/disable the Intervals tab in the tab bar."""
        index = self.tab_widget.indexOf(self.intervals_tab)
        if index != -1:
            self.tab_widget.setTabEnabled(index, enabled)

    def connect_signals(self):
        """Connect widget signals to slots."""
        self.load_button.clicked.connect(self.load_files_requested)
        self.remove_button.clicked.connect(self.on_remove_button_clicked)
        self.clear_button.clicked.connect(self.clear_files_requested)
        self.export_button.clicked.connect(self.export_table_requested)
        self.visualize_button.clicked.connect(self.visualize_files_requested)

        # Connect interval analysis controls
        self.interval_checkbox.stateChanged.connect(self.on_interval_settings_changed)
        self.interval_seconds_spinner.valueChanged.connect(self.on_interval_settings_changed)

        # Connect metrics configuration buttons
        self.configure_metrics_button.clicked.connect(self.configure_metrics_requested)
        self.export_metrics_button.clicked.connect(self.export_metrics_config_requested)
        self.import_metrics_button.clicked.connect(self.import_metrics_config_requested)

        # Copy-to-clipboard buttons on the result tabs
        self.copy_summary_button.clicked.connect(
            lambda: self._copy_table_to_clipboard(self.summary_table)
        )
        self.copy_intervals_button.clicked.connect(
            lambda: self._copy_table_to_clipboard(self.intervals_table)
        )
    
    def on_interval_settings_changed(self):
        """Handle changes to interval analysis settings."""
        self.update_interval_controls_state()
        
        # Emit signal with the new settings
        enabled = self.interval_checkbox.isChecked()
        seconds = self.interval_seconds_spinner.value()
        self.interval_settings_changed.emit(enabled, seconds)
        
        # Log the change
        self.logger.debug(f"Interval analysis settings changed: enabled={enabled}, seconds={seconds}")
        
        # Update status message
        if enabled:
            self.set_status_message(f"Interval analysis enabled with {seconds}-second intervals")
        else:
            self.set_status_message("Interval analysis disabled")
    
    def set_interval_settings(self, enabled, seconds):
        """
        Set the interval analysis settings in the UI.

        Args:
            enabled (bool): Whether interval analysis is enabled
            seconds (int): Size of each interval in seconds
        """
        # Block signals to prevent recursion / double emission while we
        # write both control values inside the same batch.
        self.interval_checkbox.blockSignals(True)
        self.interval_seconds_spinner.blockSignals(True)

        # Set values
        self.interval_checkbox.setChecked(enabled)
        self.interval_seconds_spinner.setValue(seconds)

        # Update control states
        self.update_interval_controls_state()

        # Restore signals
        self.interval_checkbox.blockSignals(False)
        self.interval_seconds_spinner.blockSignals(False)

        # 1.3.3+ FIX: emit explicitly after the batch write.  Previously
        # the surrounding ``blockSignals(True)`` swallowed the
        # ``stateChanged`` emission that normally drives
        # ``on_interval_settings_changed`` -> controller ->
        # ``model.set_interval_analysis``.  That meant a config-restored
        # "Enable interval analysis" checkbox displayed as ON at launch
        # while the model still believed interval analysis was disabled,
        # and the very first drop of CSVs produced an empty Intervals
        # tab.  Toggling the checkbox off-then-on used to be the only
        # way to push the state through.
        self.interval_settings_changed.emit(enabled, seconds)
    
    def get_interval_settings(self):
        """
        Get the current interval analysis settings from the UI.
        
        Returns:
            tuple: (enabled, seconds)
        """
        enabled = self.interval_checkbox.isChecked()
        seconds = self.interval_seconds_spinner.value()
        return (enabled, seconds)
    
    def on_remove_button_clicked(self):
        """Handle remove button click - get selected rows and emit signal."""
        selected_items = self.files_table.selectedItems()
        
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Please select file(s) to remove.")
            return
        
        # Get unique row indices
        selected_rows = set()
        for item in selected_items:
            selected_rows.add(item.row())
        
        selected_indices = sorted(list(selected_rows))
        self.remove_files_requested.emit(selected_indices)
    
    def dragEnterEvent(self, event):
        """
        Handle drag enter events.
        
        Args:
            event (QDragEnterEvent): Drag enter event
        """
        # Check if the drag contains URLs (files)
        if event.mimeData().hasUrls():
            # Check if all URLs are CSV files
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if not file_path.lower().endswith('.csv'):
                    return
            
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        """
        Handle drop events.
        
        Args:
            event (QDropEvent): Drop event
        """
        # Get file paths from URLs
        file_paths = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            file_paths.append(file_path)
        
        if file_paths:
            self.files_dropped.emit(file_paths)
    
    @Slot(list)
    def update_file_list(self, file_paths):
        """
        Update the list of loaded files.
        
        Args:
            file_paths (list): List of file paths
        """
        # Store the file paths
        self._file_paths = file_paths
        self.visualize_button.setEnabled(bool(file_paths))
        
        # Update table
        self.files_table.setRowCount(0)
        
        for file_path in file_paths:
            row = self.files_table.rowCount()
            self.files_table.insertRow(row)
            
            file_name = os.path.basename(file_path)
            file_name_item = QTableWidgetItem(file_name)
            path_item = QTableWidgetItem(file_path)
            
            self.files_table.setItem(row, 0, file_name_item)
            self.files_table.setItem(row, 1, path_item)
    
    @Slot(dict)
    def update_summary_table(self, results, behaviors=None,
                             latency_metric_names=None,
                             total_time_metric_names=None):
        """
        Populate the Summary tab with whole-session metrics.

        Args:
            results (dict): {file_path: {metric_key: value, ...}, ...}
            behaviors (list, optional): Ordered behavior names (duration/freq
                columns). Falls back to keys present in ``results``.
            latency_metric_names (list, optional): Custom latency metric names.
            total_time_metric_names (list, optional): Custom total-time metric
                names.
        """
        self.logger.info(f"Updating summary table for {len(results)} files")

        if not results:
            self.summary_table.clear()
            self.summary_table.setRowCount(0)
            self.summary_table.setColumnCount(0)
            return

        # Determine the behaviour set if the caller did not pass one
        if not behaviors:
            inferred = set()
            for metrics in results.values():
                for key in metrics:
                    if key.endswith('_duration'):
                        inferred.add(key[:-len('_duration')])
            behaviors = sorted(inferred)

        latency_metric_names = list(latency_metric_names or [])
        total_time_metric_names = list(total_time_metric_names or [])

        # Build column headers: animal_id + duration[*] + frequency[*] + custom metrics
        columns = ['animal_id']
        columns.extend(f"{b} (s)" for b in behaviors)
        columns.extend(f"{b} (n)" for b in behaviors)
        columns.extend(f"{m} (s)" for m in latency_metric_names)
        columns.extend(f"{m} (s)" for m in total_time_metric_names)

        self.summary_table.clear()
        self.summary_table.setColumnCount(len(columns))
        self.summary_table.setHorizontalHeaderLabels(columns)
        data_rows = []

        for file_path, metrics in self._sorted_result_items(results):
            animal_id = self._animal_id_from_path(file_path)
            row = [animal_id]

            for behavior in behaviors:
                value = float(metrics.get(f"{behavior}_duration", 0.0))
                row.append(f"{value:.2f}")
            for behavior in behaviors:
                value = int(metrics.get(f"{behavior}_count", 0))
                row.append(str(value))
            for metric_name in latency_metric_names:
                key = metric_name.lower().replace(' ', '_')
                value = float(metrics.get(key, metrics.get('test_duration', 0.0)))
                row.append(f"{value:.2f}")
            for metric_name in total_time_metric_names:
                key = metric_name.lower().replace(' ', '_')
                value = float(metrics.get(key, 0.0))
                row.append(f"{value:.2f}")

            data_rows.append(row)

        display_rows = data_rows
        if data_rows:
            mean_row = ["mean"]
            sem_row = ["SEM"]
            for col_idx in range(1, len(columns)):
                values = []
                for row in data_rows:
                    try:
                        values.append(float(row[col_idx]))
                    except (TypeError, ValueError, IndexError):
                        continue
                mean_cell, sem_cell = self._mean_sem_strings(values)
                mean_row.append(mean_cell)
                sem_row.append(sem_cell)
            display_rows = data_rows + [mean_row, sem_row]

        self.summary_table.setRowCount(len(display_rows))
        for row_idx, row in enumerate(display_rows):
            for col_idx, value in enumerate(row):
                self.summary_table.setItem(row_idx, col_idx, QTableWidgetItem(value))

        self.summary_table.resizeColumnsToContents()

    @Slot(dict)
    def update_interval_table(self, interval_results, behaviors=None,
                              total_time_metric_names=None):
        """
        Populate the Intervals tab.

        Args:
            interval_results (dict): {file_path: [interval_dict, ...]}
            behaviors (list, optional): Ordered behavior names.
            total_time_metric_names (list, optional): Custom total-time
                metric names.
        """
        self.logger.info(
            f"Updating interval table ({len(interval_results)} files)"
        )

        if not interval_results:
            self.intervals_table.clear()
            self.intervals_table.setRowCount(0)
            self.intervals_table.setColumnCount(0)
            return

        if not behaviors:
            inferred = set()
            for intervals in interval_results.values():
                for interval in intervals:
                    for key in interval:
                        if key.endswith('_duration'):
                            inferred.add(key[:-len('_duration')])
            behaviors = sorted(inferred)

        total_time_metric_names = list(total_time_metric_names or [])

        columns = ['animal_id', 'Interval', 'Time (sec)']
        columns.extend(f"{b} (s)" for b in behaviors)
        columns.extend(f"{b} (n)" for b in behaviors)
        columns.extend(f"{m} (s)" for m in total_time_metric_names)

        rows = []
        for source_path, intervals in self._sorted_result_items(interval_results):
            animal_id = self._animal_id_from_path(source_path)

            for interval in intervals:
                row = [animal_id,
                       str(interval.get('interval_number', '')),
                       f"{interval.get('start_time', 0):.1f}-"
                       f"{interval.get('end_time', 0):.1f}"]
                for behavior in behaviors:
                    row.append(f"{float(interval.get(f'{behavior}_duration', 0.0)):.2f}")
                for behavior in behaviors:
                    row.append(str(int(interval.get(f'{behavior}_count', 0))))
                for metric_name in total_time_metric_names:
                    key = metric_name.lower().replace(' ', '_')
                    row.append(f"{float(interval.get(key, 0.0)):.2f}")
                rows.append(row)

        self.intervals_table.clear()
        self.intervals_table.setColumnCount(len(columns))
        self.intervals_table.setHorizontalHeaderLabels(columns)
        self.intervals_table.setRowCount(len(rows))

        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                self.intervals_table.setItem(r, c, QTableWidgetItem(cell))

        self.intervals_table.resizeColumnsToContents()

    def _copy_table_to_clipboard(self, table):
        """Copy a ``QTableWidget`` to the clipboard as tab-separated text."""
        if table is None or table.rowCount() == 0 or table.columnCount() == 0:
            return

        rows = []
        headers = []
        for col in range(table.columnCount()):
            header_item = table.horizontalHeaderItem(col)
            headers.append(header_item.text() if header_item else '')
        rows.append('\t'.join(headers))

        for r in range(table.rowCount()):
            cells = []
            for c in range(table.columnCount()):
                item = table.item(r, c)
                cells.append(item.text() if item else '')
            rows.append('\t'.join(cells))

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText('\n'.join(rows))
            self.set_status_message("Table copied to clipboard")
    
    def show_progress(self, visible=True, value=0):
        """
        Show or hide progress bar.
        
        Args:
            visible (bool): Whether progress bar should be visible
            value (int): Progress value (0-100)
        """
        self.progress_bar.setVisible(visible)
        if visible:
            self.progress_bar.setValue(value)
    
    def set_status_message(self, message):
        """
        Set status message.
        
        Args:
            message (str): Status message to display
        """
        self.status_label.setText(message)
    
    def select_files(self):
        """
        Open file dialog to select files.
        
        Returns:
            list: List of selected file paths
        """
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        file_dialog.setNameFilter("CSV Files (*.csv)")
        
        if file_dialog.exec():
            return file_dialog.selectedFiles()
        else:
            return []
    
    def select_export_file(self, default_dir=None, default_filename="summary_table.csv"):
        """
        Open file dialog to select export destination.
        
        Args:
            default_dir (str, optional): Default directory to start in
            default_filename (str, optional): Default filename to suggest
        
        Returns:
            str: Selected export file path or empty string if canceled
        """
        # Use current directory if no default provided
        if not default_dir:
            default_dir = os.getcwd()
        
        # Combine path and filename
        default_path = os.path.join(default_dir, default_filename)
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Export Summary Table", 
            default_path, 
            "CSV Files (*.csv)"
        )
        
        return file_path
