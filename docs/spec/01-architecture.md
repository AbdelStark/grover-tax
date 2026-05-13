# Architecture

## System shape

`grover-tax` is two prover pipelines fed by one fixture and measured by one harness, then summarised by one report. There are no servers, no daemons, no networked components. Everything runs on a single laptop from a single clone.

```
                           +----------------------+
                           |  fixtures/v0.1.json  |
                           |   (canonical input)  |
                           +----------+-----------+
                                      |
                +---------------------+---------------------+
                |                                           |
                v                                           v
   +-------------------------+                  +-------------------------+
   |  bin/run_sp1.sh         |                  |  bin/run_stwo.sh        |
   |    SP1 prover + Groth16 |                  |    Stwo prover (Cairo)  |
   |    wrap                 |                  |                         |
   +-----------+-------------+                  +-------------+-----------+
               |                                              |
               |  emits proof file + stdout log               |
               |                                              |
               v                                              v
   +-------------------------+                  +-------------------------+
   |  bin/verify_sp1.sh      |                  |  bin/verify_stwo.sh     |
   +-----------+-------------+                  +-------------+-----------+
               |                                              |
               +--------------------+-------------------------+
                                    |
                                    v
                       +--------------------------+
                       |  scripts/measure.sh      |
                       |    hyperfine + gnu-time  |
                       +-------------+------------+
                                     |
                                     v
                       +--------------------------+
                       |  results/*.json + logs   |
                       +-------------+------------+
                                     |
                                     v
                       +--------------------------+
                       |  uv run analyze          |
                       |  uv run plot             |
                       +-------------+------------+
                                     |
                                     v
                       +--------------------------+
                       |  RESULTS.md + plots/     |
                       +--------------------------+
```

Diagrams supplement prose. The same shape is described in §"Module boundaries" below; if the two ever disagree, the prose wins.

## Module boundaries

### Fixture pipeline (`python/grover_tax/`)

- `gen_fixtures.py`: deterministic generator. Reads the workload parameters pinned in `WORKLOAD.md`, computes test cases `T`, materialises the gate-list `C`, cross-validates `C` against the Python reference simulator, and emits `fixtures/v0.1.json`. Entry: `uv run gen-fixtures`. See `RFC-0002`.
- `sim_reference.py`: Python reimplementation of `tanujkhattar/zkp_ecc/lib/src/sim.rs` gate semantics. Pure function from `(C, x_i)` to register state. Used as cross-validation oracle. See `RFC-0003`.
- `analyze.py`: ingests `results/*.json` from `hyperfine` and `gnu-time` outputs, computes median / IQR / min / max / stddev, applies the discard rules of `RFC-0010`, and emits `RESULTS.md`. Entry: `uv run analyze`.
- `plot.py`: emits histograms and bar charts under `results/plots/`. Entry: `uv run plot`. See `RFC-0011`.

### SP1 prover side (`sp1-side/` and `sp1-side-patches/`)

- `sp1-side/`: git submodule pinned to `tanujkhattar/zkp_ecc` at a recorded commit.
- `sp1-side-patches/0001-read-fixtures-from-json.patch`: single patch, target diff under 50 lines, applied at build time. Replaces the example's internal SHA-2 XOF derivation of test cases with a deserialise-from-JSON path. Emits the proof to a CLI-supplied path. See `RFC-0006`.
- The SP1 verifier is unmodified and invoked through SP1's standard Groth16 verify entry point.

### Stwo prover side (`stwo-side/`)

- `stwo-side/circuit.cairo`: the Cairo program. Reads `fixtures/v0.1.json` (public: `T`, `H_C_blake2s`; secret witness: `C`), executes the gate-by-gate simulator on each test case, asserts equality with `y_i`, and asserts `blake2s(C_serialised) == H_C_blake2s`. See `RFC-0004`.
- `stwo-side/prover_main.rs`: thin Rust wrapper that invokes Stwo's prover on `circuit.cairo` and emits the proof.
- `stwo-side/verifier_main.rs`: thin Rust wrapper that invokes Stwo's verifier.
- Stwo itself is consumed as a pinned-SHA dependency (or git submodule), not vendored.

### Measurement harness (`scripts/` and `bin/`)

- `bin/run_<prover>.sh` and `bin/verify_<prover>.sh`: symmetric two-argument wrappers (`<fixtures.json> <output_proof_path>` for run; `<proof_path>` for verify). Exit 0 on success, non-zero on failure. See `RFC-0007`.
- `scripts/preflight.sh`: asserts environmental hygiene preconditions (AC power, low-power mode off, frequency governor, no swap, no GPU residency, env vars set). See `RFC-0010`.
- `scripts/measure.sh`: invokes one prover under `hyperfine` for the wall-clock distribution and under `gnu-time -v` for peak RSS; runs the verifier under `hyperfine`; writes results JSON. See `RFC-0008`.
- `scripts/measure_setup.sh`: one-shot capture of SP1 Groth16 trusted-setup cost. Reported separately from the headline.
- `scripts/lock_versions.sh`: regenerates `versions.lock` capturing every toolchain version, commit SHA, and binary checksum. See `RFC-0012`.
- `scripts/run_all.sh`: orchestration entry point. Calls `preflight.sh`, then runs both provers, then runs `analyze` and `plot`, then assembles `RESULTS.md`. The 30-minute clean-clone-to-results target binds this script.

## Data flow contracts

Five hops, each typed:

1. **PRD → workload pinning.** `WORKLOAD.md` is produced by reading the upstream `tanujkhattar/zkp_ecc` repo at the pinned commit (`N`, `W`, gate count, commitment scheme, entropy seed). Once written, it is frozen. See `RFC-0001`.
2. **Workload → fixture.** `gen_fixtures.py` consumes `WORKLOAD.md` constants and emits `fixtures/v0.1.json`. The fixture schema is in `03-data-model.md`. Cross-validation against `sim_reference.py` and `coincurve` happens here; failure aborts generation.
3. **Fixture → proof.** Each `bin/run_<prover>.sh` consumes the fixture and emits a proof artifact. The on-disk proof formats are prover-defined (opaque to the harness), but their sizes are measured (M6).
4. **Proof → verification.** Each `bin/verify_<prover>.sh` reads the proof and the fixture, returns 0/non-zero. The harness asserts 0 before accepting any timing measurement.
5. **Measurements → report.** `analyze.py` reads `results/*.json` (`hyperfine` JSON, `gnu-time` text, prover stdout, `discards.log`) and emits `RESULTS.md` + `results/plots/`. See `RFC-0011`.

## Concurrency and determinism

- Build-time concurrency is unrestricted (cargo, rustc parallelism is acceptable).
- Run-time concurrency is forced to 1 by environment variables (`RAYON_NUM_THREADS=1`, `TOKIO_WORKER_THREADS=1`, `OMP_NUM_THREADS=1`) and OS-level affinity (`taskpolicy -c utility` on macOS, `taskset -c 0` on Linux). See `RFC-0009` for the gap and its mitigation.
- The fixture generator is fully deterministic: the same `SEED` constant yields the same `fixtures/v0.1.json` byte-for-byte, modulo the `generator_commit` field. The deterministic build envelope is described in `RFC-0013`.
- Both provers must be deterministic given the same fixture and the same fixed environment. Non-determinism is a defect (issue: `bug` label, `area:correctness`).

## What lives outside this repo

- The PRD is `PRD.md`, kept in the repo as historical record of intent, but not the implementation contract.
- The upstream `tanujkhattar/zkp_ecc` repository (the SP1 example) is consumed as a submodule under `sp1-side/`.
- The upstream `starkware-libs/stwo` repository is consumed as a pinned-SHA dependency or submodule; the specific consumption model is decided in `RFC-0014`.
- `coincurve` (Python secp256k1 binding) is consumed via `uv` and pinned in `uv.lock`.
- `hyperfine` and `gnu-time` are system-installed; their versions are recorded in `versions.lock` (`RFC-0012`).

## Failure isolation

The measurement harness must distinguish "the prover failed" from "the measurement infrastructure failed". The prover wrappers (`bin/`) own exit code semantics for proof success/failure. The measurement scripts own exit code semantics for environmental violations (GPU residency, thermal, swap, env-var misses). The two error classes never share an exit code. See `04-error-model.md` for the full taxonomy.
