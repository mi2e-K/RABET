# views/analysis_charts.py - Shared matplotlib chart widget for analysis dialogs.
#
# A single reusable Qt-embedded matplotlib canvas with two chart helpers
# (heatmap, grouped bars). Analysis dialogs feed their already-computed results
# to this one component (surfaced as a "Plot" view) rather than each growing its
# own charting code — so visual aids stay DRY and out of the Visualization mode.

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtWidgets import QVBoxLayout, QWidget


class MplChartWidget(QWidget):
    """Reusable matplotlib canvas exposing heatmap() and bars()."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure = Figure(figsize=(5.0, 3.2), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)

    def heatmap(self, matrix, row_labels, col_labels, title="", vmax=8.0, diverging=True):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        arr = np.array(matrix, dtype=float)
        data = np.nan_to_num(arr, nan=0.0)
        if diverging:
            # ColorBrewer RdBu (reversed: red = positive). seaborn's "RdBu" is
            # this same matplotlib colormap, so no extra dependency is needed.
            im = ax.imshow(data, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
        else:
            im = ax.imshow(data, cmap="Blues", vmin=0.0, vmax=vmax, aspect="auto")
        ax.set_xticks(range(len(col_labels)))
        ax.set_xticklabels(col_labels, fontsize=9, rotation=30, ha="right")
        ax.set_yticks(range(len(row_labels)))
        ax.set_yticklabels(row_labels, fontsize=9)
        for i in range(arr.shape[0]):
            for j in range(arr.shape[1]):
                if np.isfinite(arr[i, j]):
                    ax.text(j, i, f"{arr[i, j]:.0f}", ha="center", va="center",
                            fontsize=10, color="white" if abs(arr[i, j]) > vmax * 0.5 else "#333")
        ax.set_title(title, fontsize=9)
        self.figure.colorbar(im, ax=ax, shrink=0.7)
        self.canvas.draw()

    def bars(self, categories, series, title="", ylabel="", ref=None, colors=None):
        """series: dict label -> list of values (one per category).
        colors: optional dict label -> colour (hex); falls back to the cycle."""
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        colors = colors or {}
        x = np.arange(len(categories))
        n = max(1, len(series))
        width = 0.8 / n
        for k, (name, values) in enumerate(series.items()):
            ax.bar(x + (k - (n - 1) / 2) * width, values, width, label=name,
                   color=colors.get(name))
        if ref is not None:
            ax.axhline(ref, ls="--", color="#888888", lw=1)
        ax.set_xticks(x)
        ax.set_xticklabels(categories, fontsize=7, rotation=30, ha="right")
        ax.set_ylabel(ylabel, fontsize=8)
        ax.set_title(title, fontsize=9)
        if len(series) > 1:
            ax.legend(fontsize=7, frameon=False)
        self.canvas.draw()
