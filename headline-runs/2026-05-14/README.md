# Headline run — 2026-05-14

First end-to-end measurement series on a real cloud rig. Captured by
`scripts/run_all.sh` driving `bin/run_{sp1,stwo}.sh` against the
vendored SP1 (compressed STARK) and the in-tree Stwo (Circle STARK)
binaries; sample counts per RFC-0008.

## Rig

- **Provider / shape**: GCP `c3-standard-8` in `europe-west1-b`
- **CPU**: Intel Xeon Platinum 8481C (Sapphire Rapids) @ 2.70 GHz
- **Cores visible**: 4 physical (SMT disabled via `--threads-per-core=1`)
- **RAM**: 31 GiB, **0 swap**
- **OS**: Ubuntu 24.04 LTS, kernel 6.17
- **Single-core pinning**: `taskset -c 0` per RFC-0009
- **Env caps**: `RAYON_NUM_THREADS=1`, `TOKIO_WORKER_THREADS=1`,
  `OMP_NUM_THREADS=1`, `CUDA_VISIBLE_DEVICES=""`
- **Bypasses** (cloud-VM artifacts): `SKIP_GOVERNOR=1` (GCE doesn't
  expose `/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor`),
  `SKIP_VERSIONS_DRIFT=1` (versions.lock not yet committed, #7).

## Numbers

| Metric | SP1 (compressed STARK) | Stwo (Circle STARK) | Ratio (SP1 / Stwo) |
|---|---|---|---|
| **M1** prove median (n=10) | 751.603 s ± 0.396 s | 0.022 s ± 0.0005 s | **33 644×** |
| M1 min / max | 750.781 / 752.158 s | 22.094 / 23.763 ms | — |
| M1 CoV | **0.05 %** | 2.2 % | — |
| **M5** verify median (n=50) | 190.032 s | 3.56 ms | **53 381×** |
| M2 gnu-time wall (one canonical run) | 12 m 31.64 s | 0.02 s | — |
| Peak RSS during prove | **17.1 GiB** | 4.76 MB | ~3600× |
| Proof size | 1 272 625 B (1.21 MiB) | 10 557 B (10.3 KiB) | 121× |
| user-CPU / wall-clock | 0.97 | 0.5 | — |

Total measure-time on the rig: **5 h 8 m 44 s** ($2.24 of compute).
0 thermal events. 0 swap. 0 GPU residency. 1 cold-cache discard
(`stwo`, the expected D-INV-3). methodology lint: ✅ PASS.

## Scope (v0.1 MVP)

What the proofs *say*:

- **SP1**: a Groth16-able compressed STARK that SP1's zkVM read
  `circuit_byte_serialisation_hex`, committed `SHA-256(circuit_bytes)`,
  and ran a byte-by-byte state walk over the gate list. The fixture's
  `circuit_commitment_sha256_hex` is verified against the prover's
  output.
- **Stwo**: a Circle STARK over a wide-Fibonacci AIR
  (`FIB_SEQUENCE_LENGTH = 100` columns, `log_n_rows = 10` rows =
  `gate_count = 1024`).

Neither side proves a literal secp256k1 point-addition in v0.1; both
sides do work proportional to `gate_count`. The headline ratio
therefore reflects "the cost of generic STARK work on this trace
size" on each stack, not "the cost of proving point-add". A `v0.2`
that swaps both sides to a real point-add AIR is the next milestone.

See `RESULTS.md` §"Apples-to-apples disclosures" §4.

## Known gaps surfaced by this run (now tracked)

- `analyze.py` does not yet parse `*.time.txt` / `proof_size.txt` /
  `proverlog.txt` into the template's M2/M3/M4/M6/M7 fields, so the
  rendered RESULTS.md shows `0 MiB / 0 bytes / 0 constraints` for
  those rows. The raw data are present in `results/`; populating the
  template is a small follow-up.
- The discards table renders the totals but not the per-reason
  breakdown.
- Linear-y plots compress Stwo to zero pixels. A `--log` switch on
  `plot.py` is a v0.2 polish item.

## Reproduction

```bash
# On a fresh Ubuntu 24.04 box with public Internet:
curl -L https://sp1up.succinct.xyz | bash && ~/.sp1/bin/sp1up
rustup install 1.93.0 nightly-2025-07-14
sudo apt-get install -y hyperfine time jq build-essential pkg-config \
    libssl-dev clang libclang-dev golang-go protobuf-compiler cmake
git clone --recurse-submodules https://github.com/AbdelStark/grover-tax.git
cd grover-tax
uv sync --frozen
(cd third_party/sp1 && cargo +1.93.0 build --release)
cargo +nightly-2025-07-14 build --release -p stwo-side

CUDA_VISIBLE_DEVICES= RAYON_NUM_THREADS=1 TOKIO_WORKER_THREADS=1 \
OMP_NUM_THREADS=1 SKIP_GOVERNOR=1 SKIP_VERSIONS_DRIFT=1 \
HYPERFINE_PROVE_RUNS=11 HYPERFINE_VERIFY_RUNS=50 \
  bash scripts/measure.sh stwo r1
CUDA_VISIBLE_DEVICES= RAYON_NUM_THREADS=1 TOKIO_WORKER_THREADS=1 \
OMP_NUM_THREADS=1 SKIP_GOVERNOR=1 SKIP_VERSIONS_DRIFT=1 \
HYPERFINE_PROVE_RUNS=11 HYPERFINE_VERIFY_RUNS=50 \
  bash scripts/measure.sh sp1 r1
uv run analyze && uv run plot && uv run check-results-md RESULTS.md
```

Expected wall time: ~5 h 10 m on a c3-standard-8-equivalent (mostly
SP1 prove + verify; Stwo is < 1 minute total).

## Artifacts

```
RESULTS.md                  the rendered report
results/
  discards.log              jsonl, one entry per discard (only cold_cache stwo)
  sp1_v0.1_r1.timing.json   hyperfine M1 (11 runs)
  sp1_v0.1_r1.verify.json   hyperfine M5 (50 runs)
  sp1_v0.1_r1.time.txt      gnu-time -v on one canonical run (M2/M3/M4)
  sp1_v0.1_r1.proverlog.txt prover stdout/stderr (CONSTRAINTS:/TRACE_ROWS:)
  sp1_v0.1_r1.proof.bin     1.21 MiB compressed STARK proof (verifier-accepted)
  sp1_v0.1_r1.proof_size.txt M6 (one line, byte count)
  sp1_v0.1_r1.iostat.json   M10 informational
  stwo_v0.1_r1.*            mirror set for Stwo
  plots/
    wallclock_hist.png      overlaid M1 histograms (linear-y, Stwo invisible)
    medians_bar.png         M1 + M5 bars with IQR error bars
    day1_day2.png           placeholder (single-day run)
```
