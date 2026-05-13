#!/usr/bin/env bash
#
# locale_env.sh — neutralise locale + timezone for reproducible runs.
#
# Sourced (not executed) by `scripts/run_all.sh` (#37), `scripts/measure.sh`
# (#32), and any CI job that runs the prover binaries. Exports:
#
#   LANG=C        — fallback locale; suppresses locale-dependent string
#                   comparisons in `sort`, `grep`, etc.
#   LC_ALL=C      — overrides every individual LC_* variable.
#   TZ=UTC        — fixes the date-printer timezone; eliminates host-clock
#                   drift in any subprocess that timestamps output.
#
# Per RFC-0013 §"Locale neutrality" these three exports are mandatory before
# any subprocess invocation that affects measured numbers. They are no-ops
# on a host that already has them set, so sourcing this file is idempotent.
#
# Usage:
#   # shellcheck source=/dev/null
#   source "${REPO_ROOT}/scripts/locale_env.sh"

export LANG=C
export LC_ALL=C
export TZ=UTC
