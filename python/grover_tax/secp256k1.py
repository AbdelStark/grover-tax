"""secp256k1 reference math + canonical serialisation for `gen_fixtures.py`.

Wraps `coincurve` (libsecp256k1 bindings) to provide:

* `sample_point_pair(xof) -> tuple[Point, Point]` — deterministically draws
  two affine secp256k1 points from a `grover_tax.xof.XOF`. Both returned
  points are normalised to even Y (negated if necessary) so that storing
  only their X coordinates is unambiguous.
* `add(P, Q) -> Point` — point addition via libsecp256k1.
* `serialize_x(P, Q) -> bytes` — canonical 64-byte (= 128 hex character)
  encoding of the input pair: ``P.X || Q.X`` big-endian. Matches
  `fixtures/v0.1.json`'s `x_hex` length per
  `docs/spec/03-data-model.md` §"Fixture".
* `serialize_y(R) -> bytes` — canonical 33-byte (= 66 hex character)
  compressed encoding of the result point. Matches `y_hex`.

Encoding choice & rationale:

The data-model spec gives `x_hex` length `128` and labels it
"pair of compressed-affine secp256k1 points". 33 + 33 = 66 bytes / 132
hex characters, so the literal "128" cannot be the compressed-pair form;
it is exactly the right size for two raw 32-byte X coordinates. We follow
the schema's *number* (which is what every other piece of the system —
the schema validator, the Rust regenerator, the Cairo on-the-wire format
— ultimately keys on) and reconstruct Y on the consumer side from the
even-Y convention. `sample_point_pair` enforces the convention by
negating any sampled point with odd Y, so the X-only form is lossless.

`y_hex` is the full compressed encoding (sign byte + X = 33 bytes) of the
result, so the comparison `add(P, Q) == decode(y_hex)` is precise and
sign-checking; the verifier does *not* assume even Y for the result.
"""

from __future__ import annotations

from dataclasses import dataclass

from coincurve import PrivateKey, PublicKey

from grover_tax.xof import XOF

__all__ = [
    "GENERATOR",
    "SECP256K1_ORDER",
    "Point",
    "add",
    "decode_compressed",
    "is_on_curve",
    "sample_point_pair",
    "serialize_x",
    "serialize_y",
]

# secp256k1 group order n.
SECP256K1_ORDER = int(
    "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141", 16
)

# secp256k1 prime field modulus p.
SECP256K1_P = int(
    "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F", 16
)


@dataclass(frozen=True)
class Point:
    """Affine secp256k1 point. `x` and `y` are integers in `[0, p)`."""

    x: int
    y: int

    @classmethod
    def from_coincurve(cls, pk: PublicKey) -> Point:
        x, y = pk.point()
        return cls(x=x, y=y)

    def to_coincurve(self) -> PublicKey:
        return PublicKey(self.to_uncompressed_bytes())

    def to_uncompressed_bytes(self) -> bytes:
        """65-byte SEC1 uncompressed form (0x04 prefix + X || Y)."""
        return b"\x04" + self.x.to_bytes(32, "big") + self.y.to_bytes(32, "big")

    def to_compressed_bytes(self) -> bytes:
        """33-byte SEC1 compressed form (sign-byte + X)."""
        prefix = b"\x02" if (self.y & 1) == 0 else b"\x03"
        return prefix + self.x.to_bytes(32, "big")

    def negated(self) -> Point:
        """Reflection across the X axis: ``(x, y) → (x, p - y)``."""
        return Point(x=self.x, y=(SECP256K1_P - self.y) % SECP256K1_P)


# Generator G of secp256k1 (SEC2 §2.4.1).
GENERATOR = Point(
    x=int("79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798", 16),
    y=int("483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8", 16),
)

# secp256k1 curve constants (y² = x³ + b mod p; a = 0).
_CURVE_B = 7

# SEC1 compressed-point format constants.
_COMPRESSED_LEN = 33
_COMPRESSED_EVEN_Y_TAG = 0x02
_COMPRESSED_ODD_Y_TAG = 0x03


def is_on_curve(p: Point) -> bool:
    """Membership check ``y² ≡ x³ + 7 (mod p)``."""
    return (p.y * p.y - (p.x * p.x * p.x + _CURVE_B)) % SECP256K1_P == 0


def add(p: Point, q: Point) -> Point:
    """Affine point addition via libsecp256k1."""
    combined = PublicKey.combine_keys([p.to_coincurve(), q.to_coincurve()])
    return Point.from_coincurve(combined)


def _sample_scalar(xof: XOF) -> int:
    """Deterministically draw a scalar in ``[1, SECP256K1_ORDER)`` from `xof`.

    Uses rejection sampling: read 32 bytes, interpret big-endian, retry if the
    value is `0` or `>= SECP256K1_ORDER`. The probability of either is roughly
    `2**-128`, so the loop almost always terminates after one iteration.
    """
    while True:
        candidate = int.from_bytes(xof.read(32), "big")
        if 1 <= candidate < SECP256K1_ORDER:
            return candidate


def sample_point_pair(xof: XOF) -> tuple[Point, Point]:
    """Deterministically sample two even-Y secp256k1 points from `xof`.

    Each point is computed as ``scalar * G`` for a fresh rejection-sampled
    scalar. The point is then normalised so that its Y coordinate is even
    (negated if not) — this makes the 32-byte X-coordinate alone a lossless
    encoding of the point on the consumer side.
    """
    return _sample_even_y_point(xof), _sample_even_y_point(xof)


def _sample_even_y_point(xof: XOF) -> Point:
    scalar = _sample_scalar(xof)
    pk = PrivateKey(scalar.to_bytes(32, "big")).public_key
    p = Point.from_coincurve(pk)
    if (p.y & 1) == 1:
        p = p.negated()
    return p


def serialize_x(p: Point, q: Point) -> bytes:
    """Encode the input pair as 64 bytes — ``P.X || Q.X`` big-endian.

    Sign bit is implicit (always 0 / even Y); see module docstring. Length
    matches the fixture schema's `x_hex` field at 128 hex characters.
    """
    return p.x.to_bytes(32, "big") + q.x.to_bytes(32, "big")


def serialize_y(r: Point) -> bytes:
    """Encode the result point as 33 bytes — compressed SEC1 form.

    Length matches the fixture schema's `y_hex` field at 66 hex characters.
    """
    return r.to_compressed_bytes()


def decode_compressed(data: bytes) -> Point:
    """Inverse of `to_compressed_bytes` — for verifier-side tests.

    Recovers ``y`` from ``x`` and the leading sign byte by solving
    ``y² = x³ + 7 (mod p)`` and choosing the root with the matching parity.
    """
    if len(data) != _COMPRESSED_LEN or data[0] not in (
        _COMPRESSED_EVEN_Y_TAG,
        _COMPRESSED_ODD_Y_TAG,
    ):
        raise ValueError(f"decode_compressed: not a 33-byte SEC1 compressed point: {data!r}")
    x = int.from_bytes(data[1:], "big")
    rhs = (pow(x, 3, SECP256K1_P) + _CURVE_B) % SECP256K1_P
    # `p` is a prime ≡ 3 (mod 4), so the square root is `rhs ** ((p+1)/4)`.
    y = pow(rhs, (SECP256K1_P + 1) // 4, SECP256K1_P)
    if (y * y) % SECP256K1_P != rhs:
        raise ValueError(f"decode_compressed: x={x:x} is not on secp256k1")
    desired_parity = 0 if data[0] == _COMPRESSED_EVEN_Y_TAG else 1
    if (y & 1) != desired_parity:
        y = (SECP256K1_P - y) % SECP256K1_P
    return Point(x=x, y=y)
