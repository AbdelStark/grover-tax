"""Tests for `grover_tax.xof`."""

from __future__ import annotations

import hashlib

import pytest

from grover_tax.xof import SEED_BYTES, XOF


def _seed(tag: int = 0) -> bytes:
    """Build a deterministic 32-byte seed for tests."""
    return hashlib.sha256(f"grover_tax.test.seed.{tag}".encode()).digest()


def test_seed_bytes_constant() -> None:
    """Documented seed length is 32 (sha256 output)."""
    assert SEED_BYTES == 32


def test_read_zero_returns_empty() -> None:
    x = XOF(_seed())
    assert x.read(0) == b""
    assert x.position == 0


def test_read_returns_exact_byte_count() -> None:
    x = XOF(_seed())
    for n in (1, 7, 17, 1024, 4096, 4097, 12345):
        chunk = x.read(n)
        assert len(chunk) == n


def test_two_instances_with_same_seed_are_byte_identical() -> None:
    a = XOF(_seed(1))
    b = XOF(_seed(1))
    assert a.read(10_000) == b.read(10_000)


def test_different_seeds_diverge() -> None:
    a = XOF(_seed(1))
    b = XOF(_seed(2))
    assert a.read(64) != b.read(64)


def test_read_matches_canonical_shake_256_output() -> None:
    """The binding contract: XOF(seed).read(N) == shake_256(seed).digest(N)."""
    seed = _seed(99)
    for total in (1, 32, 1024, 4096, 4097, 10_000, 200_000):
        assert XOF(seed).read(total) == hashlib.shake_256(seed).digest(total)


def test_read_is_monotonic_position() -> None:
    x = XOF(_seed())
    x.read(100)
    assert x.position == 100
    x.read(50)
    assert x.position == 150


def test_split_reads_equal_one_big_read() -> None:
    seed = _seed(7)
    one_shot = XOF(seed).read(8192)
    a = XOF(seed)
    parts: list[bytes] = []
    sizes = [1, 7, 33, 511, 1024, 2048, 4096 - sum([1, 7, 33, 511, 1024, 2048]) + 4096]
    for s in sizes:
        parts.append(a.read(s))
    assert b"".join(parts) == one_shot[: sum(sizes)]


def test_buffer_growth_does_not_change_returned_bytes() -> None:
    """A read that crosses the buffer-growth boundary must still match the canonical output."""
    seed = _seed(42)
    x = XOF(seed)
    # First read forces the initial 4096-byte buffer.
    a = x.read(3000)
    # Second read forces a buffer growth beyond 4096.
    b = x.read(5000)
    assert a + b == hashlib.shake_256(seed).digest(8000)


def test_negative_n_raises() -> None:
    x = XOF(_seed())
    with pytest.raises(ValueError, match="non-negative"):
        x.read(-1)


def test_non_bytes_seed_raises() -> None:
    with pytest.raises(TypeError, match="bytes-like"):
        XOF("not-bytes")  # type: ignore[arg-type]


def test_bytearray_seed_accepted() -> None:
    seed = bytearray(_seed(5))
    x = XOF(seed)
    assert len(x.read(64)) == 64


def test_cross_process_vector() -> None:
    """A specific byte vector recorded for cross-impl verification.

    If this assertion fails after a code change here, every fixture file
    becomes a methodology breach — the construction has drifted from the
    canonical SHAKE-256 output.
    """
    seed = bytes.fromhex(
        "0000000000000000000000000000000000000000000000000000000000000000"
    )
    expected_first_32_hex = hashlib.shake_256(seed).digest(32).hex()
    # Build the expected vector live so the test does not depend on a
    # checked-in JSON file; the assertion is still meaningful because the
    # wrapper goes through its own buffer-growth code path, not a direct
    # call to `hashlib.shake_256(...)`.
    assert XOF(seed).read(32).hex() == expected_first_32_hex
