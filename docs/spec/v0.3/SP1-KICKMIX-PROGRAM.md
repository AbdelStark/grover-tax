# The SP1 kickmix program (Tier-2 SP1 side)

**Status:** normative for the Tier-2 Khattar-benchmark SP1 side (KB-12, #124).
**Companion:** `KHATTAR-BENCHMARK-ALIGNMENT.md` §4 (G4), `RFC-0006`,
`RFC-0007` (wrapper contract), `bin/run_sp1.sh` / `bin/verify_sp1.sh`.

## Goal

For a credible head-to-head, the only difference between the SP1 and Stwo
numbers must be the **proving backend**, not the program. So the SP1 side runs
the **full kickmix statement** — a byte-faithful equivalent of the upstream
kickmix fuzzer — rather than the v0.2 custom GTV1 program.

That statement computation is implemented, portably and natively tested, in
[`kickmix::statement::run_statement`](../../../kickmix/src/statement.rs): it
Fiat-Shamir-derives the inputs (KB-9), simulates the circuit on each (KB-8), and
certifies the resource counts (KB-10). The SP1 program is a thin zkVM wrapper
around that function.

## Program contract

```rust
#![no_main]
sp1_zkvm::entrypoint!(main);

pub fn main() {
    // stdin (see "Stdin layout" below)
    let circuit_bytes = sp1_zkvm::io::read_vec();   // the .kmx source bytes
    let circuit_hash: [u8; 32] = sp1_zkvm::io::read();   // sha256(circuit_bytes)
    let width: u32              = sp1_zkvm::io::read();
    let repetitions: u128       = sp1_zkvm::io::read();
    let num_samples: u64        = sp1_zkvm::io::read();
    let demanded: DemandedBounds = sp1_zkvm::io::read();

    let circuit = kickmix::Circuit::parse(&String::from_utf8(circuit_bytes).unwrap()).unwrap();
    let outputs = kickmix::statement::run_statement(&circuit, &circuit_hash, params)
        .expect("statement does not hold");

    // Public outputs, in order (matching the verifier / RESOURCE-CERTIFICATION.md):
    sp1_zkvm::io::commit(&circuit_hash);            // [u8; 32]
    sp1_zkvm::io::commit(&outputs[0]);              // num_samples
    sp1_zkvm::io::commit(&outputs[1]);              // max_qubit_count
    sp1_zkvm::io::commit(&outputs[2]);              // max_non_clifford_count
    sp1_zkvm::io::commit(&outputs[3]);              // max_circuit_instructions
    sp1_zkvm::io::commit(&outputs[4]);              // sentinel == 42
}
```

A panic (a failed fuzz case or a resource violation) means the statement does
not hold and **no proof is produced** — exactly the soundness the benchmark
wants.

### Stdin layout

| Order | Field | Type | Source |
|---|---|---|---|
| 1 | `circuit_bytes` | `Vec<u8>` | the raw `.kmx` (or the fixture's `circuit_byte_serialisation`) |
| 2 | `circuit_hash` | `[u8; 32]` | `kmx_source_sha256` (the FS seed + commitment) |
| 3 | `width` | `u32` | `register_width` |
| 4 | `repetitions` | `u128` | `repetitions` |
| 5 | `num_samples` | `u64` | `demanded_num_samples` |
| 6 | `demanded` | 4×`u64` | the fixture's `demanded_*` bounds |

`bin/run_sp1.sh` is extended to serialise these from the `v0.3-iadd` fixture
(KB-4) instead of the v0.2 `(circuit, n_cases, x, y)` layout; `bin/verify_sp1.sh`
reads back the six public outputs and asserts the resource bounds (KB-10) and
`sentinel == 42`, in addition to checking the proof.

## Build, ELF pin, and vkey — **reference-rig gated**

These steps require the SP1 toolchain (`sp1up`) and Docker, and are performed on
the maintainer's reference rig (they are **not** produced in this PR, and no
SHAs are fabricated):

1. **Build** the program ELF reproducibly:
   `cargo prove build --docker --tag <pinned>` from `third_party/sp1/program/`.
2. **Pin** the ELF SHA-256 in `versions.lock` under a new `sp1.program_elf_sha256`
   field (ties into v0.3 A2/A8/C2). The drift gate (`scripts/lock_versions.sh`)
   then catches any silent change to the proven program.
3. **vkey**: derive the verifying key from the ELF and record it; a reproducible
   Docker build must yield the same vkey. `bin/verify_sp1.sh` pins the vkey so a
   swapped program is rejected.

## Acceptance status

| Item | Status |
|---|---|
| Tier-2 statement computation (FS + sim + resource cert) | ✅ `kickmix::statement`, 5 native tests (iadd64/iadd8 hold; broken circuit and over-tight bound rejected; deterministic) |
| SP1 zkVM wrapper source + stdin/public-output contract | ✅ specified above; thin wrapper over the tested core |
| `run_sp1.sh`/`verify_sp1.sh` contract reconciliation | ✅ documented (serialise from `v0.3-iadd`; verify the 6 outputs) |
| ELF reproducible Docker build + SHA-256 pin in `versions.lock` | ⏳ reference rig (SP1 toolchain + Docker) |
| vkey match across reproducible builds | ⏳ reference rig |
| End-to-end prove of `iadd64` through the harness | ⏳ reference rig (ties into KB-6/#118) |

The portable statement core is fully verified here; the proving-backend build,
the vkey reproducibility, and the end-to-end timing are hardware/toolchain
obligations that land on the rig (and tie into the measurement series, #118).
