# grover-tax v0.2 — Master Technical Specification

**Status:** authoritative.
**Supersedes:** the proof-statement, witness-shape, and prover-architecture sections of `PRD.md::§2,§5,§6`; `docs/spec/00-overview.md`; `docs/spec/01-architecture.md`; `docs/spec/02-public-api.md`; `RFC-0003`, `RFC-0004`, `RFC-0006` (gate-execution and patch surface).
**Does not supersede:** the *methodology* RFCs (RFC-0001 workload pin, RFC-0005 commitment divergence, RFC-0007 wrapper contract, RFC-0008 measurement, RFC-0009 single-core, RFC-0010 environmental hygiene, RFC-0011 reporting, RFC-0012 versions lock, RFC-0013 reproducibility, RFC-0014 governance). Those remain load-bearing; this document refers to them by ID where applicable and amends them where RFC-0021 calls for hardening.
**Reading order:** §1 (objective), §2 (statement under proof), §3 (cryptographic ingredients), §4 (system architecture), §5 (equivalence theorem), §6 (security model), §7 (measurement protocol amendments), §8 (reproducibility envelope amendments), §9 (open questions for v0.3).

The detailed normative content lives in the RFCs that this document references. The role of this specification is to be the *single point of truth for what is being proven and why the comparison is fair* at v0.2.

---

## 1. Objective

Produce a publicly verifiable wall-clock comparison of two production STARK-based zero-knowledge proving stacks — Succinct's **SP1** (a RISC-V zkVM with compressed-STARK + optional Groth16 wrap) and Starkware's **Stwo** (a Circle-STARK prover for the Cairo CPU) — on **a single proof statement of bounded size** executed under **strict single-core, no-GPU** hardware constraints on a **named reference rig**.

The headline result is one number:

```
ρ = median_M1(SP1) / median_M1(Stwo)
```

where `median_M1(·)` is the 10-sample wall-clock median of `bin/run_<prover>.sh` measured by `hyperfine` per RFC-0008. The number is meaningful only at the soundness floor and the measurement parameters fixed in this document and in the RFCs it references.

The four success conditions of `PRD.md::§1` remain authoritative; condition 1 ("both provers run end-to-end against a shared fixture file on the reference rig") is reinterpreted at v0.2 to mean "both provers prove the v0.2 statement defined in §2 of this document, against the same `fixtures/v0.2.json` blob, on the reference rig."

---

## 2. Statement under proof

### 2.1 Mathematical definition

Fix a security parameter `λ`. Let `H_SHA256: {0,1}^* → {0,1}^256` denote SHA-256 (FIPS 180-4) and `H_BLAKE2s: {0,1}^* → {0,1}^256` denote BLAKE2s-256 with empty key, empty salt, empty personalization, and 32-byte digest length (RFC 7693 §3).

Let the *gate set* be `G = {NOP, NOT, CNOT, TOFFOLI}` with the following semantics, where `s ∈ {0,1}^256` is the state and `s[i]` denotes the `i`-th bit of `s`:

| Opcode | Encoding | Action on state |
|---|---|---|
| `NOP`  | `0x00` | `s ↦ s` |
| `NOT`  | `0x01` (target `t`, controls ignored) | `s' = s; s'[t] = s[t] ⊕ 1` |
| `CNOT` | `0x02` (target `t`, control `a`) | `s' = s; s'[t] = s[t] ⊕ s[a]` |
| `TOFFOLI` | `0x03` (target `t`, controls `a`, `b`) | `s' = s; s'[t] = s[t] ⊕ (s[a] ∧ s[b])` |

These operations are reversible classical permutations on `{0,1}^256`. We write `apply_gate: {0,1}^256 × G → {0,1}^256` for the action.

Let `GTV1` be the binary serialisation defined in `docs/spec/03-data-model.md::§"Canonical byte serialisation"`: the 4-byte ASCII magic `"GTV1"` followed by a little-endian `u32` gate count `n_g`, followed by `n_g` 8-byte records of the form `(opcode: u8, pad: u8 = 0, target: u16_le, ctrl_a: u16_le, ctrl_b: u16_le)`. For an opcode that ignores a control field, the control value `0xFFFF` is reserved as a sentinel and is the *only* legal value the field may take (RFC-0016 §4).

Let `parse_gtv1: {0,1}^* → (G^* ∪ ⊥)` denote the partial deserialisation that returns the gate sequence on a well-formed input and `⊥` otherwise.

Let `simulate: G^* × {0,1}^256 → {0,1}^256` denote the left-to-right composition of `apply_gate` over a gate sequence.

**Public statement `Φ_v0.2`.** Given public inputs

- `cb ∈ {0,1}^*` — the circuit byte serialisation,
- `h ∈ {0,1}^256` — the claimed commitment,
- `n_tc ∈ ℕ` — the number of test cases,
- `T = ((x_1, y_1), …, (x_{n_tc}, y_{n_tc})) ∈ ({0,1}^{256} × {0,1}^{256})^{n_tc}`,

the prover claims (and the verifier checks):

```
Φ_v0.2(cb, h, n_tc, T) :⇔
    h = H_*(cb)                          (commitment binding; H_* = H_SHA256 for SP1, H_BLAKE2s for Stwo)
∧   parse_gtv1(cb) = C ≠ ⊥                (well-formed serialisation)
∧   |C| = n_g where cb[4..8] = n_g_le     (length consistency)
∧   ∀ i ∈ [1..n_tc]:  simulate(C, x_i) = y_i.
```

All four conjuncts are normative. The v0.2 prover programs (RFC-0016, RFC-0017) check all four; the v0.2 verifiers re-check the first conjunct and inherit the rest from the prover's circuit constraints.

### 2.2 The two-hash divergence (the only intentional non-apples)

The two provers prove `Φ_v0.2` with two different choices of `H_*`:

| Side | `H_*` |
|---|---|
| SP1 | `H_SHA256` (FIPS 180-4) |
| Stwo | `H_BLAKE2s` (RFC 7693, 32-byte digest, empty key/salt/personalization) |

The fixture publishes both digests (`circuit_commitment_sha256_hex` and `circuit_commitment_blake2s_hex`), computed over **bit-identical** `cb`. Any third party can independently recompute both and verify the proof's binding on either side using a single line of standard tooling (RFC-0005 §"Third-party verification recipe").

This is the *single* intentional cryptographic divergence between the two sides at v0.2. RFC-0019 §5 quantifies its expected cost on each side and requires that `RESULTS.md` carries a disclosed breakdown row.

### 2.3 Witness layout

The witness on either side consists of `cb` plus the test-case bytes `T`. Neither side treats any input as a zero-knowledge witness in v0.2 — see §6.2. `cb` is bound by the commitment `h`; the test-case bytes are bound to the proof by being committed-or-asserted public inputs (RFC-0017 §4 and RFC-0019 §6.2 specify how each side anchors `T` so that a verifier cannot be tricked by a substituted test set).

---

## 3. Cryptographic ingredients

### 3.1 Hash functions

| Function | Spec | Where used |
|---|---|---|
| SHA-256 | FIPS 180-4 | SP1 circuit-commitment; fixture cross-check |
| BLAKE2s-256 | IETF RFC 7693 | Stwo circuit-commitment; fixture cross-check |
| SHAKE-256 | FIPS 202 | Fixture XOF used by `gen_fixtures.py` (RFC-0021 §16 retires the RFC-0002 ambiguity) |
| Pedersen (Stark-friendly) | Starkware Pedersen (`starknet_types_core`) | Bootloader's `program_hash_function` (RFC-0022 §3) |
| Poseidon | (not used) | — |

The bootloader's use of Pedersen is *internal* to the Stwo stack: it commits the task program to the bootloader's public input. It does **not** weaken the commitment binding stated in §2.2, which is exclusively BLAKE2s on the Stwo side. RFC-0019 §5.3 spells this out; RFC-0022 §3 documents the bootloader-internal commitment chain.

### 3.2 Proof systems

| Component | Identity | Soundness floor (v0.2) | Notes |
|---|---|---|---|
| SP1 prover backend | `sp1-sdk` v6.0.2, compressed-STARK | ≥ 100 bits conjectured against FRI + grinding (RFC-0019 §2) | Optionally Groth16-wrapped (`SP1_USE_GROTH16=1`); v0.2 defaults to compressed STARK |
| Stwo prover backend | `stwo-cairo` at pinned commit (via `third_party/stwo-cairo/`), Circle STARK | ≥ 100 bits conjectured against Circle-FRI + grinding (RFC-0019 §2) | Bootloader-driven via `stwo-run-and-prove` from `third_party/proving-utils/` |

The soundness floor is *conjectured*, not unconditionally proven: both stacks rely on FRI's `(δ, q, η)`-soundness conjecture (Ben-Sasson et al., DEEP-FRI, BCIKS20) at the parameters their respective implementations select. RFC-0019 §2 reproduces the conjectured-vs-proven boundaries and forbids any RFC-0007 wrapper exit-code-0 path from being accepted at a parameter set whose conjectured soundness drops below 100 bits.

### 3.3 Fields

| Side | Field `𝔽` | `|𝔽|` | Notes |
|---|---|---|---|
| SP1 | BabyBear, `p = 2^31 − 2^27 + 1` | 31-bit prime | Workspace constraint of SP1; non-tunable |
| Stwo | Mersenne-31, `p = 2^31 − 1` | 31-bit prime | Workspace constraint of Stwo Circle-STARK; non-tunable |

The 256-bit gate-execution state is represented per side as:

- **SP1:** `[u8; 32]` little-endian byte array (host language) reduced to per-bit boolean witnesses inside the constrained zkVM trace; SP1's RISC-V cycle model provides byte-and-bitops natively.
- **Stwo:** `State = [u31; 9]` (9 × 31-bit M31 limbs, total 279 bits of capacity, 23 bits of carry slack). Bit `i` lives at limb `i / 31`, position `i mod 31`. The mapping is fixed in `io.cairo::bytes_to_state` and `state_to_bytes`; the algebraic representation is normative in RFC-0016 §3.

Field choice is *structural to the prover* and was justified in RFC-0011 §"Disclosures #2"; no v0.2 amendment is required.

---

## 4. System architecture (v0.2)

### 4.1 Data flow

```
                  ┌─────────────────────────────────────┐
                  │ python/grover_tax/gen_fixtures.py   │
                  │  SHAKE-256(SEED) → cb, T, hashes    │  (RFC-0002 + RFC-0021 §16)
                  └────────────────┬────────────────────┘
                                   │
                          fixtures/v0.2.json
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                                         ▼
   ┌───────────────────────┐                ┌──────────────────────────────┐
   │ SP1 path              │                │ Stwo path                    │
   │                       │                │                              │
   │ bin/run_sp1.sh        │                │ bin/run_stwo.sh              │
   │   │                   │                │   │                          │
   │   ▼                   │                │   ▼                          │
   │ third_party/sp1/      │                │ bin/apples-prove             │
   │   prover/prove.rs     │                │   │                          │
   │  ┌──────────────────┐ │                │   ├─ python: build bootloader│
   │  │ zkVM program     │ │                │   │   SimpleBootloaderInput  │
   │  │  (gate sim)      │ │                │   │   (task: Cairo1Executable│
   │  └──────────────────┘ │                │   │    pointing at the scarb-│
   │   │                   │                │   │    built executable.json)│
   │   ▼                   │                │   │                          │
   │ groth16-able compressed STARK proof    │   ▼                          │
   │   (or compressed-STARK only)           │ third_party/proving-utils/   │
   │                                        │   stwo-run-and-prove         │
   │                                        │   │                          │
   │                                        │   ▼                          │
   │                                        │ Circle STARK proof           │
   │                                        │   (bootloader-mediated)      │
   └────────────┬──────────────────────────┘└──────────────┬──────────────┘
                ▼                                          ▼
        ┌─────────────────────────────────────────────────────────┐
        │ scripts/measure.sh  (RFC-0008 amended by RFC-0021 §§3-11)│
        │   hyperfine M1, M5 ; gnu-time M2/M3/M4 ; stat M6 ; ...   │
        └────────────────────────────┬────────────────────────────┘
                                     ▼
                              RESULTS.md   (RFC-0011)
```

The architecture differs from `docs/spec/01-architecture.md::"Data-flow hops"` in three load-bearing ways:

1. The Stwo path is **bootloader-mediated** (RFC-0022). The "Circle-STARK prover proves a Cairo program" model is now "Circle-STARK prover proves a Cairo bootloader running a Cairo task whose code is the apples-to-apples kernel."
2. The SP1 side is a freshly authored zkVM program (`third_party/sp1/program/`), not a patch against `tanujkhattar/zkp_ecc` (RFC-0017).
3. The fixture format is `v0.2.json` (same schema as v0.1, but `circuit_byte_serialisation_hex` now encodes a 1024-gate random circuit, not a point-addition gate list).

### 4.2 Component pinning

| Component | Pin | Source |
|---|---|---|
| Rust toolchain (root + Stwo + proving-utils) | `nightly-2025-07-14` | `rust-toolchain.toml` |
| Rust toolchain (SP1) | `1.93.0` | `third_party/sp1/rust-toolchain` |
| Scarb | `2.15.1` (Cairo 2.15.0) | `versions.lock` (RFC-0021 §9) |
| SP1 SDK | `sp1-sdk = "6.0.2"` | `third_party/sp1/prover/Cargo.toml` |
| `sp1up`-installed RISC-V toolchain | SHA-256 of installed binary | `versions.lock::sp1.toolchain_sha256` (RFC-0021 §3) |
| Stwo (via stwo-cairo) | commit SHA at `third_party/stwo-cairo/` | `versions.lock::stwo.commit` (RFC-0012 §3) |
| proving-utils | committed `Cargo.lock` + workspace member set | RFC-0021 §1 |
| Python | `>=3.12,<3.14` (CPython) | `pyproject.toml` + `uv.lock` |
| `uv` | binary SHA-256 + version | `versions.lock::uv` (RFC-0012) |

Every binary entering a measured run is bound by one of these pins. The drift gate in `scripts/preflight.sh` (RFC-0010, amended by RFC-0021 §1) refuses to enter the measurement window if any pin mismatches.

---

## 5. Equivalence theorem ("why is this apples-to-apples")

### 5.1 Statement

**Theorem (operations-counted equivalence; informal).** Fix a gate set `G = {NOP, NOT, CNOT, TOFFOLI}`, a state width `w = 256`, a gate count `n_g = 1024`, a test-case count `n_tc = 4`. Let `Π_SP1` and `Π_Stwo` be the SP1 and Stwo provers as specified in RFC-0017 and RFC-0016 respectively. There exist a constant `c_SP1 ∈ ℝ_+` (RISC-V cycles per executed gate plus per-cycle SP1 trace rows) and a constant `c_Stwo ∈ ℝ_+` (M31 trace rows per executed gate plus bootloader overhead) such that the *constraint count* of either prover's argument for `Φ_v0.2` is

```
constraints(Π_SP1)   = c_SP1   · n_tc · n_g + O(|cb|)     (RISC-V execution trace)
constraints(Π_Stwo)  = c_Stwo  · n_tc · n_g + O(|cb|) + O(bootloader_cycles)
```

with the `O(|cb|)` term capturing the commitment-hash cost on each side. The ratio `c_SP1 / c_Stwo` is the apples-to-apples primitive of the headline.

RFC-0018 §2 supplies the formal version, with `c_SP1`/`c_Stwo` derived from each prover's trace-row count function and the proof that no additional "free" advantage is smuggled in (e.g., gate-loop unrolling, opcode-specific fast paths, asymmetric range-check sharing).

### 5.2 What the equivalence does *not* assert

- It does **not** assert that proof bytes, proof structure, or the polynomial arguments are isomorphic. They are not. SP1 uses BabyBear + AIR; Stwo uses M31 + Circle AIR + bootloader.
- It does **not** assert equal soundness at the same parameters. Both stacks meet a 100-bit conjectured soundness floor (RFC-0019 §2), but the FRI parameter selections differ.
- It does **not** assert equal zero-knowledge. v0.2 makes no ZK claim (§6.2).
- It does **not** assert that the wall-clock ratio `ρ` equals `c_SP1 / c_Stwo`. The constants in §5.1 are *constraint counts*; the wall-clock includes constant-factor differences in arithmetisation, FFT layout, hashing, and (on Stwo) bootloader cycles. RFC-0018 §3 separates "constraint-counted ratio" from "wall-clock ratio" and requires both be reported.

### 5.3 What the equivalence is asserting

Subject to the disclosed divergences (commitment hash, field, bootloader), both provers expend computational effort that is *linear* in `n_tc · n_g` on the *same* gate dispatcher applied to *bit-identical* circuit bytes and *bit-identical* test-case inputs. RFC-0018 §2 establishes that:

1. Both implementations consume the entire `cb` (no shortcut for length).
2. Both compute the same 32-byte commitment digest function `H_*` over `cb` (with `H_*` differing only as in §2.2).
3. Both call `apply_gate` exactly once per gate per test case (no opcode-specific shortcut; NOP costs the same as TOFFOLI; RFC-0016 §6 and RFC-0017 §3 enforce this).
4. Both assert `simulate(C, x_i)[0..32] = y_i[0..32]` for every `i`.

Conditions (1)–(4) together are the operational meaning of "apples-to-apples" at v0.2.

---

## 6. Security model

### 6.1 Soundness floor

Both provers MUST be invoked with prover-backend parameter sets whose conjectured soundness at the published `circuit_byte_serialisation_hex` and `n_tc` is ≥ **100 bits**. RFC-0019 §2 specifies how the soundness floor is computed from each backend's FRI / Circle-FRI parameters and how `versions.lock` records the parameter set used. A run series that would publish a `RESULTS.md` whose proofs were generated below the 100-bit floor MUST be discarded with `MEASUREMENT.SOUNDNESS_FLOOR_BREACH` (new exit-code in the amended `04-error-model.md`, RFC-0021 §17).

### 6.2 Zero-knowledge: explicitly **not** claimed at v0.2

The fixture publishes `circuit_byte_serialisation_hex` in cleartext. Both prover programs consume `cb` as *public input*, not as a hidden witness. The proofs are arguments-of-knowledge for a public NP statement, not zero-knowledge proofs.

The glossary entry "Zero-knowledge proof" and the language in `PRD.md::§2` referring to "without revealing the gate-list of C" are amended in RFC-0021 §15 to remove the ZK claim from v0.2. A future v0.3 may reintroduce a ZK statement (see §9), at which point the gate list would be witness-only and a separate commitment opening would be the public input.

### 6.3 Threat model (extended; full version in RFC-0020)

Adversaries considered at v0.2:

| Adversary | Defended by |
|---|---|
| `A_fixture`: PR that adjusts `fixtures/v0.2.json` to favour one side | `gen-fixtures --check` (RFC-0002), F-INV-2 (`fixture-v0.1.schema.json`), CI gate |
| `A_toolchain`: substitution of a prover backend | `versions.lock` + `preflight.sh` drift gate (RFC-0012 + RFC-0021 §1, §3) |
| `A_wrapper`: asymmetric change to one wrapper | RFC-0007 symmetry test |
| `A_measurement`: tampering with `measure.sh` | Reproducer can re-run `scripts/measure.sh` and check `RESULTS.md` regenerates |
| `A_statement`: prover proves a weaker statement whose verifier still returns 0 | RFC-0019 §6 (verifier-side public-input cross-check), RFC-0020 §3 |
| `A_setup`: substitution of Groth16 proving/verifying keys | `versions.lock::groth16_ceremony_origin` + RFC-0021 §3 |
| `A_supplychain`: compromise of crate or installer | Partial: lockfiles + SHA-256 pins; full SLSA-3 deferred to v0.3 |

Adversaries explicitly out of scope at v0.2:

- Side-channel attackers (cache-timing, power, EM). The reference rig is single-tenant, AC-powered, network-off; this is not an adversarial setting.
- A malicious reference-rig operator. The benchmark is one human; second-party verification of the actual measurement event is future work.
- Cryptographic breaks of SHA-256, BLAKE2s, or the underlying FRI primitives.

RFC-0020 §2 gives the precise advantage definitions for each in-scope adversary; RFC-0020 §3 specifies the test obligations that each defence imposes.

---

## 7. Measurement-protocol amendments

The v0.2 measurement protocol is RFC-0008 with the following amendments, normatively specified in RFC-0021:

1. **Fixture path is parameterised**, not hard-coded. `FIXTURE_PATH=${FIXTURE_PATH:-fixtures/v0.2.json}` in `measure.sh`; assertion `jq -e '.version == "v0.2"' < "${FIXTURE_PATH}"` in `preflight.sh`. (RFC-0021 §4)
2. **M7 grammar is satisfied by parsing the real prover stdout**, not by wrapper-synthesised sentinels. The SP1 wrapper extracts `CONSTRAINTS:` from `sp1-sdk`'s `RUST_LOG=info` output; the Stwo wrapper extracts `TRACE_ROWS:` from `stwo-cairo`'s bootloader-and-task trace summary line. The `gate_count`-sentinel emission at `bin/apples-prove:163-171` is removed. (RFC-0021 §5)
3. **Within-series trend detection.** After the 10-sample M1 series, `analyze.py` runs a Mann-Kendall trend test on the 10 measured points. A `p < 0.01` two-sided result is flagged `[WARMING_TREND]` in `RESULTS.md` and lowers the run-series confidence rating to `B`. (RFC-0021 §6)
4. **Day-1 / day-2 stability gate uses a bootstrap CI.** The 5%-delta rule is replaced by a 95%-bootstrap-CI exclusion of the 5% threshold. (RFC-0021 §11)
5. **macOS affinity assertion is dropped.** The wrapper invokes `taskpolicy -c utility …` and records the invocation; it does not attempt to read the running process's QoS class (which has no public API). The disclosure paragraph in `RESULTS.md` notes this irreducible gap (RFC-0009 amendment in RFC-0021 §7).
6. **Soundness-floor assertion at preflight.** `preflight.sh` reads `versions.lock` and computes the conjectured soundness of the SP1 and Stwo parameter sets; aborts with `MEASUREMENT.SOUNDNESS_FLOOR_BREACH` if either is below 100 bits. (RFC-0019 §2.4, RFC-0021 §17)
7. **`iostat.json` schema added** at `docs/spec/schemas/iostat-v1.schema.json`; `analyze.py` validates it. (RFC-0021 §8)
8. **`discards-v1.schema.json` adds `affinity_miss`** and `soundness_floor_breach` to the `reason` enum. (RFC-0021 §10)
9. **`versions-lock-v1.schema.json` adds `host.os_build` and `sp1.toolchain_sha256`** (RFC-0021 §§3, 9).

---

## 8. Reproducibility-envelope amendments

RFC-0013's three-tier envelope is retained. The amendments live in RFC-0021:

- **Tier 1 (byte-stable)** gains the requirement that `third_party/proving-utils/Cargo.lock` be committed (currently `.gitignore`'d). Without this, byte-stability of build artefacts is impossible for any user cloning after a transitive crate version bump. RFC-0021 §1.
- **Tier 2 (number-stable)** gains the requirement that `os_build` be recorded with the precise macOS marketing version. A different macOS major version is not Tier-2-equivalent. RFC-0021 §14.
- **Tier 3 (distribution-stable)** gains the formal equivalence-class definition for the reference rig: chip SKU + core count + memory size + firmware version. RFC-0021 §13.

---

## 9. Open questions for v0.3

| Tag | Question | Owner | Trigger for resolution |
|---|---|---|---|
| `OPEN-Q-v0.3-1` | Reintroduce ZK by hiding the gate list and committing only `H(C)` as public input | proof-design | After v0.2 headline lands |
| `OPEN-Q-v0.3-2` | Replace XOF-random circuit with a real secp256k1 point-addition gate net (~17 M gates) and a per-test-case proof recursion | proof-design | Co-dependent with `OPEN-Q-v0.3-3` |
| `OPEN-Q-v0.3-3` | Distributed / multi-rig measurement protocol | methodology | When second-party reproduction becomes a requirement |
| `OPEN-Q-v0.3-4` | SLSA-3 release flow + Sigstore artefact signing | governance | After CI matrix gains release-job (RFC-0014) |
| `OPEN-Q-v0.3-5` | Cross-prover parameter equivalence (FRI blowup, num queries) at matching soundness; today's pins are upstream defaults | proof-design | RFC-0019 §2 anchors the analysis |
| `OPEN-Q-v0.3-6` | Replace conjectured FRI soundness with provable bounds (BBHR18 lower bounds) where available | proof-design | Tracking academic state of the art |

Every `OPEN-Q-v0.3-*` is informational; none blocks v0.2.

---

## 10. Document index for v0.2

| Document | Role |
|---|---|
| `docs/spec/v0.2/SPEC-v0.2.md` (this) | Master technical specification for v0.2 |
| `docs/spec/v0.2/GAP-ANALYSIS.md` | Catalogue of every drift and gap relative to the existing v0.1 corpus |
| `docs/rfcs/RFC-0015-v0.2-proof-statement.md` | Formal statement-under-proof (§2) |
| `docs/rfcs/RFC-0016-cairo-gate-execution-air.md` | Stwo-side AIR for v0.2 |
| `docs/rfcs/RFC-0017-sp1-gate-execution-program.md` | SP1-side zkVM program for v0.2 |
| `docs/rfcs/RFC-0018-operations-counted-equivalence.md` | Apples-to-apples equivalence theorem (§5) |
| `docs/rfcs/RFC-0019-soundness-zero-knowledge.md` | Security parameters, ZK scope, commitment cost |
| `docs/rfcs/RFC-0020-threat-model-extended.md` | Extended adversary catalogue (§6) |
| `docs/rfcs/RFC-0021-reproducibility-hardening.md` | Lockfile, schemas, measurement amendments (§§7-8) |
| `docs/rfcs/RFC-0022-bootloader-integration.md` | Stwo bootloader path (§4) |

Read in order if implementing; read SPEC-v0.2.md and RFC-0015/0018/0019/0020 if reviewing the cryptographic claim.

---

## 11. Status

`v0.2` — specification frozen on the date this file enters `main`. Implementation issues for each RFC will be filed under `docs/roadmap/IMPLEMENTATION.md::v0.2`. The current v0.2 *implementation* exists in the tree (commits `c5fff05` and ancestors) and is partially compliant; RFC-by-RFC compliance status will be tracked in a `docs/spec/v0.2/COMPLIANCE.md` follow-up.
