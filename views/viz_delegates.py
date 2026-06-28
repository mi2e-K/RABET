# views/viz_delegates.py - Shared table-cell visualization delegate (1.4.0).
#
# One configurable QStyledItemDelegate reused by the analysis tables so they
# read as visuals, not walls of numbers — without scattering bespoke drawing
# code across dialogs. Tints are semi-transparent so they work in light AND
# dark themes (drawn over the host cell background); text uses the palette
# colour so it stays readable in both.
#
# Each cell's numeric value is read from Qt.ItemDataRole.UserRole; cells with a
# non-numeric / NaN value are left unshaded.

from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QStyle, QStyledItemDelegate


class CellVizDelegate(QStyledItemDelegate):
    """Paints a heatmap tint or a data bar behind a table cell's text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind = "none"          # 'diverging' | 'sequential' | 'databar' | 'none'
        self.center = 0.0           # diverging midpoint
        self.scale = 1.0            # diverging half-range, or sequential/databar span
        self.vmin = 0.0             # sequential/databar lower bound
        self.accent = (42, 120, 214)

    def configure(self, kind, *, center=0.0, scale=1.0, vmin=0.0, accent=(42, 120, 214)):
        self.kind = kind
        self.center = center
        self.scale = scale if scale and scale > 0 else 1.0
        self.vmin = vmin
        self.accent = accent
        return self

    def paint(self, painter, option, index):
        value = index.data(Qt.ItemDataRole.UserRole)
        rect = option.rect
        painter.save()

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.fillRect(rect, option.palette.highlight())

        if isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)):
            if self.kind == "diverging":
                delta = value - self.center
                alpha = int(min(170, abs(delta) / self.scale * 170))
                tint = QColor(200, 40, 40, alpha) if delta >= 0 else QColor(40, 90, 200, alpha)
                painter.fillRect(rect, tint)
            elif self.kind == "sequential":
                frac = min(1.0, max(0.0, (value - self.vmin) / self.scale))
                painter.fillRect(rect, QColor(*self.accent, int(frac * 150)))
            elif self.kind == "databar":
                frac = min(1.0, max(0.0, (value - self.vmin) / self.scale))
                bar_w = max(0.0, rect.width() * frac - 2)
                bar = QRectF(rect.left() + 1, rect.top() + rect.height() * 0.18,
                             bar_w, rect.height() * 0.64)
                painter.fillRect(bar, QColor(*self.accent, 90))

        text = index.data(Qt.ItemDataRole.DisplayRole)
        pen = (option.palette.highlightedText() if selected else option.palette.text()).color()
        painter.setPen(pen)
        painter.setFont(option.font)  # honour bold/size set on the item
        align = index.data(Qt.ItemDataRole.TextAlignmentRole)
        align = int(align) if align is not None else int(Qt.AlignmentFlag.AlignCenter)
        painter.drawText(rect.adjusted(5, 0, -5, 0), align, "" if text is None else str(text))
        painter.restore()
