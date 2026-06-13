# Grover-tax STWO Bench

This directory is a benchmark harness for experimenting with STWO on the
`grover-tax` repeated-addition fixtures.

It contains two paths:

- `cairo/iadd256_loop.cairo`, a small Cairo-0 add-heavy smoke workload for the
  STWO-Cairo `gpu_bench` binary.
- `native-air/`, a standalone native STWO AIR for the `v0.3-iadd`
  fixture semantics.

The benchmark expects this repository to sit beside local `stwo` and
`stwo-cairo` checkouts:

```text
parent/
  grover-tax/
  stwo/
  stwo-cairo/
```

Override paths in `config.env` if your checkout layout is different.

Run commands in this file from `benchmarks/stwo/iadd256/` unless stated
otherwise.

## Setup

Fetch the external `zkp_ecc` checkout used for KMX parsing and simulator
equivalence checks:

```bash
./scripts/setup_external.sh
```

When this directory is used inside `grover-tax`, `setup_external.sh` uses the
parent checkout instead of cloning `grover-tax` again. If the parent checkout is
not present, it falls back to `external/grover-tax`.

## Fixture Generation

The small committed fixtures are enough for smoke checks. Generate the full
`iadd256`, `k8000/n9024` target locally when you need the large benchmark:

```bash
cd ../../..
uv run gen-iadd-fixtures \
  --repetitions 8000 \
  --samples 9024 \
  --circuit iadd256.kmx \
  --tier T8000 \
  --out fixtures/v0.3-iadd256-k8000-n9024.json
cd benchmarks/stwo/iadd256
```

Run the generator in `--check` mode to verify an existing generated fixture:

```bash
cd ../../..
uv run gen-iadd-fixtures \
  --repetitions 8000 \
  --samples 9024 \
  --circuit iadd256.kmx \
  --tier T8000 \
  --out fixtures/v0.3-iadd256-k8000-n9024.json \
  --check
cd benchmarks/stwo/iadd256
```

The generated large fixture is deliberately not committed here; benchmark data
belongs in PR notes or run reports, not in the source diff.

## STWO-Cairo Runner

Compile the add workload:

```bash
./scripts/compile_workload.sh iadd256
```

Build `gpu_bench` from the configured `stwo-cairo` checkout:

```bash
./scripts/build_gpu_bench.sh
```

Run a small SIMD smoke test:

```bash
BACKENDS=simd NS="1 10" REPS=1 ./scripts/run_ladder.sh iadd256
```

Run the intended add ladder on CUDA and SIMD:

```bash
BACKENDS="cuda simd" NS="1 10 100 1000 2000 4000 8000" REPS=3 \
  ./scripts/run_ladder.sh iadd256
```

Run the EC comparison ladder:

```bash
BACKENDS="cuda simd" NS="256 1024" REPS=3 ./scripts/run_ladder.sh ec
```

The runner writes JSONL plus a markdown summary under `results/`. Those files
are ignored by git.

## Native AIR Runner

Run a small exact-fixture proof:

```bash
cd native-air
cargo +nightly-2025-07-14 run --release
```

Run the sound lookup-backed range-check mode and compare against the upstream
KMX simulator:

```bash
cd native-air
cargo +nightly-2025-07-14 run --release -- \
  --fixture ../../../../fixtures/v0.3-iadd256-k4-n16.json \
  --range-check lookup \
  --check-kmx \
  --kmx-check-samples 4
```

Run a sampled ladder against the generated full target:

```bash
FIXTURE=../../../fixtures/v0.3-iadd256-k8000-n9024.json \
SAMPLES="64 128 256 512" \
RANGE_CHECK=lookup \
./scripts/run_native_iadd_air.sh
```

Native runner knobs:

- `RANGE_CHECK=off|bits|lookup` selects compact mode, bit-decomposition range
  checks, or the lookup-backed range-check path.
- `STORE_COEFFICIENTS=1` trades memory for faster proving.
- `LOW_MEMORY=1` enables STWO's low-memory decommit path.
- `CHECK_KMX=1` runs the upstream `iadd256.kmx` parser/simulator equivalence
  check.

## Notes

- CUDA runs need a CUDA-capable Linux host and the CUDA toolchain expected by
  the configured `stwo-cairo` checkout.
- On a non-CUDA host, use `BACKENDS=simd`.
- On macOS, treat STWO-Cairo `peak_rss_gb` as a correctness smoke signal only;
  the current `gpu_bench` RSS field assumes Linux `getrusage(ru_maxrss)` units.
