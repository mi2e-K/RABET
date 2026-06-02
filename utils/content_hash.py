"""Partial content hashing for project video relink (PR-S3 / BUG-006).

The video id is a fixed uuid (PR-S2) so it survives moving the project folder.
When an *external* video's path can no longer be resolved (it was moved or
renamed outside the project), RABET offers to relink it. To confirm a candidate
file is really the same video we compare a *partial* content hash: sha1 over the
file size plus the first and last N bytes. This is O(head+tail) IO even for
multi-GB videos and changes whenever the content changes.

It is deliberately NOT used as the video id: a content-preserving re-wrap should
not change identity (the uuid handles that). The hash is only a relink/sameness
heuristic.
"""

from __future__ import annotations

import hashlib
import os

_DEFAULT_CHUNK = 8 * 1024 * 1024  # 8 MB head + 8 MB tail


def compute_partial_hash(path, head=_DEFAULT_CHUNK, tail=_DEFAULT_CHUNK):
    """Return a hex sha1 over (size + first ``head`` bytes + last ``tail`` bytes).

    For files no larger than ``head + tail`` the whole file is hashed, with no
    bytes skipped or double-counted. Returns ``None`` if the file cannot be read
    (missing / permission / not a regular file), so callers can treat an
    unreadable file as "no hash available".
    """
    try:
        size = os.path.getsize(path)
        digest = hashlib.sha1()
        digest.update(str(size).encode("utf-8"))
        with open(path, "rb") as handle:
            digest.update(handle.read(head))
            if size > head:
                if size > head + tail:
                    # Skip the middle; hash only the trailing window.
                    handle.seek(-tail, os.SEEK_END)
                    digest.update(handle.read(tail))
                else:
                    # head < size <= head + tail: hash the remainder so every
                    # byte is covered exactly once.
                    digest.update(handle.read())
        return digest.hexdigest()
    except OSError:
        return None
