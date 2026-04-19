#!/usr/bin/env python3
"""PHASE 1: Parser — converts all data/ files into a canonical long-form DataFrame.

Output schema:
  scheme, workload, gpu_id, comp_type, comp_id, sub_id,
  metric_base, metric_index, msg_size, value, value_raw, value_is_finite, unit,
  src_file, src_line
"""

import re
import csv
import math
import gzip
from pathlib import Path

MGPUSIM_HOME = Path("/root/mgpusim_home")
RESULTS = MGPUSIM_HOME / "results"
ANALYSIS = MGPUSIM_HOME / "analysis"
PARSED_DIR = ANALYSIS / "parsed"
TABLES = ANALYSIS / "tables"
PARSED_DIR.mkdir(parents=True, exist_ok=True)
FAIL_LOG = ANALYSIS / "FAIL_LOG.md"

SCHEMES = {
    "CD":             RESULTS / "CD"             / "data",
    "REC":            RESULTS / "REC"            / "data",
    "HMG":            RESULTS / "HMG"            / "data",
    "superdirectory": RESULTS / "superdirectory" / "data",
}

WORKLOADS = ["bfs", "im2col", "matrixmultiplication", "pagerank"]

def data_filename(scheme, workload):
    if scheme == "CD":             return f"{workload}_CD_0.txt"
    if scheme == "REC":            return f"{workload}_REC.txt"
    if scheme == "HMG":            return f"{workload}_HMG.txt"
    if scheme == "superdirectory": return f"{workload}_superdirectory.txt"
    return None

# ---------------------------------------------------------------------------
# Component parser
# Pattern: GPU[g].CompType[id]  or  GPU[g].SA[s].CompType[id]  or  Driver
# ---------------------------------------------------------------------------
RE_GPU_COMP = re.compile(
    r"^GPU\[(\d+)\]"           # gpu_id
    r"\."
    r"(?:SA\[(\d+)\]\.)?"      # optional SA[sub] prefix
    r"(\w+)"                   # comp_type
    r"(?:\[(\d+)\])?"          # optional [comp_id]
    r"$"
)

# Comp type normalisation: CohDir -> CohDir (CD/REC/HMG directory)
COMP_TYPE_MAP = {
    "CohDir":          "CohDir",
    "SuperDir":        "SuperDir",
    "CommandProcessor":"CommandProcessor",
    "DRAM":            "DRAM",
    "L2Cache":         "L2Cache",
    "L2TLB":           "L2TLB",
    "L2ToDRAM":        "L2ToDRAM",
    "RDMA":            "RDMA",
    "CU":              "CU",
    "L1SCache":        "L1SCache",
    "L1ICache":        "L1ICache",
    "L1VCache":        "L1VCache",   # if present
    "L1STLB":          "L1STLB",
    "L1ITLB":          "L1ITLB",
    "L1VTLB":          "L1VTLB",
    "SA":              "SA",
}

def parse_component(loc_str):
    """Return (gpu_id, sa_id, comp_type, comp_id) or None."""
    if loc_str == "Driver":
        return ("host", None, "Driver", None)
    m = RE_GPU_COMP.match(loc_str)
    if m:
        gpu_id, sa_id, comp_raw, comp_sub = m.groups()
        comp_type = COMP_TYPE_MAP.get(comp_raw, comp_raw)
        return (int(gpu_id), int(sa_id) if sa_id is not None else None,
                comp_type, int(comp_sub) if comp_sub is not None else None)
    return None

# ---------------------------------------------------------------------------
# Metric parser
# Handles:
#   "BankChecked - 3"           → base="BankChecked", index=3
#   "UpdateEntry - 0"           → base="UpdateEntry", index=0
#   "Read Req 12"               → base="Read Req", msg_size=12
#   "read-hit"                  → base="read-hit", index=None
#   "RW: false/true"            → base="RW: false/true"
#   "Usage: 1/1"                → base="Usage: 1/1"
# ---------------------------------------------------------------------------
RE_METRIC_IDX = re.compile(r"^(.+?)\s*-\s*(\d+)$")
RE_RDMA_METRIC = re.compile(r"^(Read Req|Read Rsp|Write Req|Write Rsp|Inv Req|Inv Rsp|incoming_trans_count|outgoing_trans_count)\s*(\d+)?$")

def parse_metric(what_str):
    """Return (metric_base, metric_index, msg_size)."""
    m_idx = RE_METRIC_IDX.match(what_str)
    if m_idx:
        base, idx = m_idx.groups()
        return base.strip(), int(idx), None

    m_rdma = RE_RDMA_METRIC.match(what_str)
    if m_rdma:
        base, size = m_rdma.groups()
        return base, None, (int(size) if size else None)

    return what_str, None, None

# ---------------------------------------------------------------------------
# Value parser
# ---------------------------------------------------------------------------
def parse_value(val_str):
    """Return (numeric_value_or_None, value_raw_str, is_finite)."""
    s = val_str.strip()
    if s in ("Inf", "+Inf", "-Inf", "inf", "+inf", "-inf"):
        return None, s, False
    if s in ("NaN", "nan"):
        return None, s, False
    try:
        v = float(s)
        if math.isfinite(v):
            return v, s, True
        else:
            return None, s, False
    except ValueError:
        return None, s, False

# ---------------------------------------------------------------------------
# Main parse loop
# ---------------------------------------------------------------------------
rows = []
parse_errors = []
unknown_comps = set()

SCHEMA = [
    "scheme", "workload", "gpu_id", "sa_id", "comp_type", "comp_id",
    "metric_base", "metric_index", "msg_size",
    "value", "value_raw", "value_is_finite", "unit",
    "src_file", "src_line"
]

print("=== PHASE 1: Parser ===\n")

for scheme, data_dir in SCHEMES.items():
    for wl in WORKLOADS:
        fname = data_filename(scheme, wl)
        fpath = data_dir / fname
        if not fpath.exists():
            print(f"  [SKIP] {scheme}/{wl} — MISSING")
            continue

        text = fpath.read_text(errors="replace")
        lines = text.splitlines()
        file_rows = 0

        for lineno, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            # maxsplit=3 to avoid splitting on | inside metric names (none expected, but defensive)
            parts = line.split("|", 3)
            if len(parts) != 4:
                parse_errors.append({
                    "src_file": str(fpath), "src_line": lineno,
                    "raw": raw_line[:200],
                    "issue": f"expected 4 fields, got {len(parts)}"
                })
                continue

            loc_str, what_str, val_str, unit_str = (p.strip() for p in parts)

            comp = parse_component(loc_str)
            if comp is None:
                unknown_comps.add(loc_str)
                parse_errors.append({
                    "src_file": str(fpath), "src_line": lineno,
                    "raw": raw_line[:200],
                    "issue": f"unrecognised component: {loc_str!r}"
                })
                continue

            gpu_id, sa_id, comp_type, comp_id = comp
            metric_base, metric_index, msg_size = parse_metric(what_str)
            value, value_raw, is_finite = parse_value(val_str)

            rows.append({
                "scheme": scheme,
                "workload": wl,
                "gpu_id": gpu_id,
                "sa_id": sa_id,
                "comp_type": comp_type,
                "comp_id": comp_id,
                "metric_base": metric_base,
                "metric_index": metric_index,
                "msg_size": msg_size,
                "value": value,
                "value_raw": value_raw,
                "value_is_finite": is_finite,
                "unit": unit_str,
                "src_file": str(fpath),
                "src_line": lineno,
            })
            file_rows += 1

        print(f"  [OK] {scheme:20s} {wl:25s} → {file_rows:7d} rows")

print(f"\n  Total rows: {len(rows)}")
print(f"  Parse errors: {len(parse_errors)}")
if unknown_comps:
    print(f"  Unknown components: {unknown_comps}")

# ---------------------------------------------------------------------------
# Write outputs
# ---------------------------------------------------------------------------

# parsed/long.csv.gz
csv_gz_path = PARSED_DIR / "long.csv.gz"
with gzip.open(csv_gz_path, "wt", newline="") as f:
    w = csv.DictWriter(f, fieldnames=SCHEMA)
    w.writeheader()
    w.writerows(rows)
print(f"\n  Written: {csv_gz_path} ({len(rows)} rows)")

# parsed/long.csv (uncompressed for quick inspection)
csv_path = PARSED_DIR / "long.csv"
with open(csv_path, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=SCHEMA)
    w.writeheader()
    w.writerows(rows)
print(f"  Written: {csv_path}")

# Try parquet (optional, requires pyarrow/pandas)
try:
    import pandas as pd
    df = pd.DataFrame(rows)
    pq_path = PARSED_DIR / "long.parquet"
    df.to_parquet(pq_path, index=False)
    print(f"  Written: {pq_path}")
except ImportError:
    print("  [WARN] pandas/pyarrow not available — skipping parquet output")

# parse errors CSV
if parse_errors:
    err_path = TABLES / "01_parse_errors.csv"
    with open(err_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["src_file","src_line","raw","issue"])
        w.writeheader()
        w.writerows(parse_errors)
    print(f"  Parse errors written to: {err_path}")

    # Append to FAIL_LOG
    with open(FAIL_LOG, "a") as f:
        f.write(f"\n## PHASE 1 Parse Errors ({len(parse_errors)} total)\n\n")
        for e in parse_errors[:50]:
            f.write(f"- `{e['src_file']}` line {e['src_line']}: {e['issue']} — `{e['raw'][:100]}`\n")
        if len(parse_errors) > 50:
            f.write(f"- ... and {len(parse_errors)-50} more (see {err_path})\n")
else:
    print("  [PASS] Zero parse errors")

# ---------------------------------------------------------------------------
# PHASE 1 Checklist
# ---------------------------------------------------------------------------
print("\n=== PHASE 1 CHECKLIST ===")

# Check 1: parse errors
print(f"[{'PASS' if not parse_errors else 'FAIL'}] Parse errors: {len(parse_errors)}")

# Check 2: Inf/NaN not replaced
non_finite = [r for r in rows if not r["value_is_finite"]]
print(f"[{'PASS'}] Non-finite values preserved as-is: {len(non_finite)} entries (not replaced with 0/mean)")
for nf in non_finite[:5]:
    print(f"         {nf['scheme']}/{nf['workload']} {nf['comp_type']} {nf['metric_base']} = {nf['value_raw']!r}")

# Check 3: unknown comp types
if unknown_comps:
    print(f"[FAIL] Unknown comp types (not classified): {unknown_comps}")
else:
    print(f"[PASS] All component types classified")

# Check 4: comp type coverage
comp_types_found = set(r["comp_type"] for r in rows)
print(f"[INFO] Component types in data: {sorted(comp_types_found)}")

# Check R1-1: GPU[1].CommandProcessor kernel_time = 0 for all?
kt_rows = [r for r in rows if r["metric_base"]=="kernel_time" and r["comp_type"]=="CommandProcessor" and r["gpu_id"]==1]
if kt_rows:
    all_zero = all(r["value"]==0.0 for r in kt_rows)
    print(f"[INFO R1-1] GPU[1].CommandProcessor.kernel_time always=0: {all_zero} "
          f"(GPU[1] is host/control GPU; GPU[2-5] are compute GPUs)")
else:
    print(f"[INFO R1-1] No GPU[1].CommandProcessor.kernel_time rows found")

print("\nPHASE 1 COMPLETE")
