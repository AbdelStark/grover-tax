# grover-tax v0.2 — Gap Analysis

**Status:** normative input to RFC-0015 through RFC-0022.
**Audience:** cryptographic reviewers, prover-stack implementers, methodology auditors.
**Authoring basis:** exhaustive read of `PRD.md`, `SPEC.md`, the 14 RFCs (RFC-0001..RFC-0014), the 11 spec sections (`docs/spec/00-overview.md` ... `10-glossary.md`), the four JSON Schemas under `docs/spec/schemas/`, `docs/apples-to-apples-v0.1.md`, `docs/apples-to-apples-status.md`, `docs/roadmap/IMPLEMENTATION.md`, the current v0.2 implementation under `stwo-side/cairo/src/`, `third_party/sp1/program/src/main.rs`, `third_party/sp1/prover/prove.rs`, and `bin/apples-prove`. Cross-checked against the 2026-05-14 headline run report.

This document *names* every gap, drift, ambiguity, and silent assumption. It does not propose normative fixes — each fix is filed in an RFC under `docs/rfcs/RFC-0015..RFC-0022`. The disposition column says where each issue is resolved.

---

## 1. Specification-vs-implementation drift

The corpus was authored against the v0.1 *gate-execution* design (RFCs 0003, 0004, 0006). v0.1 then shipped a *mod-add proxy* (`apples-to-apples-v0.1.md`), and v0.2 (commit `c5fff05`) reverted to gate-execution — but with a different gate set, a different witness shape, a different prover-side architecture, and a different bootloader path. The RFC corpus describes none of these.

| # | Gap | Evidence | Disposition |
|---|---|---|---|
| 1.1 | The "proof statement" in `docs/spec/00-overview.md`, `02-public-api.md`, `RFC-0003`, `RFC-0004`, `03-data-model.md::F-INV-4/5`, and `PRD.md::§2` is "existence of a reversible classical circuit `C` over `{NOT, CNOT, Toffoli}` that realises one secp256k1 point-addition such that `C(x_i) = y_i`." The actual v0.2 statement is "for the gate list deserialised from `circuit_bytes` and for each `(x_i, y_i)` in `test_cases`, simulating the gates over the 256-bit state initialised from the first 32 bytes of `x_i` yields the first 32 bytes of `y_i`." The circuit no longer realises point-addition — it is a random 1024-gate XOF-derived circuit. | `apples-to-apples-v0.1.md` ("byte-walk... *Not point-add semantics*"); v0.2 commit body; `lib.cairo:194-263`; `third_party/sp1/program/src/main.rs:24-43`. | RFC-0015 (proof statement). |
| 1.2 | F-INV-4 in `03-data-model.md` asserts `sim_reference.py(C, x_i) == y_i` *and* F-INV-5 asserts `coincurve.add(P_i, Q_i) == y_i`. The v0.2 implementation deletes F-INV-5 (no point-add) and keeps F-INV-4 only on the first 32 bytes of `x_i`. The fixture schema (`fixture-v0.1.schema.json`) is unchanged and still references a structure for which F-INV-5 is normative. | `sim_reference.py` version-aware `_verify_fixture` (per v0.2 commit body); `fixtures/v0.2.json` still ships `x_hex` at 128 chars. | RFC-0015 §3, schema bump in RFC-0021. |
| 1.3 | `x_hex` is 128 hex chars (64 bytes) and described as "two compressed secp256k1 affine points (P, Q)". In v0.2 the prover only consumes the **first 32 bytes** (`x_bytes[:32]`). The remaining 32 bytes are unused witness bytes carried for backward schema compatibility. No RFC says this. | `third_party/sp1/program/src/main.rs:38` (`x: [u8; 32]`); `lib.cairo:227-235`. | RFC-0015 §4 (witness shape); explicit deprecation of trailing 32 bytes. |
| 1.4 | The SP1 patch surface is RFC-0006-budgeted at <50 lines as a `.patch` against the upstream `tanujkhattar/zkp_ecc` example. The actual SP1 program is a freshly authored ~130-line `main.rs` at `third_party/sp1/program/src/main.rs`, with no relation to the upstream example. The "<50-line patch" constraint was bypassed by replacing the file outright in a vendored copy. | `third_party/sp1/program/src/main.rs` (no patch lineage). | RFC-0017 (formally retires the patch-budget model). |
| 1.5 | RFC-0004's Cairo gate-dispatcher specifies a constant-cost `step` function with constraint-counted branches. The v0.2 `gates.cairo`/`io.cairo` implementation has not been audited against RFC-0004's constraint-shape claim (no test enforces "all four opcodes consume the same trace rows"). | RFC-0004 §"`step` function"; current `gates.cairo` (read but not formally checked against the claim). | RFC-0016 §6 (constraint-shape obligations and test V-T*). |
| 1.6 | The Stwo "prover" surface used by `bin/run_stwo.sh` is no longer `stwo-side/src/bin/prover_main.rs`. It is `bin/apples-prove`, which drives `third_party/proving-utils/target/release/stwo-run-and-prove` with a `simple_bootloader_compiled.json` task running the scarb-built `grover_tax_executable.executable.json`. The RFC corpus contains no description of this bootloader-mediated path. | `bin/run_stwo.sh:68-79`; `bin/apples-prove:67-156`. | RFC-0022 (bootloader integration). |
| 1.7 | The 2026-05-14 headline run measured Stwo proving a *wide-Fibonacci AIR* "sized proportionally to `gate_count`", not the apples-to-apples statement at all. `apples-to-apples-status.md` records this. No RFC formally connects a wide-Fibonacci AIR to any apples-to-apples target. The headline number that exists in the repo today (33 644×) is not measuring the v0.2 statement. | `apples-to-apples-status.md`; `gce-headline-r1/RESULTS.md`. | RFC-0018 (operations-counted equivalence) and RFC-0020 (threat model adversary "different statement under proof"). |

---

## 2. Cryptographic and security-property gaps

The corpus declares which divergences it accepts (commitment hash, field choice, trusted setup) but does not provide a formal statement of *what* is held constant across the two stacks, nor the soundness/zk parameters of either prover.

| # | Gap | Evidence | Disposition |
|---|---|---|---|
| 2.1 | **No soundness parameter is stated for either stack.** SP1's compressed-STARK soundness depends on its FRI parameters (blowup factor, num queries, grinding bits). Stwo Circle-STARK soundness depends on the analogous parameters. The headline claim "both provers prove the same statement" is meaningful only at a stated soundness level. | None — no statement anywhere in the corpus. | RFC-0019 §2 (soundness floor: both stacks ≥ 100 bits conjectured). |
| 2.2 | **No zero-knowledge claim is stated or scoped.** v0.1 carried the language "without revealing the gate-list of `C`" (`PRD.md::§2`). v0.2's `circuit_byte_serialisation_hex` is *published in the fixture*, so the gate list is not secret. Neither SP1 nor Stwo's v0.2 program treats it as a witness — both deserialise it from public input. The proofs are arguments of knowledge for a public statement, not ZK. The glossary entry "Zero-knowledge proof" remains in place. | `fixtures/v0.2.json::circuit_byte_serialisation_hex`; `third_party/sp1/program/src/main.rs:25` (`read_vec` then `commit`). | RFC-0019 §3 (formally remove the ZK claim from the headline; retain ZK aspirations as future work). |
| 2.3 | **Commitment-divergence cost is asserted as 0.05–0.1% with no source.** RFC-0005's "Drawbacks" paragraph quotes this number with no derivation. The required `RESULTS.md` "breakdown row" is not lint-enforced (RFC-0011's `check_results_md.py` only checks section presence). The cost asymmetry is potentially material: SP1's SHA-256 is a zkVM syscall (~zero marginal STARK cost); Stwo's Blake2s is real circuit computation by the Blake2s builtin. | RFC-0005 §"Drawbacks". | RFC-0019 §5 (quantitative commitment-cost analysis); RFC-0011 amendment in RFC-0021 §2. |
| 2.4 | **Verifier acceptance is the unverified contract.** `bin/verify_*.sh` is required to exit 0 on a valid proof, but the harness does no independent re-check of the public inputs. A prover whose verifier wrongly accepts an unrelated proof would be measured as "fast" without detection. RFC-0014's "trust upstream verifiers" stance is correct as scope but does not protect against this specific class of bias. | `bin/verify_sp1.sh`, `bin/verify_stwo.sh`; RFC-0014 §"Threat model". | RFC-0020 §3 (adversary "honest prover, lenient verifier"); RFC-0019 §6 (verifier-equivalence statement). |
| 2.5 | **Mod-p reduction algorithm was unspecified** (v0.1). Now obsolete for v0.2 but flagged for record. | (historical) | Resolved by v0.2's removal of mod-p; this gap is closed. |
| 2.6 | **The Blake2s parameter set in-circuit is "default" but never normatively pinned.** Blake2s admits digest-length, key, salt, and personalization parameters; Python `hashlib.blake2s` and the Cairo `commit_blake2s` builtin must agree on all four. The fixture commits to a 32-byte digest with no key/salt/personalization, but the spec only constrains the digest length. | RFC-0004 §"in-circuit Blake2s"; `commit.cairo` (asserted; not read in this analysis). | RFC-0019 §5.2 (full Blake2s parameter pin: `BLAKE2s-256(input, key="", salt=0..0, personal=0..0)`). |
| 2.7 | **SHA-256 padding length is implicitly trusted.** The SP1 zkVM ingests `circuit_bytes` of length 16 400 bytes (1024 gates × 8 bytes + 8-byte header). SP1's patched SHA-256 syscall handles padding internally; the Python generator uses `hashlib.sha256(circuit_bytes).hexdigest()`. These must produce identical 32-byte digests for any GTV1 byte string. This is an implicit equivalence; no test pins it. | None. | RFC-0019 §5.1 (hash-equivalence test vector). |
| 2.8 | **No adversary model for "prover proves a different (but verifier-accepted) statement."** RFC-0014's threat model defends against fixture/toolchain/PR tampering. It does not consider a prover whose circuit constrains a *weaker* statement than claimed while still emitting a verifier-accepting proof. This is exactly the failure mode of the 2026-05-14 wide-Fibonacci stand-in. | RFC-0014; `apples-to-apples-status.md`. | RFC-0020 (full extended threat model). |
| 2.9 | **The SP1 toolchain installer (`sp1up`) is not provenance-verified.** `versions.lock` pins `uv.sha256`, `rustc.version`, and the Stwo commit, but the SP1 prover binary depends on an `sp1up`-installed toolchain whose binary hash is not pinned anywhere. A supply-chain compromise of `sp1up`'s distribution channel can replace the SP1 prover backend without changing any committed file. | `BUILD.md` reproduction recipe; `RFC-0012` schema. | RFC-0021 §3 (SP1 toolchain SBOM + SHA-256 pin). |
| 2.10 | **The `third_party/proving-utils/Cargo.lock` is `.gitignore`'d.** Without a committed lock file, every fresh clone resolves dependency versions from `crates.io` at the time of `cargo build` — the v0.2 GCE run on 2026-05-18 broke because `ruint` resolved to 1.18.0 which requires a newer nightly than the pinned `nightly-2025-07-14`. Reproducibility is silently broken for any user who clones after a transitive dep is bumped. | `.gitignore:third_party/proving-utils/Cargo.lock`; observed CI failure 2026-05-18 (this session). | RFC-0021 §1 (mandatory committed lockfile for every Cargo workspace consumed during measurement). |

---

## 3. Measurement methodology gaps

| # | Gap | Evidence | Disposition |
|---|---|---|---|
| 3.1 | **`scripts/measure.sh` hard-codes `fixtures/v0.1.json`** despite v0.2 shipping `fixtures/v0.2.json`. Any GCE run picks up the wrong fixture unless an operator hand-patches `measure.sh`. | `scripts/measure.sh:96` (verified by direct read). | RFC-0021 §4 (fixture-path env var + version assertion). |
| 3.2 | **M7 (`CONSTRAINTS:` / `TRACE_ROWS:`) is wrapper-emitted, not prover-emitted.** `bin/apples-prove` post-processes `gate_count` and emits the two lines as a sentinel for the wrapper grammar. For Stwo, the *real* trace row count is the bootloader trace row count plus the apples-to-apples sub-trace, not `gate_count`. For SP1, the constraint count is the SP1 zkVM's per-cycle constraint count summed over the executed cycles, not `gate_count`. The reported M7 is therefore not a measure of either prover's constraint system size. | `bin/apples-prove:163-171`. | RFC-0021 §5 (extract M7 from the actual prover's stdout grammar). |
| 3.3 | **The hyperfine `--runs 11` measurement (1 warmup + 10 measured) discards only the cold-cache first run.** If the prover has within-series JIT warmup beyond the first run (e.g., cargo-incremental, page-cache pre-warming, lazy-static initialisation), measurements 2..5 will be biased. The discard rule covers `cold_cache` only and does not flag a warming trend. | RFC-0010 §"Discards"; `scripts/measure.sh:113-117`. | RFC-0021 §6 (within-series trend detector: Mann-Kendall on the 11 timing samples). |
| 3.4 | **Verifier wrapper `bin/verify_*.sh` reads `fixtures/v0.1.json` from cwd**, hard-coded. v0.2 cannot use the v0.2 fixture unless renamed. | `bin/verify_stwo.sh:17`. | RFC-0021 §4 (same as 3.1). |
| 3.5 | **`macOS affinity check** described in RFC-0007/RFC-0009 (using `pmset -g` and `sysctl kern.osproductversion`) does not actually verify the process QoS class.** No public macOS API exposes a process's QoS class to user-space. The `MEASUREMENT.AFFINITY_MISS` enforcement on macOS is unimplementable as written. | RFC-0007 §"Preconditions"; RFC-0009 §"Enforcement". | RFC-0021 §7 (drop macOS affinity-class assertion; replace with `taskpolicy -c utility` invocation provenance + thread-cap caps). |
| 3.6 | **The `iostat.json` artifact has no schema.** `05-observability.md` lists it; `03-data-model.md` does not. `analyze.py` cannot validate it. | `docs/spec/schemas/` directory; verified by `ls`. | RFC-0021 §8 (add `iostat-v1.schema.json` and a normative reference). |
| 3.7 | **`os_build` field was resolved as "add it" in OPEN-Q-12.1 but never added to `versions-lock-v1.schema.json`.** | `SPEC.md::OPEN-Q-12.1`; `docs/spec/schemas/versions-lock-v1.schema.json`. | RFC-0021 §9 (add field, regenerate `versions.lock`). |
| 3.8 | **`discards-v1.schema.json::reason` enum is missing `affinity_miss`.** The error model has `MEASUREMENT.AFFINITY_MISS`; the discards schema cannot record it without losing precision (falls back to `env_var_miss` or `other`). | Direct read of `discards-v1.schema.json`. | RFC-0021 §10. |
| 3.9 | **Day-1 / day-2 stability gate fires on a 5% median delta but the variance of the delta is not stated.** With n=10 per series and known IQR floor, a 5% delta on a high-variance run is within the sampling noise of the *delta itself*. The gate is a point estimate without an interval. | RFC-0008 §"Stability gate"; RFC-0010 §"Day-2". | RFC-0021 §11 (Bayesian or bootstrap interval for the delta; gate fires only when CI excludes 0% by more than the threshold). |

---

## 4. Reproducibility-envelope gaps

| # | Gap | Evidence | Disposition |
|---|---|---|---|
| 4.1 | **`SOURCE_DATE_EPOCH` is unset by design**, so Rust binaries are not bit-stable across reproducer hosts. RFC-0013 accepts this and claims "binary bytes do not affect measured numbers." This is an *empirically reasonable* but *not formally verified* assumption — LLVM codegen order can differ when hash maps are seeded differently. | RFC-0013 §"Build hygiene". | RFC-0021 §12 (require `SOURCE_DATE_EPOCH` plus `cargo build --reproducible` flag where toolchain supports). |
| 4.2 | **The "reference rig equivalence class" is defined only by example.** What attributes constitute "equivalence"? Same chip + same memory channel + same firmware version? RFC-0013 lists "M4 Max, 48 GB, AC power" but a 14-core M4 Max binned variant has different sustained P-core clocks than a 16-core variant. | RFC-0013 §"Reproducer's checklist". | RFC-0021 §13 (formal equivalence-class definition: chip SKU + core count + memory size + firmware version). |
| 4.3 | **macOS 26.2 is referenced** in `10-glossary.md` and the versions-lock schema as the reference rig OS. macOS 26 is a future release; results from a different macOS major version may not reproduce. | `10-glossary.md`; observed in scout's report. | RFC-0021 §14 (lock `os_build` precisely; document the macOS-version equivalence policy). |

---

## 5. Architectural / API gaps

| # | Gap | Evidence | Disposition |
|---|---|---|---|
| 5.1 | **The bootloader path is an unspecified dependency.** `bin/apples-prove` invokes `stwo-run-and-prove` with a `SimpleBootloaderInput` whose `tasks` list contains a `Cairo1Executable` task pointing at the scarb-built `grover_tax_executable.executable.json`. The bootloader's own AIR, the cost of bootloader cycles, and the way bootloader output is glued to public inputs is nowhere described. | `bin/apples-prove:84-156`. | RFC-0022 §2 (full bootloader integration spec). |
| 5.2 | **The bootloader's `program_hash_function: "Pedersen"` choice is undocumented.** Pedersen is a Stark-friendly hash; using it inside the bootloader doesn't directly contradict RFC-0005's "Blake2s only" but it does mean the *bootloader* commitment is Pedersen — a fact that should be disclosed in `RESULTS.md`. | `bin/apples-prove:124-129`. | RFC-0019 §5.3 + RFC-0022 §3. |
| 5.3 | **The Stwo-side `apples_to_apples_executable` returns `1` for success but the proof's public output is the AP-region serialisation of `(circuit_bytes, expected_commitment, n_tc, test_cases)`.** The bootloader proves a task with this entire input as public input. The *verifier* on the wrapper side does *not* check that the public input matches what the fixture says — it only checks that the proof verifies (which the prover did inline). A standalone verifier reading only the proof binary cannot reject a proof whose public input came from a different fixture. | `lib.cairo:194-263` (returns `1`); `bin/apples-prove:153` (inline verify only). | RFC-0019 §6 (verifier-side public-input cross-check) + RFC-0022 §4 (proof carries public-input hash). |
| 5.4 | **The SP1 prover emits `(commitment, n_cases)` as committed public values** but the test-case inputs (`x_i`, `y_i`) are zkVM stdin, not committed. The verifier knows only `(commitment, n_cases)`. If a prover honestly runs the gate simulation against test cases that *aren't* in the fixture but commit to the same circuit hash, the proof would still verify. | `third_party/sp1/program/src/main.rs:25-31`. | RFC-0019 §6 (commit hash of all test-case bytes, not just circuit bytes); RFC-0017 §4. |
| 5.5 | **No `bin/apples-verify` exists** despite commit `d4045d8` claiming "add apples-verify binary". The binary is missing from `bin/`. | `bin/` listing (verified by `ls`). | RFC-0022 §5 (canonical verify path). |

---

## 6. Documentation / glossary gaps

| # | Gap | Evidence | Disposition |
|---|---|---|---|
| 6.1 | **Glossary `C`, `Reference rig`, and `Zero-knowledge proof` entries reflect the v0.1 design.** | `docs/spec/10-glossary.md`. | RFC-0015 (text); RFC-0021 (glossary update). |
| 6.2 | **No "What's new in v0.2" anywhere.** A reproducer reading the spec corpus cannot tell which RFCs are still load-bearing. | All RFC headers — no `Supersedes`/`Superseded-by` field. | RFC-0015..RFC-0022 use `Supersedes:` headers; the v0.2 spec adds a status table. |
| 6.3 | **The `SEED` literal `b"grover-tax-v0.1-2026-05"`** encodes a year-month that is the *project's authoring date*, not a generation date. A re-pin in v0.3 may or may not bump it; the policy is undefined. | RFC-0002 §"SEED". | RFC-0021 §15. |
| 6.4 | **RFC-0002's pseudocode uses `ShakeXOF`** (SHAKE-256) while RFC-0002 A4 claims SHA-2 XOF, and `IMPLEMENTATION.md::#12` says SHAKE-256. This is an internal contradiction within RFC-0002 itself. | RFC-0002 §"Algorithm" and §"A4". | RFC-0021 §16 (formal pin: SHAKE-256, retire SHA-2 XOF language). |

---

## 7. Summary disposition table

| RFC (new) | Resolves gap IDs |
|---|---|
| RFC-0015 (v0.2 proof statement) | 1.1, 1.2, 1.3, 6.1, 6.2 |
| RFC-0016 (Cairo gate-execution AIR for Stwo) | 1.5 |
| RFC-0017 (SP1 gate-execution zkVM program) | 1.4, 5.4 |
| RFC-0018 (operations-counted equivalence) | 1.7, 2.8 (partial) |
| RFC-0019 (soundness, ZK, and binding) | 2.1, 2.2, 2.3, 2.6, 2.7, 5.2, 5.3, 5.4 |
| RFC-0020 (extended threat model) | 2.4, 2.8 |
| RFC-0021 (reproducibility hardening) | 2.9, 2.10, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.1, 4.2, 4.3, 6.3, 6.4 |
| RFC-0022 (bootloader integration + verify) | 1.6, 5.1, 5.2, 5.3, 5.5 |

Every issue catalogued above has a target RFC. No gap is intentionally left open. Where v0.2 closes a v0.1 gap (e.g., 2.5), the row is marked as resolved-by-implementation; where v0.2 *opens* a new gap (e.g., 2.10, 3.2, 5.1–5.5), the RFC normalises it.
