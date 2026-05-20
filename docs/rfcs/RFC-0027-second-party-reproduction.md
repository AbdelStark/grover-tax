# RFC-0027 — Second-Party Reproduction Protocol

| Field | Value |
|---|---|
| Status | Draft (v0.3) |
| Depends on | RFC-0013 (reproducibility envelope), RFC-0014 (governance), RFC-0021 (hardening), RFC-0024 (audit chain) |
| Implements | `SCOPE.md::C1`, resolves `OPEN-Q-v0.3-3` |

## 1. Summary

Defines a normative protocol by which an *independent* operator (not
the v0.3 maintainer) can reproduce the v0.3 headline ratio and have
their result accepted as a Tier-3 reproducibility data point. Closes
the "single-maintainer benchmark" critique that any reviewer at the
Google methodology bar will raise.

## 2. Reproducer requirements

A second-party reproducer's submission is accepted as a valid v0.3
Tier-3 data point iff:

1. **Rig equivalence class** (RFC-0024 §4.3): their `versions.lock::host`
   fields match the v0.3 reference within the equivalence-class
   definition (CPU SKU + physical core count + RAM in MiB + firmware
   version). A mismatched class is permitted but flagged: the
   headline-ratio tolerance widens to ±10% per RFC-0013's Tier-3 widening.
2. **Toolchain equivalence**: `versions.lock` fields (rustc.version,
   sp1.sdk_version, stwo.commit, scarb.version) are byte-equal to the
   v0.3 reference. Soundness-floor parameters (RFC-0026) MUST match.
3. **Workload identity**: reproducer uses the same `fixtures/v0.3/T<i>-pointadd-<n>.json`
   from the published v0.3 release (no regeneration).
4. **Audit chain**: every Tier-A test (`SCOPE.md`) passes on the
   reproducer's rig.
5. **Honest operator declaration**: the reproducer SHALL NOT have
   commit access to the v0.3 reference branch and SHALL submit their
   results via PR with a signed declaration (CODEOWNERS-verified) of
   independence.

## 3. Submission format

The reproducer creates a directory `headline-runs/v0.3.0/replicators/<operator-id>/`
containing:

```
RESULTS-replicator-<operator-id>.md   # rendered per RFC-0024 §4 template
results/                              # raw artefacts
fixtures/                             # symbolic link to upstream v0.3 fixtures
versions.lock                         # the reproducer's lockfile
signed_declaration.txt                # PGP-signed statement of independence
```

The signed declaration:

```
I, <operator name>, declare that:
- I am not the maintainer of grover-tax.
- I have no commit access to AbdelStark/grover-tax::main.
- I executed the v0.3 reproduction protocol on my own infrastructure.
- My infrastructure has not been pre-provisioned by the maintainer.
- The numbers in RESULTS-replicator-<operator-id>.md were captured by
  scripts/run_all.sh on my rig and have not been edited.

Signed: <PGP signature; key fingerprint in CONTRIBUTORS.md>
```

## 4. Acceptance criteria

The reproducer's PR is merged iff:

| Criterion | Check |
|---|---|
| F-INV-1..9 on every fixture file (unchanged from v0.3 release) | `validate_schemas.py` |
| Audit-chain tests (all Tier-A) green on the reproducer's rig | reproducer's CI |
| `RESULTS-replicator-<operator-id>.md` schema-validates against the new template | methodology lint |
| Reproducer's per-tier ρ values within ±5% of v0.3 reference (or ±10% if rig-class mismatched) | `analyze.py --compare-to-reference` |
| Reproducer's `versions.lock::sp1.fri_params, stwo.circle_fri_params` byte-equal to v0.3 reference | soundness equivalence (RFC-0026) |
| PGP-signed declaration verified | governance |

The reproducer's PR description SHALL include:
- Operator's affiliation (if any, for transparency).
- Rig description (cloud provider, region, instance type).
- Total wall-clock time and compute cost.
- Any deviations from the protocol with justification.

## 5. Encouragement + governance

v0.3's `CONTRIBUTORS.md` adds a "Reproducers" section listing
accepted replicators with their PGP fingerprint and one-line rig
description.

The maintainer SHALL NOT pre-coordinate the reproducer's setup beyond
the published reproduction recipe in `BUILD.md`. The reproducer's
work product is otherwise self-directed.

The v0.3 release notes recognise reproducers in the "Acknowledgements"
section.

## 6. Test obligations

| Test ID | Description | Layer |
|---|---|---|
| `S27-T1` | Reproducer's `versions.lock` matches v0.3 reference within equivalence class | meta |
| `S27-T2` | Reproducer's `RESULTS-replicator-<id>.md` schema-validates and contains the required disclosure phrases | reporting |
| `S27-T3` | Cross-result comparison: `analyze.py --compare-to-reference` produces a delta table; deltas within ±5% (or ±10% if mismatched class) | reproducibility |
| `S27-T4` | PGP signature verification on `signed_declaration.txt` (against a CONTRIBUTORS.md-listed key) | governance |

## 7. Multi-reproducer aggregation

If ≥ 3 independent reproducers submit accepted results, v0.3's
`RESULTS.md` is amended with a "Reproducibility envelope" section
showing the median + 95% CI of ρ across all accepted reproductions.
This is the Tier-D5 "multi-rig statistical envelope" promotion path
from `OPEN-Q-v0.4-5` to a v0.3 deliverable.

## 8. Adversary `A_collusion` (out of scope)

A maintainer who recruits a friendly reproducer using a rig that's
been pre-tuned to match the maintainer's numbers is not defended
against by this RFC. v0.3 acknowledges this and considers it Tier-D
trust (governance + signed declaration is the operational deterrent;
v0.4's SLSA-3 hardening would tighten it).

## 9. Open questions

- `OPEN-Q-27-1`: Should reproducers be incentivised (bounty,
  attribution in the methodology paper)? v0.3 ships with attribution
  only; bounties may be added if reproducer recruitment is slow.
- `OPEN-Q-27-2`: A "trusted reproducer registry" (community-vetted
  operators) would streamline the protocol. Out of scope for v0.3.
- `OPEN-Q-27-3`: Should reproductions on materially different CPU SKUs
  (e.g., AWS Graviton, AMD EPYC) be encouraged for cross-architecture
  data? v0.3 ships with single-class focus; v0.4 may broaden.
