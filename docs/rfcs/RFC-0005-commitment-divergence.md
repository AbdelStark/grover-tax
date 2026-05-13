# RFC-0005: Commitment hash divergence (SHA-256 on SP1 side, Blake2s on Stwo side)

- Status: Accepted
- Authors: maintainer
- Created: 2026-05-13
- Target milestone: v0.1

## Summary

The single intentional apples-to-non-apples in `v0.1` is the hash function used to commit to the circuit `C`. The SP1 side uses SHA-256 (the upstream example's native choice). The Stwo side uses Blake2s. Both commitments are computed over the *same* `circuit_byte_serialisation_hex`. Both verifiers bind to their respective hash. The choice is deliberate: implementing SHA-256 in Cairo would dominate the Stwo wall-clock and confound the comparison.

## Motivation

The PRD §6.4 makes this divergence the only deviation from apples-to-apples. This RFC documents *why* the divergence is the right call, considers the alternatives that would eliminate it, and locks the choice.

A reader of `RESULTS.md` who does not understand this divergence will read the headline ratio as "Stwo is faster" without realising part of the ratio is "Stwo skipped the SHA-256 cost". The RFC plus the disclosure in `RESULTS.md` ensure the reader has the information.

## Goals

- Lock the SP1-side commitment to SHA-256 (the upstream example's choice).
- Lock the Stwo-side commitment to Blake2s.
- Make the divergence loud in `RESULTS.md` (apples-to-apples disclosures section, §"Reporting" of `RFC-0011`).
- Make both commitments verifiable out-of-band by any third party from the public `circuit_byte_serialisation_hex`.

## Non-Goals

- Eliminating the divergence. The alternatives that would do so are inferior; see "Alternatives Considered".
- Investigating Poseidon, Rescue, Anemoi, or any other algebraic hash. Those would push the divergence further, not closer.
- Defending SHA-256 in Cairo as a future implementation track. That is its own multi-month project.

## Proposed Design

### What is committed

Both sides compute the digest over the *same byte sequence*: the canonical serialisation of `C` per `RFC-0004` (magic `b"GTV1"`, fixed-size `Gate` records). Bit-identical.

### What each verifier binds to

- SP1 + Groth16 verifier: SHA-256 of `circuit_byte_serialisation_hex`. The upstream example's native commitment; we do not modify this.
- Stwo verifier: Blake2s of `circuit_byte_serialisation_hex`. Computed in-circuit using Stwo Cairo's Blake2s built-in.

### Where in the fixture

Both commitments are stored in `fixtures/v0.1.json`:

```json
{
  "circuit_byte_serialisation_hex": "<hex of the bytes both sides hash>",
  "circuit_commitment_sha256_hex": "<sha256 digest of the above>",
  "circuit_commitment_blake2s_hex": "<blake2s digest of the above>"
}
```

A third party who clones the repo can:

```bash
python -c "import hashlib, sys; data = bytes.fromhex(sys.argv[1]); print('sha256', hashlib.sha256(data).hexdigest()); print('blake2s', hashlib.blake2s(data).hexdigest())" \
  "$(jq -r .circuit_byte_serialisation_hex fixtures/v0.1.json)"
```

and verify both digests against the recorded fields.

### Disclosure in `RESULTS.md`

The "Apples-to-apples disclosures" section of `RESULTS.md` (`RFC-0011`) has a dedicated subsection:

> **Commitment hash function.** SP1 side: SHA-256 (upstream's native choice). Stwo side: Blake2s. Both commit to the same `circuit_byte_serialisation_hex`. Implementing SHA-256 in Cairo would dominate Stwo's wall-clock; Blake2s is bit-oriented and in the same structural family as SHA-2, making the comparison closer in kind than an algebraic hash would.

This is required content. The methodology lint (`M-2`, `07-testing-strategy.md`) fails CI if the text is missing.

## Alternatives Considered

### A1. SHA-256 in Cairo

Add a SHA-256 implementation to the Stwo side and use it for the circuit commitment.

Pros: total apples-to-apples on commitment.

Cons:
- A reasonable SHA-256 implementation in Cairo (e.g., a Stwo-Cairo SHA-2 library) adds order-of-magnitude more constraints than the rest of the workload combined. The headline ratio would become "How fast does Stwo do SHA-256?" rather than "How fast does Stwo do gate-execution?".
- The PRD §6.4 explicitly identifies this as the reason the divergence exists.
- Even if a high-performance SHA-256-in-Cairo library shipped, integrating and validating it would push the project out by months.

Rejected.

### A2. Poseidon (or Rescue, Anemoi) on both sides

Use an algebraic hash, native to STARKs and SNARKs, on both sides.

Pros: cheap inside both provers.

Cons:
- The upstream SP1 example uses SHA-256. Replacing it with Poseidon requires modifying the SP1 patch beyond the < 50-line budget in `RFC-0006`.
- Algebraic hashes have a different threat model from bit-oriented hashes. A reader interpreting the result for "real-world" deployments may be misled — most real workloads commit with bit-oriented hashes (SHA-2/SHA-3), and the Stwo-vs-SP1 ratio for *real* commits is what matters.
- Switching only the Stwo side to Poseidon (and leaving SP1 on SHA-256) is *worse* than the chosen Blake2s — the structural distance to SHA-256 is greater.

Rejected.

### A3. Blake2s on both sides

Replace SP1's SHA-256 with Blake2s on the SP1 side, matching Stwo.

Pros: total apples-to-apples on commitment.

Cons:
- Requires modifying the SP1 example beyond the < 50-line budget in `RFC-0006` (the upstream example builds a SHA-256 commit; replacing the hash function touches both the prover and the verifier, well outside the budget).
- "Replace upstream's native choice" defeats the goal of measuring "how the upstream stack actually performs at the workload it ships".

Rejected.

### A4. Keccak-256 on both sides

Pros: a single SHA-3-family hash, well-defined.

Cons: neither SP1 nor Stwo has a native Keccak path that beats SHA-256 (SP1) and Blake2s (Stwo) respectively. Switching to Keccak would slow both sides without changing the comparison shape. Rejected.

### A5. No in-circuit commitment at all

Pros: simplest. Both sides assert only the test-case equations; the commitment is left out of the proof and proven out-of-band.

Cons: weakens the proof statement (now: "C exists realising these test cases" without binding to a published `C`). A future re-run could substitute a different `C` and the proof would still verify. Rejected as a soundness regression relative to the PRD.

## Drawbacks

- The headline number is *not* a clean comparison. A reader must read the disclosures section to interpret the ratio honestly. We mitigate by making the disclosures section impossible to miss (top of `RESULTS.md`, methodology lint).
- An adversary could argue "Stwo skipped the hash cost"; the reply is "yes, by 0.05 % to 0.1 % of the total proof cost, the structural cost of the comparison is the gate-execution loop, not the hash". The ratio published in `RESULTS.md` includes a separate row breaking down the in-circuit Blake2s cost (estimated via a circuit-without-commitment variant), so the reader can subtract.

## Migration / Rollout

First-time choice. No migration. The choice is the day-1 contract.

If a future release (`v0.2+`) lands a SHA-256-in-Cairo implementation and a parallel run series with it, that release reports two headlines: with-Blake2s (legacy) and with-SHA-256 (apples-to-apples). The two headlines compare to each other to surface the cost of the divergence. `v0.1` does not commit to this future work.

## Testing Strategy

- **D-T1**: A test asserts the fixture's `circuit_commitment_sha256_hex` matches `hashlib.sha256(bytes.fromhex(circuit_byte_serialisation_hex)).hexdigest()`.
- **D-T2**: Same for `blake2s`.
- **D-T3**: A regression vector pins the exact digests for a known 64-byte input on both sides.
- **D-T4**: The methodology lint (`M-2`) asserts the disclosures section of `RESULTS.md` contains the substring "SHA-256" and "Blake2s" within a section heading matching `apples-to-apples`.
- **D-T5**: A Cairo unit test asserts the in-circuit Blake2s output on a fixed input equals the Python `hashlib.blake2s` output.

## Open Questions

None.

## References

- `docs/spec/02-public-api.md` (fixture schema)
- `docs/spec/03-data-model.md` (commitment fields, F-INV-2, F-INV-3)
- `RFC-0002` (fixture generator emits both commitments)
- `RFC-0004` (Cairo Blake2s usage)
- `RFC-0006` (SP1 patch budget)
- `RFC-0011` (RESULTS.md disclosures)
- PRD `PRD.md` §6.4
