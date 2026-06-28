# views/transition_analysis_dialog.py - Optional downstream transition analysis.
#
# Behaviour-agnostic, hypothesis-driven first-order transition (sequential)
# analysis. Like bout analysis it runs in its own window, reads the already-
# loaded annotation files, and never touches the standard analysis or export.
# The numeric work lives in the pure, Qt-free ``models.sequence_analysis``.
#
# Methodological note surfaced in the UI: the headline statistic is the
# adjusted residual (chance-corrected), NOT the raw transitional probability,
# and the tool produces per-animal metrics only — "normal/abnormal" judgements
# are the user's, made by comparing groups downstream.

from __future__ import annotations

import csv
import logging
import math
import os
from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget,
)

from models.sequence_analysis import compute_transitions, pool_transitions, tidy_rows
from utils.csv_safety import SafeCsvWriter
from utils.figure_export import (
    FIGURE_EXPORT_FILTER,
    normalise_figure_export_path,
    save_matplotlib_figure,
    show_export_complete,
)

_SIG_Z = 1.96  # |adjusted residual| above this is ~ p < .05


class TransitionAnalysisDialog(QDialog):
    """Per-animal first-order transition matrix with chance-corrected stats.

    Args:
        parent: parent widget.
        per_file: list of ``(animal_id, events)`` where ``events`` is a list of
            ``(behavior, onset, offset)`` tuples (RecordingStart already removed).
        behaviors: behaviour ordering for the matrix (kept constant across
            animals so matrices are comparable).
    """

    def __init__(self, parent, per_file, behaviors, progress_cb=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self._per_file: List[Tuple[str, list]] = per_file or []
        self._events_by_animal = {animal_id: events for animal_id, events in self._per_file}
        self._behaviors = list(behaviors or [])
        self._result = None
        self._progress_cb = progress_cb

        self.setWindowTitle("Transition Analysis")
        self.resize(960, 620)
        self._build_ui()
        self._recompute()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        dialog_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        matrix_tab = QWidget()
        layout = QVBoxLayout(matrix_tab)

        intro = QLabel(
            "First-order transitions (antecedent → consequent). The headline "
            "statistic is the adjusted residual (chance-corrected z), not the "
            "raw probability. Values are per animal — compare groups in your "
            "own statistics. This window is independent of the standard analysis."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        controls = QHBoxLayout()

        controls.addWidget(QLabel("Animal:"))
        self.animal_combo = QComboBox()
        # Default to the all-animals overview, then drill into each individual.
        if len(self._per_file) > 1:
            self.animal_combo.addItem("All animals (pooled)", "__pooled__")
        for animal_id, _events in self._per_file:
            self.animal_combo.addItem(animal_id, animal_id)
        controls.addWidget(self.animal_combo)

        controls.addWidget(QLabel("Level:"))
        self.level_combo = QComboBox()
        self.level_combo.addItem("Event (each event)", "event")
        self.level_combo.addItem("Bout (collapse by BCI)", "bout")
        controls.addWidget(self.level_combo)
        self.bci_spin = QDoubleSpinBox()
        self.bci_spin.setDecimals(2); self.bci_spin.setRange(0.05, 60.0)
        self.bci_spin.setSingleStep(0.25); self.bci_spin.setValue(1.0)
        self.bci_spin.setPrefix("BCI "); self.bci_spin.setEnabled(False)
        self.bci_spin.setToolTip("Collapse each behaviour's events into bouts before counting transitions")
        controls.addWidget(self.bci_spin)

        controls.addWidget(QLabel("Window (s, 0=off):"))
        self.window_spin = QDoubleSpinBox()
        self.window_spin.setDecimals(2)
        self.window_spin.setRange(0.0, 600.0)
        self.window_spin.setSingleStep(0.5)
        self.window_spin.setValue(0.0)
        controls.addWidget(self.window_spin)

        self.exclude_self_check = QCheckBox("Exclude self-transitions")
        controls.addWidget(self.exclude_self_check)

        controls.addWidget(QLabel("Show:"))
        self.metric_combo = QComboBox()
        self.metric_combo.addItem("Adjusted residual (z)", "z")
        self.metric_combo.addItem("Conditional P(j|i)", "p")
        self.metric_combo.addItem("Odds ratio (vs rest)", "or")
        self.metric_combo.addItem("Counts", "n")
        controls.addWidget(self.metric_combo)

        controls.addStretch()
        layout.addLayout(controls)

        self.matrix_table = QTableWidget()
        self.matrix_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.matrix_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        layout.addWidget(self.matrix_table, 1)

        # Target profile: focused "what precedes a chosen behaviour" view.
        prof_row = QHBoxLayout()
        prof_row.addWidget(QLabel("Antecedents of:"))
        self.target_combo = QComboBox()
        self.target_combo.addItems(self._behaviors)
        prof_row.addWidget(self.target_combo)
        prof_row.addStretch()
        layout.addLayout(prof_row)
        self.profile_table = QTableWidget()
        self.profile_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.profile_table.setColumnCount(5)
        self.profile_table.setHorizontalHeaderLabels(
            ["antecedent", "n", "P(target|ant)", "OR", "z"]
        )
        self.profile_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.profile_table.setMaximumHeight(190)
        layout.addWidget(self.profile_table)

        self.legend = QLabel()
        self.legend.setWordWrap(True)
        layout.addWidget(self.legend)

        bottom = QHBoxLayout()
        self.copy_button = QPushButton("Copy Matrix")
        self.export_button = QPushButton("Export Tidy CSV (all animals)...")
        bottom.addWidget(self.copy_button)
        bottom.addWidget(self.export_button)
        bottom.addStretch()
        layout.addLayout(bottom)

        self.tab_widget.addTab(matrix_tab, "Matrix")

        # Shared visual aids (1.4.0): shade the matrix/profile tables by z and
        # add a matplotlib heatmap tab. Colour always encodes the adjusted
        # residual z; the cell text shows whichever metric is selected.
        from views.analysis_charts import MplChartWidget
        from views.viz_delegates import CellVizDelegate
        self._matrix_delegate = CellVizDelegate(self).configure("diverging", center=0.0, scale=8.0)
        self.matrix_table.setItemDelegate(self._matrix_delegate)
        self._profile_z_delegate = CellVizDelegate(self).configure("diverging", center=0.0, scale=8.0)
        self._profile_p_delegate = CellVizDelegate(self).configure("databar", vmin=0.0, scale=1.0)
        self.profile_table.setItemDelegateForColumn(4, self._profile_z_delegate)
        self.profile_table.setItemDelegateForColumn(2, self._profile_p_delegate)
        # Heatmap tab carries its own Animal selector (pooled / each individual),
        # independent of the Matrix tab.
        heatmap_tab = QWidget()
        heatmap_layout = QVBoxLayout(heatmap_tab)
        heatmap_row = QHBoxLayout()
        heatmap_row.addWidget(QLabel("Animal:"))
        self.heatmap_combo = QComboBox()
        if len(self._per_file) > 1:
            self.heatmap_combo.addItem("All animals (pooled)", "__pooled__")
        for animal_id, _events in self._per_file:
            self.heatmap_combo.addItem(animal_id, animal_id)
        self.heatmap_combo.currentIndexChanged.connect(self._render_heatmap)
        heatmap_row.addWidget(self.heatmap_combo)
        heatmap_row.addWidget(QLabel("DPI:"))
        self.heatmap_dpi_spin = QSpinBox()
        self.heatmap_dpi_spin.setRange(72, 1200)
        self.heatmap_dpi_spin.setSingleStep(50)
        self.heatmap_dpi_spin.setValue(300)
        self.heatmap_dpi_spin.setFixedWidth(80)
        heatmap_row.addWidget(self.heatmap_dpi_spin)
        self.heatmap_export_button = QPushButton("Export Figure...")
        heatmap_row.addWidget(self.heatmap_export_button)
        heatmap_row.addStretch()
        heatmap_layout.addLayout(heatmap_row)
        self.heatmap_chart = MplChartWidget()
        heatmap_layout.addWidget(self.heatmap_chart, 1)
        self.tab_widget.addTab(heatmap_tab, "Heatmap")

        from views.predictability_dialog import PredictabilityPanel
        self.pred_panel = PredictabilityPanel(
            self, self._per_file, self._behaviors, progress_cb=self._progress_cb)
        self.tab_widget.addTab(self.pred_panel, "Predictability")
        dialog_layout.addWidget(self.tab_widget, 1)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.reject)
        dialog_layout.addWidget(close_box)

        self.animal_combo.currentIndexChanged.connect(self._recompute)
        self.level_combo.currentIndexChanged.connect(self._on_level_changed)
        self.bci_spin.valueChanged.connect(self._recompute)
        self.window_spin.valueChanged.connect(self._recompute)
        self.exclude_self_check.stateChanged.connect(self._recompute)
        self.metric_combo.currentIndexChanged.connect(self._render_matrix)
        self.target_combo.currentIndexChanged.connect(self._render_profile)
        self.copy_button.clicked.connect(self._copy_matrix)
        self.export_button.clicked.connect(self._export_csv)
        self.heatmap_export_button.clicked.connect(self._export_heatmap_figure)

    # ------------------------------------------------------------------ #
    # Computation
    # ------------------------------------------------------------------ #
    def _current_kwargs(self):
        window = self.window_spin.value()
        bout = self.level_combo.currentData() == "bout"
        return {
            "behaviors": self._behaviors,
            "window": window if window > 0 else None,
            "exclude_self": self.exclude_self_check.isChecked(),
            "bout_bci": self.bci_spin.value() if bout else None,
        }

    def _on_level_changed(self, *_args):
        self.bci_spin.setEnabled(self.level_combo.currentData() == "bout")
        self._recompute()

    def _selected_events(self):
        animal_id = self.animal_combo.currentText()
        return self._events_by_animal.get(animal_id, [])

    def _recompute(self, *_args):
        kwargs = self._current_kwargs()
        if self.animal_combo.currentData() == "__pooled__":
            all_events = [events for _aid, events in self._per_file]
            self._result = pool_transitions(all_events, **kwargs)
        else:
            self._result = compute_transitions(self._selected_events(), **kwargs)
        self._render_matrix()
        self._render_profile()
        self._render_heatmap()

    def _render_heatmap(self, *_args):
        """Draw the heatmap for its own Animal selection (independent of Matrix)."""
        if not hasattr(self, "heatmap_chart") or not self._behaviors:
            return
        kwargs = self._current_kwargs()
        sel = self.heatmap_combo.currentData()
        if sel == "__pooled__":
            result = pool_transitions([ev for _aid, ev in self._per_file], **kwargs)
            label, suffix = "All animals (pooled)", ""
        else:
            result = compute_transitions(self._events_by_animal.get(sel, []), **kwargs)
            label, suffix = self.heatmap_combo.currentText(), " (single animal)"
        self.heatmap_chart.heatmap(
            result.adjusted_residual, self._behaviors, self._behaviors,
            title=f"adjusted residual z — {label}{suffix}", vmax=8.0,
        )

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #
    def _render_matrix(self, *_args):
        result = self._result
        behaviors = self._behaviors
        k = len(behaviors)
        self.matrix_table.setRowCount(k)
        self.matrix_table.setColumnCount(k)
        self.matrix_table.setVerticalHeaderLabels(behaviors)
        self.matrix_table.setHorizontalHeaderLabels(behaviors)

        metric = self.metric_combo.currentData()
        sig_font = QFont()
        sig_font.setBold(True)

        for i in range(k):
            for j in range(k):
                text, significant, undefined = self._cell_text(result, metric, i, j)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if significant:
                    item.setFont(sig_font)
                if result is not None:
                    # Colour always encodes z (chance-corrected) via the shared
                    # delegate; store it in UserRole for the heatmap shading.
                    zval = result.adjusted_residual[i, j]
                    if not (isinstance(zval, float) and math.isnan(zval)):
                        item.setData(Qt.ItemDataRole.UserRole, float(zval))
                    if result.low_count[i, j] and not undefined:
                        item.setToolTip("Antecedent base < 30 — interpret with caution.")
                self.matrix_table.setItem(i, j, item)

        n_trans = result.n_transitions if result is not None else 0
        self.legend.setText(
            f"Transitions: {n_trans}.  Rows = antecedent, columns = consequent.  "
            f"Bold |z| > {_SIG_Z} (≈ p < .05); red = more than chance, blue = less.  "
            "'–' = undefined / structural zero.  Cells from an antecedent seen "
            "< 30 times are flagged (tooltip) as unreliable."
        )

    @staticmethod
    def _cell_text(result, metric, i, j):
        """Return (text, is_significant, is_undefined) for one cell."""
        if result is None:
            return "", False, False
        if metric == "n":
            return str(int(result.counts[i, j])), False, False
        if metric == "p":
            value = result.cond_prob[i, j]
            if value is None or (isinstance(value, float) and math.isnan(value)):
                return "–", False, True
            return f"{value:.2f}", False, False
        if metric == "or":
            orr = result.odds_ratio[i, j]
            if orr is None or (isinstance(orr, float) and math.isnan(orr)):
                return "–", False, True
            z = result.adjusted_residual[i, j]
            sig = (not (isinstance(z, float) and math.isnan(z))) and abs(z) > _SIG_Z
            return ("∞" if orr == math.inf else f"{orr:.2f}"), sig, False
        # adjusted residual
        z = result.adjusted_residual[i, j]
        if z is None or (isinstance(z, float) and math.isnan(z)):
            return "–", False, True
        return f"{z:.2f}", abs(z) > _SIG_Z, False

    def _render_profile(self, *_args):
        """Render the antecedent profile of the selected target behaviour."""
        result = self._result
        if result is None or not self._behaviors:
            return
        t = max(0, self.target_combo.currentIndex())
        self.profile_table.setRowCount(len(self._behaviors))
        for i, ant in enumerate(self._behaviors):
            n = int(result.counts[i, t])
            p = result.cond_prob[i, t]
            orr = result.odds_ratio[i, t]
            z = result.adjusted_residual[i, t]
            vals = [
                ant, str(n),
                "–" if (isinstance(p, float) and math.isnan(p)) else f"{p:.2f}",
                "∞" if orr == math.inf else ("–" if (isinstance(orr, float) and math.isnan(orr)) else f"{orr:.2f}"),
                "–" if (isinstance(z, float) and math.isnan(z)) else f"{z:.2f}",
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter if c == 0
                    else Qt.AlignmentFlag.AlignCenter
                )
                # Values for the shading delegates: z (col 4) and P (col 2).
                if c == 4 and not (isinstance(z, float) and math.isnan(z)):
                    item.setData(Qt.ItemDataRole.UserRole, float(z))
                    if abs(z) > _SIG_Z:
                        f = QFont(); f.setBold(True); item.setFont(f)
                elif c == 2 and not (isinstance(p, float) and math.isnan(p)):
                    item.setData(Qt.ItemDataRole.UserRole, float(p))
                self.profile_table.setItem(i, c, item)

    # ------------------------------------------------------------------ #
    # Output
    # ------------------------------------------------------------------ #
    def _copy_matrix(self):
        if self._result is None:
            return
        behaviors = self._behaviors
        metric = self.metric_combo.currentData()
        lines = ["\t".join([""] + behaviors)]
        for i, antecedent in enumerate(behaviors):
            cells = [self._cell_text(self._result, metric, i, j)[0] for j in range(len(behaviors))]
            lines.append("\t".join([antecedent] + cells))
        QApplication.clipboard().setText("\n".join(lines))

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Transition Analysis", "transition_analysis.csv",
            "CSV Files (*.csv)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        kwargs = self._current_kwargs()
        fieldnames = [
            "animal_id", "antecedent", "consequent", "n", "p_cond",
            "expected", "adj_residual", "odds_ratio", "flag", "level",
            "bci_s", "mode", "window_s",
        ]
        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = SafeCsvWriter(csv.writer(handle))
                writer.writerow(fieldnames)
                for animal_id, events in self._per_file:
                    result = compute_transitions(events, **kwargs)
                    for row in tidy_rows(result, animal_id=animal_id):
                        writer.writerow([self._fmt(row[name]) for name in fieldnames])
                if len(self._per_file) > 1:
                    pooled = pool_transitions(
                        [events for _aid, events in self._per_file], **kwargs)
                    for row in tidy_rows(pooled, animal_id="ALL (pooled)"):
                        writer.writerow([self._fmt(row[name]) for name in fieldnames])
        except OSError as exc:
            QMessageBox.warning(self, "Export Failed", f"Could not write file:\n{exc}")
            return
        QMessageBox.information(
            self, "Export Complete",
            f"Transition analysis (all animals) exported to:\n{os.path.basename(path)}",
        )

    def _export_heatmap_figure(self):
        if not hasattr(self, "heatmap_chart") or not self._behaviors:
            QMessageBox.information(self, "No Figure", "There is no heatmap figure to export.")
            return

        self._render_heatmap()
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Transition Heatmap",
            "transition_heatmap.png",
            FIGURE_EXPORT_FILTER,
        )
        if not path:
            return

        try:
            path, file_format = normalise_figure_export_path(path, selected_filter)
            save_matplotlib_figure(
                self.heatmap_chart.figure,
                path,
                file_format,
                self.heatmap_dpi_spin.value(),
            )
        except Exception as exc:
            self.logger.error("Failed to export transition heatmap: %s", exc, exc_info=True)
            QMessageBox.warning(self, "Export Failed", f"Could not write figure:\n{exc}")
            return

        show_export_complete(self, path, timeout_ms=1000)

    @staticmethod
    def _fmt(value):
        if value is None:
            return ""
        if isinstance(value, float):
            if math.isnan(value):
                return ""
            return f"{value:.4f}"
        return str(value)
