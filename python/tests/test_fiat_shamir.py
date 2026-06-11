"""Tests for `grover_tax.fiat_shamir` — in-proof FS derivation (KB-9, #121)."""

from __future__ import annotations

import hashlib

import pytest

from grover_tax.fiat_shamir import derive_cases


def test_cross_vector_matches_rust_and_hashlib() -> None:
    """The shared cross-vector asserted bit-for-bit by kickmix::fiat_shamir.

    seed = sha256(b"iadd64-demo"); width=64; num_samples=4. The Rust SP1-side
    derivation (kickmix/src/fiat_shamir.rs) hardcodes these same pairs, so a
    match here proves both stacks derive byte-identical case streams.
    """
    seed = hashlib.sha256(b"iadd64-demo").digest()
    assert derive_cases(seed, 64, 4) == [
        (4113191057548519565, 17909937566100645171),
        (1222146416732106357, 15712575212200367868),
        (3544430547654831529, 45149841657852178),
        (18158939369488272335, 16905458393758049869),
    ]


def test_derivation_is_a_function_of_circuit_hash() -> None:
    """Fiat-Shamir property: a different circuit hash yields different inputs."""
    a = derive_cases(b"\x01" * 32, 64, 4)
    b = derive_cases(b"\x02" * 32, 64, 4)
    assert a != b


def test_deterministic() -> None:
    seed = hashlib.sha256(b"determinism").digest()
    assert derive_cases(seed, 64, 8) == derive_cases(seed, 64, 8)


def test_operands_respect_width() -> None:
    seed = hashlib.sha256(b"width").digest()
    for x, y in derive_cases(seed, 8, 64):
        assert 0 <= x < 256
        assert 0 <= y < 256


def test_xof_seeding_matches_hashlib_shake256() -> None:
    """The XOF seed is the circuit hash; bytes match hashlib.shake_256 directly."""
    seed = hashlib.sha256(b"anchor").digest()
    cases = derive_cases(seed, 64, 2)
    buf = hashlib.shake_256(seed).digest(2 * 2 * 8)
    expected = [
        (
            int.from_bytes(buf[0:8], "little"),
            int.from_bytes(buf[8:16], "little"),
        ),
        (
            int.from_bytes(buf[16:24], "little"),
            int.from_bytes(buf[24:32], "little"),
        ),
    ]
    assert cases == expected


def test_rejects_bad_args() -> None:
    with pytest.raises(ValueError):
        derive_cases(b"\x00" * 32, 0, 4)
    with pytest.raises(ValueError):
        derive_cases(b"\x00" * 32, 64, 0)
