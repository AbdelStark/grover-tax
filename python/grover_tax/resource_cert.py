"""Resource certification + verifier assertions — harness side (KB-10, #122).

Mirrors `kickmix::resource` (Rust) and `stwo-side/cairo/src/kickmix.cairo` Cairo
`certify`: the verifier asserts a proven circuit stays within demanded resource
bounds — at least `num_samples` fuzz cases, and at most the demanded qubit /
non-Clifford / instruction caps — alongside the upstream sentinel `42`
(`getting_started.md`, `verifier/verifier.rs`).

`count_kmx` counts the kickmix instruction stream directly from `.kmx` text so
the count matches both prover sides: instructions include `REGISTER` /
`APPEND_TO_REGISTER` metadata (e.g. `iadd64` = 757), the non-Clifford count is
the `CCX`/`CCZ` total (125), and the qubit count is one past the largest `qN`
index (128) — the upstream figures.

`uv run apples-verify` (and `bin/apples-verify`) runs the check; a circuit
exceeding any bound is rejected with `PROVER.VERIFIER_REJECTED` (exit 1).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from grover_tax.errors import PROVER_EXIT_CODE, ProverError, ProverSubcode

__all__ = [
    "SENTINEL",
    "DemandedBounds",
    "ResourceCounts",
    "certify",
    "count_kmx",
    "main",
    "public_outputs",
]

SENTINEL = 42
_QUBIT_RE = re.compile(r"\bq([0-9]+)\b")
_NON_CLIFFORD = frozenset({"CCX", "CCZ"})


@dataclass(frozen=True)
class ResourceCounts:
    """Actual resource usage committed by the prover."""

    num_samples: int
    max_qubit_count: int
    max_non_clifford_count: int
    max_circuit_instructions: int


@dataclass(frozen=True)
class DemandedBounds:
    """Bounds the verifier demands (from the fixture, KB-4)."""

    num_samples: int
    max_qubit_count: int
    max_non_clifford_count: int
    max_circuit_instructions: int


def count_kmx(text: str, num_samples: int) -> ResourceCounts:
    """Count kickmix resources from `.kmx` source text.

    Instructions include metadata lines (matching upstream's 757 for iadd64);
    non-Clifford = `CCX`/`CCZ` count; qubit count = max `qN` index + 1.
    """
    instructions = 0
    non_clifford = 0
    max_qubit = -1
    for raw in text.splitlines():
        code = raw.split("#", 1)[0].strip()
        if not code:
            continue
        instructions += 1
        name = code.split()[0]
        if name in _NON_CLIFFORD:
            non_clifford += 1
        for m in _QUBIT_RE.finditer(code):
            max_qubit = max(max_qubit, int(m.group(1)))
    return ResourceCounts(
        num_samples=num_samples,
        max_qubit_count=max_qubit + 1,
        max_non_clifford_count=non_clifford,
        max_circuit_instructions=instructions,
    )


def public_outputs(counts: ResourceCounts) -> tuple[int, int, int, int, int]:
    """The ordered integer public outputs, ending in the sentinel `42`."""
    return (
        counts.num_samples,
        counts.max_qubit_count,
        counts.max_non_clifford_count,
        counts.max_circuit_instructions,
        SENTINEL,
    )


def certify(counts: ResourceCounts, sentinel: int, demanded: DemandedBounds) -> list[str]:
    """Return the list of violations (empty = accepted).

    `num_samples >= demanded` (at least), each resource count `<= demanded` (at
    most), sentinel `== 42` — the same comparisons as the Rust/Cairo `certify`.
    """
    violations: list[str] = []
    if counts.num_samples < demanded.num_samples:
        violations.append(f"too few samples: {counts.num_samples} < {demanded.num_samples}")
    if counts.max_qubit_count > demanded.max_qubit_count:
        violations.append(
            f"qubit cap exceeded: {counts.max_qubit_count} > {demanded.max_qubit_count}"
        )
    if counts.max_non_clifford_count > demanded.max_non_clifford_count:
        violations.append(
            f"non-Clifford cap exceeded: {counts.max_non_clifford_count} > "
            f"{demanded.max_non_clifford_count}"
        )
    if counts.max_circuit_instructions > demanded.max_circuit_instructions:
        violations.append(
            f"instruction cap exceeded: {counts.max_circuit_instructions} > "
            f"{demanded.max_circuit_instructions}"
        )
    if sentinel != SENTINEL:
        violations.append(f"bad sentinel: {sentinel} != {SENTINEL}")
    return violations


def _demanded_from_fixture(path: Path) -> DemandedBounds:
    """Read the `demanded_*` bounds from a v0.3-iadd fixture (KB-4)."""
    fixture = json.loads(path.read_text(encoding="utf-8"))
    return DemandedBounds(
        num_samples=int(fixture["demanded_num_samples"]),
        max_qubit_count=int(fixture["demanded_max_qubit_count"]),
        max_non_clifford_count=int(fixture["demanded_max_non_clifford_count"]),
        max_circuit_instructions=int(fixture["demanded_max_circuit_instructions"]),
    )


def main(argv: list[str] | None = None) -> int:
    """`apples-verify` — certify a circuit's resources against demanded bounds.

    Exit 0 (accepted), 1 (`PROVER.VERIFIER_REJECTED`) on any violation, 2 on
    usage error.
    """
    parser = argparse.ArgumentParser(prog="apples-verify", description=__doc__)
    parser.add_argument("--kmx", type=Path, required=True, help="the .kmx circuit to certify")
    parser.add_argument("--num-samples", type=int, required=True, help="samples the prover ran")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="read demanded_* bounds from a v0.3-iadd fixture (KB-4)",
    )
    parser.add_argument("--demand-samples", type=int, default=None)
    parser.add_argument("--demand-qubits", type=int, default=None)
    parser.add_argument("--demand-non-clifford", type=int, default=None)
    parser.add_argument("--demand-instructions", type=int, default=None)
    args = parser.parse_args(argv)

    if args.fixture is not None:
        demanded = _demanded_from_fixture(args.fixture)
    else:
        required = (
            args.demand_samples,
            args.demand_qubits,
            args.demand_non_clifford,
            args.demand_instructions,
        )
        if any(x is None for x in required):
            print(
                "apples-verify: pass --fixture or all of "
                "--demand-{samples,qubits,non-clifford,instructions}",
                file=sys.stderr,
            )
            return 2
        demanded = DemandedBounds(
            num_samples=args.demand_samples,
            max_qubit_count=args.demand_qubits,
            max_non_clifford_count=args.demand_non_clifford,
            max_circuit_instructions=args.demand_instructions,
        )

    counts = count_kmx(args.kmx.read_text(encoding="utf-8"), args.num_samples)
    violations = certify(counts, SENTINEL, demanded)
    if violations:
        err = ProverError(
            ProverSubcode.VERIFIER_REJECTED,
            "resource certification failed: " + "; ".join(violations),
        )
        print(str(err), file=sys.stderr)
        return PROVER_EXIT_CODE
    print(f"certified: outputs={public_outputs(counts)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
