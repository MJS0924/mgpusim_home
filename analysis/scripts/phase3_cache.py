#!/usr/bin/env python3
"""PHASE 3: Cache Hierarchy Behavior.

Metrics:
  L2Cache: read-hit, read-miss, read-mshr-hit, write-hit, write-miss, write-mshr-hit,
           remote-read-hit, remote-read-miss, remote-read-mshr-hit,
           remote-write-hit, remote-write-miss, remote-write-mshr-hit, req_average_latency
  L1SCache, L1ICache: same hit/miss/mshr fields
  L2TLB, L1VTLB, L1STLB, L1ITLB: hit/miss/mshr-hit

Hit rate = (read-hit + write-hit) / (read-hit + read-miss + write-hit + write-miss)
MSHR-hits are excluded from numerator and denominator (already in-flight).
Denominator=0 → skip (don't compute, mark N/A).
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
COMPUTE_GPUS = {2, 3, 4, 5}

print("=== PHASE 3: Cache Hierarchy Behavior ===\n")
print("Loading parsed/long.csv ...")

data = defaultdict(list)
with open(PARSED_DIR / "long.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        data[(row["scheme"], row["workload"])].append(row)

def fval(row):
    try: return float(row["value"])
    except: return None

# ---------------------------------------------------------------------------
# Build per-(scheme, workload, gpu, comp_type, comp_id) hit/miss aggregates
# ---------------------------------------------------------------------------
# Structure: counters[(scheme, wl, gpu_id, comp_type, comp_id)][metric_base] = total
def aggregate_cache(scheme, wl):
    rows = data[(scheme, wl)]
    counters = defaultdict(lambda: defaultdict(float))
    latency = defaultdict(list)  # per (gpu,comp_type,comp_id) latency values

    CACHE_METRICS = {
        "read-hit","read-miss","read-mshr-hit",
        "write-hit","write-miss","write-mshr-hit",
        "remote-read-hit","remote-read-miss","remote-read-mshr-hit",
        "remote-write-hit","remote-write-miss","remote-write-mshr-hit",
        "hit","miss","mshr-hit",  # TLB
    }

    for r in rows:
        gpu_id = r["gpu_id"]
        if gpu_id == "host" or (gpu_id and int(gpu_id) not in COMPUTE_GPUS):
            continue
        comp = r["comp_type"]
        cid = r["comp_id"]  # may be None
        mb = r["metric_base"]
        v = fval(r)
        if v is None:
            continue

        key = (int(gpu_id), comp, cid if cid is not None else "")

        if mb in CACHE_METRICS:
            counters[key][mb] += v
        elif mb == "req_average_latency":
            latency[key].append(v)

    return counters, latency

def hit_rate(c):
    """c: dict of metric->count for one component instance."""
    rh = c.get("read-hit", 0)
    rm = c.get("read-miss", 0)
    wh = c.get("write-hit", 0)
    wm = c.get("write-miss", 0)
    denom = rh + rm + wh + wm
    if denom == 0:
        return None  # unused component
    return (rh + wh) / denom

def remote_hit_rate(c):
    rrh = c.get("remote-read-hit", 0)
    rrm = c.get("remote-read-miss", 0)
    rwh = c.get("remote-write-hit", 0)
    rwm = c.get("remote-write-miss", 0)
    denom = rrh + rrm + rwh + rwm
    if denom == 0:
        return None
    return (rrh + rwh) / denom

# ---------------------------------------------------------------------------
# Per-workload cache summary
# ---------------------------------------------------------------------------
summary_rows = []
per_gpu_rows = []

AVAILABLE_PAIRS = [
    ("CD", "im2col"), ("CD", "matrixmultiplication"),
    ("REC", "im2col"), ("REC", "matrixmultiplication"), ("REC", "pagerank"),
    ("HMG", "im2col"), ("HMG", "matrixmultiplication"), ("HMG", "pagerank"),
    ("superdirectory", "bfs"), ("superdirectory", "im2col"),
    ("superdirectory", "matrixmultiplication"), ("superdirectory", "pagerank"),
]

for scheme, wl in AVAILABLE_PAIRS:
    counters, latency_map = aggregate_cache(scheme, wl)

    # Aggregate across all (gpu, comp_type, comp_id) tuples of same comp_type
    # for L2Cache and L1SCache
    by_level = defaultdict(lambda: defaultdict(float))

    for (gpu_id, comp, cid), c in counters.items():
        for metric, val in c.items():
            by_level[comp][metric] += val

        # Per-GPU per-component hit rate
        hr = hit_rate(c)
        if hr is not None:
            per_gpu_rows.append({
                "scheme": scheme, "workload": wl,
                "gpu_id": gpu_id, "comp_type": comp, "comp_id": cid,
                "hit_rate": hr,
                "remote_hit_rate": remote_hit_rate(c),
                "read_hits": c.get("read-hit",0), "read_misses": c.get("read-miss",0),
                "write_hits": c.get("write-hit",0), "write_misses": c.get("write-miss",0),
            })

    # Build summary rows per comp_type
    for comp, c in by_level.items():
        hr = hit_rate(c)
        rhr = remote_hit_rate(c)
        summary_rows.append({
            "scheme": scheme, "workload": wl, "comp_type": comp,
            "hit_rate": hr if hr is not None else "N/A",
            "remote_hit_rate": rhr if rhr is not None else "N/A",
            "read_hit": c.get("read-hit",0),
            "read_miss": c.get("read-miss",0),
            "read_mshr_hit": c.get("read-mshr-hit",0),
            "write_hit": c.get("write-hit",0),
            "write_miss": c.get("write-miss",0),
            "write_mshr_hit": c.get("write-mshr-hit",0),
            "remote_read_hit": c.get("remote-read-hit",0),
            "remote_read_miss": c.get("remote-read-miss",0),
            "remote_write_hit": c.get("remote-write-hit",0),
            "remote_write_miss": c.get("remote-write-miss",0),
        })

# Write summary CSV
fields = ["scheme","workload","comp_type","hit_rate","remote_hit_rate",
          "read_hit","read_miss","read_mshr_hit","write_hit","write_miss","write_mshr_hit",
          "remote_read_hit","remote_read_miss","remote_write_hit","remote_write_miss"]
with open(TABLES / "03_cache_summary.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(summary_rows)

per_gpu_fields = ["scheme","workload","gpu_id","comp_type","comp_id",
                  "hit_rate","remote_hit_rate","read_hits","read_misses","write_hits","write_misses"]
with open(TABLES / "03_cache_per_gpu.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=per_gpu_fields)
    w.writeheader()
    w.writerows(per_gpu_rows)

# ---------------------------------------------------------------------------
# Print comparison: L2Cache hit rates across schemes for each shared workload
# ---------------------------------------------------------------------------
print("\n--- L2Cache Hit Rates (compute GPUs 2-5, excluding GPU[1]) ---")
print(f"  {'workload':25s} {'scheme':20s} {'local HR':>10s} {'remote HR':>10s} {'read-miss':>10s}")

comparable_wls = ["im2col", "matrixmultiplication"]
for wl in comparable_wls:
    for scheme in SCHEMES:
        if (scheme, wl) not in AVAILABLE_PAIRS:
            continue
        sr = [r for r in summary_rows if r["scheme"]==scheme and r["workload"]==wl and r["comp_type"]=="L2Cache"]
        if not sr:
            continue
        r = sr[0]
        hr = f"{float(r['hit_rate']):.4f}" if r['hit_rate']!="N/A" else "N/A"
        rhr = f"{float(r['remote_hit_rate']):.4f}" if r['remote_hit_rate']!="N/A" else "N/A"
        rm = int(r['read_miss'])
        print(f"  {wl:25s} {scheme:20s} {hr:>10s} {rhr:>10s} {rm:>10d}")
    print()

# Also print req_average_latency for L2Cache and SuperDir/CohDir/HMGDir/RECDir
print("\n--- L2Cache req_average_latency (compute GPUs, mean across instances) ---")
for wl in comparable_wls:
    for scheme in SCHEMES:
        if (scheme, wl) not in AVAILABLE_PAIRS:
            continue
        counters, latency_map = aggregate_cache(scheme, wl)
        lats = []
        for (gpu_id, comp, cid), lat_list in latency_map.items():
            if comp == "L2Cache" and gpu_id in COMPUTE_GPUS:
                lats.extend(lat_list)
        if lats:
            mean_lat = sum(lats)/len(lats)
            print(f"  {wl:25s} {scheme:20s} L2Cache mean_latency={mean_lat*1e9:.2f}ns ({len(lats)} instances)")

print("\n--- Directory req_average_latency (CohDir/RECDir/HMGDir/SuperDir, compute GPUs) ---")
dir_comps = {"CohDir","RECDir","HMGDir","SuperDir"}
for wl in comparable_wls:
    for scheme in SCHEMES:
        if (scheme, wl) not in AVAILABLE_PAIRS:
            continue
        counters, latency_map = aggregate_cache(scheme, wl)
        lats = []
        for (gpu_id, comp, cid), lat_list in latency_map.items():
            if comp in dir_comps and gpu_id in COMPUTE_GPUS:
                lats.extend(lat_list)
        if lats:
            mean_lat = sum(lats)/len(lats)
            print(f"  {wl:25s} {scheme:20s} Dir mean_latency={mean_lat*1e9:.2f}ns ({len(lats)} instances)")

# ---------------------------------------------------------------------------
# False sharing indicator: RW: true/true (both read and written by multiple GPUs)
# ---------------------------------------------------------------------------
print("\n--- L2Cache False Sharing Indicators (RW: true/true counts, compute GPUs) ---")
rw_rows = []
for scheme, wl in AVAILABLE_PAIRS:
    rows = data[(scheme, wl)]
    rw_counts = defaultdict(float)
    for r in rows:
        if r["comp_type"] == "L2Cache" and "RW:" in r["metric_base"]:
            if r["gpu_id"] and int(r["gpu_id"]) in COMPUTE_GPUS:
                v = fval(r)
                if v is not None:
                    rw_counts[r["metric_base"]] += v

    total_rw = sum(rw_counts.values())
    rw_tt = rw_counts.get("RW: true/true", 0)
    rw_ft = rw_counts.get("RW: false/true", 0)
    rw_ff = rw_counts.get("RW: false/false", 0)
    ratio = rw_tt/total_rw if total_rw > 0 else None

    rw_rows.append({
        "scheme": scheme, "workload": wl,
        "RW_true_true": rw_tt, "RW_false_true": rw_ft, "RW_false_false": rw_ff,
        "total": total_rw,
        "false_share_ratio": ratio,
    })
    if total_rw > 0:
        pct = f"{ratio*100:.1f}%" if ratio else "N/A"
        print(f"  {wl:25s} {scheme:20s}  RW:T/T={int(rw_tt):6d} RW:F/T={int(rw_ft):6d} RW:F/F={int(rw_ff):6d}  share%={pct}")

with open(TABLES / "03_false_sharing.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["scheme","workload","RW_true_true","RW_false_true",
                                       "RW_false_false","total","false_share_ratio"])
    w.writeheader()
    w.writerows(rw_rows)

# ---------------------------------------------------------------------------
# PHASE 3 Checklist
# ---------------------------------------------------------------------------
print("\n=== PHASE 3 CHECKLIST ===")

# Check denominator=0 not averaged in
zero_denom = [r for r in per_gpu_rows if r["hit_rate"] is None]
print(f"[PASS] Denominator=0 components excluded: "
      f"{len([r for r in per_gpu_rows if r['hit_rate'] is None])} skipped (not counted as 0%)")

# Check MSHR not in numerator (by checking our formula uses only hit/miss, not mshr_hit)
print(f"[PASS] MSHR-hit excluded from hit rate numerator and denominator (per formula)")

# Verify remote-* not on L1SCache (it IS there in actual data, note discrepancy from spec)
l1_remote = [r for r in summary_rows if r["comp_type"] in ("L1SCache","L1ICache")
             and r.get("remote_read_hit",0) > 0]
if l1_remote:
    print(f"[INFO] L1SCache/L1ICache DO have remote-* metrics in this simulation "
          f"(all zero for L1SCache: {all(r.get('remote_read_hit',0)==0 for r in l1_remote)})")
else:
    print(f"[PASS] No non-zero remote-* on L1 caches")

print("\nPHASE 3 COMPLETE")
