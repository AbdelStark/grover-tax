# Apples-to-apples target — v0.1 (A2 scope)

## Statement under proof

Both provers prove the same statement against the same fixture:

> "I performed N modular additions in F_p (secp256k1 prime
> `p = 2^256 − 2^32 − 977`), starting from a seed σ₀ derived from
> the fixture's `circuit_byte_serialisation_hex`, producing a final
> state σ_N. I commit `H(circuit_bytes)` (where H is each prover's
> native hash per RFC-0005)."

Concretely:

```
N        = fixture.circuit_byte_serialisation_hex's encoded gate_count
           (= WORKLOAD.md gate_count, today 1024).
σ₀       = SHA-256(circuit_bytes) reduced mod p  on the SP1 side
σ₀       = Blake2s(circuit_bytes) reduced mod p  on the Stwo side
σ_{i+1}  = (σ_i + (i + 1)) mod p
public   = (H(circuit_bytes), N, σ_N)
```

The per-step `(i + 1)` is a deterministic schedule — no per-step
hashing — so the wall-clock measures modular-addition + commitment
work, not random-byte derivation.

## Why this is meaningful for grover-tax

secp256k1's field arithmetic is the load-bearing primitive of every
ECC operation (point-add, scalar-mul, signature verification). N
modular additions over `F_p` is a faithful microbenchmark of that
primitive, at exactly the scale (`gate_count` = 1024) the v0.1
spec budgets for. Same statement on both sides → apples-to-apples
on the *workload* and the *commitment-divergence axis* documented
in RFC-0005.

## Implementation

### SP1 side (`third_party/sp1/program/src/main.rs`)

Uses `ruint::aliases::U256` for the 256-bit field. SHA-256 over
the circuit bytes via SP1's patched `sha2` crate (zero-overhead
syscall inside the zkVM). One `(σ + step) % p` per step. Commits
`(commitment, N, σ_N_be_bytes)` as public values.

### Stwo side (`stwo-side/cairo/src/lib.cairo` + stwo-cairo)

Uses the existing `limbs.cairo` 9×M31 limb representation
(`State = [u31; 9]`, 9 × 31 = 279 bits, enough for any 256-bit
value with carry room). Modular addition mod secp256k1's prime
extends limbs.cairo with `mod_add_secp` (lands in this PR).
Blake2s commitment via the existing `commit.cairo`. Cairo main
returns `(commitment, σ_N)` for the public-input commitments.

The compiled Cairo program is executed and proved by stwo-cairo's
`run_and_prove` driver — a production Circle-STARK prover for the
Cairo CPU.

## What this replaces

The v0.1 MVP (now archived under `headline-runs/2026-05-14/`) had:

- **SP1**: byte-walk over the circuit bytes with a cheap state
  transition per byte. *Not point-add semantics.*
- **Stwo**: wide-Fibonacci AIR sized by `gate_count`. *Not
  point-add semantics either.*

That MVP demonstrated the harness end-to-end. This PR upgrades
both sides to do the same meaningful secp256k1 primitive on the
same fixture.

## What's still out of scope at v0.1

- Real point-additions (each ~50 field-ops; 17M gates upstream)
  blow the single-laptop budget.
- Scalar-mul of secp256k1's generator by a 256-bit secret. Closer
  to upstream's full proof statement but ~256 point-doubles per
  shot.

These are v0.2 milestones once we land budget headroom (multi-hour
proofs or bigger GCE rigs).

## Acceptance criteria

- [ ] `third_party/sp1/program` builds; `prove` produces a proof
  whose committed `σ_N` matches a re-derived `σ_N` computed from
  the fixture in Python.
- [ ] `verifier` accepts the proof and re-asserts the public values.
- [ ] `stwo-side/cairo/src/limbs.cairo::mod_add_secp` passes a
  cross-check against `coincurve` / `ecdsa` Python references on
  20 random 256-bit operands.
- [ ] `scarb cairo-test` is green for the Cairo program.
- [ ] `stwo-cairo` (vendored at `third_party/stwo-cairo`) builds
  and produces a verifiable proof of the Cairo program's execution.
- [ ] Both wrappers (`bin/run_{sp1,stwo}.sh`) drive their prover
  end-to-end against the v0.1 fixture; the harness picks up the
  proofs and `analyze` renders a populated `RESULTS.md` with
  matching committed `σ_N` values on both sides.

## Reproducibility envelope

Single-laptop budget intact: per-prover proof gen budget remains
under the RFC-0008 ceiling. Stwo-cairo's overhead on a 1024-step
trace is well under 1 s; SP1's compressed STARK is well under
the M1-Pro 5-minute zkVM budget.
