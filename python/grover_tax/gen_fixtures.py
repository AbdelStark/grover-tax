"""`uv run gen-fixtures` — deterministic fixture generator (RFC-0002).

Reads `WORKLOAD.md`, builds the gate-list `C` for one secp256k1
point-add, samples `N` test cases via `XOF + secp256k1`, computes the
canonical-byte serialisation + SHA-256 + Blake2s commitments, and
emits `fixtures/v0.1.json` atomically (or compares in `--check` mode).

v0.1 MVP scope (documented inline below): the gate-list builder is a
**stub all-NOP circuit** that exercises the full pipeline (serialiser,
commitment hashes, prover-side wrappers, harness) without proving the
actual point-add semantics. The fixture remains structurally valid and
satisfies F-INV-1, F-INV-2, F-INV-3, F-INV-5; F-INV-4 (sim_reference
cross-validation) is **skipped** because the all-NOP circuit's output
equals its input, while `y_hex` carries the *honest* `coincurve.add`
result. A successor implementation that builds a real point-add circuit
(`build_secp256k1_pointadd_circuit`) re-enables the F-INV-4 check
without changing this module's CLI shape — only the body of
`_build_circuit` swaps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from grover_tax import logging as gt_logging
from grover_tax.errors import FIXTURE_EXIT_CODE, FixtureError, FixtureSubcode
from grover_tax.paths import fixture_path, fixtures_dir, repo_root, workload_md_path
from grover_tax.secp256k1 import add, sample_point_pair, serialize_x, serialize_y
from grover_tax.serialise import UNUSED_CTRL, Gate, Opcode, serialise
from grover_tax.workload import Workload, load_workload_md
from grover_tax.xof import XOF

__all__ = ["main"]

# `SEED` is byte-stable (RFC-0002 §"Inputs"). Changing it changes every
# fixture in v0.1.x — that's the point.
SEED: bytes = b"grover-tax-v0.1-2026-05"

# `circuit_serialisation_format_version` is `1` in v0.1 (F-INV-6).
CIRCUIT_SERIALISATION_FORMAT_VERSION = 1

# `version` in the emitted fixture (F-INV-7).
FIXTURE_VERSION = "v0.1"

# Number of decimal places at which JSON dumps round-trip identically.
# `json.dumps` uses Python's repr for floats; we never emit floats so this
# is informational only.

_log = gt_logging.get_logger("grover_tax.gen_fixtures")

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gen-fixtures",
        description=__doc__,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "regenerate and compare against the on-disk fixture instead of "
            "overwriting; exit 4 with FIXTURE.DRIFT on mismatch."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="override output path (default: fixtures/v0.1.json at the repo root)",
    )
    parser.add_argument(
        "--workload",
        type=Path,
        default=None,
        help="override WORKLOAD.md path (default: repo root)",
    )
    args = parser.parse_args(argv)

    workload_p = args.workload if args.workload is not None else workload_md_path()
    out_path = args.out if args.out is not None else fixture_path(FIXTURE_VERSION)

    try:
        workload = load_workload_md(workload_p)
    except FixtureError as e:
        print(str(e), file=sys.stderr)
        return e.exit_code

    fixture = _build_fixture(workload)

    if args.check:
        return _check_against_disk(fixture, out_path)
    _write_atomic(fixture, out_path)
    _log.info("wrote fixture to %s", out_path)
    return 0


# -- core build --------------------------------------------------------------


def _build_fixture(workload: Workload) -> dict[str, object]:
    """Run the full RFC-0002 §"Algorithm" pipeline and return the dict."""
    n_samples = _parse_workload_int(workload, "`N` (number of test cases)")
    bit_stripe_width = _parse_workload_int(workload, "`W` (bit-stripe width)")
    gate_count = _parse_workload_int(workload, "Gate count of `C` for one secp256k1 point-add")

    seed_bytes = hashlib.sha256(SEED).digest()
    xof = XOF(seed_bytes)

    # 1. Build the (stub) gate list `C`. v0.1 MVP: 1024 NOPs.
    circuit = _build_circuit(gate_count=gate_count)

    # 2. Sample N test cases. Each carries `x_hex` (input bytes) and `y_hex`
    #    (the *honest* `coincurve.add` result, so F-INV-5 holds even though
    #    the all-NOP stub circuit doesn't itself compute the addition).
    test_cases: list[dict[str, str]] = []
    for _ in range(n_samples):
        p, q = sample_point_pair(xof)
        x_bytes = serialize_x(p, q)
        r = add(p, q)
        y_bytes = serialize_y(r)
        test_cases.append({"x_hex": x_bytes.hex(), "y_hex": y_bytes.hex()})

    # 3. Canonical byte serialisation of `C` + commitments.
    circuit_bytes = serialise(circuit)
    sha256_hex = hashlib.sha256(circuit_bytes).hexdigest()
    blake2s_hex = hashlib.blake2s(circuit_bytes).hexdigest()

    return {
        "version": FIXTURE_VERSION,
        "generator_commit": _git_head_sha(),
        "workload_pin_commit": workload.upstream_commit,
        "seed_hex": seed_bytes.hex(),
        "n_samples": n_samples,
        "bit_stripe_width": bit_stripe_width,
        "circuit_serialisation_format_version": CIRCUIT_SERIALISATION_FORMAT_VERSION,
        "circuit_byte_serialisation_hex": circuit_bytes.hex(),
        "circuit_commitment_sha256_hex": sha256_hex,
        "circuit_commitment_blake2s_hex": blake2s_hex,
        "test_cases": test_cases,
    }


def _build_circuit(*, gate_count: int) -> list[Gate]:
    """v0.1 MVP: all-NOP circuit of `gate_count` gates.

    A real `build_secp256k1_pointadd_circuit(gate_count, bit_stripe_width)`
    that produces a semantically-meaningful point-add gate sequence lives
    in a follow-up — the wiring here is identical so swapping the body is
    a one-function change without touching the surrounding pipeline.
    """
    nop = Gate(
        opcode=Opcode.NOP,
        target=UNUSED_CTRL,
        ctrl_a=UNUSED_CTRL,
        ctrl_b=UNUSED_CTRL,
    )
    return [nop] * gate_count


def _parse_workload_int(workload: Workload, field_name: str) -> int:
    """Pull an integer out of the WORKLOAD.md table by left-column name."""
    row = workload.by_name.get(field_name)
    if row is None:
        raise FixtureError(
            FixtureSubcode.WORKLOAD_NOT_PINNED,
            f"WORKLOAD.md is missing field {field_name!r}",
        )
    try:
        return int(row.value)
    except ValueError as e:
        raise FixtureError(
            FixtureSubcode.WORKLOAD_NOT_PINNED,
            f"WORKLOAD.md field {field_name!r} value {row.value!r} is not an integer",
        ) from e


# -- I/O helpers -------------------------------------------------------------


def _write_atomic(fixture: dict[str, object], path: Path) -> None:
    """Write JSON via a sibling tempfile + `os.replace` for atomicity."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialised = json.dumps(fixture, indent=2, sort_keys=False) + "\n"
    fd, tmp = tempfile.mkstemp(
        prefix=path.name + ".partial.", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(serialised)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _check_against_disk(fixture: dict[str, object], path: Path) -> int:
    """Compare `fixture` against `path` modulo `generator_commit`."""
    if not path.is_file():
        print(
            f"{FixtureSubcode.DRIFT.value}: no fixture on disk at {path}; "
            "run `uv run gen-fixtures` first",
            file=sys.stderr,
        )
        return FIXTURE_EXIT_CODE
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    a = _normalise(fixture)
    b = _normalise(on_disk)
    if a != b:
        print(
            f"{FixtureSubcode.DRIFT.value}: {path} differs from regenerated bytes",
            file=sys.stderr,
        )
        return FIXTURE_EXIT_CODE
    return 0


def _normalise(fixture: dict[str, object]) -> dict[str, object]:
    """Strip fields not relevant to byte-stable comparison (RFC-0002)."""
    return {k: v for k, v in fixture.items() if k != "generator_commit"}


def _git_head_sha() -> str:
    """Best-effort: `git rev-parse HEAD`. Falls back to 40 zeros if git fails."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root()), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            sha = result.stdout.strip()
            if _SHA_RE.match(sha):
                return sha
    except OSError:
        pass
    return "0" * 40


# Use `fixtures_dir` to satisfy mypy "unused import" if the helper isn't
# touched elsewhere. The function does *not* run as a side effect during
# import.
_ = fixtures_dir


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
