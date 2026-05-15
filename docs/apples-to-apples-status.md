# Apples-to-apples status — 2026-05-15

## What's working

### Spec-target kernel (both sides)

Both prover sides implement the same statement and **produce
byte-identical σ_N values vs an independent Python re-derivation**:

```text
p        = 2^256 − 2^32 − 977            (secp256k1 prime)
σ₀       = H(circuit_bytes) reduced mod p
σ_{i+1}  = (σ_i + (i + 1)) mod p          for i ∈ [0, gate_count)
publish  = (H(circuit_bytes), gate_count, σ_N)
```

Where H is each prover's native hash (SHA-256 for SP1, Blake2s for Stwo)
per RFC-0005, `gate_count = 1024` per WORKLOAD.md.

| Side | Status | Cross-check |
|---|---|---|
| **SP1 prover + verifier** | ✅ proves + verifies | Committed σ_N = `0xe95ca553...4321c8` matches Python |
| **Cairo kernel** (via `scarb execute`) | ✅ runs end-to-end | Computed σ.low/σ.high match Python target byte-for-byte |
| **49 Cairo unit tests** | ✅ pass | including 3 new apples-to-apples tests |

### Prover-stack integration

- SP1's full stack (zkVM → compressed STARK → public values) is **green**.
- Stwo's full stack via **`stwo-cairo` `run_and_prove`** hits a format-compatibility wall (next section).

## The stwo-cairo format gap

`third_party/stwo-cairo/` is vendored and its prover binaries
(`run_and_prove`, `verify`) **build cleanly** with the pinned
`nightly-2025-06-23` toolchain. Running `run_and_prove --program_type
executable` against `scarb execute`'s output panics in
`extract_public_segments` (`stwo_cairo_prover/crates/prover/src/witness/cairo.rs:28`):

```text
thread 'main' panicked at crates/prover/src/witness/cairo.rs:28:60:
called `Result::unwrap()` on an `Err` value: TryFromIntError(())
```

`extract_public_segments` reads pointer-typed values from
`memory[initial_ap..initial_ap+N]` and casts them `u128 → u32`. The
scarb-execute output places non-pointer values (function arguments,
locals) at those AP slots, exceeding u32 range.

**Root cause**: stwo-cairo's `--program_type executable` expects
output from `cairo-execute` (the binary built from
[`starkware-libs/cairo`](https://github.com/starkware-libs/cairo)), not
from `scarb execute`. The two tools share the `#[executable]`
attribute but produce subtly different executable.json layouts.

This is verified by stwo-cairo's own
`stwo_cairo_verifier/crates/cairo_verifier_mock/src/lib.cairo` which
documents the `cairo-execute` workflow explicitly:

```text
cairo-execute stwo_cairo_verifier/ --executable stwo_cairo_verifier_mock::main --build-only
cairo-execute --prebuilt path/to/compiled_mock_verifier.json --layout=all_cairo --args-file ...
```

stwo-cairo's known-working test_data `compiled.json` programs are
**Cairo-Zero** format (older `func main{}()`, compiled with
`cairo-compile`) consumed via `--program_type json` — that path is
green out of the box but Cairo-Zero is a different language than the
Cairo 2024_07 we use.

## What's needed to close the gap (v0.2-scope)

Three viable paths. Each is multi-hour.

### Path 1 — Install `cairo-execute` and rebuild the executable

`cairo-execute` lives in `starkware-libs/cairo`; build via `cargo
install --path crates/bin/cairo-execute`. Replace `scarb execute` in
our build with `cairo-execute` and re-test stwo-cairo's
`--program_type executable`. Estimated effort: 2-4 hours (toolchain
install + format diff debugging).

### Path 2 — Rewrite the Cairo program in Cairo-Zero

Use `func main{output_ptr, range_check_ptr, ...}` style + `cairo-compile`.
This is the path stwo-cairo's test_data uses and is known to work
with `--program_type json`. Estimated effort: 4-8 hours (different
language, no `u256` support — must use 128-bit limbs).

### Path 3 — Wait for stwo-cairo to accept scarb-execute output

Track [the stwo-cairo issue tracker](https://github.com/starkware-libs/stwo-cairo/issues)
for native scarb-execute support. Their CI already uses scarb;
the interop gap is a recent discovery, likely to be closed upstream.

## Recommendation

**For v0.1 release**: accept this gap. Document that the SP1 side
proves the full apples-to-apples statement and the Cairo kernel is
verified end-to-end via `scarb execute`; the prover-stack integration
on the Stwo side is gated by the `cairo-execute` toolchain wiring.

The **measurement-substrate MVP** (Stwo proving the wide-Fibonacci
AIR as a proportional stand-in) remains the published v0.1 headline,
with an explicit note in `RESULTS.md`'s apples-to-apples disclosures
that the Stwo proof is structurally proportional to the apples-to-apples
target, not literal.

The full Cairo-via-stwo-cairo loop lands in v0.2.

## Artifact map

```
docs/apples-to-apples-v0.1.md                  design spec (Phase 1/2/3a target)
third_party/sp1/program/src/main.rs            SP1 zkVM apples-to-apples body
third_party/sp1/prover/prove.rs                SP1 driver (gate_count via stdin)
third_party/sp1/verifier/verifier.rs           SP1 verifier with σ_N re-derivation
stwo-side/cairo/src/lib.cairo                  Cairo kernel + #[executable] entry
stwo-side/cairo/Scarb.toml                     scarb executable target wired
third_party/stwo-cairo/                        vendored prover (binaries built)
```
