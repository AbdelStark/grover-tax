---
upstream_repo: https://github.com/tanujkhattar/zkp_ecc
upstream_commit: 88e7cd5330bab9590df107b57bdce90672ff2b26
pinned_at: 2026-06-11
pinned_by: grover-tax-v0.3-khattar
fixture_target_version: v0.3-iadd
---

# Workload pin

These six fields are frozen for the **Khattar/Google addition-circuit
benchmark** (`fixtures/v0.3-iadd-*.json`). The workload is the upstream
integer-addition circuit `iadd64.kmx` (a 64-bit Cuccaro adder, `r0 += r1 mod
2⁶⁴`), run **repeatedly** (`K` copies) as the scaling knob — the explicit
benchmark Tanuj Khattar (Google Quantum AI) requested on 2026-05-27. See
`docs/spec/v0.3/KHATTAR-BENCHMARK-ALIGNMENT.md` for the full analysis and
`docs/spec/v0.3/COMMITMENT-POLICY.md` for the commitment scheme.

Every cell carries a citation back to the pinned upstream source or, where a
value is downscaled from upstream's production setting, a justification for the
divergence (see `## Methodology notes`). Once pinned, this file does not change
without a project minor or major version bump (RFC-0001).

The CI gate `scripts/check_workload.sh` exits `4`
(`FIXTURE.WORKLOAD_NOT_PINNED`) until every value in this table is populated
(no placeholder sentinel) and `upstream_commit` is a 40-character lowercase hex
SHA. The values below satisfy both conditions.

> The vendored upstream source lives at `third_party/sp1/docs/example_data/`;
> `upstream_commit` records its provenance SHA. **Verify independently** that
> this commit is the one providing `iadd64.kmx` upstream before publishing the
> benchmark (human-in-the-loop; KB-13/#125 coordination).

| Field | Source location (upstream) | Value | Notes |
|---|---|---|---|
| Canonical circuit `C` | `docs/example_data/iadd64.kmx` | `iadd64.kmx` (64-bit Cuccaro adder, `r0 += r1 mod 2⁶⁴`) | the explicit Khattar/Google ask; run `K` times for the scaling ladder (KB-7/#119) |
| Gate count of `C` per repetition | derived histogram of `iadd64.kmx` (transpiled to GTV1, KB-1/#113) | 627 | 502 `CX`→CNOT + 125 `CCX`→TOFFOLI; `n_g ≈ 627·K` for `K` repetitions |
| Non-Clifford (`CCX`/TOFFOLI) count per repetition | derived histogram of `iadd64.kmx` | 125 | the resource-certified non-Clifford bound (forward-looking, KB-10/#122) |
| Register width `W` | `iadd64.kmx` `APPEND_TO_REGISTER` layout | 64 | two 64-bit registers `r0`,`r1`; 128 qubits total; 2's-complement little-endian |
| Circuit-commitment scheme | `program/src/main.rs` (`Sha256` over `private_circuit_kmx_bytes`) | SHA-256 over the **raw `.kmx` bytes** | cross-comparable with upstream `sha256(iadd64.kmx)`; GTV1 hashes are internal integrity (see COMMITMENT-POLICY.md) |
| Test-case entropy source | `docs/getting_started.md` §"Using Fuzz Testing as a Proof Strategy" | Tier-1: **supplied** (deterministic XOF); Tier-2: SHAKE-256 Fiat–Shamir seeded by `H(C)` | Tier-1 divergence disclosed; closed by KB-9/#121 |

## Methodology notes

Upstream `tanujkhattar/zkp_ecc` is engineered for *production* proof generation
against multi-GPU SP1 clusters. The headline point-add proof spans ~17M
operations, 1175+ qubits, and 9024 Fiat–Shamir test cases — hours on a
single-core, no-GPU laptop, well outside the project's hard 45-minute
wall-clock ceiling.

`grover-tax`'s headline number is **the ratio of single-laptop wall times for
two prover stacks (SP1 vs Stwo) proving the *same fixed circuit*.** The circuit
is now the requested integer adder rather than a random gate net, and the
scaling knob is **repetition count `K`** rather than a synthetic gate budget:

* **Circuit = `iadd64.kmx`.** The exact circuit Tanuj asked for. It uses only
  `CX`/`CCX` (+ register metadata), so the classical reversible subset is
  reachable by the existing `{NOT, CNOT, TOFFOLI}` simulator (KB-1/#113);
  `iadd8_with_ancillae` and the qubit-efficient adders need the full kickmix
  simulator (Tier-2, KB-8/#120).
* **`n_g ≈ 627·K`.** A `K`-fold repeated adder applied to `(x, y)` computes
  `(x + K·y mod 2⁶⁴, y)` (KB-3/#115, KB-4/#116). `K` maps onto the RFC-0024
  scale tiers (KB-7/#119).
* **`W = 64`.** The two adder registers are 64 bits each (128 qubits total).
* **Commitment = SHA-256 over the raw `.kmx` bytes.** Byte-identical to what
  upstream commits, so the public statement lines up for a head-to-head.
* **Entropy: Tier-1 supplied, Tier-2 Fiat–Shamir.** Tier-1 cases are
  deterministically generated (XOF-seeded) and *supplied* in the fixture; the
  in-proof SHAKE-256 Fiat–Shamir derivation that prevents prover-chosen inputs
  is the Tier-2 obligation KB-9/#121.

The v0.2 **random-circuit** workload (`fixtures/v0.2.json`, 1024 gates) is
**retained** as a regression / T0-continuity artifact (KB-2/#114); its
generator parameters are frozen in `grover_tax.gen_fixtures` and no longer read
from this file. The Khattar fixtures are produced by `grover_tax.iadd_fixture`
(`uv run gen-iadd-fixtures`).
