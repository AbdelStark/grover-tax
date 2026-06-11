# Error model

Errors in `grover-tax` fall into five disjoint categories. Each has a distinct exit code, a distinct logging channel, and a distinct recovery path. The harness must never confuse a prover-internal failure with an environmental violation, because conflating them invalidates the run series silently.

## Error categories

| Category | Source | Exit code | Channel | Recovery |
|---|---|---|---|---|
| `BUILD` | toolchain, submodule, cargo, uv | wrapper exit `3` | stderr (harness) | rebuild; fix toolchain pin |
| `FIXTURE` | `gen_fixtures.py` or schema-validate | `gen-fixtures` exit `4` | stderr (Python) | regenerate; investigate seed/witness |
| `PROVER` | the prover binary itself | wrapper exit `1` | stdout (prover log) | retry; investigate witness shape |
| `MEASUREMENT` | env hygiene, harness preconditions | wrapper exit `2`; `measure.sh` exit `5` | stderr (harness) | fix environment; re-run |
| `REPORT` | `analyze.py` or `plot.py` | exit `6` | stderr (Python) | re-run; investigate inputs |

Exit code `0` is reserved for success. Exit codes outside `{0,1,2,3,4,5,6}` are unspecified and indicate a defect.

## Per-category enumeration

### BUILD (exit 3)

| Subcode (logged) | Trigger | Response |
|---|---|---|
| `BUILD.RUSTC_MISMATCH` | local `rustc --version` differs from `versions.lock` | abort; instruct user to `rustup install <pin>` |
| `BUILD.SP1_PATCH_FAIL` | `sp1-side-patches/0001-...patch` does not apply cleanly to `sp1-side/` HEAD | abort; investigate submodule SHA drift |
| `BUILD.STWO_SHA_DRIFT` | `stwo` submodule HEAD differs from `versions.lock.stwo.commit` | abort; `git submodule update --init --checkout` |
| `BUILD.CARGO_FAIL` | upstream cargo build returns non-zero | propagate; emit upstream stderr |
| `BUILD.UV_SYNC_FAIL` | `uv sync --frozen` returns non-zero | propagate; check `uv.lock` integrity |
| `BUILD.LICENSE_CHECK_FAIL` | `scripts/check_licenses.sh` finds incompatible licence in any submodule | abort; do not run measurements |

### FIXTURE (exit 4)

| Subcode | Trigger | Response |
|---|---|---|
| `FIXTURE.CROSS_VALIDATION_FAIL` | `sim_reference.py` output ≠ `coincurve` output for any test case | abort; investigate `sim_reference.py`, not the fixture |
| `FIXTURE.COMMITMENT_MISMATCH` | `sha256` or `blake2s` of `circuit_byte_serialisation_hex` ≠ committed hash | abort; investigate canonical serialiser |
| `FIXTURE.SCHEMA_INVALID` | the emitted file fails its own JSON Schema | abort; defect in `gen_fixtures.py` |
| `FIXTURE.WORKLOAD_NOT_PINNED` | `WORKLOAD.md` contains `TBD` | abort; complete `WORKLOAD.md` per `RFC-0001` |
| `FIXTURE.SEED_DRIFT` | regenerating with the same seed produces different bytes | defect; non-determinism in the generator |
| `FIXTURE.UNSUPPORTED_INSTRUCTION` | the `.kmx → GTV1` transpiler (KB-1) hits a phase/measurement/classical/control-flow instruction or an `if` condition (outside the classical reversible subset) | abort; the circuit needs the full kickmix simulator (KB-8) |
| `FIXTURE.KMX_PARSE_ERROR` | a `.kmx` source line is malformed: bad instruction name, unparseable target, wrong gate arity, non-qubit operand, or qubit id over the GTV1 u16 wire limit | abort; fix the circuit source |

### PROVER (exit 1)

| Subcode | Trigger | Response |
|---|---|---|
| `PROVER.WITNESS_REJECTED` | prover reports witness does not satisfy constraints | investigate witness construction; do *not* mark as measurement failure |
| `PROVER.VERIFIER_REJECTED` | `bin/verify_<prover>.sh` exit non-zero on a freshly emitted proof | abort; defect in prover or wrapper |
| `PROVER.OOM` | OOM-killed (Linux: SIGKILL with exit 137; macOS: SIGSEGV-like termination) | discard run; record in `discards.log` with reason `other` and detail `oom` |
| `PROVER.TIMEOUT` | wall-clock exceeds the per-run ceiling (set in `08-performance-budget.md`) | discard run; record |
| `PROVER.STDOUT_GRAMMAR_VIOLATION` | required `CONSTRAINTS:` / `TRACE_ROWS:` lines absent | abort; defect in prover wrapper |

`PROVER.WITNESS_REJECTED` is the only PROVER-class error that is informative *about the workload itself* (e.g., a bug in `circuit.cairo`). The other subcodes are operational.

### MEASUREMENT (exit 2 from wrapper; exit 5 from `measure.sh`)

| Subcode | Trigger | Response |
|---|---|---|
| `MEASUREMENT.ENV_VAR_MISS` | one of `CUDA_VISIBLE_DEVICES`, `RAYON_NUM_THREADS`, `TOKIO_WORKER_THREADS`, `OMP_NUM_THREADS` unset or wrong | abort; wrapper exits 2 *before* invoking the prover |
| `MEASUREMENT.AFFINITY_MISS` | macOS: `taskpolicy -c utility` not in the command line; Linux: `taskset -c 0` not in the command line | abort |
| `MEASUREMENT.GPU_RESIDENT` | `powermetrics --samplers gpu_power` reports non-zero residency during run | discard; record |
| `MEASUREMENT.THERMAL_EXCEEDED` | P-core T > 95°C (macOS) or junction > 90°C (Linux) | discard; record |
| `MEASUREMENT.SWAP_ACTIVE` | `sysctl vm.swapusage` (macOS) or `/proc/swaps` (Linux) reports non-zero | discard; record |
| `MEASUREMENT.AC_POWER_MISS` | `pmset -g ps` does not include `AC Power` on macOS | abort run series; record |
| `MEASUREMENT.LOWPOWER_ENABLED` | `pmset -g | grep -E 'lowpowermode\s+1'` on macOS | abort run series |
| `MEASUREMENT.GOVERNOR_MISS` | Linux: `scaling_governor != performance` or `no_turbo != 1` | abort run series |
| `MEASUREMENT.VERSIONS_DRIFT` | in-tree `versions.lock` ≠ live toolchain state | abort run series |

`measure.sh` itself exits 5 if any series-level precondition fails; individual run wrappers exit 2 for per-run precondition violations.

### REPORT (exit 6)

| Subcode | Trigger | Response |
|---|---|---|
| `REPORT.INSUFFICIENT_SAMPLES` | fewer than 10 valid (non-discarded) proof-gen runs per prover | abort `analyze`; do not emit `RESULTS.md` |
| `REPORT.STABILITY_BREACH` | day-1 vs day-2 median delta > 5% | flag in `RESULTS.md`; do not abort, but require human acknowledgement note |
| `REPORT.MISSING_ARTIFACT` | expected `results/*.json` not on disk | abort; surface which file |
| `REPORT.SCHEMA_INVALID` | any input fails its JSON Schema | abort |

## Failure modes designed against

These are the failure modes the spec is *engineered to prevent or detect*, not patch over later.

1. **Silent measurement contamination.** Background process inflates one prover's wall-clock; the report does not flag it. Defended by `MEASUREMENT.*` discards and the day-1/day-2 stability gate.
2. **Apples-to-oranges divergence creep.** A subsequent change to one prover's invocation that does not have a mirror on the other side. Defended by the symmetric wrapper contract (C2/C3 in `02-public-api.md`) and the `RFC-0007` symmetry check.
3. **Fixture drift.** Hand-editing `fixtures/v0.1.json` between runs. Defended by `gen-fixtures --check` in CI and the `circuit_commitment_*_hex` self-checks.
4. **Toolchain drift.** Local toolchain different from committed `versions.lock`. Defended by `preflight.sh` and `MEASUREMENT.VERSIONS_DRIFT`.
5. **Cold-cache leakage into the headline.** First-run timing dominates median for short series. Defended by hyperfine `--warmup` and the unconditional first-run discard (`D-INV-3`).
6. **Trusted-setup cost folded into headline.** Defended by separating M8/M9 into their own `sp1_setup.json` and explicitly excluding them from the proof-gen ratio (`RFC-0011`).
7. **Verifier never actually checked.** Defended by `run_all.sh` invoking `verify_<prover>.sh` and exiting non-zero before any timing measurement is recorded.

## Logging conventions

All harness errors emit a single line to stderr with the format:

```
<subcode>: <human message> | run_id=<id> prover=<sp1|stwo> path=<file>
```

Example:

```
MEASUREMENT.GPU_RESIDENT: powermetrics reported 4.2 mW gpu_power during run | run_id=1715610912-abcd123 prover=stwo path=results/stwo_v0.1_1715610912-abcd123.timing.json
```

Subcodes are stable identifiers; the human message after the colon is free-form and may evolve.

## Recovery responsibility

| Category | Who handles it |
|---|---|
| BUILD | implementer / reproducer (one-time setup) |
| FIXTURE | spec / generator authors (rare; defect-class) |
| PROVER | prover upstreams + harness maintainers |
| MEASUREMENT | reproducer (environmental) |
| REPORT | harness maintainer |

The reproducer's user manual (`README.md`) lists exactly the categories they are expected to encounter (`BUILD`, `MEASUREMENT`) and links to remediation. PROVER and FIXTURE errors indicate defects in this repository, not in the reproducer's environment.
