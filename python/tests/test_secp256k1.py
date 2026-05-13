"""Tests for `grover_tax.secp256k1`."""

from __future__ import annotations

import hashlib

import pytest

from grover_tax.secp256k1 import (
    GENERATOR,
    SECP256K1_ORDER,
    Point,
    add,
    decode_compressed,
    is_on_curve,
    sample_point_pair,
    serialize_x,
    serialize_y,
)
from grover_tax.xof import XOF

# Reference value for 2G on secp256k1 (Wikipedia / SEC1 / many test vectors).
TWO_G = Point(
    x=int("C6047F9441ED7D6D3045406E95C07CD85C778E4B8CEF3CA7ABAC09B95C709EE5", 16),
    y=int("1AE168FEA63DC339A3C58419466CEAEEF7F632653266D0E1236431A950CFE52A", 16),
)


def _seed(tag: int = 0) -> bytes:
    return hashlib.sha256(f"grover_tax.test.secp256k1.{tag}".encode()).digest()


def test_generator_is_on_curve() -> None:
    assert is_on_curve(GENERATOR)


def test_two_g_matches_published_constant() -> None:
    """Acceptance bullet: add(G, G) matches the published 2G constant."""
    got = add(GENERATOR, GENERATOR)
    assert got == TWO_G


def test_add_g_plus_2g_equals_3g() -> None:
    """Triple-check via scalar mul: G + 2G == 3G (computed via coincurve)."""
    from coincurve import PrivateKey  # local import to keep top-level deps minimal
    pk = PrivateKey((3).to_bytes(32, "big")).public_key
    three_g = Point.from_coincurve(pk)
    assert add(GENERATOR, TWO_G) == three_g


def test_sampled_points_are_on_curve() -> None:
    """Acceptance bullet: every sampled point is on-curve."""
    x = XOF(_seed(1))
    for _ in range(20):
        p, q = sample_point_pair(x)
        assert is_on_curve(p)
        assert is_on_curve(q)


def test_sample_point_pair_returns_even_y() -> None:
    """Sampled points are even-Y normalised (so X-only encoding is lossless)."""
    x = XOF(_seed(2))
    for _ in range(20):
        p, q = sample_point_pair(x)
        assert (p.y & 1) == 0, f"P.y is odd: {p.y:x}"
        assert (q.y & 1) == 0, f"Q.y is odd: {q.y:x}"


def test_sample_is_deterministic() -> None:
    a = XOF(_seed(7))
    b = XOF(_seed(7))
    assert sample_point_pair(a) == sample_point_pair(b)


def test_serialize_x_is_128_hex_chars() -> None:
    """Length matches the fixture schema's `x_hex` field."""
    x = XOF(_seed(9))
    p, q = sample_point_pair(x)
    data = serialize_x(p, q)
    assert len(data) == 64
    assert len(data.hex()) == 128


def test_serialize_y_is_66_hex_chars() -> None:
    """Length matches the fixture schema's `y_hex` field."""
    data = serialize_y(TWO_G)
    assert len(data) == 33
    assert len(data.hex()) == 66
    assert data[0] in (0x02, 0x03)


def test_decode_compressed_round_trips_for_2g() -> None:
    assert decode_compressed(serialize_y(TWO_G)) == TWO_G


def test_decode_compressed_round_trips_for_random_points() -> None:
    x = XOF(_seed(11))
    for _ in range(10):
        p, _ = sample_point_pair(x)
        assert decode_compressed(p.to_compressed_bytes()) == p


def test_decode_compressed_rejects_bad_length() -> None:
    with pytest.raises(ValueError, match="33-byte SEC1"):
        decode_compressed(b"\x02" + b"\x00" * 31)


def test_decode_compressed_rejects_bad_prefix() -> None:
    with pytest.raises(ValueError, match="33-byte SEC1"):
        decode_compressed(b"\x04" + b"\x00" * 32)


def test_decode_compressed_rejects_off_curve_x() -> None:
    # x=0 is not on secp256k1 (0^3 + 7 = 7 is not a QR mod p).
    bad = b"\x02" + b"\x00" * 32
    with pytest.raises(ValueError, match="not on secp256k1"):
        decode_compressed(bad)


def test_point_to_uncompressed_starts_with_0x04() -> None:
    assert GENERATOR.to_uncompressed_bytes()[0] == 0x04


def test_point_negated_inverts_y_parity() -> None:
    p = TWO_G
    neg = p.negated()
    assert (p.y + neg.y) % 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F == 0
    assert (p.y & 1) != (neg.y & 1)


def test_secp256k1_order_constant() -> None:
    """Sanity check on the curve order constant — used by rejection sampling."""
    assert (
        SECP256K1_ORDER
        == 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
    )


def test_known_addition_vectors() -> None:
    """Cross-validation against ten known additions (k*G + m*G == (k+m)*G).

    Uses coincurve as the reference math; our wrapper must agree for each.
    """
    from coincurve import PrivateKey
    pairs = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16), (17, 18), (19, 20)]
    for k, m in pairs:
        p = Point.from_coincurve(PrivateKey(k.to_bytes(32, "big")).public_key)
        q = Point.from_coincurve(PrivateKey(m.to_bytes(32, "big")).public_key)
        expected = Point.from_coincurve(PrivateKey((k + m).to_bytes(32, "big")).public_key)
        assert add(p, q) == expected
