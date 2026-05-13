# Observability

This project is a benchmark, not a long-running service. "Observability" here means: every run leaves enough on disk for a third party — reading the repo six months later — to reconstruct what happened, why it happened, and whether the numbers are trustworthy. Logging, metrics, and traces all serve that goal.

## Principles

1. **Append-only.** No file the harness writes is ever rewritten or deleted by the harness itself. Bad runs are *moved* to `results/archive/<date>/` with a `WHY.md`. This makes the run history self-evidencing.
2. **Per-run isolation.** Every artifact for a given run is prefixed with `<prover>_v<fixture_version>_<run_id>`. Cross-run state lives in `versions.lock` and `discards.log` only.
3. **Structured where it matters; text where humans read.** Timing JSON is structured. Prover stdout is text. `RESULTS.md` is Markdown for humans and contains JSON-derived numbers.
4. **No telemetry.** This project sends nothing over the network. There is no opt-in metrics. Observability is local-file-only.

## Logging

### Levels

- Prover invocations run with `RUST_LOG=info`. `debug` and `trace` are reserved for ad-hoc investigation and never enabled in measured runs (their I/O cost biases timings).
- Harness scripts (`scripts/*.sh`, `bin/*.sh`) use `set -euo pipefail` and emit one structured stderr line per error per `04-error-model.md`.
- Python entry points use `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")`.

### Channels

- **Stdout:** prover-emitted content. Captured to `results/<prover>_v0.1_<run_id>.proverlog.txt`. Contains the M7 grammar (`CONSTRAINTS:` and `TRACE_ROWS:` lines) plus prover internal logs.
- **Stderr:** harness-emitted error lines (single-line per error, per the convention in `04-error-model.md`). Never captured into the proof log; reserved for run failures the human operator must see.
- **Files:** all timing data, all proof artifacts, all derived numbers.

### Required prover log lines

`bin/run_<prover>.sh` is responsible for guaranteeing these two lines exist in the proverlog (parse and re-emit if necessary):

```
CONSTRAINTS: <integer>
TRACE_ROWS:  <integer>
```

Absence is `PROVER.STDOUT_GRAMMAR_VIOLATION` (exit 1, defect-class).

### Redaction

There is nothing to redact. The repo is public from day one; the workload has no secret beyond `C`, which is checked into `fixtures/v0.1.json` *publicly* as part of the apples-to-apples requirement (see `RFC-0002` and `06-security.md` — `C` is "secret" only inside the proof system; out of band it is published). Path strings in logs are repo-relative, never absolute.

If a future contributor adds a feature that handles user-specific data (e.g., a personal cloud-run mode), redaction policy moves to that contributor's RFC.

## Metrics

The fixed metric set is M1–M10. M1–M9 enter `RESULTS.md`; M10 is informational and is footnoted, not headline.

| ID | Metric | Unit | Source | Stored in |
|---|---|---|---|---|
| M1 | Proof gen wall-clock | seconds | `hyperfine` | `<prover>_*.timing.json` |
| M2 | Proof gen peak RSS | MiB | `gnu-time -v` | `<prover>_*.time.txt` |
| M3 | Proof gen user CPU | seconds | `gnu-time -v` | `<prover>_*.time.txt` |
| M4 | Proof gen sys CPU | seconds | `gnu-time -v` | `<prover>_*.time.txt` |
| M5 | Verifier wall-clock | milliseconds | `hyperfine` | `<prover>_*.verify.json` |
| M6 | Proof file size | bytes | `stat` | `<prover>_*.proof_size.txt` |
| M7 | Trace rows / constraints | count | prover stdout | `<prover>_*.proverlog.txt` |
| M8 | Setup wall-clock (SP1 only) | seconds | `gnu-time` one-shot | `sp1_setup.json` |
| M9 | Setup output size (PK + VK) | bytes | `stat` | `sp1_setup.json` |
| M10 | Disk writes during proving | bytes | `iostat`-integrated | `<prover>_*.iostat.json` |

### Derived statistics (computed by `analyze.py`)

- median, IQR (Q3 - Q1), min, max, mean, stddev, run count, discard count per (metric, prover).
- ratios with denominator-prover = Stwo (so all SP1 / Stwo ratios are reported uniformly).
- per-day medians for the day-1 / day-2 stability check.

These derived numbers live only in `RESULTS.md`. They are not re-persisted to JSON; reproducers regenerate them from inputs.

## Tracing

There is no distributed tracing — there is no distributed system. The only "trace" is the prover's own log, which the harness captures verbatim. Stwo and SP1 may emit prover-internal trace lines; the harness does not parse them beyond the M7 grammar.

If a future contributor wants to add detailed phase timing within a prover, they should add it to the prover (not the harness) and let `RUST_LOG` carry it. Avoid adding harness-side instrumentation that runs during the measured window — it would bias M1/M2.

## What gets recorded for every measured run

A "run" is one invocation of `bin/run_<prover>.sh` plus the matching `bin/verify_<prover>.sh`.

A "run series" is N runs (default 10) of one prover, under one `hyperfine` invocation.

For each run series, the following files exist:

- `<prover>_v0.1_<run_id>.timing.json`
- `<prover>_v0.1_<run_id>.time.txt`
- `<prover>_v0.1_<run_id>.verify.json`
- `<prover>_v0.1_<run_id>.proverlog.txt`
- `<prover>_v0.1_<run_id>.proof_size.txt`
- `<prover>_v0.1_<run_id>.iostat.json` (M10, informational)

For each discarded individual run within a series, an entry appears in `results/discards.log`.

## What is *not* captured

- Anything via SaaS (no DataDog, no Sentry, no anything).
- Environment variables beyond those listed in `versions.lock.host`. Specifically: home paths, usernames, hostnames are *not* recorded.
- Wall-clock timestamps inside the prover process beyond what the prover emits.
- The full process tree at run time.

## Day-1 / Day-2 stability gate

This is the strongest form of observability the project ships: a *self-disagreement detector*. Two independent run series, separated by at least one full cold-boot, are recorded. `analyze.py` computes the day-1 vs day-2 median delta on M1. If the delta exceeds 5%, `RESULTS.md`:

- still publishes,
- marks the headline with `[STABILITY BREACH]`,
- includes a paragraph describing the investigation outcome in the apples-to-apples disclosures section.

A stability breach is not failure; it is information. The number is honest about its own noise.

## Versioning of observability artifacts

Every JSON artifact has a `schema_version` integer (see `03-data-model.md`). `analyze.py` rejects artifacts with unknown schema versions rather than silently skipping fields. `hyperfine` JSON does not carry a schema version of its own; the pin in `versions.lock` is the substitute.

## Failure to record is failure

If a measured run completes but its corresponding `*.timing.json` is missing or unreadable, the run is treated as discarded. Silent loss of measurement artifacts is the worst observability failure a benchmark can ship.
