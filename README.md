# grover-tax

Single-laptop, single-core, no-GPU wall-clock comparison of two zero-knowledge proving stacks — Stwo (StarkWare) and SP1 with a Groth16 wrap (Succinct Labs) — on one fixed proof statement:

> *There exists a reversible classical circuit `C` over `{NOT, CNOT, Toffoli}` that realises one elliptic-curve point addition over secp256k1, attested in zero knowledge against a public set of test cases.*

One number ships: `t_SP1_Groth16 / t_Stwo`, with median, IQR, min, max, stddev over ≥10 measured runs per prover. Around it: peak RSS, proof size, verifier time, constraint count, and the trusted-setup cost of the SP1 side, reported separately.

## Status

Specification frozen. Implementation pending against [milestone `v0.1`](https://github.com/AbdelStark/grover-tax/milestone/1) (57 issues). `RESULTS.md` is produced on the reference rig by `./scripts/run_all.sh` once implementation closes.

## Reference rig

Apple M4 Max, 16 cores (1 used), 48 GB RAM, macOS 26.2, AC power, Wi-Fi/Bluetooth off, low-power mode off. Full toolchain pinned in `versions.lock` once implementation lands. A Linux x86_64 CI rig provides regression coverage but is not headline-canonical.

## Reproduce

```bash
git clone https://github.com/AbdelStark/grover-tax.git
cd grover-tax
./scripts/run_all.sh
```

Expected wall time on the reference rig: ~25 min. Hard ceiling: 45 min. Output lands in `RESULTS.md` and `results/`.

## Apples-to-apples

Only one intentional divergence between the two sides: the circuit-commitment hash function (SP1 uses SHA-256 — upstream's native choice; Stwo uses Blake2s — a bit-oriented hash in the same structural family that Stwo Cairo has as a built-in). Both commitments are computed over identical bytes; both verifiers bind. The full justification is in [RFC-0005](docs/rfcs/RFC-0005-commitment-divergence.md). Other structural differences (BabyBear vs M31 field, trusted setup required on SP1 side only, macOS frequency-pinning gap) are disclosed in `RESULTS.md`.

## Repository layout

- [`PRD.md`](PRD.md) — original technical brief, frozen as historical record.
- [`SPEC.md`](SPEC.md) — index of the implementation specification corpus.
- [`docs/spec/`](docs/spec/) — eleven specification sections (overview, architecture, public API, data model, error model, observability, security, testing, performance, release, glossary).
- [`docs/rfcs/`](docs/rfcs/) — fourteen RFCs locking the load-bearing technical decisions.
- [`docs/roadmap/IMPLEMENTATION.md`](docs/roadmap/IMPLEMENTATION.md) — implementation tracker keyed to GitHub issues.

## Contributing

The methodology is contractual. Any change that affects measured numbers requires an RFC update before merge. `CONTRIBUTING.md` (pending, issue [#45](https://github.com/AbdelStark/grover-tax/issues/45)) will document the PR workflow.

## License

MIT. See [`LICENSE`](LICENSE) (pending, issue [#45](https://github.com/AbdelStark/grover-tax/issues/45)).
