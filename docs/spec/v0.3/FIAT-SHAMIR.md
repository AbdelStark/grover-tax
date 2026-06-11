# In-proof Fiat-Shamir test-case derivation

**Status:** normative for the Tier-2 Khattar-benchmark statement (KB-9, #121).
**Companion:** `KHATTAR-BENCHMARK-ALIGNMENT.md` §2 (G2), `getting_started.md`
§"Using Fuzz Testing as a Proof Strategy".

## Why

The reference benchmark's soundness rests on the prover **not** choosing its own
test inputs. If Alice could pick the `(x, y)` pairs her circuit is fuzzed on, she
could simply avoid the inputs it gets wrong. The reference closes this by
deriving the inputs *inside the proof* as a one-way function of the circuit, via
the Fiat-Shamir heuristic: seed a CSPRNG/XOF with `H(circuit)` and read the test
inputs from it. Finding a flawed circuit whose Fiat-Shamir-derived inputs happen
to dodge its bugs is intractable when bugs are common.

grover-tax's Tier-1 path *supplies* the cases in the fixture (a disclosed
divergence). Tier-2 closes it: the cases are derived in-proof on both stacks.

## Algorithm

```
derive_cases(H, width, num_samples):
    xof   = SHAKE-256(H)                 # H = the circuit hash (seed)
    nbyte = ceil(width / 8)
    for _ in range(num_samples):
        x = int.from_bytes(xof.read(nbyte), "little") & (2^width - 1)
        y = int.from_bytes(xof.read(nbyte), "little") & (2^width - 1)
        yield (x, y)
```

- **XOF**: SHAKE-256 (FIPS 202), the same primitive grover-tax already uses for
  fixture randomness (`grover_tax.xof`). `XOF(H).read(n) == hashlib.shake_256(H).digest(n)`.
- **Seed `H`**: the circuit hash. We use `kmx_source_sha256` — SHA-256 over the
  **raw `.kmx` bytes** — so the seed is byte-identical to upstream's circuit
  commitment (see `COMMITMENT-POLICY.md`).
- **Operand layout**: `x` then `y`, each `ceil(width/8)` little-endian bytes
  masked to `width` bits — identical to the supplied-case layout
  (`grover_tax.registers.iadd_test_cases`), differing only in the seed.
- The expected output is **not** derived; the prover computes it by running the
  circuit and the verifier trusts the in-proof simulation.

## Cross-stack obligation

All implementations MUST produce byte-identical case streams for a given
`(H, width, num_samples)`:

| Stack | Implementation | Status |
|---|---|---|
| Host / reference | `grover_tax.fiat_shamir.derive_cases` (Python, `hashlib.shake_256`) | ✅ landed |
| SP1 (Rust) | `kickmix::fiat_shamir::derive_cases` (pure-Rust SHAKE-256) | ✅ landed; byte-for-byte cross-vector vs the Python reference |
| Stwo (Cairo) | in-circuit SHAKE-256 | ⏳ aligned under KB-13 (#125) — reuse Tanuj's exact XOF so the two Cairo programs prove the identical statement |

### Shared cross-vector (regression anchor)

`seed = sha256("iadd64-demo")`, `width = 64`, `num_samples = 4`:

```
case0: x=4113191057548519565   y=17909937566100645171
case1: x=1222146416732106357   y=15712575212200367868
case2: x=3544430547654831529   y=45149841657852178
case3: x=18158939369488272335  y=16905458393758049869
```

Asserted by `python/tests/test_fiat_shamir.py` and
`kickmix/src/fiat_shamir.rs` (`derive_cases_matches_python_reference`). SHAKE-256
itself is anchored to the FIPS-202 vectors `shake_256("")`/`shake_256("abc")`.

## Fixture impact

For the Tier-2 statement the fixture omits `test_cases` entirely; it carries only
the circuit (commitment + bytes), `num_samples`, `width`, and the demanded
resource bounds (KB-10/#122). The verifier re-derives the cases from the
committed circuit hash, so there is nothing for the prover to fix.
