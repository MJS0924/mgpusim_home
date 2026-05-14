#!/usr/bin/env python3
"""
vmem_cpi_chain.py — recursive causality search.

Layer 0: cpi_VMem (the thing we want to explain).
Layer 1: which available metric most strongly co-moves with cpi_VMem
         across the 54 (workload, region size) panel?
Layer 2: which metric most strongly co-moves with that layer-1 winner?
…and so on, until we hit metrics that have no obvious upstream signal
in the available data, or until we cycle.

Why correlate, not regress: at this stage we want to *narrow the
suspect list*, not estimate effect sizes. Spearman ρ tolerates the
order-of-magnitude differences across workloads (cpi_VMem ranges from
~1 to >1500 between mm and matrixtranspose) and is monotone-invariant,
so we don't have to pre-log-transform or worry about scale.

Two normalization views are reported because they answer different
questions:

  (A) "Across the panel" (raw): each (workload, region) is a sample.
      ρ here mostly captures cross-workload differences (mm has low
      cpi_VMem, mt has very high cpi_VMem); region-size variation
      within a workload contributes little to the rank.

  (B) "Within-workload deltas": within each workload subtract that
      workload's CD_0 value from every config's value, then pool. This
      removes cross-workload baseline differences and isolates
      "what changes as we sweep region size."

Output:
  results/figures/fig_i_vmem_chain.csv  (panel data + derived metrics)
  results/figures/fig_i_vmem_chain.md   (per-stage ranked correlates)
"""

from __future__ import annotations

import csv
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path("/root/mgpusim_home/results")
DATA_DIR = ROOT / "data"
SUMMARY_CSV = ROOT / "summary.csv"
CPI_CACHE = ROOT / "figures" / "fig_i_cpi_cache.csv"
OUT_CSV = ROOT / "figures" / "fig_i_vmem_chain.csv"
OUT_MD = ROOT / "figures" / "fig_i_vmem_chain.md"

CD_ORDER = ["0", "1", "2", "4", "6", "8"]
CD_TO_BYTES = {c: 64 * (1 << int(c)) for c in CD_ORDER}


# ─────────────────────── Stat helpers ───────────────────────
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


# ─────────────────── Per-component aggregators ───────────────────
LATENCY_RE = re.compile(
    r"^(GPU\[[2-5]\]\.\S+)\treq_average_latency\t([\d.eE+-]+)\tsecond",
    re.MULTILINE,
)
TLB_HIT_RE = re.compile(
    r"^GPU\[[2-5]\]\.SA\[\d+\]\.L1VTLB\[\d+\]\t(hit|miss|mshr-hit)\t"
    r"([\d.eE+-]+)\tcount",
    re.MULTILINE,
)
DRAM_RE = re.compile(
    r"^GPU\[[2-5]\]\.DRAM\[\d+\]\t(read_avg_latency|write_avg_latency)\t"
    r"([\d.eE+-]+)\tsecond",
    re.MULTILINE,
)


def parse_dump(path: Path) -> dict:
    """Pull every per-component aggregate we'll correlate against."""
    out: dict[str, float | None] = {}
    if not path.exists():
        return out
    text = path.read_text()

    by_loc: dict[str, list[float]] = defaultdict(list)
    for m in LATENCY_RE.finditer(text):
        by_loc[m.group(1)].append(float(m.group(2)))

    def _mean_for(name: str) -> float | None:
        vs = [v for loc, vs in by_loc.items() if name in loc for v in vs]
        return (statistics.fmean(vs) * 1e9) if vs else None

    def _spread_for(name: str) -> tuple[float | None, float | None,
                                        float | None, float | None]:
        """Return (mean, std, max÷min, top4_share) across all bank-mean
        latencies for components whose location contains `name`. All
        measurements are at the same per-bank granularity the simulator
        already records, so this captures *between-bank* skew."""
        vs = [v * 1e9 for loc, vs in by_loc.items() if name in loc
              for v in vs]
        if len(vs) < 2:
            return (None, None, None, None)
        s = sorted(vs)
        mean = statistics.fmean(s)
        std = statistics.pstdev(s)
        mom = s[-1] / s[0] if s[0] > 0 else float("inf")
        # Top-4 latency share if we have ≥8 banks; else None.
        top4 = (sum(s[-4:]) / sum(s)) if len(s) >= 8 else None
        return mean, std, mom, top4

    out["L1ICache_lat_ns"] = _mean_for("L1ICache")
    out["L1SCache_lat_ns"] = _mean_for("L1SCache")
    l1v_mean, l1v_std, l1v_mom, l1v_top4 = _spread_for("L1VCache")
    out["L1VCache_lat_ns"] = l1v_mean
    out["L1VCache_lat_std_ns"] = l1v_std
    out["L1VCache_lat_max_over_min"] = l1v_mom
    out["L1VCache_lat_top4_share"] = l1v_top4
    l2_mean, l2_std, l2_mom, l2_top4 = _spread_for("L2Cache")
    out["L2Cache_lat_ns"] = l2_mean
    out["L2Cache_lat_std_ns"] = l2_std
    out["L2Cache_lat_max_over_min"] = l2_mom
    out["L2Cache_lat_top4_share"] = l2_top4
    out["CohDir_lat_ns"] = _mean_for("CohDir")

    tlb_h = tlb_m = tlb_mshr = 0.0
    for m in TLB_HIT_RE.finditer(text):
        v = float(m.group(2))
        if m.group(1) == "hit":
            tlb_h += v
        elif m.group(1) == "miss":
            tlb_m += v
        else:
            tlb_mshr += v
    tot = tlb_h + tlb_m + tlb_mshr
    out["L1VTLB_miss_rate"] = (tlb_m / tot) if tot > 0 else None
    out["L1VTLB_mshr_hit_rate"] = (tlb_mshr / tot) if tot > 0 else None
    out["L1VTLB_total_accesses"] = tot

    dram_r, dram_w = [], []
    for m in DRAM_RE.finditer(text):
        if m.group(1) == "read_avg_latency":
            dram_r.append(float(m.group(2)))
        else:
            dram_w.append(float(m.group(2)))
    out["DRAM_read_lat_ns"] = (
        statistics.fmean(dram_r) * 1e9 if dram_r else None
    )
    out["DRAM_write_lat_ns"] = (
        statistics.fmean(dram_w) * 1e9 if dram_w else None
    )

    return out


# ────────────────────────── Main ──────────────────────────────
def main() -> int:
    summary = {}
    with SUMMARY_CSV.open() as f:
        for r in csv.DictReader(f):
            if r["variant"] != "CD" or r["config"] not in CD_ORDER:
                continue
            summary[(r["workload"], r["config"])] = r

    cpi: dict[tuple[str, str], dict] = {}
    if CPI_CACHE.exists():
        with CPI_CACHE.open() as f:
            for r in csv.DictReader(f):
                cpi[(r["workload"], str(r["config"]))] = r
    else:
        print(f"missing {CPI_CACHE}; run fig_i_ushape_attribution first",
              file=sys.stderr)
        return 1

    workloads = sorted({wl for wl, _ in summary})

    panel = []
    for wl in workloads:
        for cfg in CD_ORDER:
            r = summary.get((wl, cfg))
            cp = cpi.get((wl, cfg))
            if not r or not cp:
                continue
            row = {"workload": wl, "config": cfg,
                   "region_bytes": CD_TO_BYTES[cfg]}

            # CU-side
            row["cpi_VMem"] = float(cp["cpi_VMem"])
            row["cpi_VMemInst"] = float(cp["cpi_VMemInst"])
            row["cpi_VALU"] = float(cp["cpi_VALU"])
            row["cpi_total"] = float(cp["cpi_total"])
            row["cu_CPI"] = float(cp["cpi_total"])  # alias

            # Memory-hierarchy
            comp = parse_dump(DATA_DIR / wl / f"{wl}_CD_{cfg}.txt")
            for k, v in comp.items():
                row[k] = v

            # From summary.csv (already aggregated)
            kt = float(r["kernel_time(s)"]) or 0
            row["kernel_time_s"] = kt
            row["L2_hit_rate_pct"] = float(r["L2_hit_rate(%)"] or 0)
            row["L2_local_hit_pct"] = float(r["L2_local_hit_rate(%)"] or 0)
            row["L2_remote_hit_pct"] = float(r["L2_remote_hit_rate(%)"] or 0)
            row["L2_miss_total"] = sum(
                float(r.get(f"L2_read-miss-{x}") or 0)
                for x in ("cold", "capacity", "coh-write", "coh-evict", "other")
            )
            row["L2_miss_capacity"] = float(r["L2_read-miss-capacity"] or 0)
            row["L2_miss_coh_evict"] = float(r["L2_read-miss-coh-evict"] or 0)
            row["L2_miss_coh_write"] = float(r["L2_read-miss-coh-write"] or 0)
            row["L2_inv_valid"] = float(r["L2_InvalidateValidBlock"] or 0)
            row["L2_inv_invalid"] = float(r["L2_InvalidateInvalidBlock"] or 0)
            row["L2_evict_valid"] = float(r["L2_EvictValidBlock"] or 0)
            row["DRAM_read_count"] = float(r["DRAM_read_count"] or 0)
            row["DRAM_read_bytes"] = float(r["DRAM_read_bytes"] or 0)
            row["DRAM_write_count"] = float(r["DRAM_write_count"] or 0)
            row["DRAM_write_bytes"] = float(r["DRAM_write_bytes"] or 0)
            row["RDMA_total_bytes"] = float(r["RDMA_total_bytes"] or 0)
            row["RDMA_inv_bytes"] = (
                float(r["RDMA_InvReq_bytes"] or 0)
                + float(r["RDMA_InvRsp_bytes"] or 0)
            )
            row["dir_avg_latency_ns"] = float(r["dir_avg_latency(ns)"] or 0)

            panel.append(row)

    if not panel:
        print("no data", file=sys.stderr)
        return 1

    metric_cols = [k for k in panel[0].keys()
                   if k not in ("workload", "config", "region_bytes")]

    # Persist panel
    with OUT_CSV.open("w", newline="") as f:
        cols = ["workload", "config", "region_bytes"] + metric_cols
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(panel)
    print(f"wrote {len(panel)} rows to {OUT_CSV}")

    # Within-workload deltas (relative to CD_0).
    base_view: dict[str, dict] = {}
    for r in panel:
        if r["config"] == "0":
            base_view[r["workload"]] = r
    deltas = []
    for r in panel:
        if r["config"] == "0":
            continue
        base = base_view.get(r["workload"])
        if not base:
            continue
        d = {"workload": r["workload"], "config": r["config"],
             "region_bytes": r["region_bytes"]}
        for k in metric_cols:
            v0 = base.get(k)
            v1 = r.get(k)
            if v0 is None or v1 is None:
                d[k] = None
                continue
            try:
                if v0 == 0:
                    d[k] = v1 - v0  # absolute when baseline is zero
                else:
                    d[k] = (v1 - v0) / v0  # relative
            except Exception:
                d[k] = None
        deltas.append(d)

    # ────── Layer-by-layer correlation search ──────
    md: list[str] = []
    md.append("# Recursive causality search for cpi_VMem")
    md.append("")
    md.append("Two views per stage:")
    md.append("")
    md.append("  • **panel ρ**: Spearman over all 54 (workload, region) "
              "pairs. Captures cross-workload differences.")
    md.append("  • **within-workload Δ ρ**: same correlation but on "
              "within-workload deltas relative to CD_0 (n=45). "
              "Isolates region-sweep effects.")
    md.append("")

    # Helper: compute both ρ for a target metric vs every other column.
    # Ranking is by **within-Δ |ρ|** only — the panel ρ is dominated by
    # cross-workload absolute-scale differences and gives misleadingly
    # high correlations for any pair of "big" metrics. Δ ρ isolates the
    # region-sweep effect, which is what we actually want to attribute.
    def rank_correlates(target: str, exclude: set[str]) -> list[tuple]:
        out = []
        for k in metric_cols:
            if k == target or k in exclude:
                continue
            xs_p, ys_p = [], []
            for r in panel:
                if r.get(target) is None or r.get(k) is None:
                    continue
                xs_p.append(r[target])
                ys_p.append(r[k])
            xs_d, ys_d = [], []
            for r in deltas:
                if r.get(target) is None or r.get(k) is None:
                    continue
                xs_d.append(r[target])
                ys_d.append(r[k])
            if len(xs_p) < 5 or len(xs_d) < 5:
                continue
            rho_p = spearman(xs_p, ys_p)
            rho_d = spearman(xs_d, ys_d)
            score = abs(rho_d) if rho_d == rho_d else 0
            out.append((k, rho_p, len(xs_p), rho_d, len(xs_d), score))
        out.sort(key=lambda x: -x[5])
        return out

    # Tautological exclusions:
    #   - kernel_time_s  : both depend on runtime → trivial high ρ
    #   - cpi_total / cu_CPI : sums that include cpi_VMem
    #   - cpi_VMemInst   : structurally inverse to cpi_VMem
    #   - cpi_VALU       : another CPI component, not a memory cause
    chain_excludes: set[str] = {
        "kernel_time_s", "cpi_total", "cu_CPI",
        "cpi_VMemInst", "cpi_VALU",
    }
    chain = ["cpi_VMem"]

    md.append("## Stage layout")
    md.append("")
    md.append("Each stage takes the previous stage's winning metric as "
              "the new target, excludes already-cited metrics from the "
              "candidate pool (so the chain doesn't loop), and reports "
              "the top correlates by combined |ρ|.")
    md.append("")

    def fmt_row(k, rho_p, n_p, rho_d, n_d):
        rho_p_s = f"{rho_p:+.3f}" if rho_p == rho_p else "  —  "
        rho_d_s = f"{rho_d:+.3f}" if rho_d == rho_d else "  —  "
        return f"| {k} | {rho_p_s} ({n_p}) | {rho_d_s} ({n_d}) |"

    target = "cpi_VMem"
    for stage_idx in range(1, 6):
        chain_excludes.add(target)
        results = rank_correlates(target, chain_excludes)
        if not results:
            md.append(f"## Stage {stage_idx}: no correlates left for "
                      f"`{target}` — chain ends.")
            md.append("")
            break
        md.append(f"## Stage {stage_idx}: what correlates with `{target}`?")
        md.append("")
        md.append("Ranked by within-workload Δ |ρ|.")
        md.append("")
        md.append("| candidate | within-Δ ρ (n) | panel ρ (n) |")
        md.append("|---|---:|---:|")
        for k, rho_p, n_p, rho_d, n_d, _ in results[:12]:
            rho_p_s = f"{rho_p:+.3f}" if rho_p == rho_p else "  —  "
            rho_d_s = f"{rho_d:+.3f}" if rho_d == rho_d else "  —  "
            md.append(f"| {k} | {rho_d_s} ({n_d}) | {rho_p_s} ({n_p}) |")
        md.append("")
        winner = results[0][0]
        # Stop the chain if the top |ρ| is too weak — no real signal.
        if results[0][5] < 0.4:
            md.append(f"→ Stage {stage_idx}: top correlate's |Δρ| = "
                      f"{results[0][5]:.3f} < 0.4. Chain ends here "
                      "(no metric in the available data convincingly "
                      f"drives `{target}`).")
            md.append("")
            break
        chain.append(winner)
        md.append(f"→ Stage {stage_idx} winner: **`{winner}`** "
                  f"(Δρ = {results[0][3]:+.3f}).")
        md.append("")
        target = winner

    md.append("## Causality chain (top → bottom)")
    md.append("")
    md.append(" → ".join(f"`{c}`" for c in chain))
    md.append("")

    # Trajectory dump for the chosen chain.
    md.append("## Per-(workload, region) trajectory of the chain")
    md.append("")
    md.append("Each cell is **value at that config / value at that "
              "workload's CD_0**, so 1.00 means \"same as CD_0\".")
    md.append("")
    for c in chain:
        if c not in metric_cols:
            continue
        md.append(f"### `{c}`")
        md.append("")
        md.append("| workload | "
                  + " | ".join(f"CD_{cfg}" for cfg in CD_ORDER) + " |")
        md.append("|---" * (len(CD_ORDER) + 1) + "|")
        for wl in workloads:
            base = base_view.get(wl)
            if not base or base.get(c) in (None, 0):
                continue
            cells = []
            for cfg in CD_ORDER:
                r = next((p for p in panel
                          if p["workload"] == wl and p["config"] == cfg), None)
                if r is None or r.get(c) is None:
                    cells.append("—")
                    continue
                ratio = r[c] / base[c]
                cells.append(f"{ratio:.2f}×")
            md.append(f"| {wl} | " + " | ".join(cells) + " |")
        md.append("")

    OUT_MD.write_text("\n".join(md) + "\n")
    print(f"wrote chain to {OUT_MD}")
    print()
    for line in md:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
