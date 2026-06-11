"""In-proof Fiat-Shamir test-case derivation — Python reference (KB-9, #121).

The reference benchmark derives its fuzz-test inputs *inside the proof* from the
circuit hash, via the Fiat-Shamir heuristic, so a cheating prover cannot pick
inputs its circuit gets wrong (`getting_started.md` §"Using Fuzz Testing as a
Proof Strategy"). This module is the authoritative reference for that
derivation; the SP1 Rust side (`kickmix::fiat_shamir`) and the Stwo Cairo side
must reproduce its byte stream exactly.

Algorithm (see `docs/spec/v0.3/FIAT-SHAMIR.md`):

1. Seed SHAKE-256 with the circuit hash `H(C)` (the cross-comparable
   `kmx_source_sha256` over the raw `.kmx` bytes).
2. For each of `num_samples` cases, read `ceil(width/8)` little-endian bytes for
   `x` then the same for `y`, masking each to `width` bits — the same layout as
   the supplied-case generator (`grover_tax.registers.iadd_test_cases`), but
   seeded by the circuit hash rather than a fixed constant.

Tier-1 cases are supplied; Tier-2 cases come from here, so the fixture no longer
needs to carry `test_cases` (only the circuit + demanded bounds).
"""

from __future__ import annotations

from grover_tax.xof import XOF

__all__ = ["derive_cases"]

_BITS_PER_BYTE = 8


def derive_cases(circuit_hash: bytes, width: int, num_samples: int) -> list[tuple[int, int]]:
    """Derive `num_samples` register-input pairs `(x, y)` from `circuit_hash`.

    `circuit_hash` is the SHAKE-256 seed (typically the 32-byte
    `kmx_source_sha256`). Returns unsigned residues in ``[0, 2^width)``.

    Raises:
        ValueError: if `width` or `num_samples` is non-positive.
    """
    if width <= 0:
        raise ValueError(f"derive_cases: width must be positive, got {width}")
    if num_samples <= 0:
        raise ValueError(f"derive_cases: num_samples must be positive, got {num_samples}")

    xof = XOF(circuit_hash)
    nbytes = (width + _BITS_PER_BYTE - 1) // _BITS_PER_BYTE
    mask = (1 << width) - 1

    cases: list[tuple[int, int]] = []
    for _ in range(num_samples):
        x = int.from_bytes(xof.read(nbytes), "little") & mask
        y = int.from_bytes(xof.read(nbytes), "little") & mask
        cases.append((x, y))
    return cases
