#!/usr/bin/env python3
"""
l2_latency_spread.py — extract per-bank L2 request-latency *spread* from
the existing CD sqlite dumps (no simulator changes), and join it against
the wasted-invalidation counters in summary.csv to test whether wasted
invalidation correlates with bank-level latency imbalance.

Per (workload, region size), each GPU has 16 L2 banks × 4 GPUs = 64
banks. The simulator already records `req_average_latency` (seconds) per
bank in the mgpusim_metrics table. That gives 64 *bank-mean* samples per
configuration — not a per-request distribution, but enough to see
whether wasted-inv pressure spreads load unevenly across banks.

Outputs:
  results/figures/fig_g_l2_latency_spread.csv     — per-(workload,config) stats
  results/figures/fig_g_l2_latency_spread_table.md — pretty table per workload
  stdout: Spearman correlation of (CV, wasted_inv) across configs.
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
OUT_DIR = ROOT / "figures"
OUT_CSV = OUT_DIR / "fig_g_l2_latency_spread.csv"
OUT_MD = OUT_DIR / "fig_g_l2_latency_spread_table.md"

CD_ORDER = ["0", "1", "2", "4", "6", "8"]
CD_TO_BYTES = {c: 64 * (1 << int(c)) for c in CD_ORDER}
WORKLOADS = sorted({p.name.split("_CD_")[0] for p in SQL_DIR.glob("*_CD_*.sqlite3")})


def fetch_bank_latencies(sqlite_path: Path) -> list[float]:
    """Return per-bank L2 req_average_latency in nanoseconds (GPU[2-5] only,
    matching summary.csv aggregation convention)."""
    con = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute(
        "SELECT value FROM mgpusim_metrics "
        "WHERE what='req_average_latency' "
        "AND location LIKE '%L2Cache%' "
        "AND location NOT LIKE 'GPU[1].%' "
        "AND location NOT LIKE 'GPU[0].%';"
    )
    vals = [float(v[0]) * 1e9 for v in cur.fetchall() if v[0] is not None]
    con.close()
    return vals


def percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interp percentile, q in [0,100]."""
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * q / 100.0
    lo, hi = int(pos), min(int(pos) + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def stats_for(vals: list[float]) -> dict:
    if not vals:
        return {}
    s = sorted(vals)
    mean = statistics.fmean(s)
    std = statistics.pstdev(s) if len(s) > 1 else 0.0
    return {
        "n_banks": len(s),
        "mean_ns": mean,
        "std_ns": std,
        "cv": std / mean if mean > 0 else 0.0,
        "min_ns": s[0],
        "max_ns": s[-1],
        "p25_ns": percentile(s, 25),
        "p50_ns": percentile(s, 50),
        "p75_ns": percentile(s, 75),
        "iqr_ns": percentile(s, 75) - percentile(s, 25),
        "range_ns": s[-1] - s[0],
        "max_over_min": s[-1] / s[0] if s[0] > 0 else float("inf"),
    }


def load_summary_index() -> dict[tuple[str, str], dict]:
    """{(workload, config): row} from summary.csv for variant=CD."""
    out = {}
    with SUMMARY_CSV.open() as f:
        for row in csv.DictReader(f):
            if row["variant"] != "CD":
                continue
            out[(row["workload"], row["config"])] = row
    return out


def spearman(xs: list[float], ys: list[float]) -> float:
    """Spearman rank correlation, handling ties with average ranks."""
    if len(xs) < 2:
        return float("nan")

    def ranks(vs):
        order = sorted(range(len(vs)), key=lambda i: vs[i])
        r = [0.0] * len(vs)
        i = 0
        while i < len(vs):
            j = i
            while j + 1 < len(vs) and vs[order[j + 1]] == vs[order[i]]:
                j += 1
            avg_rank = (i + j) / 2 + 1  # 1-based
            for k in range(i, j + 1):
                r[order[k]] = avg_rank
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = sum((rx[i] - mx) ** 2 for i in range(n)) ** 0.5
    dy = sum((ry[i] - my) ** 2 for i in range(n)) ** 0.5
    if dx == 0 or dy == 0:
        return float("nan")
    return num / (dx * dy)


def main() -> int:
    if not SQL_DIR.is_dir():
        print(f"missing {SQL_DIR}", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    summary = load_summary_index()

    rows = []
    for wl in WORKLOADS:
        for cfg in CD_ORDER:
            path = SQL_DIR / f"{wl}_CD_{cfg}.sqlite3"
            if not path.exists():
                continue
            vals = fetch_bank_latencies(path)
            st = stats_for(vals)
            if not st:
                continue
            sm = summary.get((wl, cfg), {})
            wasted_evict = float(sm.get("L2_InvalidateInvalidBlock-Evict") or 0)
            wasted_write = float(sm.get("L2_InvalidateInvalidBlock-Write") or 0)
            valid_evict = float(sm.get("L2_InvalidateValidBlock-Evict") or 0)
            valid_write = float(sm.get("L2_InvalidateValidBlock-Write") or 0)
            inv_by_evict_dir = float(sm.get("InvalidateByEviction") or 0)
            wasted_total = wasted_evict + wasted_write
            useful_total = valid_evict + valid_write
            wasted_ratio = (
                wasted_total / (wasted_total + useful_total)
                if (wasted_total + useful_total) > 0 else 0.0
            )

            rows.append({
                "workload": wl,
                "config": cfg,
                "region_bytes": CD_TO_BYTES[cfg],
                **st,
                "wasted_inv_evict": wasted_evict,
                "wasted_inv_write": wasted_write,
                "wasted_inv_total": wasted_total,
                "useful_inv_total": useful_total,
                "wasted_ratio": wasted_ratio,
                "dir_inv_by_evict": inv_by_evict_dir,
                "kernel_time_ms": float(sm.get("kernel_time(s)") or 0) * 1000,
            })

    if not rows:
        print("no rows extracted", file=sys.stderr)
        return 1

    cols = list(rows[0].keys())
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT_CSV}")

    md_lines: list[str] = []
    md_lines.append("# L2 latency spread vs wasted invalidation")
    md_lines.append("")
    md_lines.append("Per-bank L2 `req_average_latency` aggregated across "
                    "GPU[2-5] × 16 banks = 64 samples per (workload, region).")
    md_lines.append("")
    md_lines.append("Columns: mean / std / CV (=std/mean) / min / max / "
                    "max÷min / wasted_inv_total (eviction-induced "
                    "InvalidateInvalidBlock + write-induced).")
    md_lines.append("")
    by_wl: dict[str, list[dict]] = {}
    for r in rows:
        by_wl.setdefault(r["workload"], []).append(r)

    for wl, rs in by_wl.items():
        rs.sort(key=lambda r: r["region_bytes"])
        md_lines.append(f"## {wl}")
        md_lines.append("")
        md_lines.append(
            "| region | mean (ns) | std (ns) | CV | min (ns) | max (ns) | "
            "max÷min | wasted_inv | useful_inv | kern (ms) |"
        )
        md_lines.append(
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
        )
        for r in rs:
            md_lines.append(
                f"| {r['region_bytes']}B | {r['mean_ns']:.1f} | "
                f"{r['std_ns']:.1f} | {r['cv']:.3f} | "
                f"{r['min_ns']:.1f} | {r['max_ns']:.1f} | "
                f"{r['max_over_min']:.2f} | "
                f"{int(r['wasted_inv_total']):,} | "
                f"{int(r['useful_inv_total']):,} | "
                f"{r['kernel_time_ms']:.3f} |"
            )
        md_lines.append("")

    md_lines.append("## Per-workload Spearman ρ across region sizes")
    md_lines.append("")
    md_lines.append("Two wasted-invalidation channels behave very "
                    "differently as region size grows: eviction-driven "
                    "(`InvalidateInvalidBlock-Evict`) peaks then collapses "
                    "to zero once the directory stops overflowing; "
                    "write-driven (`InvalidateInvalidBlock-Write`) grows "
                    "super-linearly because each remote write to a coarse "
                    "region forces invalidations to every recorded sub-line "
                    "× sharer, and most of those sub-lines are not cached. "
                    "We test each separately.")
    md_lines.append("")

    def per_wl_corr(metric_name: str, metric_fn) -> None:
        md_lines.append(f"### vs {metric_name}")
        md_lines.append("")
        md_lines.append("| workload | n configs | ρ(CV) | ρ(range) | ρ(max÷min) |")
        md_lines.append("|---|---:|---:|---:|---:|")
        for wl, rs in by_wl.items():
            active = [r for r in rs if metric_fn(r) > 0]
            if len(active) < 3:
                md_lines.append(f"| {wl} | {len(active)} | — | — | — |")
                continue
            xs = [metric_fn(r) for r in active]
            md_lines.append(
                f"| {wl} | {len(active)} | "
                f"{spearman([r['cv'] for r in active], xs):+.3f} | "
                f"{spearman([r['range_ns'] for r in active], xs):+.3f} | "
                f"{spearman([r['max_over_min'] for r in active], xs):+.3f} |"
            )
        md_lines.append("")

    per_wl_corr("evict-driven wasted_inv", lambda r: r["wasted_inv_evict"])
    per_wl_corr("write-driven wasted_inv", lambda r: r["wasted_inv_write"])
    per_wl_corr("total wasted_inv",        lambda r: r["wasted_inv_total"])

    md_lines.append("## Pooled Spearman across all active (workload, config)")
    md_lines.append("")
    for label, fn in [
        ("evict-driven wasted_inv", lambda r: r["wasted_inv_evict"]),
        ("write-driven wasted_inv", lambda r: r["wasted_inv_write"]),
        ("total wasted_inv",        lambda r: r["wasted_inv_total"]),
    ]:
        active_rows = [r for r in rows if fn(r) > 0]
        if len(active_rows) < 3:
            continue
        xs = [fn(r) for r in active_rows]
        md_lines.append(f"### vs {label} (n = {len(active_rows)})")
        md_lines.append(
            f"- ρ(CV, x)       = {spearman([r['cv'] for r in active_rows], xs):+.3f}"
        )
        md_lines.append(
            f"- ρ(range, x)    = {spearman([r['range_ns'] for r in active_rows], xs):+.3f}"
        )
        md_lines.append(
            f"- ρ(max÷min, x)  = {spearman([r['max_over_min'] for r in active_rows], xs):+.3f}"
        )
        md_lines.append("")

    OUT_MD.write_text("\n".join(md_lines) + "\n")
    print(f"wrote table to {OUT_MD}")

    print()
    print("=== Summary printed to stdout ===")
    for line in md_lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
