# views/predictability_dialog.py - Antecedent-window predictability panel.
#
# Behaviour-agnostic "predictability / announced fraction": of all occurrences
# of a chosen TARGET (event- or bout-level), what fraction are preceded within a
# time window by any of a chosen ANTECEDENT set? Optional chance-correction
# (circular-shift null) controls for how common the antecedents are. Plus a
# pooled lag profile. Per-animal output only; group stats are done downstream.
#
# Embedded as the "Predictability" tab of the Transition Analysis dialog (1.4.0).

from __future__ import annotations

import csv
import logging
import math
import os
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from models.sequence_analysis import antecedent_window_metric, pooled_lag_profile
from utils.csv_safety import SafeCsvWriter
from utils.figure_export import (
    FIGURE_EXPORT_FILTER,
    normalise_figure_export_path,
    save_matplotlib_figure,
    show_export_complete,
)
from views.analysis_charts import MplChartWidget
from views.bout_analysis_dialog import _ClickToggleList
from views.viz_delegates import CellVizDelegate

_COLS = [
    ("animal_id", "animal_id"), ("n_targets", "n target"), ("n_antecedents", "n antec"),
    ("observed", "observed"), ("chance_mean", "chance"), ("above_chance", "above chance"),
]


class PredictabilityPanel(QWidget):
    """Antecedent-window predictability of a target behaviour, per animal."""

    def __init__(self, parent, per_file, behaviors, progress_cb=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self._per_file = per_file or []
        self._behaviors = list(behaviors or [])
        self._rows: List[dict] = []
        # Optional callback(done, total) to drive an external progress dialog
        # during the initial compute (set by the controller); cleared afterwards
        # so in-panel Compute uses the panel's own progress bar.
        self._progress_cb = progress_cb
        self._build_ui()
        self._recompute()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Of all TARGET occurrences, what fraction are preceded within the "
            "window by any ANTECEDENT? Chance-correction shifts the antecedent "
            "times to remove their base-rate. Per-animal values — compare groups "
            "downstream."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Target:"))
        self.target_combo = QComboBox()
        self.target_combo.addItems(self._behaviors)
        ai = self.target_combo.findText("Attack bites")
        if ai >= 0:
            self.target_combo.setCurrentIndex(ai)
        row1.addWidget(self.target_combo)

        row1.addWidget(QLabel("Window (s):"))
        self.window_spin = QDoubleSpinBox()
        self.window_spin.setDecimals(2); self.window_spin.setRange(0.1, 600.0)
        self.window_spin.setSingleStep(0.5); self.window_spin.setValue(2.0)
        row1.addWidget(self.window_spin)

        row1.addWidget(QLabel("Target level:"))
        self.level_combo = QComboBox()
        self.level_combo.addItem("Event", "event")
        self.level_combo.addItem("Bout (BCI)", "bout")
        row1.addWidget(self.level_combo)
        self.bci_spin = QDoubleSpinBox()
        self.bci_spin.setDecimals(2); self.bci_spin.setRange(0.05, 60.0)
        self.bci_spin.setSingleStep(0.25); self.bci_spin.setValue(1.0)
        self.bci_spin.setPrefix("BCI "); self.bci_spin.setEnabled(False)
        row1.addWidget(self.bci_spin)
        row1.addStretch()
        layout.addLayout(row1)

        body = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("Antecedents:"))
        self.ant_list = _ClickToggleList()
        self.ant_list.setMaximumWidth(210)
        self.ant_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        target0 = self.target_combo.currentText()
        for b in self._behaviors:
            it = QListWidgetItem(b)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked if b == target0 else Qt.CheckState.Checked)
            self.ant_list.addItem(it)
        left.addWidget(self.ant_list)
        body.addLayout(left)

        right = QVBoxLayout()
        chrow = QHBoxLayout()
        self.chance_check = QCheckBox("Chance-correct")
        self.chance_check.setChecked(True)
        chrow.addWidget(self.chance_check)
        chrow.addWidget(QLabel("perms:"))
        self.perm_spin = QSpinBox()
        self.perm_spin.setRange(50, 5000); self.perm_spin.setSingleStep(50); self.perm_spin.setValue(200)
        chrow.addWidget(self.perm_spin)
        self.compute_button = QPushButton("Compute")
        chrow.addWidget(self.compute_button)
        self.progress_label = QLabel("Calculating...")
        self.progress_label.setVisible(False)
        chrow.addWidget(self.progress_label)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(160)
        self.progress.setMaximumHeight(14)
        self.progress.setVisible(False)
        chrow.addWidget(self.progress)
        chrow.addStretch()
        self.copy_button = QPushButton("Copy")
        self.export_button = QPushButton("Export CSV...")
        chrow.addWidget(self.copy_button); chrow.addWidget(self.export_button)
        chrow.addWidget(QLabel("DPI:"))
        self.figure_dpi_spin = QSpinBox()
        self.figure_dpi_spin.setRange(72, 1200)
        self.figure_dpi_spin.setSingleStep(50)
        self.figure_dpi_spin.setValue(300)
        self.figure_dpi_spin.setFixedWidth(80)
        chrow.addWidget(self.figure_dpi_spin)
        self.figure_export_button = QPushButton("Export Figure...")
        chrow.addWidget(self.figure_export_button)
        right.addLayout(chrow)

        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setColumnCount(len(_COLS))
        self.table.setHorizontalHeaderLabels([lbl for _, lbl in _COLS])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        right.addWidget(self.table, 1)
        # Shade the observed (data bar) and above-chance (diverging) columns.
        self._obs_delegate = CellVizDelegate(self).configure("databar", vmin=0.0, scale=1.0)
        self.table.setItemDelegateForColumn(3, self._obs_delegate)
        self._above_delegate = CellVizDelegate(self).configure("diverging", center=0.0, scale=0.3)
        self.table.setItemDelegateForColumn(5, self._above_delegate)

        self.chart = MplChartWidget()
        self.chart.setMinimumHeight(190)
        right.addWidget(self.chart)

        self.lag_label = QLabel("")
        self.lag_label.setWordWrap(True)
        right.addWidget(self.lag_label)
        body.addLayout(right, 1)
        layout.addLayout(body, 1)

        self.level_combo.currentIndexChanged.connect(
            lambda: self.bci_spin.setEnabled(self.level_combo.currentData() == "bout"))
        self.compute_button.clicked.connect(self._recompute)
        self.copy_button.clicked.connect(self._copy)
        self.export_button.clicked.connect(self._export)
        self.figure_export_button.clicked.connect(self._export_figure)

    def _selected_antecedents(self):
        return [self.ant_list.item(i).text() for i in range(self.ant_list.count())
                if self.ant_list.item(i).checkState() == Qt.CheckState.Checked]

    def _recompute(self, *_a):
        target = self.target_combo.currentText()
        antec = self._selected_antecedents()
        window = self.window_spin.value()
        bout = self.level_combo.currentData() == "bout"
        level = "bout" if bout else "event"
        bci = self.bci_spin.value()
        n_perm = self.perm_spin.value() if self.chance_check.isChecked() else 0

        # Progress feedback for the (slower) chance-correction pass, modelled on
        # the Reliability Compute button: a determinate bar + "Calculating..."
        # label, busy cursor, and the Compute button disabled while it runs.
        show_progress = n_perm > 0 and len(self._per_file) > 0
        if show_progress:
            self.progress.setRange(0, len(self._per_file))
            self.progress.setValue(0)
            self.progress.setVisible(True)
            self.progress_label.setVisible(True)
            self.compute_button.setEnabled(False)
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        self._rows = []
        try:
            for idx, (animal_id, events) in enumerate(self._per_file):
                r = antecedent_window_metric(
                    events, target, antec, window, target_level=level, bci=bci,
                    n_perm=n_perm, seed=0)
                r["animal_id"] = animal_id
                r["target"] = target; r["antecedents"] = ", ".join(antec)
                r["window_s"] = window; r["level"] = level
                r["bci_s"] = bci if bout else ""
                self._rows.append(r)
                if self._progress_cb is not None:
                    self._progress_cb(idx + 1, len(self._per_file))
                if show_progress:
                    self.progress.setValue(idx + 1)
                    QApplication.processEvents()
        finally:
            if show_progress:
                self.progress.setVisible(False)
                self.progress_label.setVisible(False)
                self.compute_button.setEnabled(True)
                QApplication.restoreOverrideCursor()
        self._render()

        # Per-animal bar chart: observed (+ chance baseline when corrected).
        cats = [row["animal_id"] for row in self._rows]
        series = {"observed": [row.get("observed", float("nan")) for row in self._rows]}
        if n_perm > 0 and any(
            isinstance(row.get("chance_mean"), float) and not math.isnan(row["chance_mean"])
            for row in self._rows
        ):
            series["chance"] = [row.get("chance_mean", float("nan")) for row in self._rows]
        self.chart.bars(cats, series, title="announced fraction (per animal)",
                        ylabel="fraction",
                        colors={"observed": "#0067C0", "chance": "#BDBDB7"})

        lag = pooled_lag_profile([ev for _, ev in self._per_file], antec, target,
                                 bout_bci=bci if bout else None)
        self.lag_label.setText(
            "Pooled lag profile z (antecedents → target), lag 1–5: "
            + "  ".join(f"L{k}={('–' if (v != v) else f'{v:+.2f}')}" for k, v in enumerate(lag, 1))
        )

    @staticmethod
    def _fmt(v):
        if v is None:
            return ""
        if isinstance(v, float):
            return "–" if math.isnan(v) else f"{v:.3f}"
        return str(v)

    def _render(self):
        self.table.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            for c, (key, _lbl) in enumerate(_COLS):
                v = row.get(key)
                text = str(int(v)) if key in ("n_targets", "n_antecedents") else self._fmt(v)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if key in ("observed", "above_chance") and isinstance(v, float) and not math.isnan(v):
                    item.setData(Qt.ItemDataRole.UserRole, float(v))
                self.table.setItem(r, c, item)

    def _copy(self):
        if not self._rows:
            return
        lines = ["\t".join(lbl for _, lbl in _COLS)]
        for row in self._rows:
            lines.append("\t".join(
                (str(int(row[k])) if k in ("n_targets", "n_antecedents") else self._fmt(row.get(k)))
                for k, _ in _COLS))
        QApplication.clipboard().setText("\n".join(lines))

    def _export(self):
        if not self._rows:
            QMessageBox.information(self, "No Results", "Nothing to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Predictability",
                                              "predictability.csv", "CSV Files (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        fields = ["animal_id", "target", "antecedents", "window_s", "level", "bci_s",
                  "n_targets", "n_antecedents", "observed", "chance_mean", "above_chance"]
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = SafeCsvWriter(csv.writer(fh))
                w.writerow(fields)
                for row in self._rows:
                    w.writerow([self._fmt(row.get(f)) if isinstance(row.get(f), float) else row.get(f, "") for f in fields])
        except OSError as exc:
            QMessageBox.warning(self, "Export Failed", f"Could not write file:\n{exc}")
            return
        QMessageBox.information(self, "Export Complete", f"Exported to:\n{os.path.basename(path)}")

    def _export_figure(self):
        if not self._rows:
            QMessageBox.information(self, "No Figure", "There is no figure to export.")
            return

        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Predictability Figure",
            "predictability.png",
            FIGURE_EXPORT_FILTER,
        )
        if not path:
            return

        try:
            path, file_format = normalise_figure_export_path(path, selected_filter)
            save_matplotlib_figure(
                self.chart.figure,
                path,
                file_format,
                self.figure_dpi_spin.value(),
            )
        except Exception as exc:
            self.logger.error(
                "Failed to export predictability figure: %s",
                exc,
                exc_info=True,
            )
            QMessageBox.warning(self, "Export Failed", f"Could not write figure:\n{exc}")
            return

        show_export_complete(self, path, timeout_ms=1000)
