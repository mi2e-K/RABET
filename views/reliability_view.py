# views/reliability_view.py - Inter-rater / intra-rater reliability tab
"""
ReliabilityView - the Qt widget for the Reliability tab.

Two sub-tabs:

* **Summary mode** - load two ``summary_table.csv`` files, match by
  ``animal_id``, show per-metric agreement (ICC(2,1), Pearson r, mean
  absolute difference) plus per-metric scatter plots.

* **Detailed mode** - load two annotation CSVs, choose a bin width,
  compute Cohen's kappa, Krippendorff's alpha, raw percentage
  agreement; the right-hand panel renders the pairwise event raster
  overlay so disagreement segments are visible at a glance.

Both sub-tabs support exporting the results table as CSV.
"""

from __future__ import annotations

import csv
import logging
import os
import re
from typing import Optional

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFileDialog, QTabWidget, QGroupBox, QFormLayout, QDoubleSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QSplitter,
    QMessageBox, QSizePolicy, QRadioButton, QButtonGroup, QProgressBar,
    QApplication, QDialog, QDialogButtonBox, QListWidget, QListWidgetItem,
)

logger = logging.getLogger(__name__)


# Thresholds used to colour-code agreement values.
# - ICC(2,1): Cicchetti (1994) "Guidelines, criteria, and rules of thumb..."
#   classifies <0.40 as poor, 0.40-0.59 fair, 0.60-0.74 good, >=0.75
#   excellent. We collapse this into a three-band scheme:
#     >= 0.75 green (excellent), 0.50-0.75 amber (moderate), <0.50 red.
# - Cohen's kappa: Landis & Koch (1977) lay out six bands, commonly
#   condensed to three: >= 0.70 substantial/almost-perfect (green),
#   0.40-0.70 moderate (amber), < 0.40 poor (red).
_ICC_GOOD = 0.75
_ICC_MODERATE = 0.50
_KAPPA_GOOD = 0.70
_KAPPA_MODERATE = 0.40

# Color palette tuned for color-universal design (CUD) so the
# green/amber/red distinction is readable for the common red-green
# colour-vision-deficient phenotype as well.
_OK_COLOR = "#77d9a8"        # green - acceptable agreement
_CAUTION_COLOR = "#ffca80"   # warm amber - moderate, inspect carefully
_WARN_COLOR = "#ff4b00"      # orange-red - below acceptance threshold
_NEUTRAL_COLOR = "#000000"
# Highlight color for Pearson r ≥ 0.9 - distinct gold so an
# exceptionally strong correlation reads at a glance.
_HIGHLIGHT_COLOR = "#f6aa00"
_STATUS_TEXT_COLOR = "#8a8a8a"  # secondary-grey for status labels

# ----------------------------------------------------------------- #
# Progress-bar styles. Pick ONE by binding it to _PROGRESS_BAR_QSS.
# Default is the "Solid cyan" look (#00E5FF).
# To preview a different style, comment out the active assignment
# below and uncomment one of the alternatives.
# ----------------------------------------------------------------- #

# --- Style A: Solid cyan (current default) ---
_PROGRESS_BAR_STYLE_SOLID = """
QProgressBar {
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    border-radius: 4px;
}
QProgressBar::chunk {
    background-color: #00E5FF;
    border-radius: 3px;
}
"""

# --- Style B: Cyan-to-blue horizontal gradient ---
_PROGRESS_BAR_STYLE_GRADIENT = """
QProgressBar {
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    border-radius: 4px;
}
QProgressBar::chunk {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #00E5FF, stop:1 #2962FF
    );
    border-radius: 3px;
}
"""

# --- Style C: Ultra-thin minimalist (4px tall, no rounded corners) ---
_PROGRESS_BAR_STYLE_THIN = """
QProgressBar {
    background-color: #2a2a2a;
    border: none;
    max-height: 4px;
    min-height: 4px;
}
QProgressBar::chunk {
    background-color: #00E5FF;
}
"""

# --- Style D: Translucent capsule with subtle inner glow ---
_PROGRESS_BAR_STYLE_CAPSULE = """
QProgressBar {
    background-color: rgba(255, 255, 255, 25);
    border: 1px solid rgba(0, 229, 255, 60);
    border-radius: 8px;
}
QProgressBar::chunk {
    background-color: rgba(0, 229, 255, 200);
    border-radius: 6px;
    margin: 1px;
}
"""

# --- Style E: Striped (matches macOS indeterminate look) ---
_PROGRESS_BAR_STYLE_STRIPED = """
QProgressBar {
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    border-radius: 4px;
}
QProgressBar::chunk {
    background: qlineargradient(
        x1:0, y1:0, x2:0.06, y2:0.5, spread:repeat,
        stop:0    #00E5FF,
        stop:0.5  #00E5FF,
        stop:0.5  rgba(0, 229, 255, 90),
        stop:1    rgba(0, 229, 255, 90)
    );
    border-radius: 3px;
}
"""

# Active style. Swap this line to try one of the alternatives above.
_PROGRESS_BAR_QSS = _PROGRESS_BAR_STYLE_SOLID



def _icc_color(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    if value >= _ICC_GOOD:
        return _OK_COLOR
    if value >= _ICC_MODERATE:
        return _CAUTION_COLOR
    return _WARN_COLOR


def _kappa_color(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    if value >= _KAPPA_GOOD:
        return _OK_COLOR
    if value >= _KAPPA_MODERATE:
        return _CAUTION_COLOR
    return _WARN_COLOR


def _pearson_color(value: Optional[float]) -> Optional[str]:
    """Two-step highlight for Pearson r: green at >= 0.80, gold at >= 0.90."""
    if value is None:
        return None
    if value >= 0.90:
        return _HIGHLIGHT_COLOR
    if value >= 0.80:
        return _OK_COLOR
    return None


def _format_value(value: Optional[float], digits: int = 3) -> str:
    if value is None:
        return "—"
    try:
        return f"{value:.{digits}f}"
    except (TypeError, ValueError):
        return "—"


# -------------------------------------------------------------------- #
# Generic file-picker row used by both sub-tabs
# -------------------------------------------------------------------- #


class _FilePickerRow(QWidget):
    """A label + QLineEdit + Browse button. Emits ``path_changed`` when
    the path is updated. Remembers the last directory the user picked
    so subsequent Browse clicks open there. The controller can also seed
    the initial directory via :meth:`set_initial_dir` to restore a
    persisted directory across sessions."""
    path_changed = Signal(str)

    def __init__(
        self,
        label: str,
        file_dialog_title: str,
        file_filter: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._dialog_title = file_dialog_title
        self._file_filter = file_filter
        # In-memory remembered directory. Seeded by set_initial_dir from
        # ConfigManager, updated on every successful Browse.
        self._initial_dir: str = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.label = QLabel(label)
        self.label.setMinimumWidth(110)
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("Click Browse to select a file...")
        self.browse_button = QPushButton("Browse...")

        layout.addWidget(self.label)
        layout.addWidget(self.path_edit, 1)
        layout.addWidget(self.browse_button)

        self.browse_button.clicked.connect(self._on_browse_clicked)

    def _on_browse_clicked(self) -> None:
        # Open at the most recently used directory, falling back to the
        # caller-supplied seed and then to the OS default.
        start_dir = self._initial_dir if self._initial_dir and os.path.isdir(self._initial_dir) else ""
        path, _ = QFileDialog.getOpenFileName(
            self, self._dialog_title, start_dir, self._file_filter
        )
        if path:
            # Remember the parent directory for the next browse and the
            # next session (the controller listens to path_changed and
            # persists this through ConfigManager).
            self._initial_dir = os.path.dirname(path)
            self.set_path(path)

    def set_path(self, path: str) -> None:
        self.path_edit.setText(path)
        self.path_changed.emit(path)

    def set_initial_dir(self, directory: str) -> None:
        """Seed the directory used by the next Browse click."""
        if directory and os.path.isdir(directory):
            self._initial_dir = directory

    def set_label_text(self, text: str) -> None:
        """Update the row's leading label (used to swap between
        ``Scorer A:`` / ``Session 1:`` etc. when the inter/intra-rater
        radio is toggled)."""
        self.label.setText(text)

    def set_dialog_title(self, title: str) -> None:
        """Update the file-dialog title shown by the next Browse click.

        Paired with :meth:`set_label_text` so the Reliability tab can
        keep the picker label *and* the dialog header in sync when the
        Inter/Intra-rater radio toggles.
        """
        self._dialog_title = title

    def path(self) -> str:
        return self.path_edit.text().strip()


class SummaryMatchDialog(QDialog):
    """Resolve leftover Summary-mode animal_id matches."""

    def __init__(self, auto_pairs, unmatched_a, unmatched_b, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Match animal IDs")
        self.resize(860, 560)
        self._auto_pairs = list(auto_pairs or [])
        self._manual_pairs: list[tuple[str, str]] = []
        self._auto_a = {pair.animal_id_a for pair in self._auto_pairs}
        self._auto_b = {pair.animal_id_b for pair in self._auto_pairs}
        self._all_a = set(unmatched_a or []) | self._auto_a
        self._all_b = set(unmatched_b or []) | self._auto_b
        self._excluded_a: set[str] = set()
        self._excluded_b: set[str] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        note = QLabel(
            "Automatic matching left some animal IDs unmatched. Add any "
            "remaining pairs below, or press OK to continue with unmatched "
            "IDs excluded."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {_STATUS_TEXT_COLOR};")
        layout.addWidget(note)

        self.auto_table = QTableWidget(0, 4)
        self.auto_table.setHorizontalHeaderLabels(
            ["Match ID", "Summary A", "Summary B", "Source"]
        )
        self.auto_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.auto_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.auto_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._populate_auto_table()
        layout.addWidget(QLabel("Automatic matches"))
        layout.addWidget(self.auto_table, 1)

        manual_row = QHBoxLayout()
        left_col = QVBoxLayout()
        left_col.addWidget(QLabel("Unmatched A"))
        self.list_a = QListWidget()
        self.list_a.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._populate_list(self.list_a, unmatched_a or [])
        left_col.addWidget(self.list_a)
        self.exclude_a_button = QPushButton("Exclude Selected")
        self.exclude_a_button.clicked.connect(lambda: self._exclude_selected(self.list_a, "A"))
        left_col.addWidget(self.exclude_a_button)
        manual_row.addLayout(left_col, 1)

        middle_col = QVBoxLayout()
        middle_col.addStretch()
        self.add_pair_button = QPushButton("Add Pair")
        self.add_pair_button.clicked.connect(self._add_selected_pair)
        middle_col.addWidget(self.add_pair_button)
        self.pair_sorted_button = QPushButton("Pair Sorted")
        self.pair_sorted_button.clicked.connect(self._pair_sorted)
        middle_col.addWidget(self.pair_sorted_button)
        middle_col.addStretch()
        manual_row.addLayout(middle_col)

        right_col = QVBoxLayout()
        right_col.addWidget(QLabel("Unmatched B"))
        self.list_b = QListWidget()
        self.list_b.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._populate_list(self.list_b, unmatched_b or [])
        right_col.addWidget(self.list_b)
        self.exclude_b_button = QPushButton("Exclude Selected")
        self.exclude_b_button.clicked.connect(lambda: self._exclude_selected(self.list_b, "B"))
        right_col.addWidget(self.exclude_b_button)
        manual_row.addLayout(right_col, 1)
        layout.addLayout(manual_row, 2)

        self.manual_table = QTableWidget(0, 2)
        self.manual_table.setHorizontalHeaderLabels(["Summary A", "Summary B"])
        self.manual_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.manual_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.manual_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        layout.addWidget(QLabel("Manual matches"))
        layout.addWidget(self.manual_table, 1)

        action_row = QHBoxLayout()
        self.remove_pair_button = QPushButton("Remove Selected")
        self.remove_pair_button.clicked.connect(self._remove_selected_pairs)
        self.load_button = QPushButton("Load Map...")
        self.load_button.clicked.connect(self._load_map)
        self.save_button = QPushButton("Save Map...")
        self.save_button.clicked.connect(self._save_map)
        action_row.addWidget(self.remove_pair_button)
        action_row.addStretch()
        action_row.addWidget(self.load_button)
        action_row.addWidget(self.save_button)
        layout.addLayout(action_row)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def manual_pairs(self) -> list[tuple[str, str]]:
        return list(self._manual_pairs)

    def all_pairs(self) -> list[tuple[str, str]]:
        pairs = [
            (pair.animal_id_a, pair.animal_id_b)
            for pair in self._auto_pairs
        ]
        pairs.extend(self._manual_pairs)
        return pairs

    @staticmethod
    def _natural_sort_key(value: str) -> tuple:
        parts: list[tuple[int, object]] = []
        for part in re.split(r"(\d+)", str(value)):
            if not part:
                continue
            if part.isdigit():
                parts.append((0, int(part)))
            else:
                parts.append((1, part.casefold()))
        return tuple(parts)

    def _populate_auto_table(self) -> None:
        self.auto_table.setRowCount(len(self._auto_pairs))
        for row, pair in enumerate(self._auto_pairs):
            for col, value in enumerate(
                [pair.match_id, pair.animal_id_a, pair.animal_id_b, pair.source]
            ):
                self.auto_table.setItem(row, col, QTableWidgetItem(str(value)))

    def _populate_list(self, widget: QListWidget, values) -> None:
        widget.clear()
        for value in sorted((str(v) for v in values), key=self._natural_sort_key):
            widget.addItem(QListWidgetItem(value))

    def _list_values(self, widget: QListWidget) -> list[str]:
        return [widget.item(i).text() for i in range(widget.count())]

    def _selected_list_values(self, widget: QListWidget) -> list[str]:
        return [item.text() for item in widget.selectedItems()]

    def _take_list_value(self, widget: QListWidget, value: str) -> None:
        for index in range(widget.count()):
            if widget.item(index).text() == value:
                widget.takeItem(index)
                return

    def _add_list_value(self, widget: QListWidget, value: str) -> None:
        values = set(self._list_values(widget))
        values.add(value)
        self._populate_list(widget, values)

    def _exclude_selected(self, widget: QListWidget, side: str) -> None:
        values = self._selected_list_values(widget)
        if not values:
            QMessageBox.information(
                self, "Reliability",
                f"Select one or more unmatched {side} item(s) first.",
            )
            return
        excluded = self._excluded_a if side == "A" else self._excluded_b
        for value in values:
            excluded.add(value)
            self._take_list_value(widget, value)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            focused = self.focusWidget()
            if focused is self.list_a:
                self._exclude_selected(self.list_a, "A")
                return
            if focused is self.list_b:
                self._exclude_selected(self.list_b, "B")
                return
        super().keyPressEvent(event)

    def _add_selected_pair(self) -> None:
        item_a = self.list_a.currentItem()
        item_b = self.list_b.currentItem()
        if item_a is None or item_b is None:
            QMessageBox.information(
                self, "Reliability",
                "Select one animal_id from each unmatched list first.",
            )
            return
        self._add_manual_pair(item_a.text(), item_b.text(), show_errors=True)

    def _pair_sorted(self) -> None:
        values_a = sorted(self._list_values(self.list_a), key=self._natural_sort_key)
        values_b = sorted(self._list_values(self.list_b), key=self._natural_sort_key)
        if not values_a or not values_b:
            QMessageBox.information(
                self, "Reliability",
                "There are no remaining unmatched IDs to pair.",
            )
            return
        if len(values_a) != len(values_b):
            QMessageBox.warning(
                self, "Reliability",
                "The unmatched A/B counts are different. Exclude extra IDs "
                "first, then run Pair Sorted again.",
            )
            return

        added = 0
        for animal_id_a, animal_id_b in zip(values_a, values_b, strict=False):
            if self._add_manual_pair(animal_id_a, animal_id_b, show_errors=False):
                added += 1
        QMessageBox.information(
            self, "Reliability",
            f"Added {added} sorted match pair(s).",
        )

    def _add_manual_pair(
        self, animal_id_a: str, animal_id_b: str, show_errors: bool
    ) -> bool:
        try:
            self._validate_new_pair(animal_id_a, animal_id_b)
        except ValueError as exc:
            if show_errors:
                QMessageBox.warning(self, "Reliability", str(exc))
            return False

        self._manual_pairs.append((animal_id_a, animal_id_b))
        self._take_list_value(self.list_a, animal_id_a)
        self._take_list_value(self.list_b, animal_id_b)
        self._refresh_manual_table()
        return True

    def _validate_new_pair(self, animal_id_a: str, animal_id_b: str) -> None:
        if not animal_id_a or not animal_id_b:
            raise ValueError("animal_id values cannot be empty.")
        if animal_id_a not in self._all_a:
            raise ValueError(f"'{animal_id_a}' is not in summary A.")
        if animal_id_b not in self._all_b:
            raise ValueError(f"'{animal_id_b}' is not in summary B.")
        if animal_id_a in self._excluded_a:
            raise ValueError(f"'{animal_id_a}' is excluded from matching.")
        if animal_id_b in self._excluded_b:
            raise ValueError(f"'{animal_id_b}' is excluded from matching.")
        existing = dict(self.all_pairs())
        reverse = {b: a for a, b in self.all_pairs()}
        if animal_id_a in existing:
            if existing[animal_id_a] == animal_id_b:
                raise ValueError(
                    f"'{animal_id_a}' and '{animal_id_b}' are already matched."
                )
            raise ValueError(f"'{animal_id_a}' is already matched.")
        if animal_id_b in reverse:
            raise ValueError(f"'{animal_id_b}' is already matched.")

    def _refresh_manual_table(self) -> None:
        self.manual_table.setRowCount(len(self._manual_pairs))
        for row, (animal_id_a, animal_id_b) in enumerate(self._manual_pairs):
            self.manual_table.setItem(row, 0, QTableWidgetItem(animal_id_a))
            self.manual_table.setItem(row, 1, QTableWidgetItem(animal_id_b))

    def _remove_selected_pairs(self) -> None:
        selected_rows = sorted(
            {index.row() for index in self.manual_table.selectedIndexes()},
            reverse=True,
        )
        for row in selected_rows:
            animal_id_a, animal_id_b = self._manual_pairs.pop(row)
            self._add_list_value(self.list_a, animal_id_a)
            self._add_list_value(self.list_b, animal_id_b)
        self._refresh_manual_table()

    @staticmethod
    def _read_map_csv(path: str) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            first_data_seen = False
            for row_num, row in enumerate(reader, start=1):
                cells = [cell.strip() for cell in row]
                if not any(cells):
                    continue
                if len(cells) < 2:
                    raise ValueError(
                        f"Row {row_num} must have animal_id_a and animal_id_b."
                    )
                animal_id_a, animal_id_b = cells[0], cells[1]
                if not first_data_seen:
                    first_data_seen = True
                    if (
                        animal_id_a.casefold() == "animal_id_a"
                        and animal_id_b.casefold() == "animal_id_b"
                    ):
                        continue
                if not animal_id_a or not animal_id_b:
                    raise ValueError(f"Row {row_num} has an empty animal_id.")
                pairs.append((animal_id_a, animal_id_b))
        return pairs

    def _load_map(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load animal_id match map",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        try:
            pairs = self._read_map_csv(path)
            added = 0
            for animal_id_a, animal_id_b in pairs:
                if (animal_id_a, animal_id_b) in self.all_pairs():
                    continue
                self._validate_new_pair(animal_id_a, animal_id_b)
                if self._add_manual_pair(animal_id_a, animal_id_b, show_errors=False):
                    added += 1
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Reliability", f"Could not load map:\n{exc}")
            return
        QMessageBox.information(
            self, "Reliability",
            f"Loaded {added} manual match pair(s).",
        )

    def _save_map(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save animal_id match map",
            "animal_id_match_map.csv",
            "CSV files (*.csv)",
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(["animal_id_a", "animal_id_b"])
                writer.writerows(self.all_pairs())
        except OSError as exc:
            QMessageBox.warning(self, "Reliability", f"Could not save map:\n{exc}")
            return
        QMessageBox.information(
            self, "Reliability",
            f"Match map saved to:\n{path}",
        )


# -------------------------------------------------------------------- #
# ReliabilityView
# -------------------------------------------------------------------- #


class ReliabilityView(QWidget):
    """Top-level widget for the Reliability tab."""

    # Mode 1
    compute_summary_requested = Signal(str, str)  # path_a, path_b
    export_summary_requested = Signal()

    # Mode 2
    compute_detailed_requested = Signal(str, str, float)  # path_a, path_b, bin
    export_detailed_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self._summary_result = None
        self._detailed_result = None
        # Detailed-mode labels override what the model recorded inside the
        # DetailedAgreementResult - the model is mode-agnostic, so we let
        # the radio buttons drive the legend wording.
        self._detailed_labels: tuple[str, str] = ("Scorer A", "Scorer B")
        self._setup_ui()
        self._connect_signals()

    # ---------------- UI construction ---------------- #

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QLabel("Reliability Assessment")
        header.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(header)

        explanation = QLabel(
            "Compare two RABET outputs to estimate inter-rater agreement "
            "(two scorers on the same animals) or intra-rater consistency "
            "(one scorer rescoring the same animals after a gap)."
        )
        explanation.setWordWrap(True)
        explanation.setStyleSheet("font-size: 14px; color: #8a8a8a;")
        layout.addWidget(explanation)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_summary_tab(), "Summary mode  (frequency / duration ICC)")
        self.tabs.addTab(self._build_detailed_tab(), "Detailed mode  (moment-to-moment κ / α)")
        layout.addWidget(self.tabs, 1)

    def _build_summary_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setSpacing(6)

        input_box = QGroupBox("Input files")
        input_layout = QVBoxLayout(input_box)

        self.summary_picker_a = _FilePickerRow(
            "Scorer A summary:", "Select scorer A's summary table CSV",
            "CSV files (*.csv);;All files (*)",
        )
        self.summary_picker_b = _FilePickerRow(
            "Scorer B summary:", "Select scorer B's summary table CSV",
            "CSV files (*.csv);;All files (*)",
        )
        input_layout.addWidget(self.summary_picker_a)
        input_layout.addWidget(self.summary_picker_b)

        # Compute / Export buttons share a row with the inter/intra-rater
        # mode picker. The radios only relabel the file pickers - the
        # actual ICC / Pearson / MAD computation is identical for both
        # modes.
        button_row = QHBoxLayout()
        self.summary_compute_btn = QPushButton("🚀 Compute agreement")
        self.summary_export_btn = QPushButton("Export results...")
        self.summary_export_btn.setEnabled(False)
        button_row.addWidget(self.summary_compute_btn)
        button_row.addWidget(self.summary_export_btn)
        # Mode picker sits immediately to the right of the buttons.
        button_row.addSpacing(20)
        button_row.addWidget(QLabel("Mode:"))
        self.summary_inter_radio = QRadioButton("Inter-rater")
        self.summary_intra_radio = QRadioButton("Intra-rater")
        self.summary_inter_radio.setChecked(True)
        self.summary_inter_radio.setToolTip(
            "Two different scorers on the same animals."
        )
        self.summary_intra_radio.setToolTip(
            "One scorer rescoring the same animals (test-retest)."
        )
        self._summary_mode_group = QButtonGroup(self)
        self._summary_mode_group.addButton(self.summary_inter_radio)
        self._summary_mode_group.addButton(self.summary_intra_radio)
        button_row.addWidget(self.summary_inter_radio)
        button_row.addWidget(self.summary_intra_radio)
        button_row.addStretch()
        # "Calculating..." label + indeterminate progress bar, shown
        # only while pingouin is working through every metric. Both are
        # hidden by default.
        self.summary_progress_label = QLabel("Calculating...")
        self.summary_progress_label.setStyleSheet("color: white;")
        self.summary_progress_label.setVisible(False)
        button_row.addWidget(self.summary_progress_label)
        self.summary_progress = QProgressBar()
        self.summary_progress.setRange(0, 0)
        self.summary_progress.setMaximumWidth(160)
        self.summary_progress.setMaximumHeight(14)
        self.summary_progress.setTextVisible(False)
        self.summary_progress.setStyleSheet(_PROGRESS_BAR_QSS)
        self.summary_progress.setVisible(False)
        button_row.addWidget(self.summary_progress)
        input_layout.addLayout(button_row)
        outer.addWidget(input_box)

        # Splitter: results table on the left, scatter plot on the right.
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.summary_status = QLabel("")
        self.summary_status.setWordWrap(True)
        self.summary_status.setStyleSheet(f"color: {_STATUS_TEXT_COLOR};")
        left_layout.addWidget(self.summary_status)

        self.summary_table = QTableWidget(0, 6)
        self.summary_table.setHorizontalHeaderLabels(
            ["Metric", "n", "ICC(2,1)", "Pearson r", "Mean|A−B|", "Mean A / B"]
        )
        header = self.summary_table.horizontalHeader()
        # Metric column is wide and user-resizable, the rest stretch to
        # fill what's left. n is forced narrow because it only ever
        # holds a small integer.
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.summary_table.setColumnWidth(0, 280)
        self.summary_table.setColumnWidth(1, 50)
        self.summary_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        # Make all cells non-editable at the table level so individual
        # items do not need their ItemIsEditable flag masked off.
        self.summary_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        left_layout.addWidget(self.summary_table, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        scatter_controls = QHBoxLayout()
        scatter_controls.addWidget(QLabel("Scatter for metric:"))
        self.summary_scatter_picker = QComboBox()
        self.summary_scatter_picker.setMinimumWidth(220)
        scatter_controls.addWidget(self.summary_scatter_picker, 1)
        right_layout.addLayout(scatter_controls)

        # NOTE (1.3.2 / C2): We deliberately keep the Figure / Canvas
        # alive across view switches. _draw_summary_scatter calls
        # ``self.summary_figure.clear()`` before each redraw, so the
        # peak resource use is bounded; explicit Figure teardown was
        # considered but the user-visible benefit of keeping the last
        # result on screen when navigating away outweighs the small
        # memory saving. Revisit if profiling shows accumulation.
        self.summary_figure = Figure(figsize=(4, 4))
        self.summary_canvas = FigureCanvas(self.summary_figure)
        self.summary_canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        right_layout.addWidget(self.summary_canvas, 1)
        splitter.addWidget(right)
        splitter.setSizes([520, 380])

        outer.addWidget(splitter, 1)
        return page

    def _build_detailed_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setSpacing(6)

        input_box = QGroupBox("Input files")
        input_layout = QVBoxLayout(input_box)

        self.detailed_picker_a = _FilePickerRow(
            "Scorer A CSV:", "Select scorer A's annotation CSV",
            "CSV files (*.csv);;All files (*)",
        )
        self.detailed_picker_b = _FilePickerRow(
            "Scorer B CSV:", "Select scorer B's annotation CSV",
            "CSV files (*.csv);;All files (*)",
        )
        input_layout.addWidget(self.detailed_picker_a)
        input_layout.addWidget(self.detailed_picker_b)

        form = QFormLayout()
        self.detailed_bin_spin = QDoubleSpinBox()
        self.detailed_bin_spin.setRange(0.05, 60.0)
        self.detailed_bin_spin.setSingleStep(0.5)
        self.detailed_bin_spin.setValue(1.0)
        self.detailed_bin_spin.setSuffix(" s")
        self.detailed_bin_spin.setDecimals(2)
        form.addRow("Bin width:", self.detailed_bin_spin)
        input_layout.addLayout(form)

        button_row = QHBoxLayout()
        self.detailed_compute_btn = QPushButton("🚀 Compute agreement")
        self.detailed_export_btn = QPushButton("Export results...")
        self.detailed_export_btn.setEnabled(False)
        button_row.addWidget(self.detailed_compute_btn)
        button_row.addWidget(self.detailed_export_btn)
        button_row.addSpacing(20)
        button_row.addWidget(QLabel("Mode:"))
        self.detailed_inter_radio = QRadioButton("Inter-rater")
        self.detailed_intra_radio = QRadioButton("Intra-rater")
        self.detailed_inter_radio.setChecked(True)
        self.detailed_inter_radio.setToolTip(
            "Two different scorers on the same video."
        )
        self.detailed_intra_radio.setToolTip(
            "One scorer rescoring the same video (test-retest)."
        )
        self._detailed_mode_group = QButtonGroup(self)
        self._detailed_mode_group.addButton(self.detailed_inter_radio)
        self._detailed_mode_group.addButton(self.detailed_intra_radio)
        button_row.addWidget(self.detailed_inter_radio)
        button_row.addWidget(self.detailed_intra_radio)
        button_row.addStretch()
        self.detailed_progress_label = QLabel("Calculating...")
        self.detailed_progress_label.setStyleSheet("color: white;")
        self.detailed_progress_label.setVisible(False)
        button_row.addWidget(self.detailed_progress_label)
        self.detailed_progress = QProgressBar()
        self.detailed_progress.setRange(0, 0)
        self.detailed_progress.setMaximumWidth(160)
        self.detailed_progress.setMaximumHeight(14)
        self.detailed_progress.setTextVisible(False)
        self.detailed_progress.setStyleSheet(_PROGRESS_BAR_QSS)
        self.detailed_progress.setVisible(False)
        button_row.addWidget(self.detailed_progress)
        input_layout.addLayout(button_row)
        outer.addWidget(input_box)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.detailed_status = QLabel("")
        self.detailed_status.setWordWrap(True)
        self.detailed_status.setStyleSheet(f"color: {_STATUS_TEXT_COLOR};")
        left_layout.addWidget(self.detailed_status)

        self.detailed_table = QTableWidget(0, 6)
        self.detailed_table.setHorizontalHeaderLabels(
            ["Behaviour", "Bins", "Active A", "Active B",
             "Cohen κ", "Krippendorff α"]
        )
        self.detailed_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.detailed_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        self.detailed_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.detailed_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        left_layout.addWidget(self.detailed_table, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Pairwise raster overlay:"))

        self.detailed_figure = Figure(figsize=(4, 4))
        self.detailed_canvas = FigureCanvas(self.detailed_figure)
        self.detailed_canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        right_layout.addWidget(self.detailed_canvas, 1)
        splitter.addWidget(right)
        splitter.setSizes([520, 480])

        outer.addWidget(splitter, 1)
        return page

    def _connect_signals(self) -> None:
        self.summary_compute_btn.clicked.connect(self._on_compute_summary_clicked)
        self.summary_export_btn.clicked.connect(self.export_summary_requested.emit)
        self.summary_scatter_picker.currentIndexChanged.connect(
            self._on_summary_scatter_changed
        )
        self.detailed_compute_btn.clicked.connect(self._on_compute_detailed_clicked)
        self.detailed_export_btn.clicked.connect(self.export_detailed_requested.emit)

        # Inter/Intra-rater mode toggles only swap picker labels - the
        # computation itself is identical for both modes.
        self.summary_inter_radio.toggled.connect(self._on_summary_mode_toggled)
        self.detailed_inter_radio.toggled.connect(self._on_detailed_mode_toggled)
        # Initialise labels to the default (Inter-rater).
        self._on_summary_mode_toggled(True)
        self._on_detailed_mode_toggled(True)

    # ---------------- Mode toggle handlers ---------------- #

    def _on_summary_mode_toggled(self, inter_checked: bool) -> None:
        # 1.3.3+: sync the file-dialog title too. Previously the picker
        # label flipped between "Scorer A summary:" and "Session 1
        # summary:" but the Browse dialog header stayed on the inter-
        # rater wording even in intra-rater mode.
        if inter_checked:
            self.summary_picker_a.set_label_text("Scorer A summary:")
            self.summary_picker_b.set_label_text("Scorer B summary:")
            self.summary_picker_a.set_dialog_title(
                "Select scorer A's summary table CSV"
            )
            self.summary_picker_b.set_dialog_title(
                "Select scorer B's summary table CSV"
            )
        else:
            self.summary_picker_a.set_label_text("Session 1 summary:")
            self.summary_picker_b.set_label_text("Session 2 summary:")
            self.summary_picker_a.set_dialog_title(
                "Select session 1 summary table CSV"
            )
            self.summary_picker_b.set_dialog_title(
                "Select session 2 summary table CSV"
            )

    def _on_detailed_mode_toggled(self, inter_checked: bool) -> None:
        if inter_checked:
            self.detailed_picker_a.set_label_text("Scorer A CSV:")
            self.detailed_picker_b.set_label_text("Scorer B CSV:")
            self.detailed_picker_a.set_dialog_title(
                "Select scorer A's annotation CSV"
            )
            self.detailed_picker_b.set_dialog_title(
                "Select scorer B's annotation CSV"
            )
        else:
            self.detailed_picker_a.set_label_text("Session 1 CSV:")
            self.detailed_picker_b.set_label_text("Session 2 CSV:")
            self.detailed_picker_a.set_dialog_title(
                "Select session 1 annotation CSV"
            )
            self.detailed_picker_b.set_dialog_title(
                "Select session 2 annotation CSV"
            )

    # ---------------- Slots / event handlers ---------------- #

    def _on_compute_summary_clicked(self) -> None:
        path_a = self.summary_picker_a.path()
        path_b = self.summary_picker_b.path()
        if not path_a or not path_b:
            QMessageBox.information(
                self, "Reliability",
                "Please select both summary table CSV files first."
            )
            return
        if not os.path.isfile(path_a) or not os.path.isfile(path_b):
            QMessageBox.warning(
                self, "Reliability",
                "One or both selected files cannot be found."
            )
            return
        self.summary_status.setText("Computing agreement...")
        # Lock the button so a double-click cannot trigger a duplicate
        # computation. show_summary_results / show_error re-enable it.
        self.summary_compute_btn.setEnabled(False)
        self.summary_progress_label.setVisible(True)
        self.summary_progress.setVisible(True)
        # Force the status + progress bar to repaint before pingouin
        # blocks the event loop. Without this the user would see the
        # old UI until the computation returns.
        QApplication.processEvents()
        self.compute_summary_requested.emit(path_a, path_b)

    def _on_compute_detailed_clicked(self) -> None:
        path_a = self.detailed_picker_a.path()
        path_b = self.detailed_picker_b.path()
        if not path_a or not path_b:
            QMessageBox.information(
                self, "Reliability",
                "Please select both annotation CSV files first."
            )
            return
        if not os.path.isfile(path_a) or not os.path.isfile(path_b):
            QMessageBox.warning(
                self, "Reliability",
                "One or both selected files cannot be found."
            )
            return
        bin_seconds = float(self.detailed_bin_spin.value())
        self.detailed_status.setText("Computing agreement...")
        # Same lock as the Summary side.
        self.detailed_compute_btn.setEnabled(False)
        self.detailed_progress_label.setVisible(True)
        self.detailed_progress.setVisible(True)
        QApplication.processEvents()
        # Remember the labels that match the current mode so the raster
        # overlay legend matches what the user sees in the input panel.
        if self.detailed_inter_radio.isChecked():
            self._detailed_labels = ("Scorer A", "Scorer B")
        else:
            self._detailed_labels = ("Session 1", "Session 2")
        self.compute_detailed_requested.emit(path_a, path_b, bin_seconds)

    def _on_summary_scatter_changed(self, _index: int) -> None:
        if self._summary_result is None:
            return
        metric = self.summary_scatter_picker.currentText()
        if not metric:
            return
        self._draw_summary_scatter(metric)

    # ---------------- Result rendering ---------------- #

    def show_summary_results(self, result) -> None:
        """Render a SummaryAgreementResult into the table and scatter."""
        self._summary_result = result
        # Always re-enable the Compute button on result arrival - paired
        # with the disable in _on_compute_summary_clicked.
        self.summary_compute_btn.setEnabled(True)
        self.summary_progress.setVisible(False)
        self.summary_progress_label.setVisible(False)
        self.summary_export_btn.setEnabled(bool(result and result.rows))

        if result is None or not result.rows:
            self.summary_status.setText(
                "No comparable metrics were found between the two summary files."
            )
            self.summary_table.setRowCount(0)
            self.summary_scatter_picker.clear()
            self.summary_figure.clear()
            self.summary_canvas.draw_idle()
            return

        source_counts = {"exact": 0, "flexible": 0, "manual": 0}
        for pair in getattr(result, "matched_pairs", []):
            if pair.source in source_counts:
                source_counts[pair.source] += 1
        status_lines = [
            (
                f"Matched animals: {len(result.matched_animals)} "
                f"(exact {source_counts['exact']} / "
                f"flexible {source_counts['flexible']} / "
                f"manual {source_counts['manual']})"
            ),
        ]
        changed_pairs = [
            pair for pair in getattr(result, "matched_pairs", [])
            if pair.animal_id_a != pair.animal_id_b
        ]
        if changed_pairs:
            preview = [
                f"{pair.animal_id_a} <-> {pair.animal_id_b}"
                for pair in changed_pairs[:5]
            ]
            if len(changed_pairs) > 5:
                preview.append(f"... +{len(changed_pairs) - 5} more")
            status_lines.append("Matched pairs: " + "; ".join(preview))
        if result.unmatched_a:
            status_lines.append(
                f"Only in scorer A ({len(result.unmatched_a)}): "
                + ", ".join(result.unmatched_a)
            )
        if result.unmatched_b:
            status_lines.append(
                f"Only in scorer B ({len(result.unmatched_b)}): "
                + ", ".join(result.unmatched_b)
            )
        self.summary_status.setText("\n".join(status_lines))

        self.summary_table.setRowCount(len(result.rows))
        for row_idx, row in enumerate(result.rows):
            metric_item = QTableWidgetItem(row.metric)
            n_item = QTableWidgetItem(str(row.n_pairs))
            icc_item = QTableWidgetItem(_format_value(row.icc, 3))
            pearson_item = QTableWidgetItem(_format_value(row.pearson_r, 3))
            mad_item = QTableWidgetItem(_format_value(row.mean_abs_diff, 3))
            mean_item = QTableWidgetItem(
                f"{_format_value(row.mean_a, 2)} / "
                f"{_format_value(row.mean_b, 2)}"
            )

            # Three-band ICC colouring (Cicchetti 1994 thresholds).
            colour = _icc_color(row.icc)
            if colour is not None:
                icc_item.setForeground(self._colour(colour))

            # Pearson r highlight: green at >=0.80, gold at >=0.90.
            pearson_colour = _pearson_color(row.pearson_r)
            if pearson_colour is not None:
                pearson_item.setForeground(self._colour(pearson_colour))

            for col_idx, item in enumerate(
                [metric_item, n_item, icc_item, pearson_item, mad_item, mean_item]
            ):
                self.summary_table.setItem(row_idx, col_idx, item)

        # Repopulate scatter picker. We block signals around the rebuild so
        # the intermediate ``addItem`` calls do not each trigger a redraw,
        # and we draw the initial scatter explicitly after unblocking to
        # make sure the picker's first item is rendered regardless of
        # whether currentIndexChanged actually fired.
        self.summary_scatter_picker.blockSignals(True)
        self.summary_scatter_picker.clear()
        for metric in result.scatter_data.keys():
            self.summary_scatter_picker.addItem(metric)
        if result.scatter_data:
            self.summary_scatter_picker.setCurrentIndex(0)
        self.summary_scatter_picker.blockSignals(False)

        if result.scatter_data:
            first_metric = next(iter(result.scatter_data.keys()))
            self._draw_summary_scatter(first_metric)
        else:
            self.summary_figure.clear()
            self.summary_canvas.draw_idle()

    def show_detailed_results(self, result) -> None:
        """Render a DetailedAgreementResult into the table and raster overlay."""
        self._detailed_result = result
        # Re-enable the Compute button, mirroring show_summary_results.
        self.detailed_compute_btn.setEnabled(True)
        self.detailed_progress.setVisible(False)
        self.detailed_progress_label.setVisible(False)
        self.detailed_export_btn.setEnabled(bool(result and result.rows))

        if result is None or not result.rows:
            self.detailed_status.setText(
                "No behaviours were found in the annotation files."
            )
            self.detailed_table.setRowCount(0)
            self.detailed_figure.clear()
            self.detailed_canvas.draw_idle()
            return

        self.detailed_status.setText(
            f"Test duration: {result.test_duration_seconds:.1f} s, "
            f"bin width: {result.bin_seconds:.2f} s, "
            f"behaviours: {len(result.behaviors)}"
        )

        self.detailed_table.setRowCount(len(result.rows))
        for row_idx, row in enumerate(result.rows):
            beh_item = QTableWidgetItem(row.behavior)
            bins_item = QTableWidgetItem(str(row.n_bins))
            act_a_item = QTableWidgetItem(str(row.n_active_a))
            act_b_item = QTableWidgetItem(str(row.n_active_b))
            kappa_item = QTableWidgetItem(_format_value(row.cohen_kappa, 3))
            alpha_item = QTableWidgetItem(_format_value(row.krippendorff_alpha, 3))

            # Three-band kappa colouring (Landis & Koch 1977 thresholds).
            kappa_colour = _kappa_color(row.cohen_kappa)
            if kappa_colour is not None:
                kappa_item.setForeground(self._colour(kappa_colour))
            # Krippendorff's alpha shares the same thresholds as kappa for
            # nominal-level data.
            alpha_colour = _kappa_color(row.krippendorff_alpha)
            if alpha_colour is not None:
                alpha_item.setForeground(self._colour(alpha_colour))

            for col_idx, item in enumerate(
                [beh_item, bins_item, act_a_item, act_b_item,
                 kappa_item, alpha_item]
            ):
                self.detailed_table.setItem(row_idx, col_idx, item)

        self._draw_detailed_raster(result)

    # ---------------- Plot helpers ---------------- #

    def _draw_summary_scatter(self, metric: str) -> None:
        if self._summary_result is None or metric not in self._summary_result.scatter_data:
            return
        _animals, values_a, values_b = self._summary_result.scatter_data[metric]
        self.summary_figure.clear()
        ax = self.summary_figure.add_subplot(111)
        # CUD-aligned blue fill with a thin black outline so the dots
        # remain readable on light and dark backgrounds.
        ax.scatter(
            values_a, values_b,
            facecolor="#005aff", edgecolor="black", linewidth=0.8,
            s=42, alpha=0.9,
        )
        if values_a and values_b:
            lo = min(min(values_a), min(values_b))
            hi = max(max(values_a), max(values_b))
            ax.plot([lo, hi], [lo, hi], "--", color="#888", linewidth=1)
        # Axis labels follow the inter/intra-rater radio so the scatter
        # legend matches the file-picker rows.
        if self.summary_inter_radio.isChecked():
            ax.set_xlabel("Scorer A")
            ax.set_ylabel("Scorer B")
        else:
            ax.set_xlabel("Session 1")
            ax.set_ylabel("Session 2")
        ax.set_title(metric)
        ax.grid(True, linestyle=":", alpha=0.4)
        self.summary_figure.tight_layout()
        self.summary_canvas.draw_idle()

    def _draw_detailed_raster(self, result) -> None:
        """Draw events from both scorers as a horizontal raster:
        behaviours stacked on the y-axis, each row split into an A
        ribbon (above) and a B ribbon (below)."""
        self.detailed_figure.clear()
        if not result.behaviors:
            self.detailed_canvas.draw_idle()
            return

        ax = self.detailed_figure.add_subplot(111)

        # Order behaviours top-to-bottom so the natural reading order is
        # preserved.
        behaviors = list(result.behaviors)
        y_positions = {beh: i for i, beh in enumerate(behaviors)}

        # CUD palette: blue for scorer A / session 1, orange-red for
        # scorer B / session 2.
        a_colour = "#005aff"
        b_colour = "#ff4b00"

        def _add_events(events, colour, y_offset):
            for beh, onset, offset in events:
                if beh not in y_positions:
                    continue
                y = y_positions[beh] + y_offset
                ax.hlines(
                    y=y,
                    xmin=onset,
                    xmax=max(offset, onset + 0.05),
                    colors=colour,
                    linewidth=6,
                    alpha=0.85,
                )

        _add_events(result.events_a, a_colour, +0.2)
        _add_events(result.events_b, b_colour, -0.2)

        ax.set_yticks(list(y_positions.values()))
        ax.set_yticklabels(behaviors)
        ax.set_xlabel("Time (seconds)")
        ax.set_xlim(0, max(result.test_duration_seconds, 1.0))
        ax.invert_yaxis()
        ax.grid(True, axis="x", linestyle=":", alpha=0.3)

        # Custom legend: use the labels chosen by the inter/intra-rater
        # radio in this view, falling back to whatever the model
        # recorded if the radios have not been initialised yet.
        label_a = self._detailed_labels[0] or result.label_a
        label_b = self._detailed_labels[1] or result.label_b
        from matplotlib.lines import Line2D
        legend_items = [
            Line2D([0], [0], color=a_colour, linewidth=6, label=label_a),
            Line2D([0], [0], color=b_colour, linewidth=6, label=label_b),
        ]
        # ``handlelength=0.9`` shrinks the swatch in the legend to about
        # 40% of the default 2.0 - matches the request to halve the
        # legend line width.
        ax.legend(handles=legend_items, loc="upper right", handlelength=0.9)
        self.detailed_figure.tight_layout()
        self.detailed_canvas.draw_idle()

    # ---------------- Utilities ---------------- #

    @staticmethod
    def _colour(hex_str: str):
        from PySide6.QtGui import QBrush, QColor
        return QBrush(QColor(hex_str))

    def show_error(self, message: str) -> None:
        # Always release whichever Compute button was disabled so the UI
        # remains operable after an error path.
        self.summary_compute_btn.setEnabled(True)
        self.detailed_compute_btn.setEnabled(True)
        self.summary_progress.setVisible(False)
        self.summary_progress_label.setVisible(False)
        self.detailed_progress.setVisible(False)
        self.detailed_progress_label.setVisible(False)
        QMessageBox.warning(self, "Reliability", message)
        # Echo the error into the active tab's status label, trimmed so
        # long messages do not blow out the layout.
        snippet = message if len(message) <= 160 else message[:157] + "..."
        current = self.tabs.currentIndex()
        if current == 0:
            self.summary_status.setText(f"Error: {snippet}")
        else:
            self.detailed_status.setText(f"Error: {snippet}")

    def reset_summary_compute_state(self, message: str = "") -> None:
        self.summary_compute_btn.setEnabled(True)
        self.summary_progress.setVisible(False)
        self.summary_progress_label.setVisible(False)
        if message:
            self.summary_status.setText(message)

    # ---------------- Result accessors (for export) ---------------- #

    def current_summary_result(self):
        return self._summary_result

    def current_detailed_result(self):
        return self._detailed_result
