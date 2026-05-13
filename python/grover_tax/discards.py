"""Append-only writer for `results/discards.log`.

Per `docs/spec/03-data-model.md` §"Discards log" the file is JSON-lines:
one record per line, terminated by `\\n`. Invariants:

* D-INV-1: every discarded measurement artifact has a matching record.
* D-INV-2: `reason` is one of the documented enum values; free-form text
  goes in `detail`.
* D-INV-3: the first run of any series is always discarded with
  `reason: cold_cache`.

This module enforces D-INV-2 at the call site and never rewrites or
deletes records — only appends. Concurrent writers from multiple
threads or processes are serialised via `fcntl.flock(LOCK_EX)`, which
is portable across macOS and Linux (the only two host platforms in
scope per RFC-0009).

The matching shell helper `scripts/discard.sh` builds an equivalent
record with `jq` and appends through the same lock — see that file's
header for the contract.
"""

from __future__ import annotations

import fcntl
import json
import os
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Final

from grover_tax.paths import discards_log_path, results_dir

__all__ = [
    "DiscardReason",
    "append_discard",
]


class DiscardReason(str, Enum):
    """Enumerated `reason` values per `docs/spec/03-data-model.md`.

    `other` is the catch-all; free-form text always lives in `detail`.
    """

    THERMAL = "thermal"
    GPU_RESIDENCY = "gpu_residency"
    SWAP_ACTIVE = "swap_active"
    COLD_CACHE = "cold_cache"
    ENV_VAR_MISS = "env_var_miss"
    OTHER = "other"


_VALID_REASONS: Final[frozenset[str]] = frozenset(r.value for r in DiscardReason)


def append_discard(  # noqa: PLR0913 — every arg lands directly in the record
    *,
    run_id: str,
    prover: str,
    reason: str | DiscardReason,
    detail: str,
    measurement_artifact: str,
    log_path: Path | None = None,
) -> None:
    """Append one record to `results/discards.log`.

    Args:
        run_id: Identifier of the discarded run.
        prover: ``"sp1"`` or ``"stwo"``.
        reason: One of the `DiscardReason` enum values, or its literal
            string. Anything else raises `ValueError`.
        detail: Free-form human-readable explanation.
        measurement_artifact: Path (repo-relative) of the timing.json
            file that was emitted-then-discarded.
        log_path: Override the destination (tests pass a tmp_path).
            Defaults to `results/discards.log` under the repo root.

    Raises:
        ValueError: If `reason` is not one of the documented enum values
            or if `prover` is not ``"sp1"`` / ``"stwo"``.

    Concurrent safety: the function takes an exclusive `flock` over the
    file descriptor for the duration of the write and `flush()` + `fsync()`
    before releasing it. Multiple writers across threads or processes
    interleave at line boundaries — never inside a record.
    """
    reason_str = reason.value if isinstance(reason, DiscardReason) else str(reason)
    if reason_str not in _VALID_REASONS:
        raise ValueError(
            f"append_discard: reason {reason_str!r} not in {sorted(_VALID_REASONS)}"
        )
    if prover not in ("sp1", "stwo"):
        raise ValueError(f"append_discard: prover must be 'sp1' or 'stwo', got {prover!r}")

    record = {
        "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_id": run_id,
        "prover": prover,
        "reason": reason_str,
        "detail": detail,
        "measurement_artifact": measurement_artifact,
    }
    serialised = json.dumps(record, separators=(",", ":"), ensure_ascii=False)

    if log_path is None:
        log_path = discards_log_path()
        results_dir().mkdir(parents=True, exist_ok=True)
    else:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    # Open in binary append mode so seeks land at end-of-file even with
    # multiple writers, then hold an exclusive lock across the single
    # `write()`. Linux and macOS both honour BSD `flock(2)` on regular
    # files.
    with open(log_path, "ab") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(serialised.encode("utf-8") + b"\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
