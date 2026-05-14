#!/usr/bin/env python3
"""h4_relu_compare.py — Step C-1 50K-window vs 4× input length comparison.

Reads:
  results/oracle_relative_stats.csv  (existing relu stats from 50K window run)
  results/per_window/relu_4x/         (new 4× length CSVs)

Writes:
  results/h4_relu_comparison.csv  — flat comparison rows
  results/h4_relu_step_report.md  — markdown table + classification

Pre-committed thresholds (from plan, do NOT change post-hoc):
  Δcapture < 5%점        → H4 영향 작음, 다음 Step (spmv) 진행
  5%점 ≤ Δcapture < 15%점 → H4 영향 중간, 다음 Step에서 일관성 확인
  Δcapture ≥ 15%점        → H4 영향 큼, paper 결론 변동 가능
  Δcapture < 0  (악화)    → 정지, 추가 진단

(Δcapture is the absolute change in sd_headroom_capture: 4× minus 50K.)
"""

import csv
import importlib.util
import math
import sys
from pathlib import Path

REPO = Path("/root/mgpusim_home")
SCRIPTS = REPO / "scripts"
RESULTS = REPO / "results"

# load oracle_relative_stats.py as a module
spec = importlib.util.spec_from_file_location(
    "ors", SCRIPTS / "oracle_relative_stats.py"
)
ors = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ors)

OUT_CSV = RESULTS / "h4_relu_comparison.csv"
OUT_REPORT = RESULTS / "h4_relu_step_report.md"


def load_relu_baseline() -> dict[str, dict]:
    """Existing relu stats keyed by warmup_variant."""
    path = RESULTS / "oracle_relative_stats.csv"
    out = {}
    with path.open() as f:
        for r in csv.DictReader(f):
            if r["workload"] == "relu":
                out[r["warmup_variant"]] = r
    return out


def main() -> int:
    base = load_relu_baseline()
    if not base:
        print("ERR: no relu rows in oracle_relative_stats.csv", file=sys.stderr)
        return 1

    rows_4x = {}
    for post in (False, True):
        r = ors.compute("relu_4x", post)
        if r is None:
            print(f"ERR: ors.compute('relu_4x', post={post}) returned None",
                  file=sys.stderr)
            return 1
        rows_4x[r["warmup_variant"]] = r

    # produce flat comparison CSV
    fields_to_compare = [
        "n_windows", "best_cd_entropy", "best_cd_switch_rate",
        "sd_oracle_mean", "sd_oracle_p10", "sd_oracle_p50", "sd_oracle_p90",
        "sd_above_oracle_fraction",
        "sd_vs_static_best", "best_static_cd",
        "oracle_headroom", "sd_headroom_capture",
        "sd_speedup_over_static_best_time",
        "static_best_cd_time",
    ]

    out_rows = []
    for variant in ("all_windows", "post_warmup"):
        b = base[variant]; n = rows_4x[variant]
        row = {"warmup_variant": variant}
        for f in fields_to_compare:
            row[f"50K_{f}"] = b.get(f, "")
            row[f"4x_{f}"] = n.get(f, "")
        out_rows.append(row)

    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    print(f"wrote {OUT_CSV}")

    # classification + markdown report
    def fnum(s, fmt=".3f"):
        try:
            return f"{float(s):{fmt}}"
        except Exception:
            return str(s)

    md = ["# Step C-1 H4 input-length 검증 — relu (4× length)", ""]
    md.append("`length=15,360,000` (4× of 3,840,000) × 7 variants. Sequential→parallel batch (max=4) launch.")
    md.append("")
    md.append("Files: `results/per_window/relu_4x/relu_4x_<variant>_per_window.csv`")
    md.append("")

    for variant in ("post_warmup", "all_windows"):
        b = base[variant]
        n = rows_4x[variant]
        md.append(f"## {variant}")
        md.append("")
        md.append("| metric | 50K-window (baseline) | 4× length | Δ |")
        md.append("|---|--:|--:|--:|")

        def cell(field, fmt=".3f"):
            try:
                bv = float(b[field]); nv = float(n[field])
                return (f"| {field} | {bv:{fmt}} | {nv:{fmt}} | "
                        f"{nv - bv:+.3f} |")
            except Exception:
                return f"| {field} | {b[field]} | {n[field]} | (categorical) |"

        for f_ in [
            "n_windows", "best_cd_entropy", "best_cd_switch_rate",
            "sd_oracle_mean", "sd_oracle_p10", "sd_oracle_p50", "sd_oracle_p90",
            "sd_above_oracle_fraction",
            "sd_vs_static_best",
            "oracle_headroom", "sd_headroom_capture",
            "sd_speedup_over_static_best_time",
        ]:
            md.append(cell(f_))
        md.append(f"| best_static_cd (geomean-IPC) | {b['best_static_cd']} | {n['best_static_cd']} | — |")
        md.append(f"| static_best_cd_time          | {b['static_best_cd_time']} | {n['static_best_cd_time']} | — |")
        md.append("")

    # classify by post_warmup Δcapture
    delta_capture = (
        float(rows_4x["post_warmup"]["sd_headroom_capture"])
        - float(base["post_warmup"]["sd_headroom_capture"])
    )
    md.append("## 잠정 분류 (post_warmup 기준)")
    md.append("")
    md.append(f"Δcapture (4× − 50K) = **{delta_capture:+.3f}** (= {delta_capture*100:+.1f}%점)")
    md.append("")
    if delta_capture < 0:
        verdict = "❌ **악화** — 정지, 추가 진단 필요"
        next_step = "Step C-2 진행 보류; CD_6/CD_8 sub-process 또는 RSB state dump 검사"
    elif delta_capture < 0.05:
        verdict = "✅ **H4 영향 작음** (Δ < 5%점) — H3c가 dominant 재확인"
        next_step = "Step C-2 (spmv 4× input) 진행"
    elif delta_capture < 0.15:
        verdict = "⚠️ **H4 영향 중간** (5%점 ≤ Δ < 15%점) — 다음 Step에서 일관성 확인"
        next_step = "Step C-2 (spmv) + Step C-3 (conv2d) 진행 후 종합"
    else:
        verdict = "🔥 **H4 영향 큼** (Δ ≥ 15%점) — paper 결론 변동 가능"
        next_step = "Step C-2 / C-3 우선 진행; SD framing 재검토"
    md.append(f"**Verdict**: {verdict}")
    md.append("")
    md.append(f"**다음 행동**: {next_step}")
    md.append("")
    md.append("**커밋된 임계값** (post-hoc 변경 금지):")
    md.append("- Δ < 5%점 → H4 영향 작음")
    md.append("- 5%점 ≤ Δ < 15%점 → 중간")
    md.append("- Δ ≥ 15%점 → 큼")
    md.append("- Δ < 0 → 악화, 정지")
    md.append("")
    md.append("## Note")
    md.append("이 결과는 **잠정**입니다 (Step C-1 단독). C-1/C-2/C-3 종합 후에만 final 결론 가능.")

    OUT_REPORT.write_text("\n".join(md))
    print(f"wrote {OUT_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
