# Licence exceptions

`scripts/check_licenses.sh` enforces every git submodule and `uv.lock`
entry carries an MIT-compatible licence (RFC-0014 §"Licensing"). A small
exception list is permitted for upstreams whose redistribution is
governed by an out-of-tree grant that the LICENSE-file detector can't see
directly. Every exception is recorded here.

## Current exceptions

| Path | Reason | Verified out-of-band |
|---|---|---|
| `third_party/sp1` (vendored `tanujkhattar/zkp_ecc`) | Upstream repo does not ship a LICENSE file in its tree. The project is a Google Quantum AI research artifact accompanying [the cryptocurrency white paper](https://quantumai.google/static/site-assets/downloads/cryptocurrency-whitepaper.pdf); Google research outputs are by Google's default policy Apache-2.0-licensed unless explicitly otherwise noted. We ship `third_party/sp1/LICENSE` recording the Apache-2.0 grant and our modifications. | yes — see PRD §1 |

## How exceptions are applied

`scripts/check_licenses.sh` reads `LICENSE_SUBMODULE_EXCEPTIONS` from the
environment as a space-separated list of submodule paths. CI sources
this from `.github/workflows/ci.yml` (#48 / #49); the orchestrator
`run_all.sh` (#37) re-uses the same value.

The exception is *minimal*: a submodule named here is excused from the
"must ship a LICENSE file" check, **not** from the licence-compatibility
check itself. If upstream later ships an incompatible LICENSE file the
gate fails again — the exception only covers the missing-file case.

## How to add an exception

1. Document the upstream's effective licence and how you verified it.
2. Add the path to the table above and to `LICENSE_SUBMODULE_EXCEPTIONS`
   in the relevant CI / orchestrator step.
3. File a tracking issue to follow upstream until they ship a LICENSE
   file; close the exception once they do.

## How to remove an exception

Drop the entry from the table here and from
`LICENSE_SUBMODULE_EXCEPTIONS`. The check will then enforce the
LICENSE-file requirement on the next run; if the upstream still lacks
one, the gate fails and the path must be re-added or upstream must
ship the file.
