# RFC-0011: Reporting and `RESULTS.md`

- Status: Accepted
- Authors: maintainer
- Created: 2026-05-13
- Target milestone: v0.1

## Summary

`RESULTS.md` is the single human-readable artifact that summarises the benchmark. It is generated, not hand-edited. The template, the headline table, the distribution plots, and the apples-to-apples disclosures section are all locked here. Methodology lints in CI enforce the structure.

## Motivation

A benchmark's headline number is read first; everything else is glanced at. We engineer `RESULTS.md` so the *first read* contains the headline ratio, the IQR, the apples-to-apples disclosures, and the trusted-setup status. A reader who stops there has the honest picture.

We also lock the structure so that future "improvements" to `RESULTS.md` are visible as version bumps rather than silent renumberings.

## Goals

- A frozen `RESULTS.md` template (`docs/spec/templates/RESULTS.md.j2`).
- Headline table with median, IQR, min, max, stddev, ratio, sample counts.
- Distribution plots embedded by relative path.
- Required apples-to-apples disclosures section.
- Required reproduction recipe.
- Methodology lints in CI.

## Non-Goals

- HTML report or web UI. Markdown only.
- Multi-page reports. One file.
- Embedded raw JSON. The JSON lives in `results/`; `RESULTS.md` links by relative path.

## Proposed Design

### Template (`docs/spec/templates/RESULTS.md.j2`)

```markdown
# Results: {{ project_version }} — {{ generated_at }}

{{ headline_status }}      # e.g., empty, or "[STABILITY BREACH]", "[HIGH VARIANCE]"

> Reference rig: see `versions.lock`. Run `./scripts/run_all.sh`. Wall time approximately 25 minutes from a clean clone. Output lands here and in `results/`.

## Headline

| Metric | SP1 + Groth16 | Stwo | Ratio (SP1 / Stwo) |
|---|---|---|---|
| Proof gen median (n={{ n_sp1 }} / {{ n_stwo }}) | {{ m1_sp1_median }} {{ m1_unit }} | {{ m1_stwo_median }} {{ m1_unit }} | {{ ratio_m1 }}× |
| Proof gen IQR | {{ m1_sp1_iqr }} | {{ m1_stwo_iqr }} | n/a |
| Proof gen min / max | {{ m1_sp1_min }} / {{ m1_sp1_max }} | {{ m1_stwo_min }} / {{ m1_stwo_max }} | n/a |
| Verifier median (n={{ n_verify_sp1 }} / {{ n_verify_stwo }}) | {{ m5_sp1_median }} {{ m5_unit }} | {{ m5_stwo_median }} {{ m5_unit }} | {{ ratio_m5 }}× |
| Peak RSS | {{ m2_sp1 }} MiB | {{ m2_stwo }} MiB | {{ ratio_m2 }}× |
| Proof size | {{ m6_sp1 }} bytes | {{ m6_stwo }} bytes | {{ ratio_m6 }}× |
| Trace / constraints | {{ m7_sp1 }} | {{ m7_stwo }} | n/a |
| Trusted setup required | yes ({{ m8_sp1 }} s one-time, {{ m9_sp1 }} MiB keys) | no | structural |

## Distributions

![Proof generation wall-clock histogram (overlaid)](results/plots/wallclock_hist.png)

![Median and IQR (proof gen and verify)](results/plots/medians_bar.png)

## Stability

![Day-1 vs Day-2 comparison](results/plots/day1_day2.png)

Day-1 median ({{ day1_median_sp1 }} s SP1 / {{ day1_median_stwo }} s Stwo).
Day-2 median ({{ day2_median_sp1 }} s SP1 / {{ day2_median_stwo }} s Stwo).
Delta: {{ day1_day2_delta_sp1 }}% (SP1), {{ day1_day2_delta_stwo }}% (Stwo).

{% if stability_breach %}
**Stability breach.** {{ stability_breach_explanation }}
{% endif %}

## Apples-to-apples disclosures

The headline ratio reflects two prover *stacks*, not two prover algorithms in isolation. The following structural and intentional differences are part of what is being measured:

1. **Commitment hash function.** SP1 side: SHA-256 (the upstream example's native choice). Stwo side: Blake2s. Both commitments are computed over the same `circuit_byte_serialisation_hex`. Implementing SHA-256 in Cairo would dominate Stwo's wall-clock and confound the comparison; Blake2s is bit-oriented and in the same structural family as SHA-2. See `RFC-0005`.

2. **Field choice.** SP1 uses BabyBear (`p = 2^31 - 2^27 + 1`); Stwo uses M31 (`p = 2^31 - 1`). Both are 31-bit primes, structural to their respective provers. This is not a tunable knob.

3. **Trusted setup.** SP1+Groth16 requires a trusted setup (one-time, {{ m8_sp1 }} s wall-clock, {{ m9_sp1 }} MiB of proving + verifying keys). Stwo has no trusted setup. Setup cost is **excluded** from the proof-generation ratio above and reported separately. Ceremony provenance: `{{ groth16_ceremony_origin }}`.

4. **Thread fan-out.** Both provers were invoked with `RAYON_NUM_THREADS=1`, `TOKIO_WORKER_THREADS=1`, `OMP_NUM_THREADS=1`, plus OS-level affinity ({{ affinity_macos_or_linux }}). Observed user-CPU / wall-clock ratios: {{ user_wall_sp1 }} (SP1), {{ user_wall_stwo }} (Stwo). {% if residual_concurrency %}A user-CPU excess of more than 10% on either prover indicates residual concurrency despite the env caps and is noted here. {{ residual_concurrency_note }}{% endif %}

5. **Affinity gap (macOS-only).** Apple Silicon does not expose a kernel knob to disable dynamic frequency scaling or to pin a process to a single physical core. The harness uses `taskpolicy -c utility` plus the thread caps above. The macOS measurement is single-threaded by construction but not single-core-pinned. The Linux CI rig results, with hard `taskset -c 0` pinning, are reported in the `RESULTS-linux.md` companion file (if generated) as a cross-check.

## Discards

| Reason | SP1 | Stwo |
|---|---|---|
| cold_cache | {{ d_cold_sp1 }} | {{ d_cold_stwo }} |
| thermal | {{ d_thermal_sp1 }} | {{ d_thermal_stwo }} |
| gpu_residency | {{ d_gpu_sp1 }} | {{ d_gpu_stwo }} |
| swap_active | {{ d_swap_sp1 }} | {{ d_swap_stwo }} |
| env_var_miss / affinity_miss | {{ d_env_sp1 }} | {{ d_env_stwo }} |
| other | {{ d_other_sp1 }} | {{ d_other_stwo }} |
| **total discard rate** | **{{ discard_pct_sp1 }}%** | **{{ discard_pct_stwo }}%** |

Per-run discard log: `results/discards.log`.

## Reproduction

- Workload pin (upstream `zkp_ecc` commit): `{{ workload_pin_commit }}`
- Fixture: `fixtures/v0.1.json` (sha256: `{{ fixture_sha256 }}`)
- Versions lock: `versions.lock` (sha256: `{{ versions_lock_sha256 }}`)

```bash
git clone https://github.com/AbdelStark/grover-tax.git
cd grover-tax
./scripts/run_all.sh
```

Expected wall time on the reference rig: ~25 minutes. Hard ceiling: 45 minutes.

## Run metadata

- Reference rig: {{ host_summary }}
- Date of day-1 run: {{ day1_date }}
- Date of day-2 run: {{ day2_date }}
- Spec version this report ties to: `{{ spec_version }}`
- Generator: `analyze.py` from commit `{{ analyze_commit }}`

## Underlying numbers

- Raw timing JSON: `results/sp1_v0.1_*.timing.json`, `results/stwo_v0.1_*.timing.json`
- gnu-time output: `results/<prover>_v0.1_*.time.txt`
- Prover logs: `results/<prover>_v0.1_*.proverlog.txt`
- Setup record: `results/sp1_setup.json`
```

### `analyze.py`'s responsibility

`analyze.py`:

1. Loads every `results/<prover>_v0.1_*.timing.json`, applies discard rules per `RFC-0010`, computes per-prover stats.
2. Loads `gnu-time` output for M2/M3/M4.
3. Loads proverlog grammar lines for M7.
4. Loads `sp1_setup.json` for M8/M9.
5. Loads `discards.log` and tallies by reason.
6. Loads `versions.lock` for host metadata.
7. Renders the template with the data into `RESULTS.md`.
8. Verifies the rendered document still contains:
   - the Apples-to-apples disclosures heading,
   - the five numbered disclosure subsections,
   - the reproduction recipe.

Any failure of step 8 is a defect.

### Methodology lints (CI)

`tests/lint/check_results_md.py`:

```python
REQUIRED_SECTIONS = [
    "## Headline",
    "## Distributions",
    "## Stability",
    "## Apples-to-apples disclosures",
    "## Discards",
    "## Reproduction",
    "## Run metadata",
    "## Underlying numbers",
]
REQUIRED_PHRASES = [
    "SHA-256",
    "Blake2s",
    "BabyBear",
    "M31",
    "Trusted setup",
    "taskpolicy",
    "RAYON_NUM_THREADS",
]
def main():
    text = open("RESULTS.md").read()
    for s in REQUIRED_SECTIONS:
        assert s in text, f"Missing section: {s}"
    for p in REQUIRED_PHRASES:
        assert p in text, f"Missing phrase: {p}"
```

The lint runs in CI on every PR that touches `RESULTS.md`, `analyze.py`, or the template. A failure blocks merge.

### Ratio convention

Headline ratio is always `SP1 / Stwo`. Even if the actual value is < 1, the ratio is reported as-is (`0.34×` is reported as `0.34×`, not "Stwo slower"). The reader interprets the number.

### Distribution plot specifications

- `results/plots/wallclock_hist.png`: overlaid histograms of M1 for both provers. 50 bins. Axis labels with units. Legend top-right.
- `results/plots/medians_bar.png`: bar chart of M1 and M5 medians, error bars = IQR. Two pairs of bars.
- `results/plots/day1_day2.png`: side-by-side bars for day-1 and day-2 medians. Annotated with delta percentage.

All plots use a colourblind-safe palette (`viridis` or equivalent). All plots are reproducible from the data; `plot.py` is deterministic.

## Alternatives Considered

### A1. Generate a PDF report

Pros: prettier, prints well.

Cons: PDFs are not greppable in the repo; adds a build dep on LaTeX or wkhtmltopdf. Markdown is sufficient.

Rejected.

### A2. Use a notebook (`jupyter`, `quarto`) as the report

Pros: more flexible.

Cons:
- Notebooks rot (cell execution state drift).
- Reviewers cannot easily diff a notebook.

Rejected.

### A3. Skip the disclosures section; trust readers to read the spec

Genuinely tempting (reduces RESULTS.md length). Rejected: most readers do not read the spec. The disclosures must live at the point of consumption.

### A4. Make the ratio convention "larger / smaller" instead of "SP1 / Stwo"

Pros: ratio is always ≥ 1, easier to read.

Cons:
- Hides which prover is faster.
- Requires direction-dependent text ("SP1 faster" vs "Stwo faster"), which is harder to template.

Rejected.

## Drawbacks

- The template is verbose. Acceptable: a benchmark report should be exhaustive about caveats.
- Methodology lints are textual greps; obfuscated submissions could pass. Mitigation: human review of `analyze.py` and the template.

## Migration / Rollout

First-time. Lands once `RFC-0008`, `RFC-0009`, `RFC-0010` are in.

## Testing Strategy

- **R-T1**: Synthetic input data (mocked timing JSONs) → rendered `RESULTS.md` passes all methodology lints.
- **R-T2**: Each disclosure subsection includes its required phrase (text match).
- **R-T3**: Discard tally adds up to the discard log entries.
- **R-T4**: Ratio convention test: with `m1_sp1=2`, `m1_stwo=1`, ratio reads `2×`; with `m1_sp1=1`, `m1_stwo=2`, ratio reads `0.5×`.
- **R-T5**: Sample size guard: if N_valid < 10 for either prover, `analyze.py` aborts with `REPORT.INSUFFICIENT_SAMPLES` and does *not* emit `RESULTS.md`.
- **R-T6**: Plot determinism: two runs of `plot.py` on the same data produce byte-identical PNGs.

## Open Questions

**OPEN-Q-11.1** — Whether to publish a CSV companion (`results/headline.csv`) for tooling. Current decision: no, in `v0.1`. Tools can parse the JSON in `results/`. Owner: maintainer. Resolution target: post-`v0.1` if a downstream consumer requests.

## References

- `docs/spec/02-public-api.md` (RESULTS.md is a public-API output)
- `docs/spec/05-observability.md` (M1..M10)
- `docs/spec/07-testing-strategy.md` (M-1, M-2, M-3 self-consistency)
- `RFC-0005` (disclosure content)
- `RFC-0008` (data sources)
- `RFC-0009` (affinity disclosure)
- `RFC-0010` (discards and stability)
- PRD `PRD.md` §9
