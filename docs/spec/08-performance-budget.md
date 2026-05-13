# Performance budget

This project is itself a performance measurement. The "budget" therefore has two faces:

- The *headline workload* (proving and verifying) is what we measure. There is no a-priori target on M1 — we report whatever it is. What we constrain is the *measurement experience*: how long the full reproduction takes, how much disk and RAM the harness needs, how much noise is acceptable.
- The *harness overhead* must be small relative to what it measures, or the numbers are about the harness, not about the provers.

## Headline budget: clean-clone-to-results

| Phase | Target wall-clock (reference rig) | Hard ceiling |
|---|---|---|
| `git clone` of this repo | 30 s | 2 min |
| `git submodule update --init` (`sp1-side`, `stwo`) | 2 min | 5 min |
| `uv sync --frozen` (Python env) | 30 s | 2 min |
| `cargo build --release` for SP1 side | 5 min | 12 min |
| `cargo build --release` for Stwo side | 4 min | 10 min |
| `preflight.sh` | < 5 s | 30 s |
| `gen-fixtures` | < 5 s | 30 s |
| `scripts/measure_setup.sh` (SP1 Groth16 setup) | 1 min | 5 min |
| `scripts/measure.sh sp1` (10 runs + verify x50) | 6 min | 12 min |
| `scripts/measure.sh stwo` (10 runs + verify x50) | 5 min | 10 min |
| `analyze` + `plot` | < 30 s | 2 min |
| **Total `git clone` → `RESULTS.md`** | **~25 min** | **45 min** |

The 30-minute headline target is the *aspirational* end-to-end time on the reference rig. The 45-minute ceiling is binding: a `run_all.sh` that exceeds 45 minutes triggers a workload-size revisit (per `RFC-0001`).

Per-prover wall-clock budgets above are estimates pending day-1 measurement on the reference rig. They are *not* targets — they are sanity bounds that, if violated by more than 2x, indicate the workload is mis-sized for the headline target.

## Per-run cost envelope

Each individual proof-generation run must complete within:

- **Wall-clock ceiling:** 600 s (10 min). Runs exceeding this are killed with `PROVER.TIMEOUT` and discarded.
- **RSS ceiling:** 32 GiB. Approaching this on the 48 GiB reference rig is the first sign of imminent swap activity. The harness does not enforce a hard kill at this limit, but `RESULTS.md` flags any run with peak RSS > 32 GiB as `[HIGH MEMORY]`.

Each individual verifier run must complete within:

- **Wall-clock ceiling:** 60 s. Verifier slower than that is a defect (verifier is supposed to be `O(circuit_size_log)` or constant for the Groth16-wrapped side).

These ceilings are *operational*, not targets. The actual numbers we publish are whatever they are.

## Harness overhead budget

The harness must not dominate the measurement. Specifically:

- **Per-run harness overhead:** ≤ 200 ms beyond the prover's own wall-clock, comprising `bin/run_<prover>.sh` shell startup, fixture file read into the prover, and the `hyperfine` per-iteration overhead. Anything larger requires investigation.
- **`gnu-time` overhead:** negligible on macOS and Linux at the granularity we measure.
- **Schema validation overhead:** runs *outside* the measured window. `analyze.py` validates after the runs complete.
- **`preflight.sh` overhead:** runs *before* the measured window. Its own wall-clock is not measured.

If harness overhead approaches the prover's own wall-clock, switch to longer per-run workloads rather than to a thinner harness; the harness is correctness-load-bearing.

## Disk budget

A full `run_all.sh` produces:

| Artifact category | Per-run series (one prover) | Total (both provers + setup) |
|---|---|---|
| Proof artifacts | ~10 × 200 KB to 1 MB | 10–20 MB |
| Timing JSON | ~10 × 5 KB | < 200 KB |
| Proverlogs | ~10 × 50 KB | < 2 MB |
| `iostat` JSON (M10) | ~10 × 20 KB | < 1 MB |
| Plots | n/a | < 500 KB |
| SP1 trusted-setup keys | n/a | 50 MB – 2 GB (verify pin) |

Total under 2.5 GB on disk for one full run series. Reference rig requires ≥ 50 GB free per `4.1`; CI requires ≥ 10 GB.

## Noise budget

The day-1 / day-2 stability check enforces a ≤ 5% delta in M1 medians (see `RFC-0010`). Beyond that:

- IQR / median ≤ 10% per prover. If IQR exceeds 10% of the median on M1, `RESULTS.md` flags `[HIGH VARIANCE]` and includes the discard-rate breakdown.
- Per-run user-CPU vs wall-clock delta ≤ 10%. If user CPU exceeds wall-clock by more than 10%, residual concurrency is presumed and reported in the apples-to-apples disclosures section.

These are reporting gates, not run-abort gates. The benchmark always publishes; it just publishes with appropriate flags.

## Profile-plan

This is the explicit profiling plan for *the harness itself*, not the provers:

1. After implementation, run `scripts/measure.sh sp1` and `scripts/measure.sh stwo` once each on the reference rig.
2. Subtract `hyperfine`'s reported mean from `gnu-time`'s wall-clock; the difference is the per-run shell + I/O overhead.
3. If overhead > 200 ms per run, profile the shell wrappers with `dtruss` (macOS) or `strace -c` (Linux) inside a non-measured run.
4. Land overhead reductions in the wrappers, not in the measured prover invocation.

We do not commit to profiling the provers themselves. SP1 and Stwo profiling are upstream concerns.

## What "fast enough" looks like

For `v0.1`, "fast enough" is *not* a comparative claim. It is a fixed clock budget:

- `run_all.sh` completes within 45 minutes on the reference rig.
- The headline ratio `t_SP1_Groth16 / t_Stwo` is reportable (i.e., both provers actually finish a run series).
- The day-1 / day-2 stability gate passes (or is reported with `[STABILITY BREACH]` and an investigation note).

If any of these fails, the workload is re-sized (smaller `N`, fewer runs) and the project re-runs the budget exercise before publishing.

## Future-work performance items (out of `v0.1`)

These are noted here so they do not surprise a future maintainer:

- Multi-core proving: would invalidate the single-core comparison; deliberately out of scope.
- GPU proving paths on either side: deliberately out of scope.
- Cross-laptop variance: out of scope.
- Provenance-bounded build (bit-stable `cargo build`): see `RFC-0013`; partial in `v0.1`, full in a future release.
