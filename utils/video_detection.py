"""
utils/video_detection.py - Video file detection that does not rely only on
file extensions.

Some recording pipelines write standard MP4/MKV/AVI containers under
non-standard suffixes (``.video``, ``.bin``, custom vendor extensions, or
typo'd extensions). The legacy RABET behaviour was a strict extension
whitelist that silently rejected those files even though PyAV can decode
them perfectly. This module centralises the detection logic so the rest
of the application can ask one question, ``is_video_file(path)``, and
get a robust answer.

Detection order (cheapest check first):

1. Extension whitelist - the fast path for the overwhelmingly common case.
2. Magic-number sniffing via the optional ``filetype`` library.
3. Last-resort trial-open via PyAV: if the file can be opened as a
   container with at least one video stream, accept it.

The cascade stops at the first successful step. ``filetype`` is treated
as optional; if it is not installed we fall straight through to PyAV.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable, Tuple

logger = logging.getLogger(__name__)

# Common video extensions used for the fast path. Kept slightly broader
# than the legacy hard-coded list inside views/main_window.py to also
# cover camcorder formats that PyAV decodes happily.
DEFAULT_VIDEO_EXTENSIONS: Tuple[str, ...] = (
    ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".mpg", ".mpeg", ".m4v",
    ".webm", ".flv", ".mts", ".m2ts", ".3gp", ".3g2", ".ts",
)


def has_video_extension(
    path: str,
    extensions: Iterable[str] = DEFAULT_VIDEO_EXTENSIONS,
) -> bool:
    """Return True iff ``path`` ends with a known video extension."""
    if not path:
        return False
    ext = os.path.splitext(path)[1].lower()
    return ext in tuple(e.lower() for e in extensions)


def sniff_video_magic(path: str) -> bool:
    """Return True iff the file's magic number identifies it as a video
    container. Uses the optional ``filetype`` library; returns False if
    the library is not installed."""
    try:
        import filetype  # type: ignore
    except ImportError:
        logger.debug("filetype library not available; skipping magic-number sniff")
        return False

    try:
        kind = filetype.guess(path)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Magic-number sniffing failed for %s: %s", path, exc)
        return False

    if kind is None:
        return False
    return kind.mime.startswith("video/")


def is_video_via_pyav(path: str) -> bool:
    """Last-resort: ask PyAV to open the file. Accept if it has at least
    one video stream that exposes a frame rate."""
    try:
        import av  # type: ignore
    except ImportError:  # pragma: no cover - PyAV is a hard dependency
        logger.warning("PyAV is not available; cannot trial-open %s", path)
        return False

    try:
        container = av.open(path)
    except Exception as exc:
        logger.debug("PyAV trial-open failed for %s: %s", path, exc)
        return False

    try:
        if not container.streams.video:
            return False
        stream = container.streams.video[0]
        # Accessing average_rate raises if the stream is broken / not
        # really a video stream.
        _ = stream.average_rate
        return True
    except Exception as exc:
        logger.debug("PyAV stream probe failed for %s: %s", path, exc)
        return False
    finally:
        try:
            container.close()
        except Exception as close_exc:  # pragma: no cover - defensive
            logger.debug(
                "Failed to close PyAV container for %s: %s",
                path, close_exc,
            )


def is_video_file(path: str) -> bool:
    """Decide whether ``path`` should be treated as a video file.

    Cascades through three checks in order of cost:

    1. Extension whitelist (cheapest).
    2. Magic-number sniff via the ``filetype`` library, if installed.
    3. PyAV trial-open (most expensive but most reliable).

    Returns False if the path does not exist or none of the checks
    succeed.
    """
    if not path:
        return False
    if not os.path.isfile(path):
        return False

    if has_video_extension(path):
        return True

    if sniff_video_magic(path):
        logger.info("Accepted as video by magic-number sniff: %s", path)
        return True

    if is_video_via_pyav(path):
        logger.info("Accepted as video by PyAV trial-open: %s", path)
        return True

    return False


def video_file_dialog_filter() -> str:
    """Return the filter string used by QFileDialog.getOpenFileName(s).

    The common extensions are presented as the default; "All Files" is
    appended so users can still pick a file whose extension is unusual,
    relying on the downstream ``is_video_file`` check to validate it.
    """
    primary = " ".join(f"*{ext}" for ext in DEFAULT_VIDEO_EXTENSIONS)
    return f"Video Files ({primary});;All Files (*)"
