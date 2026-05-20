# RFC-0025 — Direct Stwo Cairo Path (No Bootloader)

| Field | Value |
|---|---|
| Status | Draft (v0.3) |
| Supersedes | RFC-0022 §1-4 for the v0.3 headline path; bootloader path retained as legacy |
| Depends on | RFC-0015 (statement), RFC-0016 (Cairo AIR), RFC-0023 (workload) |
| Resolves | `OPEN-Q-22-1` |

## 1. Summary

Removes the bootloader from the Stwo headline measurement path. v0.3
Stwo proves `Φ_v0.3` by invoking `stwo-cairo`'s prover *directly* on
`grover_tax_executable.executable.json` (the scarb-built Cairo
executable), bypassing `simple_bootloader_compiled.json`. This:

1. Eliminates the bootloader's `B ≈ 55 000` fixed trace rows (RFC-0022
   §2), tightening Stwo's wall-clock by an estimated 10–20% at small
   scale tiers (T0/T1) and a negligible fraction at large scales (T3/T4).
2. Removes the Pedersen-based program-hash commitment that requires
   disclosure in `RESULTS.md` (RFC-0022 §3).
3. Removes the bootloader's internal AIR from the apples-to-apples
   accounting, making RFC-0018's operations-counted equivalence
   theorem cleaner.
4. Closes the asymmetry adversary `A_param` notes in RFC-0024
   (bootloader is Stwo-only; SP1 has no analogous overhead).

The bootloader path remains shipped at `bin/apples-prove --legacy
bootloader` for backward-compatibility with v0.2 `RESULTS.md` files.

## 2. Background: why v0.2 used a bootloader

v0.2's Stwo path used `stwo-run-and-prove` with `simple_bootloader_compiled.json`
because, at the pinned `third_party/stwo-cairo/` commit, the direct
`stwo-cairo`-on-Cairo-1-executable proving path had a known bug in
`extract_public_segments` that rejected the AP-region layout of `Array<felt252>`
inputs containing `u128` values. The bootloader sidestepped this by
passing the input via a fixed-pointer indirection.

A patch (`third_party/stwo-cairo/0001-extract-public-segments.patch`)
was developed and vendored but never merged upstream. v0.3 uses this
patch directly, eliminating the bootloader requirement.

## 3. Implementation

### 3.1 Patch upstream `stwo-cairo`

The patch at `third_party/stwo-cairo/0001-extract-public-segments.patch`
must:
1. Apply cleanly to the pinned upstream commit (`T22-6` from RFC-0022 §8).
2. Be ≤ 100 lines (line-budget bumped from RFC-0006's 50-line; this
   patch is structurally larger than the historical SP1 fixture patch).
3. Add a doc-comment explaining the upstream issue.

### 3.2 `bin/apples-prove` defaults to direct Cairo

The wrapper script gains a `--driver {direct|bootloader}` flag,
defaulting to `direct`:

```
bin/apples-prove --fixture fixtures/v0.3/T1-pointadd-16384.json \
                 --proof-out results/stwo.proof.bin \
                 --driver direct
```

In `direct` mode, the wrapper invokes:

```
stwo-cairo prove \
    --program stwo-side/cairo/target/dev/grover_tax_executable.executable.json \
    --user-args-file <(jq -c '.user_args | .[]' <<< "$INPUT_JSON") \
    --proof-out "${PROOF_OUT}" \
    --proof-format json \
    --verify
```

The `user-args-file` semantics is the same as the bootloader's
`SimpleBootloaderInput::tasks[0].user_args_list`; it's a flat
`Array<felt252>` per RFC-0016 §2.

### 3.3 Public-input anchoring in direct mode

The direct-Cairo proof's public input is the `user_args` array
directly (no bootloader-mediated indirection). `bin/apples-verify`
(RFC-0024 §2.6) recomputes the expected `user_args` from the fixture
and asserts the proof's public-input slot matches byte-for-byte.

This is *simpler* than the bootloader anchoring (RFC-0022 §4) — no
Pedersen layer in the middle.

### 3.4 Operations-counted impact

RFC-0018 §2.1's theorem is amended:

```
Stwo direct-path:    rows_Stwo = c_Stwo · n_tc · n_g + k_Stwo · |cb| + b_Stwo
Stwo bootloader:     rows_Stwo = c_Stwo · n_tc · n_g + k_Stwo · |cb| + b_Stwo + B
```

where `B ≈ 55 000` is the bootloader fixed cost. The direct path
removes `B` entirely.

For T0 (`c_Stwo · 4 · 1024 ≈ 327 680`, `k_Stwo · 16 400 ≈ 1 968 000`,
`b_Stwo ≈ 10 000`), removing `B ≈ 55 000` saves ~2.4% of total rows.
For T3 (`c_Stwo · 4 · 1 048 576 ≈ 3.36×10⁸` rows from the gate loop
alone), `B / total ≪ 0.1%`.

So the direct-path benefit is largest at small scales (T0/T1) and
asymptotically vanishes at large scales (T3/T4). RFC-0018's scaling
analysis remains valid; only the small-scale constants shift.

## 4. Migration path for v0.2 results

v0.2 `RESULTS.md` files reference the bootloader-mediated Stwo path.
v0.3 publishes the direct-path numbers as the *primary* result and
optionally retains the bootloader-path numbers under a "Legacy v0.2
comparison" subsection of `RESULTS.md`.

The T0 cross-check (`S23-T4`) is between:
- v0.2's `fixtures/v0.2.json` (XOF-random circuit) via bootloader path
  → 298.755 s on Stwo (the 2026-05-20 measurement).
- v0.3's `fixtures/v0.3/T0-pointadd-1024.json` (upstream-prefix
  point-add) via direct path → expected ~280–290 s (2-3% lower due to
  bootloader removal, possibly counterbalanced by the point-add circuit
  having different opcode mix than XOF-random).

If the cross-check shows > 10% drift between v0.2 and v0.3 at T0, the
direct-path or the new workload has an issue; investigate before
publishing.

## 5. Test obligations

| Test ID | Description | Layer |
|---|---|---|
| `S25-T1` | `bin/apples-prove --driver direct` produces a verifying proof on T0 fixture | integration |
| `S25-T2` | `bin/apples-verify` accepts the direct-mode proof | integration |
| `S25-T3` | Direct-mode and bootloader-mode proofs of the same fixture both verify; their wall-clocks differ by the predicted `B ≈ 55 000` rows (within ±10%) | methodology |
| `S25-T4` | `third_party/stwo-cairo/0001-extract-public-segments.patch` applies cleanly to upstream pinned commit; the patched binary passes `stwo-cairo`'s own test suite | upstream-compat |
| `S25-T5` | Methodology lint `L4` accepts "Direct Cairo path; no bootloader" as a valid disclosure phrase | reporting |

## 6. Risks

- Upstream `stwo-cairo` may rebase the patched code, breaking the
  vendored patch. Mitigation: pin `third_party/stwo-cairo/` commit
  tightly in `versions.lock`; re-patch on upstream-bump.
- The direct-path AIR may have subtly different prover behaviour
  (different ordering of polynomial commitments, different FRI tree
  shape) than the bootloader path, affecting wall-clock in ways not
  captured by the `B` constant. Empirical at Phase 1.

## 7. Open questions

- `OPEN-Q-25-1`: Upstream `stwo-cairo` is actively developed; we may
  need to re-patch on upstream bumps. Tracking effort is the same as
  RFC-0006 for SP1.
- `OPEN-Q-25-2`: A future Stwo prover may support `--program_type
  executable` natively (removing the patch). v0.3 ships with the patch;
  v0.4 may deprecate it.
