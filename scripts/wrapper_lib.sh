#!/usr/bin/env bash
#
# wrapper_lib.sh — shared helpers for `bin/run_<prover>.sh`.
#
# Sourced (not executed) by both wrappers so the precondition and
# grammar-enforcement logic stays in one place. The script itself is *not*
# meant to be invoked directly; `set -e` is not enabled here because that's
# the responsibility of the caller (which it must enable per RFC-0007
# §"Wrapper internals").
#
# Public helpers:
#   require_env <var> <required_value>
#     Exit 2 with `MEASUREMENT.ENV_VAR_MISS` if `$<var>` is unset or != value.
#     Distinguishes "unset" from "set to empty string" via `${!var-...}` so
#     CUDA_VISIBLE_DEVICES="" (literal empty) passes the check.
#
#   resolve_affinity
#     Echoes the affinity-prefix argv that the caller should `${ARR[@]}`-prefix
#     onto the prover invocation. macOS: `taskpolicy -c utility`; Linux:
#     `taskset -c 0`. Exits 2 with `MEASUREMENT.AFFINITY_MISS` if the host
#     platform is neither, or the relevant tool isn't on PATH.
#
#   enforce_proverlog_grammar <log_file>
#     Asserts the prover-log file at `$1` contains exactly one
#     `CONSTRAINTS: <integer>` line and exactly one `TRACE_ROWS: <integer>`
#     line, integers decimal non-negative. Exit 1 with
#     `PROVER.STDOUT_GRAMMAR_VIOLATION` on any deviation.

require_env() {
  local var="$1"
  local want="$2"
  local got="${!var-__UNSET__}"
  if [[ "${got}" != "${want}" ]]; then
    echo "MEASUREMENT.ENV_VAR_MISS: ${var}='${got}' but harness requires '${want}'" >&2
    exit 2
  fi
}

# Print the OS-appropriate affinity-prefix tokens, space-separated, on stdout.
# Caller does `read -ra AFFINITY <<< "$(resolve_affinity)"` to fold the result
# into an argv array.
resolve_affinity() {
  case "$(uname)" in
    Darwin)
      if ! command -v taskpolicy >/dev/null 2>&1; then
        echo "MEASUREMENT.AFFINITY_MISS: taskpolicy not on PATH (required on macOS per RFC-0009)" >&2
        exit 2
      fi
      echo "taskpolicy -c utility"
      ;;
    Linux)
      if ! command -v taskset >/dev/null 2>&1; then
        echo "MEASUREMENT.AFFINITY_MISS: taskset not on PATH (required on Linux per RFC-0009)" >&2
        exit 2
      fi
      echo "taskset -c 0"
      ;;
    *)
      echo "MEASUREMENT.AFFINITY_MISS: unsupported platform $(uname); RFC-0009 limits to darwin/linux" >&2
      exit 2
      ;;
  esac
}

# Enforce the prover-log grammar (RFC-0007 §"Stdout", RFC-0010 §"Required
# prover log lines"). Exact regex:
#   ^CONSTRAINTS: [0-9]+$              (one or more digits, decimal, non-neg)
#   ^TRACE_ROWS:[[:space:]]+[0-9]+$    (trailing spaces between colon and value
#                                       are intentional — matches the canonical
#                                       sample line in `05-observability.md`)
# Exactly *one* match for each is required. Zero or > 1 is a violation.
enforce_proverlog_grammar() {
  local log="$1"
  local n_constraints n_trace_rows

  n_constraints="$(grep -cE '^CONSTRAINTS: [0-9]+$' "${log}" || true)"
  n_trace_rows="$(grep -cE '^TRACE_ROWS:[[:space:]]+[0-9]+$' "${log}" || true)"

  if [[ "${n_constraints}" != "1" ]]; then
    echo "PROVER.STDOUT_GRAMMAR_VIOLATION: expected exactly one 'CONSTRAINTS: <int>' line, found ${n_constraints}" >&2
    exit 1
  fi
  if [[ "${n_trace_rows}" != "1" ]]; then
    echo "PROVER.STDOUT_GRAMMAR_VIOLATION: expected exactly one 'TRACE_ROWS: <int>' line, found ${n_trace_rows}" >&2
    exit 1
  fi
}
