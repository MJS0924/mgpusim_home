#!/usr/bin/env python3
"""
u_shape_attribution.py — find which counters explain the U-shaped
kernel-time curve vs coherence unit size.

Strategy:
  1. For each workload, identify the U-bottom CD (= argmin kernel_time).
  2. For each (workload, CD), compute relative degradation
     d_kt = (kt[CD] - kt[bottom]) / kt[bottom].
  3. For every candidate metric m, compute the same relative shift
     d_m = (m[CD] - m[bottom]) / m[bottom].
  4. Spearman ρ(d_kt, d_m) across all (workload, CD≠bottom) tells us
     which metric tracks performance loss away from the optimum.

Candidate metrics include things summary.csv already records plus
derived ratios (DRAM bytes / kernel_time, RDMA bytes / kernel_time,
invalidation work, useful_inv, etc.) and per-CU CPI stack categories
(VMem / ScalarMem / Idle / VALU) parsed from the raw .txt dumps.

Output:
  results/figures/fig_i_ushape_attribution.csv  (per (workload, CD) panel)
  results/figures/fig_i_ushape_attribution.md   (summary table)
"""

from __future__ import annotations

import csv
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path("/root/mgpusim_home/results")
SUMMARY_CSV = ROOT / "summary.csv"
DATA_DIR = ROOT / "data"
OUT_CSV = ROOT / "figures" / "fig_i_ushape_attribution.csv"
OUT_MD = ROOT / "figures" / "fig_i_ushape_attribution.md"

CD_ORDER = ["0", "1", "2", "4", "6", "8"]
CD_TO_BYTES = {c: 64 * (1 << int(c)) for c in CD_ORDER}

# Candidate "rate" metrics derived from summary.csv.
# (display_name, lambda r: float)  — r is a summary.csv row.
def f(col, default=0.0):
    return lambda r, _col=col: float(r.get(_col) or default)


SUMMARY_METRICS = {
    "kernel_time_s":            f("kernel_time(s)"),
    "L2_hit_rate":              f("L2_hit_rate(%)"),
    "L2_local_hit":             f("L2_local_hit_rate(%)"),
    "L2_remote_hit":            f("L2_remote_hit_rate(%)"),
    "dir_avg_latency_ns":       f("dir_avg_latency(ns)"),
    "dir_evict_count":          f("dir_EvictCount"),
    "L2_evict_valid":           f("L2_EvictValidBlock"),
    "L2_evict_invalid":         f("L2_EvictInvalidBlock"),
    "L2_inv_valid":             f("L2_InvalidateValidBlock"),
    "L2_inv_invalid":           f("L2_InvalidateInvalidBlock"),
    "L2_inv_valid_evict":       f("L2_InvalidateValidBlock-Evict"),
    "L2_inv_valid_write":       f("L2_InvalidateValidBlock-Write"),
    "L2_miss_cold":             f("L2_read-miss-cold"),
    "L2_miss_capacity":         f("L2_read-miss-capacity"),
    "L2_miss_coh_write":        f("L2_read-miss-coh-write"),
    "L2_miss_coh_evict":        f("L2_read-miss-coh-evict"),
    "L2_miss_other":            f("L2_read-miss-other"),
    "L2_miss_total": (lambda r: float(r.get("L2_read-miss-cold") or 0)
                      + float(r.get("L2_read-miss-capacity") or 0)
                      + float(r.get("L2_read-miss-coh-write") or 0)
                      + float(r.get("L2_read-miss-coh-evict") or 0)
                      + float(r.get("L2_read-miss-other") or 0)),
    "RDMA_total_bytes":         f("RDMA_total_bytes"),
    "RDMA_inv_bytes": (lambda r: float(r.get("RDMA_InvReq_bytes") or 0)
                       + float(r.get("RDMA_InvRsp_bytes") or 0)),
    "RDMA_read_bytes": (lambda r: float(r.get("RDMA_ReadReq_bytes") or 0)
                        + float(r.get("RDMA_ReadRsp_bytes") or 0)),
    "RDMA_write_bytes": (lambda r: float(r.get("RDMA_WriteReq_bytes") or 0)
                         + float(r.get("RDMA_WriteRsp_bytes") or 0)),
    "DRAM_total_bytes":         f("DRAM_total_bytes"),
    "DRAM_read_bytes":          f("DRAM_read_bytes"),
    "DRAM_write_bytes":         f("DRAM_write_bytes"),
    "DRAM_total_count":         f("DRAM_total_count"),
    "DRAM_read_count":          f("DRAM_read_count"),
    "DRAM_write_count":         f("DRAM_write_count"),
    "InvalidateByEviction":     f("InvalidateByEviction"),
    "ToRemoteData":             f("ToRemoteData"),
}

# Rate-form metrics (per kernel_time second) — to factor out the runtime
# itself. d_kt and d_m would otherwise be confounded for any volume metric
# that scales with kernel_time.
def rates(r):
    kt = float(r.get("kernel_time(s)") or 0)
    if kt <= 0:
        return {}
    out = {}
    for k, fn in SUMMARY_METRICS.items():
        if k in ("kernel_time_s", "L2_hit_rate", "L2_local_hit",
                 "L2_remote_hit", "dir_avg_latency_ns",
                 "dir_evict_count"):
            continue
        out[k + "_per_s"] = fn(r) / kt
    return out


# ─────────────────────── Per-CU CPI Stack parsing ───────────────────────
CPI_RE = re.compile(
    r"^GPU\[[2-5]\]\.SA\[\d+\]\.CU\[\d+\]\t(CPIStack\.\w+)\t([\d.eE+-]+)\t",
    re.MULTILINE,
)


def parse_cpi_stack(txt_path: Path) -> dict[str, float]:
    """Mean CPI per category across all CUs in GPU[2-5]."""
    accum: dict[str, list[float]] = defaultdict(list)
    try:
        text = txt_path.read_text()
    except OSError:
        return {}
    for m in CPI_RE.finditer(text):
        accum[m.group(1)].append(float(m.group(2)))
    return {k: statistics.fmean(v) for k, v in accum.items() if v}


# ─────────────────────────── Stats helpers ────────────────────────────
def spearman(xs, ys):
    if len(xs) < 3:
        return float("nan")

    def ranks(vs):
        order = sorted(range(len(vs)), key=lambda i: vs[i])
        r = [0.0] * len(vs)
        i = 0
        while i < len(vs):
            j = i
            while j + 1 < len(vs) and vs[order[j + 1]] == vs[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = sum((rx[i] - mx) ** 2 for i in range(n)) ** 0.5
    dy = sum((ry[i] - my) ** 2 for i in range(n)) ** 0.5
    return num / (dx * dy) if dx * dy > 0 else float("nan")


def main() -> int:
    summary: dict[tuple[str, str], dict] = {}
    with SUMMARY_CSV.open() as f_in:
        for r in csv.DictReader(f_in):
            if r["variant"] != "CD" or r["config"] not in CD_ORDER:
                continue
            summary[(r["workload"], r["config"])] = r

    workloads = sorted({wl for wl, _ in summary})

    # Bottom config = argmin kernel_time per workload.
    bottoms: dict[str, str] = {}
    for wl in workloads:
        candidates = [(cfg, float(summary[(wl, cfg)]["kernel_time(s)"]))
                      for cfg in CD_ORDER if (wl, cfg) in summary]
        bottoms[wl] = min(candidates, key=lambda x: x[1])[0]

    # Pull CPI stacks for every (workload, config).
    cpi_data: dict[tuple[str, str], dict] = {}
    for wl in workloads:
        for cfg in CD_ORDER:
            txt = DATA_DIR / wl / f"{wl}_CD_{cfg}.txt"
            if not txt.exists():
                continue
            cpi = parse_cpi_stack(txt)
            if cpi:
                cpi_data[(wl, cfg)] = cpi

    # Build the panel: one row per (workload, config), columns =
    # raw + per-second-rate metrics + CPI categories. Pre-compute the
    # full CPI key set so every panel row has the same fields (writers
    # need stable column lists).
    cpi_keys = set()
    for cpi in cpi_data.values():
        cpi_keys.update(cpi.keys())

    panel = []
    for wl in workloads:
        for cfg in CD_ORDER:
            r = summary.get((wl, cfg))
            if not r:
                continue
            row = {"workload": wl, "config": cfg,
                   "region_bytes": CD_TO_BYTES[cfg]}
            for k, fn in SUMMARY_METRICS.items():
                row[k] = fn(r)
            row.update(rates(r))
            cpi = cpi_data.get((wl, cfg), {})
            for k in cpi_keys:
                col = f"cpi_{k.replace('CPIStack.', '')}"
                row[col] = cpi.get(k, float("nan"))
            panel.append(row)

    # Compute relative deviation from each workload's U-bottom.
    # Skip the bottom row itself.
    metric_cols = [c for c in panel[0].keys()
                   if c not in ("workload", "config", "region_bytes")]
    deltas = []
    for r in panel:
        wl, cfg = r["workload"], r["config"]
        if cfg == bottoms[wl]:
            continue
        bot = next(p for p in panel
                   if p["workload"] == wl and p["config"] == bottoms[wl])
        d_row = {"workload": wl, "config": cfg, "bottom_cd": bottoms[wl],
                 "region_bytes": r["region_bytes"]}
        for k in metric_cols:
            base = bot.get(k, 0)
            cur = r.get(k, 0)
            if base in (0, None) or cur is None:
                d_row[k] = float("nan")
                continue
            try:
                d_row[k] = (cur - base) / base
            except ZeroDivisionError:
                d_row[k] = float("nan")
        deltas.append(d_row)

    if not deltas:
        print("no off-bottom rows extracted", file=sys.stderr)
        return 1

    # Persist the panel + deltas.
    OUT_CSV.parent.mkdir(exist_ok=True)
    with OUT_CSV.open("w", newline="") as f_out:
        cols = (["workload", "config", "bottom_cd", "region_bytes"]
                + metric_cols)
        w = csv.DictWriter(f_out, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(deltas)
    print(f"wrote {len(deltas)} delta rows to {OUT_CSV}")

    # Spearman of d_kt vs d_metric across all workloads, off-bottom only.
    d_kt = [r["kernel_time_s"] for r in deltas]
    rho_table = []
    for k in metric_cols:
        if k == "kernel_time_s":
            continue
        ys = []
        xs = []
        for i, r in enumerate(deltas):
            v = r.get(k, float("nan"))
            if isinstance(v, float) and (v != v):  # NaN
                continue
            xs.append(d_kt[i])
            ys.append(v)
        if len(xs) < 5:
            continue
        rho_table.append((k, spearman(xs, ys), len(xs)))

    rho_table.sort(key=lambda x: -abs(x[1]) if x[1] == x[1] else 0)

    md = ["# U-shape attribution: which metric tracks the rise off the optimum?",
          ""]
    md.append("**Method.** For each workload identify the coherence "
              "unit size that minimizes `kernel_time` (the U-bottom). "
              "Then for every other config measure the relative "
              "degradation Δ in kernel_time and in every candidate "
              "metric, and Spearman-correlate the two across all "
              "(workload, CD≠bottom) pairs (n=45). High |ρ| means the "
              "metric rises (or falls) in lockstep with kernel time as "
              "we move away from the U-bottom.")
    md.append("")
    md.append("**Per-workload U-bottom:**")
    md.append("")
    md.append("| workload | bottom CD | bottom region | bottom kernel (ms) |")
    md.append("|---|---:|---:|---:|")
    for wl in workloads:
        b = bottoms[wl]
        kt_b = float(summary[(wl, b)]["kernel_time(s)"]) * 1000
        md.append(f"| {wl} | {b} | {CD_TO_BYTES[b]}B | {kt_b:.3f} |")
    md.append("")

    md.append("## Spearman ρ(Δkernel_time, Δmetric), pooled n≈45")
    md.append("")
    md.append("Sorted by |ρ|. Positive ρ = metric grows when kernel "
              "slows. Negative ρ = metric shrinks when kernel slows.")
    md.append("")
    md.append("| metric | ρ | n |")
    md.append("|---|---:|---:|")
    for k, rho, n in rho_table[:40]:
        if rho != rho:  # NaN
            continue
        md.append(f"| {k} | {rho:+.3f} | {n} |")
    md.append("")

    # Also report ρ restricted to right-side-of-U only (region > bottom),
    # since that's the user's actual question (degradation as region grows
    # past the optimum).
    md.append("## Spearman ρ restricted to right-side-of-U (region > bottom)")
    md.append("")
    md.append("This isolates *coarsening past the optimum* — the side "
              "where wasted-invalidation amplification kicks in.")
    md.append("")
    md.append("| metric | ρ | n |")
    md.append("|---|---:|---:|")
    rho_right = []
    for k in metric_cols:
        if k == "kernel_time_s":
            continue
        xs, ys = [], []
        for r in deltas:
            if r["region_bytes"] <= CD_TO_BYTES[r["bottom_cd"]]:
                continue
            v = r.get(k, float("nan"))
            kt = r["kernel_time_s"]
            if isinstance(v, float) and (v != v):
                continue
            xs.append(kt)
            ys.append(v)
        if len(xs) < 5:
            continue
        rho_right.append((k, spearman(xs, ys), len(xs)))
    rho_right.sort(key=lambda x: -abs(x[1]) if x[1] == x[1] else 0)
    for k, rho, n in rho_right[:40]:
        if rho != rho:
            continue
        md.append(f"| {k} | {rho:+.3f} | {n} |")
    md.append("")

    # Per-workload kernel-time + top-3 candidate metrics for diagnosis.
    md.append("## Per-workload trajectory of top-correlated metrics")
    md.append("")
    md.append("For each workload: kernel_ms across CDs, plus the three "
              "right-side-of-U winning metrics in absolute terms so we "
              "can eyeball whether the U is actually visible there.")
    md.append("")
    top_metrics = [k for k, _, _ in rho_right[:5]]
    md.append("Top-5 by |ρ| right-side: " + ", ".join(top_metrics))
    md.append("")
    for wl in workloads:
        md.append(f"### {wl} (bottom = CD_{bottoms[wl]} = "
                  f"{CD_TO_BYTES[bottoms[wl]]}B)")
        md.append("")
        md.append("| CD | region | kern (ms) | "
                  + " | ".join(top_metrics) + " |")
        md.append("|---|---:|---:|" + "---:|" * len(top_metrics))
        for cfg in CD_ORDER:
            row = next((p for p in panel
                        if p["workload"] == wl and p["config"] == cfg), None)
            if not row:
                continue
            kt_ms = row["kernel_time_s"] * 1000
            mark = " *(bottom)*" if cfg == bottoms[wl] else ""
            cells = []
            for m in top_metrics:
                v = row.get(m, float("nan"))
                if isinstance(v, float) and v != v:
                    cells.append("—")
                elif abs(v) >= 1e9:
                    cells.append(f"{v/1e9:.2f}G")
                elif abs(v) >= 1e6:
                    cells.append(f"{v/1e6:.2f}M")
                elif abs(v) >= 1e3:
                    cells.append(f"{v/1e3:.2f}K")
                else:
                    cells.append(f"{v:.3f}")
            md.append(f"| {cfg}{mark} | {CD_TO_BYTES[cfg]}B | "
                      f"{kt_ms:.3f} | " + " | ".join(cells) + " |")
        md.append("")

    OUT_MD.write_text("\n".join(md) + "\n")
    print(f"wrote analysis to {OUT_MD}")
    print()
    for line in md:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
