# Build

Builds `grover-tax` and both prover backends from a clean clone.

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| `git` | 2.30+ | submodules |
| `uv` | 0.9.18 (pinned by `versions.lock`) | Python deps |
| `cargo` / `rustc` | 1.94+ (pinned by `versions.lock`) | Rust crates |
| `scarb` | 2.15+ | Cairo for `stwo-side/cairo/` |
| `hyperfine` | 1.18+ | measurement (M1, M5) |
| `gtime` (macOS) / `/usr/bin/time` (Linux) | GNU 1.9+ | measurement (M2/M3/M4) |
| `jq` | 1.6+ | JSON helpers |
| `sp1up` (optional) | matched in `versions.lock` | SP1 build toolchain |

On macOS: `brew install hyperfine gnu-time jq scarb`. On Ubuntu:
`apt install hyperfine time jq` plus `scarb` via its own installer.

## One-line full build

```bash
./scripts/run_all.sh --skip-measure
```

That runs every step up through `cargo build --release` and `gen-fixtures`,
then exits before the timed series. Adequate for verifying a clean checkout
boots.

## Step-by-step

```bash
# 1. Submodules + Python deps.
./scripts/init_submodules.sh
uv sync --frozen

# 2. SP1 patch + build.
./scripts/apply_sp1_patch.sh
(cd sp1-side && cargo build --release)

# 3. Stwo build (Rust workspace + Cairo).
cargo build --release -p stwo-side
(cd stwo-side/cairo && scarb build)

# 4. Fixture + validation.
uv run gen-fixtures
uv run python -m grover_tax.validate_schemas fixtures/v0.1.json
```

## SP1 setup (passwordless sudo, macOS)

The GPU-residency probe uses `sudo -n powermetrics`. One-time setup:

```bash
echo "$(whoami) ALL=(root) NOPASSWD: /usr/bin/powermetrics" | \
  sudo tee /etc/sudoers.d/grover-tax-powermetrics
```

## Headline run (reference rig only)

```bash
./scripts/run_all.sh --day 1
# cool the rig (≥ 1 hour, fan returned to idle)
./scripts/run_all.sh --day 2
uv run analyze   # produces RESULTS.md
```

## Re-pinning upstreams

A submodule SHA bump is an RFC-0001 minor or major project bump. See
`docs/rfcs/RFC-0001-workload-pinning.md` §"Re-pinning".
