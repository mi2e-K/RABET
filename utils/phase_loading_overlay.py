"""Minimal segmented loading overlay for first-time heavy tab construction."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


RABET_PROGRESS_PALETTE = (
    "#28FEDA",
    "#1BE6D8",
    "#00CED5",
    "#1FC5CF",
    "#00B5D1",
    "#029CC9",
    "#0B7FC0",
    "#1F5FBA",
    "#24208E",
    "#3A46B6",
    "#5C31B1",
    "#801EAC",
    "#9B0BA0",
    "#B12CAE",
    "#BC0D93",
    "#D41FA6",
    "#F22A9D",
    "#F43E8B",
    "#F94E7B",
    "#FB626A",
    "#FC795C",
    "#FD9150",
    "#FEAC49",
    "#FDE62E",
)


class PhaseLoadingOverlay(QWidget):
    """A tab-area overlay with a compact 24-segment RABET palette indicator."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._title = "Preparing"
        self._progress = 8
        self._pulse = 0.0

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._advance)

        self.hide()

    def show_loader(self, title, detail=None, phases=None):
        self._title = title or "Preparing"
        self._progress = 8
        self._pulse = 0.0
        if self.parentWidget() is not None:
            self.resize(self.parentWidget().size())
        self.raise_()
        self.show()
        self._timer.start()
        self.update()

    def hide_loader(self):
        self._timer.stop()
        self.hide()

    def finish_loader(self):
        """Show a completed ring before the overlay is hidden."""
        self._progress = 100
        self.update()

    def _advance(self):
        self._pulse = (self._pulse + 0.035) % 1.0
        if self._progress < 88:
            self._progress += 2
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(18, 20, 22, 142))

        bounds = self.rect()
        panel = QRectF(
            (bounds.width() - 230) / 2,
            (bounds.height() - 168) / 2,
            230,
            168,
        )

        self._draw_panel(painter, panel)
        self._draw_segmented_ring(painter, panel)
        self._draw_title(painter, panel)

    def _draw_panel(self, painter, panel):
        shadow = QRectF(panel)
        shadow.translate(0, 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 82))
        painter.drawRoundedRect(shadow, 8, 8)

        painter.setPen(QPen(QColor(104, 122, 132, 132), 1))
        painter.setBrush(QColor(27, 31, 34, 236))
        painter.drawRoundedRect(panel, 8, 8)

    def _draw_segmented_ring(self, painter, panel):
        center = QPointF(panel.center().x(), panel.top() + 70)
        radius = 42
        segment_count = len(RABET_PROGRESS_PALETTE)
        active_segments = max(1, min(segment_count, math.ceil(segment_count * self._progress / 100.0)))

        for index, hex_color in enumerate(RABET_PROGRESS_PALETTE):
            angle = -90 + index * (360 / segment_count)
            span = 360 / segment_count * 0.56
            rect = QRectF(
                center.x() - radius,
                center.y() - radius,
                radius * 2,
                radius * 2,
            )
            if index < active_segments:
                color = QColor(hex_color)
                if index == active_segments - 1 and self._progress < 100:
                    color.setAlpha(168 + int(70 * (0.5 + 0.5 * math.sin(self._pulse * math.tau))))
                else:
                    color.setAlpha(235)
                width = 6
            else:
                color = QColor(84, 98, 106, 92)
                width = 5

            pen = QPen(color, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(rect, int(-angle * 16), int(-span * 16))

        inner = QRectF(center.x() - 25, center.y() - 25, 50, 50)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(13, 17, 20, 185))
        painter.drawEllipse(inner)

    def _draw_title(self, painter, panel):
        font = QFont("Segoe UI", 12)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(244, 248, 250))
        painter.drawText(
            QRectF(panel.left() + 18, panel.bottom() - 47, panel.width() - 36, 28),
            Qt.AlignmentFlag.AlignCenter,
            self._title,
        )
