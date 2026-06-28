"""Shared figure-export helpers for analysis dialogs."""

from __future__ import annotations

import math
import os

from PySide6.QtCore import QMarginsF, QPoint, QRect, QSize, QSizeF
from PySide6.QtGui import (
    QColor,
    QImage,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
)
from PySide6.QtSvg import QSvgGenerator

from utils.auto_close_message import AutoCloseMessageBox

FIGURE_EXPORT_FILTER = (
    "PNG Files (*.png);;SVG Files (*.svg);;PDF Files (*.pdf);;All Files (*)"
)

_EXTENSION_TO_FORMAT = {
    ".png": "png",
    ".svg": "svg",
    ".pdf": "pdf",
}

_FILTER_TO_EXTENSION = {
    "PNG Files (*.png)": ".png",
    "SVG Files (*.svg)": ".svg",
    "PDF Files (*.pdf)": ".pdf",
}


def normalise_figure_export_path(file_path, selected_filter, default_format="png"):
    """Return ``(path, format)`` for a figure export destination."""
    if not file_path:
        return "", ""

    root, extension = os.path.splitext(file_path)
    extension = extension.lower()
    if extension in _EXTENSION_TO_FORMAT:
        return file_path, _EXTENSION_TO_FORMAT[extension]

    default_extension = f".{default_format.lower()}"
    selected_extension = _FILTER_TO_EXTENSION.get(selected_filter, default_extension)
    if selected_extension not in _EXTENSION_TO_FORMAT:
        selected_extension = default_extension
    return f"{file_path}{selected_extension}", _EXTENSION_TO_FORMAT[selected_extension]


def save_matplotlib_figure(figure, file_path, file_format, dpi):
    """Save a Matplotlib figure as PNG, SVG, or PDF."""
    figure.savefig(
        file_path,
        format=file_format,
        dpi=int(dpi),
        bbox_inches="tight",
    )


def save_qwidget_figure(widget, file_path, file_format, dpi):
    """Save a custom-painted QWidget as PNG, SVG, or PDF."""
    file_format = (file_format or "").lower()
    if file_format == "svg":
        _save_qwidget_svg(widget, file_path, dpi)
    elif file_format == "pdf":
        _save_qwidget_pdf(widget, file_path, dpi)
    elif file_format == "png":
        _save_qwidget_png(widget, file_path, dpi)
    else:
        raise ValueError(f"Unsupported figure format: {file_format}")


def show_export_complete(parent, file_path, timeout_ms=1000):
    """Show the standard auto-closing export completion message."""
    AutoCloseMessageBox.information(
        parent,
        "Export Complete",
        f"Figure exported to:\n{file_path}",
        timeout=timeout_ms,
    )


def _widget_size(widget):
    size = widget.size()
    if size.width() <= 0 or size.height() <= 0:
        size = widget.sizeHint()
    width = max(1, size.width())
    height = max(1, size.height())
    return QSize(width, height)


def _render_qwidget_image(widget, dpi):
    size = _widget_size(widget)
    base_dpi = widget.logicalDpiX() or 96
    scale = max(0.1, float(dpi) / float(base_dpi))
    image_size = QSize(
        max(1, int(math.ceil(size.width() * scale))),
        max(1, int(math.ceil(size.height() * scale))),
    )

    image = QImage(image_size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("white"))
    dots_per_meter = int(round(float(dpi) / 0.0254))
    image.setDotsPerMeterX(dots_per_meter)
    image.setDotsPerMeterY(dots_per_meter)

    painter = QPainter(image)
    painter.scale(scale, scale)
    widget.render(painter, QPoint(0, 0))
    painter.end()
    return image


def _save_qwidget_png(widget, file_path, dpi):
    image = _render_qwidget_image(widget, dpi)
    if not image.save(file_path, "PNG"):
        raise OSError(f"Could not write PNG file: {file_path}")


def _save_qwidget_svg(widget, file_path, dpi):
    size = _widget_size(widget)
    generator = QSvgGenerator()
    generator.setFileName(file_path)
    generator.setSize(size)
    generator.setViewBox(QRect(0, 0, size.width(), size.height()))
    generator.setResolution(int(dpi))

    painter = QPainter(generator)
    widget.render(painter, QPoint(0, 0))
    painter.end()


def _save_qwidget_pdf(widget, file_path, dpi):
    image = _render_qwidget_image(widget, dpi)
    writer = QPdfWriter(file_path)
    writer.setResolution(int(dpi))
    page_size_points = QSizeF(
        image.width() / float(dpi) * 72.0,
        image.height() / float(dpi) * 72.0,
    )
    writer.setPageSize(QPageSize(page_size_points, QPageSize.Unit.Point, "RABET Figure"))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Point)

    painter = QPainter(writer)
    painter.drawImage(QRect(0, 0, writer.width(), writer.height()), image)
    painter.end()
