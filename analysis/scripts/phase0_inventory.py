#!/usr/bin/env python3
"""PHASE 0: Inventory & Sanity — catalogs all (scheme, workload) pairs and extracts missing data."""

import os
import subprocess
import csv
import sqlite3 as sq
from pathlib import Path

MGPUSIM_HOME = Path("/root/mgpusim_home")
RESULTS = MGPUSIM_HOME / "results"
ANALYSIS = MGPUSIM_HOME / "analysis"
TABLES = ANALYSIS / "tables"
TABLES.mkdir(parents=True, exist_ok=True)
FAIL_LOG = ANALYSIS / "FAIL_LOG.md"

# Schemes: (name, data_dir, sql_dir, has_numbered_variants, use_variant)
SCHEMES = {
    "CD":             (RESULTS / "CD"            / "data", RESULTS / "CD"            / "rawdata/sql"),
    "REC":            (RESULTS / "REC"           / "data", RESULTS / "REC"           / "rawdata/sql"),
    "HMG":            (RESULTS / "HMG"           / "data", RESULTS / "HMG"           / "rawdata/sql"),
    "superdirectory": (RESULTS / "superdirectory"/ "data", RESULTS / "superdirectory"/ "rawdata/sql"),
}

# For CD, the canonical baseline variant is CD_0 (coherence-unit-size=0 = standard 64B cacheline directory)
# For LBC, not in scope for this analysis.

WORKLOADS = ["bfs", "im2col", "matrixmultiplication", "pagerank"]

# Expected data filename per (scheme, workload)
def expected_data_filename(scheme, workload):
    if scheme == "CD":
        return f"{workload}_CD_0.txt"           # CD_0 = unit-size=0 baseline
    elif scheme == "REC":
        return f"{workload}_REC.txt"
    elif scheme == "HMG":
        return f"{workload}_HMG.txt"
    elif scheme == "superdirectory":
        return f"{workload}_superdirectory.txt"
    return None

# Expected SQL filename for extraction (if data file missing)
def expected_sql_filename(scheme, workload):
    if scheme == "CD":
        return f"{workload}_CD_0.sqlite3"
    elif scheme == "REC":
        return f"{workload}_REC.sqlite3"
    elif scheme == "HMG":
        return f"{workload}_HMG.sqlite3"
    elif scheme == "superdirectory":
        return f"{workload}_superdirectory.sqlite3"
    return None


def extract_from_sqlite(sql_path, out_path):
    """Extract cohDir_metrics + mgpusim_metrics from SQLite into pipe-delimited text."""
    con = sq.connect(sql_path)
    cur = con.cursor()
    lines = []
    for table in ("cohDir_metrics", "mgpusim_metrics"):
        try:
            cur.execute(f"SELECT Location, What, Value, Unit FROM {table}")
            for row in cur.fetchall():
                lines.append("|".join(str(c) for c in row))
        except sq.OperationalError as e:
            lines.append(f"# ERROR reading {table}: {e}")
    con.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")
    return len(lines)


def check_data_file(path):
    """Returns (size_ok, has_kernel_time, format_violations, line_count)."""
    if not path.exists():
        return False, False, 0, 0
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    size_ok = len(lines) > 0
    has_kt = any("kernel_time" in l and l.startswith("Driver|") for l in lines)
    violations = 0
    for l in lines:
        if l.strip() == "" or l.startswith("#"):
            continue
        parts = l.split("|")
        if len(parts) != 4:
            violations += 1
    return size_ok, has_kt, violations, len(lines)


fail_entries = []
inventory = []

print("=== PHASE 0: Inventory & Sanity ===\n")

for scheme, (data_dir, sql_dir) in SCHEMES.items():
    for wl in WORKLOADS:
        fname = expected_data_filename(scheme, wl)
        data_path = data_dir / fname
        sql_fname = expected_sql_filename(scheme, wl)
        sql_path = sql_dir / sql_fname if sql_fname else None

        status = "OK"
        notes = []

        if not data_path.exists():
            # Try to extract from SQLite
            if sql_path and sql_path.exists():
                print(f"  Extracting {scheme}/{wl} from SQLite → {data_path}")
                n = extract_from_sqlite(sql_path, data_path)
                notes.append(f"extracted from SQLite ({n} lines)")
                status = "EXTRACTED"
            else:
                # Check if SQL file exists at all
                sql_exists = sql_path.exists() if sql_path else False
                if not sql_exists:
                    status = "MISSING"
                    msg = f"MISSING: {scheme}/{wl} — no data file and no SQL ({data_path})"
                    fail_entries.append(("PHASE0", scheme, wl, msg))
                    print(f"  [MISSING] {scheme}/{wl}")
                else:
                    status = "MISSING"
                    msg = f"MISSING: {scheme}/{wl} — data absent, SQL present at unexpected path"
                    fail_entries.append(("PHASE0", scheme, wl, msg))

        if data_path.exists():
            size_ok, has_kt, violations, n_lines = check_data_file(data_path)
            if not size_ok:
                status = "TRUNCATED"
                fail_entries.append(("PHASE0", scheme, wl, f"TRUNCATED: {data_path} is empty"))
            if not has_kt:
                msg = f"NO_KERNEL_TIME: {scheme}/{wl} — Driver|kernel_time not found in {data_path}"
                fail_entries.append(("PHASE0", scheme, wl, msg))
                if status == "OK":
                    status = "WARN_NO_KT"
            if violations > 0:
                msg = f"FORMAT_VIOLATIONS: {scheme}/{wl} — {violations} lines with ≠4 pipe fields in {data_path}"
                fail_entries.append(("PHASE0", scheme, wl, msg))
            notes.append(f"lines={n_lines}, has_kernel_time={has_kt}, violations={violations}")

        inventory.append({
            "scheme": scheme, "workload": wl, "status": status,
            "data_file": str(data_path) if data_path.exists() else "MISSING",
            "notes": "; ".join(notes) if notes else ""
        })
        symbol = "✓" if status in ("OK","EXTRACTED") else ("⚠" if "WARN" in status else "✗")
        print(f"  [{symbol}] {scheme:20s} {wl:25s} → {status}")

# Special: note that data files end with DRAM metrics, NOT kernel_time as last line
# This is by design (SQLite SELECT order: cohDir_metrics first, then mgpusim_metrics with kernel_time near top)
fail_entries.append(("PHASE0-DESIGN", "ALL", "ALL",
    "DESIGN NOTE: data/ files do NOT end with Driver|kernel_time. "
    "kernel_time appears near the TOP of mgpusim_metrics section (~line 29-165). "
    "Files end with L2ToDRAM metrics. "
    "This is consistent with SQLite SELECT ORDER: cohDir_metrics → mgpusim_metrics. "
    "Simulation completion is verified by presence of kernel_time anywhere in file, not as last line."))

# Note: CD has no result.sh
fail_entries.append(("PHASE0-MISSING", "CD", "ALL",
    "MISSING result.sh: CD scheme has no result.sh (unlike REC, HMG, superdirectory). "
    "Data extracted directly from rawdata/sql/*.sqlite3 via custom extraction."))

# Note: pagerank_CD SQL missing
fail_entries.append(("PHASE0-MISSING", "CD", "pagerank",
    "MISSING SQL: pagerank_CD_0.sqlite3 does not exist. "
    "Only pagerank_CD_0.txt (raw simulation log) exists in rawdata/text/ — NOT pipe-delimited, cannot extract metrics. "
    "CD×pagerank → MISSING in all analyses."))

# Note: BFS baseline missing
fail_entries.append(("PHASE0-MISSING", "CD,REC,HMG", "bfs",
    "MISSING: bfs has no data for CD, REC, or HMG schemes. "
    "bfs_superdirectory only. Cannot compute speedup for bfs. → MISSING in PHASE 2-6."))

# Note: matrixmultiplication_CD SQL missing for variants 1-4
fail_entries.append(("PHASE0-INFO", "CD", "matrixmultiplication",
    "INFO: Only matrixmultiplication_CD_0.sqlite3 exists (not 1-4). "
    "CD_0 (coherence-unit-size=0) is the standard 64B cache-line directory and correct baseline. "
    "CD_1..4 are CD with larger coherence units (not the primary baseline)."))

# Write FAIL_LOG.md
with open(FAIL_LOG, "w") as f:
    f.write("# FAIL_LOG.md — SuperDir Experiment Analysis\n\n")
    f.write("Auto-generated by phase0_inventory.py. Updated incrementally by each PHASE script.\n\n")
    f.write("| Phase | Scheme | Workload | Issue |\n")
    f.write("|-------|--------|----------|-------|\n")
    for (phase, scheme, wl, msg) in fail_entries:
        f.write(f"| {phase} | {scheme} | {wl} | {msg} |\n")

# Write 00_inventory.csv
fieldnames = ["scheme", "workload", "status", "data_file", "notes"]
with open(TABLES / "00_inventory.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(inventory)

print("\n=== PHASE 0 SUMMARY ===")
statuses = {}
for row in inventory:
    statuses[row["status"]] = statuses.get(row["status"], 0) + 1
for s, n in sorted(statuses.items()):
    print(f"  {s}: {n}")

print(f"\nFAIL_LOG entries: {len(fail_entries)}")
print(f"Output: {TABLES}/00_inventory.csv")
print(f"Output: {FAIL_LOG}")

# PHASE 0 checklist
print("\n=== PHASE 0 CHECKLIST ===")
missing = [r for r in inventory if r["status"] == "MISSING"]
ok = [r for r in inventory if r["status"] in ("OK", "EXTRACTED")]
print(f"[{'PASS' if len(missing) < 16 else 'FAIL'}] {len(ok)}/{len(inventory)} (scheme×workload) pairs have data")
print(f"[NOTE] {len(missing)} MISSING pairs: {[(r['scheme'], r['workload']) for r in missing]}")
kt_fails = [e for e in fail_entries if "NO_KERNEL_TIME" in e[3]]
print(f"[{'PASS' if not kt_fails else 'FAIL'}] kernel_time present: {len(kt_fails)} failures")
fmt_fails = [e for e in fail_entries if "FORMAT_VIOLATIONS" in e[3]]
print(f"[{'PASS' if not fmt_fails else 'FAIL'}] Format violations: {len(fmt_fails)} files with violations")
