"""Partial content hash used for relink matching (PR-S3)."""

from __future__ import annotations

from utils.content_hash import compute_partial_hash


def _write(path, data: bytes):
    path.write_bytes(data)
    return str(path)


def test_deterministic_same_content(tmp_path):
    a = _write(tmp_path / "a.bin", b"hello world" * 10)
    assert compute_partial_hash(a) is not None
    assert compute_partial_hash(a) == compute_partial_hash(a)


def test_identical_content_different_files_match(tmp_path):
    data = b"abcdefghij" * 100
    a = _write(tmp_path / "a.bin", data)
    b = _write(tmp_path / "b.bin", data)
    assert compute_partial_hash(a) == compute_partial_hash(b)


def test_one_byte_change_in_head_differs(tmp_path):
    a = _write(tmp_path / "a.bin", b"A" + b"x" * 1000)
    b = _write(tmp_path / "b.bin", b"B" + b"x" * 1000)
    assert compute_partial_hash(a) != compute_partial_hash(b)


def test_one_byte_change_in_tail_differs(tmp_path):
    # Small head/tail so the middle is skipped but the trailing byte is hashed.
    a = _write(tmp_path / "a.bin", b"x" * 1000 + b"A")
    b = _write(tmp_path / "b.bin", b"x" * 1000 + b"B")
    assert compute_partial_hash(a, head=4, tail=4) != compute_partial_hash(
        b, head=4, tail=4
    )


def test_size_change_differs(tmp_path):
    a = _write(tmp_path / "a.bin", b"x" * 100)
    b = _write(tmp_path / "b.bin", b"x" * 101)
    assert compute_partial_hash(a) != compute_partial_hash(b)


def test_mid_size_covers_all_bytes(tmp_path):
    # head < size <= head+tail: the remainder is hashed, so a change between the
    # head window and the tail is still detected (no bytes are skipped).
    a = _write(tmp_path / "a.bin", b"xxxxx" + b"A" + b"x")  # size 7
    b = _write(tmp_path / "b.bin", b"xxxxx" + b"B" + b"x")
    assert compute_partial_hash(a, head=4, tail=4) != compute_partial_hash(
        b, head=4, tail=4
    )


def test_missing_file_returns_none(tmp_path):
    assert compute_partial_hash(str(tmp_path / "nope.bin")) is None
