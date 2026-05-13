# RFC-0008: Measurement protocol (M1–M10)

- Status: Accepted
- Authors: maintainer
- Created: 2026-05-13
- Target milestone: v0.1

## Summary

This RFC locks the measurement protocol: which tools, which sample sizes, which output formats, and which fields enter `RESULTS.md`. Two principles bind: (a) use existing standards (`hyperfine`, `gnu-time -v`) rather than rolling our own timing layer; (b) capture distributions, not single numbers.

## Motivation

A benchmark whose numbers are a single sample is not a benchmark — it is a story. The PRD §7 enumerates a fixed metric set and a capture script; this RFC formalises both and locks the parameters (warmup, runs, output format) so future "let's tune the measurement" PRs are visible as version bumps.

## Goals

- Capture M1 (proof gen wall-clock) as a distribution over ≥ 10 measured (post-discard) runs per prover.
- Capture M2 (peak RSS) and M3/M4 (user/sys CPU) via `gnu-time -v` on one representative run per series.
- Capture M5 (verifier wall-clock) as a distribution over ≥ 50 measured runs per prover.
- Capture M6 (proof size), M7 (trace/constraints), M8/M9 (setup), M10 (disk writes) per the schema in `03-data-model.md`.
- Make all captures resumable / re-runnable without manual cleanup.

## Non-Goals

- Production performance regression infrastructure. This is a one-shot release benchmark, not a CI continuous-perf regime.
- Process-isolation tooling beyond what `taskset` / `taskpolicy` provide.
- Custom timing harnesses. Established tools only.

## Proposed Design

### Tool matrix

| Metric | Tool | Sample size | Output format |
|---|---|---|---|
| M1 (proof gen wall-clock) | `hyperfine --warmup 1 --runs 10 --export-json` | 10 | JSON |
| M2 (peak RSS) | `gnu-time -v` on a single representative run | 1 | text |
| M3 (user CPU) | `gnu-time -v` | 1 | text |
| M4 (sys CPU) | `gnu-time -v` | 1 | text |
| M5 (verifier wall-clock) | `hyperfine --warmup 3 --runs 50 --export-json` | 50 | JSON |
| M6 (proof size) | `stat` | 1 | text |
| M7 (trace rows / constraints) | prover stdout grammar | 1 | text |
| M8 (SP1 setup wall-clock) | `gnu-time -v` one-shot | 1 | text |
| M9 (setup output size) | `stat` (PK + VK) | 1 | text |
| M10 (disk writes) | `iostat`-integrated | 1 (informational) | JSON |

### `scripts/measure.sh`

The capture script is closely modelled on PRD §7.2. It is the *only* place that knows the sample sizes and warmup counts; changing them anywhere else is forbidden.

```bash
#!/usr/bin/env bash
# scripts/measure.sh — capture one prover's run series
set -euo pipefail

PROVER="$1"               # sp1 | stwo
RUN_ID="$2"               # <epoch_ts>-<short_repo_sha>
OUT_DIR="results"
OUT="${OUT_DIR}/${PROVER}_v0.1_${RUN_ID}"
mkdir -p "$OUT_DIR"

export CUDA_VISIBLE_DEVICES=""
export RAYON_NUM_THREADS=1
export TOKIO_WORKER_THREADS=1
export OMP_NUM_THREADS=1

if [[ "$(uname)" == "Darwin" ]]; then
  PREFIX="taskpolicy -c utility"
  TIME_BIN="gtime"
  STAT_CMD="stat -f %z"
else
  PREFIX="taskset -c 0"
  TIME_BIN="/usr/bin/time"
  STAT_CMD="stat -c %s"
fi

PROVE_CMD="$PREFIX ./bin/run_${PROVER}.sh fixtures/v0.1.json ${OUT}.proof"
VERIFY_CMD="$PREFIX ./bin/verify_${PROVER}.sh ${OUT}.proof"

# Hygiene preflight — exits 5 on violation.
./scripts/preflight.sh

# M1: wall-clock distribution.
hyperfine --warmup 1 --runs 10 --export-json "${OUT}.timing.json" "$PROVE_CMD"

# M2 M3 M4: representative run under gnu-time.
$TIME_BIN -v -o "${OUT}.time.txt" $PROVE_CMD

# M6: proof size.
$STAT_CMD "${OUT}.proof" > "${OUT}.proof_size.txt"

# M7: trace + constraints scraped from a debug run.
RUST_LOG=info $PROVE_CMD 2>&1 | tee "${OUT}.proverlog.txt"

# M5: verifier distribution.
hyperfine --warmup 3 --runs 50 --export-json "${OUT}.verify.json" "$VERIFY_CMD"

# M10: disk-write monitoring during a representative run (informational).
( ./scripts/iostat_capture.sh "${OUT}.iostat.json" $PROVE_CMD ) || true

# Post-run discard inspection (thermal, GPU residency, swap, cold cache).
./scripts/post_run_discard_check.sh "$OUT" "$PROVER" "$RUN_ID"

echo "DONE: $OUT"
```

### Sample sizes and warmup

- **M1**: `--warmup 1 --runs 10`. One warmup is enough because the first measured run is independently discarded as `cold_cache` (`D-INV-3`). The 10-run minimum is the floor under which IQR is unreliable; we may revisit for `v0.2`.
- **M5**: `--warmup 3 --runs 50`. The verifier is short-running; sub-second wall-clock benefits from many samples to suppress per-invocation noise.
- **M8** (setup): single shot. The trusted-setup ceremony is structural and not part of the proof-gen distribution.

### Discard application

`scripts/post_run_discard_check.sh` is called *after* each `hyperfine` series. It samples:

- `powermetrics --samplers gpu_power -n 1 -i 100` on macOS, or `nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits` on Linux (returning "no GPU" if no GPU is present). If non-zero residency during the run window: `MEASUREMENT.GPU_RESIDENT`.
- `sudo powermetrics --samplers smc -n 1 -i 1000` (macOS) or `sensors` (Linux) for thermals. Threshold per `RFC-0010`. If exceeded: `MEASUREMENT.THERMAL_EXCEEDED`.
- `sysctl vm.swapusage` (macOS) or `/proc/swaps` (Linux). If non-zero: `MEASUREMENT.SWAP_ACTIVE`.
- The unconditional cold-cache first-run discard (`D-INV-3`).

Each discard appends to `results/discards.log`. The valid sample size after discards must remain ≥ 10 for M1 and ≥ 40 for M5; otherwise `analyze.py` reports `REPORT.INSUFFICIENT_SAMPLES`.

### Stability check (Day-1 / Day-2)

The protocol *requires* two run series separated by at least one cold-boot. `scripts/run_all.sh` does day-1 only; the operator manually re-runs the day after to produce day-2 results. `analyze.py` compares the two and flags `[STABILITY BREACH]` if M1 medians differ by > 5%.

The mechanics:

- Day-1 results live at `results/day1/`.
- Day-2 results live at `results/day2/`.
- `scripts/run_all.sh --day 1` (default) writes day-1; `--day 2` writes day-2.
- `analyze.py` computes per-day medians and the delta.

### `analyze.py` derived statistics

For each `(prover, metric)`, `analyze.py` computes:

```python
@dataclass
class Stats:
    median: float
    mean: float
    stddev: float
    iqr: float
    min: float
    max: float
    n_valid: int
    n_discarded: int
```

Stored in memory only; written to `RESULTS.md`. Not re-persisted to JSON.

### Headline ratio definition

```
ratio = median(SP1, M1) / median(Stwo, M1)
```

Numerator first because the project's prior expectation is `ratio > 1` (Stwo faster). The convention is *binding*: even if the actual ratio is `< 1`, the headline reports it in the same form (a `0.3×` headline is a `0.3×` headline, not "Stwo is slower").

### Verifier wall-clock units

Reported in milliseconds. `hyperfine` reports seconds; `analyze.py` converts. The choice of milliseconds reflects the operating range of typical Groth16 and STARK verifiers.

## Alternatives Considered

### A1. Roll our own timing harness

Pros: fully under our control.

Cons:
- `hyperfine` is well-tested and produces a stable JSON output. Re-implementing it would expand attack surface.
- A custom timer would have to defend against the same noise sources `hyperfine` already addresses (cache warmth, scheduler jitter).

Rejected.

### A2. Bigger sample sizes (e.g., 100 runs of M1)

Pros: tighter confidence intervals.

Cons:
- Pushes total wall-clock past the 30-minute headline target.
- IQR over 10 vs 100 samples differs by < 30% in typical short-tailed distributions; the marginal precision gain is not worth the time.
- Day-1/Day-2 stability provides the *cross-environment* noise check that bigger sample sizes do not.

Rejected for `v0.1`. May revisit for `v0.2` once the workload is sized definitively.

### A3. Median-of-three protocol instead of full distribution

Pros: faster, simpler.

Cons: loses the IQR and stddev needed to honest reporting.

Rejected.

### A4. Use `perf stat` (Linux) for richer counters

Pros: instruction counts, cache misses, branch mispredictions — richer comparison.

Cons:
- `perf` is Linux-only; would diverge the macOS and Linux capture paths.
- Counters are not what the headline is about. They are interesting future-work.

Rejected for `v0.1`; possible `v0.2` minor extension.

## Drawbacks

- The 10-run M1 sample size is at the low end. We accept this in exchange for the 30-minute headline target; if the headline can be relaxed (e.g., `v0.2` with a 60-minute target), bumping to 30+ runs is straightforward.
- macOS thermals can shift across the M1 and M5 measurement windows. Mitigated by the 5-minute cool-down between SP1 and Stwo series (`RFC-0010`).

## Migration / Rollout

First-time. Lands alongside `RFC-0010` (hygiene) since the two are coupled.

## Testing Strategy

- **M-T1**: `scripts/measure.sh sp1 1` on the reference rig produces all expected output files.
- **M-T2**: `hyperfine` JSON is parseable by `analyze.py`; a malformed JSON aborts with `REPORT.SCHEMA_INVALID`.
- **M-T3**: `gnu-time -v` output is parseable; a missing field aborts with the appropriate error.
- **M-T4**: Sample-size discipline: simulate 11 timing samples; discard 1 cold-cache; assert `analyze.py` accepts (10 valid). Simulate 10; discard 1; assert `REPORT.INSUFFICIENT_SAMPLES`.
- **M-T5**: Day-1/Day-2 delta check: synthetic timing series with known medians; assert correct `[STABILITY BREACH]` flagging.
- **M-T6**: Headline ratio convention: assert `analyze.py` produces `(SP1 / Stwo)` always, even when `<1`.

## Open Questions

**OPEN-Q-8.1** — `iostat_capture.sh` interaction with the measured window. The current draft samples *during* the run, which has a small but nonzero overhead. The mitigation is to make M10 informational (footnoted in `RESULTS.md`). If overhead is found to materially affect M1, the M10 capture moves to a *separate* unmeasured run. Owner: maintainer. Target resolution: end of measurement-implementation phase.

## References

- `docs/spec/02-public-api.md` (output files)
- `docs/spec/05-observability.md` (metric set)
- `docs/spec/08-performance-budget.md`
- `RFC-0007` (wrapper contract consumed here)
- `RFC-0010` (preflight + post-run discards)
- `RFC-0011` (analyze.py consumes these outputs)
- PRD `PRD.md` §7
