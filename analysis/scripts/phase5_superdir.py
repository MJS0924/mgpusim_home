#!/usr/bin/env python3
"""PHASE 5: SuperDir Internal Behavior (superdirectory scheme only).

Metrics from GPU[g].SuperDir:
  UpdateEntry, InvalidateByEviction, InvalidateByWrite, InvalidateByPromotion,
  InvalidateByDemotion, ToLocalData, ToRemoteData, FromLocal, FromRemote
  req_average_latency

Bank-split metrics (metric_index = 0..4):
  Bank 0: 64B region  (1 cacheline)  — note: verify from source
  Bank 1: 256B region (4 cachelines)
  Bank 2: 1KB region  (16 cachelines)
  Bank 3: 4KB region  (64 cachelines)
  Bank 4: 16KB region (256 cachelines)
  (Must verify from Go source — assumption based on design description)

BankChecked - k: how many banks were checked in serial lookup (k = lookup depth)
"""

import csv
from pathlib import Path
from collections import defaultdict

MGPUSIM_HOME = Path("/root/mgpusim_home")
ANALYSIS = MGPUSIM_HOME / "analysis"
PARSED_DIR = ANALYSIS / "parsed"
TABLES = ANALYSIS / "tables"
FAIL_LOG = ANALYSIS / "FAIL_LOG.md"
TABLES.mkdir(parents=True, exist_ok=True)

COMPUTE_GPUS = {2, 3, 4, 5}
SUPERDIR_WORKLOADS = ["bfs", "im2col", "matrixmultiplication", "pagerank"]

# Bank index → region size (to be verified in Go source)
# Provisional mapping from prompt description: bank 4=64B → bank 0=64B based on data observation
# The prompt says: 0=16KB, 1=4KB, 2=1KB, 3=256B, 4=64B
# Verify below.
BANK_SIZES_PROMPT = {0: "16KB", 1: "4KB", 2: "1KB", 3: "256B", 4: "64B"}

print("=== PHASE 5: SuperDir Internal Behavior ===\n")
print("Loading parsed/long.csv ...")

data = defaultdict(list)
with open(PARSED_DIR / "long.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        data[(row["scheme"], row["workload"])].append(row)

def fval(r):
    try: return float(r["value"])
    except: return None

# ---------------------------------------------------------------------------
# For each workload, aggregate SuperDir metrics across compute GPUs
# ---------------------------------------------------------------------------
# Check what bank indices appear
all_bank_indices = set()
for wl in SUPERDIR_WORKLOADS:
    for r in data[("superdirectory", wl)]:
        if r["comp_type"] == "SuperDir" and r["metric_index"] is not None:
            try:
                all_bank_indices.add(int(r["metric_index"]))
            except:
                pass
print(f"Bank indices found in data: {sorted(all_bank_indices)}")

# Check what BankChecked indices appear
all_bc_indices = set()
for wl in SUPERDIR_WORKLOADS:
    for r in data[("superdirectory", wl)]:
        if r["comp_type"] == "SuperDir" and r["metric_base"] == "BankChecked" and r["metric_index"] is not None:
            try:
                all_bc_indices.add(int(r["metric_index"]))
            except:
                pass
print(f"BankChecked indices found in data: {sorted(all_bc_indices)}")

breakdown_rows = []

for wl in SUPERDIR_WORKLOADS:
    rows = data[("superdirectory", wl)]
    sd_rows = [r for r in rows if r["comp_type"] == "SuperDir"
               and r["gpu_id"] and int(r["gpu_id"]) in COMPUTE_GPUS]

    # Aggregate across GPUs
    agg = defaultdict(float)
    bank_split = defaultdict(lambda: defaultdict(float))  # bank_idx -> metric_base -> count
    bc_split = defaultdict(float)  # BankChecked[k] -> count

    for r in sd_rows:
        mb = r["metric_base"]
        mi = r["metric_index"]
        v = fval(r)
        if v is None:
            continue

        if mi is not None:
            try:
                mi = int(mi)
            except:
                mi = None

        if mb == "BankChecked" and mi is not None:
            bc_split[mi] += v
        elif mi is not None:
            bank_split[mi][mb] += v
        else:
            agg[mb] += v

    # Summary
    print(f"\n=== {wl} ===")
    print(f"  Totals (sum over GPU 2-5):")
    for k in ["UpdateEntry","InvalidateByEviction","InvalidateByWrite",
              "InvalidateByPromotion","InvalidateByDemotion",
              "ToLocalData","ToRemoteData","FromLocal","FromRemote"]:
        print(f"    {k:30s} = {int(agg.get(k,0)):>10,d}")

    total_update = agg.get("UpdateEntry", 0)
    total_adapt = agg.get("InvalidateByPromotion", 0) + agg.get("InvalidateByDemotion", 0)
    adapt_ratio = total_adapt / total_update if total_update > 0 else None
    print(f"  Adaptation ratio (Prom+Dem)/UpdateEntry = "
          f"{adapt_ratio:.4f}" if adapt_ratio else "  Adaptation ratio: N/A (UpdateEntry=0)")

    # Bank utilization
    print(f"\n  Bank utilization (UpdateEntry - bank_idx):")
    total_bank_update = sum(bank_split[b].get("UpdateEntry",0) for b in all_bank_indices)
    for bi in sorted(all_bank_indices):
        cnt = bank_split[bi].get("UpdateEntry", 0)
        pct = cnt/total_bank_update*100 if total_bank_update > 0 else 0
        label = BANK_SIZES_PROMPT.get(bi, f"bank{bi}")
        inv_by_w = bank_split[bi].get("InvalidateByWrite", 0)
        inv_by_e = bank_split[bi].get("InvalidateByEviction", 0)
        inv_by_p = bank_split[bi].get("InvalidateByPromotion", 0)
        inv_by_d = bank_split[bi].get("InvalidateByDemotion", 0)
        print(f"    bank {bi} ({label:6s}): UpdateEntry={int(cnt):>8,d} ({pct:5.1f}%)  "
              f"InvWrite={int(inv_by_w):>6,d}  InvEvict={int(inv_by_e):>6,d}  "
              f"InvProm={int(inv_by_p):>5,d}  InvDem={int(inv_by_d):>5,d}")

        breakdown_rows.append({
            "workload": wl, "bank_idx": bi, "bank_size": label,
            "UpdateEntry": int(cnt), "bank_pct": pct,
            "InvalidateByWrite": int(inv_by_w), "InvalidateByEviction": int(inv_by_e),
            "InvalidateByPromotion": int(inv_by_p), "InvalidateByDemotion": int(inv_by_d),
        })

    # BankChecked distribution
    print(f"\n  BankChecked distribution (lookup depth):")
    total_bc = sum(bc_split.values())
    for k in sorted(bc_split.keys()):
        cnt = bc_split[k]
        pct = cnt/total_bc*100 if total_bc > 0 else 0
        print(f"    BankChecked[{k}] = {int(cnt):>10,d}  ({pct:5.1f}%)")
    if total_bc > 0:
        depth_1_pct = bc_split.get(1, 0) / total_bc * 100
        avg_depth = sum(k * cnt for k,cnt in bc_split.items()) / total_bc
        print(f"    Average lookup depth: {avg_depth:.2f}")
        print(f"    BankChecked[1] (single-step) fraction: {depth_1_pct:.1f}%")

    # Invalidation breakdown
    print(f"\n  Invalidation breakdown:")
    total_inv = (agg.get("InvalidateByEviction",0) + agg.get("InvalidateByWrite",0) +
                 agg.get("InvalidateByPromotion",0) + agg.get("InvalidateByDemotion",0))
    for inv_type in ["InvalidateByEviction","InvalidateByWrite","InvalidateByPromotion","InvalidateByDemotion"]:
        cnt = agg.get(inv_type, 0)
        pct = cnt/total_inv*100 if total_inv > 0 else 0
        print(f"    {inv_type:25s} = {int(cnt):>8,d}  ({pct:5.1f}%)")

    # Directory latency
    lat_rows = [r for r in sd_rows if r["metric_base"] == "req_average_latency"]
    if lat_rows:
        lats = [fval(r) for r in lat_rows if fval(r) is not None]
        print(f"\n  req_average_latency: mean={sum(lats)/len(lats)*1e9:.2f}ns "
              f"min={min(lats)*1e9:.2f}ns max={max(lats)*1e9:.2f}ns ({len(lats)} GPUs)")

# Write breakdown table
bd_fields = ["workload","bank_idx","bank_size","UpdateEntry","bank_pct",
             "InvalidateByWrite","InvalidateByEviction","InvalidateByPromotion","InvalidateByDemotion"]
with open(TABLES / "05_superdir_breakdown.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=bd_fields)
    w.writeheader()
    w.writerows(breakdown_rows)

# Verify bank size mapping from source
print("\n\n=== Checking Go source for bank size definitions ===")
import subprocess
src_dir = MGPUSIM_HOME / "mgpusim"
result = subprocess.run(
    ["grep", "-rn", "bank\|Bank\|region.*size\|RegionSize\|64B\|256B\|1KB\|4KB\|16KB",
     "--include=*.go", str(src_dir)],
    capture_output=True, text=True
)
lines = result.stdout.strip().split('\n') if result.stdout else []
# Filter for superdirectory
sd_lines = [l for l in lines if 'super' in l.lower() or 'superdir' in l.lower() or 'bank' in l.lower()]
for l in sd_lines[:30]:
    print(f"  {l}")

# ---------------------------------------------------------------------------
# PHASE 5 Checklist
# ---------------------------------------------------------------------------
print("\n\n=== PHASE 5 CHECKLIST ===")

# Check bank index mapping
print("[WARN] Bank index → region size: provisional mapping from prompt description:")
for bi, sz in BANK_SIZES_PROMPT.items():
    print(f"       bank {bi} → {sz}  (MUST verify in Go source before paper submission)")

# Check adaptation activity
for wl in SUPERDIR_WORKLOADS:
    rows = data[("superdirectory", wl)]
    sd_rows = [r for r in rows if r["comp_type"] == "SuperDir"
               and r["gpu_id"] and int(r["gpu_id"]) in COMPUTE_GPUS]
    agg = defaultdict(float)
    for r in sd_rows:
        if r["metric_index"] is None:
            v = fval(r)
            if v:
                agg[r["metric_base"]] += v
    prom = agg.get("InvalidateByPromotion", 0)
    dem = agg.get("InvalidateByDemotion", 0)
    if prom == 0 and dem == 0:
        print(f"[WARN R5-3] {wl}: Promotion=0 AND Demotion=0 — "
              "adaptation mechanism did NOT trigger for this workload. "
              "Paper's 'dynamic adaptation' claim weakened for this workload.")
    else:
        print(f"[INFO] {wl}: Promotion={int(prom)}, Demotion={int(dem)} — adaptation triggered")

# Check for bank diversity (R5-1: not all in one bank)
print("\n[INFO] Bank diversity check (≥3 banks with >10% share needed for R5-1 defense):")
for wl in SUPERDIR_WORKLOADS:
    bank_data = [r for r in breakdown_rows if r["workload"]==wl]
    significant_banks = [r for r in bank_data if r["bank_pct"] > 10]
    total_b = sum(r["UpdateEntry"] for r in bank_data)
    if total_b == 0:
        print(f"  {wl}: UpdateEntry=0 — no region assignments recorded!")
        continue
    dominant = max(bank_data, key=lambda r: r["bank_pct"]) if bank_data else None
    if dominant:
        print(f"  {wl}: {len(significant_banks)}/5 banks >10%  dominant=bank{dominant['bank_idx']}({dominant['bank_size']}) "
              f"{dominant['bank_pct']:.1f}%  ← {'✓ diverse' if len(significant_banks)>=3 else '⚠ concentrated'}")

print("\nPHASE 5 COMPLETE")
