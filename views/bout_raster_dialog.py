# views/bout_raster_dialog.py - Reusable bout-raster canvas widget.
#
# Draws, for one behaviour, one timeline row per animal with each bout a block
# (width = duration, height/colour = events in the bout). Embedded as the
# "Raster" tab of the Bout Analysis dialog (1.4.0). Pure-visual; bout numbers
# come from models.bout_analysis.

from __future__ import annotations

from typing import List, Tuple

from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


def _size_color(n):
    """Light→dark blue by bout size (1 → many events)."""
    t = min(1.0, (n - 1) / 7.0)
    r = int(181 + (24 - 181) * t)
    g = int(212 + (95 - 212) * t)
    b = int(244 + (165 - 244) * t)
    return QColor(r, g, b)


class _RasterCanvas(QWidget):
    """Custom-painted per-animal bout raster."""

    def __init__(self):
        super().__init__()
        self._data: List[Tuple[str, list]] = []   # (animal_id, [Bout, ...])
        self._max_t = 300.0
        self._row_h = 34
        self.setMinimumHeight(120)

    def set_data(self, data, max_t):
        self._data = data
        self._max_t = max(1.0, max_t)
        self.setMinimumHeight(40 + len(data) * self._row_h + 6)
        self.updateGeometry()
        self.update()

    def paintEvent(self, _event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        qp.fillRect(self.rect(), QColor(250, 250, 250))
        left, top, right_pad = 96, 16, 16
        plot_w = max(10, self.width() - left - right_pad)
        rh = self._row_h
        axis_col = QColor(150, 150, 150)
        # Use the widget's inherited UI font (sized down) rather than an
        # empty-family QFont, which on Windows resolves to the legacy bitmap
        # "MS Sans Serif" and triggers a harmless DirectWrite warning.
        label_font = self.font()
        label_font.setPointSize(8)
        qp.setFont(label_font)
        bottom = top + len(self._data) * rh
        t = 0
        while t <= self._max_t:
            x = int(left + t / self._max_t * plot_w)
            qp.setPen(QPen(QColor(220, 220, 220)))
            qp.drawLine(x, top, x, bottom)
            qp.setPen(QPen(axis_col))
            qp.drawText(x - 8, bottom + 14, f"{t}s")
            t += 60
        for i, (animal_id, bouts) in enumerate(self._data):
            base = top + i * rh + rh - 6
            qp.setPen(QPen(QColor(80, 80, 80)))
            qp.drawText(4, base, str(animal_id))
            qp.setPen(QPen(QColor(150, 150, 150)))
            qp.drawLine(left, base, left + plot_w, base)
            for bt in bouts:
                x = int(left + bt.start / self._max_t * plot_w)
                w = max(2, int((bt.end - bt.start) / self._max_t * plot_w))
                h = min(rh - 8, 4 + bt.n_events * 3)
                col = _size_color(bt.n_events)
                qp.setPen(QPen(col.darker(130)))
                qp.setBrush(QBrush(col))
                qp.drawRect(x, base - h, w, h)
        qp.end()
