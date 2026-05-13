# RFC-0009: Single-core / no-GPU enforcement

- Status: Accepted
- Authors: maintainer
- Created: 2026-05-13
- Target milestone: v0.1

## Summary

The headline numbers are produced under explicit single-core, no-GPU constraints. This RFC locks both the *enforcement mechanism* (env vars, OS-level affinity) and the *verification mechanism* (`preflight.sh` assertions, GPU residency sampling). It also names the macOS gap — Apple Silicon does not expose kernel-level single-core affinity — and the mitigations that keep that gap honest.

## Motivation

If the comparison drifts to "multi-threaded SP1 vs single-threaded Stwo" or "SP1 with a touch of Apple Silicon GPU vs CPU-only Stwo", the headline is meaningless. Both deviations are silent unless deliberately checked: `RAYON_NUM_THREADS` is unset by default; Apple Silicon's GPU may be used by background processes; macOS does not expose `taskset`-equivalent affinity.

The defence is layered: env caps, OS-affinity, runtime GPU sampling, and explicit disclosure of the macOS gap.

## Goals

- A measured run uses one and only one CPU core for prover work.
- A measured run uses no GPU.
- A `MEASUREMENT.*` precondition violation is detectable before the prover runs.
- A `MEASUREMENT.GPU_RESIDENT` violation during the run window is detectable after.
- The macOS frequency-pinning gap is documented in `RESULTS.md`.

## Non-Goals

- Achieving cryptographically-perfect single-core isolation. macOS does not support it; we document and mitigate.
- GPU detection on hypothetical exotic platforms (TPU, NPU). The scope is "Apple Silicon GPU" and "discrete NVIDIA/AMD GPU".
- Detection of "indirect" parallelism (e.g., spawning subprocesses that the env caps would not cap). Practically, neither prover does this at the pinned versions.

## Proposed Design

### Environment caps (applied by `measure.sh` and asserted by `bin/*` wrappers)

```bash
export CUDA_VISIBLE_DEVICES=""
export RAYON_NUM_THREADS=1
export TOKIO_WORKER_THREADS=1
export OMP_NUM_THREADS=1
```

- `CUDA_VISIBLE_DEVICES=""` zeroes NVIDIA visibility; the prover sees no CUDA devices.
- `RAYON_NUM_THREADS=1` caps Rust `rayon` parallelism (both SP1 and Stwo depend on `rayon`).
- `TOKIO_WORKER_THREADS=1` caps `tokio` runtime parallelism. SP1's prover uses `tokio` indirectly through some dependencies.
- `OMP_NUM_THREADS=1` caps OpenMP-using native deps if any are pulled transitively.

The wrappers assert each variable is *set and exactly equals the expected value* before invoking the prover. Missing or wrong → `MEASUREMENT.ENV_VAR_MISS` (wrapper exit 2).

### OS-level affinity

- **macOS reference rig**: `taskpolicy -c utility ./bin/run_<prover>.sh ...`. `taskpolicy -c utility` is *not* a hard single-core pin — it is a QoS class hint that confines the process to performance cores plus background concurrency. Combined with the thread-count caps above, this keeps concurrent work in the prover process at 1.
- **Linux CI rig**: `taskset -c 0 ./bin/run_<prover>.sh ...`. This is a hard pin to logical CPU 0.

The wrappers do *not* prepend the affinity prefix themselves — `measure.sh` does. The wrappers verify that the affinity prefix is present in their `${PARENT_INVOCATION}` via the `MEASUREMENT.AFFINITY_MISS` check. Implementation: the wrappers read `/proc/$$/status` (Linux) for `Cpus_allowed_list` and confirm it is exactly `0`; on macOS, the wrappers read `sysctl kern.osproductversion` and `pmset -g` to confirm the QoS class is `utility` (best-effort given the macOS API surface).

If the affinity check fails: wrapper exits 2 with `MEASUREMENT.AFFINITY_MISS`. The run is *not* discarded — it is *prevented*.

### macOS-specific gap

macOS does not expose a hard single-core CPU affinity to user-space. `taskpolicy -c utility` is the closest available; it constrains the process to a QoS class but allows the kernel to migrate the process across cores within that class.

The harness compensates with:

1. **Thread-count caps** (`RAYON_NUM_THREADS=1` etc.) — keep concurrent work at 1 even when cores are available.
2. **Warmup runs** (`hyperfine --warmup 1`) — settle frequency/thermal state before measurement.
3. **Cool-down protocol** (`RFC-0010` §thermal) — 5-minute cool-down between SP1 and Stwo series.
4. **Discard rules** — invalidate any run where user-CPU exceeds wall-clock by > 10% (`RFC-0011` apples-to-apples disclosure).
5. **Day-1 / Day-2 stability gate** — if macOS scheduler effects shift between independent run series, the gate catches it.
6. **Explicit disclosure** — `RESULTS.md` includes the paragraph:

> Apple Silicon does not expose a kernel knob to disable dynamic frequency scaling or to pin a process to a single physical core. The harness uses `taskpolicy -c utility` to constrain QoS class and `RAYON_NUM_THREADS=1` / `TOKIO_WORKER_THREADS=1` / `OMP_NUM_THREADS=1` to cap intra-process concurrency. The macOS measurement is single-threaded by construction but not single-core-pinned. The Linux CI rig results, with hard `taskset -c 0` pinning, are reported in a separate column as a cross-check.

The disclosure is required content; methodology lint `M-2` enforces it.

### GPU residency check

Before and after every measured run, the harness samples GPU power draw:

- **macOS**: `sudo powermetrics --samplers gpu_power -n 1 -i 1000`. Threshold: any reading > 0.5 mW is non-zero residency (background processes often leak ~0 mW). A reading above this triggers `MEASUREMENT.GPU_RESIDENT`.
- **Linux**: `nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits` (if NVIDIA present); analogous AMD command via `rocm-smi`. Threshold: any reading > 1 W.
- **Platforms without GPU at all**: the check is skipped with a recorded "no GPU detected" line in the run metadata.

The check is asymmetric: sampling *before* the run prevents starting under a violation; sampling *after* catches violations during. A violation in either invalidates the entire run series (`measure.sh` exit 5), not just one sample.

### `preflight.sh`

`scripts/preflight.sh` runs once before `measure.sh sp1` and once before `measure.sh stwo`, asserting:

```
# Env vars set correctly
test "$CUDA_VISIBLE_DEVICES" = ""
test "$RAYON_NUM_THREADS" = "1"
test "$TOKIO_WORKER_THREADS" = "1"
test "$OMP_NUM_THREADS" = "1"

# Power state (macOS)
pmset -g ps | grep -q "AC Power"
! pmset -g | grep -qE "lowpowermode\s+1"

# Frequency governor (Linux)
test "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)" = "performance"
test "$(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null || echo 1)" = "1"

# Swap state
case "$(uname)" in
  Darwin) ! sysctl vm.swapusage | grep -qE "used = [^0]" ;;
  Linux)  test ! -s /proc/swaps || grep -E "^[^Filename]" /proc/swaps | wc -l | grep -q "^0$" ;;
esac

# GPU pre-check
./scripts/check_gpu_residency.sh

# versions.lock drift
diff <(scripts/lock_versions.sh --dry-run) versions.lock || exit 5
```

Any failure exits with code 5 (`MEASUREMENT.*` series-level).

### Compatibility with both prover backends

Both SP1 and Stwo respect `RAYON_NUM_THREADS=1`. Both build cleanly under the env caps. If a future upstream change introduces a thread pool not capped by these variables, that is a `BUILD.*`-class issue requiring an RFC update (and possibly a re-pin to a compatible upstream commit).

## Alternatives Considered

### A1. Forgo affinity on macOS; rely solely on env-var caps

Pros: simpler.

Cons:
- macOS scheduler may park the process on an efficiency core, distorting performance. `taskpolicy -c utility` reduces (not eliminates) this risk.
- Disclosure alone is insufficient when a partial mitigation exists.

Rejected.

### A2. Run macOS measurements inside an `arm64` Linux VM

Pros: hard `taskset -c 0` becomes available.

Cons:
- The VM is a new variable that bias the numbers in an unknown direction (hypervisor scheduling, virtualised memory).
- Defeats the "single laptop, single user" promise.

Rejected.

### A3. Use `chrt --fifo 99` (Linux real-time priority)

Pros: reduces scheduler preemption.

Cons:
- Real-time priority on a non-RT kernel is a different regime; not representative of how users run provers.
- macOS has no clean equivalent; introduces a CI/reference asymmetry.

Rejected.

### A4. Cool the reference rig in a refrigerator

Genuinely considered, rejected as silly. The thermal protocol of `RFC-0010` is the documented compensation.

## Drawbacks

- macOS single-core enforcement is partial. The disclosures explain this; readers must judge.
- GPU residency sampling has its own overhead (`sudo powermetrics` is slow on macOS — ~100ms). The sample is *outside* the measured window, so the overhead is on harness wall-clock, not M1.
- If a hypothetical third prover spawned its own thread pool not capped by `RAYON_NUM_THREADS`, the env caps would fail. We accept this as a known limitation, addressable by adding a new env-cap if such a prover is added.

## Migration / Rollout

First-time. Lands alongside `RFC-0007` (wrappers) and `RFC-0010` (hygiene).

## Testing Strategy

- **S-T1**: Unit test: launch a synthetic worker with `RAYON_NUM_THREADS=4`; assert wrapper exits 2.
- **S-T2**: Unit test: launch with all env caps set, but without affinity prefix; assert wrapper exits 2 with `MEASUREMENT.AFFINITY_MISS`.
- **S-T3**: Integration: on a host with no GPU, `check_gpu_residency.sh` records "no GPU detected" and exits 0.
- **S-T4**: Integration: simulate GPU residency (writing a stub `powermetrics` that returns non-zero); assert `MEASUREMENT.GPU_RESIDENT` fires and the run series invalidates.
- **S-T5**: Methodology lint: `RESULTS.md` contains the macOS-affinity disclosure paragraph.
- **S-T6**: User-CPU vs wall-clock check: if user-CPU > wall-clock × 1.10 on a recorded run, `analyze.py` includes the residual-concurrency note in disclosures.

## Open Questions

**OPEN-Q-9.1** — A future Apple Silicon `taskpolicy` variant or third-party tool might expose hard core pinning. If/when it ships, we should adopt it. Owner: maintainer. Target resolution: scan macOS release notes for each Sequoia point release; revisit at next minor bump.

## References

- `docs/spec/04-error-model.md` (`MEASUREMENT.*`)
- `RFC-0007` (wrappers enforce per-run)
- `RFC-0008` (measure.sh applies and asserts)
- `RFC-0010` (hygiene preflight)
- `RFC-0011` (disclosures)
- PRD `PRD.md` §4.3
