# RFC-0007: Prover and verifier wrapper contract

- Status: Accepted
- Authors: maintainer
- Created: 2026-05-13
- Target milestone: v0.1

## Summary

`bin/run_<prover>.sh` and `bin/verify_<prover>.sh` are symmetric across SP1 and Stwo. Both prover wrappers take exactly `<fixtures_path> <output_proof_path>` and emit a proof file. Both verifier wrappers take exactly `<proof_path>` and read `fixtures/v0.1.json` from a fixed relative path. The harness depends on this symmetry to remain prover-agnostic; a CI symmetry check enforces it.

## Motivation

The whole comparison rests on the same measurement tool measuring the same operation across both backends. If the wrappers diverge in argument shape, exit-code semantics, or stdout discipline, the measurement script must special-case one or both, and the comparison becomes "SP1 under regime A vs Stwo under regime B" — which is a different benchmark.

Locking the wrapper contract is therefore a soundness requirement, not just a quality-of-life convenience.

## Goals

- Bit-for-bit symmetric argument shapes.
- A single contract document (this RFC) authoritative for both wrappers.
- A CI check (`I-1` in `07-testing-strategy.md`) that asserts symmetry.
- Errors at the wrapper layer separable from errors at the prover layer (per the exit-code scheme in `04-error-model.md`).

## Non-Goals

- Hiding prover-specific build steps. Each wrapper may invoke build-time helpers internally; the contract is at the *invocation* layer.
- Cross-prover proof-format interoperability. Proof files are prover-defined and opaque to the harness; verifier wrappers know how to parse their own.

## Proposed Design

### `bin/run_<prover>.sh` contract

#### Argument shape

```
bin/run_<prover>.sh <fixtures_path> <output_proof_path>
```

Exactly two positional arguments. Any other argv shape is `MEASUREMENT.ENV_VAR_MISS` (or its sibling) — the wrapper exits 2 before invoking the prover.

#### Preconditions

The wrapper must, in order:

1. Assert `$#` is 2; else exit 2.
2. Assert `$1` exists, is readable, and is a regular file; else exit 2.
3. Assert each of `CUDA_VISIBLE_DEVICES=""`, `RAYON_NUM_THREADS=1`, `TOKIO_WORKER_THREADS=1`, `OMP_NUM_THREADS=1` is in the environment; else exit 2 with `MEASUREMENT.ENV_VAR_MISS`.
4. Assert the invocation command line, as the wrapper will issue it, contains the OS-specific affinity prefix (macOS: `taskpolicy -c utility`; Linux: `taskset -c 0`); else exit 2 with `MEASUREMENT.AFFINITY_MISS`.

#### Invocation

Once preconditions pass, the wrapper invokes the prover binary with no shell-side parallelism (no `&`), captures the prover's stdout to the measurement-collected log, captures stderr to the same channel (merged), and exits with the prover's exit code (`0`/`1` per `04-error-model.md`).

#### Stdout

The wrapper's stdout is the prover's combined stdout/stderr. It must contain (either from upstream prover or post-processed by the wrapper):

```
CONSTRAINTS: <integer>
TRACE_ROWS:  <integer>
```

Absence is `PROVER.STDOUT_GRAMMAR_VIOLATION` and is the wrapper's responsibility to detect (exit `1` after writing the prover's full log to stderr).

#### Stderr

Reserved for the wrapper's own diagnostic. The prover's stderr is folded into stdout, so a reader scanning stderr sees only harness-issued errors.

#### Exit codes

| Code | Meaning |
|---|---|
| 0 | proof emitted successfully; stdout grammar satisfied |
| 1 | prover failed (witness rejected, internal error) |
| 2 | precondition violated; prover not invoked |
| 3 | build error encountered before invoking prover |

Codes outside `{0,1,2,3}` are defects.

#### Output file

Written atomically to `<output_proof_path>`. The wrapper may use a temp file plus `mv` to achieve atomicity. After exit, the file exists with non-zero size; if not, exit code must be non-zero.

### `bin/verify_<prover>.sh` contract

#### Argument shape

```
bin/verify_<prover>.sh <proof_path>
```

Exactly one positional argument.

#### Preconditions

1. Assert `$#` is 1; else exit 2.
2. Assert `$1` exists and is readable; else exit 2.
3. Assert `fixtures/v0.1.json` is readable from `$(pwd)`. The verifier reads the fixture from this fixed relative path.

#### Behaviour

- Exit 0 means the proof is valid against the fixture.
- Exit 1 means the proof is invalid (either tampered or never valid).
- Exit 2 means harness-side precondition failure.

#### Stdout / stderr

- Stdout: empty on exit 0. Any output on stdout in the success path is a contract violation (`PROVER.STDOUT_GRAMMAR_VIOLATION`).
- Stderr: human-readable diagnostic on failure.

### Symmetry CI check (`I-1`)

The check is implemented in `tests/integration/test_wrapper_symmetry.py`:

1. Spawn `bin/run_sp1.sh` and `bin/run_stwo.sh` with `--help` or with no arguments. Assert both fail with exit code 2.
2. Inspect both files. Assert:
   - both files contain the line `set -euo pipefail`,
   - both files contain the env-var assertions for `CUDA_VISIBLE_DEVICES`, `RAYON_NUM_THREADS`, `TOKIO_WORKER_THREADS`, `OMP_NUM_THREADS`,
   - both files contain the affinity-prefix assertion appropriate to the host OS,
   - both files write the proof file via an atomic temp-then-rename pattern (matched by regex).
3. Spawn both wrappers with a small `fixtures/test_v0.1.json`; assert both exit 0; assert both produce a non-empty `proof` file.

This check runs on every PR.

### Discovery and naming

- Wrappers live in `bin/` (binary-style scripts), not `scripts/` (orchestration).
- The naming pattern is binding: `bin/run_<prover>.sh` and `bin/verify_<prover>.sh`. New provers (hypothetically, in `v0.2+`) would add `bin/run_plonky3.sh` etc.
- Wrappers must be executable (`chmod +x`).

### Wrapper internals (non-binding)

The contract above is binding. Internal implementation is free to vary. Practical guidance:

- Set `set -euo pipefail` at the top.
- Use `${VAR:?error message}` for environment assertions.
- Avoid `set -x` in measured paths (it pollutes stderr).
- Avoid invoking heavy shell built-ins (`compgen`, `read -a`) inside the measured window.

## Alternatives Considered

### A1. Make the wrappers Python instead of shell

Pros: more readable for complex logic.

Cons:
- Python startup overhead (~50–100 ms) is significant relative to short-running verifier invocations.
- Adds a Python interpreter dependency on the measured path.
- The current logic (4 env checks, 1 file check, 1 exec) is well within shell's clarity envelope.

Rejected.

### A2. JSON config file instead of positional argv

Pros: extensibility, named arguments.

Cons:
- Adds a parsing step on the measured path.
- Negative for symmetry: harder to assert that two wrappers consume the same shape.

Rejected.

### A3. Single wrapper with a `--prover` flag

`bin/run.sh --prover sp1 fixtures/v0.1.json proof.bin`. Pros: enforces symmetry by construction.

Cons:
- Mixes prover-specific build logic (different toolchains, different submodule paths) in one script.
- Forces all preconditions to be common; some preconditions may be prover-specific in the future (e.g., a different env var for some hypothetical third prover).
- The "per-prover script" pattern is more conventional and easier to grep.

Rejected.

### A4. No wrapper at all; measure-script invokes the prover binary directly

Pros: one fewer indirection.

Cons:
- The measure script becomes prover-specific (different binary, different argv shape per prover).
- Loses the precondition-check boundary, allowing the measured window to silently include precondition-violation cases.

Rejected.

## Drawbacks

- The CI symmetry check is structural (greps for patterns) and can be defeated by determined obfuscation. It is a tripwire, not a proof. The fundamental defence is human PR review of `bin/`.
- Shell wrappers are easy to break; one missing `-pipefail` can hide a precondition failure. Mitigated by `set -euo pipefail` at the top and `I-1`.

## Migration / Rollout

First-time. The four wrappers (`bin/run_sp1.sh`, `bin/run_stwo.sh`, `bin/verify_sp1.sh`, `bin/verify_stwo.sh`) land in one PR alongside the symmetry check.

## Testing Strategy

- **W-T1** (`I-1`): symmetry check as above.
- **W-T2**: exit-code matrix. For each of the four wrappers, simulate each precondition violation; assert correct exit code.
- **W-T3**: atomicity. Kill the wrapper mid-execution (SIGKILL after 1 ms); assert no partial `<output_proof_path>` exists.
- **W-T4**: stdout discipline. Run the verifier on a valid proof; assert stdout is empty. Run on an invalid proof; assert stderr is non-empty.
- **W-T5**: log grammar. Run the prover wrapper; assert `CONSTRAINTS:` and `TRACE_ROWS:` lines are present in stdout, exactly once each.

## Open Questions

None for `v0.1`.

## References

- `docs/spec/02-public-api.md` (C2, C3)
- `docs/spec/04-error-model.md`
- `RFC-0008` (measurement script consumes this contract)
- `RFC-0009` (single-core enforcement realised by these preconditions)
- PRD `PRD.md` §7.4
