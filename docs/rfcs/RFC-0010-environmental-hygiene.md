# RFC-0010: Environmental hygiene, thermal protocol, discard rules

- Status: Accepted
- Authors: maintainer
- Created: 2026-05-13
- Target milestone: v0.1

## Summary

Single-laptop benchmarks live or die by environmental hygiene: background processes, thermal throttling, swap activity, and incidental display activity all inject noise. This RFC defines the preflight checks, the thermal protocol, the cool-down schedule, and the discard rules that together turn a noisy laptop into a usable measurement substrate.

## Motivation

Two run series of the same prover on the same hardware can differ by ~10%+ if one runs against a hot CPU and the other does not, or if one collides with Spotlight indexing while the other does not. The PRD §8 establishes a hygiene checklist and a thermal protocol; this RFC turns them into code (`preflight.sh`, `post_run_discard_check.sh`) and locks the discard rules so they may not be modified after seeing results.

## Goals

- A preflight script that asserts every hygiene precondition before any measured run.
- A thermal protocol that bounds CPU temperatures during the run window.
- Discard rules that are *prescriptive* (defined before measurement) and apply uniformly.
- A reproducible cool-down schedule between provers.

## Non-Goals

- Refrigeration, undervolting, or other hardware-tier interventions.
- Detecting *all* possible noise sources. We defend against the ones that actually move the median.
- Adapting to new noise sources mid-run. Adapting is a version bump.

## Proposed Design

### Pre-run hygiene checklist (macOS reference rig)

Run once before each measured session:

```bash
# Confirm AC power
pmset -g ps | grep -q "AC Power"

# Disable low-power mode (both internal and external power profiles)
sudo pmset -b lowpowermode 0
sudo pmset -a lowpowermode 0

# Disable App Nap and automatic sleep during the run series
caffeinate -dimsu &
CAFFEINATE_PID=$!

# Disable Spotlight indexing on the working tree
sudo mdutil -i off "$(pwd)"

# Wi-Fi off; Bluetooth off
networksetup -setairportpower en0 off
blueutil -p 0 2>/dev/null || true

# Background-noise sweep: quit known offenders
osascript -e 'tell application "Slack" to quit' 2>/dev/null || true
osascript -e 'tell application "Docker Desktop" to quit' 2>/dev/null || true
osascript -e 'tell application "Google Chrome" to quit' 2>/dev/null || true
# (and so on — a script-maintained list)

# Pause Time Machine for the window
sudo tmutil disable 2>/dev/null || true

# Disconnect external displays manually (asserted, not actioned).
```

After the session, the cleanup script reverses these.

### Pre-run hygiene checklist (Linux CI rig)

```bash
# Frequency governor
sudo cpupower frequency-set -g performance

# Intel turbo off (or AMD boost off)
echo 1 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null || \
echo 0 | sudo tee /sys/devices/system/cpu/cpufreq/boost 2>/dev/null

# Disable swap for the run window
sudo swapoff -a

# Confirm assertions
test "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)" = "performance"
test "$(cat /sys/devices/system/cpu/intel_pstate/no_turbo)" = "1"
```

### `preflight.sh`

A shell script that asserts the union of the above as preconditions:

- AC power confirmed (macOS).
- `lowpowermode == 0` (macOS).
- `governor == performance` (Linux).
- `no_turbo == 1` (Linux, Intel) or `boost == 0` (Linux, AMD).
- All four env caps (`RAYON_NUM_THREADS=1` etc.) set.
- Swap inactive (`vm.swapusage = 0` on macOS; `/proc/swaps` empty on Linux).
- `versions.lock` in sync.
- GPU residency check passes (per `RFC-0009`).

Any assertion failure → exit 5 (`MEASUREMENT.*` series-level), halt `measure.sh`.

### Thermal protocol

```
1. Cold-boot the laptop (or equivalent for the CI rig).
2. Wait 5 minutes for background daemons to settle.
3. Run one throwaway invocation of each prover. Discard.
4. Run SP1 measured series (`scripts/measure.sh sp1 ...`).
5. Cool-down: 5 minutes idle (no terminal interaction, no display sleep, no CPU work).
6. Run Stwo measured series (`scripts/measure.sh stwo ...`).
7. After both series: continue to verify, analyze, plot.
```

During every measured run, the harness samples temperatures:

- macOS: `sudo powermetrics --samplers smc -n 1 -i 1000` reads SMC sensors. Threshold: any P-core (performance core) temperature > 95°C invalidates the run series.
- Linux: `sensors` (lm-sensors) reads the CPU package. Threshold: package temperature > 90°C invalidates.

Sampling cadence: once before the series, once between SP1 and Stwo, once after. Sampling *during* the run is avoided to prevent interference.

### Run-order randomisation

Should we run Stwo first to invalidate "SP1 always runs hot, Stwo always runs cool"? The PRD specifies SP1 first; we accept this convention to keep the protocol deterministic, and we compensate via:

- **Day-2 reversal**: on day 2, run Stwo first, SP1 second. This sees whether the warm-vs-cool effect flips the headline; if it does, the day-1/day-2 stability gate fires and the result is reported with `[STABILITY BREACH]`.

The day-2 reversal is part of the protocol, not an optional add-on.

### Day-1 / Day-2 stability gate

- Two independent run series separated by at least one cold-boot and ≥ 12 hours of clock time.
- `analyze.py` computes `|median(M1, day1) - median(M1, day2)| / median(M1, day1)` per prover.
- If either prover's delta exceeds 5%: `RESULTS.md` headline includes `[STABILITY BREACH]` and the disclosures section includes a paragraph describing the investigation.
- A breach does *not* prevent publication; it changes the trust label on the number.

### Discard rules (binding; defined before measurement)

A measured sample is discarded if:

1. Thermal sampling during the run window exceeded the threshold above (`MEASUREMENT.THERMAL_EXCEEDED`).
2. GPU power residency was non-zero during the window (`MEASUREMENT.GPU_RESIDENT`).
3. Swap activity occurred during the window (`MEASUREMENT.SWAP_ACTIVE`).
4. The sample is the first run of its series (`cold_cache`, unconditional, `D-INV-3`).
5. The wrapper or prover exited non-zero (`PROVER.*` or `MEASUREMENT.*` per-run).

A discarded sample contributes nothing to the distribution. It is recorded in `results/discards.log` with reason and `run_id`.

These rules **may not be modified after the first measured run series**. A change to the rules is a project version bump (`09-release-and-versioning.md`).

### Discard rate cap

If, after applying the rules, fewer than 10 valid M1 samples per prover remain, `analyze.py` aborts with `REPORT.INSUFFICIENT_SAMPLES`. The operator must investigate, fix the environment, and re-run. Publishing with < 10 samples is forbidden.

If the discard rate exceeds 30% on either prover, `analyze.py` adds `[HIGH DISCARD]` to the headline and includes a per-reason histogram in disclosures.

### Post-session restoration

After all measured runs complete:

```bash
# macOS
kill $CAFFEINATE_PID
sudo pmset -a lowpowermode 1       # restore prior state, not blindly 1 — record and restore
sudo mdutil -i on "$(pwd)"
networksetup -setairportpower en0 on
sudo tmutil enable

# Linux
sudo cpupower frequency-set -g powersave   # or whichever governor was prior
echo 0 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo
sudo swapon -a
```

A `cleanup.sh` script records the prior state at preflight and restores it. Failing to restore is operator-error, not benchmark-error.

## Alternatives Considered

### A1. Skip the thermal protocol; rely on `hyperfine --warmup 1`

Pros: simpler.

Cons:
- One warmup run is enough to fill the cache but not to settle thermal state on a hot laptop.
- The day-1/day-2 stability gate would frequently fire, signalling unreproducibility.

Rejected.

### A2. Lower the thermal threshold (e.g., 85°C on macOS)

Pros: stricter discard, less thermal-bias variance.

Cons: discard rate explodes on a laptop in normal operation; would push us below the 10-sample minimum. 95°C is the level Apple cites as "thermal throttling onset"; we discard above that, not at the first hint of warmth.

Rejected.

### A3. Run measurements inside an idle-monitored sandbox (Docker, etc.)

Pros: isolates from host noise.

Cons:
- Adds hypervisor / cgroup overhead.
- The "single laptop, single user" promise is to run on the user's actual machine.

Rejected.

### A4. Skip the day-2 reversal; trust day-1 absolute numbers

Rejected: day-2 is the cheapest cross-environment noise check and would be silly to omit for a project whose headline is a wall-clock ratio.

## Drawbacks

- The preflight script is platform-specific and brittle to OS updates (a macOS version bump may rename `mdutil` flags). Mitigated by: tests that exercise `preflight.sh` against the actual reference rig, and by recording the macOS version in `versions.lock.host.kernel`.
- Manual external-display disconnection is operator-attested rather than enforced. A defect-class violation: documented, not technically enforced. The honesty trade-off is acceptable.

## Migration / Rollout

First-time. Lands alongside `RFC-0008` and `RFC-0009`.

## Testing Strategy

- **H-T1**: `preflight.sh` failure modes: simulate each precondition violation; assert exit 5.
- **H-T2**: Thermal threshold check: synthetic `powermetrics` output above threshold → series invalidated.
- **H-T3**: GPU residency check: synthetic non-zero residency → run discarded.
- **H-T4**: Swap-active check: artificially enable swap → series invalidated.
- **H-T5**: Discard rate cap: synthetic 4 discards out of 10 → `[HIGH DISCARD]` flag in disclosures.
- **H-T6**: Insufficient samples: 9 valid samples → `REPORT.INSUFFICIENT_SAMPLES`.
- **H-T7**: Stability gate: synthetic day-1 = 1.0s median, day-2 = 1.06s median → `[STABILITY BREACH]` flagged.

## Open Questions

**OPEN-Q-10.1** — Should the day-2 reversal be enforced by tooling (`scripts/run_all.sh --day 2` mandatorily runs Stwo first) or operator discipline? Current decision: tooling-enforced. The operator's `--day 2` flag is the trigger; the script then dictates the order. Owner: maintainer. Resolution: implemented as part of `scripts/run_all.sh` work.

## References

- `docs/spec/04-error-model.md` (`MEASUREMENT.*`)
- `RFC-0008` (measurement pulls preflight)
- `RFC-0009` (single-core ties into hygiene)
- `RFC-0011` (analyze.py applies discard rules; emits headline flags)
- PRD `PRD.md` §8
