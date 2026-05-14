#!/usr/bin/env python3
"""h4_synthesis.py — 3-workload C-1/C-2/C-3 H4 synthesis.

Reads:
  results/oracle_relative_stats.csv           (50K-window baseline for all 3)
  results/per_window/relu_4x/                 (Step C-1 done)
  results/per_window/spmv_4x/                 (Step C-2 done)
  results/per_window/conv2d_4x/               (Step C-3 done)

Writes:
  results/h4_synthesis.md                     (3-workload table + verdict)
  results/h4_synthesis.csv                    (flat row per (workload, variant))

Pre-committed thresholds (from plan, do NOT change post-hoc):
  3/3 Δcapture ≥ +0.05 → H4 영향 큼, paper 본문에 한 단락 추가
  3/3 Δcapture <  +0.05 → H4 영향 작음, "robust to length" 한 줄
  혼합               → workload 의존 명시, 신중 보고

  Δ < 0 in any workload → 정지 신호 (해당 workload 진단 필요)
"""

import csv
import importlib.util
import math
import sys
from pathlib import Path

REPO = Path("/root/mgpusim_home")
SCRIPTS = REPO / "scripts"
RESULTS = REPO / "results"

spec = importlib.util.spec_from_file_location(
    "ors", SCRIPTS / "oracle_relative_stats.py"
)
ors = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ors)

OUT_MD = RESULTS / "h4_synthesis.md"
OUT_CSV = RESULTS / "h4_synthesis.csv"

# (baseline_workload_name, 4x_workload_name, scaling_label)
WORKLOADS = [
    ("relu", "relu_4x", "length 4× (3.84M → 15.36M)"),
    ("spmv", "spmv_4x", "dim 2× → ~4× nnz (65K → 131K)"),
    ("conv2d", "conv2d_4x", "N 4× (1 → 4 batch)"),
]


def load_baseline(workload: str) -> dict[str, dict]:
    """Existing N=1× stats keyed by warmup_variant."""
    path = RESULTS / "oracle_relative_stats.csv"
    out = {}
    with path.open() as f:
        for r in csv.DictReader(f):
            if r["workload"] == workload:
                out[r["warmup_variant"]] = r
    return out


def main() -> int:
    base = {}
    new = {}
    missing = []
    for bw, nw, _ in WORKLOADS:
        b = load_baseline(bw)
        if not b:
            missing.append(f"baseline:{bw}")
            continue
        base[bw] = b

        # check the 4x dir exists and has files
        d = REPO / "results" / "per_window" / nw
        if not d.exists() or not list(d.glob(f"{nw}_*_per_window.csv")):
            missing.append(f"4x:{nw}")
            continue
        rows = {}
        for post in (False, True):
            r = ors.compute(nw, post)
            if r is None:
                missing.append(f"compute({nw}, post={post})")
                continue
            rows[r["warmup_variant"]] = r
        new[bw] = rows

    if missing:
        print(f"[warn] missing: {missing}", file=sys.stderr)

    md = ["# Step C synthesis — H4 input-length 검증 (3 workload)", ""]
    md.append("Workloads (50K-window → 4× input scaling):")
    for bw, _, label in WORKLOADS:
        md.append(f"- `{bw}`: {label}")
    md.append("")
    if missing:
        md.append(f"**Missing data**: {missing}")
        md.append("")

    flat = []
    for bw, _, _ in WORKLOADS:
        if bw not in base or bw not in new:
            continue
        for variant in ("post_warmup", "all_windows"):
            if variant not in base[bw] or variant not in new[bw]:
                continue
            b = base[bw][variant]
            n = new[bw][variant]
            row = {"workload": bw, "warmup_variant": variant}
            for f_ in ["n_windows", "best_cd_entropy", "best_cd_switch_rate",
                       "sd_oracle_p10", "sd_oracle_mean",
                       "sd_above_oracle_fraction", "sd_vs_static_best",
                       "oracle_headroom", "sd_headroom_capture",
                       "sd_speedup_over_static_best_time",
                       "best_static_cd", "static_best_cd_time"]:
                row[f"50K_{f_}"] = b.get(f_, "")
                row[f"4x_{f_}"] = n.get(f_, "")
            flat.append(row)

    if flat:
        with OUT_CSV.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(flat[0].keys()))
            w.writeheader()
            for r in flat:
                w.writerow(r)
        print(f"wrote {OUT_CSV}")

    # Per-variant table
    for variant in ("post_warmup", "all_windows"):
        md.append(f"## {variant}")
        md.append("")
        md.append("| metric | relu 50K → 4× | spmv 50K → 4× | conv2d 50K → 4× |")
        md.append("|---|--:|--:|--:|")

        def cell(field, fmt=".3f"):
            cells = []
            for bw, _, _ in WORKLOADS:
                if bw not in base or bw not in new or variant not in new[bw]:
                    cells.append("—")
                    continue
                b = base[bw][variant]
                n = new[bw][variant]
                try:
                    bv = float(b[field]); nv = float(n[field])
                    cells.append(f"{bv:{fmt}} → {nv:{fmt}}  Δ{nv-bv:+.3f}")
                except Exception:
                    cells.append(f"{b.get(field,'')} → {n.get(field,'')}")
            return "| " + field + " | " + " | ".join(cells) + " |"

        for f_ in ["n_windows", "best_cd_entropy", "best_cd_switch_rate",
                   "sd_oracle_mean", "sd_oracle_p10", "sd_oracle_p90",
                   "sd_above_oracle_fraction",
                   "sd_vs_static_best",
                   "oracle_headroom", "sd_headroom_capture",
                   "sd_speedup_over_static_best_time"]:
            md.append(cell(f_))
        # categorical (best_static_cd)
        cells = []
        for bw, _, _ in WORKLOADS:
            if bw not in base or bw not in new or variant not in new[bw]:
                cells.append("—")
                continue
            b = base[bw][variant]; n = new[bw][variant]
            cells.append(f"{b['best_static_cd']} → {n['best_static_cd']}")
        md.append("| best_static_cd (geomean-IPC) | " + " | ".join(cells) + " |")
        cells = []
        for bw, _, _ in WORKLOADS:
            if bw not in base or bw not in new or variant not in new[bw]:
                cells.append("—")
                continue
            b = base[bw][variant]; n = new[bw][variant]
            cells.append(f"{b['static_best_cd_time']} → {n['static_best_cd_time']}")
        md.append("| static_best_cd_time          | " + " | ".join(cells) + " |")
        md.append("")

    # Synthesis verdict (post_warmup-based)
    md.append("## 종합 분류 (post_warmup Δcapture)")
    md.append("")
    deltas = {}
    for bw, _, _ in WORKLOADS:
        if bw in base and bw in new and "post_warmup" in new[bw]:
            d = (float(new[bw]["post_warmup"]["sd_headroom_capture"])
                 - float(base[bw]["post_warmup"]["sd_headroom_capture"]))
            deltas[bw] = d

    md.append("| workload | 50K capture | 4× capture | Δ |")
    md.append("|---|--:|--:|--:|")
    for bw, _, _ in WORKLOADS:
        if bw in deltas:
            b = float(base[bw]["post_warmup"]["sd_headroom_capture"])
            n = float(new[bw]["post_warmup"]["sd_headroom_capture"])
            md.append(f"| {bw} | {b:+.3f} | {n:+.3f} | **{deltas[bw]:+.3f}** |")
    md.append("")

    big = sum(1 for d in deltas.values() if d >= 0.05)
    small = sum(1 for d in deltas.values() if d < 0.05 and d >= 0.0)
    neg = sum(1 for d in deltas.values() if d < 0.0)
    n_total = len(deltas)
    md.append(f"- ≥ +0.05 (improvement): **{big}/{n_total}**")
    md.append(f"- < +0.05 (small change): **{small}/{n_total}**")
    md.append(f"- < 0 (worsened):           **{neg}/{n_total}**")
    md.append("")

    if neg > 0:
        verdict = "🔥 **악화 워크로드 존재** — 진단 필요 (sub-process 또는 measurement check)"
    elif big == n_total and n_total > 0:
        verdict = "✅ **H4 영향 큼** (3/3 +0.05점 이상) — paper 본문에 input length sensitivity 한 단락"
    elif big == 0:
        verdict = "ℹ️ **H4 영향 작음** (3/3 < 0.05) — \"robust to length\" 한 줄 보고"
    else:
        verdict = "⚠️ **혼합** — workload 의존 명시, 일반화 금지"
    md.append(f"**Verdict**: {verdict}")
    md.append("")

    # Paper framing impact section
    md.append("## Paper framing impact")
    md.append("")
    cd_shifts = []
    for bw, _, _ in WORKLOADS:
        if bw in base and bw in new and "post_warmup" in new[bw]:
            b = base[bw]["post_warmup"]; n = new[bw]["post_warmup"]
            cd_shifted = (b["best_static_cd"] != n["best_static_cd"]
                          or b["static_best_cd_time"] != n["static_best_cd_time"])
            cd_shifts.append((bw, cd_shifted))
    n_shifted = sum(1 for _, s in cd_shifts if s)
    md.append(f"### best_static_cd input-length sensitivity")
    md.append(f"- best_static_cd가 input length에 따라 변하는 workload: **{n_shifted}/{len(cd_shifts)}**")
    for bw, s in cd_shifts:
        md.append(f"  - {bw}: {'CHANGED' if s else 'stable'}")
    if n_shifted == len(cd_shifts) and n_shifted > 0:
        md.append("  → 3/3 변경됨, paper에 best-static-CD가 input-length-dependent임을 보고")
    elif n_shifted == 0:
        md.append("  → best_static_cd는 input length에 robust")
    else:
        md.append("  → workload별 차이 있음")
    md.append("")

    sw_drops = []
    for bw, _, _ in WORKLOADS:
        if bw in base and bw in new and "post_warmup" in new[bw]:
            d = (float(new[bw]["post_warmup"]["best_cd_switch_rate"])
                 - float(base[bw]["post_warmup"]["best_cd_switch_rate"]))
            sw_drops.append((bw, d))
    md.append("### switch_rate input-length sensitivity")
    for bw, d in sw_drops:
        md.append(f"- {bw}: Δswitch_rate = **{d:+.3f}**")
    if all(d < -0.05 for _, d in sw_drops) and len(sw_drops) > 0:
        md.append("  → 3/3 감소, entropy 보고에 input-length sensitivity 명시 필요")
    elif all(abs(d) < 0.05 for _, d in sw_drops):
        md.append("  → switch_rate는 input length에 stable")
    else:
        md.append("  → workload별 차이 있음")
    md.append("")

    # Sprint A recommendation
    md.append("## Sprint A 권고")
    md.append("")
    if neg > 0:
        md.append("- 악화 워크로드 진단 우선, Sprint A 보류")
    elif big == n_total and n_total > 0:
        md.append("- Sprint A pagerank 재시뮬을 **1× + 4× 두 가지로 진행** 권고")
    elif big == 0:
        md.append("- Sprint A는 **1× input만으로 충분**")
    else:
        md.append("- Sprint A는 **1× pagerank만 우선**, 결과 보고 4× 추가 결정")
    md.append("")

    md.append("## Note")
    md.append("이 결과로 H4 단독 효과를 판단. H3c (RSB demote 비대칭)는 별도 진단에서 dominant 결정 — H4는 그 효과를 input length로 amplify/attenuate하는 secondary factor.")

    OUT_MD.write_text("\n".join(md))
    print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
