# Data model

Every persisted artifact has a schema. Schemas are versioned. Producers must emit only schema-conforming output; consumers must reject input that does not validate. Schemas live under `docs/spec/schemas/` as JSON Schema (draft 2020-12) and are exercised by CI (`area:ci`, see `RFC-0014`).

## Schemas summary

| Artifact | Schema file | Producer | Consumer |
|---|---|---|---|
| `fixtures/v0.1.json` | `fixture-v0.1.schema.json` | `gen_fixtures.py` | both provers, `analyze.py` |
| `versions.lock` | `versions-lock-v1.schema.json` | `lock_versions.sh` | CI, `analyze.py` (records into `RESULTS.md`) |
| `results/<prover>_v0.1_<run_id>.timing.json` | `hyperfine-v1.8.schema.json` (upstream) | `hyperfine` | `analyze.py` |
| `results/<prover>_v0.1_<run_id>.time.txt` | `gnu-time-v.schema.txt` (line grammar) | `gnu-time -v` | `analyze.py` |
| `results/<prover>_v0.1_<run_id>.proverlog.txt` | `proverlog-v1.schema.md` (line grammar) | prover wrapper | `analyze.py` |
| `results/discards.log` | `discards-v1.schema.json` | `measure.sh` | `analyze.py` |
| `results/sp1_setup.json` | `setup-v1.schema.json` | `measure_setup.sh` | `analyze.py` |
| `RESULTS.md` | `results-md-v1.template.md` | `analyze.py` | humans |

This file documents the *invariants* enforced by those schemas. The schema files are the source of truth at validation time; this document is the source of truth for *why* the invariants exist.

## Fixture (`fixtures/v0.1.json`)

```jsonc
{
  "version": "v0.1",
  "generator_commit": "string, /^[0-9a-f]{40}$/",
  "workload_pin_commit": "string, /^[0-9a-f]{40}$/",   // upstream zkp_ecc SHA used for WORKLOAD.md
  "seed_hex": "string, lowercase hex, len=64",          // sha256(SEED)
  "n_samples": "integer >= 1",
  "bit_stripe_width": "integer >= 1",
  "circuit_serialisation_format_version": 1,
  "circuit_byte_serialisation_hex": "string, lowercase hex, len%2==0",
  "circuit_commitment_sha256_hex": "string, lowercase hex, len=64",
  "circuit_commitment_blake2s_hex": "string, lowercase hex, len=64",
  "test_cases": [
    {
      "x_hex": "string, lowercase hex, len=128",        // pair of compressed-affine secp256k1 points
      "y_hex": "string, lowercase hex, len=66"          // one compressed-affine secp256k1 point
    }
  ]
}
```

### Invariants

1. **F-INV-1**: `len(test_cases) == n_samples`.
2. **F-INV-2**: `sha256(bytes.fromhex(circuit_byte_serialisation_hex)) == bytes.fromhex(circuit_commitment_sha256_hex)`.
3. **F-INV-3**: `blake2s(bytes.fromhex(circuit_byte_serialisation_hex)) == bytes.fromhex(circuit_commitment_blake2s_hex)`. Blake2s digest length is 32 bytes; no custom personalisation or key.
4. **F-INV-4**: For every `(x_i, y_i)`, evaluating `sim_reference.py` on `(C, x_i)` yields `y_i`. The fixture is rejected if cross-validation fails.
5. **F-INV-5**: For every `(x_i, y_i)`, parsing `x_i` as two secp256k1 affine points `(P_i, Q_i)` and computing `P_i + Q_i` via `coincurve` yields `y_i`. The fixture is rejected if reference math disagrees.
6. **F-INV-6**: `circuit_serialisation_format_version == 1`. Any other value is rejected; introducing version 2 requires a fixture-version bump.
7. **F-INV-7**: `version` is the literal string `"v0.1"`. Any other value is a fixture file from a different release; consumers must reject.
8. **F-INV-8**: All hex fields are lowercase and even-length. Whitespace is forbidden.
9. **F-INV-9**: Test cases are ordered. The fixture's iteration order is `test_cases[0]` first. Both provers must iterate in this order; reordering changes nothing soundness-wise but breaks byte-equality of internal commitments built on traversal order.

### Canonical byte serialisation of `C`

`circuit_byte_serialisation_hex` is the canonical serialisation of the gate list. Format (binding):

```
struct GateListV1 {
    magic:      [u8; 4]       = b"GTV1"           // "Grover-Tax v1"
    n_gates:    u32 (LE)
    gates:      [Gate; n_gates]
}

struct Gate {
    opcode:     u8            // 0=NOP, 1=NOT, 2=CNOT, 3=TOFFOLI
    _pad:       u8            = 0
    target:     u16 (LE)
    ctrl_a:     u16 (LE)
    ctrl_b:     u16 (LE)      // 0xFFFF if unused (NOT, CNOT)
}
```

`NOP` is reserved for padding to a power of two. Padding policy is decided in `RFC-0004`.

## Versions lock (`versions.lock`)

```jsonc
{
  "schema_version": 1,
  "generated_at": "2026-05-13T14:32:01Z",
  "generator_commit": "<repo SHA at time of generation>",
  "rustc": {
    "version": "1.83.0",
    "commit_hash": "string",
    "host": "aarch64-apple-darwin"
  },
  "cargo": { "version": "1.83.0" },
  "sp1": {
    "version": "string",                  // from sp1-side/Cargo.lock
    "sp1up_toolchain": "string"           // sp1up channel
  },
  "stwo": {
    "commit": "string, /^[0-9a-f]{40}$/",
    "remote": "https://github.com/starkware-libs/stwo"
  },
  "cairo": { "version": "string" },
  "uv": {
    "version": "string",
    "sha256": "string, lowercase hex, len=64"
  },
  "python": { "version": "3.12.x" },
  "hyperfine": { "version": "1.18.x" },
  "gnu_time": { "version": "1.9", "binary": "/opt/homebrew/bin/gtime" },
  "host": {
    "platform": "darwin | linux",
    "arch": "aarch64 | x86_64",
    "model": "string",                    // sysctl hw.model on macOS
    "cpu_brand": "string",
    "cores_total": "integer",
    "ram_gb": "integer",
    "kernel": "string"                    // uname -r
  }
}
```

### Invariants

1. **V-INV-1**: `schema_version == 1`.
2. **V-INV-2**: All commit hashes are full 40-char lowercase hex.
3. **V-INV-3**: A measured run is invalid if its in-tree `versions.lock` differs from the committed one. The harness asserts this in `preflight.sh`.
4. **V-INV-4**: `host.platform == "darwin"` is required for headline-rig numbers. Linux is permitted in CI but tagged as such in `RESULTS.md`.

## Discards log (`results/discards.log`)

Append-only JSON-lines file. One record per discarded run.

```jsonc
{
  "ts": "2026-05-13T14:35:12Z",
  "run_id": "1715610912-abcd123",
  "prover": "sp1 | stwo",
  "reason": "thermal | gpu_residency | swap_active | cold_cache | env_var_miss | other",
  "detail": "string, human-readable",
  "measurement_artifact": "path/to/the/discarded/timing.json"
}
```

### Invariants

1. **D-INV-1**: Every discarded measurement artifact has a corresponding `discards.log` entry. Missing entries are a CI-failing violation.
2. **D-INV-2**: `reason` is one of the enumerated values. Free-form reasons go in `detail`.
3. **D-INV-3**: The first run of any series is automatically discarded with `reason: cold_cache`, regardless of other state.

## Setup record (`results/sp1_setup.json`)

```jsonc
{
  "schema_version": 1,
  "run_id": "string",
  "wall_clock_s": "float >= 0",
  "user_cpu_s": "float >= 0",
  "sys_cpu_s": "float >= 0",
  "peak_rss_mib": "float >= 0",
  "proving_key_bytes": "integer >= 0",
  "verifying_key_bytes": "integer >= 0",
  "groth16_ceremony_origin": "string, free-form, e.g., 'upstream-trusted-setup-v0.x' or 'reproduced-locally-non-trusted'"
}
```

### Invariants

1. **S-INV-1**: `groth16_ceremony_origin` is non-empty. The trusted-setup ceremony provenance is part of `RESULTS.md`.
2. **S-INV-2**: Setup is captured *once* per `versions.lock` and is keyed by `versions.lock` content hash. Reusing a setup record across version locks is forbidden.

## Prover log grammar (`results/<prover>_v0.1_<run_id>.proverlog.txt`)

The harness parses two lines per prover log:

```
CONSTRAINTS: <integer>
TRACE_ROWS:  <integer>
```

These two lines are required. The prover wrapper must guarantee them, either by parsing the upstream prover's log and emitting them, or by computing them and printing them itself. All other log content is informational.

### Invariants

1. **L-INV-1**: Exactly one occurrence of each line per prover invocation.
2. **L-INV-2**: Integers are decimal, non-negative.

## Hyperfine output

Upstream JSON, consumed verbatim. The fields `times`, `median`, `mean`, `stddev`, `min`, `max`, `command` are required. `analyze.py` discards any other fields. Schema version is whatever `hyperfine` emits at the pinned version; the pin is in `versions.lock`. Breaking changes in `hyperfine` JSON are caught when the pin is bumped (see `RFC-0012`).

## `gnu-time -v` output

Free-form text, line-oriented. `analyze.py` extracts:

- `Maximum resident set size (kbytes): <integer>` → M2 (peak RSS), converted to MiB.
- `User time (seconds): <float>` → M3.
- `System time (seconds): <float>` → M4.

Missing fields fail-loudly: `analyze.py` raises an error rather than reporting zero.

## `RESULTS.md` template

`RESULTS.md` is generated, not hand-edited. Template lives at `docs/spec/templates/RESULTS.md.j2` (Jinja2). The headline table, distribution stats, apples-to-apples disclosures section, plot embeds, and reproduction recipe are all populated by `analyze.py`. See `RFC-0011`.

## Schema evolution discipline

- Schemas live next to the data model that uses them.
- Every schema has a `schema_version` integer.
- Bumping a schema version is a minor or major project bump per `09-release-and-versioning.md`.
- A schema change without a `schema_version` bump is a defect.
- CI runs `python -m grover_tax.validate_schemas` (or equivalent) on every artifact emitted into `results/` and fails on any validation error.
