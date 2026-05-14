#!/usr/bin/env python3
"""
rdma_traffic_vs_region.py — quantify how wasted invalidation translates
to inter-GPU link traffic, using only what's already in summary.csv.

Inputs:
  results/summary.csv (variant=CD rows)
Outputs:
  results/figures/fig_h_rdma_traffic.csv
  results/figures/fig_h_rdma_traffic_table.md
  stdout: per-workload table + pooled correlations.

What this measures (from existing counters, no resimulation):

  • RDMA_InvReq_bytes / RDMA_total_bytes — share of inter-GPU link
    traffic that is invalidation control vs data movement.

  • inv_bytes / kernel_time(s) — effective BW the link spends on
    invalidation traffic (GB/s). Compare to data BW for context.

  • wasted_inv_ratio = InvalidateInvalidBlock / (InvalidateValidBlock +
    InvalidateInvalidBlock) — fraction of invalidation messages whose
    target was already invalid in the receiver's L2.

  • inv_msg_count = InvReq_bytes / 12 (per-message size from raw dumps).
    Cross-check: should be close to L2 InvalidateValidBlock +
    InvalidateInvalidBlock summed across remote sharers.

  • wasted_link_bytes = inv_msg_count × wasted_inv_ratio × (12 + 4) —
    estimated bytes the link spends on invalidations that find the line
    already invalid. This is the "directly wasted on the link" number.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path("/root/mgpusim_home/results")
SUMMARY_CSV = ROOT / "summary.csv"
OUT_CSV = ROOT / "figures" / "fig_h_rdma_traffic.csv"
OUT_MD = ROOT / "figures" / "fig_h_rdma_traffic_table.md"

CD_ORDER = ["0", "1", "2", "4", "6", "8"]
CD_TO_BYTES = {c: 64 * (1 << int(c)) for c in CD_ORDER}

INV_REQ_SIZE = 12  # bytes per Inv Req message (from raw dump)
INV_RSP_SIZE = 4   # bytes per Inv Rsp message


def spearman(xs, ys):
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
            avg_rank = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg_rank
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = sum((rx[i] - mx) ** 2 for i in range(n)) ** 0.5
    dy = sum((ry[i] - my) ** 2 for i in range(n)) ** 0.5
    return num / (dx * dy) if dx * dy > 0 else float("nan")


def main() -> int:
    rows_in = []
    with SUMMARY_CSV.open() as f:
        for r in csv.DictReader(f):
            if r["variant"] != "CD" or r["config"] not in CD_ORDER:
                continue
            rows_in.append(r)

    rows = []
    for r in rows_in:
        cfg = r["config"]
        kt = float(r["kernel_time(s)"]) if r["kernel_time(s)"] else 0.0
        inv_req_b = float(r["RDMA_InvReq_bytes"] or 0)
        inv_rsp_b = float(r["RDMA_InvRsp_bytes"] or 0)
        inv_b = inv_req_b + inv_rsp_b
        total_b = float(r["RDMA_total_bytes"] or 0)
        rd_b = float(r["RDMA_ReadReq_bytes"] or 0) + float(r["RDMA_ReadRsp_bytes"] or 0)
        wr_b = float(r["RDMA_WriteReq_bytes"] or 0) + float(r["RDMA_WriteRsp_bytes"] or 0)

        valid_block = float(r["L2_InvalidateValidBlock"] or 0)
        invalid_block = float(r["L2_InvalidateInvalidBlock"] or 0)
        valid_w = float(r["L2_InvalidateValidBlock-Write"] or 0)
        invalid_w = float(r["L2_InvalidateInvalidBlock-Write"] or 0)
        valid_e = float(r["L2_InvalidateValidBlock-Evict"] or 0)
        invalid_e = float(r["L2_InvalidateInvalidBlock-Evict"] or 0)
        inv_msg_arrivals = valid_block + invalid_block
        wasted_ratio = invalid_block / inv_msg_arrivals if inv_msg_arrivals > 0 else 0.0

        # Estimated link bytes spent specifically on wasted invalidations.
        # Each Inv arriving at an L2 corresponds to one InvReq (12B) +
        # one InvRsp (4B) on the inter-GPU link (when the receiver is on
        # a different GPU than the directory). For a 4-GPU symmetric
        # setup with the home GPU excluded from sharers, almost every
        # Inv hits the link.
        wasted_link_bytes_est = invalid_block * (INV_REQ_SIZE + INV_RSP_SIZE)

        rows.append({
            "workload": r["workload"],
            "config": cfg,
            "region_bytes": CD_TO_BYTES[cfg],
            "kernel_ms": kt * 1000,
            "RDMA_total_bytes": total_b,
            "RDMA_total_GBps": (total_b / kt / 1e9) if kt > 0 else 0,
            "RDMA_inv_bytes": inv_b,
            "RDMA_inv_share_pct": (inv_b / total_b * 100) if total_b > 0 else 0,
            "RDMA_inv_GBps": (inv_b / kt / 1e9) if kt > 0 else 0,
            "RDMA_read_bytes": rd_b,
            "RDMA_write_bytes": wr_b,
            "inv_msg_count_link": inv_req_b / INV_REQ_SIZE,  # est. RDMA-side messages
            "L2_inv_arrivals": inv_msg_arrivals,
            "L2_inv_valid": valid_block,
            "L2_inv_invalid": invalid_block,
            "wasted_ratio": wasted_ratio,
            "L2_inv_evict_wasted": invalid_e,
            "L2_inv_write_wasted": invalid_w,
            "wasted_link_bytes_est": wasted_link_bytes_est,
            "wasted_link_share_pct": (wasted_link_bytes_est / total_b * 100) if total_b > 0 else 0,
            "wasted_link_GBps": (wasted_link_bytes_est / kt / 1e9) if kt > 0 else 0,
        })

    rows.sort(key=lambda x: (x["workload"], x["region_bytes"]))
    cols = list(rows[0].keys())
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT_CSV}")

    md = ["# RDMA / inter-GPU link traffic vs region size", ""]
    md.append("Reads from `summary.csv` (variant=CD). All 'wasted' "
              "numbers refer to invalidation messages whose target was "
              "already invalid at the receiving L2 "
              "(`L2_InvalidateInvalidBlock`).")
    md.append("")
    md.append("Estimated wasted link bytes = "
              "`L2_InvalidateInvalidBlock × (InvReq=12B + InvRsp=4B)`. "
              "Each L2 arrival from a remote directory crosses the RDMA "
              "link, so this is the bytes the link spent on messages "
              "that did nothing useful at the receiver.")
    md.append("")

    by_wl: dict[str, list[dict]] = {}
    for r in rows:
        by_wl.setdefault(r["workload"], []).append(r)

    for wl, rs in by_wl.items():
        md.append(f"## {wl}")
        md.append("")
        md.append(
            "| region | total RDMA (MB) | inv (MB) | inv share | "
            "inv BW (GB/s) | wasted L2 invs | wasted ratio | "
            "wasted link (MB) | wasted/total | kern (ms) |"
        )
        md.append(
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
        )
        for r in rs:
            md.append(
                f"| {r['region_bytes']}B | "
                f"{r['RDMA_total_bytes']/1e6:.1f} | "
                f"{r['RDMA_inv_bytes']/1e6:.2f} | "
                f"{r['RDMA_inv_share_pct']:.2f}% | "
                f"{r['RDMA_inv_GBps']:.3f} | "
                f"{int(r['L2_inv_invalid']):,} | "
                f"{r['wasted_ratio']*100:.1f}% | "
                f"{r['wasted_link_bytes_est']/1e6:.2f} | "
                f"{r['wasted_link_share_pct']:.2f}% | "
                f"{r['kernel_ms']:.3f} |"
            )
        md.append("")

    md.append("## Spearman ρ across region sizes (per workload)")
    md.append("")
    md.append("Tests whether RDMA invalidation bytes + wasted bytes track "
              "region size. Active = directory had ≥1 invalidation "
              "(otherwise the row is all zeros and ranks tie).")
    md.append("")
    md.append("| workload | n | ρ(region, inv MB) | ρ(region, wasted MB) | "
              "ρ(region, inv share%) | ρ(region, wasted ratio) |")
    md.append("|---|---:|---:|---:|---:|---:|")
    for wl, rs in by_wl.items():
        active = [r for r in rs if r["L2_inv_arrivals"] > 0]
        if len(active) < 3:
            md.append(f"| {wl} | {len(active)} | — | — | — | — |")
            continue
        regs = [r["region_bytes"] for r in active]
        invs = [r["RDMA_inv_bytes"] for r in active]
        wasted = [r["wasted_link_bytes_est"] for r in active]
        share = [r["RDMA_inv_share_pct"] for r in active]
        wr = [r["wasted_ratio"] for r in active]
        md.append(
            f"| {wl} | {len(active)} | {spearman(regs, invs):+.3f} | "
            f"{spearman(regs, wasted):+.3f} | "
            f"{spearman(regs, share):+.3f} | "
            f"{spearman(regs, wr):+.3f} |"
        )
    md.append("")

    md.append("## Pooled across all (workload, region)")
    md.append("")
    active = [r for r in rows if r["L2_inv_arrivals"] > 0]
    if len(active) >= 3:
        regs = [r["region_bytes"] for r in active]
        md.append(
            f"- ρ(region, inv bytes)        = {spearman(regs, [r['RDMA_inv_bytes'] for r in active]):+.3f}"
        )
        md.append(
            f"- ρ(region, wasted link bytes)= {spearman(regs, [r['wasted_link_bytes_est'] for r in active]):+.3f}"
        )
        md.append(
            f"- ρ(region, inv share%)       = {spearman(regs, [r['RDMA_inv_share_pct'] for r in active]):+.3f}"
        )
        md.append(
            f"- ρ(region, wasted ratio%)    = {spearman(regs, [r['wasted_ratio']*100 for r in active]):+.3f}"
        )
        md.append("")
        md.append(f"(n = {len(active)})")

    OUT_MD.write_text("\n".join(md) + "\n")
    print(f"wrote table to {OUT_MD}")
    print()
    for line in md:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
