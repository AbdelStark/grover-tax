# RFC-0022 — Bootloader Integration (Stwo Side)

| Field | Value |
|---|---|
| Status | Accepted |
| Supersedes | (none; v0.1 had no bootloader path) |
| Depends on | RFC-0015, RFC-0016, RFC-0019 |
| Implements | `bin/apples-prove`, `bin/apples-verify` (new), `third_party/proving-utils/crates/stwo_run_and_prove/` consumption |

## 1. Summary

Specifies the Stwo-side prover stack, which is *not* a direct Stwo-prover invocation but a **bootloader-driven proof**: a Cairo program (`simple_bootloader_compiled.json`) runs the apples-to-apples Cairo task, and the Circle STARK is generated over the bootloader's execution trace. This adds a bootloader-specific overhead `B` (RFC-0018 §2) and introduces a Pedersen-based program-hash commitment (RFC-0019 §5.3). This RFC fixes the bootloader's role, the `SimpleBootloaderInput` schema, the public-input anchoring across the bootloader-task boundary, and the verifier obligations on the wrapper side.

## 2. Bootloader semantics

The `simple_bootloader_compiled.json` (committed at `third_party/proving-utils/crates/cairo-program-runner-lib/resources/compiled_programs/bootloaders/simple_bootloader_compiled.json`) is the canonical Cairo bootloader: it consumes a `SimpleBootloaderInput`, iterates over its `tasks` list, computes each task's `program_hash` (using the `program_hash_function` field) and runs each task. The bootloader's own AIR is a fixed Cairo program with constant trace-row count `B` (modulo the bootloader's own table of tasks). For a single-task bootloader input, `B` is fixed at:

| Component | Trace rows |
|---|---|
| Bootloader preamble | ~5000 |
| Task dispatch (one task) | ~10000 |
| Program-hash computation (Pedersen on ~15 KB) | ~30000 |
| Task return-value collection | ~5000 |
| Bootloader postamble | ~5000 |
| **Total `B`** | **~55000** |

These values MUST be measured at the first v0.2 measured run and recorded in `RESULTS.md` §"Operations-counted footprint" (RFC-0018 §4). Any single-task bootloader invocation MUST agree with the recorded `B` within ±5%, else `MEASUREMENT.OPS_FOOTPRINT_DEVIATION` fires.

## 3. Bootloader's Pedersen commitment

The bootloader uses the **Starknet Pedersen** hash (`starknet_types_core::hash::pedersen_hash`) as `program_hash_function` to commit the task program. This commits the compiled `grover_tax_executable.executable.json` bytes into the bootloader's public input chain.

Pedersen is *not* `BLAKE2s` — but the BLAKE2s binding stated in RFC-0015 §2.2 is on `cb`, not on the program. The Pedersen commitment is an *additional, internal* layer that binds "the bootloader is running THIS task program," distinct from "the task program asserts `H_BLAKE2s(cb)`."

Disclosure: `RESULTS.md` §"Apples-to-apples disclosures" MUST include:

> Stwo's apples-to-apples proof is bootloader-mediated: the bootloader internally uses Pedersen as `program_hash_function` to bind the task program to its public input chain. This is structural to the Cairo bootloader pattern and is additional to the BLAKE2s commitment on `cb` that v0.2's statement requires.

## 4. Public-input anchoring across the bootloader

The bootloader's `SimpleBootloaderInput` JSON contains:

```json
{
  "fact_topologies_path": null,
  "single_page": true,
  "tasks": [
    {
      "type": "Cairo1Executable",
      "program_hash_function": "Pedersen",
      "path": "<path to executable.json>",
      "user_args_list": [<flat felt252 array>]
    }
  ]
}
```

The `user_args_list` is the v0.2 input layout (RFC-0016 §2). The bootloader passes this array to the task program. The bootloader's public input commits to:

1. The program hash (Pedersen of task program bytes).
2. The user args (per-felt commitment via the bootloader's input chain).

The resulting Stwo Circle STARK proof binds the public input. A verifier reading `(proof, fixture)` can:

1. Compute the expected `program_hash` from the committed `grover_tax_executable.executable.json` (which is built reproducibly per RFC-0021 §1/§12).
2. Compute the expected `user_args_list` from the fixture (per RFC-0016 §2's layout).
3. Verify the proof using `stwo-cairo verify`; reject if the public input differs.

`bin/apples-verify` (§5) automates this.

**Critical soundness obligation.** `bin/apples-prove` currently calls `stwo-run-and-prove --verify`, which **performs an inline verify but does NOT cross-check the public input against an external source**. The inline verify confirms "the proof is a valid Stwo proof for the public input it claims" — it does not confirm "the public input matches the fixture."

The 2026-05-14 headline relied on the inline verify alone. The v0.2 hardening (RFC-0020 §3.2, A_anchor defence) requires `bin/apples-verify` to cross-check the public input externally.

## 5. `bin/apples-verify` (new binary)

A new binary `bin/apples-verify` MUST be added. Contract:

```
bin/apples-verify --fixture <path> --proof <path>  [ --proof-format json|binary|cairo-serde ]
```

Operations:

1. Read the fixture; extract `cb`, `circuit_commitment_blake2s_hex`, `n_tc`, `T`.
2. Recompute the expected `user_args_list` per RFC-0016 §2.
3. Recompute `expected_program_hash` from the SHA-256 of `grover_tax_executable.executable.json` (or by re-running Pedersen if we want byte-equivalence; v0.2 accepts SHA-256-of-bytes as the equivalence anchor).
4. Run `stwo-cairo verify` (or `proving_utils/stwo-run-and-prove --verify --proof <path>`) on the proof.
5. Parse the proof's public input (Circle STARK proof binary format includes the committed public values).
6. Assert the proof's public-input commitments equal the expected commitments computed in steps 2-3.
7. **Defence-in-depth:** independently re-run the gate simulation in Python (`sim_reference.py`) for each test case in the fixture and assert `simulate(C, x_i[:32]) == y_i[:32]`. This catches a hypothetical Stwo verifier-acceptance of an unsound proof (RFC-0020 §3.3 A_statement).

Exit codes:
- `0`: all checks passed.
- `1`: proof verification failed *or* public-input mismatch *or* defence-in-depth simulation mismatch.
- `2`: precondition error (missing files, malformed fixture).

`bin/verify_stwo.sh` MUST call `bin/apples-verify`, not `stwo-cairo verify` directly.

## 6. `stwo-cairo` patch (extract_public_segments)

The Stwo-side path requires a small patch to `third_party/stwo-cairo/` to make `--program_type executable` work (RFC-0021 §12). The current state of the patch lives in `third_party/stwo-cairo/` and is *vendored* (not a submodule).

**Amendment.** `third_party/stwo-cairo/` MUST carry a single committed `.patch` file documenting the diff against the upstream commit. The patch file path is `third_party/stwo-cairo/0001-extract-public-segments.patch`. CI MUST assert that applying this patch to the upstream commit produces the vendored tree (`T22-6`).

## 7. Bootloader's failure modes

| Failure | Detection | Exit |
|---|---|---|
| Task panics inside the gate-loop | `stwo-run-and-prove` reports bootloader trace failure | `PROVER.WITNESS_REJECTED`, exit 1 |
| Task's `assert!(s == y_state)` fails | Same | Same |
| Bootloader cannot find the task program at `path` | `stwo-run-and-prove` exits before proving | `MEASUREMENT.ENV_VAR_MISS`, exit 2 |
| Bootloader public input mismatch | `apples-verify` catches | `PROVER.PUBLIC_INPUT_MISMATCH`, exit 1 |

## 8. Test obligations

| Test ID | Description | Layer |
|---|---|---|
| `T22-1` | `bin/apples-prove` with v0.2 fixture produces a verifying proof | integration |
| `T22-2` | `bin/apples-verify` accepts the produced proof | integration |
| `T22-3` | Tamper with `circuit_commitment_blake2s_hex` in the fixture (but leave proof unchanged); `apples-verify` rejects with `PROVER.PUBLIC_INPUT_MISMATCH` | soundness |
| `T22-4` | Tamper with one `y_i` byte in the fixture; `apples-verify` rejects with same | soundness |
| `T22-5` | Substitute the proof file with a proof for a *different* fixture (e.g., fixtures/v0.2-test-variant.json); `apples-verify` rejects | soundness |
| `T22-6` | Apply the `0001-extract-public-segments.patch` to the upstream stwo-cairo commit; assert tree equals `third_party/stwo-cairo/` | reproducibility |
| `T22-7` | Bootloader's `B` constant is measured and within ±5% of §2's table | methodology |

## 9. Open questions

- `OPEN-Q-22-1`: Can we eliminate the bootloader by invoking `stwo-cairo` directly on the apples-to-apples executable? This was the v0.1 design intent. The blocker is the `--program_type executable` path's `extract_public_segments` patch (§6) plus the fact that direct Cairo-program proofs would not get the bootloader's task-result collection. Deferred to v0.3.
- `OPEN-Q-22-2`: Should the bootloader's Pedersen be replaced by BLAKE2s for symmetry with the apples-to-apples commitment? Pedersen is the Cairo bootloader's documented choice; changing it would require a fork of `simple_bootloader_compiled.json`. Not in scope for v0.2.
