#!/usr/bin/env python3
import json
import pathlib
import statistics
import sys


def program_label(program: str) -> str:
    path = pathlib.Path(program)
    if path.name == "compiled.json" and path.parent.name:
        return f"{path.parent.name}/compiled"
    return path.stem or "-"


def load_rows(path: pathlib.Path) -> list[dict]:
    rows = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return rows


def fmt(value, digits=3):
    if value is None:
        return "-"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} results.jsonl", file=sys.stderr)
        return 2

    path = pathlib.Path(sys.argv[1])
    rows = load_rows(path)
    print(f"# Summary: `{path.name}`")
    print()

    if not rows:
        print("No rows.")
        return 0

    print("| program | backend | n | cycles | cold s | warm s | MHz | proof KB | verify ms | RSS GB | VRAM GB |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        print(
            "| {program} | {backend} | {n} | {cycles} | {cold} | {warm} | {mhz} | {proof} | {verify} | {rss} | {vram} |".format(
                program=program_label(row.get("program", "")),
                backend=row.get("backend", "-"),
                n=row.get("n", "-"),
                cycles=row.get("cycle_count", "-"),
                cold=fmt(row.get("prove_s_cold")),
                warm=fmt(row.get("prove_s_warm")),
                mhz=fmt(row.get("mhz")),
                proof=fmt(row.get("proof_kb"), 1),
                verify=fmt(row.get("verify_ms"), 1),
                rss=fmt(row.get("peak_rss_gb"), 2),
                vram=fmt(row.get("vram_gb"), 2),
            )
        )

    print()
    print("## Backend Ratios")
    print()
    by_n: dict[int, dict[str, dict]] = {}
    for row in rows:
        by_n.setdefault(row["n"], {})[row["backend"]] = row

    print("| n | cuda warm s | simd warm s | cuda/simd | simd/cuda MHz |")
    print("|---:|---:|---:|---:|---:|")
    for n in sorted(by_n):
        cuda = by_n[n].get("cuda")
        simd = by_n[n].get("simd")
        if not cuda or not simd:
            continue
        cuda_s = cuda["prove_s_warm"]
        simd_s = simd["prove_s_warm"]
        cuda_mhz = cuda["mhz"]
        simd_mhz = simd["mhz"]
        print(f"| {n} | {cuda_s:.3f} | {simd_s:.3f} | {cuda_s / simd_s:.3f} | {simd_mhz / cuda_mhz:.3f} |")

    print()
    print("## Warm-Time Slopes")
    print()
    for backend in sorted({row["backend"] for row in rows}):
        series = sorted((row["n"], row["prove_s_warm"]) for row in rows if row["backend"] == backend)
        if len(series) < 2:
            continue
        slopes = []
        for (n0, t0), (n1, t1) in zip(series, series[1:]):
            if n1 != n0:
                slopes.append((t1 - t0) / (n1 - n0))
        if slopes:
            print(f"- `{backend}` median adjacent slope: {statistics.median(slopes):.9f} s / repetition")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
