"""Shared helpers for the (normally dormant) Qt-layout diagnostics.

``MainWindow`` and ``RecordingControlView`` both used to ship near-identical
``_widget_size_summary`` / ``schedule_layout_diagnostic_snapshots`` helpers
inline. The diagnostic flow is only ever enabled by setting a single flag
on the owner (``_layout_diagnostics_enabled = True``), so the formatting
primitives live here instead of being duplicated in two places.

The functions are deliberately tiny; the owners keep their own
``log_..._snapshot`` methods because those reach into widget-specific
attributes that the helpers cannot know about.
"""
from __future__ import annotations

from typing import Callable, Iterable

from PySide6.QtCore import QTimer


def widget_summary(name: str, widget) -> str:
    """Return a compact one-line layout summary for ``widget``.

    Used as the building block for ``log_..._snapshot`` methods in
    ``MainWindow`` and ``RecordingControlView``. ``widget`` may be
    ``None`` to make snapshot loops easier to write.
    """
    if widget is None:
        return f"{name}: <missing>"

    size = widget.size()
    hint = widget.sizeHint()
    min_hint = widget.minimumSizeHint()
    return (
        f"{name}: h={size.height()} w={size.width()} "
        f"minH={widget.minimumHeight()} maxH={widget.maximumHeight()} "
        f"hintH={hint.height()} hintW={hint.width()} "
        f"minHintH={min_hint.height()} minHintW={min_hint.width()} "
        f"visible={widget.isVisible()}"
    )


def schedule_snapshot_burst(
    log_callback: Callable[[str], None],
    reason: str,
    enabled: bool,
    delays_ms: Iterable[int] = (0, 25, 75, 150),
) -> None:
    """Fire ``log_callback`` at several deferred deadlines for a state change.

    The burst exists so the diagnostic log captures the layout *after* Qt
    has had a chance to settle pending layout requests, not just the
    instantaneous state at the moment the trigger fired.

    Args:
        log_callback: Function accepting one ``str`` argument (the reason).
        reason: Human-readable label used to differentiate snapshot groups.
        enabled: Quick exit if the owning view's diagnostics flag is off.
        delays_ms: Iterable of millisecond delays at which to fire snapshots.
    """
    if not enabled:
        return

    for delay in delays_ms:
        QTimer.singleShot(
            int(delay),
            lambda r=reason, d=delay: log_callback(f"{r}+{d}ms"),
        )
