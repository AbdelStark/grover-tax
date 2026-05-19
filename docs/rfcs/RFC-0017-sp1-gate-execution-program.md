# RFC-0017 — SP1 Gate-Execution zkVM Program

| Field | Value |
|---|---|
| Status | Accepted |
| Supersedes | RFC-0006 (SP1 patch surface — patch-budget model retired) |
| Depends on | RFC-0015 (statement), RFC-0019 (soundness), RFC-0020 (threat model) |
| Implements | `third_party/sp1/program/src/main.rs`, `third_party/sp1/prover/prove.rs` |

## 1. Summary

Defines the SP1 zkVM program that proves the apples-to-apples v0.2 statement (RFC-0015 §3.6) and the SP1 host (`prove.rs`) that drives it. Replaces RFC-0006's `<50-line patch against the upstream example_zkp_prove.rs` model with a freshly authored, fully owned RISC-V program living under `third_party/sp1/program/`. Specifies the program's I/O contract, the public-input anchoring digest, the constraint-shape obligation (constant-cost-per-gate over the RISC-V cycle model), and the prover-binary CLI contract that `bin/run_sp1.sh` consumes.

## 2. Program shape

The program is a single-binary `#![no_main]` RISC-V ELF compiled by SP1's build system (`sp1-build`) and embedded into the prover via `include_elf!("zkp_ecc-program")`. Entry point:

```rust
#![no_main]
sp1_zkvm::entrypoint!(main);

pub fn main() { /* §3 */ }
```

The program lives at `third_party/sp1/program/src/main.rs`. The `cargo +1.93.0 build --release` build is normative; the build's resulting ELF byte-hash MUST be recorded in `versions.lock::sp1.program_elf_sha256` (RFC-0021 §3). A reproducer with the same SP1 toolchain MUST produce the same ELF bytes; if not, that is a v0.2 reproducibility defect (Tier 1 of RFC-0013) and the SP1 build is broken.

## 3. Program semantics

The zkVM-stdin schema is:

```
1. circuit_bytes  : Vec<u8>            (read_vec)
2. n_cases        : u64                 (read)
per test case (n_cases times):
   3. x_bytes     : [u8; 32]            (read)
   4. y_expected  : [u8; 32]            (read)
```

The program MUST:

1. Read `circuit_bytes` from stdin.
2. Read `n_cases` from stdin.
3. Compute `commitment := H_SHA256(circuit_bytes)` using SP1's patched `sha2` crate (zero-overhead zkVM syscall; RFC-0019 §5.1).
4. Commit `commitment` and `n_cases` to the proof's public values via `sp1_zkvm::io::commit(&commitment)` then `sp1_zkvm::io::commit(&n_cases)`.
5. Parse `circuit_bytes` as `GTV1` per RFC-0015 §3.3. Panic with `"invalid GTV1 circuit"` on any deviation (Magic, length mismatch, out-of-range field).
6. For `i ∈ [0..n_cases)`:
   - Read `x` (32 bytes), then `y_expected` (32 bytes) from stdin.
   - Compute `y_got = simulate(gates, &x)` using the bit-level semantics of RFC-0015 §3.4.
   - `assert_eq!(y_got, y_expected, "simulation mismatch");`
7. **Public-input anchoring (RFC-0019 §6.2):** before exit, the program MUST compute and commit a binding digest

   ```
   digest_anchor := H_SHA256(
       commitment ‖
       (n_cases as u64).to_be_bytes() ‖
       x_1 ‖ y_1 ‖ x_2 ‖ y_2 ‖ … ‖ x_{n_cases} ‖ y_{n_cases}
   )
   ```

   and `sp1_zkvm::io::commit(&digest_anchor)`. The verifier (`prove.rs` peer; `bin/apples-verify`) MUST recompute `digest_anchor` from the fixture and compare to the proof's third committed public value. Without this anchor, an honest prover could prove RFC-0015 over a different `T` than the fixture's, defeating RFC-0020 §3.2's substitution defence.

8. Return without further committed output.

The bit-level `apply_gate`, the parser, and the simulator are normative as written in `third_party/sp1/program/src/main.rs:45-129`. RFC-0015 §3.3-3.4 fixes their behaviour; this RFC fixes their implementation location.

### 3.1 Constant-cost-per-gate

The `simulate` loop MUST execute the same number of RISC-V cycles regardless of opcode. Concretely:

- The four `match` arms in `simulate` MUST compile to branches with equal cycle count after optimisation.
- The NOP branch MUST NOT short-circuit before the per-gate range-check / state update path.
- The TOFFOLI branch's `&` MUST NOT be data-dependently elided (LLVM's optimiser may attempt this; the program MUST use `core::hint::black_box` or volatile reads if optimisation removes the cycle).

A CI test (`S17-T8`) compiles the program with the pinned toolchain and inspects the `cargo objdump --release` output for the `simulate` function, asserting cycle-equivalence across the four arms. The test reads RISC-V instruction counts directly; it is platform-deterministic.

A regression on `S17-T8` is a v0.2 apples-to-apples failure. CI MUST fail the build.

## 4. Public values bound by the proof

| Slot | Type | Source | Verifier obligation |
|---|---|---|---|
| 0 | `[u8; 32]` | `commitment = H_SHA256(cb)` | `cb` matches fixture → digest matches fixture's `circuit_commitment_sha256_hex` |
| 1 | `u64` (8 bytes LE in SP1's serialisation) | `n_cases` | matches fixture `len(test_cases)` |
| 2 | `[u8; 32]` | `digest_anchor` (§3.7) | recomputed locally from fixture |

The proof exposes these three values via `SP1ProofWithPublicValues::public_values`. The verifier (RFC-0015 §5) reads them and runs the three comparisons. Any disagreement is `PROVER.PUBLIC_INPUT_MISMATCH` (new subcode, RFC-0021 §17).

## 5. Host (`prove.rs`) contract

The prover binary is `third_party/sp1/prover/prove.rs`, compiled as a workspace binary by `cargo +1.93.0 build --release`. CLI:

```
prove --fixtures <path> --output <path>
```

Reads the v0.2 fixture, builds the zkVM stdin per §3, invokes SP1's `ProverClient::prove` with the embedded ELF, and writes the resulting `SP1ProofWithPublicValues` to `<output>` via `proof.save`. Emits `CONSTRAINTS:` and `TRACE_ROWS:` on stdout per RFC-0007 §"Stdout" (RFC-0021 §5 specifies the source of these counts — the SP1 SDK's `ExecutionReport`, *not* a wrapper-synthesised value).

The default proof shape is *compressed STARK*. If `SP1_USE_GROTH16=1` is set, the prover wraps the proof in Groth16 (M8 trusted-setup cost applies; RFC-0019 §2.3). Otherwise no setup is required.

## 6. Build pinning

| Pin | Source | Rationale |
|---|---|---|
| `rust-toolchain = 1.93.0` | `third_party/sp1/rust-toolchain` | Required by `sp1-zkvm 6.0.2` |
| `sp1-sdk = "6.0.2"` | `third_party/sp1/prover/Cargo.toml` | Pinned version of the SP1 host SDK |
| `sp1-zkvm = "6.0.2"` | `third_party/sp1/program/Cargo.toml` | Pinned version of the zkVM runtime |
| `sha2 patch` | `git = "https://github.com/sp1-patches/RustCrypto-hashes", tag = "patch-sha2-0.10.9-sp1-6.0.0"` | Provides the SHA-256 zkVM syscall (RFC-0019 §5.1) |
| `third_party/sp1/Cargo.lock` | committed | RFC-0021 §1 (must be re-committed if a transitive bump alters it) |
| `third_party/sp1/program/Cargo.lock` | gitignored | sp1-build regenerates each build; RFC-0021 §1 amendment B allows this iff the program ELF SHA-256 in `versions.lock` matches |

The `sp1up`-installed toolchain (RISC-V cross-compiler + zkVM runtime) is recorded by SHA-256 in `versions.lock::sp1.toolchain_sha256` per RFC-0021 §3. `preflight.sh` re-hashes the installed toolchain and aborts on drift.

## 7. Test obligations

| Test ID | Description | Layer |
|---|---|---|
| `S17-T1` | Empty circuit (`cb = "GTV1" + 0u32_le`, `n_cases = 0`) → proof emits with `commitment = H_SHA256("GTV1\0\0\0\0")` | unit |
| `S17-T2` | One-NOP circuit, one test case `(x, y = x)` → proof emits | unit |
| `S17-T3` | One-NOT circuit on bit 0, `x = 0`, `y = [1, 0, 0, ..., 0]` → proof emits | unit |
| `S17-T4` | Reject: invalid magic header → program panics with `"invalid GTV1 circuit"`; SP1 wrapper exits 1 with `PROVER.WITNESS_REJECTED` | integration |
| `S17-T5` | Reject: `y` mismatch on test case 0 → program panics with `"simulation mismatch"`; same exit | integration |
| `S17-T6` | Public-input anchor: substitute `T[0].y` for `T[0].x` in the prover stdin (do not change fixture) → proof succeeds but `digest_anchor` differs → verifier MUST reject in `bin/apples-verify` | integration |
| `S17-T7` | ELF byte-stability: rebuild the program twice with the pinned toolchain; SHA-256 of the ELFs MUST match | reproducibility |
| `S17-T8` | Constant-cycle-per-gate: `cargo objdump --release` on `simulate`; per-arm cycle counts MUST match | reproducibility/methodology |
| `S17-T9` | Cross-prover statement: for `fixtures/v0.2.json`, both SP1 and Stwo emit proofs that verify (positive equivalence) | integration |
| `S17-T10` | `bin/apples-verify` MUST cross-check all three committed public values; tamper with each in turn and assert rejection | integration |

## 8. Alternatives considered

**A1: Patch the upstream `tanujkhattar/zkp_ecc` example (RFC-0006 model).** Rejected: upstream's example proves a different statement (point-add via a different gate dispatcher). A patch large enough to repurpose it for v0.2's statement blows the <50-line budget by ~2×. We retire the patch-budget constraint and own the entire SP1 program.

**A2: Use SP1's stdin without a public-input anchor.** Rejected: vulnerable to RFC-0020 §3.2 substitution-of-T. The anchor adds ~2 RISC-V cycles per test-case byte (~256 cycles per case at `n_tc = 4` = 1024 cycles; negligible compared to the ~12-min wall-clock).

**A3: Commit each `(x_i, y_i)` separately instead of a single rolling digest.** Same security; more verifier ergonomics but more committed public values (3 + 2·n_tc instead of 3). For `n_tc = 4` the difference is 5 extra public values; negligible. We choose the rolling digest for compactness.

**A4: Default to Groth16 wrap (`SP1_USE_GROTH16=1` always).** Rejected: the trusted-setup cost (M8, ~20-45 min) blows the 30-min clean-clone budget for any reproducer who runs the ceremony fresh. Default compressed-STARK; Groth16 is opt-in.

## 9. Open questions

- `OPEN-Q-17-1`: Should the prover's public-values commit emit `commitment` as the SHA-256 of `circuit_bytes || domain_separator` where `domain_separator = "grover-tax-v0.2-sp1"`? Would byte-distinguish the SP1-side commitment from the raw fixture digest and defend against a fixture-substitution attack where an attacker pre-commits a different `cb` whose SHA-256 matches the fixture (computationally infeasible but defence-in-depth). Deferred to v0.3.
