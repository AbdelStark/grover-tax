# grover-tax v0.3 — Acceptance Criteria

Each phase has a gate. A gate is a tuple `(test obligations, content
obligations, manual review)`. All three must be green before the phase
tag (`v0.3.0-rc.X`) lands.

## Phase 0 gate — Audit chain (`v0.3.0-rc.0`)

### Test obligations (CI-enforced)

A pull request that bundles the audit-chain implementation must show:

| Test ID | Source RFC | What it asserts |
|---|---|---|
| `T21-1` | RFC-0021 §1 | `git ls-files third_party/proving-utils/Cargo.lock` lists the file |
| `T21-3.a` | RFC-0021 §3 | `lock_versions.sh` regenerates a `versions.lock` that schema-validates and includes all 9 new fields |
| `T21-3.b` | RFC-0021 §3 | Corrupting each new field individually fires `MEASUREMENT.VERSIONS_DRIFT` at preflight |
| `T21-3.c` | RFC-0021 §3 | The preflight exit code is `5` for every corruption |
| `T21-4` | RFC-0021 §4 | `FIXTURE_PATH=missing.json ./scripts/measure.sh stwo r1` exits `5` with `MEASUREMENT.FIXTURE_VERSION_DRIFT` |
| `T21-5` | RFC-0021 §5 | The `*.proverlog.txt` from a real prove contains `CONSTRAINTS: N` with `N ≥ 1000` |
| `T21-6` | RFC-0021 §6 | Mann-Kendall trend detector flags a monotonically-increasing synthetic series |
| `T21-11` | RFC-0021 §11 | Bootstrap-CI day-2 stability gate fires on a synthetic 8% delta and does NOT fire on a 1% delta |
| `C16-T8` | RFC-0016 §5 | Per-opcode Cairo trace-row count is identical across NOP / NOT / CNOT / TOFFOLI on the canary fixture (within ±0 rows; not ±1 — this is a hard equality) |
| `S17-T8` | RFC-0017 §3.1 | Per-arm SP1 RISC-V cycle count is identical across the four opcodes on the canary fixture (hard equality) |
| `S19-T1` | RFC-0019 §2.4 | `preflight.sh` reads `versions.lock::{sp1.fri_params, stwo.circle_fri_params}` and aborts with `MEASUREMENT.SOUNDNESS_FLOOR_BREACH` on a synthetic < 100-bit param set |
| `S19-T2` | RFC-0019 §5.2 | 100 random inputs: Python `hashlib.blake2s` output matches Cairo `commit_blake2s` byte-for-byte |
| `S19-T3` | RFC-0019 §5.1 | 100 random inputs: Python `hashlib.sha256` output matches SP1 zkVM SHA-256 syscall byte-for-byte |
| `S19-T4` | RFC-0019 §6.2 | Tampered `circuit_byte_serialisation_hex` byte: both verifiers reject |
| `T20-3.2.a` | RFC-0020 §3.2 | SP1 prover stdin substitution detected: `apples-verify` exits 1 with `PROVER.PUBLIC_INPUT_MISMATCH` |
| `T20-3.2.b` | RFC-0020 §3.2 | Stwo bootloader `user_args_list` substitution detected: same |
| `T20-3.3.a` | RFC-0020 §3.3 | "Null prover" PR (replaces `simulate` with identity) caught by `apples-verify` on any non-trivial test case |
| `T20-3.3.c` | RFC-0020 §3.3 | Methodology lint asserts `rows_measured ≥ 0.95 · rows_predicted` |
| `T22-1` | RFC-0022 §8 | `bin/apples-prove` + fixture → verifying proof |
| `T22-2` | RFC-0022 §8 | `bin/apples-verify` accepts the produced proof |
| `T22-3` | RFC-0022 §8 | Tampered `circuit_commitment_blake2s_hex` in fixture → `apples-verify` rejects |
| `T22-4` | RFC-0022 §8 | Tampered `y_i` byte → `apples-verify` rejects |
| `T22-5` | RFC-0022 §8 | Substituted proof from a different fixture → `apples-verify` rejects |
| `S26-T1` | RFC-0026 §4 | SP1 conjectured soundness ≥ 100 bits at the pinned FRI params (compute and assert) |
| `S26-T2` | RFC-0026 §4 | Stwo conjectured soundness ≥ 100 bits at the pinned Circle-FRI params; soundness floors differ by ≤ 1 bit between the two stacks |

### Content obligations

- `docs/spec/v0.3/SPEC-v0.3.md` is the authoritative spec, RFCs 0023–0027
  ship.
- `versions.lock` is regenerated; CI's drift gate passes.
- `CHANGELOG.md` records the audit-chain implementation.

### Manual review

- A second maintainer reviewed every commit touching `third_party/sp1/`,
  `stwo-side/cairo/src/`, or `bin/apples-verify`.

### Gate

PR labeled `phase-0` cannot merge until all the above are green AND a
CODEOWNERS review (per RFC-0021 §18) is recorded.

`v0.3.0-rc.0` is tagged on merge.

---

## Phase 1 gate — T0/T1 workload + scaling curve start (`v0.3.0-rc.1`)

### Measurement obligations

- `headline-runs/v0.3-rc1/T0/RESULTS.md` exists with `ρ_T0` reported
  and CoV ≤ 0.5%.
- `headline-runs/v0.3-rc1/T1/RESULTS.md` exists with `ρ_T1` reported
  and CoV ≤ 1%.
- T0's ρ is within 5% of v0.2's 2.52× (cross-check against the 2026-05-20
  headline; if outside, investigate before proceeding).
- Scaling-curve preliminary fit (T0+T1, 2 points) emitted with 95% CI.

### Test obligations

All Phase 0 tests remain green. Additionally:

| Test ID | Source RFC | What it asserts |
|---|---|---|
| `S23-T1` | RFC-0023 §6 | The upstream point-add gate-net builder is pinned; running it at the pinned commit emits a fixture byte-equal to `fixtures/v0.3-pointadd-T0.json` |
| `S23-T2` | RFC-0023 §6 | F-INV-4 (Python sim-reference vs run) passes on T0 and T1 fixtures |
| `S24-T1` | RFC-0024 §3.2 | The scaling-curve fitter's linear model agrees with measured T0/T1 within ±5% |

### Content obligations

- `RESULTS.md` contains the **per-tier headline table** + **operations-
  counted footprint** + **commitment-cost asymmetry** subsection per
  RFC-0024 §9.
- The "Known limitations" section enumerates which Tier-C items remain
  open at rc.1.

---

## Phase 2 gate — T2 (+ best-effort T3) (`v0.3.0-rc.2`)

### Measurement obligations

- T2: `n_runs ≥ 3` clean prove samples, CoV ≤ 5%, ρ_T2 reported.
- T3: at least one successful prove on each stack (sample size relaxed
  to 1 if a clean series isn't budget-feasible); OR a formal
  documentation of the memory bound (e.g., "SP1 OOMs at `n_g ≥ 524288`
  on c3-highmem-22 with 176 GiB").
- The scaling-curve fitter is refit with T0+T1+T2(+T3); 95% CI on the
  extrapolation to T4 is reported.
- Empirical-vs-model deviation at T2 is < 20% (the model's linear
  approximation is faithful in the regime we measured).

### Test obligations

| Test ID | Source RFC | What it asserts |
|---|---|---|
| `S24-T2` | RFC-0024 §3.2 | Scaling-curve fit on T0+T1+T2 predicts T2 within ±10% (out-of-sample by leaving T2 out and refitting on T0+T1, then predicting T2) |
| `S24-T3` | RFC-0024 §11 | If Spot was used for any T3 run, the preemption-rate metric is recorded in `RESULTS.md` and is < 5% |

---

## Phase 3 gate — Day-2 + second-party reproduction (`v0.3.0-rc.3`)

### Measurement obligations

- Day-2 series captured at all completed scales; day-1/day-2 medians
  within bootstrap-CI 95% bound of ±5%.
- `RESULTS-replicator-<id>.md` (Tier-C C1) submitted by an independent
  operator; their ρ values within ±5% of the v0.3 reference numbers at
  the scales they measured.

### Test obligations

| Test ID | Source RFC | What it asserts |
|---|---|---|
| `S27-T1` | RFC-0027 §2 | Replicator's `versions.lock` is in the same equivalence class as the v0.3 reference (RFC-0024 §4.3) |
| `S27-T2` | RFC-0027 §2 | Replicator's `RESULTS-replicator-<id>.md` schema-validates and contains the same disclosure phrases |

### Content obligations

- "Tier-3 reproducibility validated" subsection added to `RESULTS.md`.

---

## Phase 4 gate — Release (`v0.3.0`)

### Content obligations

- `RESULTS.md` is the final accepted version (post Google-team
  feedback).
- `RESULTS-macos.md` companion is published.
- Methodology paper draft (4-6 pages) is in `docs/papers/v0.3-methodology.md`
  or `docs/papers/v0.3-methodology.pdf`.
- `CHANGELOG.md` records v0.3.0 with the headline ratio + the audit-chain
  status.
- All Tier-A items are green; any missing Tier-C is enumerated in
  "Known limitations" (RFC-0024 §9).

### Test obligations

All previous-phase tests remain green AND:

| Test ID | Source RFC | What it asserts |
|---|---|---|
| `S25-T*` | RFC-0025 | Direct Stwo Cairo path tests (no bootloader) — if Tier-B B6 is shipped |
| `S28-T1` | (deprecated) | (placeholder; this slot is reserved for any v0.3-late additions) |

### Manual review

- One CODEOWNERS approval per RFC-0021 §18.
- Methodology paper has been shared with the Khattar/Google team and at
  least one named reviewer's feedback is incorporated (or formally
  declined with rationale).

### Release artefact

`v0.3.0` git tag points at the commit where:
- `RESULTS.md`'s headline is final.
- `versions.lock` reflects the toolchain that produced the published
  numbers.
- All artefacts under `headline-runs/v0.3.0/` are reproducible from a
  clean clone on the reference rig.

## Exit-code matrix for `make headline`

`make headline` is the developer entry point that runs the full audit
chain + measurement pipeline at a configurable scale tier:

```
make headline TIER=T0    # quick smoke (~25 min on c3-highmem-22)
make headline TIER=T1    # mid (~3 hours)
make headline TIER=T2    # long (~24 hours; usually overnight)
make headline TIER=T3    # very long (~5 days; capacity-bound)
make headline TIER=T4    # full upstream scale (capacity / OOM risk)
make headline TIER=all   # T0 → T4 in sequence (~7 days)
```

| Exit code | Meaning |
|---|---|
| 0 | All tests green at the chosen tier; `RESULTS.md` regenerated |
| 1 | `PROVER.*` (witness rejected, public-input mismatch, etc.) |
| 2 | usage / argv shape |
| 3 | `BUILD.*` (toolchain drift, SP1 patch fail, etc.) |
| 4 | `FIXTURE.*` (drift, schema invalid, F-INV-4 fail) |
| 5 | `MEASUREMENT.*` (preflight, soundness-floor breach, ops-footprint deviation) |
| 6 | `REPORT.*` (methodology lint fail) |

A non-zero exit from `make headline` at any phase IS the acceptance-gate
fail.
