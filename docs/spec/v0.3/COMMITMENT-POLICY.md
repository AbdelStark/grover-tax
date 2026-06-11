# Commitment policy for the repeated-addition (Khattar) fixtures

**Status:** normative for the `v0.3-iadd` fixture series (KB-4, #116).
**Companion:** RFC-0005 (commitment divergence), `KHATTAR-BENCHMARK-ALIGNMENT.md` §2.

## The problem

The upstream reference (`tanujkhattar/zkp_ecc`) commits the circuit by hashing
the **raw `.kmx` bytes**: its SP1 program computes `sha256(circuit_kmx_bytes)`
and exposes it as a public output. grover-tax's prover side, however, consumes
the **GTV1** binary gate-list (`grover_tax.serialise`), whose bytes necessarily
differ from the `.kmx` source text. So `sha256(GTV1) != sha256(.kmx)`.

If we committed only the GTV1 hash, our public commitment would not line up with
upstream's, defeating the point of a head-to-head comparison.

## The policy

Each `v0.3-iadd` fixture carries **both** commitments, with distinct roles:

| Field | Hashed input | Role |
|---|---|---|
| `kmx_source_sha256` | the **raw single-repetition `.kmx` bytes** | **Cross-comparable** with upstream `sha256(iadd64.kmx)`. This is the *recommended* commitment for the benchmark statement. |
| `circuit_commitment_sha256_hex` | our **GTV1 bytes** of the K-repeated circuit | SP1-side internal integrity (the bytes the prover actually executes). |
| `circuit_commitment_blake2s_hex` | our **GTV1 bytes** of the K-repeated circuit | Stwo-side internal integrity (Blake2s is cheaper in-Cairo, RFC-0005). |

**Recommendation:** when reporting the benchmark statement, cite
`kmx_source_sha256` as *the* circuit commitment, since it is byte-identical to
what upstream commits. The GTV1 hashes are integrity checks over the artifact we
run, not part of the cross-stack comparison.

## Repetition and the raw hash

`kmx_source_sha256` is deliberately computed over the **single** `iadd64.kmx`
source, not over K concatenated copies — there is no canonical multi-repetition
`.kmx` file upstream. The repetition count `K` is recorded separately
(`repetitions`), so the committed statement is "the upstream circuit with
SHA-256 `h`, applied `K` times". A K-fold repeated adder applied to `(x, y)`
computes `(x + K·y mod 2^width, y)`; the fixture's `y_hex` is produced by running
the actual K-repeated GTV1 circuit, so it stays self-consistent for any `K`.

## Tier-2 forward path

The full-fidelity statement (KB-9/#121, KB-10/#122) will additionally commit the
resource-certification outputs (`num_samples`, `max_qubit_count`,
`max_non_clifford_count`, `max_circuit_instructions`). The fixture already
carries the forward-looking `demanded_*` bounds so those verifiers can be wired
without another schema bump.
