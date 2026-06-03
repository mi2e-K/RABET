# views/visualization_view.py - Visualization tools for annotation data
import logging
import os
import json
import re
import colorsys
import warnings
import numpy as np
import matplotlib
try:
    matplotlib.use('QtAgg')  # Preferred backend for Qt5/Qt6 bindings.
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
except (ImportError, ValueError):
    matplotlib.use('Qt5Agg')
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
import matplotlib.colors as mcolors
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QScrollArea, QPushButton, QFileDialog,
    QGridLayout, QGroupBox, QCheckBox, QColorDialog,
    QListWidget, QListWidgetItem, QMessageBox, QSplitter,
    QSizePolicy, QSpinBox, QStyledItemDelegate, QStyle,
    QStyleOptionViewItem, QDialog, QDialogButtonBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QApplication,
)
from PySide6.QtCore import Qt, Signal, QCoreApplication, QTimer, QPoint, QRect, QEvent
from PySide6.QtGui import QColor, QBrush, QPainter, QPen

# Custom item delegate for behavior/file list rows.
#
# Why it exists: QListWidgetItem.setBackground() colours the row with the
# behaviour's colour, but Qt's Fusion style then auto-adjusts the checkmark
# colour to keep contrast with that background. The result is a visibly
# inconsistent checkmark tint per behaviour, which the user perceives as the
# checkmark "colour drifting" between rows. This delegate takes over the
# painting completely so the checkmark stays a fixed colour everywhere while
# the row text still picks black/white based on the row's own brightness
# (matching the logic already used in TimelineCanvas._get_text_color_for_background).
class BehaviorItemDelegate(QStyledItemDelegate):
    """
    Fully-custom paint path for the visualization-view list rows.

    Responsibilities:
        - Fill row background with the item's own background brush.
        - Draw a fixed-colour check indicator (dark box + white check) so
          Fusion's automatic contrast adjustment never gets to recolour the
          checkmark per row.
        - Render the row text in black or white depending on the row's
          background brightness so light behaviour colours stay readable.
        - Translate clicks inside the indicator rect into check-state toggles
          (since we drew the indicator at our own coordinates, the default
          editorEvent hit-test based on SE_ItemViewItemCheckIndicator may be
          slightly off).
    """

    # Fixed colours and geometry for the indicator. Defined as class
    # attributes so they're trivially overridable / inspectable from tests.
    _INDICATOR_BG = QColor("#252525")
    _INDICATOR_BORDER = QColor("#777777")
    _CHECKMARK_COLOR = QColor(255, 255, 255)
    _INDICATOR_SIZE = 14
    _INDICATOR_MARGIN = 4       # gap from row's left edge to indicator
    _TEXT_GAP = 6               # gap from indicator's right edge to text
    _TEXT_BRIGHTNESS_CUTOFF = 170  # >cutoff -> black text; <=cutoff -> white

    def _indicator_rect(self, option):
        """Compute the indicator rect inside ``option.rect``."""
        size = self._INDICATOR_SIZE
        top = option.rect.top() + (option.rect.height() - size) // 2
        left = option.rect.left() + self._INDICATOR_MARGIN
        return QRect(left, top, size, size)

    def _text_color_for_background(self, bg_color):
        """Mirror TimelineCanvas's perceived-brightness rule (R*.299+G*.587+B*.114)."""
        brightness = (
            bg_color.red() * 0.299
            + bg_color.green() * 0.587
            + bg_color.blue() * 0.114
        )
        if brightness > self._TEXT_BRIGHTNESS_CUTOFF:
            return QColor(0, 0, 0)
        return QColor(255, 255, 255)

    def paint(self, painter, option, index):
        # Copy option so initStyleOption's mutations don't leak to callers.
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 1. Background: prefer the item's own brush (the behaviour colour);
        # fall back to palette.base() for rows that weren't given one (e.g.
        # the file list).
        bg_brush = opt.backgroundBrush
        if bg_brush.style() == Qt.BrushStyle.NoBrush:
            bg_brush = QBrush(opt.palette.base())
        painter.fillRect(opt.rect, bg_brush)
        bg_color = bg_brush.color()

        # 2. Selection / hover overlays. Kept semi-transparent so the
        # behaviour colour underneath remains identifiable.
        if opt.state & QStyle.StateFlag.State_Selected:
            highlight = QColor(opt.palette.highlight().color())
            highlight.setAlpha(90)
            painter.fillRect(opt.rect, highlight)
        elif opt.state & QStyle.StateFlag.State_MouseOver:
            hover = QColor(255, 255, 255, 25)
            painter.fillRect(opt.rect, hover)

        # 3. Indicator box (only if the item is user-checkable). Always
        # drawn with a fixed dark fill + border so Fusion can't mutate it.
        ind = self._indicator_rect(opt)
        is_checkable = bool(index.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        if is_checkable:
            painter.fillRect(ind, self._INDICATOR_BG)
            painter.setPen(QPen(self._INDICATOR_BORDER, 1))
            painter.drawRect(ind)

            # 4. Checkmark: drawn as a 3-point polyline so the glyph is
            # font-independent and uniform across all rows.
            check_state = index.data(Qt.ItemDataRole.CheckStateRole)
            # CheckStateRole comes back as int (Qt's underlying enum value);
            # compare against the enum's .value to stay robust to either form.
            if check_state == Qt.CheckState.Checked.value or check_state == Qt.CheckState.Checked:
                pen = QPen(self._CHECKMARK_COLOR, 2)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.drawPolyline([
                    QPoint(ind.x() + 3,  ind.y() + 8),
                    QPoint(ind.x() + 6,  ind.y() + 11),
                    QPoint(ind.x() + 11, ind.y() + 4),
                ])

        # 5. Text: chooses black/white by row brightness so light behaviour
        # colours (light yellow, light pink, etc.) stay legible.
        text = opt.text or str(index.data() or "")
        if text:
            painter.setPen(QPen(self._text_color_for_background(bg_color)))
            if opt.font:
                painter.setFont(opt.font)

            text_left = (
                (ind.right() + self._TEXT_GAP) if is_checkable
                else (opt.rect.left() + self._INDICATOR_MARGIN)
            )
            text_rect = QRect(
                text_left,
                opt.rect.top(),
                opt.rect.right() - text_left - self._INDICATOR_MARGIN,
                opt.rect.height(),
            )
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                text,
            )

        painter.restore()

    def editorEvent(self, event, model, option, index):
        """
        Toggle the check state when the click lands inside our indicator rect.

        We override the default implementation because it hit-tests against
        SE_ItemViewItemCheckIndicator (the *style's* idea of where the
        checkbox lives), which doesn't necessarily match the rect we drew.
        For clicks outside the indicator, fall back to the default handler
        so double-click-to-recolour and selection still work.

        1.3.3+ FIX: the previous implementation toggled by calling
        ``model.setData(index, Qt.CheckState.<X>, CheckStateRole)`` and
        relied on that to flip the QListWidgetItem's checkState. On the
        PySide6 versions RABET ships with, that path sometimes leaves
        the QListWidgetItem.checkState() unchanged even though the
        QModelIndex data round-trip succeeds — producing the exact
        symptom users hit in 1.3.2: unchecking works once, the
        ``itemChanged`` slot then reads the new ``Unchecked`` state, but
        every subsequent click re-fires with the same ``Unchecked``
        reading and never restores the trace.
        The fix below writes the new state in **three** ways: (1) the
        QListWidgetItem directly (the canonical source QListWidget reads
        from), (2) the model index via setData (keeps Qt's standard
        delegate-hook contract), (3) an explicit consume-return so the
        default style logic does not silently double-toggle on the same
        click.
        """
        if not (index.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            return super().editorEvent(event, model, option, index)

        # Only handle mouse-release clicks INSIDE our indicator rect.
        # Everything else (clicks on text, drag-start, double-click for
        # recolour) bubbles up to the default handler.
        if event.type() != QEvent.Type.MouseButtonRelease:
            return super().editorEvent(event, model, option, index)
        click_point = event.position().toPoint()
        if not self._indicator_rect(option).contains(click_point):
            return super().editorEvent(event, model, option, index)

        # Read current state robustly. PySide6 returns this either as
        # ``Qt.CheckState`` (newer wheels) or as a raw ``int`` (older
        # wheels and some platform builds).
        raw = index.data(Qt.ItemDataRole.CheckStateRole)
        if isinstance(raw, Qt.CheckState):
            current_value = raw.value
        elif raw is None:
            current_value = 0
        else:
            try:
                current_value = int(raw)
            except (TypeError, ValueError):
                current_value = 0

        new_state = (
            Qt.CheckState.Unchecked
            if current_value == Qt.CheckState.Checked.value
            else Qt.CheckState.Checked
        )

        # Write through the QListWidgetItem directly. This is the
        # authoritative source that QListWidget.itemChanged reads from
        # and fires the signal RABET's controller listens for.
        #
        # 1.3.3+: we explicitly do NOT also call
        # ``model.setData(index, new_state, CheckStateRole)`` here. The
        # symptom that hint led to was: on re-checking a behaviour, the
        # ``True`` reading would log first, and ~200 ms later a second
        # ``itemChanged`` would land with ``False`` and silently overwrite
        # the visibility back to off (see logs from 1.3.3-dev with both
        # writes enabled). The double-write produced two ``itemChanged``
        # emissions whose interleaving — combined with PySide6's internal
        # CheckState normalisation for the ``setData`` path — could land
        # the second one with the *previous* state and clobber the user's
        # intent. Going via ``setCheckState`` only keeps things simple
        # and consistent.
        widget = self.parent()
        item = None
        if widget is not None and hasattr(widget, "item"):
            try:
                item = widget.item(index.row())
            except Exception:
                item = None
        if item is not None:
            item.setCheckState(new_state)

        # Consume the event so the base implementation does not run its
        # own SE_ItemViewItemCheckIndicator-based toggle, which would
        # otherwise flip the state right back to where it started.
        return True


class ColorMapEditorDialog(QDialog):
    """Dialog for editing and saving Visualization custom color maps."""

    def __init__(
        self,
        current_name,
        color_map,
        available_names,
        can_overwrite,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit Color Map")
        self.resize(520, 420)
        self._current_name = current_name or "custom_color_map"
        self._available_names = set(available_names or [])
        self._result_name = ""
        self._result_map = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        save_row = QHBoxLayout()
        save_row.addWidget(QLabel("Save:"))
        self.save_mode_combo = QComboBox()
        if can_overwrite:
            self.save_mode_combo.addItem("Overwrite current", "overwrite")
        self.save_mode_combo.addItem("Save as new", "new")
        self.save_mode_combo.currentIndexChanged.connect(self._on_save_mode_changed)
        save_row.addWidget(self.save_mode_combo)

        save_row.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit(self._default_name(can_overwrite))
        save_row.addWidget(self.name_edit, 1)
        layout.addLayout(save_row)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Behavior", "Color"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self.table, 1)

        for behavior, color in sorted((color_map or {}).items()):
            self._add_row(behavior, color)

        button_row = QHBoxLayout()
        add_button = QPushButton("Add Row")
        add_button.clicked.connect(lambda: self._add_row("", "#808080"))
        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self._remove_selected_rows)
        pick_button = QPushButton("Pick Color")
        pick_button.clicked.connect(self._pick_selected_color)
        button_row.addWidget(add_button)
        button_row.addWidget(remove_button)
        button_row.addWidget(pick_button)
        button_row.addStretch()
        layout.addLayout(button_row)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._on_save_mode_changed()

    def _default_name(self, can_overwrite):
        if can_overwrite:
            return self._current_name
        return self._default_new_name()

    def _on_save_mode_changed(self):
        mode = self.save_mode_combo.currentData()
        is_new = mode == "new"
        self.name_edit.setEnabled(is_new)
        if not is_new:
            self.name_edit.setText(self._current_name)
        elif self.name_edit.text().strip() == self._current_name:
            self.name_edit.setText(self._default_new_name())

    def _default_new_name(self):
        base = self._current_name or "color_map"
        candidate = f"{base}_copy"
        index = 2
        while self._normalise_name(candidate) in self._available_names:
            candidate = f"{base}_copy_{index}"
            index += 1
        return candidate

    def _add_row(self, behavior, color):
        row = self.table.rowCount()
        self.table.insertRow(row)
        behavior_item = QTableWidgetItem(str(behavior))
        color_item = QTableWidgetItem(self._normalise_color(color) or "#808080")
        self.table.setItem(row, 0, behavior_item)
        self.table.setItem(row, 1, color_item)
        self._style_color_item(color_item)

    def _remove_selected_rows(self):
        selected_rows = sorted(
            {index.row() for index in self.table.selectedIndexes()},
            reverse=True,
        )
        for row in selected_rows:
            self.table.removeRow(row)

    def _on_cell_double_clicked(self, row, column):
        if column == 1:
            self._pick_color_for_row(row)

    def _pick_selected_color(self):
        row = self.table.currentRow()
        if row >= 0:
            self._pick_color_for_row(row)

    def _pick_color_for_row(self, row):
        item = self.table.item(row, 1)
        current = item.text() if item else "#808080"
        color = QColorDialog.getColor(QColor(current), self, "Select Behavior Color")
        if not color.isValid():
            return
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, 1, item)
        item.setText(color.name().upper())
        self._style_color_item(item)

    def _style_color_item(self, item):
        color_text = self._normalise_color(item.text())
        if not color_text:
            return
        color = QColor(color_text)
        item.setText(color_text)
        item.setBackground(QBrush(color))
        luminance = (
            0.2126 * (color.red() / 255) ** 2.2
            + 0.7152 * (color.green() / 255) ** 2.2
            + 0.0722 * (color.blue() / 255) ** 2.2
        )
        item.setForeground(QBrush(QColor("#000000" if luminance > 0.35 else "#FFFFFF")))

    def _normalise_color(self, value):
        color = QColor(str(value).strip())
        if not color.isValid():
            return ""
        return color.name().upper()

    def _normalise_name(self, value):
        name = os.path.splitext(str(value).strip())[0]
        name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
        name = name.strip("._-")
        if not name:
            return ""
        if not name.startswith("custom_"):
            name = f"custom_{name}"
        return name

    def _collect_mapping(self):
        mapping = {}
        for row in range(self.table.rowCount()):
            behavior_item = self.table.item(row, 0)
            color_item = self.table.item(row, 1)
            behavior = behavior_item.text().strip() if behavior_item else ""
            color = self._normalise_color(color_item.text() if color_item else "")
            if not behavior:
                raise ValueError("Behavior names cannot be empty.")
            if behavior in mapping:
                raise ValueError(f"Duplicate behavior: {behavior}")
            if not color:
                raise ValueError(f"Invalid color for {behavior}. Use #RRGGBB.")
            mapping[behavior] = color
        if not mapping:
            raise ValueError("Color map must contain at least one behavior.")
        return mapping

    def accept(self):
        mode = self.save_mode_combo.currentData()
        raw_name = self.name_edit.text().strip()
        normalised_name = self._normalise_name(raw_name)
        if not normalised_name:
            QMessageBox.warning(self, "Invalid Name", "Enter a color map name.")
            return
        if mode == "new" and normalised_name in self._available_names:
            QMessageBox.warning(
                self,
                "Name Exists",
                "A color map with this name already exists. Choose a new name or overwrite it.",
            )
            return
        try:
            mapping = self._collect_mapping()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Color Map", str(exc))
            return

        self._result_name = normalised_name
        self._result_map = mapping
        super().accept()

    def result(self):
        return self._result_name, self._result_map.copy()


class GridStyleDialog(QDialog):
    """Dialog for editing raster plot grid color and line style."""

    DEFAULT_GRID_COLOR = "#B0B0B0"
    LINE_STYLES = [
        ("Solid", "-"),
        ("Dashed", "--"),
        ("Dotted", ":"),
        ("Dash-dot", "-."),
    ]

    def __init__(self, color, linestyle, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Grid Style")
        self._register_default_custom_color()
        self._color = QColor(color)
        if not self._color.isValid():
            self._color = QColor(self.DEFAULT_GRID_COLOR)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Color:"))
        self.color_button = QPushButton(self._color.name().upper())
        self.color_button.clicked.connect(self._choose_color)
        color_row.addWidget(self.color_button, 1)

        reset_color_button = QPushButton("Reset")
        reset_color_button.clicked.connect(self._reset_color)
        color_row.addWidget(reset_color_button)
        layout.addLayout(color_row)

        style_row = QHBoxLayout()
        style_row.addWidget(QLabel("Line type:"))
        self.line_style_combo = QComboBox()
        for label, value in self.LINE_STYLES:
            self.line_style_combo.addItem(label, value)
        current_index = self.line_style_combo.findData(linestyle)
        if current_index >= 0:
            self.line_style_combo.setCurrentIndex(current_index)
        style_row.addWidget(self.line_style_combo, 1)
        layout.addLayout(style_row)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._update_color_button()

    def _register_default_custom_color(self):
        """Put the default grid color in Qt's custom color swatches."""
        QColorDialog.setCustomColor(0, QColor(self.DEFAULT_GRID_COLOR))

    def _choose_color(self):
        self._register_default_custom_color()
        color = QColorDialog.getColor(self._color, self, "Select Grid Color")
        if color.isValid():
            self._color = color
            self._update_color_button()

    def _reset_color(self):
        self._color = QColor(self.DEFAULT_GRID_COLOR)
        self._update_color_button()

    def _update_color_button(self):
        self.color_button.setText(self._color.name().upper())
        red, green, blue = self._color.red(), self._color.green(), self._color.blue()
        luminance = (
            0.2126 * (red / 255) ** 2.2
            + 0.7152 * (green / 255) ** 2.2
            + 0.0722 * (blue / 255) ** 2.2
        )
        text_color = "#000000" if luminance > 0.35 else "#FFFFFF"
        self.color_button.setStyleSheet(
            f"background-color: {self._color.name()}; color: {text_color};"
        )

    def result(self):
        return self._color.name(), self.line_style_combo.currentData()


class CheckableBehaviorTable(QTableWidget):
    """Behavior table whose first-column checkbox toggles from the whole cell."""

    def mousePressEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        index = self.indexAt(pos)
        if index.isValid() and index.column() == 0:
            item = self.item(index.row(), 0)
            if item and item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                if not item.flags() & Qt.ItemFlag.ItemIsEnabled:
                    return
                new_state = (
                    Qt.CheckState.Unchecked
                    if item.checkState() == Qt.CheckState.Checked
                    else Qt.CheckState.Checked
                )
                item.setCheckState(new_state)
                self.setCurrentCell(index.row(), 0)
                self.selectRow(index.row())
                event.accept()
                return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            row = self.currentRow()
            item = self.item(row, 0) if row >= 0 else None
            if item and item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                if not item.flags() & Qt.ItemFlag.ItemIsEnabled:
                    return
                new_state = (
                    Qt.CheckState.Unchecked
                    if item.checkState() == Qt.CheckState.Checked
                    else Qt.CheckState.Checked
                )
                item.setCheckState(new_state)
                event.accept()
                return
        super().keyPressEvent(event)


class OverlayGroupEditDialog(QDialog):
    """Dialog for creating or editing one behavior overlay group."""

    def __init__(
        self,
        behaviors,
        group_name="",
        selected_behaviors=None,
        reserved_behaviors=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Overlay Group")
        self.resize(520, 520)
        self._behaviors = list(behaviors or [])
        self._reserved_behaviors = reserved_behaviors or {}
        self._result_name = ""
        self._result_behaviors = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Group name:"))
        self.name_edit = QLineEdit(group_name)
        name_row.addWidget(self.name_edit, 1)
        layout.addLayout(name_row)

        self.behavior_table = CheckableBehaviorTable(0, 1)
        self.behavior_table.setHorizontalHeaderLabels(["Behaviors"])
        self.behavior_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.behavior_table.verticalHeader().setVisible(False)
        self.behavior_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.behavior_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.behavior_table, 1)

        self._populate_behavior_table(selected_behaviors or [])

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _populate_behavior_table(self, selected_behaviors):
        selected = set(selected_behaviors)
        self.behavior_table.setRowCount(0)
        for row, behavior in enumerate(self._behaviors):
            self.behavior_table.insertRow(row)
            label = behavior
            reserved_group = self._reserved_behaviors.get(behavior)
            if reserved_group:
                label = f"{behavior}  ({reserved_group})"
            item = QTableWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, behavior)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
            )
            if reserved_group:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(
                Qt.CheckState.Checked
                if behavior in selected
                else Qt.CheckState.Unchecked
            )
            self.behavior_table.setItem(row, 0, item)

    def _checked_behaviors(self):
        checked = []
        for row in range(self.behavior_table.rowCount()):
            item = self.behavior_table.item(row, 0)
            if (
                item
                and item.flags() & Qt.ItemFlag.ItemIsEnabled
                and item.checkState() == Qt.CheckState.Checked
            ):
                checked.append(item.data(Qt.ItemDataRole.UserRole))
        return checked

    def accept(self):
        name = self.name_edit.text().strip()
        behaviors = self._checked_behaviors()
        if not name:
            QMessageBox.warning(self, "Invalid Group", "Enter a group name.")
            return
        if len(behaviors) < 2:
            QMessageBox.warning(
                self,
                "Invalid Group",
                "Select at least two behaviors for an overlay group.",
            )
            return
        self._result_name = name
        self._result_behaviors = behaviors
        super().accept()

    def result(self):
        return self._result_name, list(self._result_behaviors)


class OverlayGroupsDialog(QDialog):
    """Dialog for editing behavior overlay groups and per-behavior opacity."""

    SCHEMA = "rabet_visualization_overlay_groups_v1"

    def __init__(self, behaviors, groups, behavior_opacity, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Overlay Groups")
        self.resize(780, 560)
        self._behaviors = self._unique_behaviors(behaviors)
        self._groups = self._normalise_groups(groups or [], show_warnings=False)
        self._behavior_opacity = {
            behavior: self._clamp_opacity(
                (behavior_opacity or {}).get(behavior, 1.0)
            )
            for behavior in self._behaviors
        }
        self._opacity_spinboxes = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        table_row = QHBoxLayout()
        self.group_table = QTableWidget(0, 2)
        self.group_table.setHorizontalHeaderLabels(["Group", "Behaviors"])
        self.group_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.group_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.group_table.verticalHeader().setVisible(False)
        self.group_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.group_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.group_table.itemDoubleClicked.connect(self._edit_selected_group)
        table_row.addWidget(self.group_table, 1)

        self.behavior_table = QTableWidget(0, 2)
        self.behavior_table.setHorizontalHeaderLabels(["Behavior", "Opacity"])
        self.behavior_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.behavior_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.behavior_table.verticalHeader().setVisible(False)
        table_row.addWidget(self.behavior_table, 1)
        layout.addLayout(table_row, 1)

        button_row = QHBoxLayout()
        new_button = QPushButton("New Group")
        new_button.clicked.connect(self._new_group)
        edit_button = QPushButton("Edit Selected")
        edit_button.clicked.connect(self._edit_selected_group)
        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self._remove_selected_group)
        load_button = QPushButton("Load...")
        load_button.clicked.connect(self._load_groups)
        save_button = QPushButton("Save...")
        save_button.clicked.connect(self._save_groups)
        button_row.addWidget(new_button)
        button_row.addWidget(edit_button)
        button_row.addWidget(remove_button)
        button_row.addStretch()
        button_row.addWidget(load_button)
        button_row.addWidget(save_button)
        layout.addLayout(button_row)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._populate_behavior_table()
        self._refresh_group_table()

    def _unique_behaviors(self, behaviors):
        result = []
        seen = set()
        for behavior in behaviors or []:
            behavior = str(behavior).strip()
            if behavior and behavior not in seen:
                result.append(behavior)
                seen.add(behavior)
        return result

    def _clamp_opacity(self, value):
        try:
            opacity = float(value)
        except (TypeError, ValueError):
            opacity = 1.0
        return max(0.0, min(1.0, opacity))

    def _populate_behavior_table(self):
        self.behavior_table.setRowCount(0)
        self._opacity_spinboxes = {}
        for row, behavior in enumerate(self._behaviors):
            self.behavior_table.insertRow(row)
            behavior_item = QTableWidgetItem(behavior)
            behavior_item.setFlags(behavior_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            behavior_item.setData(Qt.ItemDataRole.UserRole, behavior)
            self.behavior_table.setItem(row, 0, behavior_item)

            opacity_spinbox = QSpinBox()
            opacity_spinbox.setMinimum(0)
            opacity_spinbox.setMaximum(100)
            opacity_spinbox.setSuffix("%")
            opacity_spinbox.setValue(int(round(self._behavior_opacity[behavior] * 100)))
            self._opacity_spinboxes[behavior] = opacity_spinbox
            self.behavior_table.setCellWidget(row, 1, opacity_spinbox)

    def _refresh_group_table(self):
        was_blocked = self.group_table.blockSignals(True)
        try:
            self.group_table.setRowCount(0)
            for row, group in enumerate(self._groups):
                self.group_table.insertRow(row)
                name_item = QTableWidgetItem(group["name"])
                members_item = QTableWidgetItem(", ".join(group["behaviors"]))
                self.group_table.setItem(row, 0, name_item)
                self.group_table.setItem(row, 1, members_item)
        finally:
            self.group_table.blockSignals(was_blocked)

    def _selected_group_index(self):
        row = self.group_table.currentRow()
        if 0 <= row < len(self._groups):
            return row
        return None

    def _next_group_name(self):
        existing_names = {group["name"] for group in self._groups}
        base = "New Group"
        if base not in existing_names:
            return base
        index = 2
        while f"{base} {index}" in existing_names:
            index += 1
        return f"{base} {index}"

    def _reserved_behaviors(self, selected_index=None):
        reserved = {}
        for index, group in enumerate(self._groups):
            if index == selected_index:
                continue
            for behavior in group["behaviors"]:
                reserved[behavior] = group["name"]
        return reserved

    def _validate_group(self, name, behaviors, selected_index=None):
        for index, group in enumerate(self._groups):
            if index != selected_index and group["name"] == name:
                QMessageBox.warning(
                    self,
                    "Invalid Group",
                    f"A group named '{name}' already exists.",
                )
                return False

        assigned_elsewhere = self._reserved_behaviors(selected_index)
        conflicts = [
            f"{behavior} ({assigned_elsewhere[behavior]})"
            for behavior in behaviors
            if behavior in assigned_elsewhere
        ]
        if conflicts:
            QMessageBox.warning(
                self,
                "Invalid Group",
                "Each behavior can belong to only one group:\n"
                + "\n".join(conflicts),
            )
            return False
        return True

    def _open_group_editor(self, selected_index=None):
        if selected_index is None:
            group_name = self._next_group_name()
            selected_behaviors = []
        else:
            group = self._groups[selected_index]
            group_name = group["name"]
            selected_behaviors = group["behaviors"]

        dialog = OverlayGroupEditDialog(
            self._behaviors,
            group_name,
            selected_behaviors,
            self._reserved_behaviors(selected_index),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        name, behaviors = dialog.result()
        if not self._validate_group(name, behaviors, selected_index):
            return False

        new_group = {"name": name, "behaviors": behaviors}
        if selected_index is None:
            self._groups.append(new_group)
            selected_index = len(self._groups) - 1
        else:
            self._groups[selected_index] = new_group

        self._refresh_group_table()
        self.group_table.selectRow(selected_index)
        return True

    def _new_group(self):
        self._open_group_editor(None)

    def _edit_selected_group(self):
        selected_index = self._selected_group_index()
        if selected_index is None:
            QMessageBox.information(
                self,
                "Overlay Groups",
                "Select a group to edit.",
            )
            return
        self._open_group_editor(selected_index)

    def _remove_selected_group(self):
        selected_index = self._selected_group_index()
        if selected_index is None:
            return
        del self._groups[selected_index]
        self._refresh_group_table()

    def _current_opacity(self):
        opacity = {}
        for behavior in self._behaviors:
            spinbox = self._opacity_spinboxes.get(behavior)
            if spinbox:
                opacity[behavior] = spinbox.value() / 100
        return opacity

    def _config_dict(self):
        return {
            "schema": self.SCHEMA,
            "groups": [
                {
                    "name": group["name"],
                    "behaviors": list(group["behaviors"]),
                }
                for group in self._groups
            ],
            "behavior_opacity": self._current_opacity(),
        }

    def _normalise_groups(self, groups, show_warnings=True):
        behavior_set = set(self._behaviors)
        normalised = []
        assigned = set()
        group_names = set()
        warnings_list = []

        if not isinstance(groups, list):
            if show_warnings:
                QMessageBox.warning(
                    self,
                    "Invalid Overlay Groups",
                    "The groups field must be a list.",
                )
            return []

        for group in groups:
            if not isinstance(group, dict):
                warnings_list.append("Skipped a non-object group entry.")
                continue
            name = str(group.get("name", "")).strip()
            if not name:
                warnings_list.append("Skipped a group without a name.")
                continue
            if name in group_names:
                warnings_list.append(f"Skipped duplicate group name: {name}")
                continue

            members = []
            for raw_behavior in group.get("behaviors", []):
                behavior = str(raw_behavior).strip()
                if not behavior:
                    continue
                if behavior not in behavior_set:
                    warnings_list.append(
                        f"Ignored missing behavior in '{name}': {behavior}"
                    )
                    continue
                if behavior in assigned:
                    warnings_list.append(
                        f"Ignored duplicate behavior membership: {behavior}"
                    )
                    continue
                if behavior not in members:
                    members.append(behavior)

            if len(members) < 2:
                warnings_list.append(
                    f"Skipped '{name}' because it has fewer than two valid behaviors."
                )
                continue

            normalised.append({"name": name, "behaviors": members})
            group_names.add(name)
            assigned.update(members)

        if show_warnings and warnings_list:
            QMessageBox.warning(
                self,
                "Overlay Groups Loaded",
                "\n".join(warnings_list[:12]),
            )
        return normalised

    def _load_groups(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Overlay Groups",
            "",
            "JSON Files (*.json);;All Files (*)",
        )
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Overlay group file must be a JSON object.")
            if data.get("schema") != self.SCHEMA:
                raise ValueError(f"Unsupported overlay group schema: {data.get('schema')!r}")

            groups = self._normalise_groups(data.get("groups", []), show_warnings=True)
            opacity_data = data.get("behavior_opacity", {})
            if not isinstance(opacity_data, dict):
                opacity_data = {}

            self._groups = groups
            self._behavior_opacity = {
                behavior: self._clamp_opacity(opacity_data.get(behavior, 1.0))
                for behavior in self._behaviors
            }
            for behavior, spinbox in self._opacity_spinboxes.items():
                spinbox.setValue(int(round(self._behavior_opacity[behavior] * 100)))
            self._refresh_group_table()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Overlay Groups Error",
                f"Failed to load overlay groups:\n{exc}",
            )

    def _save_groups(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Overlay Groups",
            "overlay_groups.json",
            "JSON Files (*.json);;All Files (*)",
        )
        if not file_path:
            return
        if not os.path.splitext(file_path)[1]:
            file_path = f"{file_path}.json"

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self._config_dict(), f, indent=2)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Overlay Groups Error",
                f"Failed to save overlay groups:\n{exc}",
            )

    def result(self):
        return (
            [
                {
                    "name": group["name"],
                    "behaviors": list(group["behaviors"]),
                }
                for group in self._groups
            ],
            self._current_opacity(),
        )


# Custom reorderable list widget
class ReorderableListWidget(QListWidget):
    """List widget that supports drag and drop reordering.

    A plain click anywhere on a row (the file/individual name, not only the
    checkbox indicator) toggles that row's checkbox; dragging still reorders.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        # Apply the custom delegate so checkmark colour stays uniform across
        # rows regardless of the row's background colour.
        delegate = BehaviorItemDelegate(self)
        self.setItemDelegate(delegate)
        self._press_pos = None
        self._press_item = None
        # One-shot INFO log so we can confirm from the log that the delegate
        # was actually attached at construction time. Without this, a
        # silently-missed setItemDelegate (e.g. because an older copy of the
        # file was running) would look identical to a working install.
        logging.getLogger(__name__).info(
            "ReorderableListWidget: attached BehaviorItemDelegate=%s",
            type(delegate).__name__,
        )

    def mousePressEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        self._press_pos = pos
        self._press_item = self.itemAt(pos)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        # A plain click anywhere on a checkable, enabled row toggles it - not
        # only the checkbox indicator. We bypass the base handler on that path
        # so Qt's own indicator toggle does not double-fire. A drag (movement
        # beyond the platform drag threshold) falls through to the base class so
        # InternalMove reordering keeps working.
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        item = self.itemAt(pos)
        press_item, self._press_item = self._press_item, None
        press_pos, self._press_pos = self._press_pos, None
        if (
            item is not None
            and item is press_item
            and bool(item.flags() & Qt.ItemFlag.ItemIsUserCheckable)
            and bool(item.flags() & Qt.ItemFlag.ItemIsEnabled)
        ):
            threshold = QApplication.startDragDistance()
            dragged = press_pos is not None and (
                (pos - press_pos).manhattanLength() >= threshold
            )
            if not dragged:
                new_state = (
                    Qt.CheckState.Unchecked
                    if item.checkState() == Qt.CheckState.Checked
                    else Qt.CheckState.Checked
                )
                item.setCheckState(new_state)
                self.setCurrentItem(item)
                event.accept()
                return
        super().mouseReleaseEvent(event)


class MatplotlibCanvas(FigureCanvas):
    """Matplotlib canvas for embedding in Qt applications."""
    
    def __init__(self, parent=None, width=10, height=6, dpi=100):
        """
        Initialize the canvas.
        
        Args:
            parent: Parent widget
            width: Figure width in inches
            height: Figure height in inches
            dpi: DPI for the figure
        """
        # Create figure WITHOUT tight_layout to avoid warnings with manual axis positioning
        self.fig = Figure(figsize=(width, height), dpi=dpi, tight_layout=False)
        self.axes = self.fig.add_subplot(111)
        
        super().__init__(self.fig)
        self.setParent(parent)
        
        # Don't set size policy here - let the parent widget control it
        FigureCanvas.updateGeometry(self)


class RasterPlotWidget(QWidget):
    """Widget for displaying raster plots of behavioral events."""

    files_selected = Signal(list)
    selected_colormap_changed = Signal(str)
    plot_save_directory_changed = Signal(str)
    # 1.3.3+: emitted from the Clear button so the controller can drop
    # its own cache. Without this, clicking Clear only wipes the in-view
    # state and a subsequent re-drop of the same files restored the
    # previous data straight out of the controller's _visualization_data
    # cache.
    clear_data_requested = Signal()
    custom_colormap_save_requested = Signal(str, dict)
    
    # Default custom color mapping for common behaviors
    DEFAULT_COLOR_MAP = {
        "Attack bites": "#FF4B00",
        "Sideways threats": "#F6AA00",
        "Tail rattles": "#C9ACE6",
        "Chasing": "#FF8082",
        "Social contact": "#4DC4FF",
        "Self-grooming": "#03AF7A",
        "Locomotion": "#FFFFB2",
        "Rearing": "#FFCABF"
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing RasterPlotWidget")
        
        # Data storage
        self._data = {}  # Dictionary to store annotation data
        self._behavior_colors = {}  # Dictionary to store behavior colors
        self._behavior_visibility = {}  # Dictionary to store behavior visibility
        self._file_visibility = {}  # Dictionary to store file visibility
        self._default_colormap = 'Set1'  # Default built-in colormap
        self._custom_color_map = {}
        self._overlay_groups = []
        self._behavior_opacity = {}
        
        # Available custom color maps (discovered from configs folder)
        self._available_custom_colormaps = {}
        
        # Display settings
        self._time_unit = "Seconds"  # Time unit (Seconds or Minutes)
        self._tick_interval = 60     # Tick interval in seconds (default 1 minute)
        self._x_range_max = 300      # X-axis maximum in seconds (default 5 minutes)
        self._bar_height = 15        # Height of raster plot bars (line width)
        self._text_font_size = 10    # Axis/tick/behavior label font size
        self._png_dpi = 300          # PNG export DPI
        self._display_mode = "Separate Behaviors"  # Display mode setting
        self._show_vertical_grid = True
        self._show_horizontal_grid = True
        self._grid_color = "#B0B0B0"
        self._grid_linestyle = "--"
        self._border_mode = "All"
        self._transparent_outside_plot = False
        self._last_plot_save_directory = ""
        self._show_file_label_numbers = True
        self._show_file_separators = True

        # Track custom ordering
        self._custom_behavior_order = []
        self._custom_file_order = []
        self._fixed_behavior_order = []
        self._fixed_action_map_path = None
        
        # Individual frames setting for overlay mode
        self._individual_frames = False
        
        # Matplotlib warning context manager
        self._mpl_warning_filter = warnings.catch_warnings()
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface."""
        # Main layout with reduced spacing
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(3)
        self.layout.setContentsMargins(5, 5, 5, 0)
        
        # Control panel
        self._create_control_panel()
        
        # Buttons
        self._create_button_panel()
        
        # Create main content area with splitter
        self._create_main_content()
        
        # Status label
        self.status_label = QLabel("No data loaded")
        self.status_label.setMaximumHeight(25)
        self.status_label.setContentsMargins(0, 2, 0, 2)
        self.status_label.setWordWrap(False)
        self.layout.addWidget(self.status_label, 0)
        
        # Initialize display settings
        self._time_unit = "Seconds"
        self._tick_interval = 60
        self._x_range_max = 300
        self._bar_height = 20
    
    def _create_control_panel(self):
        """Create the control panel for plot settings."""
        self.controls_group = QGroupBox("Plot Controls")
        self.controls_group.setMaximumHeight(110)
        self.controls_layout = QGridLayout(self.controls_group)
        self.controls_layout.setContentsMargins(5, 5, 5, 5)
        self.controls_layout.setHorizontalSpacing(12)
        self.controls_layout.setVerticalSpacing(2)
        for column in range(4):
            self.controls_layout.setColumnStretch(column, 1)

        # Display mode selection
        self.display_mode_label = QLabel("Display Mode:")
        self.display_mode_combo = QComboBox()
        self.display_mode_combo.addItems(["Separate Behaviors", "Overlay Behaviors"])
        self.display_mode_combo.setFixedWidth(170)
        self.display_mode_combo.setCurrentText(self._display_mode)
        self.display_mode_combo.currentTextChanged.connect(self.on_display_mode_changed)

        # Colormap selection
        self.colormap_label = QLabel("Color Map:")
        self.colormap_combo = QComboBox()
        self.builtin_colormaps = [
            'Set1', 'Set2', 'Set3', 'Accent',
            'Dark2', 'viridis', 'plasma', 'inferno'
        ]
        self.colormap_combo.addItems(self.builtin_colormaps)
        self.colormap_combo.setFixedWidth(120)
        self.colormap_combo.setCurrentText(self._default_colormap)
        self.colormap_combo.currentTextChanged.connect(self.on_colormap_changed)

        # Time unit
        self.time_unit_label = QLabel("Display Unit:")
        self.time_unit_combo = QComboBox()
        self.time_unit_combo.addItems(["Seconds", "Minutes"])
        self.time_unit_combo.setFixedWidth(100)
        self.time_unit_combo.setCurrentText("Seconds")
        self.time_unit_combo.currentTextChanged.connect(self.on_time_unit_changed)

        # Text font size
        self.text_font_size_label = QLabel("Font Size:")
        self.text_font_size_spinbox = QSpinBox()
        self.text_font_size_spinbox.setMinimum(6)
        self.text_font_size_spinbox.setMaximum(24)
        self.text_font_size_spinbox.setValue(self._text_font_size)
        self.text_font_size_spinbox.setFixedWidth(70)
        self.text_font_size_spinbox.valueChanged.connect(self.on_text_font_size_changed)

        # Tick interval
        self.tick_interval_label = QLabel("Tick Interval (sec):")
        self.tick_interval_spinbox = QSpinBox()
        self.tick_interval_spinbox.setMinimum(1)
        self.tick_interval_spinbox.setMaximum(600)
        self.tick_interval_spinbox.setValue(60)
        self.tick_interval_spinbox.setFixedWidth(80)
        self.tick_interval_spinbox.valueChanged.connect(self.on_tick_interval_changed)

        # X-axis range
        self.x_range_label = QLabel("Max Range (sec):")
        self.x_range_spinbox = QSpinBox()
        self.x_range_spinbox.setMinimum(60)
        self.x_range_spinbox.setMaximum(7200)
        self.x_range_spinbox.setValue(300)
        self.x_range_spinbox.setFixedWidth(90)
        self.x_range_spinbox.valueChanged.connect(self.on_x_range_changed)

        # Bar height control
        self.bar_height_label = QLabel("Bar Height:")
        self.bar_height_spinbox = QSpinBox()
        self.bar_height_spinbox.setMinimum(1)
        self.bar_height_spinbox.setMaximum(100)
        self.bar_height_spinbox.setValue(20)
        self.bar_height_spinbox.setFixedWidth(70)
        self.bar_height_spinbox.valueChanged.connect(self.on_bar_height_changed)

        # PNG export DPI
        self.png_dpi_label = QLabel("PNG DPI:")
        self.png_dpi_spinbox = QSpinBox()
        self.png_dpi_spinbox.setMinimum(72)
        self.png_dpi_spinbox.setMaximum(1200)
        self.png_dpi_spinbox.setValue(self._png_dpi)
        self.png_dpi_spinbox.setFixedWidth(80)
        self.png_dpi_spinbox.valueChanged.connect(self.on_png_dpi_changed)

        self._add_labeled_control(0, 0, self.display_mode_label, self.display_mode_combo)
        self._add_labeled_control(0, 1, self.colormap_label, self.colormap_combo)
        self._add_labeled_control(0, 2, self.time_unit_label, self.time_unit_combo)
        self._add_labeled_control(0, 3, self.text_font_size_label, self.text_font_size_spinbox)
        self._add_labeled_control(1, 0, self.tick_interval_label, self.tick_interval_spinbox)
        self._add_labeled_control(1, 1, self.x_range_label, self.x_range_spinbox)
        self._add_labeled_control(1, 2, self.bar_height_label, self.bar_height_spinbox)
        self._add_labeled_control(1, 3, self.png_dpi_label, self.png_dpi_spinbox)

        # Add controls to main layout
        self.layout.addWidget(self.controls_group, 0)

    def _add_labeled_control(self, row, column, label, control):
        """Add a compact label/control pair to the Plot Controls grid."""
        pair_widget = QWidget()
        pair_layout = QHBoxLayout(pair_widget)
        pair_layout.setContentsMargins(0, 0, 0, 0)
        pair_layout.setSpacing(4)
        pair_widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        pair_layout.addWidget(label)
        pair_layout.addWidget(control)
        self.controls_layout.addWidget(
            pair_widget,
            row,
            column,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
    
    def _create_button_panel(self):
        """Create the button panel."""
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 2, 0, 2)
        button_layout.setSpacing(5)
        
        # Load button
        self.load_button = QPushButton("Load CSV")
        self.load_button.clicked.connect(self.load_files_from_dialog)
        self.load_button.setMaximumWidth(120)
        self.load_button.setMaximumHeight(30)

        # Optional action map behavior source for visualization only
        self.load_action_map_button = QPushButton("Load Action Map")
        self.load_action_map_button.clicked.connect(self.load_action_map_from_dialog)
        self.load_action_map_button.setMaximumWidth(150)
        self.load_action_map_button.setMaximumHeight(30)

        self.edit_colormap_button = QPushButton("Edit Color Map")
        self.edit_colormap_button.clicked.connect(self.edit_current_colormap)
        self.edit_colormap_button.setMaximumWidth(140)
        self.edit_colormap_button.setMaximumHeight(30)

        self.clear_action_map_button = QPushButton("Use Data Behaviors")
        self.clear_action_map_button.clicked.connect(self.clear_action_map_behavior_source)
        self.clear_action_map_button.setMaximumWidth(160)
        self.clear_action_map_button.setMaximumHeight(30)
        self.clear_action_map_button.setEnabled(False)

        self.action_map_status_label = QLabel("Behaviors: data")
        self.action_map_status_label.setMaximumHeight(30)
        self.action_map_status_label.setMinimumWidth(120)
        self.action_map_status_label.setMaximumWidth(220)

        # Refresh button
        self.refresh_button = QPushButton("Refresh Plot")
        self.refresh_button.clicked.connect(self.update_plot)
        self.refresh_button.setMaximumWidth(150)
        self.refresh_button.setMaximumHeight(30)
        
        # Save button
        self.save_button = QPushButton("Save Plot")
        self.save_button.clicked.connect(self.save_plot)
        self.save_button.setMaximumWidth(150)
        self.save_button.setMaximumHeight(30)
        
        # Clear button
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_data)
        self.clear_button.setMaximumWidth(100)
        self.clear_button.setMaximumHeight(30)
        
        button_layout.addWidget(self.load_button)
        button_layout.addWidget(self.load_action_map_button)
        button_layout.addWidget(self.edit_colormap_button)
        button_layout.addWidget(self.clear_action_map_button)
        button_layout.addWidget(self.action_map_status_label)
        button_layout.addSpacing(15)
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.save_button)
        button_layout.addSpacing(15)
        button_layout.addWidget(self.clear_button)
        button_layout.addStretch()
        
        self.layout.addLayout(button_layout, 0)
    
    def _create_main_content(self):
        """Create the main content area with splitter."""
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side container
        self._create_left_panel()
        
        # Right side plot area
        self._create_plot_area()
        
        # Set splitter sizes (30% for list, 70% for plot)
        self.splitter.setSizes([300, 700])
        
        # Add splitter to main layout
        self.layout.addWidget(self.splitter, 10)
    
    def _create_left_panel(self):
        """Create the left panel with behavior and file lists."""
        self.left_container = QWidget()
        self.left_layout = QVBoxLayout(self.left_container)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(5)
        
        # Behavior list
        self.behavior_group = QGroupBox("Behaviors (drag to reorder)")
        self.behavior_layout = QVBoxLayout(self.behavior_group)
        self.behavior_layout.setContentsMargins(5, 10, 5, 5)
        self.behavior_layout.setSpacing(2)
        
        self.behavior_list = ReorderableListWidget()
        self.behavior_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.behavior_list.setMinimumHeight(220)
        self.behavior_list.itemDoubleClicked.connect(self.on_behavior_double_clicked)
        self.behavior_list.itemChanged.connect(self.on_behavior_selection_changed)
        self.behavior_list.model().rowsMoved.connect(self.on_behaviors_reordered)
        self.behavior_layout.addWidget(self.behavior_list)

        self.overlay_groups_button = QPushButton("Overlay Groups...")
        self.overlay_groups_button.clicked.connect(self.edit_overlay_groups)
        self.overlay_groups_button.setMaximumHeight(30)
        self.behavior_layout.addWidget(self.overlay_groups_button)
        
        self.left_layout.addWidget(self.behavior_group, 1)
        
        # File selection list (shown when multiple individuals/files are loaded)
        self.file_group = QGroupBox("Files / Individuals (drag to reorder)")
        self.file_layout = QVBoxLayout(self.file_group)
        self.file_layout.setContentsMargins(5, 10, 5, 5)
        self.file_layout.setSpacing(2)
        
        self.file_list = ReorderableListWidget()
        self.file_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.file_list.setMinimumHeight(180)
        self.file_list.itemChanged.connect(self.on_file_selection_changed)
        self.file_list.model().rowsMoved.connect(self.on_files_reordered)
        self.file_layout.addWidget(self.file_list)

        self.export_individual_plots_button = QPushButton("Export Individual Plots...")
        self.export_individual_plots_button.clicked.connect(self.export_individual_plots)
        self.export_individual_plots_button.setMaximumHeight(30)
        self.file_layout.addWidget(self.export_individual_plots_button)

        self.file_options_layout = QHBoxLayout()
        self.file_options_layout.setContentsMargins(0, 0, 0, 0)
        self.file_options_layout.setSpacing(8)

        self.file_label_numbers_checkbox = QCheckBox("Number labels")
        self.file_label_numbers_checkbox.setChecked(self._show_file_label_numbers)
        self.file_label_numbers_checkbox.setToolTip(
            "Prefix behavior labels with the file number when multiple files are plotted."
        )
        self.file_label_numbers_checkbox.stateChanged.connect(
            self.on_file_label_numbers_changed
        )

        self.file_separators_checkbox = QCheckBox("File separators")
        self.file_separators_checkbox.setChecked(self._show_file_separators)
        self.file_separators_checkbox.setToolTip(
            "Draw separator lines between individual file blocks."
        )
        self.file_separators_checkbox.stateChanged.connect(
            self.on_file_separators_changed
        )

        self.file_options_layout.addWidget(self.file_label_numbers_checkbox)
        self.file_options_layout.addWidget(self.file_separators_checkbox)
        self.file_options_layout.addStretch()
        self.file_layout.addLayout(self.file_options_layout)
        
        self.file_group.setVisible(False)
        self.left_layout.addWidget(self.file_group, 1)
        
        self.left_layout.addStretch(1)
        self.splitter.addWidget(self.left_container)
    
    def _create_plot_area(self):
        """Create the plot area with canvas and controls."""
        self.plot_widget = QWidget()
        self.plot_layout = QVBoxLayout(self.plot_widget)
        self.plot_layout.setContentsMargins(0, 0, 0, 0)
        self.plot_layout.setSpacing(5)
        
        # Plot size controls
        self._create_plot_size_controls()
        
        # Create scroll area for canvas
        self.canvas_scroll = QScrollArea()
        self.canvas_scroll.setWidgetResizable(True)
        
        # Create matplotlib canvas
        self.canvas = MatplotlibCanvas(self, width=8, height=6, dpi=100)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.canvas_scroll.setWidget(self.canvas)
        self.plot_layout.addWidget(self.canvas_scroll, 10)
        
        self.splitter.addWidget(self.plot_widget)
    
    def _create_plot_size_controls(self):
        """Create plot size control widgets."""
        self.plot_controls_layout = QHBoxLayout()
        self.plot_controls_layout.setContentsMargins(0, 0, 0, 5)
        self.plot_controls_layout.setSpacing(10)
        
        # Width control
        self.width_label = QLabel("Width:")
        self.width_spinbox = QSpinBox()
        self.width_spinbox.setMinimum(400)
        self.width_spinbox.setMaximum(2000)
        self.width_spinbox.setValue(800)
        self.width_spinbox.setSuffix(" px")
        self.width_spinbox.setMaximumHeight(25)
        self.width_spinbox.valueChanged.connect(self.on_plot_size_changed)
        
        # Height control
        self.height_label = QLabel("Height:")
        self.height_spinbox = QSpinBox()
        self.height_spinbox.setMinimum(100)
        self.height_spinbox.setMaximum(2000)
        self.height_spinbox.setValue(600)
        self.height_spinbox.setSuffix(" px")
        self.height_spinbox.setMaximumHeight(25)
        self.height_spinbox.valueChanged.connect(self.on_plot_size_changed)

        # Border visibility
        self.border_label = QLabel("Border:")
        self.border_combo = QComboBox()
        self.border_combo.addItems(["All", "Left + Bottom", "Bottom Only"])
        self.border_combo.setCurrentText(self._border_mode)
        self.border_combo.setMaximumHeight(25)
        self.border_combo.setFixedWidth(125)
        self.border_combo.currentTextChanged.connect(self.on_border_mode_changed)

        # Auto-size checkbox
        self.auto_size_checkbox = QCheckBox("Auto-fit")
        self.auto_size_checkbox.setChecked(True)
        self.auto_size_checkbox.stateChanged.connect(self.on_auto_size_changed)

        # Grid controls
        self.vertical_grid_checkbox = QCheckBox("V Grid")
        self.vertical_grid_checkbox.setChecked(self._show_vertical_grid)
        self.vertical_grid_checkbox.stateChanged.connect(self.on_vertical_grid_changed)

        self.horizontal_grid_checkbox = QCheckBox("H Grid")
        self.horizontal_grid_checkbox.setChecked(self._show_horizontal_grid)
        self.horizontal_grid_checkbox.stateChanged.connect(self.on_horizontal_grid_changed)

        self.grid_style_button = QPushButton("Grid Style")
        self.grid_style_button.clicked.connect(self.on_grid_style_clicked)
        self.grid_style_button.setMaximumWidth(95)
        self.grid_style_button.setMaximumHeight(25)
        self.grid_style_button.setToolTip("Set grid color and line type.")
        self._update_grid_style_button()

        self.transparent_outside_checkbox = QCheckBox("Transparent Outside")
        self.transparent_outside_checkbox.setChecked(self._transparent_outside_plot)
        self.transparent_outside_checkbox.setMaximumHeight(25)
        self.transparent_outside_checkbox.stateChanged.connect(
            self.on_transparent_outside_changed
        )
        
        # Individual frames checkbox (only for overlay mode)
        self.individual_frames_checkbox = QCheckBox("Individual frames")
        self.individual_frames_checkbox.setChecked(False)
        self.individual_frames_checkbox.stateChanged.connect(self.on_individual_frames_changed)
        self.individual_frames_checkbox.setVisible(False)
        
        # Frame height control
        self.frame_height_label = QLabel("Frame height:")
        self.frame_height_spinbox = QSpinBox()
        self.frame_height_spinbox.setMinimum(5)
        self.frame_height_spinbox.setMaximum(200)
        self.frame_height_spinbox.setValue(30)
        self.frame_height_spinbox.setSuffix(" px")
        self.frame_height_spinbox.setToolTip(
            "Height of each individual frame in pixels.\n"
            "Auto-fit mode: Use smaller values (1.5x bar height)\n"
            "Fixed size mode: Use larger values (3x bar height)\n"
            "Adjusts automatically when switching modes."
        )
        self.frame_height_spinbox.valueChanged.connect(self.on_frame_height_changed)
        self.frame_height_label.setVisible(False)
        self.frame_height_spinbox.setVisible(False)
        
        # Add controls to layout
        self.plot_controls_layout.addWidget(self.width_label)
        self.plot_controls_layout.addWidget(self.width_spinbox)
        self.plot_controls_layout.addSpacing(15)
        self.plot_controls_layout.addWidget(self.height_label)
        self.plot_controls_layout.addWidget(self.height_spinbox)
        self.plot_controls_layout.addSpacing(15)
        self.plot_controls_layout.addWidget(self.border_label)
        self.plot_controls_layout.addWidget(self.border_combo)
        self.plot_controls_layout.addSpacing(15)
        self.plot_controls_layout.addWidget(self.auto_size_checkbox)
        self.plot_controls_layout.addSpacing(15)
        self.plot_controls_layout.addWidget(self.vertical_grid_checkbox)
        self.plot_controls_layout.addWidget(self.horizontal_grid_checkbox)
        self.plot_controls_layout.addWidget(self.grid_style_button)
        self.plot_controls_layout.addWidget(self.transparent_outside_checkbox)
        self.plot_controls_layout.addSpacing(15)
        self.plot_controls_layout.addWidget(self.individual_frames_checkbox)
        self.plot_controls_layout.addSpacing(8)
        self.plot_controls_layout.addWidget(self.frame_height_label)
        self.plot_controls_layout.addWidget(self.frame_height_spinbox)
        self.plot_controls_layout.addStretch()
        
        # Initially disable size controls when auto-fit is checked
        self.width_spinbox.setEnabled(False)
        self.height_spinbox.setEnabled(False)
        
        self.plot_layout.addLayout(self.plot_controls_layout, 0)
    
    # Utility methods
    def _suppress_matplotlib_warnings(self):
        """Context manager to suppress matplotlib tight_layout warnings."""
        return warnings.catch_warnings()
    
    def _get_recording_start(self, df, file_name=""):
        """
        Extract recording start time from dataframe.
        
        Args:
            df: Pandas DataFrame with annotation data
            file_name: Name of file for logging
            
        Returns:
            float: Recording start time in seconds
        """
        recording_start = 0.0
        if 'Event' in df.columns:
            recording_start_events = df[df['Event'] == 'RecordingStart']
            if not recording_start_events.empty and 'Onset' in recording_start_events.columns:
                starts = []
                for raw_onset in recording_start_events['Onset']:
                    try:
                        onset = float(raw_onset)
                    except (TypeError, ValueError):
                        continue
                    if np.isfinite(onset):
                        starts.append(onset)

                if starts:
                    recording_start = min(starts)
                    if len(starts) > 1:
                        self.logger.warning(
                            "Multiple RecordingStart events found in %s; "
                            "using earliest finite onset %.4fs",
                            file_name or "loaded data",
                            recording_start,
                        )
                if file_name:
                    self.logger.info(f"Found RecordingStart at {recording_start}s in {file_name}")
        return recording_start

    def _ordered_file_paths(self):
        """Return loaded file paths in the user-defined order."""
        file_paths = list(self._data.keys())

        if self._custom_file_order:
            existing_files = set(file_paths)
            ordered_files = [f for f in self._custom_file_order if f in existing_files]
            new_files = [f for f in file_paths if f not in ordered_files]
            return ordered_files + new_files

        return file_paths

    def _visible_file_paths(self):
        """Return ordered file paths whose file checkbox is enabled."""
        return [
            file_path
            for file_path in self._ordered_file_paths()
            if self._file_visibility.get(file_path, True)
        ]

    def _should_show_file_group(self):
        """Return whether the file/individual list should be visible.

        1.3.3+: previously hidden whenever a *single* file was loaded in
        Separate Behaviors mode, on the (now obsolete) reasoning that
        one-track lists carry no information. In practice users want to
        see the file's checkbox even for a single file — both as a
        reminder of which file is being plotted and so they can toggle it
        off without going through Clear first. Show the panel whenever
        any data is loaded.
        """
        return bool(self._data)

    def _refresh_file_group_visibility(self):
        """Show the file list when individual identity matters."""
        show_file_group = self._should_show_file_group()
        self.file_group.setVisible(show_file_group)
        if show_file_group:
            self.update_file_list()

    def _display_time_limit(self):
        """Return the exact user-requested x-axis upper limit."""
        return float(self._x_range_max)

    def _display_ticks(self, display_max_time):
        """Return x-axis ticks clipped to the displayed range."""
        interval = max(1, int(self._tick_interval))
        ticks = np.arange(0, display_max_time + 1e-9, interval, dtype=float)
        if ticks.size == 0:
            ticks = np.array([0.0])
        if not np.isclose(ticks[-1], display_max_time):
            ticks = np.append(ticks, display_max_time)
        return ticks

    def _format_time_tick_labels(self, ticks):
        """Format x-axis tick labels for the selected time unit."""
        if self._time_unit == "Minutes":
            return [f"{tick / 60:g}" for tick in ticks]
        return [f"{tick:g}" for tick in ticks]

    def _normalise_plot_export_path(self, file_path, selected_filter):
        """Return a path and Matplotlib format for a plot export."""
        extension_to_format = {
            ".svg": "svg",
            ".png": "png",
            ".pdf": "pdf",
        }
        selected_filter_to_extension = {
            "SVG Files (*.svg)": ".svg",
            "PNG Files (*.png)": ".png",
            "PDF Files (*.pdf)": ".pdf",
        }

        _root, extension = os.path.splitext(file_path)
        extension = extension.lower()
        if extension in extension_to_format:
            return file_path, extension_to_format[extension]

        selected_extension = selected_filter_to_extension.get(selected_filter, ".svg")
        return f"{file_path}{selected_extension}", extension_to_format[selected_extension]

    def _plot_export_default_path(self, default_name):
        """Return a default export path rooted at the last plot save folder."""
        if self._last_plot_save_directory and os.path.isdir(self._last_plot_save_directory):
            return os.path.join(self._last_plot_save_directory, default_name)
        return default_name

    def _remember_plot_save_path(self, file_path):
        """Persist the directory used by a successful plot export."""
        directory = os.path.dirname(os.path.abspath(file_path))
        if not directory:
            return
        self._last_plot_save_directory = directory
        self.plot_save_directory_changed.emit(directory)

    def set_last_plot_save_directory(self, directory):
        """Restore the last directory used for plot exports."""
        if directory and os.path.isdir(directory):
            self._last_plot_save_directory = directory

    def _plot_save_kwargs(self, file_format):
        """Build Matplotlib savefig keyword arguments from current settings."""
        save_kwargs = {
            "format": file_format,
            "bbox_inches": "tight",
        }
        if self._transparent_outside_plot:
            save_kwargs["facecolor"] = "none"
            save_kwargs["edgecolor"] = "none"
        if file_format == "png":
            save_kwargs["dpi"] = self._png_dpi
        return save_kwargs

    def _save_current_figure_to_path(self, file_path, file_format):
        """Save the currently rendered figure using current export options."""
        self._apply_figure_background_style()
        self.canvas.fig.savefig(
            file_path,
            **self._plot_save_kwargs(file_format),
        )

    def _show_timed_information(self, title, message, timeout_ms=1500):
        """Show an information dialog that closes automatically."""
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setWindowTitle(title)
        dialog.setText(message)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        QTimer.singleShot(timeout_ms, dialog.accept)
        dialog.exec()

    def _file_paths_from_list(self):
        """Return file paths in the exact order shown in the Files list."""
        file_paths = []
        for row in range(self.file_list.count()):
            item = self.file_list.item(row)
            file_path = item.data(Qt.ItemDataRole.UserRole)
            if file_path in self._data:
                file_paths.append(file_path)
        return file_paths or self._ordered_file_paths()

    def _safe_export_stem(self, file_path, index):
        """Return a filesystem-safe stem for an individual export."""
        stem = os.path.splitext(os.path.basename(file_path))[0]
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", stem)
        stem = stem.strip(" ._")
        return stem or f"individual_{index:02d}"

    def _behavior_order_from_list(self):
        """Return behavior names in the current user-defined list order."""
        return [
            self.behavior_list.item(row).text()
            for row in range(self.behavior_list.count())
        ]

    def _visible_behaviors_from_list(self):
        """Return visible behavior names in the current list order."""
        return [
            behavior
            for behavior in self._behavior_order_from_list()
            if self._behavior_visibility.get(behavior, True)
        ]

    def _valid_overlay_groups(self, behavior_order=None):
        """Return overlay groups filtered to behaviors currently available."""
        behavior_order = behavior_order or self._behavior_order_from_list()
        behavior_set = set(behavior_order)
        assigned = set()
        valid_groups = []
        for group in self._overlay_groups:
            name = str(group.get("name", "")).strip()
            if not name:
                continue
            members = []
            for behavior in group.get("behaviors", []):
                if (
                    behavior in behavior_set
                    and behavior not in assigned
                    and behavior not in members
                ):
                    members.append(behavior)
            if len(members) < 2:
                continue
            assigned.update(members)
            valid_groups.append({"name": name, "behaviors": members})
        return valid_groups

    def _has_active_overlay_groups(self, behavior_order=None):
        """Return whether at least one valid overlay group is configured."""
        return bool(self._valid_overlay_groups(behavior_order))

    def _behavior_rows(self, behavior_order=None):
        """Build display rows from behaviors plus configured overlay groups."""
        behavior_order = behavior_order or self._behavior_order_from_list()
        visible_set = {
            behavior
            for behavior in behavior_order
            if self._behavior_visibility.get(behavior, True)
        }
        valid_groups = self._valid_overlay_groups(behavior_order)
        group_by_behavior = {}
        for index, group in enumerate(valid_groups):
            for behavior in group["behaviors"]:
                group_by_behavior[behavior] = index

        rows = []
        emitted_groups = set()
        for behavior in behavior_order:
            if behavior not in visible_set:
                continue
            group_index = group_by_behavior.get(behavior)
            if group_index is None:
                rows.append({
                    "label": behavior,
                    "behaviors": [behavior],
                    "is_group": False,
                })
                continue
            if group_index in emitted_groups:
                continue
            group = valid_groups[group_index]
            members = [
                member
                for member in group["behaviors"]
                if member in visible_set
            ]
            if not members:
                continue
            rows.append({
                "label": group["name"],
                "behaviors": members,
                "is_group": True,
            })
            emitted_groups.add(group_index)
        return rows

    def _behavior_zorders(self, behavior_order):
        """Return z-order values where visually higher behaviors draw on top."""
        total = len(behavior_order)
        return {
            behavior: 10 + total - index
            for index, behavior in enumerate(behavior_order)
        }

    def _behavior_alpha(self, behavior, base_alpha):
        """Apply per-behavior opacity as a multiplier to the base alpha."""
        opacity = self._behavior_opacity.get(behavior, 1.0)
        try:
            opacity = float(opacity)
        except (TypeError, ValueError):
            opacity = 1.0
        opacity = max(0.0, min(1.0, opacity))
        return max(0.0, min(1.0, base_alpha * opacity))

    def _initial_file_visibility(self, data_dict, previous_file_visibility):
        """Default multi-file loads to the first file only."""
        ordered_paths = list(data_dict.keys())
        if len(ordered_paths) <= 1:
            return {path: True for path in ordered_paths}

        visibility = {}
        preserved_any = False
        for index, file_path in enumerate(ordered_paths):
            if file_path in previous_file_visibility:
                visibility[file_path] = previous_file_visibility[file_path]
                preserved_any = True
            else:
                visibility[file_path] = index == 0 and not preserved_any

        if not preserved_any:
            visibility = {path: (index == 0) for index, path in enumerate(ordered_paths)}
        elif not any(visibility.values()):
            visibility[ordered_paths[0]] = True

        return visibility

    def _contrasting_text_color(self, color_rgb):
        """Return black or white text for a colored list item background."""
        red, green, blue = [channel / 255 for channel in color_rgb]
        luminance = (
            0.2126 * red ** 2.2
            + 0.7152 * green ** 2.2
            + 0.0722 * blue ** 2.2
        )
        return (0, 0, 0) if luminance > 0.35 else (255, 255, 255)

    def _set_item_color(self, item, color_rgb):
        """Apply a background color and readable foreground to a list item."""
        text_rgb = self._contrasting_text_color(color_rgb)
        item.setBackground(QBrush(QColor(*color_rgb)))
        item.setForeground(QBrush(QColor(*text_rgb)))

    def _rgb_to_hex(self, color_rgb):
        """Convert an RGB tuple to #RRGGBB."""
        red, green, blue = color_rgb[:3]
        return f"#{int(red):02X}{int(green):02X}{int(blue):02X}"

    def _current_color_map_for_editor(self):
        """Return the current effective behavior colors as a saveable map."""
        list_behaviors = [
            self.behavior_list.item(row).text()
            for row in range(self.behavior_list.count())
        ]
        if self._custom_color_map:
            behaviors = list(self._custom_color_map.keys())
            for behavior in list_behaviors:
                if behavior not in self._custom_color_map:
                    behaviors.append(behavior)
        elif list_behaviors:
            behaviors = list_behaviors
        else:
            behaviors = list(self.DEFAULT_COLOR_MAP.keys())

        if behaviors:
            self._generate_behavior_colors(behaviors)

        color_map = {}
        for behavior in behaviors:
            if behavior in self._custom_color_map:
                color_map[behavior] = QColor(self._custom_color_map[behavior]).name().upper()
            elif behavior in self._behavior_colors:
                color_map[behavior] = self._rgb_to_hex(self._behavior_colors[behavior])
            elif behavior in self.DEFAULT_COLOR_MAP:
                color_map[behavior] = QColor(self.DEFAULT_COLOR_MAP[behavior]).name().upper()

        if not color_map:
            return self.DEFAULT_COLOR_MAP.copy()
        return color_map

    def _apply_grid(self, ax):
        """Apply grid settings to a Matplotlib axes."""
        ax.grid(False, axis='both')
        ax.set_axisbelow(True)
        if self._show_vertical_grid:
            ax.grid(
                True, axis='x', linestyle=self._grid_linestyle, color=self._grid_color,
                alpha=0.55, linewidth=1.6, zorder=0
            )
        if self._show_horizontal_grid:
            ax.grid(
                True, axis='y', linestyle=self._grid_linestyle, color=self._grid_color,
                alpha=0.45, linewidth=1.1, zorder=0
            )

    def _apply_border_style(self, ax):
        """Apply the selected axes border/spine visibility."""
        visible_spines = {
            "All": {"left", "right", "top", "bottom"},
            "Left + Bottom": {"left", "bottom"},
            "Bottom Only": {"bottom"},
        }.get(self._border_mode, {"left", "right", "top", "bottom"})

        for name, spine in ax.spines.items():
            spine.set_visible(name in visible_spines)
            spine.set_linewidth(2.5)
            spine.set_zorder(100)

    def _update_grid_style_button(self):
        """Style the grid settings button with the current grid color."""
        color = QColor(self._grid_color)
        text_rgb = self._contrasting_text_color((color.red(), color.green(), color.blue()))
        self.grid_style_button.setStyleSheet(
            f"background-color: {self._grid_color}; "
            f"color: rgb({text_rgb[0]}, {text_rgb[1]}, {text_rgb[2]});"
        )

    def _apply_figure_background_style(self):
        """Apply the export/preview background outside the plot frame."""
        if not hasattr(self, "canvas"):
            return
        if self._transparent_outside_plot:
            self.canvas.fig.patch.set_facecolor("none")
            self.canvas.fig.patch.set_alpha(0.0)
        else:
            self.canvas.fig.patch.set_facecolor("white")
            self.canvas.fig.patch.set_alpha(1.0)

    def _update_canvas_display(self):
        """Ensure canvas is properly displayed after updates."""
        if self.auto_size_checkbox.isChecked():
            self.canvas.updateGeometry()
            # Only call processEvents once
            QCoreApplication.processEvents()
    
    def _draw_canvas_safe(self):
        """Draw canvas with warning suppression."""
        self._apply_figure_background_style()
        with self._suppress_matplotlib_warnings():
            warnings.filterwarnings("ignore", message="This figure includes Axes that are not compatible")
            self.canvas.draw()
        
        # Update display after drawing
        self._update_canvas_display()

        # Event handlers
    def on_display_mode_changed(self, mode):
        """Handle display mode change."""
        self._display_mode = mode
        self.logger.info(f"Display mode changed to: {mode}")
        
        # Show/hide UI elements based on mode
        is_overlay = (mode == "Overlay Behaviors")
        self.individual_frames_checkbox.setVisible(is_overlay)
        
        # Show frame height controls if needed
        if is_overlay and self._individual_frames:
            self.frame_height_label.setVisible(True)
            self.frame_height_spinbox.setVisible(True)
        else:
            self.frame_height_label.setVisible(False)
            self.frame_height_spinbox.setVisible(False)
        
        # Keep file/individual identity visible when it affects the plot.
        self._refresh_file_group_visibility()
        
        # Update the plot
        self._schedule_plot_update()
    
    def on_colormap_changed(self, colormap_name):
        """Handle colormap selection change."""
        if not colormap_name:
            self.logger.warning("Empty colormap name received, ignoring")
            return
        
        # Check if this is a custom colormap or built-in
        if colormap_name in self._available_custom_colormaps:
            self._custom_color_map = self._available_custom_colormaps[colormap_name].copy()
            self.logger.info(f"Selected custom colormap: {colormap_name}")
        else:
            if colormap_name:
                self._default_colormap = colormap_name
            self._custom_color_map = {}
            self.logger.info(f"Selected built-in colormap: {colormap_name}")
        
        # Reset behavior colors to force regeneration
        self._behavior_colors = {}
        
        # Update behavior list and plot
        self.update_behavior_list()
        self._schedule_plot_update()
        self.selected_colormap_changed.emit(colormap_name)
    
    def on_time_unit_changed(self, unit):
        """Handle time unit change."""
        self._time_unit = unit
        self._schedule_plot_update()
    
    def on_tick_interval_changed(self, value):
        """Handle tick interval change."""
        self._tick_interval = value
        self._schedule_plot_update()
    
    def on_x_range_changed(self, value):
        """Handle x-axis range change."""
        self._x_range_max = value
        self._schedule_plot_update()
    
    def on_bar_height_changed(self, value):
        """Handle bar height change."""
        self._bar_height = value
        self.logger.debug(f"Bar height changed to: {value}")
        self._schedule_plot_update()

    def on_text_font_size_changed(self, value):
        """Handle text font size changes."""
        self._text_font_size = value
        self._schedule_plot_update()

    def on_png_dpi_changed(self, value):
        """Handle PNG export DPI changes."""
        self._png_dpi = value

    def on_border_mode_changed(self, mode):
        """Handle plot border visibility changes."""
        self._border_mode = mode
        self._schedule_plot_update()

    def on_transparent_outside_changed(self, state):
        """Handle outside-plot transparency changes."""
        self._transparent_outside_plot = (state == Qt.CheckState.Checked.value)
        self._schedule_plot_update()
    
    def on_plot_size_changed(self, value):
        """Handle plot size change."""
        if not self.auto_size_checkbox.isChecked():
            width_pixels = self.width_spinbox.value()
            height_pixels = self.height_spinbox.value()
            
            # Set fixed size for the canvas widget
            self.canvas.setFixedSize(width_pixels, height_pixels)
            
            # Update figure size
            width_inches = width_pixels / 100
            height_inches = height_pixels / 100
            self.canvas.fig.set_size_inches(width_inches, height_inches)
            
            # Update canvas
            self.canvas.updateGeometry()
            self._schedule_plot_update()
    
    def on_auto_size_changed(self, state):
        """Handle auto-size checkbox change."""
        is_checked = (state == Qt.CheckState.Checked.value)
        
        # Enable/disable size controls
        self.width_spinbox.setEnabled(not is_checked)
        self.height_spinbox.setEnabled(not is_checked)
        
        if is_checked:
            # Enable auto-fit mode
            self.canvas_scroll.setWidgetResizable(True)
            self.canvas.setMinimumSize(0, 0)
            self.canvas.setMaximumSize(16777215, 16777215)  # Qt's QWIDGETSIZE_MAX
            self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            
            # Adjust frame height for auto-fit mode
            if self._individual_frames and self._display_mode == "Overlay Behaviors":
                suggested_height = int(self._bar_height * 1.5)
                self.frame_height_spinbox.setValue(min(max(suggested_height, 20), 50))
        else:
            # Disable auto-fit mode
            self.canvas_scroll.setWidgetResizable(False)
            self.canvas.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            
            # Apply fixed size
            width_pixels = self.width_spinbox.value()
            height_pixels = self.height_spinbox.value()
            self.canvas.setFixedSize(width_pixels, height_pixels)
            
            # Update figure size
            self.canvas.fig.set_size_inches(width_pixels / 100, height_pixels / 100)
            
            # Adjust frame height for fixed size mode
            if self._individual_frames and self._display_mode == "Overlay Behaviors":
                suggested_height = int(self._bar_height * 3)
                self.frame_height_spinbox.setValue(min(max(suggested_height, 40), 100))
        
        self.canvas.updateGeometry()
        self._schedule_plot_update()
    
    def on_individual_frames_changed(self, state):
        """Handle individual frames checkbox change."""
        self._individual_frames = (state == Qt.CheckState.Checked.value)
        
        # Show/hide frame height controls
        show_controls = self._individual_frames and self._display_mode == "Overlay Behaviors"
        self.frame_height_label.setVisible(show_controls)
        self.frame_height_spinbox.setVisible(show_controls)
        
        # Adjust frame height default
        if show_controls:
            if self.auto_size_checkbox.isChecked():
                suggested_height = int(self._bar_height * 1.5)
                self.frame_height_spinbox.setValue(min(max(suggested_height, 20), 50))
            else:
                suggested_height = int(self._bar_height * 3)
                self.frame_height_spinbox.setValue(min(max(suggested_height, 40), 100))
        
        self._schedule_plot_update()
    
    def on_frame_height_changed(self, value):
        """Handle frame height change."""
        self._schedule_plot_update()

    def on_vertical_grid_changed(self, state):
        """Handle vertical grid visibility changes."""
        self._show_vertical_grid = (state == Qt.CheckState.Checked.value)
        self._schedule_plot_update()

    def on_horizontal_grid_changed(self, state):
        """Handle horizontal grid visibility changes."""
        self._show_horizontal_grid = (state == Qt.CheckState.Checked.value)
        self._schedule_plot_update()

    def on_grid_style_clicked(self):
        """Handle grid color and line-style changes."""
        dialog = GridStyleDialog(self._grid_color, self._grid_linestyle, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._grid_color, self._grid_linestyle = dialog.result()
            self._update_grid_style_button()
            self._schedule_plot_update()

    def on_file_label_numbers_changed(self, state):
        """Handle behavior-label file number visibility changes."""
        self._show_file_label_numbers = (state == Qt.CheckState.Checked.value)
        self._schedule_plot_update()

    def on_file_separators_changed(self, state):
        """Handle individual file separator visibility changes."""
        self._show_file_separators = (state == Qt.CheckState.Checked.value)
        self._schedule_plot_update()

    def edit_overlay_groups(self):
        """Open the overlay group editor for the current behavior list."""
        behaviors = self._behavior_order_from_list()
        if not behaviors:
            QMessageBox.warning(
                self,
                "Overlay Groups",
                "Load annotation data or an action map before creating overlay groups.",
            )
            return

        dialog = OverlayGroupsDialog(
            behaviors,
            self._overlay_groups,
            self._behavior_opacity,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._overlay_groups, self._behavior_opacity = dialog.result()
        self._schedule_plot_update()

    def edit_current_colormap(self):
        """Open the custom color-map editor and request a save."""
        current_name = self.colormap_combo.currentText()
        can_overwrite = current_name in self._available_custom_colormaps
        editor_map = self._current_color_map_for_editor()
        dialog = ColorMapEditorDialog(
            current_name if can_overwrite else "color_map",
            editor_map,
            self._available_custom_colormaps.keys(),
            can_overwrite,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        colormap_name, color_map = dialog.result()
        if not colormap_name or not color_map:
            return

        self._custom_color_map = color_map.copy()
        self._behavior_colors = {}
        self.custom_colormap_save_requested.emit(colormap_name, color_map)
        self.update_behavior_list()
        self._schedule_plot_update()

    def on_behavior_selection_changed(self, item):
        """Handle behavior checkbox state change."""
        behavior = item.text()
        new_state = (item.checkState() == Qt.CheckState.Checked)
        self._behavior_visibility[behavior] = new_state
        self.logger.debug(
            f"behavior visibility -> {behavior}={new_state}"
        )
        self._schedule_plot_update()

    def on_file_selection_changed(self, item):
        """Handle file selection change in overlay mode."""
        file_path = item.data(Qt.ItemDataRole.UserRole)
        new_state = (item.checkState() == Qt.CheckState.Checked)
        self._file_visibility[file_path] = new_state
        self.logger.debug(
            f"file visibility -> {os.path.basename(file_path)}={new_state}"
        )
        self._schedule_plot_update()
    
    def on_behavior_double_clicked(self, item):
        """Handle double click on a behavior item - change color."""
        behavior = item.text()
        current_color = self._behavior_colors.get(behavior, (255, 255, 255))
        
        # Open color dialog
        color = QColorDialog.getColor(QColor(*current_color), self, f"Select Color for {behavior}")
        
        if color.isValid():
            # Update color
            rgb = (color.red(), color.green(), color.blue())
            self._behavior_colors[behavior] = rgb

            # 1.3.3+: ``setBackground`` fires ``itemChanged`` on widgets
            # that already own the item, which would otherwise re-enter
            # ``on_behavior_selection_changed`` and rewrite
            # ``_behavior_visibility[behavior]`` from a stale checkState.
            # Block the signal while we mutate the cosmetics.
            was_blocked = self.behavior_list.blockSignals(True)
            try:
                self._set_item_color(item, rgb)
            finally:
                self.behavior_list.blockSignals(was_blocked)

            # Update plot
            self._schedule_plot_update()
    
    def on_behaviors_reordered(self):
        """Handle behaviors being reordered in the list."""
        self._custom_behavior_order = []
        for i in range(self.behavior_list.count()):
            item = self.behavior_list.item(i)
            self._custom_behavior_order.append(item.text())
        
        self.logger.debug(f"Behaviors reordered: {self._custom_behavior_order}")
        self._schedule_plot_update()
    
    def on_files_reordered(self):
        """Handle files being reordered in the list."""
        self._custom_file_order = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            file_path = item.data(Qt.ItemDataRole.UserRole)
            self._custom_file_order.append(file_path)
        
        self.logger.debug(f"Files reordered: {[os.path.basename(f) for f in self._custom_file_order]}")
        
        # Update the file list to renumber items
        self.update_file_list()
        self._schedule_plot_update()
    
    # Data management methods
    def set_data(self, data_dict):
        """Set the annotation data for visualization."""
        previous_file_visibility = self._file_visibility.copy()
        self._data = data_dict
        self.logger.info(f"Visualization data set: {len(data_dict)} files")

        # Clear existing behavior colors
        self._behavior_colors = {}
        self._behavior_visibility = {}

        # Initialize file visibility
        self._file_visibility = self._initial_file_visibility(
            data_dict, previous_file_visibility
        )
        
        # Initialize custom file order if not already set
        if not self._custom_file_order:
            self._custom_file_order = list(data_dict.keys())
        
        # Update the behavior list
        self.update_behavior_list()
        
        # Update file list when the plot distinguishes files/individuals.
        self._refresh_file_group_visibility()
        
        # Update the plot
        self._schedule_plot_update()
        
        # Schedule deferred updates to ensure proper display
        for delay in [50, 100, 200]:
            QTimer.singleShot(delay, self._ensure_proper_display)
        
        # Update status
        self.status_label.setText(f"Loaded {len(data_dict)} file(s)")
    
    def _ensure_proper_display(self):
        """Ensure the canvas is properly displayed after data is loaded."""
        if self.auto_size_checkbox.isChecked():
            viewport = self.canvas_scroll.viewport()
            if viewport and viewport.width() > 50 and viewport.height() > 50:
                self.canvas.resize(viewport.size())
                self.canvas.updateGeometry()
                self.canvas.draw_idle()

    def load_files_from_dialog(self):
        """Select CSV annotation files for visualization."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Load Annotation CSV Files",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )
        if file_paths:
            self.logger.info(f"Selected {len(file_paths)} visualization file(s)")
            self.files_selected.emit(file_paths)

    def load_action_map_from_dialog(self):
        """Load an optional action map to fix the behavior list/order."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Action Map",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        if not file_path:
            return

        try:
            behaviors = self._read_action_map_behaviors(file_path)
        except Exception as e:
            self.logger.error(f"Failed to load visualization action map: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Action Map Error",
                f"Failed to load action map:\n{e}"
            )
            return

        self._fixed_behavior_order = behaviors
        self._fixed_action_map_path = file_path
        self._custom_behavior_order = behaviors.copy()
        self._behavior_colors = {}
        self._behavior_visibility = {
            behavior: self._behavior_visibility.get(behavior, True)
            for behavior in behaviors
        }
        self.clear_action_map_button.setEnabled(True)
        self.action_map_status_label.setText(f"Behaviors: {os.path.basename(file_path)}")
        self.logger.info(
            "Loaded visualization action map with %d behavior(s): %s",
            len(behaviors),
            file_path,
        )
        self.update_behavior_list()
        self._schedule_plot_update()

    def clear_action_map_behavior_source(self):
        """Return visualization behavior discovery to the loaded data."""
        self._fixed_behavior_order = []
        self._fixed_action_map_path = None
        self._custom_behavior_order = []
        self._behavior_colors = {}
        self._behavior_visibility = {}
        self.clear_action_map_button.setEnabled(False)
        self.action_map_status_label.setText("Behaviors: data")
        self.update_behavior_list()
        self._schedule_plot_update()

    def _read_action_map_behaviors(self, file_path):
        """Return unique behavior names from a RABET action map JSON file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("Action map must be a JSON object.")

        behaviors = []
        seen = set()
        for key, behavior in data.items():
            if not isinstance(key, str) or len(key) != 1:
                raise ValueError(f"Invalid key in action map: {key!r}")
            if not isinstance(behavior, str) or not behavior.strip():
                raise ValueError(f"Invalid behavior label for key {key!r}.")
            behavior = behavior.strip()
            if behavior not in seen:
                behaviors.append(behavior)
                seen.add(behavior)

        if not behaviors:
            raise ValueError("Action map does not contain any behaviors.")

        return behaviors

    def set_custom_color_map(self, color_map):
        """Set a custom color mapping for behaviors."""
        if color_map and isinstance(color_map, dict):
            self._custom_color_map = color_map.copy()
            self.logger.info(f"Custom color map set with {len(color_map)} behaviors")
            
            # Update behavior list to apply new colors
            self.update_behavior_list()
            self._schedule_plot_update()
    
    def add_custom_colormaps_to_dropdown(self, custom_colormaps):
        """Add custom colormaps to the main colormap dropdown."""
        self.logger.info(f"Adding {len(custom_colormaps)} custom colormaps to dropdown")
        self.logger.debug(f"Custom colormaps: {list(custom_colormaps.keys())}")
        
        # Store the custom colormaps
        self._available_custom_colormaps = custom_colormaps
        
        # Remember current selection
        current_selection = self.colormap_combo.currentText()

        was_blocked = self.colormap_combo.blockSignals(True)
        try:
            # Clear and rebuild the dropdown
            self.colormap_combo.clear()

            # Add built-in colormaps first
            self.colormap_combo.addItems(self.builtin_colormaps)

            # Add separator if we have custom colormaps
            if custom_colormaps:
                self.colormap_combo.insertSeparator(self.colormap_combo.count())

            # Add custom colormaps
            custom_names = sorted(custom_colormaps.keys())
            for name in custom_names:
                self.colormap_combo.addItem(name)

            # Restore selection if it still exists
            index = self.colormap_combo.findText(current_selection)
            if index >= 0:
                self.colormap_combo.setCurrentIndex(index)
            else:
                self.colormap_combo.setCurrentText(self._default_colormap)
        finally:
            self.colormap_combo.blockSignals(was_blocked)

        self.logger.info(f"Successfully added {len(custom_colormaps)} custom colormaps to dropdown")

    def select_custom_colormap(self, colormap_name):
        """Select a custom color map by dropdown name."""
        index = self.colormap_combo.findText(colormap_name)
        if index >= 0:
            self.colormap_combo.setCurrentIndex(index)
            return True
        return False

    def clear_data(self):
        """Clear all loaded data and reset the plot."""
        # Clear data
        self._data = {}
        self._behavior_colors = {}
        self._behavior_visibility = {}
        self._file_visibility = {}
        self._custom_behavior_order = []
        self._custom_file_order = []
        self._overlay_groups = []
        self._behavior_opacity = {}
        self.file_group.setVisible(False)

        # Clear lists
        self.behavior_list.clear()
        self.file_list.clear()

        # Clear the plot
        self.canvas.fig.clear()
        self.canvas.axes = self.canvas.fig.add_subplot(111)
        self.canvas.axes.clear()

        # Update status
        self.status_label.setText("No data loaded")

        # Draw the empty canvas
        self._draw_canvas_safe()

        # 1.3.3+ FIX: notify the controller so its in-memory
        # ``_visualization_data`` dict is wiped too. Otherwise a later
        # re-drop of the same CSV(s) appears to "resurrect" the cleared
        # session because the controller's cached frames are still
        # there.
        self.clear_data_requested.emit()

        self.logger.info("Cleared all data and reset plot")
    
    def save_plot(self):
        """Save the current plot to a file."""
        # Apply any debounced redraw before snapshotting the figure.
        self._flush_pending_plot_update()
        if not hasattr(self, 'canvas') or not self._data:
            QMessageBox.warning(self, "Warning", "No plot to save.")
            return
        
        # Open file dialog
        file_dialog = QFileDialog()
        file_path, selected_filter = file_dialog.getSaveFileName(
            self,
            "Save Plot",
            self._plot_export_default_path("behavioral_raster_plot.svg"),
            "SVG Files (*.svg);;PNG Files (*.png);;PDF Files (*.pdf);;All Files (*)"
        )

        if file_path:
            try:
                file_path, file_format = self._normalise_plot_export_path(
                    file_path, selected_filter
                )
                self._save_current_figure_to_path(file_path, file_format)
                self._remember_plot_save_path(file_path)
                self.logger.info(f"Plot saved to: {file_path}")
                self._show_timed_information("Success", f"Plot saved to:\n{file_path}")
            except Exception as e:
                self.logger.error(f"Error saving plot: {str(e)}")
                QMessageBox.critical(self, "Error", f"Failed to save plot:\n{str(e)}")

    def export_individual_plots(self):
        """Export one plot per file/individual using the current plot settings."""
        # Apply any debounced redraw so current settings are reflected.
        self._flush_pending_plot_update()
        if not hasattr(self, 'canvas') or not self._data:
            QMessageBox.warning(self, "Warning", "No plot to export.")
            return

        file_paths = self._file_paths_from_list()
        if not file_paths:
            QMessageBox.warning(self, "Warning", "No files are available to export.")
            return

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Individual Plots",
            self._plot_export_default_path("individual_plots.svg"),
            "SVG Files (*.svg);;PNG Files (*.png);;PDF Files (*.pdf);;All Files (*)"
        )
        if not file_path:
            return

        try:
            file_path, file_format = self._normalise_plot_export_path(
                file_path,
                selected_filter,
            )
            output_dir = os.path.dirname(os.path.abspath(file_path))
            base_stem = os.path.splitext(os.path.basename(file_path))[0]
            extension = f".{file_format}"

            original_visibility = self._file_visibility.copy()
            exported_paths = []
            failures = []

            try:
                for index, individual_path in enumerate(file_paths, start=1):
                    try:
                        self._file_visibility = {
                            path: (path == individual_path)
                            for path in self._data
                        }
                        self.update_file_list()
                        self._schedule_plot_update()

                        individual_stem = self._safe_export_stem(individual_path, index)
                        output_name = (
                            f"{base_stem}_{index:02d}_{individual_stem}{extension}"
                        )
                        output_path = os.path.join(output_dir, output_name)
                        self._save_current_figure_to_path(output_path, file_format)
                        exported_paths.append(output_path)
                    except Exception as exc:
                        failures.append((individual_path, str(exc)))
                        self.logger.error(
                            "Failed to export individual plot for %s: %s",
                            individual_path,
                            exc,
                        )
            finally:
                self._file_visibility = original_visibility
                self.update_file_list()
                self._schedule_plot_update()

            if exported_paths:
                self._remember_plot_save_path(exported_paths[-1])

            if failures:
                failed_names = "\n".join(
                    f"- {os.path.basename(path)}: {error}"
                    for path, error in failures[:5]
                )
                remaining = len(failures) - 5
                if remaining > 0:
                    failed_names += f"\n...and {remaining} more"
                QMessageBox.warning(
                    self,
                    "Export Incomplete",
                    f"Exported {len(exported_paths)} plot(s), "
                    f"but {len(failures)} failed:\n{failed_names}",
                )
                return

            self.logger.info(
                "Exported %d individual plot(s) to %s",
                len(exported_paths),
                output_dir,
            )
            self._show_timed_information(
                "Success",
                f"Exported {len(exported_paths)} individual plot(s) to:\n{output_dir}",
            )
        except Exception as e:
            self.logger.error(f"Error exporting individual plots: {str(e)}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to export individual plots:\n{str(e)}",
            )
    
    # List update methods
    def update_behavior_list(self):
        """Update the behavior list with available behaviors and colors.

        1.3.3+: the entire rebuild is wrapped in ``blockSignals`` so the
        ``setCheckState`` / ``setBackground`` calls below do not fire a
        cascade of ``itemChanged`` signals into
        ``on_behavior_selection_changed`` — previously that path could
        corrupt ``_behavior_visibility`` mid-rebuild and made re-checking
        a behaviour fail to bring it back onto the plot.
        """
        was_blocked = self.behavior_list.blockSignals(True)
        try:
            # Remember checkbox states
            checkbox_states = {}
            for i in range(self.behavior_list.count()):
                item = self.behavior_list.item(i)
                behavior = item.text()
                checkbox_states[behavior] = item.checkState()

            # Clear existing items
            self.behavior_list.clear()

            # Get all unique behaviors from the data
            all_behaviors = set()
            for file_path, df in self._data.items():
                if 'Event' in df.columns:
                    for behavior in df['Event'].dropna().unique():
                        # Skip invalid or system events
                        if behavior is None or behavior == "" or behavior == "nan" or behavior == "RecordingStart":
                            continue

                        behavior_str = str(behavior).strip()
                        if behavior_str and behavior_str != "nan":
                            all_behaviors.add(behavior_str)

            fixed_behaviors = []
            if self._fixed_behavior_order:
                seen = set()
                for behavior in self._fixed_behavior_order:
                    if behavior not in seen:
                        fixed_behaviors.append(behavior)
                        seen.add(behavior)
                all_behaviors = set(fixed_behaviors)

            # 1.3.3+: prune stale visibility / colour entries whose
            # behaviour is no longer present in the loaded data. Keeping
            # them around does no immediate harm but encourages
            # ghost-state confusion when the same RABET session loads,
            # clears, and re-loads heterogeneous CSV sets.
            for stale in [b for b in self._behavior_visibility if b not in all_behaviors]:
                self._behavior_visibility.pop(stale, None)
            for stale in [b for b in self._behavior_colors if b not in all_behaviors]:
                self._behavior_colors.pop(stale, None)

            # Order behaviors
            if fixed_behaviors:
                if self._custom_behavior_order:
                    fixed_set = set(fixed_behaviors)
                    ordered_behaviors = [
                        b for b in self._custom_behavior_order if b in fixed_set
                    ]
                    missing_behaviors = [
                        b for b in fixed_behaviors if b not in ordered_behaviors
                    ]
                    behaviors = ordered_behaviors + missing_behaviors
                else:
                    behaviors = fixed_behaviors
            elif self._custom_behavior_order:
                existing_behaviors = set(all_behaviors)
                ordered_behaviors = [b for b in self._custom_behavior_order if b in existing_behaviors]
                new_behaviors = sorted(list(existing_behaviors - set(ordered_behaviors)))
                behaviors = ordered_behaviors + new_behaviors
            else:
                behaviors = sorted(list(all_behaviors))

            # Generate colors
            self._generate_behavior_colors(behaviors)

            # Create list items
            for behavior in behaviors:
                item = QListWidgetItem(behavior)

                # Set checkbox
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                if behavior in checkbox_states:
                    item.setCheckState(checkbox_states[behavior])
                else:
                    item.setCheckState(Qt.CheckState.Checked if self._behavior_visibility.get(behavior, True) else Qt.CheckState.Unchecked)

                # Set background color
                color = self._behavior_colors[behavior]
                self._set_item_color(item, color)

                self.behavior_list.addItem(item)

            # Update custom order
            if behaviors:
                self._custom_behavior_order = behaviors
        finally:
            self.behavior_list.blockSignals(was_blocked)
    
    def _generate_behavior_colors(self, behaviors):
        """Generate colors for behaviors using current colormap settings."""
        # Get colormap
        if self._custom_color_map:
            cmap = None
        else:
            if not self._default_colormap or self._default_colormap not in matplotlib.colormaps:
                self._default_colormap = 'Set1'
            cmap = matplotlib.colormaps[self._default_colormap]
        
        # Determine if gradient colormap
        is_gradient = False
        if cmap:
            is_gradient = cmap.name in ['viridis', 'plasma', 'inferno', 'cividis']
        
        # Generate colors
        for i, behavior in enumerate(behaviors):
            if self._custom_color_map and behavior in self._custom_color_map:
                # Use custom color
                hex_color = self._custom_color_map[behavior]
                color = mcolors.hex2color(hex_color)
                color = tuple(int(c * 255) for c in color)
                self._behavior_colors[behavior] = color
            else:
                # Generate from colormap
                if cmap:
                    if is_gradient and len(behaviors) > 1:
                        norm_index = i / (len(behaviors) - 1) if len(behaviors) > 1 else 0.5
                        color_rgba = cmap(norm_index)
                    else:
                        color_rgba = cmap(i % cmap.N)
                    
                    color = (int(color_rgba[0]*255), int(color_rgba[1]*255), int(color_rgba[2]*255))
                else:
                    # Fallback color
                    hue = (i * 360 / len(behaviors)) % 360
                    rgb = colorsys.hsv_to_rgb(hue/360, 0.7, 0.9)
                    color = tuple(int(c * 255) for c in rgb)
                
                self._behavior_colors[behavior] = color
            
            # Set default visibility
            if behavior not in self._behavior_visibility:
                self._behavior_visibility[behavior] = True

    def update_file_list(self):
        """Update the file/individual list widget."""
        was_blocked = self.file_list.blockSignals(True)

        # Remember checkbox states
        checkbox_states = {}
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            file_path = item.data(Qt.ItemDataRole.UserRole)
            checkbox_states[file_path] = item.checkState()

        # Clear existing items
        self.file_list.clear()

        # Get list of files in display order
        file_paths = self._ordered_file_paths()

        # Update custom file order
        self._custom_file_order = file_paths

        # Create items for each file
        for i, file_path in enumerate(file_paths):
            # Create display name with number
            display_name = f"{i + 1}: {os.path.basename(file_path)}"

            # Create list item
            item = QListWidgetItem(display_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)

            # Set check state
            if file_path in checkbox_states:
                item.setCheckState(checkbox_states[file_path])
            else:
                is_visible = self._file_visibility.get(file_path, True)
                item.setCheckState(Qt.CheckState.Checked if is_visible else Qt.CheckState.Unchecked)

            # Store the full file path as data
            item.setData(Qt.ItemDataRole.UserRole, file_path)

            self.file_list.addItem(item)

        self.file_list.blockSignals(was_blocked)
    
    # Main plotting methods
    def _schedule_plot_update(self, reason=""):
        """Debounced raster redraw (Phase 4).

        Settings widgets (spin boxes, check boxes, selection toggles) can fire
        in rapid succession; redrawing on every one is wasteful. Coalesce them
        into a single redraw ~150 ms after the last change. Explicit Refresh,
        file loads and exports bypass this via update_plot() /
        _flush_pending_plot_update().
        """
        timer = getattr(self, "_plot_update_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self.update_plot)
            self._plot_update_timer = timer
        timer.start(150)
        if hasattr(self, "status_label") and self.status_label is not None:
            self.status_label.setText("Updating plot...")

    def _flush_pending_plot_update(self):
        """Run any debounced redraw now (e.g. before exporting an image)."""
        timer = getattr(self, "_plot_update_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
            self.update_plot()

    def update_plot(self):
        """Update the raster plot with current data and settings."""
        # A debounced update (if any) is now satisfied by this redraw.
        timer = getattr(self, "_plot_update_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
        # Check if data is available
        if not self._data:
            self.status_label.setText("No data loaded")
            self.canvas.fig.clear()
            self.canvas.axes = self.canvas.fig.add_subplot(111)
            self.canvas.axes.clear()
            self._draw_canvas_safe()
            return
        
        # Clear the current plot
        self.canvas.fig.clear()
        
        # Branch based on display mode
        if self._display_mode == "Overlay Behaviors":
            self.update_plot_overlay_mode()
        else:
            # For separate behaviors mode, recreate single axes
            self.canvas.axes = self.canvas.fig.add_subplot(111)
            self.update_plot_separate_mode()
        
        # Ensure canvas fills available space in auto-fit mode
        if self.auto_size_checkbox.isChecked():
            viewport = self.canvas_scroll.viewport()
            if viewport and viewport.width() > 0 and viewport.height() > 0:
                self.canvas.resize(viewport.size())

    def _file_recording_starts_and_max_time(self, selected_files):
        """Return recording starts and maximum finite displayed offset."""
        file_recording_starts = {}
        max_time = 0
        for file_path in selected_files:
            df = self._data[file_path]
            recording_start = self._get_recording_start(df, os.path.basename(file_path))
            file_recording_starts[file_path] = recording_start

            if 'Offset' in df.columns:
                try:
                    file_max_time = float(df['Offset'].max()) - recording_start
                    if np.isfinite(file_max_time):
                        max_time = max(max_time, file_max_time)
                except (TypeError, ValueError):
                    self.logger.warning(
                        "Could not calculate max Offset for %s",
                        os.path.basename(file_path),
                    )
        return file_recording_starts, max_time

    def _add_event_segments(
        self,
        ax,
        behavior_events,
        recording_start,
        y_pos,
        color,
        alpha,
        zorder,
    ):
        """Draw all events of one behavior as a single LineCollection.

        Replaces a per-event ``ax.plot`` loop with one matplotlib artist per
        behavior row instead of one per event - dramatically faster to build and
        render for dense data (perf 4-B). Per-event parsing and the warning on
        bad timestamps are unchanged. Returns the number of event bars drawn.

        Axis limits are set explicitly by the callers (``_configure_plot_axes``
        / ``_configure_individual_frame``), so ``add_collection`` not
        autoscaling is fine.
        """
        segments = []
        for _, event in behavior_events.iterrows():
            if 'Onset' not in event or 'Offset' not in event:
                continue
            try:
                onset = float(event['Onset']) - recording_start
                offset = float(event['Offset']) - recording_start
                if onset >= 0:
                    segments.append([(onset, y_pos), (offset, y_pos)])
            except (ValueError, TypeError) as e:
                self.logger.warning(
                    f"Invalid timestamp in event: {event}, error: {str(e)}"
                )
        if not segments:
            return 0
        collection = LineCollection(
            segments,
            linewidths=self._bar_height,
            colors=[tuple(color)],
            alpha=alpha,
            zorder=zorder,
        )
        collection.set_capstyle('butt')
        ax.add_collection(collection)
        return len(segments)

    def _plot_behavior_events_on_axis(
        self,
        ax,
        df,
        recording_start,
        behavior,
        y_pos,
        base_alpha,
        zorder,
    ):
        """Plot all events for one behavior on one y position."""
        if 'Event' not in df.columns:
            return 0

        behavior_events = df[df['Event'].astype(str) == behavior]
        if behavior_events.empty:
            return 0

        color_rgb = self._behavior_colors.get(behavior, (0, 0, 0))
        color = [c / 255 for c in color_rgb]
        alpha = self._behavior_alpha(behavior, base_alpha)
        return self._add_event_segments(
            ax, behavior_events, recording_start, y_pos, color, alpha, zorder
        )

    def _plot_grouped_rows_single_axes(
        self,
        selected_files,
        behavior_rows,
        behavior_order,
        base_alpha,
        status_prefix,
    ):
        """Plot grouped behavior rows into the main single axes."""
        if not behavior_rows:
            self.status_label.setText("No behaviors selected")
            self._draw_canvas_safe()
            return

        display_rows = [
            (file_path, row_index, row)
            for file_path in selected_files
            for row_index, row in enumerate(behavior_rows)
        ]
        row_positions = {
            display_index: len(display_rows) - display_index - 1
            for display_index in range(len(display_rows))
        }
        file_numbers = {
            file_path: file_index + 1
            for file_index, file_path in enumerate(selected_files)
        }
        zorders = self._behavior_zorders(behavior_order)
        file_recording_starts, max_time = self._file_recording_starts_and_max_time(
            selected_files
        )

        event_count = 0
        for display_index, (file_path, _row_index, row) in enumerate(display_rows):
            df = self._data[file_path]
            y_pos = row_positions[display_index]
            for behavior in row["behaviors"]:
                event_count += self._plot_behavior_events_on_axis(
                    self.canvas.axes,
                    df,
                    file_recording_starts[file_path],
                    behavior,
                    y_pos,
                    base_alpha,
                    zorders.get(behavior, 10),
                )

        rows_per_file = len(behavior_rows)
        if self._show_file_separators and len(selected_files) > 1:
            for file_index in range(1, len(selected_files)):
                boundary_index = file_index * rows_per_file
                boundary_y = (
                    row_positions[boundary_index]
                    + row_positions[boundary_index - 1]
                ) / 2
                self.canvas.axes.axhline(
                    boundary_y,
                    color=self._grid_color,
                    linestyle="-",
                    linewidth=1.0,
                    alpha=0.7,
                    zorder=1,
                )

        y_ticks = [row_positions[index] for index in range(len(display_rows))]
        y_labels = []
        for file_path, _row_index, row in display_rows:
            if len(selected_files) > 1 and self._show_file_label_numbers:
                y_labels.append(f"{file_numbers[file_path]}: {row['label']}")
            else:
                y_labels.append(row["label"])
        self.canvas.axes.set_yticks(y_ticks)
        self.canvas.axes.set_yticklabels(y_labels, fontsize=self._text_font_size)

        self._configure_plot_axes(max_time, len(display_rows))

        group_count = sum(1 for row in behavior_rows if row["is_group"])
        self.status_label.setText(
            f"{status_prefix}: {event_count} events across {len(selected_files)} file(s), "
            f"{len(behavior_rows)} row(s), {group_count} overlay group(s)"
        )

        self._draw_canvas_safe()

    def update_plot_separate_mode(self):
        """Update the plot in separate behaviors mode."""
        # 1.3.3+: visibility is now owned by on_behavior_selection_changed.
        # Previously this method re-derived ``_behavior_visibility`` from
        # ``item.checkState()`` at every replot, which could overwrite a
        # just-toggled True back to False if the checkState was read while
        # Qt was still mid-update (the reproducible "uncheck works, but
        # re-check does not bring the behaviour back" bug).
        behavior_order = self._behavior_order_from_list()
        visible_behaviors = self._visible_behaviors_from_list()
        
        if not visible_behaviors:
            self.status_label.setText("No behaviors selected")
            self._draw_canvas_safe()
            return

        selected_files = self._visible_file_paths()
        if not selected_files:
            self.status_label.setText("No files selected")
            self._draw_canvas_safe()
            return

        if self._has_active_overlay_groups(behavior_order):
            self._plot_grouped_rows_single_axes(
                selected_files,
                self._behavior_rows(behavior_order),
                behavior_order,
                0.8,
                "Separate mode overlay groups",
            )
            return

        if len(selected_files) > 1:
            self._plot_separate_files_mode(selected_files, visible_behaviors)
            return

        # Create behavior positions
        behavior_positions = {b: i for i, b in enumerate(reversed(visible_behaviors))}

        # Track plot statistics
        max_time = 0
        file_count = 0
        event_count = 0
        
        # Collect recording starts for all files
        file_recording_starts = {}
        for file_path in selected_files:
            df = self._data[file_path]
            file_name = os.path.basename(file_path)
            recording_start = self._get_recording_start(df, file_name)
            file_recording_starts[file_path] = recording_start
            
            # Get maximum time
            if 'Offset' in df.columns:
                file_max_time = df['Offset'].max() - recording_start
                max_time = max(max_time, file_max_time)
        
        # Plot events
        for file_path in selected_files:
            df = self._data[file_path]
            recording_start = file_recording_starts[file_path]
            
            for behavior in visible_behaviors:
                if 'Event' not in df.columns:
                    continue
                
                # Get events for this behavior
                behavior_events = df[df['Event'].astype(str) == behavior]
                
                if behavior_events.empty:
                    continue
                
                # Get color for this behavior
                color_rgb = self._behavior_colors.get(behavior, (0, 0, 0))
                color = [c/255 for c in color_rgb]
                
                # Calculate y position
                y_pos = behavior_positions[behavior]
                
                # Plot each event
                event_count += self._add_event_segments(
                    self.canvas.axes, behavior_events, recording_start,
                    y_pos, color, 0.8, 10,
                )
            
            file_count += 1
        
        # Set y-axis
        y_ticks = [behavior_positions[b] for b in visible_behaviors]
        y_labels = list(visible_behaviors)
        self.canvas.axes.set_yticks(y_ticks)
        self.canvas.axes.set_yticklabels(y_labels, fontsize=self._text_font_size)
        
        # Configure plot
        self._configure_plot_axes(max_time, len(visible_behaviors))
        
        # Update status
        self.status_label.setText(
            f"Displaying {event_count} events across {file_count} file(s) and {len(visible_behaviors)} behaviors"
        )
        
        # Draw the canvas
        self._draw_canvas_safe()

    def _plot_separate_files_mode(self, selected_files, visible_behaviors):
        """Plot separate behavior rows for each loaded file/individual."""
        display_rows = [
            (file_path, behavior)
            for file_path in selected_files
            for behavior in visible_behaviors
        ]
        row_positions = {
            row: len(display_rows) - row_index - 1
            for row_index, row in enumerate(display_rows)
        }
        file_numbers = {
            file_path: file_index + 1
            for file_index, file_path in enumerate(selected_files)
        }

        max_time = 0
        event_count = 0

        # Collect recording starts for all files.
        file_recording_starts = {}
        for file_path in selected_files:
            df = self._data[file_path]
            recording_start = self._get_recording_start(df, os.path.basename(file_path))
            file_recording_starts[file_path] = recording_start

            if 'Offset' in df.columns:
                file_max_time = df['Offset'].max() - recording_start
                max_time = max(max_time, file_max_time)

        # Plot each file on its own block of behavior rows.
        for file_path in selected_files:
            df = self._data[file_path]
            recording_start = file_recording_starts[file_path]

            if 'Event' not in df.columns:
                continue

            for behavior in visible_behaviors:
                behavior_events = df[df['Event'].astype(str) == behavior]
                if behavior_events.empty:
                    continue

                color_rgb = self._behavior_colors.get(behavior, (0, 0, 0))
                color = [c / 255 for c in color_rgb]
                y_pos = row_positions[(file_path, behavior)]

                event_count += self._add_event_segments(
                    self.canvas.axes, behavior_events, recording_start,
                    y_pos, color, 0.8, 10,
                )

        # Add subtle separators between files/individuals.
        rows_per_file = len(visible_behaviors)
        if self._show_file_separators:
            for file_index in range(1, len(selected_files)):
                boundary_row = display_rows[file_index * rows_per_file]
                previous_row = display_rows[file_index * rows_per_file - 1]
                boundary_y = (row_positions[boundary_row] + row_positions[previous_row]) / 2
                self.canvas.axes.axhline(
                    boundary_y,
                    color=self._grid_color,
                    linestyle="-",
                    linewidth=1.0,
                    alpha=0.7,
                    zorder=1,
                )

        # Set y-axis labels. The file list shows which filename belongs to each number.
        y_ticks = [row_positions[row] for row in display_rows]
        if self._show_file_label_numbers:
            y_labels = [
                f"{file_numbers[file_path]}: {behavior}"
                for file_path, behavior in display_rows
            ]
        else:
            y_labels = [behavior for _file_path, behavior in display_rows]
        self.canvas.axes.set_yticks(y_ticks)
        self.canvas.axes.set_yticklabels(y_labels, fontsize=self._text_font_size)

        self._configure_plot_axes(max_time, len(display_rows))

        self.status_label.setText(
            f"Displaying {event_count} events across {len(selected_files)} individual file(s) "
            f"and {len(visible_behaviors)} behavior(s)"
        )

        self._draw_canvas_safe()
    
    def update_plot_overlay_mode(self):
        """Update the plot in overlay mode."""
        # 1.3.3+: visibility is owned by on_behavior_selection_changed
        # (see note in update_plot_separate_mode). Read from the
        # authoritative ``_behavior_visibility`` dict directly.
        behavior_order = self._behavior_order_from_list()
        visible_behaviors = self._visible_behaviors_from_list()
        
        # Get selected files
        selected_files = self._visible_file_paths()
        
        if not selected_files:
            self.status_label.setText("No files selected")
            self._draw_canvas_safe()
            return
        
        if not visible_behaviors:
            self.status_label.setText("No behaviors selected")
            self._draw_canvas_safe()
            return
        
        # Clear the figure
        self.canvas.fig.clear()

        if self._has_active_overlay_groups(behavior_order):
            behavior_rows = self._behavior_rows(behavior_order)
            if self._individual_frames:
                self._plot_overlay_grouped_individual_frames(
                    selected_files,
                    behavior_rows,
                    behavior_order,
                )
            else:
                self.canvas.axes = self.canvas.fig.add_subplot(111)
                self._plot_grouped_rows_single_axes(
                    selected_files,
                    behavior_rows,
                    behavior_order,
                    0.9,
                    "Overlay mode groups",
                )
            return
        
        if self._individual_frames:
            self._plot_overlay_individual_frames(selected_files, visible_behaviors)
        else:
            self.canvas.axes = self.canvas.fig.add_subplot(111)
            self._plot_overlay_single_frame(selected_files, visible_behaviors)
    
    def _plot_overlay_single_frame(self, selected_files, visible_behaviors):
        """Plot overlay mode with a single shared frame."""
        # Create file positions
        file_positions = {f: len(selected_files) - i - 1 for i, f in enumerate(selected_files)}
        
        # Track statistics
        max_time = 0
        event_count = 0
        
        # Calculate recording starts and max time
        file_recording_starts = {}
        for file_path in selected_files:
            df = self._data[file_path]
            recording_start = self._get_recording_start(df, os.path.basename(file_path))
            file_recording_starts[file_path] = recording_start
            
            if 'Offset' in df.columns:
                file_max_time = df['Offset'].max() - recording_start
                max_time = max(max_time, file_max_time)
        
        # Plot behaviors in reverse order for proper stacking
        for behavior_idx, behavior in enumerate(reversed(visible_behaviors)):
            z_order = behavior_idx + 1
            
            for file_path in selected_files:
                df = self._data[file_path]
                recording_start = file_recording_starts[file_path]
                y_pos = file_positions[file_path]
                
                if 'Event' in df.columns:
                    behavior_events = df[df['Event'].astype(str) == behavior]
                    
                    if behavior_events.empty:
                        continue
                    
                    color_rgb = self._behavior_colors.get(behavior, (0, 0, 0))
                    color = [c/255 for c in color_rgb]
                    
                    event_count += self._add_event_segments(
                        self.canvas.axes, behavior_events, recording_start,
                        y_pos, color, 0.9, 10 + z_order,
                    )
        
        # Set y-axis
        ordered_by_position = sorted(selected_files, key=lambda path: file_positions[path])
        y_ticks = [file_positions[file_path] for file_path in ordered_by_position]
        y_labels = [str(selected_files.index(file_path) + 1) for file_path in ordered_by_position]
        self.canvas.axes.set_yticks(y_ticks)
        self.canvas.axes.set_yticklabels(y_labels, fontsize=self._text_font_size)
        
        # Configure plot
        self._configure_plot_axes(max_time, len(selected_files))
        
        # Update status
        self.status_label.setText(
            f"Overlay mode: {event_count} events across {len(selected_files)} file(s) with {len(visible_behaviors)} behavior(s)"
        )
        
        # Draw the canvas
        self._draw_canvas_safe()

    def _plot_overlay_grouped_individual_frames(
        self,
        selected_files,
        behavior_rows,
        behavior_order,
    ):
        """Plot overlay groups inside one subplot per file/individual."""
        if not behavior_rows:
            self.status_label.setText("No behaviors selected")
            self._draw_canvas_safe()
            return

        num_files = len(selected_files)
        rows_per_file = len(behavior_rows)
        row_height_pixels = self.frame_height_spinbox.value()

        top_margin_pixels = 20
        bottom_margin_pixels = 50
        between_plots_pixels = 40
        frame_height_pixels = max(row_height_pixels * rows_per_file, row_height_pixels)
        total_height_pixels = (
            top_margin_pixels
            + (frame_height_pixels * num_files)
            + (between_plots_pixels * (num_files - 1))
            + bottom_margin_pixels
        )

        current_width_inches = self.canvas.fig.get_figwidth()
        current_dpi = self.canvas.fig.dpi if self.canvas.fig.dpi else 100
        total_height_inches = total_height_pixels / current_dpi
        frame_height_inches = frame_height_pixels / current_dpi
        top_margin_inches = top_margin_pixels / current_dpi
        between_plots_inches = between_plots_pixels / current_dpi

        if self.auto_size_checkbox.isChecked():
            self.canvas.fig.set_size_inches(current_width_inches, total_height_inches)
            fig_height_inches = total_height_inches
        else:
            fig_height_inches = self.canvas.fig.get_figheight()

        self.canvas.fig.clear()
        axes_list = []
        for index in range(num_files):
            top_position = top_margin_inches + index * (
                frame_height_inches + between_plots_inches
            )
            bottom_position = fig_height_inches - top_position - frame_height_inches
            bottom_norm = max(0, bottom_position / fig_height_inches)
            height_norm = min(1, frame_height_inches / fig_height_inches)
            if bottom_norm + height_norm > 1.01 or bottom_norm < -0.01:
                continue
            axes_list.append(self.canvas.fig.add_axes([0.12, bottom_norm, 0.86, height_norm]))

        file_recording_starts, max_time = self._file_recording_starts_and_max_time(
            selected_files
        )
        zorders = self._behavior_zorders(behavior_order)
        row_positions = {
            row_index: rows_per_file - row_index - 1
            for row_index in range(rows_per_file)
        }
        y_ticks = [row_positions[row_index] for row_index in range(rows_per_file)]
        y_labels = [row["label"] for row in behavior_rows]
        total_event_count = 0

        for file_idx, (file_path, ax) in enumerate(zip(selected_files, axes_list, strict=False)):
            df = self._data[file_path]
            for row_index, row in enumerate(behavior_rows):
                y_pos = row_positions[row_index]
                for behavior in row["behaviors"]:
                    total_event_count += self._plot_behavior_events_on_axis(
                        ax,
                        df,
                        file_recording_starts[file_path],
                        behavior,
                        y_pos,
                        0.9,
                        zorders.get(behavior, 10),
                    )

            self._configure_grouped_individual_frame(
                ax,
                file_idx,
                num_files,
                max_time,
                rows_per_file,
                y_ticks,
                y_labels,
            )
            ax.set_ylabel(
                str(file_idx + 1),
                fontweight='bold',
                fontsize=self._text_font_size,
                rotation=0,
                ha='right',
                va='center',
            )

        self._draw_canvas_safe()
        group_count = sum(1 for row in behavior_rows if row["is_group"])
        self.status_label.setText(
            f"Overlay mode (individual frames): {total_event_count} events across "
            f"{num_files} file(s), {rows_per_file} row(s), {group_count} overlay group(s)"
        )
    
    def _plot_overlay_individual_frames(self, selected_files, visible_behaviors):
        """Plot overlay mode with individual frames for each file."""
        num_files = len(selected_files)
        frame_height_pixels = self.frame_height_spinbox.value()
        
        # Define spacing in pixels
        top_margin_pixels = 20
        bottom_margin_pixels = 50
        between_plots_pixels = 40
        
        # Calculate total height needed
        total_height_pixels = (
            top_margin_pixels + 
            (frame_height_pixels * num_files) + 
            (between_plots_pixels * (num_files - 1)) + 
            bottom_margin_pixels
        )
        
        # Get current figure properties
        current_width_inches = self.canvas.fig.get_figwidth()
        current_dpi = self.canvas.fig.dpi if self.canvas.fig.dpi else 100
        
        # Convert to inches
        total_height_inches = total_height_pixels / current_dpi
        frame_height_inches = frame_height_pixels / current_dpi
        top_margin_inches = top_margin_pixels / current_dpi
        between_plots_inches = between_plots_pixels / current_dpi
        
        # Update figure size if auto-fit is enabled
        if self.auto_size_checkbox.isChecked():
            self.canvas.fig.set_size_inches(current_width_inches, total_height_inches)
            fig_height_inches = total_height_inches
        else:
            fig_height_inches = self.canvas.fig.get_figheight()
        
        # Clear any existing subplots
        self.canvas.fig.clear()
        
        # Create subplots with manual positioning
        axes_list = []
        
        for i in range(num_files):
            # Calculate position
            top_position = top_margin_inches + i * (frame_height_inches + between_plots_inches)
            bottom_position = fig_height_inches - top_position - frame_height_inches
            
            # Normalize positions
            left = 0.1
            right = 0.98
            bottom_norm = max(0, bottom_position / fig_height_inches)
            height_norm = min(1, frame_height_inches / fig_height_inches)
            width = right - left
            
            # Skip if outside visible area
            if bottom_norm + height_norm > 1.01 or bottom_norm < -0.01:
                continue
            
            # Create subplot
            ax = self.canvas.fig.add_axes([left, bottom_norm, width, height_norm])
            axes_list.append(ax)
        
        # Track statistics
        max_time = 0
        total_event_count = 0
        
        # Calculate recording starts
        file_recording_starts = {}
        for file_path in selected_files:
            df = self._data[file_path]
            recording_start = self._get_recording_start(df, os.path.basename(file_path))
            file_recording_starts[file_path] = recording_start
            
            if 'Offset' in df.columns:
                file_max_time = df['Offset'].max() - recording_start
                max_time = max(max_time, file_max_time)
        
        # Plot each file
        for file_idx, (file_path, ax) in enumerate(zip(selected_files, axes_list, strict=False)):
            df = self._data[file_path]
            recording_start = file_recording_starts[file_path]
            event_count = 0
            
            # Plot behaviors in reverse order
            for behavior_idx, behavior in enumerate(reversed(visible_behaviors)):
                z_order = behavior_idx + 1
                
                if 'Event' in df.columns:
                    behavior_events = df[df['Event'].astype(str) == behavior]
                    
                    if behavior_events.empty:
                        continue
                    
                    color_rgb = self._behavior_colors.get(behavior, (0, 0, 0))
                    color = [c/255 for c in color_rgb]
                    
                    event_count += self._add_event_segments(
                        ax, behavior_events, recording_start,
                        0, color, 0.9, 10 + z_order,
                    )
            
            total_event_count += event_count
            
            # Configure this subplot
            self._configure_individual_frame(ax, file_idx, num_files, max_time)
            
            # Set y-axis label
            ax.set_ylabel(
                str(file_idx + 1),
                fontweight='bold',
                fontsize=self._text_font_size,
                rotation=0,
                ha='right',
                va='center',
            )
        
        # Draw with warning suppression
        self._draw_canvas_safe()
        
        # Update status
        self.status_label.setText(
            f"Overlay mode (individual frames): {total_event_count} events across {num_files} file(s) with {len(visible_behaviors)} behavior(s)"
        )

    def _configure_grouped_individual_frame(
        self,
        ax,
        file_idx,
        num_files,
        max_time,
        num_rows,
        y_ticks,
        y_labels,
    ):
        """Configure an individual overlay-group subplot."""
        display_max_time = self._display_time_limit()
        display_ticks = self._display_ticks(display_max_time)
        ax.set_xlim(0, display_max_time)
        ax.set_xticks(display_ticks)

        if file_idx == num_files - 1:
            x_label = 'Time (minutes)' if self._time_unit == "Minutes" else 'Time (seconds)'
            ax.set_xlabel(
                x_label,
                fontweight='bold',
                fontsize=self._text_font_size,
            )
            ax.set_xticklabels(
                self._format_time_tick_labels(display_ticks),
                fontsize=self._text_font_size,
            )
            for label in ax.get_xticklabels():
                label.set_fontweight('bold')
                label.set_fontsize(self._text_font_size)
        else:
            ax.set_xticklabels([])
            ax.set_xlabel('')

        ax.set_ylim(-0.5, num_rows - 0.5)
        ax.set_yticks(y_ticks)
        ax.set_yticklabels(y_labels, fontsize=self._text_font_size)
        for label in ax.get_yticklabels():
            label.set_fontweight('bold')
            label.set_fontsize(self._text_font_size)

        self._apply_border_style(ax)
        ax.tick_params(
            axis='both',
            which='major',
            length=6,
            width=2.5,
            labelsize=self._text_font_size,
            zorder=100,
        )
        self._apply_grid(ax)
        ax.patch.set_alpha(0)
    
    def _configure_individual_frame(self, ax, file_idx, num_files, max_time):
        """Configure an individual subplot frame."""
        # Set x-axis limits
        display_max_time = self._display_time_limit()
        ax.set_xlim(0, display_max_time)

        # Create x-tick intervals
        display_ticks = self._display_ticks(display_max_time)
        ax.set_xticks(display_ticks)

        # Only show x-axis labels on the bottom subplot
        if file_idx == num_files - 1:
            if self._time_unit == "Minutes":
                ax.set_xlabel(
                    'Time (minutes)',
                    fontweight='bold',
                    fontsize=self._text_font_size,
                )
            else:
                ax.set_xlabel(
                    'Time (seconds)',
                    fontweight='bold',
                    fontsize=self._text_font_size,
                )
            display_tick_labels = self._format_time_tick_labels(display_ticks)

            ax.set_xticklabels(
                display_tick_labels,
                fontsize=self._text_font_size,
            )

            for label in ax.get_xticklabels():
                label.set_fontweight('bold')
                label.set_fontsize(self._text_font_size)
        else:
            ax.set_xticklabels([])
            ax.set_xlabel('')

        # Set y-axis limits
        y_range = 0.5
        ax.set_ylim(-y_range, y_range)
        ax.set_yticks([])
        
        self._apply_border_style(ax)

        ax.tick_params(axis='both', which='major',
                      length=6, width=2.5, labelsize=self._text_font_size, zorder=100)

        self._apply_grid(ax)
        ax.patch.set_alpha(0)
    
    def _configure_plot_axes(self, max_time, num_rows):
        """Configure plot axes, limits, and labels for single frame mode."""
        # Max Range is a user-requested display cap, not a lower bound from data length.
        display_max_time = self._display_time_limit()

        # Create ticks
        display_ticks = self._display_ticks(display_max_time)

        # Set labels based on time unit
        if self._time_unit == "Minutes":
            x_label = 'Time (minutes)'
        else:
            x_label = 'Time (seconds)'
        display_tick_labels = self._format_time_tick_labels(display_ticks)
        
        # Configure axes
        self.canvas.axes.set_xlim(0, display_max_time)
        self.canvas.axes.set_xticks(display_ticks)
        self.canvas.axes.set_xticklabels(
            display_tick_labels,
            fontsize=self._text_font_size,
        )
        self.canvas.axes.set_ylim(-0.5, num_rows - 0.5)
        self.canvas.axes.set_xlabel(
            x_label,
            fontweight='bold',
            fontsize=self._text_font_size,
        )

        # Make text bold
        for label in self.canvas.axes.get_xticklabels():
            label.set_fontweight('bold')
            label.set_fontsize(self._text_font_size)
        for label in self.canvas.axes.get_yticklabels():
            label.set_fontweight('bold')
            label.set_fontsize(self._text_font_size)

        self._apply_border_style(self.canvas.axes)

        self.canvas.axes.tick_params(axis='both', which='major',
                                    length=6, width=2.5,
                                    labelsize=self._text_font_size, zorder=100)

        self._apply_grid(self.canvas.axes)
        
        # Draw with warning suppression
        self._draw_canvas_safe()
    
    # Override methods for proper event handling
    def resizeEvent(self, event):
        """Handle resize events to ensure proper canvas display."""
        super().resizeEvent(event)
        if hasattr(self, 'auto_size_checkbox') and hasattr(self, 'canvas'):
            if self.auto_size_checkbox.isChecked():
                self.canvas.updateGeometry()
    
    def showEvent(self, event):
        """Handle show events to ensure proper initial display."""
        super().showEvent(event)
        if hasattr(self, 'canvas'):
            self.canvas.updateGeometry()
            if hasattr(self, '_data') and self._data:
                QTimer.singleShot(100, self.update_plot)


class VisualizationView(QWidget):
    """
    View for visualization of annotation data.
    Includes raster plots and other visualization tools.
    
    Signals:
        files_dropped: Emitted when files are dropped (list of file paths)
    """
    
    files_dropped = Signal(list)
    clear_data_requested = Signal()
    custom_colormap_save_requested = Signal(str, dict)
    selected_colormap_changed = Signal(str)
    plot_save_directory_changed = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing VisualizationView")
        
        # Enable drag and drop
        self.setAcceptDrops(True)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface."""
        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 0)
        self.layout.setSpacing(3)
        
        # Title
        self.title_label = QLabel("Drop CSV annotation files here for visualization")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setMaximumHeight(30)
        self.layout.addWidget(self.title_label, 0)
        
        # Add raster plot widget
        self.raster_plot = RasterPlotWidget()
        self.raster_plot.files_selected.connect(self._on_files_selected)
        self.raster_plot.clear_data_requested.connect(self.clear_data_requested.emit)
        self.raster_plot.custom_colormap_save_requested.connect(
            self.custom_colormap_save_requested.emit
        )
        self.raster_plot.selected_colormap_changed.connect(
            self.selected_colormap_changed.emit
        )
        self.raster_plot.plot_save_directory_changed.connect(
            self.plot_save_directory_changed.emit
        )
        self.layout.addWidget(self.raster_plot, 10)

    def set_data(self, data_dict):
        """Set the annotation data for visualization."""
        self.raster_plot.set_data(data_dict)

    def _on_files_selected(self, file_paths):
        """Forward files chosen from the toolbar to the controller path."""
        self.files_dropped.emit(file_paths)
    
    def set_custom_color_map(self, color_map):
        """Set a custom color mapping for behaviors."""
        self.raster_plot.set_custom_color_map(color_map)
    
    def add_custom_colormaps_to_dropdown(self, colormap_dict):
        """Add custom color maps to the main colormap dropdown."""
        self.raster_plot.add_custom_colormaps_to_dropdown(colormap_dict)

    def select_custom_colormap(self, colormap_name):
        """Select a custom color map by dropdown name."""
        return self.raster_plot.select_custom_colormap(colormap_name)

    def set_last_plot_save_directory(self, directory):
        """Restore the last directory used for plot exports."""
        self.raster_plot.set_last_plot_save_directory(directory)
    
    def dragEnterEvent(self, event):
        """Handle drag enter events."""
        if event.mimeData().hasUrls():
            # Check if all URLs are CSV files
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if not file_path.lower().endswith('.csv'):
                    event.ignore()
                    return

            event.acceptProposedAction()
            self.logger.debug("Drag enter event accepted for CSV files")
            return
        event.ignore()

    def dragMoveEvent(self, event):
        """Keep CSV drags accepted throughout the Visualization view."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if not file_path.lower().endswith('.csv'):
                    event.ignore()
                    return
            event.acceptProposedAction()
            return
        event.ignore()
    
    def dropEvent(self, event):
        """Handle drop events."""
        # Check if this view is current
        from PySide6.QtWidgets import QApplication
        main_window = None
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, 'stacked_widget') and hasattr(widget, '_view_index'):
                main_window = widget
                break
        
        # Check if this view is the current view
        is_current = False
        if main_window and hasattr(main_window, 'stacked_widget'):
            current_widget = main_window.stacked_widget.currentWidget()
            if current_widget == self:
                is_current = True
        
        if not is_current:
            self.logger.warning("Drop event ignored - visualization view is not the current view")
            event.ignore()
            return
        
        # Get file paths from URLs
        file_paths = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            file_paths.append(file_path)
        
        if file_paths:
            self.logger.info(f"Received dropped files in visualization view: {file_paths}")
            self.files_dropped.emit(file_paths)
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def showEvent(self, event):
        """Handle show event for the visualization view."""
        super().showEvent(event)
        if hasattr(self, 'raster_plot'):
            self.raster_plot.canvas.updateGeometry()
