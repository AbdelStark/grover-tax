# v0.1 Technical Specification

**Document:** Single-laptop, single-core, no-GPU benchmark of Stwo vs SP1+Groth16 on the ECDLP-paper point-addition ZKP example.
**Status:** spec frozen for implementation.
**Scope:** Tier 1 only.
**Repository:** `grover-tax`.

---

## 1. Objective

Produce a reproducible, publicly verifiable wall-clock comparison of two ZK proving stacks on a single proof statement, on a single CPU core, on a single laptop.

Exit conditions (all four required):

1. Both provers run end-to-end against a shared fixture file on the reference rig.
2. The full protocol completes in under 30 minutes from `git clone` on a clean machine.
3. The headline ratio `t_SP1_Groth16 / t_Stwo` is reported with median, IQR, min, max, and stddev over a minimum of 10 measured runs per prover.
4. A `RESULTS.md` file reports results on each of (wall-clock, peak RSS, proof size, verify time, constraint count, setup cost) with apples-to-apples caveats called out explicitly.

---

## 2. Proof statement (locked)

The proof attests, in zero knowledge over a secret reversible classical circuit `C`:

> There exists a reversible classical circuit `C` composed of NOT, CNOT, and Toffoli gates such that for the public test-case set `T = {(x_i, y_i)}_{i=1..N}`, executing `C` on each `x_i` produces the corresponding `y_i`, and `C` realises one elliptic-curve point addition over secp256k1.

Public inputs:
- `T` (the fixed test-case set, serialised in `fixtures/v0.1.json`).
- `H_C`, a commitment to the gate-list encoding of `C`. SP1 side: SHA-256. Stwo side: Blake2s. Both commitments are bound by their respective verifiers.

Secret input (witness):
- `C` itself, the gate-list encoding.

The simulator semantics on both sides are the same gate-by-gate semantics implemented in `tanujkhattar/zkp_ecc/lib/src/sim.rs`. Both sides ingest the same `fixtures/v0.1.json`. The only intentional divergence is the hash function used to commit to `C`, called out below in §6.4.

---

## 3. Workload parameters (read-from-repo, then freeze)

The following fields are extracted from `tanujkhattar/zkp_ecc` at the pinned commit and committed verbatim into `WORKLOAD.md` on day 1 of implementation. Until they are filled in, no Cairo is written.

| Field | Source | Value |
|---|---|---|
| Number of test cases `N` | default in `example_zkp_prove.rs` | TBD |
| Gate count of `C` for one secp256k1 point-add | output of `sim.rs` initialisation | TBD |
| Bit-stripe width `W` | constant in `sim.rs` hot loop | TBD |
| Modular-arithmetic gate count | derived from `sim.rs` | TBD |
| Circuit-commitment scheme on SP1 side | source-read `example_zkp_prove.rs` | TBD (expected: SHA-256 over gate list) |
| Entropy source for test-case generation | source-read `example_zkp_prove.rs` | SHA-2 XOF, seed TBD |

These six values are the contract. The fixture generator, the Cairo translation, and the result reporting all bind to them. Changing any of them after they are pinned invalidates the prior run series.

---

## 4. Hardware specification

### 4.1 Reference rig (canonical, all headline numbers come from this)

| Attribute | Specification |
|---|---|
| Architecture | arm64 (Apple Silicon) |
| Chip | Apple M4 Max |
| Cores | 16 total (12 performance + 4 efficiency) |
| Cores used by prover | 1 |
| RAM | 48 GB unified memory |
| Storage | internal NVMe, ≥50 GB free |
| OS | macOS 26.2 (build 25C56) |
| Power | AC, low-power mode disabled (`pmset -b lowpowermode 0`) |
| Network | offline for measured runs (Wi-Fi and Bluetooth off) |

### 4.2 CI rig (Linux, optional, separate column)

Used for automated regression runs in CI only. Never substitutes for the reference rig in headline numbers.

| Attribute | Specification |
|---|---|
| Architecture | x86_64 |
| CPU | recorded per-run in `versions.lock`; minimum 8 physical cores at ≥3.5 GHz base |
| Cores used by prover | 1, pinned with `taskset -c 0` |
| Frequency | governor `performance`, turbo disabled (`intel_pstate/no_turbo=1` or AMD `cpufreq/boost=0`) |
| RAM | ≥32 GB DDR4/DDR5 |
| Swap | disabled via `swapoff -a` for the run series |
| OS | Ubuntu 24.04 LTS, kernel ≥6.5 |

### 4.3 What single-core, no-GPU means in practice

The following environment variables are exported in every shell that invokes either prover:

```
CUDA_VISIBLE_DEVICES=""
RAYON_NUM_THREADS=1
TOKIO_WORKER_THREADS=1
OMP_NUM_THREADS=1
RUST_LOG=info
```

macOS reference rig: single-core CPU pinning is not exposed by the kernel. The harness uses `taskpolicy -c utility` to confine the process to performance cores plus the thread-count caps above to keep concurrent work at 1. The gap (no hard single-core affinity) is documented in `RESULTS.md`.

Linux CI rig: invocation prefix `taskset -c 0`.

Both provers must be invoked through their single-threaded CPU backends. SP1's CUDA prover and Stwo's GPU and sharded-prover paths are explicitly off-limits for v0.1.

GPU activity must be zero during measured runs. The harness asserts this on macOS by sampling `powermetrics --samplers gpu_power -n 1 -i 1000` before and after each run; non-zero GPU residency invalidates the run.

---

## 5. Software specification

### 5.1 Toolchain matrix (pinned in `versions.lock`)

| Tool | Source | Pin |
|---|---|---|
| `rustc` | rustup, channel `stable` | exact version at start of work, recorded via `rustc --version --verbose` |
| `cargo` | rustup | matches `rustc` |
| SP1 | `succinctlabs/sp1` | version pinned in `tanujkhattar/zkp_ecc/Cargo.lock` |
| `sp1up` toolchain | `succinctlabs/sp1` | matches SP1 |
| Stwo | `starkware-libs/stwo` | specific commit SHA on `main`, recorded |
| Cairo | `starkware-libs/cairo` | version compatible with the pinned Stwo commit |
| `uv` | astral-sh release | ≥0.5, pinned by SHA-256 in `versions.lock` |
| Python | managed by `uv`, declared in `pyproject.toml` | `>=3.12,<3.14` |
| `hyperfine` | upstream release | ≥1.18 |
| `gnu-time` | brew (coreutils on macOS), apt on Linux | latest |

`versions.lock` is regenerated by `scripts/lock_versions.sh` and committed before any measured run.

### 5.2 Build invocation

Reference rig (macOS, arm64). Identical invocation on the Linux CI rig.

```bash
# SP1 side
git clone https://github.com/tanujkhattar/zkp_ecc.git sp1-side
( cd sp1-side && cargo build --release --bin example_zkp_prove )

# Stwo side
git clone https://github.com/starkware-libs/stwo.git
( cd stwo && git checkout <pinned-sha> && cargo build --release )

# Local Cairo translation
( cd stwo-side && cargo build --release )

# Python tooling (fixture generator + analysis scripts)
uv sync --frozen
```

Both Rust builds use `--release`. No `--features` flags beyond defaults unless required to disable a GPU or multi-thread default, in which case the flag is documented in `BUILD.md`. The Python environment is fully declared in `pyproject.toml` with a committed `uv.lock`; `uv sync --frozen` is the only entry point.

### 5.3 Stwo-side workload (what we write)

A Cairo program in `stwo-side/circuit.cairo` that:

1. Reads `fixtures/v0.1.json`, treating `T` and `H_C` (the Blake2s commitment) as public inputs.
2. Reads the gate-list encoding of `C` as the secret witness.
3. Implements the gate-by-gate semantics of `sim.rs`: NOT flips one bit, CNOT XORs one bit into another, Toffoli ANDs two control bits into a target bit.
4. For each test case `(x_i, y_i)` in `T`, sets the initial register state from `x_i`, applies `C`, and asserts the final register state equals `y_i`.
5. Computes Blake2s over the canonical serialisation of `C` and asserts equality with `H_C`.

Design parameters to settle before writing Cairo:

| Parameter | Decision |
|---|---|
| Base field | M31 (Mersenne-31), as Stwo natively requires |
| 256-bit element representation | 9 × 31-bit limbs (one limb of slack for carry handling) |
| Gate encoding | flat array of `(opcode: u8, target: u16, ctrl_a: u16, ctrl_b: u16)` tuples |
| `|C|` representation | fixed-length array, padded with no-op gates to a power of two |
| Bit-stripe handling | mirror what `sim.rs` does at the same `W` |
| Circuit commitment | Blake2s over the canonical byte serialisation of the gate-list array |
| Per-test-case state | bit-vector of width 256 (or width set by `sim.rs`), packed into 9 limbs |

### 5.4 SP1-side workload (what we modify minimally)

`example_zkp_prove.rs` is modified to:

1. Accept `fixtures/v0.1.json` as its only test-case source. The example's current internal SHA-2 XOF derivation of test cases is replaced by a deserialise-from-JSON path. No other logic changes.
2. Emit the proof to a path passed on the command line.

Patch lives in `sp1-side-patches/` as a single `.patch` file applied at build time. Net diff target: under 50 lines. Anything larger triggers escalation.

The SP1 verifier is unmodified and invoked through SP1's standard Groth16 verify entry point.

---

## 6. Fixtures (the apples-to-apples bridge)

### 6.1 Generator

A Python script at `python/grover_tax/gen_fixtures.py`, invoked via `uv run gen-fixtures`. Deterministic. No external network calls. Dependencies declared in `pyproject.toml` (stdlib `hashlib` plus `coincurve` for secp256k1 reference math); resolved by `uv` and locked in `uv.lock`. Type-checked under `mypy --strict`, linted under `ruff`.

Inputs to the generator (constants in the script, committed):

- `SEED = b"grover-tax-v0.1-2026-05"` (32 bytes after SHA-256 expansion)
- `N` = the value pinned in §3
- `W` = the bit-stripe width pinned in §3

### 6.2 Procedure

1. SHA-2 XOF on `SEED` yields a byte stream.
2. Consume the byte stream to produce `N` test-case inputs `x_i`. Each `x_i` is a tuple of two secp256k1 affine points `(P_i, Q_i)`.
3. Compute `y_i = P_i + Q_i` using `coincurve` as the reference adder. This is the ground truth.
4. Construct the gate-list `C` for the chosen secp256k1 point-add implementation. The gate list is the same gate list `sim.rs` emits when initialised for one point-addition.
5. Cross-validate: feed `C` and the `x_i` through a Python reimplementation of the `sim.rs` gate semantics. The output must equal `y_i` for every test case. If not, the Python reimplementation is wrong; do not adjust the fixtures, fix the reimplementation.
6. Compute `sha256(C_serialised)` and `blake2s(C_serialised)` using identical canonical serialisation.
7. Emit `fixtures/v0.1.json`.

### 6.3 Fixture schema

```json
{
  "version": "v0.1",
  "generator_commit": "<git sha of the repo at generation time>",
  "seed_hex": "...",
  "n_samples": 0,
  "bit_stripe_width": 0,
  "circuit_serialisation_format_version": 1,
  "circuit_byte_serialisation_hex": "...",
  "circuit_commitment_sha256_hex": "...",
  "circuit_commitment_blake2s_hex": "...",
  "test_cases": [
    {"x_hex": "...", "y_hex": "..."}
  ]
}
```

The full `C` byte serialisation is included so any third party can recompute both commitments independently.

### 6.4 The intentional divergence

SP1 binds to `circuit_commitment_sha256_hex`. Stwo binds to `circuit_commitment_blake2s_hex`. The underlying `circuit_byte_serialisation_hex` is bit-identical. Both verifiers therefore attest to the same circuit `C`. Only the binding hash differs.

This is the only deviation from full apples-to-apples in v0.1. Implementing SHA-2 in Cairo would dominate the Stwo wall-clock and confound the comparison. The choice of Blake2s over Poseidon is deliberate: Blake2s is in the same structural family as SHA-2 (bit-oriented, ARX-style) and Stwo Cairo has a Blake2s built-in, making the comparison closer in kind than Poseidon would be.

This divergence is documented in `RESULTS.md` and in the README headline.

---

## 7. Measurement specification

### 7.1 Metric set

| ID | Metric | Unit | Capture |
|---|---|---|---|
| M1 | Proof generation wall-clock | seconds | `hyperfine --warmup 1 --runs 10 --export-json` |
| M2 | Proof generation peak RSS | MiB | `gnu-time -v` field "Maximum resident set size" |
| M3 | Proof generation user CPU time | seconds | `gnu-time -v` field "User time" |
| M4 | Proof generation system CPU time | seconds | `gnu-time -v` field "System time" |
| M5 | Verifier wall-clock | milliseconds | `hyperfine --warmup 3 --runs 50 --export-json` |
| M6 | Proof file size | bytes | `stat -f %z` (macOS) / `stat -c %s` (Linux) |
| M7 | Trace rows / constraint count | count | prover stdout with `RUST_LOG=info` |
| M8 | Setup phase time (SP1+Groth16 only) | seconds | dedicated one-shot timing |
| M9 | Setup output size (proving + verifying key) | bytes | same `stat` invocation as M6 |
| M10 | Disk writes during proving | bytes | `iostat -d -w 1` (macOS) / `iostat -dxk 1` (Linux) sampled, integrated |

M10 is informational only and not part of the headline. It surfaces if either prover spills heavily to disk.

### 7.2 Capture script (`scripts/measure.sh`)

```bash
#!/usr/bin/env bash
set -euo pipefail

PROVER="$1"           # sp1 | stwo
RUN_ID="$2"           # epoch-ts + short hash
OUT="results/${PROVER}_v0.1_${RUN_ID}"
mkdir -p "$(dirname "$OUT")"

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

# M1: wall-clock distribution
hyperfine --warmup 1 --runs 10 --export-json "${OUT}.timing.json" "$PROVE_CMD"

# M2 M3 M4: representative single run under gnu-time
$TIME_BIN -v -o "${OUT}.time.txt" $PROVE_CMD

# M6: proof size
$STAT_CMD "${OUT}.proof" > "${OUT}.proof_size.txt"

# M7: trace + constraints scraped from a debug run
RUST_LOG=info $PROVE_CMD 2>&1 | tee "${OUT}.proverlog.txt"

# M5: verifier distribution
hyperfine --warmup 3 --runs 50 --export-json "${OUT}.verify.json" "$VERIFY_CMD"
```

### 7.3 Setup-cost capture (SP1 only)

`scripts/measure_setup.sh` runs the Groth16 trusted-setup phase once, captures wall-clock and key sizes (M8, M9), and writes `results/sp1_setup.json`. The setup cost is reported separately and is explicitly excluded from the headline proof-generation ratio. The headline reports it as a one-time structural cost.

### 7.4 Wrapper contract

`bin/run_sp1.sh` and `bin/run_stwo.sh` take exactly two positional arguments: `<fixtures.json> <output_proof_path>`. They exit 0 on success and non-zero on failure. Stdout is the prover's log. Stderr is reserved for measurement-side errors.

`bin/verify_sp1.sh` and `bin/verify_stwo.sh` take one positional argument: `<proof_path>`. They read the same `fixtures/v0.1.json` from a known relative path. Exit 0 means valid, non-zero means invalid. No human-readable output on stdout in the success path.

This symmetric contract makes the harness prover-agnostic.

---

## 8. Environmental hygiene

### 8.1 Power and thermal state (reference rig, macOS)

Before any measured run:

```bash
# Confirm AC power
pmset -g ps | grep -q "AC Power"

# Disable low-power mode
sudo pmset -b lowpowermode 0
sudo pmset -a lowpowermode 0

# Disable App Nap and automatic sleep during the run series
caffeinate -dimsu &
CAFFEINATE_PID=$!

# Disable Spotlight indexing on the working tree
sudo mdutil -i off "$(pwd)"
```

After the run series, reverse these. `scripts/preflight.sh` asserts the AC-power and low-power-mode states and exits non-zero on any failure.

macOS does not expose a kernel knob to disable Apple Silicon's dynamic frequency scaling. The harness compensates with the warmup run, the cool-down protocol in §8.3, and the discard rules in §8.4. The lack of hard frequency pinning is recorded in `RESULTS.md`.

### 8.1b Power and thermal state (Linux CI rig)

```bash
sudo cpupower frequency-set -g performance
echo 1 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo  # Intel
# On AMD:
# echo 0 | sudo tee /sys/devices/system/cpu/cpufreq/boost
```

`scripts/preflight.sh` asserts:

```bash
test "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)" = "performance"
test "$(cat /sys/devices/system/cpu/intel_pstate/no_turbo)" = "1"
```

### 8.2 Background-noise checklist (macOS reference rig)

- Quit browsers, Slack, IDEs, Docker Desktop, Xcode background services.
- `launchctl print user/$UID` to enumerate running user agents; stop any non-essential ones with `launchctl bootout`.
- Wi-Fi off (`networksetup -setairportpower en0 off`), Bluetooth off.
- Spotlight indexing disabled on the working tree (see §8.1).
- Time Machine paused for the run window.
- External displays disconnected (reduces unrelated GPU/IO activity).

### 8.3 Thermal protocol

- Cold-boot the laptop. Wait 5 minutes for background daemons to settle.
- Run one throwaway invocation of each prover. Discard.
- Measured series for SP1: 10 runs via hyperfine.
- 5-minute cool-down.
- Measured series for Stwo: 10 runs via hyperfine.
- During every measured run: sample temperatures via `sudo powermetrics --samplers smc -n 1 -i 1000` on macOS or `sensors` on Linux. Any P-core temperature reading above 95°C on Apple Silicon (or 90°C junction on x86) invalidates the run series.
- Day-2 repeat. If day-1 and day-2 medians differ by more than 5%, investigate before publishing.

### 8.4 Discard rules

A run is discarded if:

- Thermal sampling exceeded the threshold in §8.3.
- `powermetrics` reports non-zero GPU residency during the run window.
- Swap activity is non-zero (`sysctl vm.swapusage` on macOS, `/proc/swaps` on Linux).
- The first run of any series (cold cache), regardless of timing.

Discards are recorded with reason in `results/discards.log`.

---

## 9. Reporting

### 9.1 Headline table (in `RESULTS.md`)

| Metric | SP1+Groth16 | Stwo | Ratio (SP1 / Stwo) |
|---|---|---|---|
| Proof gen median (10 runs) | TBD s | TBD s | TBD× |
| Proof gen IQR | TBD s | TBD s | n/a |
| Verifier median (50 runs) | TBD ms | TBD ms | TBD× |
| Peak RSS | TBD MiB | TBD MiB | TBD× |
| Proof size | TBD bytes | TBD bytes | TBD× |
| Trace / constraints | TBD | TBD | n/a |
| Trusted setup required | yes (`E` s one-time, `F` MiB keys) | no | structural |

### 9.2 Distribution plots

`uv run plot` emits, committed to `results/plots/`:

- Histogram of proof-gen wall-clock per prover, overlaid.
- Bar chart of medians with IQR error bars across both provers and both metrics (proof gen, verify).
- A side-by-side day-1 / day-2 comparison for stability evidence.

### 9.3 Apples-to-apples disclosures

`RESULTS.md` includes a dedicated section listing every known divergence between the two sides:

1. Hash function for circuit commitment: SHA-256 (SP1) vs Blake2s (Stwo). Justification per §6.4.
2. Field choice: BabyBear (SP1) vs M31 (Stwo). Structural to the provers, not a knob.
3. Trusted setup: required for Groth16 wrap on SP1 side, absent on Stwo side. Reported separately, not folded into the headline ratio.
4. Thread fan-out: documented per-prover in `RESULTS.md` if either prover's user CPU time exceeds wall-clock time by more than 10% (indicating residual concurrency despite the env caps). Both provers must be reported on the same fan-out basis.

### 9.4 Reproduction recipe

`README.md` opens with:

> Reference rig: see `versions.lock`.
> Run `./scripts/run_all.sh`. Wall time approximately 25 minutes from a clean clone. Output lands in `RESULTS.md` and `results/`.

A 30-minute clean-clone-to-results time is a hard target. If `run_all.sh` exceeds 45 minutes on the reference rig, the workload size or measurement protocol must be revisited.

---

## 10. Repository layout

```
grover-tax/
├── README.md
├── WORKLOAD.md
├── BUILD.md
├── RESULTS.md
├── LICENSE                       # MIT
├── versions.lock
├── pyproject.toml                # uv-managed Python project
├── uv.lock
├── fixtures/
│   └── v0.1.json
├── python/
│   └── grover_tax/
│       ├── __init__.py
│       ├── gen_fixtures.py       # entry: `uv run gen-fixtures`
│       ├── sim_reference.py      # Python reimplementation of sim.rs semantics
│       ├── analyze.py            # entry: `uv run analyze`
│       └── plot.py               # entry: `uv run plot`
├── scripts/
│   ├── lock_versions.sh
│   ├── preflight.sh
│   ├── measure.sh
│   ├── measure_setup.sh
│   └── run_all.sh
├── bin/
│   ├── run_sp1.sh
│   ├── verify_sp1.sh
│   ├── run_stwo.sh
│   └── verify_stwo.sh
├── sp1-side/                     # git submodule of tanujkhattar/zkp_ecc
├── sp1-side-patches/
│   └── 0001-read-fixtures-from-json.patch
├── stwo-side/
│   ├── Cargo.toml
│   ├── circuit.cairo
│   ├── prover_main.rs
│   └── verifier_main.rs
└── results/
    ├── plots/
    ├── discards.log
    └── (JSON outputs from measure.sh)
```

### 10.1 Licensing

MIT for the repo root. SP1 and Stwo submodules retain their upstream licences. The Apache-2.0 / MIT compatibility check is run by `scripts/check_licenses.sh` and required by `run_all.sh` before any measurement begins.

### 10.2 Public repo discipline

Because the repo is MIT and public from day one:

- No commit touches `fixtures/v0.1.json` after the day-1 generation pass without a corresponding version bump.
- No commit touches `versions.lock` after the first measured run without invalidating the prior `results/`.
- `results/` history is preserved; bad runs are not deleted, they are moved under `results/archive/<date>/` with a `WHY.md` next to them.