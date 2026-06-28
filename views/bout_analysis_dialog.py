# views/bout_analysis_dialog.py - Optional downstream bout-analysis window.
#
# Bout analysis is deliberately kept OUT of the standard analysis path: it runs
# in this dedicated dialog, reads the already-loaded annotation files, and never
# touches the Summary/Intervals tables or the auto-exported summary_table.csv
# (1.4.0). The numeric work lives in the pure, Qt-free ``models.bout_analysis``.

from __future__ import annotations

import csv
import logging
import os
import statistics
from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSpinBox, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from models.bout_analysis import (
    BoutStats,
    compute_bout_stats,
    compute_bouts,
    estimate_bci_broken_stick,
    estimate_bci_lognormal_mixture,
)
from utils.csv_safety import SafeCsvWriter
from utils.figure_export import (
    FIGURE_EXPORT_FILTER,
    normalise_figure_export_path,
    save_qwidget_figure,
    show_export_complete,
)
from views.bout_raster_dialog import _RasterCanvas
from views.viz_delegates import CellVizDelegate

# (attribute on BoutStats, column header) in display/export order.
_COLUMNS = [
    ("animal_id", "animal_id"),
    ("behavior", "behavior"),
    ("bci", "BCI (s)"),
    ("n_events", "Events"),
    ("n_bouts", "Bouts"),
    ("events_per_bout_mean", "Events/bout (mean)"),
    ("bout_duration_mean", "Bout dur mean (s)"),
    ("bout_duration_median", "Bout dur median (s)"),
    ("bout_duration_total", "Bout dur total (s)"),
    ("within_bout_active_total", "Active in bouts (s)"),
    ("inter_bout_interval_mean", "Inter-bout (s)"),
    ("bout_rate_per_min", "Bouts/min"),
]

_INT_FIELDS = {"n_events", "n_bouts"}


class _ClickToggleList(QListWidget):
    """List whose checkable items toggle when clicked anywhere (text or box).

    A plain QListWidget only toggles when the user hits the small checkbox
    indicator. Here a click anywhere on the row flips the check state exactly
    once (we accept the event so Qt's default indicator toggle doesn't also
    fire), which is friendlier for selecting behaviours.
    """

    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if item is not None and (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            new_state = (
                Qt.CheckState.Unchecked
                if item.checkState() == Qt.CheckState.Checked
                else Qt.CheckState.Checked
            )
            item.setCheckState(new_state)  # emits itemChanged -> recompute
            event.accept()
            return
        super().mousePressEvent(event)


class BoutAnalysisDialog(QDialog):
    """Compute and display per-(animal, behaviour) bout statistics.

    Args:
        parent: parent widget.
        per_file: list of ``(animal_id, events_by_behavior, test_duration)``
            where ``events_by_behavior`` is ``{behavior: [(onset, offset), ...]}``
            in seconds.
        behaviors: behaviour names to offer in the selector (ordered).
    """

    def __init__(self, parent, per_file, behaviors):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self._per_file = per_file or []
        self._behaviors = list(behaviors or [])
        self._rows: List[Tuple[str, BoutStats]] = []

        self.setWindowTitle("Bout Analysis")
        self.resize(940, 580)
        self._build_ui()
        self._recompute()
        self._refresh_raster()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Cluster repeated events of a behaviour into bouts: consecutive "
            "events no further apart than the bout criterion (BCI) belong to "
            "the same bout. This window is independent of the standard "
            "analysis and export."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # Controls row: BCI + estimate + recompute.
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Bout criterion (s):"))
        self.bci_spin = QDoubleSpinBox()
        self.bci_spin.setDecimals(2)
        self.bci_spin.setRange(0.0, 600.0)
        self.bci_spin.setSingleStep(0.25)
        self.bci_spin.setValue(1.0)
        controls.addWidget(self.bci_spin)

        self.estimate_button = QPushButton("Estimate BCI...")
        self.estimate_button.setToolTip(
            "Advisory estimate from the inter-event-interval distribution "
            "(review before adopting; not applied automatically)"
        )
        controls.addWidget(self.estimate_button)

        self.recompute_button = QPushButton("Recompute")
        controls.addWidget(self.recompute_button)
        controls.addStretch()
        layout.addLayout(controls)

        # Inline estimate read-out (no modal dialog): shows the suggested BCI
        # and which method produced it.
        self.estimate_label = QLabel("")
        self.estimate_label.setStyleSheet("color: gray;")
        layout.addWidget(self.estimate_label)

        # Body: behaviour selector (left) + results table (right).
        body = QHBoxLayout()

        selector_box = QVBoxLayout()
        selector_box.addWidget(QLabel("Behaviours:"))
        self.behavior_list = _ClickToggleList()
        self.behavior_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.behavior_list.setMaximumWidth(220)
        for index, behavior in enumerate(self._behaviors):
            item = QListWidgetItem(behavior)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            # Default to only the first behaviour checked; the user opts in to
            # the others (avoids a large initial computation / wall of rows).
            item.setCheckState(
                Qt.CheckState.Checked if index == 0 else Qt.CheckState.Unchecked
            )
            self.behavior_list.addItem(item)
        selector_box.addWidget(self.behavior_list)
        body.addLayout(selector_box)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(len(_COLUMNS))
        self.results_table.setHorizontalHeaderLabels([label for _, label in _COLUMNS])
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        # Inline data bars on the key numeric columns (scale set per render).
        self._bar_delegates = {}
        for col in (4, 5, 6, 8, 11):  # n_bouts, events/bout, dur mean, dur total, bouts/min
            delegate = CellVizDelegate(self).configure("databar", vmin=0.0, scale=1.0)
            self.results_table.setItemDelegateForColumn(col, delegate)
            self._bar_delegates[col] = delegate
        body.addWidget(self.results_table, 1)

        # Two tabs: the statistics table and a per-animal bout raster, both
        # driven by the shared BCI / behaviour selection above.
        self.tab_widget = QTabWidget()
        table_tab = QWidget()
        table_tab.setLayout(body)
        self.tab_widget.addTab(table_tab, "Table")

        raster_tab = QWidget()
        raster_layout = QVBoxLayout(raster_tab)
        raster_row = QHBoxLayout()
        raster_row.addWidget(QLabel("Behaviour:"))
        self.raster_combo = QComboBox()
        self.raster_combo.addItems(self._behaviors)
        _ai = self.raster_combo.findText("Attack bites")
        if _ai >= 0:
            self.raster_combo.setCurrentIndex(_ai)
        raster_row.addWidget(self.raster_combo)
        raster_row.addWidget(QLabel("(uses the BCI above; bar height/colour = bites per bout)"))
        raster_row.addStretch()
        raster_row.addWidget(QLabel("DPI:"))
        self.raster_dpi_spin = QSpinBox()
        self.raster_dpi_spin.setRange(72, 1200)
        self.raster_dpi_spin.setSingleStep(50)
        self.raster_dpi_spin.setValue(300)
        self.raster_dpi_spin.setFixedWidth(80)
        raster_row.addWidget(self.raster_dpi_spin)
        self.raster_figure_export_button = QPushButton("Export Figure...")
        raster_row.addWidget(self.raster_figure_export_button)
        self.raster_export_button = QPushButton("Export Bouts CSV...")
        raster_row.addWidget(self.raster_export_button)
        raster_layout.addLayout(raster_row)
        self.raster_canvas = _RasterCanvas()
        raster_scroll = QScrollArea()
        raster_scroll.setWidgetResizable(True)
        raster_scroll.setWidget(self.raster_canvas)
        raster_layout.addWidget(raster_scroll, 1)
        self.tab_widget.addTab(raster_tab, "Raster")
        layout.addWidget(self.tab_widget, 1)

        # Bottom: copy / export / close.
        bottom = QHBoxLayout()
        self.copy_button = QPushButton("Copy to Clipboard")
        self.export_button = QPushButton("Export CSV...")
        bottom.addWidget(self.copy_button)
        bottom.addWidget(self.export_button)
        bottom.addStretch()
        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.reject)
        bottom.addWidget(close_box)
        layout.addLayout(bottom)

        self.estimate_button.clicked.connect(self._estimate)
        self.recompute_button.clicked.connect(self._recompute)
        self.bci_spin.valueChanged.connect(self._recompute)
        self.bci_spin.valueChanged.connect(self._refresh_raster)
        self.behavior_list.itemChanged.connect(self._recompute)
        self.raster_combo.currentIndexChanged.connect(self._refresh_raster)
        self.copy_button.clicked.connect(self._copy_to_clipboard)
        self.export_button.clicked.connect(self._export_csv)
        self.raster_figure_export_button.clicked.connect(self._export_raster_figure)
        self.raster_export_button.clicked.connect(self._export_raster)

    # ------------------------------------------------------------------ #
    # Computation
    # ------------------------------------------------------------------ #
    def _selected_behaviors(self):
        selected = []
        for row in range(self.behavior_list.count()):
            item = self.behavior_list.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
        return selected

    def _recompute(self, *_args):
        bci = float(self.bci_spin.value())
        behaviors = self._selected_behaviors()
        rows: List[Tuple[str, BoutStats]] = []
        for animal_id, events_by_behavior, duration in self._per_file:
            for behavior in behaviors:
                events = events_by_behavior.get(behavior)
                if not events:
                    continue
                stats = compute_bout_stats(
                    events, bci, behavior=behavior,
                    session_duration=duration if duration > 0 else None,
                )
                rows.append((animal_id, stats))
        self._rows = rows
        self._populate_table(rows)

    def _estimate(self):
        """Suggest a BCI inline (no modal). Default method = log-normal mixture
        (Tolkamp & Kyriazakis), with broken-stick (Sibly et al.) as fallback."""
        mixture_values = []
        broken_values = []
        for _animal_id, events_by_behavior, _duration in self._per_file:
            for behavior in self._selected_behaviors():
                events = events_by_behavior.get(behavior)
                if not events:
                    continue
                mixture = estimate_bci_lognormal_mixture(events)
                if mixture is not None:
                    mixture_values.append(mixture)
                broken = estimate_bci_broken_stick(events)
                if broken is not None:
                    broken_values.append(broken)

        if mixture_values:
            value = float(statistics.median(mixture_values))
            label = f"log-normal mixture, median of {len(mixture_values)}"
        elif broken_values:
            value = float(statistics.median(broken_values))
            label = f"broken-stick fallback, median of {len(broken_values)}"
        else:
            self.estimate_label.setText(
                "Estimated BCI: not enough repeated events to estimate."
            )
            return

        # Setting the spin box triggers a recompute via valueChanged.
        self.bci_spin.setValue(round(value, 2))
        self.estimate_label.setText(f"Estimated BCI ≈ {value:.2f} s  ({label})")

    # ------------------------------------------------------------------ #
    # Raster tab
    # ------------------------------------------------------------------ #
    def _raster_bouts(self):
        behavior = self.raster_combo.currentText()
        bci = float(self.bci_spin.value())
        data, max_t = [], 1.0
        for animal_id, events_by_behavior, _duration in self._per_file:
            events = events_by_behavior.get(behavior, [])
            data.append((animal_id, compute_bouts(events, bci)))
            for _onset, offset in events:
                max_t = max(max_t, offset)
        return data, max_t

    def _refresh_raster(self, *_args):
        data, max_t = self._raster_bouts()
        self.raster_canvas.set_data(data, max_t)

    def _export_raster_figure(self):
        if not self._per_file:
            QMessageBox.information(self, "No Results", "There is no raster figure to export.")
            return

        self._refresh_raster()
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Bout Raster Figure",
            "bout_raster.png",
            FIGURE_EXPORT_FILTER,
        )
        if not path:
            return

        try:
            path, file_format = normalise_figure_export_path(path, selected_filter)
            save_qwidget_figure(
                self.raster_canvas,
                path,
                file_format,
                self.raster_dpi_spin.value(),
            )
        except Exception as exc:
            self.logger.error("Failed to export bout raster figure: %s", exc, exc_info=True)
            QMessageBox.warning(self, "Export Failed", f"Could not write figure:\n{exc}")
            return

        show_export_complete(self, path, timeout_ms=1000)

    def _export_raster(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Bouts", "bouts.csv", "CSV Files (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        behavior = self.raster_combo.currentText()
        bci = float(self.bci_spin.value())
        data, _ = self._raster_bouts()
        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = SafeCsvWriter(csv.writer(handle))
                writer.writerow(["animal_id", "behavior", "bci_s", "bout_index",
                                 "start_s", "end_s", "n_events", "duration_s"])
                for animal_id, bouts in data:
                    for k, bt in enumerate(bouts, 1):
                        writer.writerow([animal_id, behavior, f"{bci:.2f}", k,
                                         f"{bt.start:.4f}", f"{bt.end:.4f}", bt.n_events,
                                         f"{bt.duration:.4f}"])
        except OSError as exc:
            QMessageBox.warning(self, "Export Failed", f"Could not write file:\n{exc}")
            return
        QMessageBox.information(self, "Export Complete", f"Bouts exported to:\n{os.path.basename(path)}")

    # ------------------------------------------------------------------ #
    # Rendering / output
    # ------------------------------------------------------------------ #
    @staticmethod
    def _format(attr, value):
        if value is None:
            return ""
        if attr in _INT_FIELDS:
            return str(int(value))
        if attr == "behavior" or attr == "animal_id":
            return str(value)
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return str(value)

    def _row_values(self, animal_id, stats):
        values = []
        for attr, _label in _COLUMNS:
            if attr == "animal_id":
                values.append(self._format(attr, animal_id))
            else:
                values.append(self._format(attr, getattr(stats, attr, None)))
        return values

    def _populate_table(self, rows):
        self.results_table.setRowCount(0)
        col_max = {col: 0.0 for col in self._bar_delegates}
        for animal_id, stats in rows:
            row = self.results_table.rowCount()
            self.results_table.insertRow(row)
            for col, value in enumerate(self._row_values(animal_id, stats)):
                item = QTableWidgetItem(value)
                if col in self._bar_delegates:
                    num = getattr(stats, _COLUMNS[col][0], None)
                    if isinstance(num, (int, float)):
                        item.setData(Qt.ItemDataRole.UserRole, float(num))
                        col_max[col] = max(col_max[col], float(num))
                self.results_table.setItem(row, col, item)
        for col, delegate in self._bar_delegates.items():
            delegate.configure("databar", vmin=0.0, scale=col_max[col] or 1.0)
        self.results_table.viewport().update()

    def _copy_to_clipboard(self):
        if not self._rows:
            return
        lines = ["\t".join(label for _, label in _COLUMNS)]
        for animal_id, stats in self._rows:
            lines.append("\t".join(self._row_values(animal_id, stats)))
        QApplication.clipboard().setText("\n".join(lines))

    def _export_csv(self):
        if not self._rows:
            QMessageBox.information(self, "No Results", "There is nothing to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Bout Analysis", "bout_analysis.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = SafeCsvWriter(csv.writer(handle))
                writer.writerow([attr for attr, _ in _COLUMNS])
                for animal_id, stats in self._rows:
                    writer.writerow(self._row_values(animal_id, stats))
        except OSError as exc:
            QMessageBox.warning(self, "Export Failed", f"Could not write file:\n{exc}")
            return
        QMessageBox.information(
            self, "Export Complete", f"Bout analysis exported to:\n{os.path.basename(path)}"
        )
