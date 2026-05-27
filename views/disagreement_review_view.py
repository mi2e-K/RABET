# views/disagreement_review_view.py - Event-level disagreement review dialog
"""
DisagreementReviewDialog - dedicated UI for reviewing event-level
disagreements between a Reference and a Trainee annotation file.

This dialog sits on top of the existing Detailed-mode reliability
result. It does not recompute Cohen's kappa, Krippendorff's alpha, or
raw percentage agreement; instead it builds an event-level matching of
``DetailedAgreementResult.events_a`` (Reference) against ``events_b``
(Trainee) and lets the user step through the disagreements, optionally
seeking a loaded video to each item's onset.

The dialog owns its own dedicated ``VideoModel`` / ``VideoPlayerView``
/ ``VideoController`` stack so loading a video here does not interfere
with the main application's playback state. The video model is closed
when the dialog is closed.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QKeySequence, QPainter, QPen,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QComboBox,
    QSizePolicy, QSplitter, QVBoxLayout, QWidget,
)

from controllers.video_controller import VideoController
from models.reliability_model import (
    DetailedAgreementResult,
    DisagreementReviewResult,
    EventMatch,
    build_disagreement_review,
)
from models.video_model import VideoModel
from utils.video_detection import video_file_dialog_filter
from views.video_player_view import VideoPlayerView

logger = logging.getLogger(__name__)


# Color-universal-design palette. Same hues across Reference and
# Trainee lanes, distinguished by lane position and (optionally) alpha.
_BEHAVIOR_COLOR_PALETTE: Tuple[str, ...] = (
    "#005aff",  # blue
    "#ff4b00",  # orange-red
    "#03af7a",  # green
    "#f6aa00",  # gold
    "#990099",  # purple
    "#804000",  # brown
    "#ff8082",  # pink
    "#4dc4ff",  # sky
    "#990000",  # dark red
    "#84919e",  # grey
)

_STATUS_DISPLAY: Dict[str, str] = {
    "time_matched": "Time matched",
    "timing_offset": "Timing offset",
    "reference_only": "Reference only",
    "trainee_only": "Trainee only",
}

_TYPE_FILTER_OPTIONS: Tuple[Tuple[str, str], ...] = (
    ("__all__", "All disagreements"),
    ("reference_only", "Reference only"),
    ("trainee_only", "Trainee only"),
    ("timing_offset", "Timing offset"),
)

_BEHAVIOR_FILTER_ALL = "__all__"

# Video-position marker (playhead) on the raster. Rose-600 reads clearly
# over the behaviour-coloured ribbons without colliding with any palette
# entry above.
_PLAYHEAD_COLOR = "#E11D48"


def _build_behavior_color_map(behaviors: List[str]) -> Dict[str, str]:
    """Return a deterministic behaviour -> color mapping.

    The mapping is keyed by the sorted behaviour list so the same color
    is assigned across redraws regardless of how the dialog filters its
    visible items.
    """
    mapping: Dict[str, str] = {}
    for index, behavior in enumerate(behaviors):
        mapping[behavior] = _BEHAVIOR_COLOR_PALETTE[
            index % len(_BEHAVIOR_COLOR_PALETTE)
        ]
    return mapping


def load_custom_color_map() -> Dict[str, str]:
    """Read ``configs/custom_color_map.json`` and return the mapping.

    Ordering matters: the JSON's insertion order drives the default
    behaviour ordering used by the raster. Returns an empty dict if the
    file does not exist or cannot be parsed.
    """
    try:
        from utils.config_path_manager import ConfigPathManager
        manager = ConfigPathManager()
        path = manager.get_color_map_config_path()
        if path is None:
            return {}
        path_str = str(path)
        if not os.path.exists(path_str):
            return {}
        with open(path_str, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items()}
    except Exception:
        logger.exception("Failed to load custom_color_map.json")
        return {}


# -------------------------------------------------------------------- #
# Behavior display settings (separate UI)
# -------------------------------------------------------------------- #


@dataclass
class BehaviorDisplaySettings:
    """User-editable raster display settings for one set of behaviours.

    ``ordered_behaviors`` is the y-axis ordering used by the raster (top
    to bottom). ``visible`` and ``colors`` are keyed by behaviour name.
    """
    ordered_behaviors: List[str] = field(default_factory=list)
    visible: Dict[str, bool] = field(default_factory=dict)
    colors: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def defaults_for(cls, behaviors: List[str]) -> "BehaviorDisplaySettings":
        ordered = sorted(behaviors, key=lambda s: s.casefold())
        return cls(
            ordered_behaviors=list(ordered),
            visible={beh: True for beh in ordered},
            colors=_build_behavior_color_map(ordered),
        )

    @classmethod
    def from_custom_color_map(
        cls,
        behaviors: List[str],
        color_map: Dict[str, str],
    ) -> "BehaviorDisplaySettings":
        """Build settings using ``color_map`` (JSON insertion order)
        as the default ordering and colour assignment.

        Behaviours present in ``color_map`` adopt the JSON order. Any
        behaviour not in the map is appended in alphabetical order and
        coloured with the fallback CUD palette so nothing renders as
        plain grey.
        """
        if not color_map:
            return cls.defaults_for(behaviors)

        behavior_set = set(behaviors)
        ordered: List[str] = []
        colors: Dict[str, str] = {}
        for behavior, hex_color in color_map.items():
            if behavior in behavior_set and behavior not in ordered:
                ordered.append(behavior)
                colors[behavior] = hex_color

        remaining = sorted(
            (b for b in behavior_set if b not in colors),
            key=lambda s: s.casefold(),
        )
        fallback_palette = _build_behavior_color_map(remaining)
        for behavior in remaining:
            ordered.append(behavior)
            colors[behavior] = fallback_palette[behavior]

        return cls(
            ordered_behaviors=list(ordered),
            visible={beh: True for beh in ordered},
            colors=dict(colors),
        )

    def copy(self) -> "BehaviorDisplaySettings":
        return BehaviorDisplaySettings(
            ordered_behaviors=list(self.ordered_behaviors),
            visible=dict(self.visible),
            colors=dict(self.colors),
        )


class BehaviorDisplaySettingsDialog(QDialog):
    """Edit which behaviours appear on the raster, their order, and the
    colour assigned to each.

    The dialog operates on a copy of ``BehaviorDisplaySettings`` so the
    caller can decide whether to keep the edits (``exec`` returned
    ``Accepted``) or discard them.
    """

    def __init__(
        self,
        settings: BehaviorDisplaySettings,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Behavior display settings")
        self.resize(440, 540)

        self._settings = settings.copy()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        intro = QLabel(
            "Drag rows to reorder. Toggle the checkbox to show/hide a "
            "behaviour. Click the swatch to change its colour."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #8a8a8a;")
        outer.addWidget(intro)

        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove
        )
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.list_widget.setUniformItemSizes(False)
        outer.addWidget(self.list_widget, 1)

        for behavior in self._settings.ordered_behaviors:
            self._add_row(behavior)

        action_row = QHBoxLayout()
        self.reset_btn = QPushButton("Reset to defaults")
        self.reset_btn.clicked.connect(self._on_reset_clicked)
        action_row.addWidget(self.reset_btn)
        action_row.addStretch()
        outer.addLayout(action_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ----- row helpers ----- #

    def _add_row(self, behavior: str) -> None:
        item = QListWidgetItem(self.list_widget)
        item.setData(Qt.ItemDataRole.UserRole, behavior)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(6, 2, 6, 2)
        row_layout.setSpacing(8)

        check = QCheckBox()
        check.setChecked(self._settings.visible.get(behavior, True))
        check.toggled.connect(
            lambda checked, b=behavior: self._on_visibility_toggled(b, checked)
        )
        row_layout.addWidget(check)

        swatch = QPushButton()
        swatch.setFixedSize(28, 18)
        swatch.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        color = self._settings.colors.get(behavior, "#888888")
        swatch.setStyleSheet(
            f"background-color: {color}; border: 1px solid #333;"
        )
        swatch.clicked.connect(
            lambda _checked=False, b=behavior, btn=swatch: self._on_color_clicked(b, btn)
        )
        row_layout.addWidget(swatch)

        label = QLabel(behavior)
        row_layout.addWidget(label, 1)

        item.setSizeHint(row.sizeHint())
        self.list_widget.setItemWidget(item, row)

    def _on_visibility_toggled(self, behavior: str, checked: bool) -> None:
        self._settings.visible[behavior] = checked

    def _on_color_clicked(self, behavior: str, swatch: QPushButton) -> None:
        current = QColor(self._settings.colors.get(behavior, "#888888"))
        chosen = QColorDialog.getColor(
            current, self, f"Choose colour for {behavior}"
        )
        if chosen.isValid():
            hex_color = chosen.name()
            self._settings.colors[behavior] = hex_color
            swatch.setStyleSheet(
                f"background-color: {hex_color}; border: 1px solid #333;"
            )

    def _on_reset_clicked(self) -> None:
        # Prefer the project's custom_color_map.json so reset returns
        # the user to their canonical RABET colour scheme rather than
        # the built-in CUD palette.
        custom_map = load_custom_color_map()
        if custom_map:
            self._settings = BehaviorDisplaySettings.from_custom_color_map(
                self._settings.ordered_behaviors, custom_map,
            )
        else:
            self._settings = BehaviorDisplaySettings.defaults_for(
                self._settings.ordered_behaviors
            )
        # Rebuild the list to reflect the reset order/colours/visibility.
        self.list_widget.clear()
        for behavior in self._settings.ordered_behaviors:
            self._add_row(behavior)

    # ----- accessor ----- #

    def settings(self) -> BehaviorDisplaySettings:
        """Return the edited settings.

        We re-read the y-axis ordering from the list widget so any
        drag-and-drop reorder the user did is reflected. Visibility and
        colour are kept in sync via the row signals above.
        """
        ordered: List[str] = []
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            behavior = item.data(Qt.ItemDataRole.UserRole)
            if behavior:
                ordered.append(str(behavior))
        self._settings.ordered_behaviors = ordered
        return self._settings


# -------------------------------------------------------------------- #
# Raster painter widget (replaces matplotlib for performance)
# -------------------------------------------------------------------- #


class RasterPainterWidget(QWidget):
    """Custom QPainter-based raster for the Disagreement Review dialog.

    matplotlib's full re-rasterization on every ``draw_idle()`` was the
    root cause of choppy video playback — even with throttling, the
    figure rebuild on the main thread competes with PyAV decoding. This
    widget paints rectangles directly via ``paintEvent`` (the same
    approach as ``views/timeline_view.py``) so a playhead move costs
    one ``update()`` and a single sub-millisecond repaint.
    """

    _MARGIN_LEFT = 56
    _MARGIN_RIGHT = 16
    _MARGIN_TOP = 16
    _MARGIN_BOTTOM = 28
    _MIN_ROW_HEIGHT = 22
    _SUBLANE_GAP = 4  # vertical gap between R and T sub-lanes

    # Emitted when the user clicks an event ribbon. Payload is
    # (source, behavior, onset, offset) so the parent dialog can match
    # it against its review_items list and navigate to that item.
    event_clicked = Signal(str, str, float, float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        self.setMinimumHeight(180)
        # Crosshair cursor over the plot area so users know they can
        # click events. Updated on mouseMove.
        self.setMouseTracking(True)

        self._events_a: List[Tuple[str, float, float]] = []
        self._events_b: List[Tuple[str, float, float]] = []
        self._behaviors: List[str] = []
        self._colors: Dict[str, str] = {}
        self._duration: float = 1.0
        self._playhead_seconds: float = 0.0
        self._show_legend: bool = False
        self._white_bg: bool = False
        self._selected: Optional[EventMatch] = None

        # Hit-test rectangles built each paintEvent. Each entry maps a
        # QRect on screen to the (source, behavior, onset, offset)
        # tuple it represents. Updated in paintEvent so the geometry
        # always matches what the user sees.
        self._event_rects: List[Tuple[QRect, str, str, float, float]] = []

    # ----- setters: each one triggers a repaint via update() ----- #

    def set_events(
        self,
        events_a: List[Tuple[str, float, float]],
        events_b: List[Tuple[str, float, float]],
        duration: float,
    ) -> None:
        self._events_a = list(events_a)
        self._events_b = list(events_b)
        self._duration = max(float(duration), 1.0)
        self.update()

    def set_display(
        self,
        behaviors: List[str],
        colors: Dict[str, str],
        show_legend: bool,
        white_bg: bool = False,
    ) -> None:
        self._behaviors = list(behaviors)
        self._colors = dict(colors)
        self._show_legend = bool(show_legend)
        self._white_bg = bool(white_bg)
        self.update()

    def set_selected(self, item: Optional[EventMatch]) -> None:
        self._selected = item
        self.update()

    def set_playhead(self, seconds: float) -> None:
        """Update the playhead position only. Cheap: just an
        ``update()`` to schedule a repaint on Qt's next idle cycle."""
        self._playhead_seconds = max(0.0, float(seconds))
        self.update()

    # ----- geometry helpers ----- #

    def _plot_rect(self) -> QRect:
        legend_w = self._legend_width() if self._show_legend else 0
        return QRect(
            self._MARGIN_LEFT,
            self._MARGIN_TOP,
            max(1, self.width() - self._MARGIN_LEFT - self._MARGIN_RIGHT - legend_w),
            max(1, self.height() - self._MARGIN_TOP - self._MARGIN_BOTTOM),
        )

    def _legend_width(self) -> int:
        if not self._behaviors:
            return 0
        fm = QFontMetrics(self.font())
        max_text = max(
            (fm.horizontalAdvance(b) for b in self._behaviors),
            default=0,
        )
        return min(180, max_text + 32)

    def _x_for_time(self, t: float, plot: QRect) -> int:
        if self._duration <= 0:
            return plot.left()
        frac = max(0.0, min(1.0, float(t) / self._duration))
        return plot.left() + int(round(frac * plot.width()))

    def _row_geometry(
        self, plot: QRect
    ) -> Tuple[int, int, Dict[str, int]]:
        n = len(self._behaviors)
        if n == 0:
            return 0, 0, {}
        row_height = max(self._MIN_ROW_HEIGHT, plot.height() // n)
        y_centers = {
            beh: plot.top() + row_height // 2 + i * row_height
            for i, beh in enumerate(self._behaviors)
        }
        return row_height, row_height // 2 - self._SUBLANE_GAP // 2, y_centers

    # ----- painting ----- #

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Hit-test rects must be rebuilt on every paint so clicks
        # match the visible geometry after a resize / filter change.
        self._event_rects = []

        # Background.
        bg = QColor("#ffffff") if self._white_bg else QColor("#1e1e1e")
        painter.fillRect(self.rect(), bg)

        plot = self._plot_rect()
        if not self._behaviors:
            painter.end()
            return

        row_height, sublane_half, y_centers = self._row_geometry(plot)
        sublane_h = max(4, sublane_half - 1)

        # Grid + row labels.
        self._draw_axes(painter, plot, row_height, y_centers)

        # Event ribbons.
        for behavior, onset, offset in self._events_a:
            if behavior not in y_centers:
                continue
            y_center = y_centers[behavior]
            self._draw_event(
                painter, plot, onset, offset,
                y_center - self._SUBLANE_GAP // 2 - sublane_h, sublane_h,
                self._colors.get(behavior, "#888888"),
                alpha=220, source="reference", behavior=behavior,
            )
        for behavior, onset, offset in self._events_b:
            if behavior not in y_centers:
                continue
            y_center = y_centers[behavior]
            self._draw_event(
                painter, plot, onset, offset,
                y_center + self._SUBLANE_GAP // 2, sublane_h,
                self._colors.get(behavior, "#888888"),
                alpha=160, source="trainee", behavior=behavior,
            )

        # Selected-event outline (no yellow band).
        if self._selected is not None:
            self._draw_selected_outline(
                painter, plot, y_centers, sublane_h,
            )

        # R / T sub-lane labels just inside the y axis.
        self._draw_sublane_labels(painter, plot, y_centers, sublane_h)

        # Live playhead.
        playhead_x = self._x_for_time(self._playhead_seconds, plot)
        pen = QPen(QColor(_PLAYHEAD_COLOR))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawLine(playhead_x, plot.top(), playhead_x, plot.bottom())

        # Optional legend.
        if self._show_legend:
            self._draw_legend(painter)

        painter.end()

    def _draw_axes(
        self,
        painter: QPainter,
        plot: QRect,
        row_height: int,
        y_centers: Dict[str, int],
    ) -> None:
        # White-bg variant uses darker grid lines and black text so
        # everything stays legible against the lighter surface.
        if self._white_bg:
            grid_color = QColor(200, 200, 200)
            text_color = QColor("#222222")
            tick_color = QColor("#444444")
        else:
            grid_color = QColor(60, 60, 60)
            text_color = QColor("#dddddd")
            tick_color = QColor("#9a9a9a")

        # Grid lines (one per second up to a sensible cap).
        painter.setPen(QPen(grid_color, 1, Qt.PenStyle.DotLine))
        step = max(1.0, self._duration / 12.0)
        # Snap to a nicer interval.
        for nice in (1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0):
            if self._duration / nice <= 12:
                step = nice
                break
        t = 0.0
        while t <= self._duration + 1e-6:
            x = self._x_for_time(t, plot)
            painter.drawLine(x, plot.top(), x, plot.bottom())
            t += step

        # Behaviour labels along the y-axis.
        painter.setPen(QPen(text_color))
        font = painter.font()
        font.setPointSize(max(8, font.pointSize() - 1))
        painter.setFont(font)
        fm = QFontMetrics(font)
        for behavior, y in y_centers.items():
            text_rect = QRect(
                0, y - row_height // 2,
                self._MARGIN_LEFT - 8, row_height,
            )
            elided = fm.elidedText(
                behavior, Qt.TextElideMode.ElideRight, text_rect.width(),
            )
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                elided,
            )

        # Bottom axis ticks (time labels).
        painter.setPen(QPen(tick_color))
        t = 0.0
        while t <= self._duration + 1e-6:
            x = self._x_for_time(t, plot)
            label = f"{t:g}s"
            text_w = fm.horizontalAdvance(label)
            painter.drawText(
                QPoint(x - text_w // 2, plot.bottom() + fm.ascent() + 4),
                label,
            )
            t += step

    def _draw_event(
        self,
        painter: QPainter,
        plot: QRect,
        onset: float,
        offset: float,
        y: int,
        height: int,
        hex_color: str,
        alpha: int = 220,
        source: str = "",
        behavior: str = "",
    ) -> None:
        x1 = self._x_for_time(onset, plot)
        x2 = self._x_for_time(max(offset, onset), plot)
        # 1-pixel minimum so very short events (e.g. button presses
        # under 50 ms) remain visible without inflating their apparent
        # duration the way a 2-3 px minimum did.
        width = max(1, x2 - x1)
        color = QColor(hex_color)
        color.setAlpha(alpha)
        rect = QRect(x1, y, width, height)
        painter.fillRect(rect, QBrush(color))
        if source and behavior:
            # Cache a slightly enlarged hit rect so a 1-pixel ribbon
            # is still easy to click. Padding is added vertically to
            # cover the entire sub-lane height.
            hit = QRect(
                rect.x(), rect.y(),
                max(4, rect.width() + 2),
                rect.height(),
            )
            self._event_rects.append(
                (hit, source, behavior, float(onset), float(offset))
            )

    def _draw_selected_outline(
        self,
        painter: QPainter,
        plot: QRect,
        y_centers: Dict[str, int],
        sublane_h: int,
    ) -> None:
        assert self._selected is not None
        outline_color = QColor("#000000") if self._white_bg else QColor("#ffffff")
        pen = QPen(outline_color)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        sel = self._selected
        if sel.reference is not None and sel.reference.behavior in y_centers:
            y_center = y_centers[sel.reference.behavior]
            x1 = self._x_for_time(sel.reference.onset, plot)
            x2 = self._x_for_time(
                max(sel.reference.offset, sel.reference.onset), plot,
            )
            painter.drawRect(
                QRect(
                    x1 - 1,
                    y_center - self._SUBLANE_GAP // 2 - sublane_h - 1,
                    max(3, x2 - x1) + 2,
                    sublane_h + 2,
                )
            )
        if sel.trainee is not None and sel.trainee.behavior in y_centers:
            y_center = y_centers[sel.trainee.behavior]
            x1 = self._x_for_time(sel.trainee.onset, plot)
            x2 = self._x_for_time(
                max(sel.trainee.offset, sel.trainee.onset), plot,
            )
            painter.drawRect(
                QRect(
                    x1 - 1,
                    y_center + self._SUBLANE_GAP // 2 - 1,
                    max(3, x2 - x1) + 2,
                    sublane_h + 2,
                )
            )

    def _draw_sublane_labels(
        self,
        painter: QPainter,
        plot: QRect,
        y_centers: Dict[str, int],
        sublane_h: int,
    ) -> None:
        label_color = QColor("#444444") if self._white_bg else QColor("#888888")
        painter.setPen(QPen(label_color))
        font = QFont(painter.font())
        font.setPointSize(max(7, font.pointSize() - 1))
        painter.setFont(font)
        for _behavior, y_center in y_centers.items():
            painter.drawText(
                QPoint(plot.left() - 14,
                       y_center - self._SUBLANE_GAP // 2 - sublane_h // 2 + 4),
                "R",
            )
            painter.drawText(
                QPoint(plot.left() - 14,
                       y_center + self._SUBLANE_GAP // 2 + sublane_h // 2 + 4),
                "T",
            )

    def _draw_legend(self, painter: QPainter) -> None:
        legend_w = self._legend_width()
        if legend_w <= 0 or not self._behaviors:
            return
        plot = self._plot_rect()
        legend_x = plot.right() + 8
        legend_y = plot.top()
        font = painter.font()
        fm = QFontMetrics(font)
        line_h = fm.height() + 2
        swatch_size = max(8, fm.height() - 4)
        legend_text_color = QColor("#222222") if self._white_bg else QColor("#dddddd")
        painter.setPen(QPen(legend_text_color))
        for index, behavior in enumerate(self._behaviors):
            y = legend_y + index * line_h
            color = QColor(self._colors.get(behavior, "#888888"))
            painter.fillRect(
                QRect(legend_x, y + 2, swatch_size, swatch_size),
                QBrush(color),
            )
            painter.drawText(
                QPoint(legend_x + swatch_size + 6, y + fm.ascent()),
                behavior,
            )

    # ----- input ----- #

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        # Walk hit rects in reverse (last drawn wins; matches the
        # visual stacking order if any events overlap).
        for hit, source, behavior, onset, offset in reversed(self._event_rects):
            if hit.contains(pos):
                self.event_clicked.emit(source, behavior, onset, offset)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        hovering = any(
            hit.contains(pos) for hit, *_ in self._event_rects
        )
        if hovering:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)


class DisagreementReviewDialog(QDialog):
    """Dedicated UI for stepping through Detailed-mode disagreements."""

    def __init__(
        self,
        detailed_result: DetailedAgreementResult,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Disagreement Review")
        # Promote to a top-level window so it gets full system buttons
        # (minimize / maximize / close). A bare QDialog on Windows
        # otherwise has only a close button, which made the dialog
        # impossible to maximize without resizing by edge.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(1180, 760)
        self.logger = logging.getLogger(__name__)

        self._detailed_result = detailed_result
        self._review_result: Optional[DisagreementReviewResult] = None
        self._review_items_filtered: List[EventMatch] = []
        self._current_review_index: int = -1

        # Behaviour ordering for the raster: union of Reference and
        # Trainee behaviour sets so the dialog still has rows to draw
        # even when only one side scored a particular behaviour.
        behavior_set = set(detailed_result.behaviors or [])
        for beh, _, _ in detailed_result.events_a:
            if beh:
                behavior_set.add(beh)
        for beh, _, _ in detailed_result.events_b:
            if beh:
                behavior_set.add(beh)
        self._all_behaviors: List[str] = sorted(
            behavior_set, key=lambda s: s.casefold()
        )
        # User-editable display settings (order / visibility / colour).
        # Defaults come from configs/custom_color_map.json so the dialog
        # opens with the team's canonical colour scheme + ordering.
        custom_map = load_custom_color_map()
        if custom_map:
            self._display_settings = BehaviorDisplaySettings.from_custom_color_map(
                self._all_behaviors, custom_map,
            )
        else:
            self._display_settings = BehaviorDisplaySettings.defaults_for(
                self._all_behaviors
            )

        # Dedicated video stack — opened on demand via Load video.
        self._video_model: Optional[VideoModel] = None
        self._video_view: Optional[VideoPlayerView] = None
        self._video_controller: Optional[VideoController] = None
        self._video_loaded: bool = False

        # Live playhead state. With the QPainter-based RasterPainter
        # we just stash the latest seconds and call ``update()`` —
        # Qt schedules a paintEvent on the next idle cycle and the
        # repaint is sub-millisecond, so the previous matplotlib
        # throttle is no longer needed for performance. We keep a
        # lightweight timer only to coalesce the ~30 position_changed
        # signals per second into ~20 Hz repaints, which still keeps
        # the line visually smooth without paying for 30 paintEvents.
        self._current_video_seconds: float = 0.0
        self._pending_playhead_seconds: Optional[float] = None
        self._playhead_timer = QTimer(self)
        self._playhead_timer.setSingleShot(True)
        self._playhead_timer.timeout.connect(self._flush_playhead)

        self._setup_ui()
        self._connect_signals()
        self._rebuild_review_result()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        # Top control band: Review controls (left) and Plot controls
        # (right) side by side, each laid out in a single horizontal
        # row to keep the dialog header compact.
        top_band = QHBoxLayout()
        top_band.setSpacing(8)

        controls_box = QGroupBox("Review controls")
        controls = QHBoxLayout(controls_box)
        controls.setSpacing(6)

        self.load_video_btn = QPushButton("Load video...")
        controls.addWidget(self.load_video_btn)
        # Filename appears here after Load video is used; starts blank
        # so the row doesn't carry a placeholder before any video is
        # selected.
        self.video_name_label = QLabel("")
        self.video_name_label.setStyleSheet("color: #8a8a8a;")
        controls.addWidget(self.video_name_label)

        controls.addSpacing(8)
        controls.addWidget(QLabel("Window: ±"))
        self.matching_window_spin = QDoubleSpinBox()
        self.matching_window_spin.setRange(0.0, 60.0)
        self.matching_window_spin.setDecimals(2)
        self.matching_window_spin.setSingleStep(0.5)
        self.matching_window_spin.setValue(2.0)
        self.matching_window_spin.setSuffix(" s")
        self.matching_window_spin.setFixedWidth(90)
        controls.addWidget(self.matching_window_spin)

        controls.addWidget(QLabel("Pre-roll:"))
        self.pre_roll_spin = QDoubleSpinBox()
        self.pre_roll_spin.setRange(0.0, 30.0)
        self.pre_roll_spin.setDecimals(2)
        self.pre_roll_spin.setSingleStep(0.25)
        self.pre_roll_spin.setValue(1.0)
        self.pre_roll_spin.setSuffix(" s")
        self.pre_roll_spin.setFixedWidth(80)
        controls.addWidget(self.pre_roll_spin)

        controls.addWidget(QLabel("Behavior:"))
        self.behavior_filter = QComboBox()
        self.behavior_filter.setMinimumWidth(140)
        self.behavior_filter.addItem("All behaviors", _BEHAVIOR_FILTER_ALL)
        for behavior in self._all_behaviors:
            self.behavior_filter.addItem(behavior, behavior)
        controls.addWidget(self.behavior_filter)

        controls.addWidget(QLabel("Type:"))
        self.type_filter = QComboBox()
        self.type_filter.setMinimumWidth(130)
        for key, label in _TYPE_FILTER_OPTIONS:
            self.type_filter.addItem(label, key)
        controls.addWidget(self.type_filter)
        controls.addStretch()

        top_band.addWidget(controls_box, 3)

        # Plot controls box (raster appearance), also single-row.
        plot_box = QGroupBox("Plot controls")
        plot_layout = QHBoxLayout(plot_box)
        plot_layout.setSpacing(8)
        self.show_legend_check = QCheckBox("Show legend")
        # Default off — colours are visible on the rows themselves, and
        # the legend can eat a sizeable chunk of the plot area for
        # studies with many behaviours.
        self.show_legend_check.setChecked(False)
        plot_layout.addWidget(self.show_legend_check)

        self.white_bg_check = QCheckBox("White background")
        self.white_bg_check.setToolTip(
            "Switch the raster background to white (useful for "
            "presentations / printed exports). Text and grid colours "
            "adapt automatically."
        )
        plot_layout.addWidget(self.white_bg_check)

        self.display_settings_btn = QPushButton("Behavior display settings...")
        self.display_settings_btn.setToolTip(
            "Choose which behaviours appear on the raster, their order, "
            "and the colour assigned to each."
        )
        plot_layout.addWidget(self.display_settings_btn)
        plot_layout.addStretch()
        top_band.addWidget(plot_box, 2)

        outer.addLayout(top_band)

        # Main splitter: video on the left, raster + status on the right.
        splitter = QSplitter(Qt.Orientation.Horizontal)

        video_panel = QWidget()
        video_layout = QVBoxLayout(video_panel)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(2)
        # Create the dedicated video stack. VideoModel takes no parent
        # argument; we close it explicitly in closeEvent so leak-free
        # cleanup doesn't depend on the Qt object hierarchy.
        self._video_model = VideoModel()
        self._video_view = VideoPlayerView()
        self._video_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        self._video_controller = VideoController(
            self._video_model, self._video_view,
        )
        video_layout.addWidget(self._video_view, 1)
        splitter.addWidget(video_panel)

        raster_panel = QWidget()
        raster_layout = QVBoxLayout(raster_panel)
        raster_layout.setContentsMargins(0, 0, 0, 0)
        raster_layout.setSpacing(4)
        raster_layout.addWidget(QLabel("Reference / Trainee raster (color = behavior)"))
        # Custom QPainter-based raster — see RasterPainterWidget. The
        # previous matplotlib path was the root cause of choppy video
        # playback: full re-rasterization on every position update
        # competed with PyAV decoding for main-thread time.
        self.raster_widget = RasterPainterWidget()
        raster_layout.addWidget(self.raster_widget, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(60)
        self.status_label.setStyleSheet("color: #eeeeee;")
        raster_layout.addWidget(self.status_label)

        # Live readout of Reference events active at the current
        # playhead. Updated whenever the playhead moves so reviewers
        # can see what the expert called at this exact moment.
        self.live_ref_label = QLabel("Reference now: —")
        self.live_ref_label.setWordWrap(True)
        self.live_ref_label.setStyleSheet(
            "color: #ffd680; font-weight: bold; padding: 4px;"
        )
        raster_layout.addWidget(self.live_ref_label)

        splitter.addWidget(raster_panel)
        splitter.setSizes([520, 660])
        outer.addWidget(splitter, 1)

        # Navigation row + counts.
        nav_row = QHBoxLayout()
        self.current_label = QLabel("0 / 0")
        self.current_label.setStyleSheet("font-weight: bold;")
        nav_row.addWidget(self.current_label)
        nav_row.addStretch()

        self.first_btn = QPushButton("First")
        self.prev_btn = QPushButton("Prev")
        self.next_btn = QPushButton("Next")
        self.last_btn = QPushButton("Last")
        for btn in (
            self.first_btn, self.prev_btn, self.next_btn, self.last_btn
        ):
            btn.setMinimumWidth(72)
            nav_row.addWidget(btn)

        outer.addLayout(nav_row)

        # Bottom buttons row.
        bottom_row = QHBoxLayout()
        self.counts_label = QLabel("")
        self.counts_label.setStyleSheet("color: #8a8a8a;")
        bottom_row.addWidget(self.counts_label, 1)

        self.export_btn = QPushButton("Export review CSV...")
        bottom_row.addWidget(self.export_btn)
        self.close_btn = QPushButton("Close")
        bottom_row.addWidget(self.close_btn)
        outer.addLayout(bottom_row)

    # ------------------------------------------------------------------ #
    # Signal wiring
    # ------------------------------------------------------------------ #

    def _connect_signals(self) -> None:
        self.load_video_btn.clicked.connect(self._on_load_video_clicked)
        self.matching_window_spin.valueChanged.connect(
            self._on_matching_window_changed
        )
        self.pre_roll_spin.valueChanged.connect(self._on_pre_roll_changed)
        self.behavior_filter.currentIndexChanged.connect(
            self._on_filter_changed
        )
        self.type_filter.currentIndexChanged.connect(
            self._on_filter_changed
        )
        self.show_legend_check.toggled.connect(self._on_show_legend_toggled)
        self.white_bg_check.toggled.connect(self._on_white_bg_toggled)
        self.display_settings_btn.clicked.connect(
            self._on_display_settings_clicked
        )
        # Raster click → navigate to that event (if it's a review item).
        self.raster_widget.event_clicked.connect(self._on_raster_event_clicked)
        self.first_btn.clicked.connect(self._on_first_clicked)
        self.prev_btn.clicked.connect(self._on_prev_clicked)
        self.next_btn.clicked.connect(self._on_next_clicked)
        self.last_btn.clicked.connect(self._on_last_clicked)
        self.export_btn.clicked.connect(self._on_export_clicked)
        self.close_btn.clicked.connect(self.close)

        # Live playhead: react to the dedicated VideoModel's
        # ``position_changed`` signal (ms). The signal fires once per
        # decoded frame during playback and on every seek.
        if self._video_model is not None:
            self._video_model.position_changed.connect(
                self._on_video_position_changed
            )

        # Spacebar toggles play/pause window-wide. QShortcut with
        # WindowShortcut context intercepts Space before focused
        # buttons / checkboxes can swallow it.
        self._space_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._space_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._space_shortcut.activated.connect(self._on_spacebar)

    # ------------------------------------------------------------------ #
    # Review-result management
    # ------------------------------------------------------------------ #

    def _rebuild_review_result(self) -> None:
        """Rebuild the event-matching result.

        Called once on dialog open and whenever the matching window
        changes. Filter changes never rebuild — they only re-filter the
        already-computed ``review_items`` list.
        """
        matching_window = float(self.matching_window_spin.value())
        pre_roll = float(self.pre_roll_spin.value())
        self._review_result = build_disagreement_review(
            events_reference=self._detailed_result.events_a,
            events_trainee=self._detailed_result.events_b,
            matching_window_seconds=matching_window,
            pre_roll_seconds=pre_roll,
        )
        self._apply_filters(reset_index=True)
        self._update_counts_label()

    def _apply_filters(self, reset_index: bool = False) -> None:
        if self._review_result is None:
            self._review_items_filtered = []
        else:
            behavior_key = self.behavior_filter.currentData()
            type_key = self.type_filter.currentData()
            items = list(self._review_result.review_items)
            if behavior_key and behavior_key != _BEHAVIOR_FILTER_ALL:
                items = [item for item in items if item.behavior == behavior_key]
            if type_key and type_key != _BEHAVIOR_FILTER_ALL and type_key != "__all__":
                items = [item for item in items if item.status == type_key]
            self._review_items_filtered = items

        if reset_index or not self._review_items_filtered:
            self._current_review_index = 0 if self._review_items_filtered else -1
        else:
            self._current_review_index = max(
                0, min(self._current_review_index,
                       len(self._review_items_filtered) - 1)
            )

        self._update_navigation_enabled()
        if self._review_items_filtered and 0 <= self._current_review_index < len(
            self._review_items_filtered
        ):
            self._jump_to_review_index(self._current_review_index)
        else:
            self._update_current_disagreement_label(None)
            self._draw_review_raster()

    def _update_counts_label(self) -> None:
        if self._review_result is None:
            self.counts_label.setText("")
            return
        counts = self._review_result.counts_by_type
        self.counts_label.setText(
            f"Counts — Reference only: {counts.get('reference_only', 0)} | "
            f"Trainee only: {counts.get('trainee_only', 0)} | "
            f"Timing offset: {counts.get('timing_offset', 0)} | "
            f"Time matched: {counts.get('time_matched', 0)}"
        )

    def _update_navigation_enabled(self) -> None:
        has_items = bool(self._review_items_filtered)
        for btn in (self.first_btn, self.prev_btn, self.next_btn, self.last_btn):
            btn.setEnabled(has_items)
        self.export_btn.setEnabled(
            self._review_result is not None
            and bool(self._review_result.review_items)
        )

    # ------------------------------------------------------------------ #
    # Slots
    # ------------------------------------------------------------------ #

    def _on_matching_window_changed(self, _value: float) -> None:
        self._rebuild_review_result()

    def _on_pre_roll_changed(self, _value: float) -> None:
        # Pre-roll changes only affect future seeks; keep the result in
        # sync so export reflects the chosen value.
        if self._review_result is not None:
            self._review_result.pre_roll_seconds = float(_value)

    def _on_filter_changed(self, _index: int) -> None:
        self._apply_filters(reset_index=True)

    def _on_first_clicked(self) -> None:
        if self._review_items_filtered:
            self._jump_to_review_index(0)

    def _on_prev_clicked(self) -> None:
        if self._review_items_filtered:
            new_index = max(0, self._current_review_index - 1)
            self._jump_to_review_index(new_index)

    def _on_next_clicked(self) -> None:
        if self._review_items_filtered:
            new_index = min(
                len(self._review_items_filtered) - 1,
                self._current_review_index + 1,
            )
            self._jump_to_review_index(new_index)

    def _on_last_clicked(self) -> None:
        if self._review_items_filtered:
            self._jump_to_review_index(len(self._review_items_filtered) - 1)

    def _on_load_video_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load video for disagreement review",
            "",
            video_file_dialog_filter(),
        )
        if not path:
            return
        if self._video_controller is None:
            return
        try:
            self._video_controller.load_video(path)
        except Exception as exc:
            self.logger.error("Failed to load video: %s", exc, exc_info=True)
            QMessageBox.warning(
                self, "Disagreement Review",
                f"Could not load video:\n{exc}",
            )
            return
        self._video_loaded = True
        self.video_name_label.setText(os.path.basename(path))
        # If we already have a selected item, seek to it now.
        if 0 <= self._current_review_index < len(self._review_items_filtered):
            self._jump_to_review_index(self._current_review_index)

    def _on_show_legend_toggled(self, _checked: bool) -> None:
        self._draw_review_raster()

    def _on_white_bg_toggled(self, _checked: bool) -> None:
        self._draw_review_raster()

    def _on_raster_event_clicked(
        self, source: str, behavior: str, onset: float, offset: float,
    ) -> None:
        """User clicked an event ribbon on the raster.

        We search ``review_items_filtered`` for an EventMatch whose
        Reference or Trainee side matches (behavior + onset + offset).
        If found, navigate to that item. Time-matched events are not in
        ``review_items``; for those we just seek the video instead of
        changing the selection — they're not navigable but the user
        still gets to peek at them.
        """
        # First try to match a filtered review item.
        target_index = -1
        for idx, item in enumerate(self._review_items_filtered):
            side = item.reference if source == "reference" else item.trainee
            if side is None or side.behavior != behavior:
                continue
            if (abs(side.onset - onset) < 1e-6
                    and abs(side.offset - offset) < 1e-6):
                target_index = idx
                break
        if target_index >= 0:
            self._jump_to_review_index(target_index)
            return

        # Fall back: seek the video to the click location even if it's
        # not in the current filter set (e.g. a time_matched event).
        if self._video_model is not None and self._video_model.get_duration() > 0:
            pre_roll = float(self.pre_roll_spin.value())
            seek_ms = int(max(0.0, onset - pre_roll) * 1000)
            self._video_model.seek(seek_ms)

    def _on_display_settings_clicked(self) -> None:
        dialog = BehaviorDisplaySettingsDialog(self._display_settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._display_settings = dialog.settings()
        # Settings only affect rendering — never re-run matching. The
        # current selected review item may now point at a hidden
        # behaviour; that's fine, navigation still works (it'll just
        # have no row to highlight).
        self._draw_review_raster()

    def _on_video_position_changed(self, position_ms: int) -> None:
        """Coalesce the live-playhead update.

        Connected to ``VideoModel.position_changed``, which fires every
        decoded frame during playback (~30 Hz). Calling
        ``canvas.draw_idle`` at 30 Hz on the same thread that's
        decoding video makes playback visibly choppy. We instead stash
        the latest seconds value and let ``_flush_playhead`` paint at
        ~20 Hz via ``_playhead_timer``.
        """
        self._pending_playhead_seconds = max(
            0.0, float(position_ms) / 1000.0
        )
        if not self._playhead_timer.isActive():
            self._playhead_timer.start(50)

    def _flush_playhead(self) -> None:
        """Apply the latest pending playhead position to the raster.

        With RasterPainterWidget this is just one ``update()`` —
        sub-millisecond — which is what makes playback smooth.
        """
        if self._pending_playhead_seconds is None:
            return
        seconds = self._pending_playhead_seconds
        self._pending_playhead_seconds = None
        self._current_video_seconds = seconds
        self.raster_widget.set_playhead(seconds)
        self._update_live_ref_label(seconds)

    def _update_live_ref_label(self, seconds: float) -> None:
        """Show which Reference events are active at ``seconds``.

        Cheap O(N) sweep over events_a — annotation studies usually
        have hundreds to low thousands of events, which is well below
        the 20 Hz repaint budget.
        """
        active = [
            behavior
            for behavior, onset, offset in self._detailed_result.events_a
            if onset <= seconds <= offset
        ]
        if not active:
            self.live_ref_label.setText("Reference now: —")
        else:
            self.live_ref_label.setText(
                "Reference now: " + ", ".join(active)
            )

    # ------------------------------------------------------------------ #
    # Navigation core
    # ------------------------------------------------------------------ #

    def _jump_to_review_index(self, index: int) -> None:
        if not self._review_items_filtered:
            self._current_review_index = -1
            self._update_current_disagreement_label(None)
            self._draw_review_raster()
            return

        index = max(0, min(index, len(self._review_items_filtered) - 1))
        self._current_review_index = index

        item = self._review_items_filtered[index]
        pre_roll = float(self.pre_roll_spin.value())
        seek_ms = int(max(0.0, item.jump_time - pre_roll) * 1000)

        if (
            self._video_model is not None
            and self._video_model.get_duration() > 0
        ):
            self._video_model.seek(seek_ms)

        self._draw_review_raster()
        self._update_current_disagreement_label(item)

    def _update_current_disagreement_label(
        self, item: Optional[EventMatch]
    ) -> None:
        total = len(self._review_items_filtered)
        if item is None or total == 0:
            self.current_label.setText("0 / 0")
            if self._review_result is None:
                self.status_label.setText("")
            elif not self._review_result.review_items:
                self.status_label.setText(
                    "No disagreements found with the current matching "
                    "window and filters."
                )
            else:
                self.status_label.setText(
                    "No disagreements match the current filters."
                )
            return
        self.current_label.setText(
            f"{self._current_review_index + 1} / {total}"
        )
        self.status_label.setText(self._format_status_text(item))

    def _format_status_text(self, item: EventMatch) -> str:
        status_display = _STATUS_DISPLAY.get(item.status, item.status)
        if item.status == "reference_only":
            assert item.reference is not None
            return (
                f"{item.behavior} | {status_display} | "
                f"{item.reference.onset:.2f}–{item.reference.offset:.2f} s"
            )
        if item.status == "trainee_only":
            assert item.trainee is not None
            return (
                f"{item.behavior} | {status_display} | "
                f"{item.trainee.onset:.2f}–{item.trainee.offset:.2f} s"
            )
        # timing_offset (or time_matched, though that never appears in
        # filtered review items unless the spec is changed).
        assert item.reference is not None and item.trainee is not None
        lines = [
            f"{item.behavior} | {status_display}",
            f"Reference: {item.reference.onset:.2f}–{item.reference.offset:.2f} s",
            f"Trainee: {item.trainee.onset:.2f}–{item.trainee.offset:.2f} s",
        ]
        if item.onset_delta is not None and item.offset_delta is not None:
            lines.append(
                f"onset Δ = {item.onset_delta:.2f} s, "
                f"offset Δ = {item.offset_delta:.2f} s"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Raster drawing
    # ------------------------------------------------------------------ #

    def _draw_review_raster(self) -> None:
        """Push current state to the QPainter raster widget.

        Cheap: just sets bound attributes and calls ``update()`` on the
        widget. The actual painting happens in
        ``RasterPainterWidget.paintEvent`` and is sub-millisecond.
        """
        visible_behaviors = [
            beh for beh in self._display_settings.ordered_behaviors
            if self._display_settings.visible.get(beh, True)
            and beh in self._all_behaviors
        ]
        self.raster_widget.set_events(
            self._detailed_result.events_a,
            self._detailed_result.events_b,
            self._detailed_result.test_duration_seconds,
        )
        self.raster_widget.set_display(
            visible_behaviors,
            self._display_settings.colors,
            self.show_legend_check.isChecked(),
            white_bg=self.white_bg_check.isChecked(),
        )
        selected: Optional[EventMatch] = None
        if 0 <= self._current_review_index < len(self._review_items_filtered):
            selected = self._review_items_filtered[self._current_review_index]
        self.raster_widget.set_selected(selected)
        self.raster_widget.set_playhead(self._current_video_seconds)

    # ------------------------------------------------------------------ #
    # CSV export
    # ------------------------------------------------------------------ #

    def _on_export_clicked(self) -> None:
        if self._review_result is None or not self._review_result.review_items:
            QMessageBox.information(
                self, "Disagreement Review",
                "No disagreements to export.",
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export disagreement review CSV",
            "disagreement_review.csv",
            "CSV files (*.csv)",
        )
        if not path:
            return

        try:
            self._write_review_csv(path, self._review_result)
        except OSError as exc:
            QMessageBox.warning(
                self, "Disagreement Review",
                f"Could not write {path}:\n{exc}",
            )
            return
        QMessageBox.information(
            self, "Disagreement Review",
            f"Review CSV exported to:\n{path}",
        )

    @staticmethod
    def _write_review_csv(path: str, result: DisagreementReviewResult) -> None:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "Type", "Behavior", "Jump_time_s",
                "Review_start_s", "Review_end_s",
                "Reference_onset_s", "Reference_offset_s",
                "Trainee_onset_s", "Trainee_offset_s",
                "Onset_delta_s", "Offset_delta_s",
                "Overlap_s", "IoU",
                "Matching_window_s",
            ])
            window = result.matching_window_seconds
            for item in result.review_items:
                ref_onset = (
                    f"{item.reference.onset:.4f}" if item.reference else ""
                )
                ref_offset = (
                    f"{item.reference.offset:.4f}" if item.reference else ""
                )
                trn_onset = (
                    f"{item.trainee.onset:.4f}" if item.trainee else ""
                )
                trn_offset = (
                    f"{item.trainee.offset:.4f}" if item.trainee else ""
                )
                onset_delta = (
                    f"{item.onset_delta:.4f}"
                    if item.onset_delta is not None else ""
                )
                offset_delta = (
                    f"{item.offset_delta:.4f}"
                    if item.offset_delta is not None else ""
                )
                iou = (
                    f"{item.iou:.6f}" if item.iou is not None else ""
                )
                writer.writerow([
                    item.status,
                    item.behavior,
                    f"{item.jump_time:.4f}",
                    f"{item.review_start:.4f}",
                    f"{item.review_end:.4f}",
                    ref_onset,
                    ref_offset,
                    trn_onset,
                    trn_offset,
                    onset_delta,
                    offset_delta,
                    f"{item.overlap_seconds:.4f}",
                    iou,
                    f"{window:.4f}",
                ])

    # ------------------------------------------------------------------ #
    # Cleanup
    # ------------------------------------------------------------------ #

    def _on_spacebar(self) -> None:
        """Toggle video play/pause. Bound to Space via QShortcut so it
        fires regardless of which child widget has focus (a plain
        keyPressEvent would otherwise lose Space to focused buttons /
        checkboxes)."""
        if (
            self._video_model is not None
            and self._video_model.get_duration() > 0
        ):
            self._video_model.toggle_play()

    def closeEvent(self, event):
        # Release the dedicated PyAV container so we don't hold a file
        # handle (or ~50MB of codec context) until Python GCs the dialog.
        try:
            if self._video_model is not None:
                self._video_model.close()
        except Exception:
            self.logger.exception("DisagreementReviewDialog: video model close failed")
        finally:
            super().closeEvent(event)
