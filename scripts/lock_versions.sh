#!/usr/bin/env bash
#
# lock_versions.sh — regenerate `versions.lock` from the live toolchain.
#
# Per RFC-0012:
#
#   * Default behaviour: overwrite `versions.lock` (or the path passed as $1).
#   * `DRY=1 ./scripts/lock_versions.sh` prints to stdout without overwriting.
#   * Output is pretty-printed with sorted keys (jq --sort-keys) so diffs are
#     byte-stable. Exclude `generated_at` and `generator_commit` when comparing
#     two runs for drift (those fields change on every regeneration).
#
# The schema this script targets is `docs/spec/schemas/versions-lock-v1.schema.json`.
# CI validates the emitted file via `python -m grover_tax.validate_schemas`.
#
# Toolchain dependencies (must all be on PATH):
#   jq, awk, git, rustc, cargo, uv, hyperfine, gnu-time (gtime on macOS,
#   /usr/bin/time on Linux), shasum / sha256sum, sysctl (macOS) or /proc (Linux).
#
# Anything not on PATH is recorded as the literal string `unknown`. The schema
# accepts this only for `stwo.commit` (where the submodule may not yet be
# wired); other `unknown` values surface as schema-validation failures.

set -euo pipefail

OUT="${1:-versions.lock}"
DRY="${DRY:-0}"

# Resolve the gnu-time binary the way the spec wants: gtime on macOS, /usr/bin/time
# on Linux. Both are GNU time; the macOS `time` builtin is *not*.
gnu_time_binary() {
  if command -v gtime >/dev/null 2>&1; then
    command -v gtime
  elif [[ -x /usr/bin/time ]]; then
    echo /usr/bin/time
  else
    echo unknown
  fi
}

# Single-line value: never two lines, never the literal word `unknown`
# unless the value really is unavailable.
gnu_time_version() {
  local bin out
  bin="$(gnu_time_binary)"
  if [[ "$bin" == "unknown" ]]; then
    echo unknown
    return
  fi
  # GNU time accepts --version; BSD time (the macOS default at /usr/bin/time)
  # does not. Capture stdout+stderr; if the first line looks like an error,
  # treat the binary as not-GNU-time and report unknown.
  out="$("$bin" --version 2>&1 | head -n1 || true)"
  if [[ "$out" == *"illegal option"* || "$out" == *"unknown option"* || -z "$out" ]]; then
    echo unknown
  else
    echo "$out"
  fi
}

host_model() {
  if command -v sysctl >/dev/null 2>&1 && sysctl -n hw.model >/dev/null 2>&1; then
    sysctl -n hw.model
  elif [[ -r /sys/devices/virtual/dmi/id/product_name ]]; then
    cat /sys/devices/virtual/dmi/id/product_name
  else
    echo unknown
  fi
}

host_cpu_brand() {
  if command -v sysctl >/dev/null 2>&1 && sysctl -n machdep.cpu.brand_string >/dev/null 2>&1; then
    sysctl -n machdep.cpu.brand_string
  elif [[ -r /proc/cpuinfo ]]; then
    awk -F: '/^model name/ {gsub(/^[ \t]+|[ \t]+$/,"",$2); print $2; exit}' /proc/cpuinfo
  else
    echo unknown
  fi
}

host_cores_total() {
  if command -v sysctl >/dev/null 2>&1 && sysctl -n hw.ncpu >/dev/null 2>&1; then
    sysctl -n hw.ncpu
  elif command -v nproc >/dev/null 2>&1; then
    nproc
  else
    echo 1
  fi
}

host_ram_gb() {
  local bytes
  if command -v sysctl >/dev/null 2>&1 && sysctl -n hw.memsize >/dev/null 2>&1; then
    bytes="$(sysctl -n hw.memsize)"
  elif [[ -r /proc/meminfo ]]; then
    # MemTotal is in kB; convert to bytes.
    bytes="$(( $(awk '/^MemTotal:/ {print $2}' /proc/meminfo) * 1024 ))"
  else
    echo 0
    return
  fi
  echo $(( bytes / 1024 / 1024 / 1024 ))
}

uv_sha256() {
  local bin
  bin="$(command -v uv || true)"
  if [[ -z "$bin" ]]; then
    echo unknown
    return
  fi
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$bin" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$bin" | awk '{print $1}'
  else
    echo unknown
  fi
}

sp1_version() {
  if [[ -r sp1-side/Cargo.lock ]]; then
    awk '/^name = "sp1-/ {ok=1} ok && /^version =/ {gsub(/"/,"",$3); print $3; exit}' \
      sp1-side/Cargo.lock
  else
    echo unknown
  fi
}

sp1up_toolchain() {
  if command -v sp1up >/dev/null 2>&1; then
    sp1up --version 2>/dev/null | awk '{print $2}'
  else
    echo unknown
  fi
}

stwo_commit() {
  if [[ -d stwo/.git || -f stwo/.git ]]; then
    (cd stwo && git rev-parse HEAD)
  else
    echo unknown
  fi
}

cairo_version() {
  if command -v cairo-compile >/dev/null 2>&1; then
    cairo-compile --version 2>&1 | head -n1
  else
    echo unknown
  fi
}

# Emit the raw record. `jq` does the heavy lifting: every value is constructed
# in shell, then jq builds the object with --arg for strings and --argjson for
# numbers. This avoids any chance of an embedded quote breaking the JSON.

RUSTC_VERBOSE="$(rustc --version --verbose 2>/dev/null || true)"
RUSTC_VERSION="$(echo "$RUSTC_VERBOSE" | awk '/^rustc/{print $2}')"
RUSTC_COMMIT="$(echo "$RUSTC_VERBOSE" | awk '/commit-hash/{print $2}')"
RUSTC_HOST="$(echo "$RUSTC_VERBOSE" | awk '/^host/{print $2}')"

RECORD="$(
  jq -n \
    --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg generator_commit "$(git rev-parse HEAD 2>/dev/null || echo unknown)" \
    --arg rustc_version "${RUSTC_VERSION:-unknown}" \
    --arg rustc_commit_hash "${RUSTC_COMMIT:-unknown}" \
    --arg rustc_host "${RUSTC_HOST:-unknown}" \
    --arg cargo_version "$(cargo --version 2>/dev/null | awk '{print $2}' || echo unknown)" \
    --arg sp1_version "$(sp1_version)" \
    --arg sp1up_toolchain "$(sp1up_toolchain)" \
    --arg stwo_commit "$(stwo_commit)" \
    --arg cairo_version "$(cairo_version)" \
    --arg uv_version "$(uv --version 2>/dev/null | awk '{print $2}' || echo unknown)" \
    --arg uv_sha256 "$(uv_sha256)" \
    --arg python_version "$(uv run python --version 2>&1 | awk '{print $2}' || echo unknown)" \
    --arg hyperfine_version "$(hyperfine --version 2>/dev/null | awk '{print $2}' || echo unknown)" \
    --arg gnu_time_version "$(gnu_time_version)" \
    --arg gnu_time_binary "$(gnu_time_binary)" \
    --arg platform "$(uname | tr '[:upper:]' '[:lower:]')" \
    --arg arch "$(uname -m)" \
    --arg model "$(host_model)" \
    --arg cpu_brand "$(host_cpu_brand)" \
    --argjson cores_total "$(host_cores_total)" \
    --argjson ram_gb "$(host_ram_gb)" \
    --arg kernel "$(uname -r)" \
    '{
       schema_version: 1,
       generated_at: $generated_at,
       generator_commit: $generator_commit,
       rustc: {version: $rustc_version, commit_hash: $rustc_commit_hash, host: $rustc_host},
       cargo: {version: $cargo_version},
       sp1: {version: $sp1_version, sp1up_toolchain: $sp1up_toolchain},
       stwo: {commit: $stwo_commit, remote: "https://github.com/starkware-libs/stwo"},
       cairo: {version: $cairo_version},
       uv: {version: $uv_version, sha256: $uv_sha256},
       python: {version: $python_version},
       hyperfine: {version: $hyperfine_version},
       gnu_time: {version: $gnu_time_version, binary: $gnu_time_binary},
       host: {
         platform: $platform,
         arch: $arch,
         model: $model,
         cpu_brand: $cpu_brand,
         cores_total: $cores_total,
         ram_gb: $ram_gb,
         kernel: $kernel
       }
     }'
)"

# Pretty-print + sort keys for stable diffs.
SORTED="$(echo "$RECORD" | jq --sort-keys '.')"

if [[ "$DRY" == "1" ]]; then
  printf '%s\n' "$SORTED"
else
  printf '%s\n' "$SORTED" > "$OUT"
fi
