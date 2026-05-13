# Implementation Tracker — 2026-05-13

Generated from the spec corpus committed in [PR #1](https://github.com/AbdelStark/grover-tax/pull/1). Every implementable unit of work in the spec is filed below. Each issue is independently shippable; cross-issue dependencies are noted inline and as comments on each issue.

Milestone for the entire v0.1 issue set: [`v0.1`](https://github.com/AbdelStark/grover-tax/milestone/1).

## Milestone: v0.1

### Build / toolchain / reproducibility (`area:build`)

| # | Title | Priority | Effort | RFC | Status |
|---|---|---|---|---|---|
| [#3](https://github.com/AbdelStark/grover-tax/issues/3) | build: WORKLOAD.md template + check_workload.sh CI gate | p0 | s | RFC-0001 | open |
| [#4](https://github.com/AbdelStark/grover-tax/issues/4) | build: source-read upstream zkp_ecc to fill WORKLOAD.md | p0 | m | RFC-0001 | open |
| [#5](https://github.com/AbdelStark/grover-tax/issues/5) | build: pin sp1-side and stwo as git submodules | p0 | s | RFC-0006, RFC-0014 | open |
| [#6](https://github.com/AbdelStark/grover-tax/issues/6) | build: lock_versions.sh + versions-lock-v1 JSON schema | p0 | m | RFC-0012 | open |
| [#7](https://github.com/AbdelStark/grover-tax/issues/7) | build: commit initial versions.lock from reference rig | p0 | s | RFC-0012 | open |
| [#8](https://github.com/AbdelStark/grover-tax/issues/8) | build: locale neutrality, matplotlib pin, deterministic plots | p1 | s | RFC-0013 | open |
| [#9](https://github.com/AbdelStark/grover-tax/issues/9) | build: bootstrap pyproject.toml, uv.lock, Cargo workspace | p0 | s | RFC-0002, RFC-0014 | open |

### Fixture pipeline (`area:fixture`)

| # | Title | Priority | Effort | RFC | Status |
|---|---|---|---|---|---|
| [#10](https://github.com/AbdelStark/grover-tax/issues/10) | fixture: grover_tax package scaffolding (errors, workload, paths) | p0 | m | RFC-0002 | open |
| [#11](https://github.com/AbdelStark/grover-tax/issues/11) | fixture: canonical byte serialiser (Python) for gate list | p0 | m | RFC-0002 | open |
| [#12](https://github.com/AbdelStark/grover-tax/issues/12) | fixture: deterministic XOF wrapper (SHAKE-256) | p0 | s | RFC-0002 | open |
| [#13](https://github.com/AbdelStark/grover-tax/issues/13) | fixture: secp256k1 reference math wrapper (coincurve) | p0 | s | RFC-0002 | open |
| [#14](https://github.com/AbdelStark/grover-tax/issues/14) | fixture: author fixture-v0.1 + setup-v1 + discards-v1 schemas | p0 | m | RFC-0002, RFC-0011 | open |
| [#15](https://github.com/AbdelStark/grover-tax/issues/15) | fixture: implement sim_reference.py (gate semantics + BitVector) | p0 | m | RFC-0003 | open |
| [#16](https://github.com/AbdelStark/grover-tax/issues/16) | fixture: implement gen_fixtures.py pipeline + --check mode | p0 | l | RFC-0002 | open |
| [#17](https://github.com/AbdelStark/grover-tax/issues/17) | fixture: validate_schemas module + gen-fixtures-check CI gate | p0 | s | RFC-0002 | open |
| [#18](https://github.com/AbdelStark/grover-tax/issues/18) | fixture: bit-layout interop test across Python/Rust/Cairo | p1 | s | RFC-0003, RFC-0004 | open |

### Stwo prover side (`area:stwo`)

| # | Title | Priority | Effort | RFC | Status |
|---|---|---|---|---|---|
| [#19](https://github.com/AbdelStark/grover-tax/issues/19) | stwo: bootstrap stwo-side/ Cargo project + prover/verifier shims | p0 | m | RFC-0004, RFC-0007 | open |
| [#20](https://github.com/AbdelStark/grover-tax/issues/20) | stwo: Cairo M31 9-limb 256-bit arithmetic + get_bit/set_bit | p0 | m | RFC-0004 | open |
| [#21](https://github.com/AbdelStark/grover-tax/issues/21) | stwo: Cairo gate dispatcher with constant-cost step() | p0 | l | RFC-0004 | open |
| [#22](https://github.com/AbdelStark/grover-tax/issues/22) | stwo: Cairo canonical-byte serialisation + NOP padding | p0 | m | RFC-0002, RFC-0004 | open |
| [#23](https://github.com/AbdelStark/grover-tax/issues/23) | stwo: Cairo in-circuit Blake2s commitment check | p0 | m | RFC-0004, RFC-0005 | open |
| [#24](https://github.com/AbdelStark/grover-tax/issues/24) | stwo: Cairo unit-test suite (C-T1..C-T8) | p0 | m | RFC-0004 | open |

### SP1 prover side (`area:sp1`)

| # | Title | Priority | Effort | RFC | Status |
|---|---|---|---|---|---|
| [#25](https://github.com/AbdelStark/grover-tax/issues/25) | sp1: author 0001-read-fixtures-from-json.patch | p0 | s | RFC-0006 | open |
| [#26](https://github.com/AbdelStark/grover-tax/issues/26) | sp1: scripts/apply_sp1_patch.sh + SP1 build wiring + BUILD.md | p0 | s | RFC-0006 | open |
| [#27](https://github.com/AbdelStark/grover-tax/issues/27) | sp1: CI gates for patch line-budget and clean-apply | p0 | s | RFC-0006 | open |

### Measurement harness (`area:harness`)

| # | Title | Priority | Effort | RFC | Status |
|---|---|---|---|---|---|
| [#28](https://github.com/AbdelStark/grover-tax/issues/28) | harness: bin/run_sp1.sh + bin/verify_sp1.sh | p0 | s | RFC-0007 | open |
| [#29](https://github.com/AbdelStark/grover-tax/issues/29) | harness: bin/run_stwo.sh + bin/verify_stwo.sh | p0 | s | RFC-0007 | open |
| [#30](https://github.com/AbdelStark/grover-tax/issues/30) | harness: wrapper symmetry CI test + exit-code matrix | p0 | s | RFC-0007 | open |
| [#31](https://github.com/AbdelStark/grover-tax/issues/31) | harness: proverlog grammar enforcement (CONSTRAINTS / TRACE_ROWS) | p0 | s | RFC-0007 | open |
| [#32](https://github.com/AbdelStark/grover-tax/issues/32) | harness: scripts/measure.sh (hyperfine + gnu-time capture) | p0 | m | RFC-0008 | open |
| [#33](https://github.com/AbdelStark/grover-tax/issues/33) | harness: scripts/measure_setup.sh (SP1 trusted setup capture) | p0 | s | RFC-0008 | open |
| [#34](https://github.com/AbdelStark/grover-tax/issues/34) | harness: iostat_capture.sh (M10) + post_run_discard_check.sh | p1 | s | RFC-0008, RFC-0010 | open |
| [#35](https://github.com/AbdelStark/grover-tax/issues/35) | harness: scripts/check_gpu_residency.sh (cross-platform) | p0 | s | RFC-0009 | open |
| [#36](https://github.com/AbdelStark/grover-tax/issues/36) | harness: scripts/preflight.sh + cleanup.sh | p0 | m | RFC-0010, RFC-0012 | open |
| [#37](https://github.com/AbdelStark/grover-tax/issues/37) | harness: scripts/run_all.sh orchestrator + --day flag | p0 | m | RFC-0010, RFC-0013 | open |
| [#38](https://github.com/AbdelStark/grover-tax/issues/38) | harness: results/discards.log append-only writer | p0 | s | RFC-0010 | open |
| [#39](https://github.com/AbdelStark/grover-tax/issues/39) | harness: integration test suite (M-T*, H-T*, S-T*) | p0 | m | RFC-0007..RFC-0010 | open |

### Reporting (`area:reporting`)

| # | Title | Priority | Effort | RFC | Status |
|---|---|---|---|---|---|
| [#40](https://github.com/AbdelStark/grover-tax/issues/40) | reporting: author RESULTS.md.j2 Jinja2 template | p0 | s | RFC-0011 | open |
| [#41](https://github.com/AbdelStark/grover-tax/issues/41) | reporting: analyze.py — ingest, statistics, discard tally, render | p0 | l | RFC-0011 | open |
| [#42](https://github.com/AbdelStark/grover-tax/issues/42) | reporting: day-1/day-2 stability gate + residual-concurrency flag | p0 | s | RFC-0010, RFC-0011 | open |
| [#43](https://github.com/AbdelStark/grover-tax/issues/43) | reporting: plot.py — deterministic histogram + bar + day-1/day-2 | p0 | m | RFC-0011, RFC-0013 | open |
| [#44](https://github.com/AbdelStark/grover-tax/issues/44) | reporting: check_results_md.py methodology lint + R-T test suite | p0 | s | RFC-0011 | open |

### Governance / CI (`area:ci`)

| # | Title | Priority | Effort | RFC | Status |
|---|---|---|---|---|---|
| [#45](https://github.com/AbdelStark/grover-tax/issues/45) | ci: LICENSE + README + CONTRIBUTING + SECURITY + COC + CHANGELOG | p1 | s | RFC-0014 | open |
| [#46](https://github.com/AbdelStark/grover-tax/issues/46) | ci: .github/CODEOWNERS routing methodology files to maintainer | p1 | s | RFC-0014 | open |
| [#47](https://github.com/AbdelStark/grover-tax/issues/47) | ci: Python-side Actions (ruff, mypy, pytest, gen-fixtures-check) | p0 | m | RFC-0014 | open |
| [#48](https://github.com/AbdelStark/grover-tax/issues/48) | ci: Rust/Cairo/wrapper/patch GitHub Actions | p0 | s | RFC-0014 | open |
| [#49](https://github.com/AbdelStark/grover-tax/issues/49) | ci: integration E2E + methodology-lint CI jobs | p1 | s | RFC-0014 | open |
| [#50](https://github.com/AbdelStark/grover-tax/issues/50) | ci: scripts/check_licenses.sh + license-check CI | p1 | s | RFC-0014 | open |
| [#51](https://github.com/AbdelStark/grover-tax/issues/51) | ci: branch-protection.md + actionlint + audit script | p2 | s | RFC-0014 | open |

## Tracking issues

| # | Subsystem | RFCs | Children |
|---|---|---|---|
| [#52](https://github.com/AbdelStark/grover-tax/issues/52) | Build / toolchain / reproducibility | RFC-0001, RFC-0012, RFC-0013 | #3 — #9 |
| [#53](https://github.com/AbdelStark/grover-tax/issues/53) | Fixture pipeline | RFC-0002, RFC-0003, RFC-0005 | #10 — #18 |
| [#54](https://github.com/AbdelStark/grover-tax/issues/54) | Stwo prover side | RFC-0004, RFC-0005 | #19 — #24 |
| [#55](https://github.com/AbdelStark/grover-tax/issues/55) | SP1 prover side | RFC-0006 | #25 — #27 |
| [#56](https://github.com/AbdelStark/grover-tax/issues/56) | Measurement harness | RFC-0007, RFC-0008, RFC-0009 | #28 — #35 |
| [#57](https://github.com/AbdelStark/grover-tax/issues/57) | Environmental hygiene | RFC-0010 | #36 — #39 |
| [#58](https://github.com/AbdelStark/grover-tax/issues/58) | Reporting | RFC-0011 | #40 — #44 |
| [#59](https://github.com/AbdelStark/grover-tax/issues/59) | Governance and CI | RFC-0014 | #45 — #51 |

## Cross-cutting dependencies

The dependency graph below highlights the load-bearing chains. Cross-issue dependency comments live on each issue; this section is the cheat-sheet.

- **Workload-pin chain**: #3 → #4 → many downstream (#5, #10, #14, #16). The chain blocks fixture generation and most prover-side work.
- **Versions-lock chain**: #5 → #6 → #7 → #36 (preflight) → measured runs. The chain blocks any measured headline number.
- **Fixture chain**: #10..#13 (foundations) → #14 (schema) → #15 (sim) → #16 (gen) → #17 (validator). Every prover-side issue depends on a populated `fixtures/v0.1.json`.
- **Cairo chain**: #19 (bootstrap) → #20 (limbs) → #21 (dispatcher) → #22 (serialise) → #23 (Blake2s commit) → #24 (tests). The chain is strictly linear.
- **SP1 chain**: #5 → #25 (patch) → #26 (apply) → #27 (CI). Short and tight.
- **Wrapper chain**: prover binaries land → #28..#31 (wrappers + symmetry + grammar) → #32 (measure.sh).
- **Hygiene chain**: #6 + #35 → #36 (preflight) → #37 (run_all). #37 is the single most-blocked issue.
- **Reporting chain**: #14 (schemas) + #38 (discards log) → #41 (analyze) → #42, #43 → #44 (lints). `RESULTS.md` lives or dies here.
- **CI chain**: every implementation issue → its CI gate (#47..#51).

The longest chain (workload → fixtures → Cairo → wrappers → measure → preflight → run_all → analyze → results) bounds the critical path: roughly **30 issues to close in dependency-order** before the headline can ship.

## Open questions (carried from the RFC corpus)

These are informational; none block `v0.1` filing:

- **OPEN-Q-2.1** — Fixture inline reproduction recipe. Decided: no.
- **OPEN-Q-4.1** — Cairo limb count (9 vs 11). Decided: 9; revisit if reduction overhead is excessive.
- **OPEN-Q-6** — Supply-chain hardening. Decided: out of scope for `v0.1`.
- **OPEN-Q-8.1** — `iostat_capture.sh` overhead. Decided: M10 informational; revisit if it materially affects M1.
- **OPEN-Q-9.1** — Future macOS hard-core-pinning. Watch list.
- **OPEN-Q-10.1** — Day-2 reversal tooling-enforced. Decided: yes (issue #37).
- **OPEN-Q-11.1** — CSV companion to `RESULTS.md`. Decided: no in `v0.1`.
- **OPEN-Q-12.1** — Record macOS marketing build in `versions.lock`. Decided: yes; lands during #6.
- **OPEN-Q-13.1** — SLSA-3 / Sigstore graduation. Post-`v0.1`.
- **OPEN-Q-13.2** — Publish reference-rig binaries. Currently no.
- **OPEN-Q-14.1** — When to add second maintainer. Trigger defined.
- **OPEN-Q-14.2** — GPG-signed commits on `main`. Currently no.

## Counts

- Implementation issues: **49** (p0: 41, p1: 7, p2: 1).
- Tracking issues: **8**.
- Effort distribution: s = 31, m = 16, l = 2.
- Areas: build 7, fixture 9, stwo 6, sp1 3, harness 12, reporting 5, ci 7.
- Total open work units against milestone `v0.1`: **57**.
