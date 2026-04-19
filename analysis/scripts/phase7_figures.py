#!/usr/bin/env python3
"""PHASE 7: Figures and final REPORT.md.

Uses matplotlib (text-only fallback if not available).
All figures: PDF + PNG + CSV (source data).
"""

import csv
import math
from pathlib import Path
from collections import defaultdict

MGPUSIM_HOME = Path("/root/mgpusim_home")
ANALYSIS = MGPUSIM_HOME / "analysis"
TABLES = ANALYSIS / "tables"
FIGURES = ANALYSIS / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

# Check matplotlib availability
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print("[WARN] matplotlib not available — generating CSV sources only, no plots")

SCHEME_LABELS = {
    "CD": "CD",
    "REC": "REC",
    "HMG": "HMG",
    "superdirectory": "SuperDir",
}
SCHEME_COLORS = {
    "CD": "#4878CF",
    "REC": "#6ACC65",
    "HMG": "#D65F5F",
    "superdirectory": "#B47CC7",
}
WORKLOADS_ABBREV = {
    "im2col": "im2col",
    "matrixmultiplication": "MM",
    "bfs": "BFS",
    "pagerank": "PR",
}

# ---------------------------------------------------------------------------
# Load tables
# ---------------------------------------------------------------------------
def load_csv(path):
    if not path.exists():
        return []
    with open(path) as f:
        return list(csv.DictReader(f))

speedup = load_csv(TABLES / "02_speedup.csv")
exec_time = load_csv(TABLES / "02_exec_time.csv")
cache = load_csv(TABLES / "03_cache_summary.csv")
false_share = load_csv(TABLES / "03_false_sharing.csv")
network = load_csv(TABLES / "04_network_bytes.csv")
superdir_bd = load_csv(TABLES / "05_superdir_breakdown.csv")
crosscheck = load_csv(TABLES / "06_crosscheck.csv")

print("=== PHASE 7: Figures & Report ===\n")

# ---------------------------------------------------------------------------
# F-P1: Normalized speedup bar chart (CD=1.0)
# ---------------------------------------------------------------------------
SCHEMES = ["CD", "REC", "HMG", "superdirectory"]
WORKLOADS = ["im2col", "matrixmultiplication"]  # only where CD baseline exists

print("Generating F-P1: Speedup chart...")

fp1_data = []
for wl in WORKLOADS:
    for scheme in SCHEMES:
        row = next((r for r in speedup if r["scheme"]==scheme and r["workload"]==wl), None)
        if row:
            v = row["speedup_vs_cd"]
            try:
                fp1_data.append({"scheme": scheme, "workload": wl, "speedup": float(v)})
            except:
                fp1_data.append({"scheme": scheme, "workload": wl, "speedup": None})

with open(FIGURES / "FP1_speedup.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["scheme","workload","speedup"])
    w.writeheader()
    w.writerows(fp1_data)

if HAS_MPL:
    fig, ax = plt.subplots(figsize=(8, 4))
    x = range(len(WORKLOADS))
    width = 0.2
    offsets = [-1.5, -0.5, 0.5, 1.5]
    for i, scheme in enumerate(SCHEMES):
        vals = []
        for wl in WORKLOADS:
            row = next((r for r in fp1_data if r["scheme"]==scheme and r["workload"]==wl), None)
            vals.append(row["speedup"] if row and row["speedup"] else 0)
        bars = ax.bar([xi + offsets[i]*width for xi in x], vals, width,
                      label=SCHEME_LABELS[scheme], color=SCHEME_COLORS[scheme], alpha=0.85)
    ax.axhline(1.0, color="black", linewidth=0.8, linestyle="--", label="CD baseline")
    ax.set_xlabel("Workload")
    ax.set_ylabel("Normalized Speedup (CD = 1.0)")
    ax.set_title("F-P1: Normalized Speedup vs CD (2 workloads; bfs/pagerank CD baseline MISSING)")
    ax.set_xticks(list(x))
    ax.set_xticklabels([WORKLOADS_ABBREV.get(w, w) for w in WORKLOADS])
    ax.legend()
    ax.set_ylim(0, 1.4)
    plt.tight_layout()
    plt.savefig(FIGURES / "FP1_speedup.pdf", bbox_inches="tight")
    plt.savefig(FIGURES / "FP1_speedup.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {FIGURES}/FP1_speedup.pdf + .png")
else:
    print(f"  Saved (CSV only): {FIGURES}/FP1_speedup.csv")

# ---------------------------------------------------------------------------
# F-P2: NVLink bytes (normalized to CD)
# ---------------------------------------------------------------------------
print("Generating F-P2: Network bytes chart...")

fp2_data = []
cd_bytes = {wl: None for wl in WORKLOADS}
for wl in WORKLOADS:
    for r in network:
        if r["scheme"]=="CD" and r["workload"]==wl:
            cd_bytes[wl] = float(r["total_bytes"]) if r["total_bytes"] else None

for scheme in SCHEMES:
    for wl in WORKLOADS:
        row = next((r for r in network if r["scheme"]==scheme and r["workload"]==wl), None)
        if not row:
            continue
        total = float(row["total_bytes"])
        cd = cd_bytes.get(wl)
        norm = total / cd if cd and cd > 0 else None
        fp2_data.append({
            "scheme": scheme, "workload": wl,
            "total_bytes": total,
            "read_rsp_bytes": float(row["read_rsp_bytes"]),
            "write_req_bytes": float(row["write_req_bytes"]),
            "inv_req_bytes": float(row["inv_req_bytes"]),
            "normalized_to_cd": norm,
        })

with open(FIGURES / "FP2_network_bytes.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["scheme","workload","total_bytes","read_rsp_bytes",
                                       "write_req_bytes","inv_req_bytes","normalized_to_cd"])
    w.writeheader()
    w.writerows(fp2_data)

if HAS_MPL:
    fig, axes = plt.subplots(1, len(WORKLOADS), figsize=(10, 4), sharey=False)
    for wi, wl in enumerate(WORKLOADS):
        ax = axes[wi]
        cd_tb = cd_bytes.get(wl) or 1
        for i, scheme in enumerate(SCHEMES):
            row = next((r for r in fp2_data if r["scheme"]==scheme and r["workload"]==wl), None)
            if not row:
                continue
            rsp = row["read_rsp_bytes"] / cd_tb
            wreq = row["write_req_bytes"] / cd_tb
            inv = row["inv_req_bytes"] / cd_tb
            x_pos = i
            ax.bar(x_pos, rsp, color="#4878CF", alpha=0.85, label="Read Rsp" if i==0 else "")
            ax.bar(x_pos, wreq, bottom=rsp, color="#6ACC65", alpha=0.85, label="Write Req" if i==0 else "")
            ax.bar(x_pos, inv, bottom=rsp+wreq, color="#D65F5F", alpha=0.85, label="Inv Req" if i==0 else "")
        ax.set_title(WORKLOADS_ABBREV.get(wl, wl))
        ax.set_xticks(range(len(SCHEMES)))
        ax.set_xticklabels([SCHEME_LABELS[s] for s in SCHEMES], rotation=15)
        ax.set_ylabel("Normalized RDMA Bytes (CD=1.0)" if wi==0 else "")
        if wi == 0:
            ax.legend(fontsize=8)
    plt.suptitle("F-P2: Normalized RDMA Traffic (CD=1.0) — stacked by type")
    plt.tight_layout()
    plt.savefig(FIGURES / "FP2_network_bytes.pdf", bbox_inches="tight")
    plt.savefig(FIGURES / "FP2_network_bytes.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {FIGURES}/FP2_network_bytes.pdf + .png")

# ---------------------------------------------------------------------------
# F-P3: L2 cache hit rates
# ---------------------------------------------------------------------------
print("Generating F-P3: L2 miss rate chart...")

fp3_data = []
for scheme in SCHEMES:
    for wl in WORKLOADS:
        row = next((r for r in cache if r["scheme"]==scheme and r["workload"]==wl
                    and r["comp_type"]=="L2Cache"), None)
        if row and row["hit_rate"] != "N/A":
            fp3_data.append({
                "scheme": scheme, "workload": wl,
                "hit_rate": float(row["hit_rate"]),
                "miss_rate": 1 - float(row["hit_rate"]),
                "remote_hit_rate": float(row["remote_hit_rate"]) if row["remote_hit_rate"] != "N/A" else None,
            })

with open(FIGURES / "FP3_L2_miss_rate.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["scheme","workload","hit_rate","miss_rate","remote_hit_rate"])
    w.writeheader()
    w.writerows(fp3_data)

if HAS_MPL:
    fig, ax = plt.subplots(figsize=(8, 4))
    x = range(len(WORKLOADS))
    width = 0.2
    offsets = [-1.5, -0.5, 0.5, 1.5]
    for i, scheme in enumerate(SCHEMES):
        mrs = []
        for wl in WORKLOADS:
            row = next((r for r in fp3_data if r["scheme"]==scheme and r["workload"]==wl), None)
            mrs.append(row["miss_rate"] if row else 0)
        ax.bar([xi + offsets[i]*width for xi in x], mrs, width,
               label=SCHEME_LABELS[scheme], color=SCHEME_COLORS[scheme], alpha=0.85)
    ax.set_xlabel("Workload")
    ax.set_ylabel("L2 Cache Miss Rate")
    ax.set_title("F-P3: L2 Cache Miss Rate by Scheme (compute GPUs 2-5)")
    ax.set_xticks(list(x))
    ax.set_xticklabels([WORKLOADS_ABBREV.get(w, w) for w in WORKLOADS])
    ax.legend()
    plt.tight_layout()
    plt.savefig(FIGURES / "FP3_L2_miss_rate.pdf", bbox_inches="tight")
    plt.savefig(FIGURES / "FP3_L2_miss_rate.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {FIGURES}/FP3_L2_miss_rate.pdf + .png")

# ---------------------------------------------------------------------------
# F-P4: Region-size distribution per workload (SuperDir bank utilization)
# ---------------------------------------------------------------------------
print("Generating F-P4: Bank utilization chart...")
BANK_SIZES = {0: "16KB", 1: "4KB", 2: "1KB", 3: "256B", 4: "64B"}
SD_WORKLOADS = ["bfs", "im2col", "matrixmultiplication", "pagerank"]

fp4_data = []
for wl in SD_WORKLOADS:
    for bi in range(5):
        row = next((r for r in superdir_bd if r["workload"]==wl and int(r["bank_idx"])==bi), None)
        pct = float(row["bank_pct"]) if row else 0
        fp4_data.append({"workload": wl, "bank_idx": bi,
                          "bank_size": BANK_SIZES.get(bi, f"bank{bi}"), "pct": pct})

with open(FIGURES / "FP4_bank_utilization.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["workload","bank_idx","bank_size","pct"])
    w.writeheader()
    w.writerows(fp4_data)

if HAS_MPL:
    fig, ax = plt.subplots(figsize=(9, 4))
    x = range(len(SD_WORKLOADS))
    bottoms = [0]*len(SD_WORKLOADS)
    bank_colors = ["#4878CF","#6ACC65","#D65F5F","#B47CC7","#F0A500"]
    for bi in range(5):
        vals = [next((r["pct"] for r in fp4_data if r["workload"]==wl and r["bank_idx"]==bi), 0)
                for wl in SD_WORKLOADS]
        ax.bar(x, vals, bottom=bottoms, color=bank_colors[bi], alpha=0.85,
               label=f"bank{bi} ({BANK_SIZES.get(bi,'?')})")
        bottoms = [b+v for b,v in zip(bottoms, vals)]
    ax.set_xlabel("Workload")
    ax.set_ylabel("% of UpdateEntry")
    ax.set_title("F-P4: SuperDir Bank Utilization (region size distribution)\n"
                 "WARNING: 97-99% in bank4 (64B) — adaptation NEVER triggered")
    ax.set_xticks(list(x))
    ax.set_xticklabels([WORKLOADS_ABBREV.get(w, w) for w in SD_WORKLOADS])
    ax.legend(fontsize=8, loc="center right")
    ax.set_ylim(0, 102)
    plt.tight_layout()
    plt.savefig(FIGURES / "FP4_bank_utilization.pdf", bbox_inches="tight")
    plt.savefig(FIGURES / "FP4_bank_utilization.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {FIGURES}/FP4_bank_utilization.pdf + .png")

# ---------------------------------------------------------------------------
# F-P6: BankChecked depth (from PHASE 5 output, but we need the raw data)
# Re-load from parsed/long.csv
# ---------------------------------------------------------------------------
print("Generating F-P6: BankChecked CDF...")

from collections import defaultdict
bc_data_by_wl = defaultdict(lambda: defaultdict(float))
fp6_rows = []
try:
    with open(ANALYSIS / "parsed/long.csv") as f:
        for row in csv.DictReader(f):
            if (row["scheme"]=="superdirectory" and row["comp_type"]=="SuperDir"
                    and row["metric_base"]=="BankChecked"
                    and row["metric_index"] and row["value"]):
                wl = row["workload"]
                k = int(row["metric_index"])
                v = float(row["value"]) if row["value"] else 0
                bc_data_by_wl[wl][k] += v
except:
    pass

for wl in ["matrixmultiplication", "pagerank"]:
    bc = bc_data_by_wl[wl]
    total = sum(bc.values())
    if total == 0:
        continue
    cdf = 0
    for k in sorted(bc.keys()):
        cdf += bc[k] / total * 100
        fp6_rows.append({"workload": wl, "banks_checked": k, "count": bc[k],
                          "pct": bc[k]/total*100, "cdf_pct": cdf})

with open(FIGURES / "FP6_bankchecked_cdf.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["workload","banks_checked","count","pct","cdf_pct"])
    w.writeheader()
    w.writerows(fp6_rows)

if HAS_MPL and fp6_rows:
    fig, ax = plt.subplots(figsize=(6, 4))
    for wl in ["matrixmultiplication", "pagerank"]:
        rows = [r for r in fp6_rows if r["workload"]==wl]
        if rows:
            ax.plot([r["banks_checked"] for r in rows], [r["cdf_pct"] for r in rows],
                    marker="o", label=WORKLOADS_ABBREV.get(wl,wl))
    ax.axhline(90, color="gray", linestyle="--", linewidth=0.8, label="90% line")
    ax.set_xlabel("Number of Banks Checked (lookup depth)")
    ax.set_ylabel("CDF (%)")
    ax.set_title("F-P6: SuperDir BankChecked CDF\n"
                 "Note: avg MM=2.55, PR=2.95 banks/request")
    ax.legend()
    ax.set_ylim(0, 105)
    plt.tight_layout()
    plt.savefig(FIGURES / "FP6_bankchecked_cdf.pdf", bbox_inches="tight")
    plt.savefig(FIGURES / "FP6_bankchecked_cdf.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {FIGURES}/FP6_bankchecked_cdf.pdf + .png")

# ---------------------------------------------------------------------------
# L2Cache latency comparison table (key attribution)
# ---------------------------------------------------------------------------
l2lat_rows = []
for scheme in SCHEMES:
    for wl in WORKLOADS:
        rows_l2 = [r for r in cache if r["scheme"]==scheme and r["workload"]==wl
                   and r["comp_type"]=="L2Cache"]
        if rows_l2:
            l2lat_rows.append({"scheme": scheme, "workload": wl,
                                "note": "See 03_cache_summary.csv for latency values"})
with open(FIGURES / "attribution_L2latency.csv", "w", newline="") as f:
    # Write the key numbers from phase3
    w = csv.writer(f)
    w.writerow(["scheme", "workload", "L2Cache_req_avg_latency_ns", "speedup_vs_cd"])
    latency_data = {
        ("CD", "im2col"): 346.14, ("REC", "im2col"): 215.37,
        ("HMG", "im2col"): 343.11, ("superdirectory", "im2col"): 340.83,
        ("CD", "matrixmultiplication"): 728.63, ("REC", "matrixmultiplication"): 690.16,
        ("HMG", "matrixmultiplication"): 739.31, ("superdirectory", "matrixmultiplication"): 998.89,
    }
    speedup_map = {}
    for r in speedup:
        try:
            speedup_map[(r["scheme"], r["workload"])] = float(r["speedup_vs_cd"])
        except:
            pass
    for (sc, wl), lat in latency_data.items():
        w.writerow([sc, wl, lat, speedup_map.get((sc,wl), "N/A")])
print(f"  Saved: {FIGURES}/attribution_L2latency.csv")

print("\nAll PHASE 7 figures generated.")
