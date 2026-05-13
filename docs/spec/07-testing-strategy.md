# Testing strategy

This project's correctness criterion is: *the two provers produce verifier-accepted proofs of the same statement against the same fixture, and the measurement harness reports the resulting numbers honestly*. The testing strategy is structured to defend that criterion at every layer.

## Test pyramid

```
                  +-------------------+
                  |   Methodology     |   day-1 vs day-2 stability gate
                  |   self-consistency|   apples-to-apples disclosures audit
                  +-------------------+
              +---------------------------+
              |   End-to-end / harness    |   run_all.sh on reference rig
              |                           |   30-min ceiling, RESULTS.md present
              +---------------------------+
         +-------------------------------------+
         |   Integration                       |   prover wrapper symmetry
         |                                     |   schema-validate every artifact
         |                                     |   verify_<prover>.sh on fresh proofs
         +-------------------------------------+
    +-------------------------------------------------+
    |   Component                                     |   sim_reference vs coincurve
    |                                                 |   gen_fixtures determinism
    |                                                 |   canonical serialiser round-trip
    +-------------------------------------------------+
+---------------------------------------------------------+
|   Property / unit                                       |   gate-list invariants
|                                                         |   M31 limb arithmetic
|                                                         |   fixture-schema validators
+---------------------------------------------------------+
```

The pyramid is wider at the bottom because the higher tiers are slow and rare; the lower tiers are fast and run on every commit.

## Layer 1: property & unit tests

### Python (`tests/python/`)

- **P-1.1: Canonical serialiser round-trip.** For every `Gate` opcode, serialise → deserialise → assert identity. Hypothesis-based property test: generate random `(opcode, target, ctrl_a, ctrl_b)` tuples, round-trip them.
- **P-1.2: SHA-256 / Blake2s digest stability.** Fixed inputs → fixed outputs. Regression vector lives in `tests/python/fixtures/digest_vectors.json`.
- **P-1.3: M31 limb-vector arithmetic.** Property: `from_int(a) + from_int(b) == from_int((a+b) % p_secp256k1)` for random 256-bit `a, b`. Tests the Python-side 9×31-bit limb routines used by `gen_fixtures.py` to construct test cases for `sim_reference`.
- **P-1.4: Gate semantics.** For each opcode in `{NOT, CNOT, TOFFOLI}`, table-driven tests over all 2/4/8-bit input combinations.
- **P-1.5: Fixture schema validator.** Negative tests: 20 hand-crafted malformed fixtures; each must raise the appropriate `FIXTURE.*` error.

### Cairo (`stwo-side/tests/`)

- **P-2.1: Gate semantics (Cairo).** Same table-driven tests as P-1.4, asserted inside the Cairo program with `assert_eq`. Runs as a Cairo unit test, not under the prover.
- **P-2.2: M31 limb operations on `[u31; 9]`.** Add, sub, conditional-select. Range checks asserted.
- **P-2.3: Blake2s round-trip on a 64-byte fixed input.** Regression vector.

### Rust (`stwo-side/`)

- **P-3.1: Fixture deserialiser.** Round-trip a known good fixture; reject 10 malformed fixtures.
- **P-3.2: Wrapper exit codes.** Drive `bin/run_stwo.sh` with synthetic preconditions; assert correct exit code per `04-error-model.md`. Same for `bin/run_sp1.sh`.

## Layer 2: component tests

- **C-1: `sim_reference` vs `coincurve`.** For 100 random test cases (drawn from the same SHA-2 XOF as `gen_fixtures`), assert `sim_reference(C, x_i) == coincurve.add(P_i, Q_i)`. Lives in `tests/python/test_sim_vs_coincurve.py`.
- **C-2: `gen_fixtures` determinism.** Run `gen-fixtures` twice from a clean tree with the same `SEED` and `WORKLOAD.md`; assert byte-identical `fixtures/v0.1.json` (modulo `generator_commit`, which is excluded from byte comparison).
- **C-3: `gen-fixtures --check` semantics.** Tamper with one byte of `fixtures/v0.1.json`; assert `gen-fixtures --check` exits non-zero.
- **C-4: Canonical serialiser cross-impl.** Same gate list serialised by Python and by Rust (and ideally Cairo) yields the same bytes. CI rebuilds and compares.
- **C-5: Schema validator on every artifact.** `python -m grover_tax.validate_schemas results/` is run as a step of `run_all.sh` and as a CI step on a corpus of recorded sample results.

## Layer 3: integration tests

- **I-1: Wrapper symmetry.** A CI test invokes a stub prover via both `bin/run_sp1.sh` and `bin/run_stwo.sh` and asserts identical argv structure and stdout discipline. See `RFC-0007`.
- **I-2: `verify_<prover>.sh` on fresh proofs.** In CI on a smaller fixture (`fixtures/test_v0.1.json` — a `n_samples=2` variant used only for CI), invoke run → verify; assert exit 0.
- **I-3: `verify_<prover>.sh` on tampered proofs.** Flip one byte of a fresh proof, re-run verify; assert exit non-zero.
- **I-4: Cross-prover fixture sharing.** Run SP1 prover then Stwo prover on the same fixture in CI; both succeed.
- **I-5: Schema-versioned artifact round-trip.** Generate `results/*.json` in CI; pass through `analyze.py`; assert it produces a valid `RESULTS.md` (renderable, expected sections present, no template placeholders).

CI runs use the smaller `fixtures/test_v0.1.json` so total CI wall-clock stays under 15 minutes. Headline numbers are not generated in CI; that is a manual operation on the reference rig.

## Layer 4: end-to-end harness tests

- **E-1: `run_all.sh` on reference rig.** Full clean clone, full run, presence of `RESULTS.md` with non-`TBD` numbers, total wall-clock under 30 minutes. This is the headline reproduction.
- **E-2: `run_all.sh` failure surfaces.** Inject each `MEASUREMENT.*` violation in a fixture rig (e.g., spin up a CPU-bound competing process and assert thermal discard fires); assert correct discard + non-zero exit per `04-error-model.md`.
- **E-3: `run_all.sh` resume semantics.** None — `run_all.sh` is not resumable; partial state must be cleaned with `scripts/clean.sh`. This is tested by running `run_all.sh`, killing it mid-run, running `scripts/clean.sh`, re-running `run_all.sh`; assert clean completion.

## Layer 5: methodology self-consistency

- **M-1: Day-1 vs day-2 stability gate.** `analyze.py` computes the M1 median delta; CI surfaces it (in informational mode) so reviewers can scan for instability across PRs. Not enforced as pass/fail because day-2 requires real time and is operator-driven.
- **M-2: Apples-to-apples disclosures audit.** A textual lint checks that `RESULTS.md` contains the four named disclosures (hash divergence, field choice, trusted setup, thread fan-out) in `§Apples-to-apples`. Missing any one fails CI.
- **M-3: Discards inspector.** `analyze.py` summarises discard reasons in `RESULTS.md`. If discard rate exceeds 30% on either prover, `analyze.py` marks the headline `[HIGH DISCARD]` and includes a discard-by-reason histogram.

## ML-adjacent test discipline

This benchmark is not ML, but it shares ML's hardest test problem: *statistical claims about non-deterministic numbers*. We adopt three ML-style practices:

1. **Pin seeds; record provenance.** `SEED`, `versions.lock`, `WORKLOAD.md`, `generator_commit` all flow into the fixture as recorded metadata.
2. **Bound the noise.** The discard rules in `RFC-0010` are precisely the "outlier handling" of an ML eval. They are *prescriptive*, not retroactive — a discard rule may not be added or relaxed after seeing results.
3. **Two independent series.** Day-1 vs day-2 is the cheapest, hardest-to-game stability check. A single series can be lucky; two cannot.

## Test infrastructure

- Python tests: `pytest`, with `pytest-xdist` permitted *only outside the timed window* (test runs are not measured runs). `hypothesis` for property tests.
- Rust tests: `cargo test`, single-threaded for the wrapper tests (`-- --test-threads=1`).
- Cairo tests: in-program `assert` and the cairo-lang test harness as available at the pinned version.
- CI: GitHub Actions. The CI rig matches the spec in `04.2` and runs the full Layers 1–3 plus a CI-fixture-sized Layer 4. Headline numbers are not produced in CI.

## What this strategy does not promise

- It does not promise that SP1 and Stwo are correct provers. That is upstream.
- It does not promise byte-stability of the proof files. Provers may include randomness in their proofs as long as their verifiers accept. We measure size, not bytes.
- It does not promise that the reference rig will always produce identical timings to second-decimal precision across reproductions. It promises medians and IQRs within the day-1/day-2 stability envelope.

## What this strategy does promise

- Every claim in `RESULTS.md` is reproducible from `git clone` → `./scripts/run_all.sh` within the published wall-clock and discard budgets.
- Every artifact on disk validates against its schema.
- Every divergence from apples-to-apples is named and justified.
- Every discard is recorded with reason.
