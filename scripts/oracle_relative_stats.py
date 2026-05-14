#!/usr/bin/env python3
"""oracle_relative_stats.py — §3.3 oracle-relative statistics extractor.

Pre-committed definitions (do NOT change post-hoc; see plan):
  - Candidate static CDs (in ascending granularity order):
      CD_0=64B, CD_1=128B, CD_2=256B, CD_4=1KB, CD_6=4KB, CD_8=16KB
    CD_3, CD_5, CD_7 are not superdirectory granularities and are excluded.
  - oracle_CD(w) = window-IPC-best static CD; tie within ±1% → smaller CD.
    tie_fraction reports how often any other CD is within 1% of the best.
  - IPC = delta_instructions / delta_sim_time_ns.
    Frequency assumed 1 GHz (verified once via grep WithFreq).
    Ratios are clock-frequency-invariant, so the assumption only affects
    absolute IPC, not the oracle-relative comparisons reported here.
  - Two warmup variants emitted: all_windows, post_warmup (skip first 5).
  - sd_vs_static_best uses the SAME static CD across all windows
    (geomean-best over all windows), per the plan's "global 최선 정적 CD".

Pre-committed thresholds for §3.3 claims (printed in threshold_report.md):
  - entropy >= 1.5
  - sd_oracle_p10 >= 0.7
  - sd_above_oracle_fraction >= 0.1 in >= 2 workloads
  - sd_vs_static_best geomean >= 1.05
"""

import csv
import math
import sys
from pathlib import Path
from statistics import mean

WORKLOADS = [
    "matrixmultiplication", "matrixtranspose", "spmv",
    "pagerank", "conv2d", "relu", "stencil2d",
]
# default static CDs for "deployment-realistic" comparison.
# Pre-committed (do NOT change post-hoc): the system at deployment time does
# NOT know the per-workload IPC-best CD, so a workload-agnostic fixed R is
# the realistic baseline. We report all three so the §3.3 claim is robust:
#   CD_2 (256B)  — HMG-adjacent mid-range
#   CD_4 (1KB)   — median of the 6-CD candidate set
#   CD_6 (4KB)   — coarse-grained representative
DEFAULT_STATIC_CDS = ["CD_2", "CD_4", "CD_6"]
CD_VARIANTS = ["CD_0", "CD_1", "CD_2", "CD_4", "CD_6", "CD_8"]
CD_LABELS = {
    "CD_0": "64B", "CD_1": "128B", "CD_2": "256B",
    "CD_4": "1KB", "CD_6": "4KB", "CD_8": "16KB",
}
SD_VARIANT = "SD"
TIE_TOL = 0.01  # ±1%
WARMUP_SKIP = 5

REPO_ROOT = Path("/root/mgpusim_home")
PER_WINDOW_DIR = REPO_ROOT / "results" / "per_window"
OUTPUT_CSV = REPO_ROOT / "results" / "oracle_relative_stats.csv"
OUTPUT_TABLE = REPO_ROOT / "results" / "oracle_relative_table.md"
OUTPUT_REPORT = REPO_ROOT / "results" / "threshold_report.md"

PRE_COMMITTED = {
    "entropy_min": 1.5,
    "p10_min": 0.7,
    "above_oracle_min_fraction": 0.1,
    "above_oracle_min_workloads": 2,
    "sd_vs_static_best_min": 1.05,
    # Time-sum oracle thresholds (pre-committed; classify motivation strength)
    "headroom_strong": 0.10,   # >=10%
    "headroom_moderate": 0.05, # 5-10%
    "capture_good": 0.5,       # SD captures >=50% of headroom
    # Cross-variant cum_instructions consistency tolerance
    "delta_inst_tol": 0.01,    # ±1%
}


def load_window_raw(path: Path) -> list[tuple[int, float, float]]:
    """Return sorted list of (idx, sim_time_ns, cum_instructions)."""
    rows: list[tuple[int, float, float]] = []
    with path.open() as f:
        for r in csv.DictReader(f):
            rows.append((int(r["window_idx"]),
                         float(r["sim_time_ns"]),
                         float(r["cum_instructions"])))
    rows.sort()
    return rows


def deltas(raw: list[tuple[int, float, float]]) -> tuple[list[float], list[float]]:
    """From sorted raw rows, return (delta_t per window, delta_inst per window)."""
    dt_list, di_list = [], []
    prev_t, prev_i = 0.0, 0.0
    for _, t, i in raw:
        dt_list.append(t - prev_t)
        di_list.append(i - prev_i)
        prev_t, prev_i = t, i
    return dt_list, di_list


def load_window_ipc(path: Path) -> list[float]:
    """Per-window IPC list. Window 0 IPC uses (inst[0] / t[0]); window k>0
    uses delta against window k-1. Zero or non-positive dt → IPC=0."""
    raw = load_window_raw(path)
    dt_list, di_list = deltas(raw)
    return [(di / dt) if dt > 0 else 0.0 for dt, di in zip(dt_list, di_list)]


def cross_variant_inst_check(
    workload: str,
    raws: dict[str, list[tuple[int, float, float]]],
) -> tuple[bool, str]:
    """Verify per-window cum_instructions agree across CD variants within tol.

    Pre-committed: tolerance is PRE_COMMITTED['delta_inst_tol'] (±1%).
    Returns (ok, message). Aborts the headroom analysis if not ok.
    """
    n = len(next(iter(raws.values())))
    tol = PRE_COMMITTED["delta_inst_tol"]
    for v, raw in raws.items():
        if len(raw) != n:
            return False, f"{workload}: {v} has {len(raw)} windows vs {n}"
    for w in range(n):
        insts = [raw[w][2] for raw in raws.values()]
        lo, hi = min(insts), max(insts)
        if lo > 0 and (hi - lo) / lo > tol:
            return False, (
                f"{workload}: window {w} cum_inst spread "
                f"{lo}..{hi} exceeds ±{tol * 100:.0f}% across variants"
            )
    return True, ""


def oracle_per_window(cd_ipcs: dict[str, list[float]]):
    """For each window, return (best_cd, best_ipc, tie_with_best)."""
    n = len(next(iter(cd_ipcs.values())))
    out_cd, out_ipc, out_tie = [], [], []
    for w in range(n):
        # CD_VARIANTS is in ascending granularity order, so smaller-CD wins ties
        best_cd = CD_VARIANTS[0]
        best_ipc = cd_ipcs[best_cd][w]
        for cd in CD_VARIANTS[1:]:
            v = cd_ipcs[cd][w]
            if best_ipc <= 0:
                if v > 0:
                    best_cd, best_ipc = cd, v
                continue
            if v / best_ipc > 1.0 + TIE_TOL:
                best_cd, best_ipc = cd, v
        # tie detection: any other CD within ±1% of best?
        tied = False
        if best_ipc > 0:
            for cd in CD_VARIANTS:
                if cd == best_cd:
                    continue
                v = cd_ipcs[cd][w]
                if v > 0 and abs(v / best_ipc - 1.0) <= TIE_TOL:
                    tied = True
                    break
        out_cd.append(best_cd)
        out_ipc.append(best_ipc)
        out_tie.append(tied)
    return out_cd, out_ipc, out_tie


def shannon_entropy(items: list[str]) -> float:
    if not items:
        return 0.0
    counts: dict[str, int] = {}
    for it in items:
        counts[it] = counts.get(it, 0) + 1
    total = len(items)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = p * (len(s) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] * (1.0 - (pos - lo)) + s[hi] * (pos - lo)


def geomean(values: list[float]) -> float:
    pos = [v for v in values if v > 0]
    if not pos:
        return 0.0
    return math.exp(sum(math.log(v) for v in pos) / len(pos))


def compute(workload: str, post_warmup: bool) -> dict | None:
    wd = PER_WINDOW_DIR / workload
    raws: dict[str, list[tuple[int, float, float]]] = {}
    for cd in CD_VARIANTS:
        f = wd / f"{workload}_{cd}_per_window.csv"
        if not f.exists():
            print(f"  [skip] missing {f}", file=sys.stderr)
            return None
        raws[cd] = load_window_raw(f)
    sd_path = wd / f"{workload}_{SD_VARIANT}_per_window.csv"
    if not sd_path.exists():
        print(f"  [skip] missing {sd_path}", file=sys.stderr)
        return None
    raws[SD_VARIANT] = load_window_raw(sd_path)

    n_total = len(raws[SD_VARIANT])
    for v, raw in raws.items():
        if len(raw) != n_total:
            print(f"  [err] {workload}: window count mismatch {v}={len(raw)} vs SD={n_total}",
                  file=sys.stderr)
            return None

    # Sanity: cum_instructions must agree across variants per window (±1%).
    # If not, oracle/static_best/sd time comparisons would be meaningless
    # (different variants ran different amounts of work per window).
    ok, msg = cross_variant_inst_check(workload, raws)
    if not ok:
        print(f"  [abort] {msg}", file=sys.stderr)
        return None

    cd_ipcs = {cd: [(di / dt) if dt > 0 else 0.0
                    for dt, di in zip(*deltas(raws[cd]))]
               for cd in CD_VARIANTS}
    sd_ipc = [(di / dt) if dt > 0 else 0.0
              for dt, di in zip(*deltas(raws[SD_VARIANT]))]

    # Per-window delta_t for time-sum oracle; identical layout as cd_ipcs.
    cd_dt = {cd: deltas(raws[cd])[0] for cd in CD_VARIANTS}
    sd_dt = deltas(raws[SD_VARIANT])[0]

    if post_warmup:
        if n_total <= WARMUP_SKIP:
            return None
        for cd in CD_VARIANTS:
            cd_ipcs[cd] = cd_ipcs[cd][WARMUP_SKIP:]
            cd_dt[cd] = cd_dt[cd][WARMUP_SKIP:]
        sd_ipc = sd_ipc[WARMUP_SKIP:]
        sd_dt = sd_dt[WARMUP_SKIP:]

    oracle_cd, oracle_ipc, ties = oracle_per_window(cd_ipcs)
    n = len(oracle_cd)

    cd_count = {cd: 0 for cd in CD_VARIANTS}
    for cd in oracle_cd:
        cd_count[cd] += 1

    ratios = [
        sd_ipc[w] / oracle_ipc[w] if oracle_ipc[w] > 0 else 0.0
        for w in range(n)
    ]

    cd_geomean = {cd: geomean(cd_ipcs[cd]) for cd in CD_VARIANTS}
    best_static_cd = max(cd_geomean, key=cd_geomean.get)
    best_static_g = cd_geomean[best_static_cd]
    sd_g = geomean(sd_ipc)

    # sd_vs_default_X: SD vs deployment-realistic fixed R (per pre-committed
    # candidate list DEFAULT_STATIC_CDS). Workload-agnostic.
    sd_vs_default = {
        cd: (sd_g / cd_geomean[cd]) if cd_geomean[cd] > 0 else 0.0
        for cd in DEFAULT_STATIC_CDS
    }

    # ---- Time-sum oracle headroom ----------------------------------------
    # delta_inst is identical across variants (sanity-checked above), so
    # per-window time min ⇔ per-window IPC max. We aggregate by SUM of
    # times, which is workload-runtime-realistic (long windows weighted
    # more) — distinct from the equal-weight per-window IPC ratio above.
    n = len(sd_dt)
    oracle_time_ns = 0.0
    for w in range(n):
        per_win = [cd_dt[cd][w] for cd in CD_VARIANTS if cd_dt[cd][w] > 0]
        oracle_time_ns += min(per_win) if per_win else 0.0
    cd_total_t = {cd: sum(cd_dt[cd]) for cd in CD_VARIANTS}
    static_best_cd_time = min(cd_total_t, key=cd_total_t.get)
    static_best_time_ns = cd_total_t[static_best_cd_time]
    sd_time_ns = sum(sd_dt)

    oracle_headroom = (
        (static_best_time_ns / oracle_time_ns - 1.0)
        if oracle_time_ns > 0 else 0.0
    )
    headroom_window = static_best_time_ns - oracle_time_ns
    sd_headroom_capture = (
        (static_best_time_ns - sd_time_ns) / headroom_window
        if headroom_window > 0 else 0.0
    )
    # SD speedup over the time-defined static best (separate from the
    # geomean-IPC-defined sd_vs_static_best already computed).
    sd_speedup_over_static_best_time = (
        (static_best_time_ns / sd_time_ns) if sd_time_ns > 0 else 0.0
    )

    return {
        "workload": workload,
        "warmup_variant": "post_warmup" if post_warmup else "all_windows",
        "n_windows": n,
        "n_warmup_excluded": WARMUP_SKIP if post_warmup else 0,
        "tie_fraction": sum(ties) / n if n else 0.0,
        **{f"share_{cd}": cd_count[cd] / n if n else 0.0 for cd in CD_VARIANTS},
        "best_cd_entropy": shannon_entropy(oracle_cd),
        "best_cd_switch_rate": (
            sum(1 for i in range(1, n) if oracle_cd[i] != oracle_cd[i - 1]) /
            (n - 1) if n > 1 else 0.0
        ),
        "sd_oracle_mean": mean(ratios) if ratios else 0.0,
        "sd_oracle_p10": percentile(ratios, 0.10),
        "sd_oracle_p50": percentile(ratios, 0.50),
        "sd_oracle_p90": percentile(ratios, 0.90),
        "sd_above_oracle_fraction": (
            sum(1 for w in range(n) if sd_ipc[w] > oracle_ipc[w]) / n if n else 0.0
        ),
        "sd_vs_static_best": sd_g / best_static_g if best_static_g > 0 else 0.0,
        "best_static_cd": best_static_cd,
        **{f"sd_vs_default_{cd.lower()}": sd_vs_default[cd] for cd in DEFAULT_STATIC_CDS},
        # Time-sum oracle headroom block
        "oracle_time_ns": oracle_time_ns,
        "static_best_cd_time": static_best_cd_time,
        "static_best_time_ns": static_best_time_ns,
        "sd_time_ns": sd_time_ns,
        "oracle_headroom": oracle_headroom,
        "sd_headroom_capture": sd_headroom_capture,
        "sd_speedup_over_static_best_time": sd_speedup_over_static_best_time,
    }


def main() -> int:
    rows: list[dict] = []
    for w in WORKLOADS:
        for post in (False, True):
            r = compute(w, post)
            if r is not None:
                rows.append(r)
    if not rows:
        print("no data computed", file=sys.stderr)
        return 1

    fieldnames = [
        "workload", "warmup_variant", "n_windows", "n_warmup_excluded",
        "tie_fraction",
        *[f"share_{cd}" for cd in CD_VARIANTS],
        "best_cd_entropy", "best_cd_switch_rate",
        "sd_oracle_mean", "sd_oracle_p10", "sd_oracle_p50", "sd_oracle_p90",
        "sd_above_oracle_fraction",
        "sd_vs_static_best", "best_static_cd",
        *[f"sd_vs_default_{cd.lower()}" for cd in DEFAULT_STATIC_CDS],
        "oracle_time_ns", "static_best_cd_time", "static_best_time_ns",
        "sd_time_ns",
        "oracle_headroom", "sd_headroom_capture",
        "sd_speedup_over_static_best_time",
    ]
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})
    print(f"wrote {OUTPUT_CSV}  ({len(rows)} rows)")

    # markdown table
    def fmt(r: dict) -> str:
        return (
            f"| {r['workload']:<22}"
            f" | {r['n_windows']:>5}"
            f" | {r['tie_fraction']:.3f}"
            f" | {r['best_cd_entropy']:.2f}"
            f" | {r['best_cd_switch_rate']:.2f}"
            f" | {r['sd_oracle_mean']:.3f}"
            f" | {r['sd_oracle_p10']:.3f}"
            f" | {r['sd_oracle_p50']:.3f}"
            f" | {r['sd_oracle_p90']:.3f}"
            f" | {r['sd_above_oracle_fraction']:.3f}"
            f" | {r['sd_vs_static_best']:.3f}"
            f" | {r['best_static_cd']}"
            f" |"
        )

    header = (
        "| workload | n | tie | entropy | switch | sd/oracle | p10 | p50 | p90 | above | sd/best | best CD |\n"
        "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|"
    )
    parts = ["# §3.3 Oracle-relative statistics", ""]
    for variant in ("all_windows", "post_warmup"):
        parts += [f"## {variant}", "", header]
        for r in rows:
            if r["warmup_variant"] == variant:
                parts.append(fmt(r))
        parts.append("")
    OUTPUT_TABLE.write_text("\n".join(parts))
    print(f"wrote {OUTPUT_TABLE}")

    # threshold report
    rep = [
        "# Threshold report (pre-committed; not adjustable post-hoc)",
        "",
        f"Thresholds: {PRE_COMMITTED}",
        "",
    ]
    for variant in ("all_windows", "post_warmup"):
        rep += [f"## {variant}", ""]
        sub = [r for r in rows if r["warmup_variant"] == variant]

        rep.append("### entropy >= 1.5  (phase variation general)")
        for r in sub:
            ok = r["best_cd_entropy"] >= PRE_COMMITTED["entropy_min"]
            rep.append(f"- {r['workload']:<22}  entropy={r['best_cd_entropy']:.2f}"
                       f"  {'PASS' if ok else 'FAIL'}")
        rep.append("")

        rep.append("### sd_oracle_p10 >= 0.7  (worst-case >= 70% of oracle)")
        for r in sub:
            ok = r["sd_oracle_p10"] >= PRE_COMMITTED["p10_min"]
            rep.append(f"- {r['workload']:<22}  p10={r['sd_oracle_p10']:.3f}"
                       f"  {'PASS' if ok else 'FAIL'}")
        rep.append("")

        n_above = sum(
            1 for r in sub
            if r["sd_above_oracle_fraction"] >= PRE_COMMITTED["above_oracle_min_fraction"]
        )
        ok = n_above >= PRE_COMMITTED["above_oracle_min_workloads"]
        rep.append("### sd_above_oracle_fraction >= 0.1 in >= 2 workloads (oracle ceiling)")
        rep.append(f"  {n_above} workloads pass.  {'PASS' if ok else 'FAIL'}")
        for r in sub:
            rep.append(f"  - {r['workload']:<22}  above={r['sd_above_oracle_fraction']:.3f}")
        rep.append("")

        ratios = [r["sd_vs_static_best"] for r in sub if r["sd_vs_static_best"] > 0]
        gm = (
            math.exp(sum(math.log(x) for x in ratios) / len(ratios))
            if ratios else 0.0
        )
        ok = gm >= PRE_COMMITTED["sd_vs_static_best_min"]
        rep.append(f"### sd_vs_static_best geomean >= 1.05  (got {gm:.4f})  {'PASS' if ok else 'FAIL'}")
        for r in sub:
            rep.append(f"  - {r['workload']:<22}  sd/best={r['sd_vs_static_best']:.3f}"
                       f"  best_static_cd={r['best_static_cd']}")
        rep.append("")

        # sd_vs_default — deployment-realistic baselines (CD_2/4/6).
        # Same 1.05 threshold as sd_vs_static_best (pre-committed in plan).
        rep.append("### sd_vs_default — deployment-realistic fixed R (CD_2 / CD_4 / CD_6)")
        rep.append("Same 1.05 geomean threshold as sd_vs_static_best.")
        rep.append("")
        rep.append("| workload | sd/CD_2 (256B) | sd/CD_4 (1KB) | sd/CD_6 (4KB) |")
        rep.append("|---|--:|--:|--:|")
        for r in sub:
            rep.append(
                f"| {r['workload']:<22}"
                f" | {r['sd_vs_default_cd_2']:.3f}"
                f" | {r['sd_vs_default_cd_4']:.3f}"
                f" | {r['sd_vs_default_cd_6']:.3f}"
                f" |"
            )
        rep.append("")
        # geomean per default
        for cd in DEFAULT_STATIC_CDS:
            key = f"sd_vs_default_{cd.lower()}"
            vals = [r[key] for r in sub if r[key] > 0]
            gm_d = (
                math.exp(sum(math.log(x) for x in vals) / len(vals))
                if vals else 0.0
            )
            ok_d = gm_d >= PRE_COMMITTED["sd_vs_static_best_min"]
            rep.append(
                f"  geomean(sd/{cd}) = {gm_d:.4f}  "
                f"{'PASS' if ok_d else 'FAIL'} (>= 1.05)"
            )
        rep.append("")

        # ---- Time-sum oracle headroom -----------------------------------
        rep.append("### Time-sum oracle headroom (deployment runtime)")
        rep.append(
            "oracle_time = sum_w min_cd dt; "
            "static_best_time = min_cd sum_w dt; "
            "headroom = static_best/oracle - 1; "
            "capture = (static_best - sd) / (static_best - oracle)"
        )
        rep.append("")
        rep.append("| workload | oracle (ns) | static_best CD | static_best (ns) | sd (ns) | headroom | sd_capture |")
        rep.append("|---|--:|---|--:|--:|--:|--:|")
        for r in sub:
            rep.append(
                f"| {r['workload']:<22}"
                f" | {r['oracle_time_ns']:.3e}"
                f" | {r['static_best_cd_time']}"
                f" | {r['static_best_time_ns']:.3e}"
                f" | {r['sd_time_ns']:.3e}"
                f" | {r['oracle_headroom'] * 100:+.2f}%"
                f" | {r['sd_headroom_capture']:+.3f}"
                f" |"
            )
        rep.append("")
        # classify each workload's headroom strength
        rep.append("**Headroom strength classification (per pre-committed thresholds):**")
        for r in sub:
            h = r["oracle_headroom"]
            if h >= PRE_COMMITTED["headroom_strong"]:
                cls = "STRONG (>=10%)"
            elif h >= PRE_COMMITTED["headroom_moderate"]:
                cls = "MODERATE (5-10%)"
            else:
                cls = "WEAK (<5%)"
            rep.append(f"  - {r['workload']:<22}  headroom={h * 100:+.2f}%  → {cls}")
        rep.append("")
        # capture distribution incl. negatives
        rep.append("**SD headroom capture distribution:**")
        capture_neg = [r for r in sub if r["sd_headroom_capture"] < 0]
        capture_lo = [r for r in sub
                      if 0 <= r["sd_headroom_capture"] < PRE_COMMITTED["capture_good"]]
        capture_ok = [r for r in sub
                      if r["sd_headroom_capture"] >= PRE_COMMITTED["capture_good"]]
        if capture_neg:
            rep.append(
                f"  - SD WORSE than static_best (capture < 0):  "
                + ", ".join(f"{r['workload']}({r['sd_headroom_capture']:+.2f})"
                            for r in capture_neg)
            )
            rep.append(
                "    → exclude these from §3.3 main; report in §5 limitations."
            )
        if capture_lo:
            rep.append(
                f"  - SD captures <50% of headroom:  "
                + ", ".join(f"{r['workload']}({r['sd_headroom_capture']:+.2f})"
                            for r in capture_lo)
            )
        if capture_ok:
            rep.append(
                f"  - SD captures >=50%:  "
                + ", ".join(f"{r['workload']}({r['sd_headroom_capture']:+.2f})"
                            for r in capture_ok)
            )
        rep.append("")
        # candidate sentences — strong / medium / weak
        n_strong = sum(1 for r in sub if r["oracle_headroom"] >= PRE_COMMITTED["headroom_strong"])
        n_mod = sum(1 for r in sub
                    if PRE_COMMITTED["headroom_moderate"] <= r["oracle_headroom"]
                    < PRE_COMMITTED["headroom_strong"])
        # geomean headroom across workloads (multiplicative, on (1+h))
        h_factors = [(1.0 + r["oracle_headroom"]) for r in sub]
        gm_h = (
            math.exp(sum(math.log(f) for f in h_factors) / len(h_factors))
            if h_factors else 1.0
        )
        avg_h = (gm_h - 1.0) * 100
        cap_vals = [r["sd_headroom_capture"] for r in sub]
        avg_cap = sum(cap_vals) / len(cap_vals) if cap_vals else 0.0
        cap_min = min(cap_vals) if cap_vals else 0.0
        cap_max = max(cap_vals) if cap_vals else 0.0
        worst = min(sub, key=lambda r: r["sd_headroom_capture"])
        best = max(sub, key=lambda r: r["sd_headroom_capture"])
        rep.append("**§3.3 candidate sentences (auto-generated from results):**")
        rep.append("")
        rep.append("STRONG variant (use only if " +
                   f"avg headroom >=10%; observed {avg_h:.1f}%):")
        rep.append(
            f"> Across {len(sub)} workloads, statically choosing the best fixed "
            f"coherence granularity leaves an average headroom of {avg_h:.1f}% "
            f"relative to a per-window oracle. SD captures {avg_cap * 100:.0f}% "
            f"of this headroom on average, with workload variance ranging from "
            f"{cap_min * 100:+.0f}% ({worst['workload']}) to "
            f"{cap_max * 100:+.0f}% ({best['workload']})."
        )
        rep.append("")
        rep.append("MEDIUM variant (use if 5% <= avg headroom < 10%):")
        rep.append(
            f"> A per-window oracle outperforms the best fixed coherence "
            f"granularity by {avg_h:.1f}% on average across {len(sub)} "
            f"workloads. SD recovers a fraction of this headroom "
            f"(mean capture {avg_cap * 100:.0f}%); we report per-workload "
            f"capture in Table X to characterize where dynamic adaptation "
            f"helps most."
        )
        rep.append("")
        rep.append("WEAK variant (use if avg headroom < 5%):")
        rep.append(
            f"> Static R choices already realize most of the available "
            f"runtime; the per-window oracle yields only {avg_h:.1f}% "
            f"additional headroom on average. SD's role is therefore better "
            f"framed as adaptive matching rather than quantitative speedup."
        )
        rep.append("")

    rep += [
        "## Action on threshold miss (per plan)",
        "",
        "- entropy < 1.5: do not generalize 'phase variation' in §3.3.",
        "- p10 < 0.7: do not claim 'SD maintains >=70% of oracle in the worst case'.",
        "- above_oracle < 0.1 (or <2 workloads): do not claim SD exceeds the static-R ceiling.",
        "- sd_vs_static_best < 1.05: do not claim '5% over static best' in §3.3.",
        "- sd_vs_default all FAIL (geomean < 1.05 for every default candidate):",
        "    use only qualitative claim ('SD captures phase-level optimal R')",
        "    in §3.3, not a quantitative speedup.",
        "- sd_vs_default partial PASS: report which default(s) and justify the",
        "    choice as deployment-reasonable in §4 or §5.",
        "- Thresholds themselves are pre-committed: weaken claims, do not adjust thresholds.",
    ]
    OUTPUT_REPORT.write_text("\n".join(rep))
    print(f"wrote {OUTPUT_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
