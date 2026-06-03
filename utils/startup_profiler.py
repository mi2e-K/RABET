"""Lightweight startup profiler (PR-STARTUP-01).

Records ``perf_counter`` milestones during application start so we can see, per
stage, where time goes -- the baseline for the import-deferral work that follows
(PR-STARTUP-02+). Standard-library only, so it works in packaged builds.

Set the environment variable ``RABET_STARTUP_PROFILE=1`` for a per-mark INFO log;
a single one-line summary is always emitted at the end. Profiling never raises
into the startup path.
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)


def _env_enabled() -> bool:
    value = os.environ.get("RABET_STARTUP_PROFILE", "").strip().lower()
    return value in ("1", "true", "yes", "on")


class StartupProfiler:
    """Collect (label, cumulative_ms, delta_ms) milestones during startup."""

    def __init__(self, enabled: bool | None = None) -> None:
        self._enabled = _env_enabled() if enabled is None else bool(enabled)
        now = time.perf_counter()
        self._t0 = now
        self._last = now
        self._marks: list[tuple[str, float, float]] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def marks(self) -> list[tuple[str, float, float]]:
        """Recorded milestones as (label, cumulative_ms, delta_ms)."""
        return list(self._marks)

    def mark(self, label: str) -> None:
        """Record a milestone; log it per-mark only when enabled."""
        try:
            now = time.perf_counter()
            cum_ms = (now - self._t0) * 1000.0
            delta_ms = (now - self._last) * 1000.0
            self._last = now
            self._marks.append((label, cum_ms, delta_ms))
            if self._enabled:
                logger.info(
                    "[startup] %s @ %.1fms (+%.1fms)", label, cum_ms, delta_ms
                )
        except Exception:
            # Never let profiling break startup.
            pass

    def summary(self) -> None:
        """Emit a single-line summary of all milestones (always, cheaply)."""
        try:
            if not self._marks:
                return
            total_ms = self._marks[-1][1]
            parts = " ".join(
                f"{label}={delta:.0f}" for label, _cum, delta in self._marks
            )
            logger.info("[startup] total %.0fms: %s", total_ms, parts)
        except Exception:
            pass
