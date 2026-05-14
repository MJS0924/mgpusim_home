#!/usr/bin/env python3
"""
per_bank_l2_skew.py — quantify L2-bank latency skew per (workload,
region size). For each sqlite, we already have one
`req_average_latency` per L2 bank (16 banks × 4 GPUs = 64 samples).
This script computes spread statistics (CV, max÷min, p95/p50, top-k
share) and reports them next to the kernel-time U-shape, to test
whether bank skew tracks the right side of the U.

Output: results/figures/fig_i_l2_bank_skew.{csv,md}
"""

from __future__ import annotations

import csv
import sqlite3
import statistics
import sys
from pathlib import Path

ROOT = Path("/root/mgpusim_home/results")
SQL_DIR = ROOT / "CD" / "rawdata" / "sql"
SUMMARY_CSV = ROOT / "summary.csv"
OUT_CSV = ROOT / "figures" / "fig_i_l2_bank_skew.csv"
OUT_MD = ROOT / "figures" / "fig_i_l2_bank_skew.md"

CD_ORDER = ["0", "1", "2", "4", "6", "8"]
CD_TO_BYTES = {c: 64 * (1 << int(c)) for c in CD_ORDER}


def fetch_bank_latencies(sqlite_path: Path) -> list[float]:
    con = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute(
        "SELECT value FROM mgpusim_metrics "
        "WHERE what='req_average_latency' "
        "AND location LIKE '%L2Cache%' "
        "AND location NOT LIKE 'GPU[1].%' "
        "AND location NOT LIKE 'GPU[0].%';"
    )
    out = [float(v[0]) * 1e9 for v in cur.fetchall() if v[0] is not None]
    con.close()
    return out


def percentile(s: list[float], q: float) -> float:
    if not s:
        return float("nan")
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * q / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def main() -> int:
    summary = {}
    with SUMMARY_CSV.open() as f:
        for r in csv.DictReader(f):
            if r["variant"] != "CD" or r["config"] not in CD_ORDER:
                continue
            summary[(r["workload"], r["config"])] = r

    workloads = sorted({wl for wl, _ in summary})

    rows = []
    for wl in workloads:
        for cfg in CD_ORDER:
            path = SQL_DIR / f"{wl}_CD_{cfg}.sqlite3"
            if not path.exists():
                continue
            vals = fetch_bank_latencies(path)
            if not vals:
                continue
            s = sorted(vals)
            mean = statistics.fmean(s)
            std = statistics.pstdev(s) if len(s) > 1 else 0.0
            kt_ms = float(summary[(wl, cfg)]["kernel_time(s)"]) * 1000
            top4 = sum(s[-4:]) / sum(s)  # share of total latency in 4 hottest banks
            rows.append({
                "workload": wl,
                "config": cfg,
                "region_bytes": CD_TO_BYTES[cfg],
                "n_banks": len(s),
                "mean_ns": mean,
                "min_ns": s[0],
                "max_ns": s[-1],
                "std_ns": std,
                "cv": std / mean if mean > 0 else 0,
                "max_over_min": s[-1] / s[0] if s[0] > 0 else float("inf"),
                "p95_over_p50": percentile(s, 95) / percentile(s, 50),
                "top4_lat_share": top4,  # of total bank-mean-latency sum
                "kernel_ms": kt_ms,
            })

    rows.sort(key=lambda r: (r["workload"], r["region_bytes"]))
    cols = list(rows[0].keys())
    OUT_CSV.write_text("")
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT_CSV}")

    md = ["# Per-bank L2 latency skew vs region size", ""]
    md.append("64 samples per cell = 4 GPU × 16 banks. We're correlating "
              "*bank-mean* dispersion (not per-request distribution) "
              "with region size.")
    md.append("")
    md.append("Columns: mean / std / CV (=std/mean) / min / max / "
              "max÷min / p95÷p50 / top-4 share (sum of 4 hottest "
              "banks ÷ sum of all 64). High top-4 share means the "
              "load is concentrated on a few banks.")
    md.append("")
    by_wl = {}
    for r in rows:
        by_wl.setdefault(r["workload"], []).append(r)
    for wl, rs in by_wl.items():
        md.append(f"## {wl}")
        md.append("")
        md.append("| region | mean (ns) | CV | max÷min | p95÷p50 | "
                  "top-4 share | kernel (ms) |")
        md.append("|---:|---:|---:|---:|---:|---:|---:|")
        for r in rs:
            md.append(
                f"| {r['region_bytes']}B | {r['mean_ns']:.1f} | "
                f"{r['cv']:.3f} | {r['max_over_min']:.2f} | "
                f"{r['p95_over_p50']:.2f} | "
                f"{r['top4_lat_share']*100:.1f}% | "
                f"{r['kernel_ms']:.3f} |"
            )
        md.append("")

    OUT_MD.write_text("\n".join(md) + "\n")
    print(f"wrote {OUT_MD}")
    print()
    for line in md:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
