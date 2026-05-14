#!/usr/bin/env python3
"""
mm_l1v_verify.py — quick verification on the matrix-multiplication
CD_0/CD_4/CD_8 re-sim with the L1V tracer enabled and bank
interleaving fixed at 128B.

Compares against the baseline mm sims under
results/CD/rawdata/sql/ and prints a side-by-side table of:

  - kernel_time
  - cpi_VMem (mean across CUs)
  - L1VCache req_average_latency (mean / std / max÷min across the
    256 banks per workload-config)
  - L2Cache req_average_latency (same statistics)
  - DRAM_read_bytes
  - L2 hit / local-hit / remote-hit rates
  - L2_read-miss-{cold,capacity,coh-evict,coh-write}

The point: confirm the fix produces L1V data, and see whether the
bank-interleaving decoupling changes the U-shape (vs the baseline
which had bank striding scale with CD).
"""

from __future__ import annotations

import sqlite3
import statistics
import sys
from pathlib import Path

VERIFY_DIR = Path("/tmp/mm_l1v_verify")
BASELINE_DIR = Path("/root/mgpusim_home/results/CD/rawdata/sql")
WORKLOAD = "matrixmultiplication"
CONFIGS = ["0", "4", "8"]


def find_sqlite(parent: Path) -> Path | None:
    paths = sorted(parent.glob("akita_sim_*.sqlite3"))
    return paths[-1] if paths else None


def fetch(con, what: str, loc_like: str | None = None) -> list[float]:
    cur = con.cursor()
    if loc_like:
        cur.execute(
            "SELECT value FROM mgpusim_metrics "
            "WHERE what=? AND location LIKE ? "
            "AND location NOT LIKE 'GPU[0].%' "
            "AND location NOT LIKE 'GPU[1].%';",
            (what, loc_like),
        )
    else:
        cur.execute(
            "SELECT value FROM mgpusim_metrics WHERE what=?;",
            (what,),
        )
    return [float(v[0]) for v in cur.fetchall() if v[0] is not None]


def fetch_kernel_time(con) -> float | None:
    cur = con.cursor()
    cur.execute(
        "SELECT value FROM mgpusim_metrics "
        "WHERE what='kernel_time' AND location='Driver';"
    )
    rows = cur.fetchall()
    return float(rows[0][0]) if rows else None


def fetch_dir(con, what: str) -> float:
    cur = con.cursor()
    cur.execute(
        "SELECT SUM(value) FROM cohDir_metrics "
        "WHERE what=? AND location LIKE 'GPU[%].CohDir%' "
        "AND location NOT LIKE 'GPU[0].%' "
        "AND location NOT LIKE 'GPU[1].%';",
        (what,),
    )
    rows = cur.fetchall()
    return float(rows[0][0] or 0)


def stats(vs: list[float]) -> dict:
    if not vs:
        return {"n": 0}
    s = sorted(vs)
    return {
        "n": len(s),
        "mean": statistics.fmean(s),
        "min": s[0],
        "max": s[-1],
        "std": statistics.pstdev(s) if len(s) > 1 else 0.0,
        "max_over_min": s[-1] / s[0] if s[0] > 0 else float("inf"),
    }


def gather(con) -> dict:
    out = {}
    out["kernel_time_s"] = fetch_kernel_time(con) or 0
    out["L1V_lat_ns"] = stats(
        [v * 1e9 for v in fetch(con, "req_average_latency",
                                "%L1VCache%")]
    )
    out["L2_lat_ns"] = stats(
        [v * 1e9 for v in fetch(con, "req_average_latency",
                                "%L2Cache%")]
    )
    out["L1S_lat_ns"] = stats(
        [v * 1e9 for v in fetch(con, "req_average_latency",
                                "%L1SCache%")]
    )
    out["CohDir_lat_ns"] = stats(
        [v * 1e9 for v in fetch(con, "req_average_latency",
                                "%CohDir%")]
    )

    # CPIStack mean across CUs
    cpi = {}
    for stack_name in ("VMem", "VMemInst", "VALU", "Idle", "total"):
        vs = fetch(con, f"CPIStack.{stack_name}",
                   "GPU[%].SA[%].CU[%]")
        cpi[stack_name] = statistics.fmean(vs) if vs else None
    out["cpi"] = cpi

    # L2 hit rate from per-bank read-hit / read-miss / read-mshr-hit
    rh = sum(fetch(con, "read-hit", "%L2Cache%"))
    rm = sum(fetch(con, "read-miss", "%L2Cache%"))
    rmh = sum(fetch(con, "read-mshr-hit", "%L2Cache%"))
    rrh = sum(fetch(con, "remote-read-hit", "%L2Cache%"))
    rrm = sum(fetch(con, "remote-read-miss", "%L2Cache%"))
    rrmh = sum(fetch(con, "remote-read-mshr-hit", "%L2Cache%"))
    tot_r = rh + rm + rmh
    tot_rr = rrh + rrm + rrmh
    out["L2_hit_pct"] = (rh + rmh) / tot_r * 100 if tot_r > 0 else 0
    out["L2_remote_hit_pct"] = (rrh + rrmh) / tot_rr * 100 if tot_rr > 0 else 0
    local_h = (rh - rrh) + (rmh - rrmh)
    local_tot = tot_r - tot_rr
    out["L2_local_hit_pct"] = local_h / local_tot * 100 if local_tot > 0 else 0

    # L2 read-miss reason breakdown
    miss_reasons = {}
    for reason in ("cold", "capacity", "coh-write", "coh-evict", "other"):
        miss_reasons[reason] = sum(fetch(con, f"read-miss-{reason}",
                                         "%L2Cache%"))
    out["miss_reasons"] = miss_reasons

    # DRAM
    out["DRAM_read_bytes"] = sum(fetch(con, "read_size", "%DRAM%"))
    out["DRAM_read_count"] = sum(fetch(con, "read_trans_count", "%DRAM%"))

    # RDMA total bytes — sum (count × per-msg size) over all (op, dir)
    rdma_bytes = 0.0
    cur = con.cursor()
    cur.execute(
        "SELECT what, value FROM mgpusim_metrics "
        "WHERE location LIKE 'GPU[%].RDMA' "
        "AND location NOT LIKE 'GPU[0].%' "
        "AND location NOT LIKE 'GPU[1].%';"
    )
    import re
    pat = re.compile(r"^(Read|Write|Inv) (Req|Rsp) (\d+)$")
    for what, val in cur.fetchall():
        m = pat.match(what)
        if m:
            rdma_bytes += float(val) * int(m.group(3))
    out["RDMA_total_bytes"] = rdma_bytes

    # Bank-skew-friendly stats already in L1V/L2 stats above.
    return out


def fmt(d: dict, key: str, fmt_str: str = "{:.1f}") -> str:
    if not d:
        return "—"
    sub = d.get(key)
    if sub is None or (isinstance(sub, dict) and sub.get("n", 0) == 0):
        return "—"
    if isinstance(sub, dict):
        return ("mean=" + fmt_str.format(sub["mean"])
                + f"  std={fmt_str.format(sub['std'])}"
                + f"  max÷min={sub['max_over_min']:.2f}"
                + f"  (n={sub['n']})")
    return fmt_str.format(sub)


def main() -> int:
    print(f"{'='*72}\n  matrix-multiplication L1V verification\n{'='*72}\n")
    print("Bank interleaving: fixed at 128B (decoupled from CD)")
    print("L1V tracer:        enabled (writearound/coalescer.go fix)")
    print()

    rows = []
    for cfg in CONFIGS:
        verify_db = find_sqlite(VERIFY_DIR / f"CD_{cfg}")
        baseline_db = BASELINE_DIR / f"{WORKLOAD}_CD_{cfg}.sqlite3"
        v_data = {}
        b_data = {}
        if verify_db and verify_db.exists():
            try:
                con = sqlite3.connect(f"file:{verify_db}?mode=ro", uri=True)
                v_data = gather(con)
                con.close()
            except Exception as exc:
                print(f"verify CD_{cfg} read error: {exc}")
        if baseline_db.exists():
            try:
                con = sqlite3.connect(f"file:{baseline_db}?mode=ro", uri=True)
                b_data = gather(con)
                con.close()
            except Exception as exc:
                print(f"baseline CD_{cfg} read error: {exc}")
        rows.append((cfg, b_data, v_data))

    # Header
    print(f"{'metric':<25}  " + "  ".join(
        f"{'CD_'+c+' baseline':>22}  {'CD_'+c+' new':>22}"
        for c, _, _ in rows
    )[:200])
    print()

    headline_keys = [
        ("kernel_time_s", "{:.6f}"),
        ("L2_hit_pct", "{:.2f}"),
        ("L2_local_hit_pct", "{:.2f}"),
        ("L2_remote_hit_pct", "{:.2f}"),
        ("DRAM_read_bytes", "{:.0f}"),
        ("DRAM_read_count", "{:.0f}"),
        ("RDMA_total_bytes", "{:.0f}"),
    ]
    for k, fs in headline_keys:
        line = f"{k:<25}  "
        for cfg, b, v in rows:
            bv = b.get(k, "—") if b else "—"
            vv = v.get(k, "—") if v else "—"
            bs = fs.format(bv) if isinstance(bv, (int, float)) else str(bv)
            vs = fs.format(vv) if isinstance(vv, (int, float)) else str(vv)
            line += f"{bs:>22}  {vs:>22}  "
        print(line)
    print()

    # Latency stats blocks
    for lat_key in ("L1V_lat_ns", "L2_lat_ns", "L1S_lat_ns", "CohDir_lat_ns"):
        print(f"  {lat_key} (per-bank mean across {WORKLOAD}):")
        for cfg, b, v in rows:
            print(f"    CD_{cfg}: baseline {fmt(b, lat_key)}")
            print(f"          new      {fmt(v, lat_key)}")
        print()

    # CPI stack
    print("  CPI stack (mean across CUs):")
    cpi_keys = ("VMem", "VMemInst", "VALU", "Idle", "total")
    print(f"    {'config':<8}{'  '.join(f'{k:>10}' for k in cpi_keys)}")
    for cfg, b, v in rows:
        for label, d in (("baseline", b), ("new", v)):
            row = f"    CD_{cfg}/{label:<8}"
            for k in cpi_keys:
                cpi = d.get("cpi", {}) if d else {}
                val = cpi.get(k)
                row += f"  {val:10.3f}" if val is not None else f"  {'—':>10}"
            print(row)
    print()

    # L2 miss reason breakdown
    print("  L2 read-miss reason breakdown:")
    reason_keys = ("cold", "capacity", "coh-write", "coh-evict", "other")
    print(f"    {'config':<8}" + "  ".join(f"{r:>12}" for r in reason_keys))
    for cfg, b, v in rows:
        for label, d in (("baseline", b), ("new", v)):
            row = f"    CD_{cfg}/{label:<8}"
            for r in reason_keys:
                miss = d.get("miss_reasons", {}) if d else {}
                val = miss.get(r)
                row += f"  {val:12.0f}" if val is not None else f"  {'—':>12}"
            print(row)
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
