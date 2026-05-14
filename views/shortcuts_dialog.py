"""Keyboard shortcuts reference dialog.

A small modal dialog listing every keyboard shortcut RABET responds to,
plus the user's current key → behaviour mappings. Triggered from
``Help -> Show Shortcuts``.
"""
from __future__ import annotations

import logging
from typing import Iterable, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


# Order: (shortcut, action). The list is intentionally hand-maintained so
# unmapped or accelerator-less actions can still appear here for the user.
_BUILTIN_SHORTCUTS: list[Tuple[str, str]] = [
    ("Space", "Toggle video play / pause"),
    ("→", "Step forward by the configured step size"),
    ("←", "Step backward by the configured step size"),
    ("Ctrl + Z", "Undo the most recently recorded annotation"),
    ("F1 / Help → Show Shortcuts", "Open this shortcuts dialog"),
    ("(any mapped key)", "Tag the corresponding behaviour while recording"),
]


class ShortcutsDialog(QDialog):
    """Display a read-only reference of all keyboard shortcuts."""

    def __init__(self, parent=None, mapped_keys: Iterable[Tuple[str, str]] = ()):
        """
        Args:
            parent: Parent widget.
            mapped_keys: Iterable of ``(key, behavior)`` pairs taken from
                the action map. Listed under the *Action map* section.
        """
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)

        self.setWindowTitle("Keyboard Shortcuts")
        self.resize(520, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        intro = QLabel(
            "RABET recognises the following keyboard shortcuts. "
            "Behaviour keys come from the active action map and can be "
            "edited from the Action Map panel."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # Built-in shortcuts section
        builtins_label = QLabel("Built-in shortcuts")
        builtins_label.setStyleSheet("font-weight: bold; margin-top: 4px;")
        layout.addWidget(builtins_label)

        builtins_table = self._make_two_column_table()
        self._populate_table(builtins_table, _BUILTIN_SHORTCUTS)
        layout.addWidget(builtins_table)

        # Action map section
        mapped_pairs = list(mapped_keys or ())
        mapped_label = QLabel(
            "Action map" if mapped_pairs
            else "Action map (no behaviour keys are currently mapped)"
        )
        mapped_label.setStyleSheet("font-weight: bold; margin-top: 4px;")
        layout.addWidget(mapped_label)

        mapped_table = self._make_two_column_table()
        # Sort by key for deterministic presentation.
        mapped_pairs.sort(key=lambda pair: pair[0].lower())
        self._populate_table(mapped_table, mapped_pairs)
        layout.addWidget(mapped_table)

        # Close button
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        # ``Close`` is the only button - connect its clicked() to accept().
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.clicked.connect(self.accept)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _make_two_column_table(self) -> QTableWidget:
        table = QTableWidget(0, 2, self)
        table.setHorizontalHeaderLabels(["Shortcut", "Action"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        return table

    def _populate_table(
        self,
        table: QTableWidget,
        rows: Iterable[Tuple[str, str]],
    ) -> None:
        rows = list(rows)
        table.setRowCount(len(rows))
        mono = QFont()
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setFamily("monospace")
        for r, (shortcut, action) in enumerate(rows):
            key_item = QTableWidgetItem(shortcut)
            key_item.setFont(mono)
            key_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(r, 0, key_item)
            table.setItem(r, 1, QTableWidgetItem(action))
