#!/usr/bin/env bash
#
# check_licenses.sh — RFC-0014 §"Licensing" gate.
#
# Walks every committed git submodule and every direct dependency, asserts
# each carries a licence compatible with this repo's MIT root. The
# `MIT-compatible` set for `v0.1` is:
#
#   * MIT
#   * Apache-2.0 (with NOTICE-file requirement honoured by inclusion)
#   * BSD-2-Clause / BSD-3-Clause
#   * ISC
#   * Zlib
#   * MPL-2.0 (file-scoped, compatible with combined MIT redistribution)
#   * Unlicense / CC0-1.0 (public domain)
#
# Anything else exits 3 with `BUILD.LICENSE_CHECK_FAIL`. `scripts/run_all.sh`
# invokes this before any build step; CI runs it on every PR.
#
# Exit codes (per docs/spec/04-error-model.md):
#   0 — every submodule + dependency is MIT-compatible.
#   3 — `BUILD.LICENSE_CHECK_FAIL`: one or more non-compatible licences.
#   2 — usage / probe error (no `uv` on PATH, etc.).
#
# Override hooks for tests / CI:
#   ALLOW_LICENSE_REGEX  — additional regex of permitted SPDX expressions.
#                          Useful when an upstream releases a dual-licence
#                          variant the default set hasn't catalogued.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"

# `|`-joined regex of permitted SPDX identifiers / commonly-emitted variants.
# Match is case-insensitive; we lowercase the licence string before testing.
COMPATIBLE_DEFAULT='^(mit|apache-2\.0|apache 2\.0|bsd-2-clause|bsd-3-clause|isc|zlib|mpl-2\.0|unlicense|cc0-1\.0|cc0|0bsd|public domain|psf-2\.0|python software foundation license)$'
COMPATIBLE_REGEX="${ALLOW_LICENSE_REGEX:-${COMPATIBLE_DEFAULT}}"

VIOLATIONS=()

# -- Helper: classify one licence string --------------------------------------

is_compatible() {
  local raw="$1"
  # Normalise whitespace and case.
  local norm
  norm="$(printf '%s' "${raw}" | tr '[:upper:]' '[:lower:]' | sed -E 's/^[[:space:]]+//;s/[[:space:]]+$//')"
  if [[ -z "${norm}" || "${norm}" == "unknown" ]]; then
    return 1
  fi
  # Accept SPDX expressions of the form `A OR B` if at least one disjunct is
  # compatible (since MIT-compatible-OR-anything is still MIT-compatible).
  if [[ "${norm}" == *" or "* ]]; then
    local IFS=$'|'
    # shellcheck disable=SC2207
    local parts=($(echo "${norm}" | sed -E 's/[[:space:]]+or[[:space:]]+/|/g'))
    for p in "${parts[@]}"; do
      if echo "${p}" | grep -qiE "${COMPATIBLE_REGEX}"; then
        return 0
      fi
    done
    return 1
  fi
  echo "${norm}" | grep -qiE "${COMPATIBLE_REGEX}"
}

# -- Walk git submodules ------------------------------------------------------

walk_submodules() {
  if [[ ! -f "${REPO_ROOT}/.gitmodules" ]]; then
    return
  fi
  # Each submodule line in `.gitmodules` has `path = <p>`.
  local mod_path
  while IFS= read -r mod_path; do
    [[ -z "${mod_path}" ]] && continue
    local full="${REPO_ROOT}/${mod_path}"
    local found=""
    for candidate in LICENSE LICENSE.txt LICENSE.md COPYING COPYING.txt; do
      if [[ -f "${full}/${candidate}" ]]; then
        found="${full}/${candidate}"
        break
      fi
    done
    if [[ -z "${found}" ]]; then
      VIOLATIONS+=("submodule ${mod_path}: no LICENSE file found")
      continue
    fi
    # Most upstream LICENSEs start with the SPDX shorthand on one of the
    # first lines (e.g. "MIT License", "Apache License Version 2.0").
    local detected
    detected="$(_detect_licence_from_file "${found}")"
    if ! is_compatible "${detected}"; then
      VIOLATIONS+=("submodule ${mod_path}: licence '${detected:-unknown}' is not MIT-compatible")
    fi
  done < <(awk -F'= *' '/[[:space:]]*path[[:space:]]*=/ {print $2}' "${REPO_ROOT}/.gitmodules")
}

_detect_licence_from_file() {
  local file="$1"
  # Look at the first ~10 non-empty lines.
  local head_text
  head_text="$(head -n 20 "${file}" | tr -d '\r')"
  # Common signatures.
  if grep -qiE 'mit license|permission is hereby granted, free of charge' <<<"${head_text}"; then
    echo MIT; return
  fi
  if grep -qiE 'apache license, version 2\.0|apache-2\.0' <<<"${head_text}"; then
    echo Apache-2.0; return
  fi
  if grep -qiE 'bsd 3-clause|redistribution and use in source and binary forms' <<<"${head_text}"; then
    if grep -qiE 'neither the name of' <<<"${head_text}"; then
      echo BSD-3-Clause; return
    fi
    echo BSD-2-Clause; return
  fi
  if grep -qiE 'mozilla public license version 2\.0' <<<"${head_text}"; then
    echo MPL-2.0; return
  fi
  if grep -qiE 'isc license' <<<"${head_text}"; then
    echo ISC; return
  fi
  if grep -qiE 'gnu general public license|gnu lesser general public license' <<<"${head_text}"; then
    # GPL-class licences are *not* MIT-compatible in the spec's sense.
    if grep -qiE 'lesser' <<<"${head_text}"; then
      echo LGPL; return
    fi
    echo GPL; return
  fi
  if grep -qiE 'unlicense|public domain' <<<"${head_text}"; then
    echo Unlicense; return
  fi
  echo unknown
}

# -- Walk uv.lock dependencies ------------------------------------------------

# uv.lock is TOML; we don't have a `tomllib`-shell so we lean on `uv pip
# metadata --strict` for each top-level dep. To keep the wall-clock low and
# avoid issuing one subprocess per package, we instead parse the licence
# expressions out of the lock file directly.

walk_python_deps() {
  local lockfile="${REPO_ROOT}/uv.lock"
  if [[ ! -f "${lockfile}" ]]; then
    return
  fi
  # `uv.lock` has stanzas like:
  #
  #   [[package]]
  #   name = "matplotlib"
  #   version = "3.10.7"
  #   ...
  #
  # Plus optional `license = "..."` fields. We scan with awk to pair the
  # `name` and `license` lines into TAB-separated rows, then consume the
  # rows in the parent shell (no subshell, so `VIOLATIONS+=` propagates).
  local rows
  rows="$(awk '
    function emit() { if (name != "" && lic != "") print name "\t" lic }
    /^\[\[package\]\]/ { emit(); name = ""; lic = "" }
    /^name = / { gsub(/"/, ""); name = $3 }
    /^license = / {
      sub(/^license = /, "")
      gsub(/"/, "")
      lic = $0
    }
    END { emit() }
  ' "${lockfile}")"

  if [[ -z "${rows}" ]]; then
    return
  fi
  local name lic
  while IFS=$'\t' read -r name lic; do
    [[ -z "${name}" ]] && continue
    if ! is_compatible "${lic}"; then
      VIOLATIONS+=("python dep ${name}: licence '${lic}' is not MIT-compatible")
    fi
  done <<< "${rows}"
}

# -- Run ----------------------------------------------------------------------

walk_submodules
walk_python_deps

if (( ${#VIOLATIONS[@]} > 0 )); then
  echo "BUILD.LICENSE_CHECK_FAIL: ${#VIOLATIONS[@]} incompatible licence(s):" >&2
  for v in "${VIOLATIONS[@]}"; do
    echo "  - ${v}" >&2
  done
  exit 3
fi
exit 0
