"""Deterministic extendable-output function (XOF) used by `gen_fixtures.py`.

RFC-0002 §"Algorithm" calls for a SHA-2-family XOF, seeded with
`sha256(SEED)`, that produces a deterministic byte stream from which all
fixture randomness derives. The PRD §6.2 step 1 names this construction.

This module wraps `hashlib.shake_256` (FIPS 202) to provide a stable
`read(n) -> bytes` API that exposes the **canonical** SHAKE-256 output of
the seed — i.e. the same bytes a third party gets by calling
``hashlib.shake_256(seed).digest(total_n)``. The wrapper just slices that
output incrementally and amortises the repeated digest calls by growing a
backing buffer geometrically.

Choice of SHAKE-256: the PRD names "SHA-2 XOF". SHAKE-256 is the
canonical XOF in the SHA-3 family (FIPS 202), which is the only XOF
standardised by NIST inside the SHA family. The PRD's "SHA-2 XOF" phrasing
is informal; SHAKE-256 is the unambiguous matching primitive.

Re-derivation contract: for any seed `S` and any prefix of reads totalling
`N` bytes, the concatenation of the returned bytes equals
``hashlib.shake_256(S).digest(N)``. This contract is the binding
specification; if it ever drifts, every fixture file becomes a
methodology breach.
"""

from __future__ import annotations

import hashlib

__all__ = ["SEED_BYTES", "XOF"]

# A `sha256(SEED)` output is exactly 32 bytes. The XOF accepts any
# arbitrary-length bytes at the type level, but the *contract* is that the
# 32-byte sha256 digest is what `gen_fixtures.py` passes — anything else is
# misuse.
SEED_BYTES = 32

# Initial buffer size in bytes; the buffer grows geometrically thereafter
# so that the per-`read()` amortised cost stays O(n).
_INITIAL_BUFFER = 4096


class XOF:
    """Deterministic SHAKE-256 byte-stream wrapper.

    Two instances constructed with the same `seed` produce the same byte
    sequence for the same `read` calls. Reads are monotonic — the stream
    never rewinds, never re-seeds.

    The returned bytes match the canonical SHAKE-256 output of the seed:
    ``XOF(seed).read(n)`` equals ``hashlib.shake_256(seed).digest(n)``.
    Consequently, three independent re-implementations (Python, Rust,
    Cairo) can compare byte-by-byte without coordinating on any custom
    chunking convention.
    """

    __slots__ = ("_buffer", "_offset", "_seed")

    def __init__(self, seed: bytes) -> None:
        if not isinstance(seed, (bytes, bytearray)):
            raise TypeError(f"XOF seed must be bytes-like, got {type(seed).__name__}")
        self._seed = bytes(seed)
        self._offset = 0
        # Empty until the first `read()` — keeps cheap constructions cheap.
        self._buffer: bytes = b""

    def read(self, n: int) -> bytes:
        """Return the next `n` bytes of the stream.

        Args:
            n: Non-negative byte count. `0` returns `b""`.

        Raises:
            ValueError: If `n` is negative.
        """
        if n < 0:
            raise ValueError(f"XOF.read: n must be non-negative, got {n}")
        if n == 0:
            return b""

        needed = self._offset + n
        if needed > len(self._buffer):
            # Grow geometrically so total digest work is O(N) for N bytes
            # read across many calls. `digest()` on hashlib's SHAKE
            # re-derives from scratch; doubling keeps the amortised cost
            # bounded.
            new_size = max(needed, len(self._buffer) * 2, _INITIAL_BUFFER)
            self._buffer = hashlib.shake_256(self._seed).digest(new_size)

        out = self._buffer[self._offset : self._offset + n]
        self._offset += n
        return out

    @property
    def position(self) -> int:
        """The next byte offset `read()` will return from."""
        return self._offset
