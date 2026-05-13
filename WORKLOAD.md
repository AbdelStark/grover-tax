---
upstream_repo: https://github.com/tanujkhattar/zkp_ecc
upstream_commit: 88e7cd5330bab9590df107b57bdce90672ff2b26
pinned_at: 2026-05-13
pinned_by: grover-tax-v0.1-autonomous
fixture_target_version: v0.1
---

# Workload pin

These six fields are frozen for `fixtures/v0.1.json`. Every cell carries a
citation back to the pinned upstream source or, where the value diverges
from upstream's production setting, a justification for the divergence
(see `## Methodology notes` below). Once pinned, this file does not change
without a project minor or major version bump (RFC-0001).

The CI gate `scripts/check_workload.sh` exits `4`
(`FIXTURE.WORKLOAD_NOT_PINNED`) until every value in this table is
populated (no placeholder sentinel) and `upstream_commit` is a
40-character lowercase hex SHA. The values below satisfy both
conditions.

| Field | Source location (upstream) | Value | Notes |
|---|---|---|---|
| `N` (number of test cases) | `prover/prove.rs:67` (`#[arg(long, default_value = "64")]` on `num_tests`) | 4 | downscaled from upstream's 9024 production count for v0.1's single-laptop runtime budget; see methodology notes |
| Gate count of `C` for one secp256k1 point-add | derived; upstream `lib/src/sim.rs` is the dispatcher consuming `C` | 1024 | downscaled from upstream's ~17,000,000-op production circuit; representative shape (power-of-two, matches RFC-0004 §"Padding") |
| `W` (bit-stripe width) | `program/src/main.rs:121` (`const BATCH_SIZE: usize = 64`) and `lib/src/sim.rs` (64-shot parallel comment) | 64 | verbatim from upstream — the simulator processes 64 shots per batch |
| Modular-arithmetic gate count | derived subset of `C`; upstream `lib/src/sim.rs` `OperationType::CCX / CCZ` counts | 512 | downscaled from upstream's ~2,100,000-Toffoli production circuit; preserves the ~50% Toffoli fraction of the upstream low-toffoli variant |
| Circuit-commitment scheme (SP1 side) | `program/src/main.rs:21-25` (`Sha256::default()` over `private_circuit_kmx_bytes`) | SHA-256 over `circuit_byte_serialisation_hex` | verbatim from upstream |
| Entropy source for test-case generation (upstream behaviour) | `program/src/main.rs:83-85` (`Shake256::default()` seeded with circuit text) | SHAKE-256 seeded with `circuit_byte_serialisation_hex` | verbatim from upstream; `gen_fixtures.py` (#16) wraps this in the `XOF` primitive |

## Methodology notes

Upstream `tanujkhattar/zkp_ecc` is engineered for *production* proof
generation against multi-GPU SP1 clusters. The published `low_qubits` and
`low_toffoli` variants prove a 17M-operation, 1175+ qubit point-add
circuit with 9024 Fiat–Shamir test cases. On a single laptop with one CPU
core and no GPU, one such proof takes hours, well outside the project's
hard 45-minute wall-clock ceiling.

`grover-tax` v0.1's headline number is **the ratio of single-laptop wall
times for two prover stacks proving the *same fixed circuit shape*. The
shape mirrors upstream's gate-set (`{NOP, NOT, CNOT, TOFFOLI}`),
serialisation format, commitment hash, and entropy source verbatim;
only the *size* is downscaled so the comparison completes in budget.
The fixture format (`fixtures/v0.1.json`) carries the exact gate list,
seed, and commitments, so a reproducer can re-derive every number from
this one file.

Specifically:

* **`N = 4`.** Four test cases is enough for `analyze.py`'s ≥ 10-run
  statistical floor (each measured run is one *prover invocation*, not
  one test case) while keeping the per-invocation work bounded.
* **`gate_count = 1024`.** A power of two, friendly to Cairo's loop
  unrolling and Stwo's trace alignment (RFC-0004 §"Padding"). Two orders
  of magnitude smaller than upstream's 17M, but large enough to exercise
  the full gate-dispatcher / serialiser / Blake2s commitment path on
  both prover sides.
* **`modular_arithmetic = 512`.** ~50% of the gate count, mirroring the
  Toffoli fraction of upstream's low-toffoli variant
  (2.1M / 4.0M total ops ≈ 50%).
* **`W = 64`** and the two hash/entropy choices are taken verbatim. They
  are structural to the upstream design and do not scale with circuit
  size.

This methodology pin is the **v0.1 commitment**. A successor `v0.2`
that uses upstream's full-size production circuit is a project minor
bump (RFC-0001 §"Re-pinning") and ships under `fixtures/v0.2.json`
alongside this one.
