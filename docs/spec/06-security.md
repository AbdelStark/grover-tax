# Security

This project is a benchmark, not a cryptographic deployment. Its security posture is shaped by three observations:

1. **Public from day one.** The repo is MIT-licensed and public from the first commit. There is no private state to protect. The "secret witness" `C` is published in `fixtures/v0.1.json`. The label "secret" is a property of the proof system's syntax, not of operational confidentiality.
2. **Verifiers are taken on upstream terms.** This project does not audit SP1 or Stwo. Verifier correctness is established by the upstream projects. We assert their verifier-returns-zero behaviour as a precondition for accepting a timing measurement, nothing more.
3. **The trusted setup is a structural concern, not a soundness claim.** SP1+Groth16 requires a trusted setup. The provenance of that ceremony is recorded in `RESULTS.md`. The Stwo side has no trusted setup. This asymmetry is reported, not eliminated.

## Threat model

### What an adversary controls

- Code submitted as PRs to this repository.
- Inputs to public scripts (a reproducer's local `fixtures/v0.1.json`, their toolchain).
- Upstream dependencies (SP1, Stwo, Cairo, `coincurve`, `uv`-resolved packages, system `hyperfine`/`gnu-time`).

### What an adversary does *not* control

- The committed `fixtures/v0.1.json` after generation.
- The committed `versions.lock`.
- The headline numbers in published `RESULTS.md`, beyond their reproduction by independent parties.

### What is in scope to defend against

1. **Workload tampering.** A PR that silently changes `fixtures/v0.1.json` to favour one prover. Defended by: (a) the `gen-fixtures --check` CI gate that asserts the on-disk fixture equals what the generator would produce; (b) the two commitment self-checks (F-INV-2, F-INV-3); (c) the cross-validation against `coincurve` (F-INV-5); (d) human review of any change touching `fixtures/`.
2. **Measurement scaffolding tampering.** A PR that changes one prover's invocation but not the other. Defended by: (a) the symmetric wrapper contract enforced by `RFC-0007`'s symmetry check; (b) the `MEASUREMENT.AFFINITY_MISS` check that requires both wrappers to use the same OS-affinity prefix.
3. **Toolchain substitution.** Reproducer accidentally builds with a different toolchain. Defended by `versions.lock` and `BUILD.RUSTC_MISMATCH`.
4. **Supply-chain compromise.** Malicious upstream of SP1, Stwo, or a Python package. Defended *partially* by: (a) `uv.lock` with hashes pinning every Python dep; (b) `sp1up` and `cargo` lockfiles. There is no full SBOM enforcement and no signing of upstream binaries. A defence-in-depth posture against a determined supply-chain attacker is out of scope for `v0.1`. See `OPEN-Q-6`.

### What is explicitly out of scope

- Side-channel analysis of either prover.
- Confidentiality of the witness on the local machine post-generation.
- Network attacks (the run is fully offline by `8.2` and `RFC-0010`).
- Multi-user trust (single laptop, single operator).
- Reproducible builds in the strong cryptographic sense (we aim for bit-stable artifacts but do not enforce a bootstrappable build chain — see `RFC-0013`).

## Trust boundaries

| Boundary | Trusted side | Untrusted side | Mechanism |
|---|---|---|---|
| Fixture file | `gen_fixtures.py` output | hand edits | `--check` mode + commitment self-checks |
| Prover wrapper | symmetric contract enforcement | implementation-specific invocations | RFC-0007 symmetry tests in CI |
| Toolchain | `versions.lock` | local installs | `preflight.sh` |
| Upstream submodules | pinned SHAs | unreviewed updates | `versions.lock` + PR review |
| Reporting | `analyze.py` from raw JSON | hand-edited `RESULTS.md` | regenerated on every `run_all.sh`; CI rejects hand edits |

## Secrets handling

There are no secrets. To remain that way:

- `.env`, `*.pem`, `*.key`, `credentials.*`, `secrets.*` are in `.gitignore` (already present).
- No environment variable consumed by the harness is treated as secret; all are recorded into `versions.lock.host` if they affect behaviour.
- No credentials are required to run the benchmark (no GitHub token, no API key, nothing).

A contribution that introduces a secret is rejected at PR review.

## Trusted setup discussion (SP1 / Groth16 side)

Groth16 requires a structured-reference-string (SRS) produced by a trusted-setup ceremony. The SP1 example consumed in `sp1-side/` uses some upstream ceremony output. The provenance of that ceremony — who ran it, when, what entropy contributions, what protocol — is recorded in `results/sp1_setup.json.groth16_ceremony_origin` and reported in `RESULTS.md`.

If the ceremony is fresh-and-locally-reproduced (non-trusted-setup-equivalent for benchmark purposes), `RESULTS.md` says so explicitly. If it is an upstream-provided SRS, `RESULTS.md` cites the ceremony's documented provenance.

This is a structural property of the SP1+Groth16 stack, not a defect of this benchmark. The Stwo side does not have an analogous concern.

## Public artifact discipline

Because the repo is public from day one:

- No commit touches `fixtures/v0.1.json` after the day-1 generation pass without a corresponding version bump (`v0.1.json` → `v0.2.json`).
- No commit touches `versions.lock` after the first measured run series without invalidating the prior `results/` (the prior runs are moved to `results/archive/<date>/`).
- `results/` history is preserved; bad runs are *not deleted*, they are moved under `results/archive/<date>/` with a `WHY.md` next to them.

This discipline makes the benchmark's history auditable: an outside observer can see every state the numbers passed through.

## Licensing as security

- Repo root: MIT.
- SP1 (Apache-2.0), Stwo (Apache-2.0 / MIT — verify at pin), Cairo (Apache-2.0): compatible with MIT redistribution.
- `coincurve` (MIT or Apache-2.0; verify at pin): compatible.
- `scripts/check_licenses.sh` runs in CI and in `run_all.sh` before any measurement. Incompatible licence detected → `BUILD.LICENSE_CHECK_FAIL`. See `RFC-0014`.

## Reporting vulnerabilities

If a contributor or reviewer identifies a soundness defect in this benchmark's *methodology* (e.g., a metric capture flaw, a hygiene gap that biases one prover), they may open a public issue with label `type:bug priority:p0`. There is no embargoed disclosure track — the project ships methodology, not exploitable systems.

If they identify a defect in SP1 or Stwo *upstream*, they should report it to those projects' security contacts (out of scope here).

## OPEN-Q-6 — Supply-chain hardening

Should `v0.1` ship with a tighter supply-chain posture (cryptographic signing of `uv.lock` entries, full SBOM generation, signature verification of `hyperfine` and `gnu-time` binaries)? Current decision: **no**, because the benchmark's reproducibility envelope already binds the relevant inputs and a full supply-chain posture is a project of its own. Resolution target: revisit during `v0.2` planning. Owner: maintainer.
