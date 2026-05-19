# RFC-0021 — Reproducibility Hardening

| Field | Value |
|---|---|
| Status | Accepted |
| Amends | RFC-0002, RFC-0007, RFC-0008, RFC-0009, RFC-0010, RFC-0011, RFC-0012, RFC-0013, `04-error-model.md`, `03-data-model.md`, schemas |
| Audience | implementers, CI maintainers, reproducers |

## 1. Committed lockfiles for every measurement-path workspace

**Problem.** `third_party/proving-utils/Cargo.lock` is currently `.gitignore`'d. A reproducer who clones after a transitive dep is bumped will build a different prover backend than the reference rig built — observed empirically on 2026-05-18 when `ruint` bumped from `1.17.2` to `1.18.0`, breaking the `nightly-2025-07-14` build.

**Amendment.**
1. Remove `third_party/proving-utils/Cargo.lock` from `.gitignore`.
2. Commit the current working `Cargo.lock` (the one that succeeded against the pinned nightly toolchain).
3. All measurement-path builds MUST use `cargo build --locked --release` (not just `cargo build --release`).
4. Add a CI job `lockfile-completeness` that asserts no measurement-path workspace has a missing or untracked `Cargo.lock`.
5. Amend `BUILD.md` to instruct re-locking only when a deliberate bump is proposed via PR.

**Test.** `T21-1`: `git ls-files third_party/proving-utils/Cargo.lock` MUST list the file.

## 2. Methodology-lint extensions

**Amendment.** `python/grover_tax/check_results_md.py` MUST also assert:

- (`L1`) Presence of the "Operations-counted footprint" section (RFC-0018 §4) with the row for `c · n_tc · n_g`, `k · |cb|`, `b`, `B` (bootloader), and totals.
- (`L2`) Presence of the "Commitment-cost asymmetry" disclosure (RFC-0019 §5.4) with the constraint-counted ratio between SHA-256 and BLAKE2s contributions.
- (`L3`) Presence of the soundness-floor declaration (RFC-0019 §2): "Both proofs at conjectured 100-bit soundness."
- (`L4`) Presence of the bootloader Pedersen disclosure (RFC-0022 §3): "Stwo's bootloader uses Pedersen as program_hash_function..."
- (`L5`) Presence of `apples-verify` cross-check confirmation: "All public inputs verified against fixture; substitution attack precluded."
- (`L6`) `n_runs ≥ 10`, `n_warmup ≥ 1` from `*.timing.json`.

Failure of any of `L1`–`L6` produces an exit code `6` with subcode `REPORT.METHODOLOGY_LINT_FAIL`.

## 3. `versions.lock` schema and content additions

Add the following fields to `versions-lock-v1.schema.json` and `lock_versions.sh`:

| Path | Type | Source | New? |
|---|---|---|---|
| `host.os_build` | string | `sw_vers -buildVersion` (macOS) / `uname -r` (Linux) | yes (resolves OPEN-Q-12.1) |
| `sp1.sdk_version` | string | `sp1-sdk` crate version from `third_party/sp1/Cargo.lock` | yes |
| `sp1.toolchain_sha256` | string | `shasum -a 256 ~/.sp1/bin/cargo-prove` | yes |
| `sp1.program_elf_sha256` | string | `shasum -a 256 third_party/sp1/target/elf-compilation/*/zkp_ecc-program/zkp_ecc-program` | yes |
| `sp1.fri_params` | object `{blowup, num_queries, grinding_bits}` | from `sp1-sdk@6.0.2`'s default config | yes |
| `stwo.commit` | string (40-char hex) | `git -C third_party/stwo-cairo rev-parse HEAD` | normative (existing) |
| `stwo.circle_fri_params` | object `{blowup, num_queries, grinding_bits}` | from stwo-cairo's default config | yes |
| `groth16.ceremony_url` | string (URL or `content-hash:<sha256>`) | per ceremony provenance | yes (replaces RFC-0011's free-form string) |
| `proving_utils.cargo_lock_sha256` | string | SHA-256 of `third_party/proving-utils/Cargo.lock` | yes |
| `scarb.version` | string | `scarb --version` | yes |

`preflight.sh` MUST drift-check every field. A missing or differing field aborts with `MEASUREMENT.VERSIONS_DRIFT`.

**Test.** `T21-3.a` regenerates `versions.lock`; `T21-3.b` corrupts each new field; `T21-3.c` re-runs preflight and asserts the exit code.

## 4. Fixture path parameterised

**Amendment.** `scripts/measure.sh`, `bin/verify_*.sh`, and `bin/run_*.sh` MUST read `FIXTURE_PATH` from environment, defaulting to `fixtures/v0.2.json`:

```bash
FIXTURE_PATH="${FIXTURE_PATH:-fixtures/v0.2.json}"
```

`preflight.sh` MUST assert `jq -e '.version | startswith("v0.")' < "${FIXTURE_PATH}"` and reject any pre-v0.2 fixture (sets the lower bound for the v0.2 measurement window).

**Test.** `T21-4`: a wrong-version fixture path produces exit code 5 with `MEASUREMENT.FIXTURE_VERSION_DRIFT`.

## 5. M7 grammar from real prover output

**Amendment.** `bin/apples-prove` MUST stop synthesising `CONSTRAINTS:` and `TRACE_ROWS:` from `gate_count`. The two lines MUST be parsed from:

- **SP1:** `sp1-sdk`'s `ExecutionReport` printed at `RUST_LOG=info`. The prover binary (`prove.rs`) MUST emit `CONSTRAINTS: <total_constraint_count>` and `TRACE_ROWS: <total_trace_row_count>` after the prove call, using the values from `report.total_instruction_count()` and `report.total_syscall_count()` mapped via the SP1 SDK's documented formula.
- **Stwo:** `stwo-cairo run_and_prove`'s component-summary log line (`Component sizes:` followed by per-component row counts). `bin/apples-prove` MUST parse and sum the row counts, then emit the two M7 lines.

`bin/run_sp1.sh::enforce_proverlog_grammar` and `bin/run_stwo.sh::enforce_proverlog_grammar` then verify "exactly one of each" as today.

**Test.** `T21-5`: M7 values in `*.proverlog.txt` MUST be ≥ 1000 for any non-degenerate v0.2 run; absurdly small values fail the test (defence-in-depth against A_statement).

## 6. Within-series trend detection

**Amendment.** `python/grover_tax/analyze.py` MUST run a two-sided Mann-Kendall trend test on the 10 measured M1 samples per prover. If `p < 0.01`, the section in `RESULTS.md` for that prover gains a `[WARMING_TREND]` flag and the confidence rating drops from `A` (CoV ≤ 5%) to `B` (CoV ≤ 10% or trend detected).

**Test.** `T21-6`: synthesise 10 monotonically increasing samples; assert flag fires. Synthesise 10 i.i.d. samples; assert flag does not fire.

## 7. macOS affinity-class assertion dropped

**Amendment.** RFC-0007 and RFC-0009's macOS affinity-class read (via `pmset -g`, `sysctl kern.osproductversion`) is **deleted**. The wrappers no longer attempt to verify the QoS class of the running process (no public macOS API supports it).

Instead, the macOS wrappers MUST:
1. Invoke the prover via `taskpolicy -c utility -- <prover_binary> ...` (preserved).
2. Record the `taskpolicy` invocation in the per-run log: `echo "[wrapper] launched via: taskpolicy -c utility ..." >&2`.
3. Document the irreducible affinity gap in `RESULTS.md` (RFC-0011, unchanged from v0.1's macOS gap disclosure).

`MEASUREMENT.AFFINITY_MISS` on macOS becomes a soft warning (logged but not aborting), as the precondition cannot be enforced.

**Test.** `T21-7`: the wrapper invocation log MUST contain the `taskpolicy -c utility` prefix on macOS; the Linux wrapper MUST contain `taskset -c 0`.

## 8. `iostat.json` schema

Add `docs/spec/schemas/iostat-v1.schema.json`:

```jsonc
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "iostat-v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["prover", "run_id", "samples"],
  "properties": {
    "prover":  {"enum": ["sp1", "stwo"]},
    "run_id":  {"type": "string"},
    "samples": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["t_unix", "kb_read", "kb_wrtn"],
        "properties": {
          "t_unix":   {"type": "number"},
          "kb_read":  {"type": "number", "minimum": 0},
          "kb_wrtn":  {"type": "number", "minimum": 0}
        }
      }
    }
  }
}
```

`analyze.py` MUST validate `results/*.iostat.json` against this schema.

## 9. `os_build` field — see §3.

## 10. `discards-v1.schema.json` enum extension

Amend the `reason` enum to add:

```
"affinity_miss",
"soundness_floor_breach",
"public_input_mismatch",
"ops_footprint_deviation"
```

Each subcode corresponds to an error in §17.

## 11. Day-1 / day-2 stability — bootstrap CI

**Amendment.** `analyze.py` replaces the point-estimate 5% delta check with a bootstrap confidence interval:

1. Resample 1000 bootstrap medians from each of day-1 and day-2 samples.
2. Compute the 95% CI of `(median_d1 - median_d2) / median_d1` (the delta ratio).
3. **Gate condition:** the CI MUST include 0 *or* MUST be entirely below `0.05`. If the CI is entirely above `0.05`, the run series fails the stability gate.

The `RESULTS.md` template (RFC-0011) gains a "Day-2 stability CI" row showing the interval.

**Test.** `T21-11`: synthesise day-1 / day-2 with known delta; assert the CI is computed correctly.

## 12. `SOURCE_DATE_EPOCH` + reproducible-builds tightening

**Amendment.** RFC-0013's "`SOURCE_DATE_EPOCH` not set" is replaced with:

```bash
export SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)
```

Set in `scripts/measure.sh` and inherited by every `cargo build`. Where the pinned toolchain supports it, add `--codegen-units=1 -C strip=debuginfo`. Tier-1 (byte-stable) Rust binaries become a v0.2 *aspiration*: if achievable on the pinned toolchain, the build is byte-stable; if not, document the gap.

**Test.** `T21-12`: build the SP1 prover twice on the same host; SHA-256 of the resulting binaries MUST match.

## 13. Reference-rig equivalence-class definition

**Amendment.** `docs/spec/06-security.md::§"Reference rig"` (or new section in `09-release-and-versioning.md::§"Equivalence"`) defines:

> Two rigs are in the same **reference equivalence class** iff they share: (a) CPU SKU (`sysctl machdep.cpu.brand_string` exact match), (b) physical core count, (c) installed RAM (MiB exact), (d) firmware version (`system_profiler SPHardwareDataType | grep "System Firmware Version"`).

`versions.lock::host` MUST record all four fields. A reproducer whose values match is in the equivalence class. A reproducer whose values differ is in a *neighbouring class* and the ±5% tolerance of Tier-3 is the operational guarantee.

## 14. macOS version locking — see §13.

## 15. v0.1 → v0.2 schema additive bump

**Amendment.** A v0.3 may narrow `x_hex` from 128 to 64 hex chars (dropping the unused trailing 32 bytes). For v0.2 the schema stays at 128 chars; the prover ignores the trailing 32 bytes per RFC-0015 §3.5. Glossary entry "C (the circuit)" is amended to reflect v0.2's "public 1024-gate random circuit, not point-add".

## 16. RFC-0002 XOF disambiguation

**Amendment.** RFC-0002's pseudocode `ShakeXOF` is normative; the "SHA-2 XOF" language in A4 is retracted. SHAKE-256 from FIPS 202 is the v0.2 XOF for fixture generation. `gen_fixtures.py` MUST use `hashlib.shake_256(SEED).digest(N)`.

## 17. `04-error-model.md` extension

Add the following subcodes:

| Subcode | Category | Exit code | Trigger |
|---|---|---|---|
| `PROVER.PUBLIC_INPUT_MISMATCH` | PROVER | 1 | `apples-verify` finds proof-public-values ≠ fixture-derived |
| `MEASUREMENT.SOUNDNESS_FLOOR_BREACH` | MEASUREMENT | 5 | `preflight.sh` computes < 100-bit conjectured soundness |
| `MEASUREMENT.OPS_FOOTPRINT_DEVIATION` | MEASUREMENT | 5 | methodology lint finds `rows_measured` outside ±5% of `rows_predicted` |
| `MEASUREMENT.FIXTURE_VERSION_DRIFT` | MEASUREMENT | 5 | wrong-version fixture path |
| `BUILD.SP1_TOOLCHAIN_DRIFT` | BUILD | 3 | `versions.lock::sp1.toolchain_sha256` mismatch |
| `BUILD.GROTH16_KEY_DRIFT` | BUILD | 3 | Groth16 SRS SHA-256 mismatch |
| `REPORT.METHODOLOGY_LINT_FAIL` | REPORT | 6 | any of L1-L6 fails (§2) |

## 18. CODEOWNERS hardening

**Amendment.** `.github/CODEOWNERS` MUST require maintainer review on:

```
/third_party/sp1/program/    @AbdelStark @<second-reviewer>
/third_party/sp1/prover/     @AbdelStark @<second-reviewer>
/stwo-side/cairo/src/        @AbdelStark @<second-reviewer>
/docs/spec/v0.2/             @AbdelStark @<second-reviewer>
/docs/rfcs/                  @AbdelStark @<second-reviewer>
/bin/                        @AbdelStark @<second-reviewer>
/scripts/measure*.sh         @AbdelStark @<second-reviewer>
```

The `<second-reviewer>` is a placeholder; OPEN-Q-14.1 (RFC-0014) tracks the trigger for assigning it. v0.2 ships with single-maintainer review on these paths and accepts the documented limitation.

## 19. Implementation issues

Each amendment in this RFC is filed as a GitHub issue under `docs/roadmap/IMPLEMENTATION.md::v0.2`:

| RFC-0021 § | Issue |
|---|---|
| §1 (lockfile) | `#v0.2-21-1` |
| §2 (lint extensions) | `#v0.2-21-2` |
| §3 (`versions.lock` schema) | `#v0.2-21-3` |
| §4 (FIXTURE_PATH) | `#v0.2-21-4` |
| §5 (M7 from real prover) | `#v0.2-21-5` |
| §6 (Mann-Kendall) | `#v0.2-21-6` |
| §7 (macOS affinity) | `#v0.2-21-7` |
| §8 (iostat schema) | `#v0.2-21-8` |
| §10 (discards enum) | `#v0.2-21-10` |
| §11 (bootstrap CI) | `#v0.2-21-11` |
| §12 (SOURCE_DATE_EPOCH) | `#v0.2-21-12` |
| §13 (equivalence class) | `#v0.2-21-13` |
| §15 (glossary) | `#v0.2-21-15` |
| §16 (SHAKE-256 disambig) | `#v0.2-21-16` |
| §17 (error model) | `#v0.2-21-17` |
| §18 (CODEOWNERS) | `#v0.2-21-18` |
