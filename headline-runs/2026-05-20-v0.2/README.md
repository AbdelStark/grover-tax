# Headline run — 2026-05-20 (v0.2 apples-to-apples)

First end-to-end measurement series on the v0.2 statement (RFC-0015 §3.6):
both provers proving execution of the same 1024-gate XOF-derived
reversible classical circuit over a 256-bit bitvector state across
N = 4 test cases, with the disclosed SHA-256 vs Blake2s commitment
divergence (RFC-0005 / RFC-0019 §5).

Supersedes the 2026-05-14 headline. That earlier run measured the v0.1
*proxy* workload (byte-walk on the SP1 side, wide-Fibonacci AIR on the
Stwo side). The v0.2 run measures **the same statement on both sides**
— real gate execution per RFC-0015.

## Rig

- **Provider / shape:** GCP `c3-standard-8` in `europe-west1-b`
- **Instance:** `grover-tax-headline-r2-20260518-1625`
- **CPU:** Intel Xeon Platinum 8481C (Sapphire Rapids) @ 2.70 GHz
- **Cores visible:** 4 physical (SMT disabled via `--threads-per-core=1`)
- **RAM:** 31 GiB, 0 swap
- **OS:** Ubuntu 24.04 LTS, kernel 6.17
- **Single-core pinning:** `taskset -c 0` per RFC-0009
- **Env caps:** `RAYON_NUM_THREADS=1`, `TOKIO_WORKER_THREADS=1`,
  `OMP_NUM_THREADS=1`, `CUDA_VISIBLE_DEVICES=""`
- **Bypasses (cloud-VM artifacts):** `SKIP_GOVERNOR=1`,
  `SKIP_VERSIONS_DRIFT=1`
- **Repo HEAD:** `7499931` (sp1 verifier rewrite for v0.2 layout)
- **Fixture:** `fixtures/v0.2.json` (gen_fixtures HEAD `c5fff05` —
  1024 random gates, 4 test cases)
- **Run ID:** `1779201876-5afbdc2`

## Numbers

| Metric | SP1 (compressed STARK) | Stwo (Circle STARK) | Ratio (SP1 / Stwo) |
|---|---|---|---|
| **M1** prove median (n=10) | **753.065 s** ± 0.529 s | **298.755 s** ± 0.290 s | **2.52×** |
| M1 IQR | 0.388 s | 0.265 s | — |
| M1 min / max | 752.736 / 754.559 s | 298.429 / 299.338 s | — |
| M1 CoV | 0.07 % | 0.10 % | — |
| **M5** verify median (n=50) | **190.349 s** ± 0.110 s | **58.2 ms** ± 0.3 ms | **3270.21×** |
| Proof size | 1 272 609 B (1.21 MiB) | 15 543 804 B (14.82 MiB) | 0.082× |

The Stwo proof being **~12× larger** than the SP1 compressed-STARK proof
is the *bootloader-mediated* Cairo proof (RFC-0022 §2): bootloader trace
+ Cairo task trace are both committed. This is the price of the Cairo
bootloader pattern; a direct Stwo Cairo proof (without bootloader) is
the v0.3 target (`OPEN-Q-22-1`).

The Stwo *verify* taking **58 ms** versus SP1's 190 s is structural:
Stwo's Circle-STARK verifier is a small FRI commitment check; SP1's
verifier replays the proof through a *recursive STARK* on the verifier
circuit (`sp1-sdk::ProverClient::verify`). Two structurally different
verification algorithms running under the same RFC-0009 single-core
caps.

### Setup-vs-verify breakdown (added 2026-05-20 18:58 UTC)

Post-publication diagnostic (4 standalone runs against the same proof
artifact, instrumented via `SP1_VERIFIER_TIMING=1`) confirmed the
**190 s SP1 verify is dominated by cryptographic verify work, not by
deterministic key derivation**:

| Component | SP1 (single-threaded) | Stwo (single-threaded) |
|---|---|---|
| Deterministic VK setup (one-time per ELF) | ~5 s | ~0 ms |
| Verify cryptographic work (FRI + recursive STARK) | ~185 s | ~58 ms |
| Total M5 wall-clock | **190.349 s** | **58.2 ms** |

The 5 s setup is the `ProverClient::setup(ELF)` call, which is a
deterministic function of the ELF and can be cached once the
verifying key is derived (see commit `6236340` for the SP1 verifier's
`SP1_VK_CACHE` env var implementation). In a production deployment
that runs many verifies per ELF, the 5 s setup amortises to zero;
the per-verify cost stays at ~185 s under single-threaded
`RAYON_NUM_THREADS=1` and at ~50 s wall-clock with multi-threaded
rayon enabled (user-CPU ~170 s, ≈3.4× parallelism on the c3-standard-8).

The 3270× ρ_verify ratio is therefore **legitimate** at the
single-threaded measurement scope. It is *not* a setup artifact. v0.3
will split this into M5 (per-verify, repeatable) and M9 (one-time
setup) per RFC-0024 §2.10 amended by `docs/spec/v0.3/`.

1 cold-cache discard (Stwo, the expected D-INV-3). 0 thermal events,
0 swap, 0 GPU residency.

## Apples-to-apples disclosures (v0.2)

Per RFC-0015 + RFC-0018 + RFC-0019 + RFC-0020, the headline ratio
reflects two prover stacks proving the **same NP statement** `Φ_v0.2`
with the following disclosed divergences:

1. **Commitment hash.** SP1: SHA-256 (zkVM syscall, near-zero marginal
   trace cost). Stwo: BLAKE2s (Cairo builtin, ~2× more trace rows per
   input byte than SP1's syscall). RFC-0005 + RFC-0019 §5.
2. **Field choice.** SP1: BabyBear (31-bit). Stwo: M31 (31-bit). Both
   structural to their stacks, not tunable.
3. **Prover stack.** SP1: zkVM (RISC-V cycle model). Stwo:
   bootloader-mediated Cairo Circle STARK. The bootloader adds
   `B ≈ 55 000` fixed trace rows on the Stwo side (RFC-0022 §2). This is
   the principal reason for the proof-size asymmetry.
4. **Statement under proof.** Both: `Φ_v0.2` (RFC-0015 §3.6).
   For each `(x_i, y_i)` in the v0.2 fixture, both provers prove
   `simulate(parse_gtv1(circuit_bytes), x_i[:32]) == y_i[:32]` AND
   `H_*(circuit_bytes) == fixture.commitment` (with `H_SHA256` on SP1,
   `H_BLAKE2s` on Stwo, both over bit-identical `circuit_bytes`).
5. **Thread fan-out.** Both: `RAYON/TOKIO/OMP=1`, `taskset -c 0`,
   `CUDA_VISIBLE_DEVICES=""`. User-CPU / wall ratios: ~0.97 SP1,
   ~0.93 Stwo (single-threaded by construction).
6. **Trusted setup.** v0.2 default: compressed STARK on SP1 (no
   Groth16, no setup). Set `SP1_USE_GROTH16=1` for the Groth16 wrap
   (one-time ~20-45 min ceremony cost; not in this headline).

## Scope (v0.2)

What the proofs *say*:

- **SP1** (`third_party/sp1/program/src/main.rs`): zkVM program reads
  `circuit_bytes`, asserts SHA-256 match, parses `GTV1`, simulates
  every NOT/CNOT/TOFFOLI gate over the 256-bit state, asserts each
  test case's output. Commits `(SHA-256(circuit_bytes), n_cases)` as
  public values.
- **Stwo** (`stwo-side/cairo/src/lib.cairo::apples_to_apples_executable`):
  Cairo 1 program does the same — Blake2s commitment check, GTV1 parse,
  gate-by-gate simulation in M31 limbs, per-test-case state equality
  check. The bootloader proves this Cairo task end-to-end via
  `stwo-cairo run_and_prove` (RFC-0022 §2).

Neither side does GPU offload, neither side parallelises across cores,
and both are bound to the same fixture bytes. Per RFC-0018 §2 the work
performed on both sides is `c · n_tc · n_g + k · |cb| + b + B`. The
constant `c` differs by stack (~12 RISC-V cycles per gate × SP1 trace
density vs ~80 constraints per gate on the Stwo AIR), but the work is
linear in `n_tc · n_g = 4096` on both sides.

## Known gaps surfaced by this run

Listed in `docs/spec/v0.2/GAP-ANALYSIS.md`; the most important:

- `RESULTS.md` rendering: Peak RSS, proof-size, and trace/constraint
  rows show `0` because `analyze.py` does not yet parse `*.time.txt` /
  `*.proof_size.txt` / `*.proverlog.txt` into the template (RFC-0021
  §11 amends this). Raw data is present in `results/*.{time.txt,
  proof_size.txt, proverlog.txt}` for manual extraction.
- The verifier wrappers (`bin/verify_{sp1,stwo}.sh`) hard-code
  `fixtures/v0.1.json`; phase-6 of this session hot-patched them via
  `sed` to use `v0.2.json`. RFC-0021 §4 formally parameterises this
  via `FIXTURE_PATH` env var.
- `scripts/measure.sh` similarly hard-codes `v0.1.json` and required
  the same `sed` hot-patch. Same RFC-0021 §4 fix.
- The SP1 verifier source (`third_party/sp1/verifier/verifier.rs`) was
  v0.1-shaped on entry to this run (it expected 3 committed public
  values; v0.2 commits 2). Fixed inline in commit `7499931`.
- `bin/apples-verify` (RFC-0022 §5) is still missing. The v0.2
  measurement relies on `bin/verify_{sp1,stwo}.sh` calling the
  upstream verifier directly; the public-input cross-check obligations
  of RFC-0015 §3.7 / RFC-0019 §6.2 / RFC-0020 §3.2 are not yet
  programmatically enforced.

These are all v0.2 spec items (RFC-0021) not yet implemented as code;
this run validates that the *measurement* path works end-to-end on
the reference rig with the workarounds documented in `~/grover-tax-run.log`
on the GCE instance.

## Reproduction

```bash
# Provision (matches the 2026-05-14 rig spec):
gcloud compute instances create grover-tax-r3 \
  --zone=europe-west1-b \
  --machine-type=c3-standard-8 \
  --threads-per-core=1 \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=100GB --boot-disk-type=pd-ssd

# On the VM:
sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    hyperfine time jq build-essential pkg-config libssl-dev clang libclang-dev \
    golang-go protobuf-compiler cmake git curl ca-certificates tar
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | \
    sh -s -- -y --default-toolchain none --profile minimal
. "$HOME/.cargo/env"
rustup install 1.93.0 nightly-2025-07-14 --profile minimal
curl --proto '=https' --tlsv1.2 -sSf https://docs.swmansion.com/scarb/install.sh | \
    sh -s -- -v 2.15.1
curl -fsSL https://sp1up.succinct.xyz | bash && ~/.sp1/bin/sp1up
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$HOME/.sp1/bin:$PATH"

git clone https://github.com/AbdelStark/grover-tax.git
cd grover-tax
uv sync --frozen

# Hot-patches required by RFC-0021 §4 (not yet in main):
sed -i 's|fixtures/v0\.1\.json|fixtures/v0.2.json|g' \
    scripts/measure.sh bin/verify_sp1.sh bin/verify_stwo.sh

# Builds (in series; each can take 10-15 min on c3-standard-8):
(cd third_party/proving-utils && cargo +nightly-2025-07-14 build --release --locked -p stwo-run-and-prove)
(cd third_party/sp1 && cargo +1.93.0 build --release)
cargo +nightly-2025-07-14 build --release --locked -p stwo-side
scarb --manifest-path stwo-side/cairo/Scarb.toml build

# Smoke + measurement:
RUN_ID="$(date -u +%s)-$(git rev-parse --short HEAD)"
CUDA_VISIBLE_DEVICES= RAYON_NUM_THREADS=1 TOKIO_WORKER_THREADS=1 \
OMP_NUM_THREADS=1 SKIP_GOVERNOR=1 SKIP_VERSIONS_DRIFT=1 \
HYPERFINE_PROVE_RUNS=11 HYPERFINE_VERIFY_RUNS=50 \
  bash scripts/measure.sh stwo "${RUN_ID}"
sleep 300  # cool-down
CUDA_VISIBLE_DEVICES= RAYON_NUM_THREADS=1 TOKIO_WORKER_THREADS=1 \
OMP_NUM_THREADS=1 SKIP_GOVERNOR=1 SKIP_VERSIONS_DRIFT=1 \
HYPERFINE_PROVE_RUNS=11 HYPERFINE_VERIFY_RUNS=50 \
  bash scripts/measure.sh sp1 "${RUN_ID}"
uv run analyze && uv run plot && uv run check-results-md RESULTS.md
```

Expected wall time on a c3-standard-8: ~1 hour Stwo (M1 + M5) +
~5 hours SP1 (M1 + M5) ≈ ~6 hours measurement, plus ~1 hour for
toolchain installs and builds. **~7 hours total** on a clean clone,
**~$3.20** of compute at on-demand pricing.

## Artifacts

```
RESULTS.md                  rendered report
results/
  discards.log              jsonl, 1 entry (cold_cache stwo, the expected D-INV-3)
  sp1_v0.1_<RUN_ID>.timing.json    hyperfine M1 (11 runs)
  sp1_v0.1_<RUN_ID>.verify.json    hyperfine M5 (50 runs)
  sp1_v0.1_<RUN_ID>.time.txt       gnu-time -v (M2/M3/M4)
  sp1_v0.1_<RUN_ID>.proverlog.txt  prover stdout/stderr (CONSTRAINTS:/TRACE_ROWS:)
  sp1_v0.1_<RUN_ID>.proof.bin      1.21 MiB compressed STARK proof
  sp1_v0.1_<RUN_ID>.proof_size.txt M6
  stwo_v0.1_<RUN_ID>.*             mirror set for Stwo (proof = 14.82 MiB)
  stwo_v0.1_<RUN_ID>.iostat.json   M10 informational
  plots/                            wallclock_hist.png, medians_bar.png, day1_day2.png
fixtures/v0.2.json          the v0.2 fixture (1024-gate XOF-derived circuit)
scripts/measure.sh          v0.1-fixture-path hot-patched to v0.2 (see above)
bin/verify_{sp1,stwo}.sh    same hot-patch
bin/run_{sp1,stwo}.sh       wrapper contracts (unchanged)
```

The `1779201876-5afbdc2` run-ID suffix encodes the start epoch and the
repo HEAD when the series began (`5afbdc2`); the verifier source fix
landed at `7499931` mid-run, but the existing M1 proof remained
verifiable under the rebuilt verifier (phase-6 parity check passed).

## Status against RFC-0015..RFC-0022

This run is *compliant* with RFC-0015 (proof statement) at the program
level: both sides prove `Φ_v0.2`. It is *partially compliant* with
RFC-0016 / RFC-0017 (the constant-cost-per-gate tests C16-T8 / S17-T8
are not yet implemented). It is *not yet compliant* with RFC-0021 (the
spec hardening: lockfile commit, fixture-path env var, M7 grammar from
real prover, methodology-lint extensions L1-L6, Mann-Kendall trend
detection, bootstrap-CI stability gate). Per RFC-0019 §2.4 the
soundness floor is met by both stacks' upstream defaults.
