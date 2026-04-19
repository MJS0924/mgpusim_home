#!/usr/bin/env python3
"""PHASE 4: NVLink/RDMA Traffic analysis.

Metrics per GPU: Read Req, Read Rsp, Write Req, Write Rsp, Inv Req, Inv Rsp
Each has a payload size in bytes embedded in the metric name (e.g. "Read Req 12" → 12 bytes).

Total bytes = count × payload_bytes per message type.
Invalidation overhead ratio = Inv Req bytes / total bytes.
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
ALL_GPUS = {1, 2, 3, 4, 5}

# Known RDMA payload sizes from the data
# These will be verified against what we find in the data
EXPECTED_PAYLOADS = {
    "Read Req": 12,    # request header only, no data
    "Read Rsp": 68,    # 64B data + 4B header
    "Write Req": 76,   # 64B data + 12B header (includes address)
    "Write Rsp": 4,    # ACK only
    "Inv Req": 12,     # invalidation request header
    "Inv Rsp": 4,      # invalidation ACK
}

print("=== PHASE 4: NVLink/RDMA Traffic ===\n")
print("Loading parsed/long.csv ...")

data = defaultdict(list)
with open(PARSED_DIR / "long.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        data[(row["scheme"], row["workload"])].append(row)

def fval(r):
    try: return float(r["value"])
    except: return None

AVAILABLE_PAIRS = [
    ("CD", "im2col"), ("CD", "matrixmultiplication"),
    ("REC", "im2col"), ("REC", "matrixmultiplication"), ("REC", "pagerank"),
    ("HMG", "im2col"), ("HMG", "matrixmultiplication"), ("HMG", "pagerank"),
    ("superdirectory", "bfs"), ("superdirectory", "im2col"),
    ("superdirectory", "matrixmultiplication"), ("superdirectory", "pagerank"),
]

RDMA_MSG_TYPES = ["Read Req", "Read Rsp", "Write Req", "Write Rsp", "Inv Req", "Inv Rsp"]

# Verify payload sizes found in data
found_payloads = {}  # (msg_type, size) -> count
for scheme, wl in AVAILABLE_PAIRS:
    for r in data[(scheme, wl)]:
        if r["comp_type"] == "RDMA" and r["msg_size"]:
            key = (r["metric_base"], int(r["msg_size"]))
            found_payloads[key] = found_payloads.get(key, 0) + 1

print("Verifying payload sizes (from data vs expected):")
payload_mismatches = []
for msg_type, expected_size in EXPECTED_PAYLOADS.items():
    found = [(k,v) for k,v in found_payloads.items() if k[0]==msg_type]
    if not found:
        print(f"  {msg_type:12s}: no data found")
        continue
    for (mt, actual_size), cnt in found:
        match = "✓" if actual_size == expected_size else "✗"
        print(f"  {msg_type:12s}: expected={expected_size}B  actual={actual_size}B  {match}  (found in {cnt} records)")
        if actual_size != expected_size:
            payload_mismatches.append((msg_type, expected_size, actual_size))

if payload_mismatches:
    print(f"\n  WARNING: Payload mismatches: {payload_mismatches}")

# ---------------------------------------------------------------------------
# Compute RDMA traffic per (scheme, workload, gpu)
# ---------------------------------------------------------------------------
network_rows = []
inv_ratio_rows = []
per_gpu_traffic = []

for scheme, wl in AVAILABLE_PAIRS:
    rows = data[(scheme, wl)]

    # Collect RDMA counts per (gpu, msg_type)
    rdma = defaultdict(lambda: defaultdict(float))  # [gpu_id][msg_type] = count
    trans_in = defaultdict(float)   # [gpu_id] incoming_trans_count
    trans_out = defaultdict(float)  # [gpu_id] outgoing_trans_count

    for r in rows:
        if r["comp_type"] != "RDMA":
            continue
        gpu_id = int(r["gpu_id"]) if r["gpu_id"] not in (None, "host", "") else None
        if gpu_id is None:
            continue
        v = fval(r)
        if v is None:
            continue
        mb = r["metric_base"]
        if mb in RDMA_MSG_TYPES:
            rdma[gpu_id][mb] += v
        elif mb == "incoming_trans_count":
            trans_in[gpu_id] += v
        elif mb == "outgoing_trans_count":
            trans_out[gpu_id] += v

    # Compute bytes per message type, per GPU
    for gpu_id in sorted(ALL_GPUS):
        row_bytes = {}
        for mt in RDMA_MSG_TYPES:
            count = rdma[gpu_id].get(mt, 0)
            size = EXPECTED_PAYLOADS.get(mt, 0)
            row_bytes[mt] = count * size

        total_bytes = sum(row_bytes.values())
        inv_bytes = row_bytes.get("Inv Req", 0)
        inv_ratio = inv_bytes / total_bytes if total_bytes > 0 else None

        per_gpu_traffic.append({
            "scheme": scheme, "workload": wl, "gpu_id": gpu_id,
            "read_req_bytes": row_bytes["Read Req"],
            "read_rsp_bytes": row_bytes["Read Rsp"],
            "write_req_bytes": row_bytes["Write Req"],
            "write_rsp_bytes": row_bytes["Write Rsp"],
            "inv_req_bytes": row_bytes["Inv Req"],
            "inv_rsp_bytes": row_bytes["Inv Rsp"],
            "total_bytes": total_bytes,
            "inv_ratio": inv_ratio,
            "incoming_trans": trans_in.get(gpu_id, 0),
            "outgoing_trans": trans_out.get(gpu_id, 0),
        })

    # Sum across compute GPUs 2-5 for aggregate
    total = defaultdict(float)
    for gpu_id in COMPUTE_GPUS:
        for mt in RDMA_MSG_TYPES:
            count = rdma[gpu_id].get(mt, 0)
            size = EXPECTED_PAYLOADS.get(mt, 0)
            total[mt] += count * size
        total["incoming_trans"] += trans_in.get(gpu_id, 0)
        total["outgoing_trans"] += trans_out.get(gpu_id, 0)

    total_bytes = sum(total[mt] for mt in RDMA_MSG_TYPES)
    inv_bytes = total["Inv Req"]
    inv_ratio = inv_bytes / total_bytes if total_bytes > 0 else 0.0

    network_rows.append({
        "scheme": scheme, "workload": wl,
        "total_bytes": total_bytes,
        "read_req_bytes": total["Read Req"],
        "read_rsp_bytes": total["Read Rsp"],
        "write_req_bytes": total["Write Req"],
        "write_rsp_bytes": total["Write Rsp"],
        "inv_req_bytes": total["Inv Req"],
        "inv_rsp_bytes": total["Inv Rsp"],
        "inv_ratio": inv_ratio,
        "incoming_trans": total["incoming_trans"],
        "outgoing_trans": total["outgoing_trans"],
    })
    inv_ratio_rows.append({
        "scheme": scheme, "workload": wl,
        "total_bytes": total_bytes,
        "inv_req_bytes": inv_bytes,
        "inv_ratio": inv_ratio,
    })

# Write tables
net_fields = ["scheme","workload","total_bytes","read_req_bytes","read_rsp_bytes",
              "write_req_bytes","write_rsp_bytes","inv_req_bytes","inv_rsp_bytes",
              "inv_ratio","incoming_trans","outgoing_trans"]
with open(TABLES / "04_network_bytes.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=net_fields)
    w.writeheader()
    w.writerows(network_rows)

inv_fields = ["scheme","workload","total_bytes","inv_req_bytes","inv_ratio"]
with open(TABLES / "04_inv_ratio.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=inv_fields)
    w.writeheader()
    w.writerows(inv_ratio_rows)

pg_fields = ["scheme","workload","gpu_id","read_req_bytes","read_rsp_bytes",
             "write_req_bytes","write_rsp_bytes","inv_req_bytes","inv_rsp_bytes",
             "total_bytes","inv_ratio","incoming_trans","outgoing_trans"]
with open(TABLES / "04_per_gpu_traffic.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=pg_fields)
    w.writeheader()
    w.writerows(per_gpu_traffic)

# ---------------------------------------------------------------------------
# Print comparison for shared workloads
# ---------------------------------------------------------------------------
print("\n--- Total RDMA Bytes (compute GPUs 2-5) ---")
print(f"  {'workload':25s} {'scheme':20s} {'total_MB':>10s} {'inv_ratio':>10s} {'read_rsp_MB':>11s} {'write_req_MB':>12s} {'inv_req_MB':>10s}")
for wl in ["im2col", "matrixmultiplication"]:
    for scheme in SCHEMES:
        r = next((x for x in network_rows if x["scheme"]==scheme and x["workload"]==wl), None)
        if r is None:
            continue
        total_mb = r["total_bytes"] / 1e6
        inv_ratio = r["inv_ratio"]
        inv_mb = r["inv_req_bytes"] / 1e6
        rsp_mb = r["read_rsp_bytes"] / 1e6
        wreq_mb = r["write_req_bytes"] / 1e6
        print(f"  {wl:25s} {scheme:20s} {total_mb:>10.2f} {inv_ratio:>10.4f} {rsp_mb:>11.2f} {wreq_mb:>12.2f} {inv_mb:>10.4f}")
    print()

# Per-GPU imbalance for matrixmultiplication
print("\n--- Per-GPU Traffic Imbalance (matrixmultiplication) ---")
for scheme in SCHEMES:
    rows = [r for r in per_gpu_traffic
            if r["scheme"]==scheme and r["workload"]=="matrixmultiplication"
            and r["gpu_id"] in COMPUTE_GPUS]
    if not rows:
        continue
    totals = [r["total_bytes"] for r in rows]
    if max(totals) > 0:
        imbalance = max(totals)/max(sum(totals)/len(totals), 1)
        print(f"  {scheme:20s} per-GPU bytes: {[f'{t/1e6:.2f}MB' for t in totals]}  max/avg={imbalance:.2f}x")

# ---------------------------------------------------------------------------
# PHASE 4 Checklist
# ---------------------------------------------------------------------------
print("\n=== PHASE 4 CHECKLIST ===")

print(f"[{'PASS' if not payload_mismatches else 'FAIL'}] Payload sizes verified against data "
      f"({len(payload_mismatches)} mismatches)")

# Sanity: incoming_trans vs outgoing_trans consistency check
print("\n--- RDMA incoming vs outgoing sanity (should be equal across peers) ---")
sanity_issues = []
for wl in ["matrixmultiplication"]:
    for scheme in SCHEMES:
        rows = [r for r in per_gpu_traffic
                if r["scheme"]==scheme and r["workload"]==wl and r["gpu_id"] in ALL_GPUS]
        total_in = sum(r["incoming_trans"] for r in rows)
        total_out = sum(r["outgoing_trans"] for r in rows)
        diff_pct = abs(total_in - total_out) / max(total_out, 1) * 100
        status = "PASS" if diff_pct < 1 else "WARN" if diff_pct < 10 else "FAIL"
        print(f"  {scheme:20s} {wl:25s} total_in={total_in:.0f} total_out={total_out:.0f} diff={diff_pct:.1f}% [{status}]")
        if status == "FAIL":
            sanity_issues.append((scheme, wl, diff_pct))

if sanity_issues:
    with open(FAIL_LOG, "a") as f:
        f.write("\n## PHASE 4 Sanity Issues\n\n")
        for s, w, d in sanity_issues:
            f.write(f"| PHASE4 | {s} | {w} | RDMA in/out mismatch: {d:.1f}% |\n")

print(f"\n[{'PASS' if not sanity_issues else 'FAIL'}] RDMA in/out sanity: "
      f"{len(sanity_issues)} failures")

# Note: Inv Req 12 bytes — this is a count*12 bytes metric
print("[INFO] Inv Req payload = 12B (header only; no cache-line data)")
print("[INFO] For SuperDir: region-level Inv may cover multiple cachelines per Inv Req (same 12B message cost)")

print("\nPHASE 4 COMPLETE")
