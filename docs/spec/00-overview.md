# Overview

## Thesis

`grover-tax` is a reproducible, single-laptop, single-core, no-GPU wall-clock comparison of two zero-knowledge proving stacks — Stwo (StarkWare) and SP1 with a Groth16 wrap (Succinct Labs) — on a single, fixed proof statement: the existence of a reversible classical circuit `C` over `{NOT, CNOT, Toffoli}` that realises one elliptic-curve point addition over secp256k1, attested in zero knowledge against a public set of test cases `T = {(x_i, y_i)}`.

The project ships one set of numbers. Those numbers are defensible, reproducible, and bound to a frozen workload contract.

## What this project is

A benchmark harness with two prover backends. The harness's job is to:

1. Generate a deterministic fixture (`fixtures/v0.1.json`) that fully specifies the workload — test cases `T`, circuit commitment `H_C`, and the full byte serialisation of `C` so any third party can recompute commitments independently.
2. Drive each prover end-to-end against that fixture using a symmetric wrapper contract.
3. Capture a fixed metric set (M1–M10, see `07-testing-strategy.md` and `08-performance-budget.md`) under tightly controlled environmental conditions.
4. Emit a `RESULTS.md` headline table, distribution plots, and an honest apples-to-apples disclosures section.

## What this project is not

- Not a general-purpose ZK benchmarking framework. The workload is fixed to one proof statement. Generalisation is explicitly out of scope.
- Not a recommendation engine. The headline number is `t_SP1_Groth16 / t_Stwo` on a fixed workload; readers draw their own inferences.
- Not a security review of either prover. Verifier correctness is asserted by running the upstream verifier; cryptographic soundness is taken on the upstream projects' terms.
- Not a multi-machine, multi-core, or GPU-accelerated comparison. Those are deliberately excluded so that a single reader on a single laptop can reproduce the result.

## Audience

Three roles use this corpus:

1. The implementer who turns this spec into code. Every contract this person needs is in `docs/spec/` and `docs/rfcs/`; the PRD is the historical brief.
2. The reproducer who clones the repo and runs `./scripts/run_all.sh`. The full experience is documented in `README.md` and bounded by the 30-minute clean-clone-to-results target.
3. The reviewer who reads `RESULTS.md` and judges whether the comparison is fair. The reviewer's questions are pre-answered in `RESULTS.md`'s apples-to-apples disclosures section (see `RFC-0011`).

## Success criteria

A `v0.1` release ships if and only if all four of the following hold:

1. Both provers run end-to-end against `fixtures/v0.1.json` on the reference rig.
2. The full protocol — from `git clone` on a clean reference machine to `RESULTS.md` populated — completes in under 30 minutes wall-clock. The hard ceiling is 45 minutes; exceeding it triggers a workload-size revisit (see `08-performance-budget.md`).
3. The headline ratio `t_SP1_Groth16 / t_Stwo` is reported with median, IQR, min, max, and stddev over a minimum of 10 measured runs per prover, with the discard rules of `RFC-0010` applied.
4. `RESULTS.md` reports each of the M1–M10 metrics, names every divergence from apples-to-apples in a dedicated section, and discloses the macOS frequency-pinning gap and SP1-side trusted-setup cost separately from the headline ratio.

Failure of any one criterion is a failed release.

## Out-of-scope (explicit)

These items are listed so future contributors know not to file issues against them in `v0.1`:

- GPU prover paths on either side.
- Multi-threaded or multi-core prover invocations.
- SHA-256 implementation in Cairo (would dominate Stwo wall-clock and confound the comparison — see `RFC-0005`).
- Alternative proof statements (post-quantum signatures, generic SNARK benchmarks, MPC-in-the-head schemes).
- Alternative provers (Plonky3, RISC Zero, Halo2, Nova, etc.).
- Cross-laptop variance studies. The reference rig is canonical; the Linux CI rig is regression-only.
- Hardware sweep (different CPUs, frequencies, cache sizes). One reference rig, fully documented.
- Online publication or paper write-up. That is downstream of `v0.1` and lives elsewhere.

## Reading order

Start at `SPEC.md` for the index. Read `00-overview.md` (this file), then `01-architecture.md` for the system shape, then `02-public-api.md` for the contracts a reproducer or downstream tool will touch. After that, branch by interest:

- Implementing? Read `03-data-model.md` and the RFCs for the subsystem you are touching.
- Reviewing the comparison? Read `RFC-0005` (commitment divergence), `RFC-0011` (reporting), `RFC-0009` (single-core enforcement), `RFC-0010` (hygiene/discard).
- Operating the run series? Read `05-observability.md`, `RFC-0008` (measurement), `RFC-0010` (hygiene).
