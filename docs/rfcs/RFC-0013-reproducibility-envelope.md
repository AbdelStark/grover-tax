# RFC-0013: Reproducibility envelope

- Status: Accepted
- Authors: maintainer
- Created: 2026-05-13
- Target milestone: v0.1

## Summary

This RFC defines what "reproducible" means for `grover-tax` at `v0.1`: which artifacts are byte-stable, which are number-stable, which are merely distribution-stable, and what build-time settings the harness depends on. Reproducibility is layered; the layers are explicit.

## Motivation

"Reproducible" is a word that misleads if used unqualified. A benchmark that produces "the same numbers" in two senses — bit-identical files vs statistically-equivalent distributions — has very different reproducibility properties. The PRD assumes reproducibility throughout; this RFC names the layers so a reproducer knows what to expect.

## Goals

- Define the three reproducibility tiers.
- Specify, per artifact, which tier applies.
- Specify the build-time settings the harness controls.
- Specify what is *not* reproducible and why.

## Non-Goals

- Full bootstrappable builds (e.g., bootstrappable Rust). Out of scope.
- Cryptographic attestation of build provenance (Sigstore, SLSA-3). Out of scope; see `OPEN-Q-13.1`.
- Cross-OS byte-identical builds. macOS and Linux produce different binaries; this is expected.

## Proposed Design

### Tier 1 — byte-stable (bit-identical between runs)

| Artifact | How |
|---|---|
| `fixtures/v0.1.json` | Deterministic generator (`RFC-0002`); same `SEED` and `WORKLOAD.md` → same bytes |
| `versions.lock` | Pretty-printed with sorted keys; differs only on `generated_at`, `generator_commit` |
| `docs/spec/*.md`, `docs/rfcs/*.md`, `SPEC.md`, etc. | Source files |
| `tests/python/fixtures/digest_vectors.json` | Authored static |
| `results/plots/*.png` | `plot.py` is deterministic; same inputs → same PNGs (locked matplotlib version, fixed RNG seeds) |

Tier 1 artifacts are required to be byte-stable. CI's `gen-fixtures --check` is the gate for `fixtures/v0.1.json`. Plot byte-stability is asserted by `R-T6` in `RFC-0011`.

### Tier 2 — number-stable (same numbers across runs, possibly different binary representation)

| Artifact | How |
|---|---|
| `RESULTS.md`-derived statistics (median, IQR, stddev for a fixed input) | Statistics are deterministic given the same `results/*.json` |
| Constraint count, trace rows (M7) | Deterministic given the same prover binary and fixture |
| Proof file size (M6) | Generally deterministic; if not, the proof itself has hidden non-determinism and we flag it |

Tier 2 artifacts may differ in encoding (whitespace, field order) but the *numbers* are identical given the same inputs.

### Tier 3 — distribution-stable (statistically equivalent, not byte-identical)

| Artifact | How |
|---|---|
| `results/*.timing.json` | Wall-clock timings are noisy; the distribution (median, IQR) should reproduce within the day-1/day-2 stability gate (≤ 5%) |
| `results/*.time.txt` (peak RSS, user/sys CPU) | Same |
| The proof artifact itself (the bytes of `*.proof`) | Provers may include randomness in their proofs; verifier accepts but bytes differ |

Tier 3 is the irreducible layer: this is the noise the benchmark *exists* to measure. Reproducibility here is "statistical equivalence within a published noise envelope", not "byte equality".

### Build-time settings the harness controls

- `cargo build --release`. No `--features` overrides unless required to disable GPU or multi-thread defaults (in which case documented in `BUILD.md`).
- `RUSTFLAGS=""` (default). We do not set `-C target-cpu=native` or similar that would couple the binary to the build host's CPU.
- `SOURCE_DATE_EPOCH` not set. We do not pursue bit-stable Rust binaries across hosts — `cargo` does not guarantee it, and the binary's bytes do not affect measured numbers.
- `LANG=C LC_ALL=C` exported by `scripts/run_all.sh` to neutralise locale-dependent text output.
- `TZ=UTC` exported by `scripts/run_all.sh` so timestamps in logs are UTC.

### What is *not* reproducible in `v0.1`

| Item | Why |
|---|---|
| Rust binary bytes (`sp1-side/target/release/example_zkp_prove`) | `cargo` does not guarantee determinism; not needed for headline reproducibility |
| Proof file bytes | Some provers include randomness |
| `gnu-time` exact RSS digit | Sampling jitter; we report the rounded MiB |
| Verifier wall-clock exact ns | Noise; distribution reported |

Future-work items toward stronger reproducibility:

1. Use `SOURCE_DATE_EPOCH` and `cargo --locked` aggressively; verify Rust binary bit-stability.
2. Adopt Nix flake (`RFC-0012.A1`).
3. SLSA-3 attestation of build provenance.

These are not in scope for `v0.1`.

### Reproducer's checklist

A third party can reproduce the headline numbers within the published noise envelope if and only if:

1. They use the toolchain matrix recorded in `versions.lock`.
2. They run on hardware in the same equivalence class as the reference rig (M4 Max, 48 GB, AC power). The Linux CI rig is a separate equivalence class; results are not interchangeable.
3. They follow the hygiene protocol of `RFC-0010` (preflight, thermal cool-down, day-1/day-2).
4. Their results land within ±5% of the published medians (the day-1/day-2 envelope).

Beyond ±5%: investigate environment differences (Spotlight indexing, IDE running, Wi-Fi on, low-power mode). Not all reproducers will achieve ±5%; that is informational, not a defect.

### Bit-stable mode for fixture pipeline

`gen-fixtures` is byte-stable. The `--check` flag asserts. CI runs `--check` on every PR. This is the strongest form of reproducibility in the project and is non-negotiable: a fixture drift is a project-level defect.

### Tooling pins for byte-stability

- Python: `python = ">=3.12,<3.14"`. Within this range, deterministic stdlib operations have been bytewise-stable across micro-versions in our experience. CI runs against both 3.12 and 3.13 to surface accidental dependencies.
- `matplotlib`: pinned exact version in `uv.lock`. Changing it requires re-asserting plot byte-stability (`R-T6`).
- `jq`: pinned in `versions.lock`. Used for `versions.lock` formatting.

## Alternatives Considered

### A1. Demand byte-stable Rust binaries

Pros: would close a remaining reproducibility gap.

Cons:
- Rust does not guarantee deterministic builds; `cargo` has documented sources of non-determinism (e.g., parallel compilation order).
- `SOURCE_DATE_EPOCH` and `--locked` help but do not fully close the gap.
- The binary's bytes do not affect the measured numbers. Investment is high; payoff is low.

Rejected.

### A2. Demand byte-stable proof artifacts

Pros: every reproducer would get identical proofs.

Cons:
- Both SP1 and Stwo may include randomness in proofs (Fiat-Shamir input variations, optional commitments to randomness). The verifier accepts; the bytes differ.
- Forcing determinism would require modifying upstream provers, exceeding the `RFC-0006` patch budget.

Rejected.

### A3. SLSA-3 attestation

Pros: gold-standard supply-chain reproducibility.

Cons:
- Requires GitHub Actions runners signing artifacts.
- Heavy ceremony; not justified for a one-shot benchmark release.

Rejected for `v0.1`; potential `v1.0` agenda item.

## Drawbacks

- Tier 3 ("distribution-stable") is the layer most readers care about, and we cannot promise tight reproduction outside the reference-rig equivalence class. Honesty wins here: we state the limitation.
- The reproducer's burden of running day-1/day-2 is real. We cannot lower it without weakening the noise envelope.

## Migration / Rollout

First-time. Some Tier 1 guarantees (plot byte-stability) will be deferred to a follow-up commit once `matplotlib` is wired in; the test exists but is initially skipped with a TODO. The skip is removed before the `v0.1.0` tag.

## Testing Strategy

- **Rp-T1**: `gen-fixtures` byte-stability (covered by `RFC-0002.F-T1`).
- **Rp-T2**: `versions.lock` byte-stability under same toolchain (covered by `RFC-0012.V-T1`).
- **Rp-T3**: `plot.py` byte-stability (covered by `RFC-0011.R-T6`).
- **Rp-T4**: `analyze.py` deterministic statistics: same `results/*.json` → same `RESULTS.md` (modulo `generated_at` and `analyze_commit`).
- **Rp-T5**: Cross-day stability gate behaviour (covered by `RFC-0010.H-T7`).
- **Rp-T6**: Locale neutrality: invoking `run_all.sh` with `LANG=fr_FR.UTF-8` produces the same output as `LANG=C` (after the script's own override).

## Open Questions

**OPEN-Q-13.1** — When does this project graduate to SLSA-3 / Sigstore? Likely a `v1.0` agenda item if the benchmark is widely cited. Owner: maintainer. Resolution target: post-`v0.1`.

**OPEN-Q-13.2** — Should we publish the *reference rig's* binary builds as release artifacts so reproducers can compare timings against a known-binary, not just a known-source? Currently no — source-build is more honest. Owner: maintainer. Resolution target: post-`v0.1`.

## References

- `docs/spec/02-public-api.md` (output contracts)
- `docs/spec/09-release-and-versioning.md` (stability commitments)
- `RFC-0001` (workload pin is the upstream side of reproducibility)
- `RFC-0002` (fixture byte-stability)
- `RFC-0011` (plot byte-stability)
- `RFC-0012` (versions.lock)
- PRD `PRD.md` §5.2
