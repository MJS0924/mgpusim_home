#!/usr/bin/env python3
"""PHASE 2: Primary Performance — execution time and speedup.

Definition 1 (primary): Driver|kernel_time (wall-clock, most conservative)
Definition 2 (cross-check): max over compute GPUs (2-5) of CommandProcessor|kernel_time
If |def1 - def2| > 1%, escalate to PHASE 6.

CD is the baseline for speedup.
Speedup = CD_time / scheme_time (>1 means faster).
"""

import csv
import math
from pathlib import Path
from collections import defaultdict

MGPUSIM_HOME = Path("/root/mgpusim_home")
ANALYSIS = MGPUSIM_HOME / "analysis"
PARSED_DIR = ANALYSIS / "parsed"
TABLES = ANALYSIS / "tables"
FAIL_LOG = ANALYSIS / "FAIL_LOG.md"
TABLES.mkdir(parents=True, exist_ok=True)

SCHEMES = ["CD", "REC", "HMG", "superdirectory"]
WORKLOADS = ["bfs", "im2col", "matrixmultiplication", "pagerank"]
COMPUTE_GPUS = [2, 3, 4, 5]

# ---------------------------------------------------------------------------
# Load parsed data
# ---------------------------------------------------------------------------
print("=== PHASE 2: Primary Performance ===\n")
print("Loading parsed/long.csv ...")

# Index: (scheme, workload) -> list of rows
data = defaultdict(list)
with open(PARSED_DIR / "long.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        key = (row["scheme"], row["workload"])
        data[key].append(row)

# ---------------------------------------------------------------------------
# Extract kernel times
# ---------------------------------------------------------------------------
def get_float(row):
    try:
        return float(row["value"])
    except (ValueError, TypeError):
        return None

def kernel_times(scheme, workload):
    """Return (driver_time, cp_max_time) both in seconds."""
    rows = data[(scheme, workload)]
    if not rows:
        return None, None

    driver_time = None
    cp_times = []

    for r in rows:
        if r["metric_base"] != "kernel_time":
            continue
        v = get_float(r)
        if v is None:
            continue
        if r["comp_type"] == "Driver":
            driver_time = v
        elif r["comp_type"] == "CommandProcessor" and r["gpu_id"] and int(r["gpu_id"]) in COMPUTE_GPUS:
            cp_times.append(v)

    cp_max = max(cp_times) if cp_times else None
    return driver_time, cp_max

# Build time tables
exec_rows = []
escalations = []

for scheme in SCHEMES:
    for wl in WORKLOADS:
        drv, cp = kernel_times(scheme, wl)
        row = {
            "scheme": scheme, "workload": wl,
            "driver_kernel_time_s": drv,
            "cp_max_kernel_time_s": cp,
        }
        exec_rows.append(row)

        if drv is None:
            print(f"  [MISSING] {scheme}/{wl} — no kernel_time found")
            continue

        print(f"  {scheme:20s} {wl:25s}  driver={drv:.6f}s  cp_max={cp:.6f}s" if cp else
              f"  {scheme:20s} {wl:25s}  driver={drv:.6f}s  cp_max=MISSING")

        # Check def1 vs def2 divergence
        if cp and cp > 0:
            diff_pct = abs(drv - cp) / cp * 100
            if diff_pct > 1.0:
                msg = (f"PHASE2-ESCALATION: {scheme}/{wl} — driver_time={drv:.6f}s vs "
                       f"cp_max={cp:.6f}s, diff={diff_pct:.2f}% > 1% threshold")
                escalations.append(("PHASE2", scheme, wl, msg))
                print(f"    ⚠ ESCALATED to PHASE 6: {diff_pct:.2f}% divergence")

# Write exec time table
fieldnames = ["scheme", "workload", "driver_kernel_time_s", "cp_max_kernel_time_s"]
with open(TABLES / "02_exec_time.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(exec_rows)

# ---------------------------------------------------------------------------
# Speedup: CD as baseline
# ---------------------------------------------------------------------------
print("\n--- Speedup (CD=1.0) ---")

time_map = {}
for r in exec_rows:
    v = r["driver_kernel_time_s"]
    if v not in (None, ""):
        time_map[(r["scheme"], r["workload"])] = float(v) if isinstance(v, str) else v

speedup_rows = []
regression_rows = []

for wl in WORKLOADS:
    cd_time = time_map.get(("CD", wl))
    for scheme in SCHEMES:
        t = time_map.get((scheme, wl))
        if cd_time is None or cd_time == 0:
            speedup = "MISSING_BASELINE"
        elif t is None:
            speedup = "MISSING"
        else:
            speedup = cd_time / t

        speedup_rows.append({"scheme": scheme, "workload": wl, "speedup_vs_cd": speedup})

        if isinstance(speedup, float):
            flag = ""
            if speedup < 1.0:
                flag = " ← REGRESSION"
                regression_rows.append({
                    "scheme": scheme, "workload": wl,
                    "speedup_vs_cd": speedup,
                    "cd_time_s": cd_time,
                    "scheme_time_s": t,
                    "slowdown_pct": (1/speedup - 1)*100
                })
            print(f"  {scheme:20s} {wl:25s}  speedup={speedup:.4f}x{flag}")
        else:
            print(f"  {scheme:20s} {wl:25s}  speedup={speedup}")

# Geomean for superdirectory vs CD (only workloads where both have data)
sd_speedups = []
available_wls = []
for r in speedup_rows:
    if r["scheme"] == "superdirectory" and isinstance(r["speedup_vs_cd"], float):
        sd_speedups.append(r["speedup_vs_cd"])
        available_wls.append(r["workload"])

if sd_speedups:
    geomean = math.exp(sum(math.log(s) for s in sd_speedups) / len(sd_speedups))
    min_s = min(sd_speedups)
    max_s = max(sd_speedups)
    min_wl = available_wls[sd_speedups.index(min_s)]
    max_wl = available_wls[sd_speedups.index(max_s)]
    print(f"\n  SuperDir vs CD geomean speedup ({len(sd_speedups)} workloads: {available_wls}):")
    print(f"    geomean={geomean:.4f}x  min={min_s:.4f}x ({min_wl})  max={max_s:.4f}x ({max_wl})")
    # Append geomean row
    speedup_rows.append({
        "scheme": "superdirectory",
        "workload": f"GEOMEAN ({len(sd_speedups)} WLs)",
        "speedup_vs_cd": geomean
    })

# Also compute geomeans for REC and HMG vs CD
for cmp_scheme in ["REC", "HMG"]:
    cmp_speedups = []
    cmp_wls = []
    for r in speedup_rows:
        if r["scheme"] == cmp_scheme and isinstance(r["speedup_vs_cd"], float):
            cmp_speedups.append(r["speedup_vs_cd"])
            cmp_wls.append(r["workload"])
    if cmp_speedups:
        gm = math.exp(sum(math.log(s) for s in cmp_speedups) / len(cmp_speedups))
        print(f"  {cmp_scheme} vs CD geomean speedup ({len(cmp_speedups)} workloads: {cmp_wls}): {gm:.4f}x")
        speedup_rows.append({
            "scheme": cmp_scheme,
            "workload": f"GEOMEAN ({len(cmp_speedups)} WLs)",
            "speedup_vs_cd": gm
        })

# Write speedup table
with open(TABLES / "02_speedup.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["scheme","workload","speedup_vs_cd"])
    w.writeheader()
    w.writerows(speedup_rows)

# Write regression table
if regression_rows:
    with open(TABLES / "02_regressions.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["scheme","workload","speedup_vs_cd",
                                           "cd_time_s","scheme_time_s","slowdown_pct"])
        w.writeheader()
        w.writerows(regression_rows)
    print(f"\n  Regressions: {len(regression_rows)} cases → {TABLES}/02_regressions.csv")
else:
    print("\n  Regressions: NONE")

# Update FAIL_LOG with escalations
if escalations:
    with open(FAIL_LOG, "a") as f:
        f.write("\n## PHASE 2 Escalations\n\n")
        for (ph, sc, wl, msg) in escalations:
            f.write(f"| {ph} | {sc} | {wl} | {msg} |\n")

# ---------------------------------------------------------------------------
# PHASE 2 Checklist
# ---------------------------------------------------------------------------
print("\n=== PHASE 2 CHECKLIST ===")

missing_cd_baseline = [wl for wl in WORKLOADS if time_map.get(("CD", wl)) is None or time_map.get(("CD", wl)) == 0]
print(f"[{'PASS' if not missing_cd_baseline else 'FAIL'}] CD baseline available for all workloads "
      f"(MISSING/zero: {missing_cd_baseline})")

unit_ok = all(r["unit"] == "second" for r in data[("CD","matrixmultiplication")]
              if r["metric_base"] == "kernel_time" and r["comp_type"] == "Driver")
print(f"[{'PASS' if unit_ok else 'FAIL'}] Driver|kernel_time unit is 'second'")

missing_speedup = [(r["scheme"],r["workload"]) for r in speedup_rows
                   if isinstance(r["speedup_vs_cd"], str) and r["speedup_vs_cd"]=="MISSING"
                   and "GEOMEAN" not in str(r["workload"])]
print(f"[INFO] Missing speedup pairs: {missing_speedup}")

reg_summary = [(r["scheme"], r["workload"], f"{r['speedup_vs_cd']:.4f}x") for r in regression_rows]
print(f"[{'PASS' if not regression_rows else 'WARN'}] Regressions (SuperDir < CD): {reg_summary}")
print(f"[INFO] Escalations (driver vs cp_max >1%): {len(escalations)}")

if sd_speedups:
    print(f"[INFO] SuperDir result: {len(sd_speedups)} workloads with data, "
          f"geomean {geomean:.4f}x vs CD, "
          f"range [{min_s:.4f}x, {max_s:.4f}x], "
          f"{'ALL faster' if min_s>=1.0 else f'{sum(1 for s in sd_speedups if s>=1.0)}/{len(sd_speedups)} faster'}")

print("\nPHASE 2 COMPLETE")
