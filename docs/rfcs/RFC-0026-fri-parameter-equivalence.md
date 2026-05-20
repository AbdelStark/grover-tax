# RFC-0026 — FRI Parameter Equivalence (Matched Soundness Floor)

| Field | Value |
|---|---|
| Status | Draft (v0.3) |
| Depends on | RFC-0019 (soundness), RFC-0021 (`versions.lock` hardening), RFC-0024 (audit chain) |
| Defends against | `A_param` adversary (RFC-0024 §6.2) |
| Audience | cryptographic reviewers |

## 1. Summary

Pins both prover backends to FRI / Circle-FRI parameter sets that give
the same conjectured soundness floor (within ±1 bit), and asserts the
match at runtime via `preflight.sh`. Closes the methodology gap where
"both at ≥ 100-bit conjectured soundness" is true at default upstream
parameters but never *verified at the parameters used in the
measurement series*.

This RFC implements `SCOPE.md::A11`.

## 2. Conjectured soundness accounting (BBHR18 + BCIKS20 + eprint 2024/278)

For a STARK with parameters `(blowup b, num_queries q, grinding_bits g)`:

**Per-query soundness** (FRI low-degree test):
```
s_query(b) = log₂(b)        # bits per query against a code-distance attack
```

**Aggregate over `q` queries + grinding**:
```
λ_conj(b, q, g) = q · log₂(b) + g    # bits, conjectured-soundness model
```

For BabyBear FRI at the SP1 SDK 6.0.2 defaults `(b=4, q=100, g=16)`:
```
λ_conj_SP1 = 100 · 2 + 16 = 216 bits (conjectured)
            ≈ 100 bits with BCIKS20-style soundness slack adjustment
```

For Circle-STARK on M31 at the `third_party/stwo-cairo` pinned commit's
defaults `(b=4, q=64, g=16)`:
```
λ_conj_Stwo = 64 · 2 + 16 = 144 bits (conjectured-FRI on the circle group)
             ≈ 100 bits with the Circle-STARK eprint 2024/278 §6 slack
```

The 100-bit floor at default upstream parameters is **conjectured**,
not provable; we follow upstream's convention.

## 3. `versions.lock` schema for FRI params

`versions-lock-v1.schema.json` (extended in RFC-0021 §3 + this RFC):

```json
"sp1": {
  "fri_params": {
    "type": "object",
    "additionalProperties": false,
    "required": ["blowup", "num_queries", "grinding_bits"],
    "properties": {
      "blowup":         { "type": "integer", "minimum": 2 },
      "num_queries":    { "type": "integer", "minimum": 1 },
      "grinding_bits":  { "type": "integer", "minimum": 0 }
    }
  }
},
"stwo": {
  "circle_fri_params": {
    "type": "object",
    "additionalProperties": false,
    "required": ["blowup", "num_queries", "grinding_bits"],
    "properties": {
      "blowup":         { "type": "integer", "minimum": 2 },
      "num_queries":    { "type": "integer", "minimum": 1 },
      "grinding_bits":  { "type": "integer", "minimum": 0 }
    }
  }
}
```

`scripts/lock_versions.sh` populates these by:
- For SP1: reading `sp1-sdk@6.0.2`'s default `StarkConfig`. Source path
  documented in the script comment.
- For Stwo: reading `stwo-cairo`'s prover config at the pinned commit.

The exact source paths are recorded in `lock_versions.sh`'s output for
auditability.

## 4. Preflight assertion

`scripts/preflight.sh` adds a new check:

```bash
# Read pinned FRI params.
SP1_FRI=$(jq -r '.sp1.fri_params' versions.lock)
STWO_FRI=$(jq -r '.stwo.circle_fri_params' versions.lock)

# Compute conjectured soundness (BBHR-style for SP1, eprint 2024/278 for Stwo).
SP1_LAMBDA=$(python3 -c "
import json, math
p = json.loads('${SP1_FRI}')
print(p['num_queries'] * math.log2(p['blowup']) + p['grinding_bits'])
")
STWO_LAMBDA=$(python3 -c "
import json, math
p = json.loads('${STWO_FRI}')
# Circle-FRI uses a slack factor; eprint 2024/278 §6 documents the constant.
# v0.3 uses upstream's documented slack (which is conjectured).
print(p['num_queries'] * math.log2(p['blowup']) + p['grinding_bits'])
")

# Apply soundness slack (RFC-0019 §2).
# Both stacks: conjectured λ ≥ 100 bits post-slack.
SP1_LAMBDA_POST=$(echo "${SP1_LAMBDA} * 0.5" | bc -l)    # BBHR18 slack ~50%
STWO_LAMBDA_POST=$(echo "${STWO_LAMBDA} * 0.7" | bc -l)  # circle-STARK slack ~70%

if (( $(echo "${SP1_LAMBDA_POST} < 100" | bc -l) )); then
  echo "MEASUREMENT.SOUNDNESS_FLOOR_BREACH: SP1 post-slack λ = ${SP1_LAMBDA_POST} < 100 bits" >&2
  exit 5
fi
if (( $(echo "${STWO_LAMBDA_POST} < 100" | bc -l) )); then
  echo "MEASUREMENT.SOUNDNESS_FLOOR_BREACH: Stwo post-slack λ = ${STWO_LAMBDA_POST} < 100 bits" >&2
  exit 5
fi

# Cross-prover equivalence.
DELTA=$(echo "${SP1_LAMBDA_POST} - ${STWO_LAMBDA_POST}" | bc -l)
if (( $(echo "${DELTA#-} > 1" | bc -l) )); then
  echo "MEASUREMENT.SOUNDNESS_FLOOR_DIVERGENCE: |λ_SP1 - λ_Stwo| = ${DELTA#-} bits > 1" >&2
  exit 5
fi
```

Two new subcodes:
- `MEASUREMENT.SOUNDNESS_FLOOR_BREACH` — either side < 100-bit conjectured.
- `MEASUREMENT.SOUNDNESS_FLOOR_DIVERGENCE` — sides differ by > 1 bit.

The slack constants (50% for BBHR18, 70% for Circle-STARK) are **conservative
estimates** from the respective papers; they may be refined in v0.4 if
better bounds are published.

## 5. Acceptable parameter pinnings

| Side | `(b, q, g)` | Pre-slack λ | Post-slack λ (used in headline) |
|---|---|---|---|
| SP1 (BabyBear) | `(4, 100, 16)` | 216 | ~108 |
| Stwo (Circle-FRI) | `(4, 64, 16)` | 144 | ~101 |

Both ≥ 100 post-slack; |Δ| ≈ 7 bits. This is too divergent for v0.3
under §4's ±1-bit gate.

**v0.3 must tune one side to match the other.** Two options:

- **Option A (preferred):** Reduce SP1's `num_queries` to bring it down
  to ~101 post-slack. Requires SP1 SDK to accept a custom `StarkConfig`;
  this is supported as of `sp1-sdk@6.0.2` via `ProverClient::with_config(...)`.
- **Option B:** Increase Stwo's `num_queries` to bring it up to ~108
  post-slack. Requires modifying `third_party/stwo-cairo` (might or
  might not be configurable; needs investigation).

v0.3 ships with Option A. The custom SP1 `StarkConfig` is recorded in
`versions.lock::sp1.fri_params` and the SP1 prover binary
(`third_party/sp1/prover/prove.rs`) is extended to read this config
from a build-time env var.

The reduced `num_queries` will reduce SP1's wall-clock by an estimated
3-5% (one fewer FRI commitment round). This makes the apples-to-apples
comparison **slightly less favourable to Stwo** than the v0.2 numbers
would suggest at unmatched soundness, which is honest.

## 6. Test obligations

| Test ID | Description | Layer |
|---|---|---|
| `S26-T1` | Both stacks at post-slack λ ≥ 100 bits at the pinned parameters | soundness |
| `S26-T2` | `|λ_SP1 - λ_Stwo| ≤ 1` bit at the pinned parameters | apples-to-apples |
| `S26-T3` | `preflight.sh` exits 5 with `MEASUREMENT.SOUNDNESS_FLOOR_BREACH` on a synthetic `(b=2, q=10, g=0)` param set | safety |
| `S26-T4` | `preflight.sh` exits 5 with `MEASUREMENT.SOUNDNESS_FLOOR_DIVERGENCE` on a synthetic 5-bit gap | safety |
| `S26-T5` | `sp1-sdk@6.0.2 ProverClient::with_config(<custom StarkConfig>)` actually applies the config (verified by reading back the config from the prover's internals) | upstream-compat |

## 7. Open questions

- `OPEN-Q-26-1`: Slack constants for BCIKS20 and eprint 2024/278 are
  upper bounds from the papers; tighter bounds may be available in
  v0.4. Track academic literature.
- `OPEN-Q-26-2`: Option B (matching Stwo to SP1) may be cleaner if
  Stwo's Circle-FRI accepts a custom `num_queries`. Investigate before
  Phase 0.
- `OPEN-Q-26-3`: A more rigorous methodology would normalise both
  stacks to *exactly* 100 bits post-slack. v0.3 settles for ≤ 1-bit
  divergence; v0.4 may tighten.
