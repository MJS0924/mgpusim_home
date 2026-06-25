#!/usr/bin/env python3
"""
SuperDirectory ablation 그림 (fig_a 포맷·색: blue #4477AA / red #E63946).

Fig 1 (fig_banklookup_per_workload):
    bank lookup 횟수 = Σ_N N·(BankChecked-N), 전 GPU 합산.
    BEC(SD) vs A0(no RSB/CBF), workload 별, BEC 기준 normalize (BEC=1.0).

Fig 2+3 (fig_perbank_a0_vs_a3, 한 그림 가로배치, 전체폭 8.75cm):
    비교 = A0(라벨 "BEC") vs A3(라벨 "no promote@Evict"), 둘 다 A0 기준 normalize, log scale.
    전 GPU·전 워크로드 합산.
    (2) Invalidation by eviction  — InvalidateByEviction-b, bank 별.
    (3) UpdateEntry + Promotion    — (UpdateEntry-b + InvalidateByPromotion-b), bank 별.

집계: A0/A3/SD 모두 있는 9 워크로드. lenet/minerva 제외.
"""
import csv
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import FixedLocator, NullLocator
import matplotlib.colors as mcolors
import numpy as np

plt.rcParams.update({
    "font.size": 9, "axes.linewidth": 0.6,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "savefig.dpi": 300, "pdf.fonttype": 42, "ps.fonttype": 42,
})
BLUE, RED = "#4477AA", "#E63946"        # fig_a 의 cool/hot 양끝
EDGE, LW = "black", 0.25
CM = 1 / 2.54
COL_W_IN = 8.5 * CM
W_8_75 = 8.75 * CM

ROOT = Path("/root/mgpusim_home")
FIGDIR = ROOT / "results_ablation/analysis/plots"
NBANKS = 5
WL_ORDER = ["conv2d", "fir", "im2col", "matrixtranspose", "stencil2d",
            "matrixmultiplication", "pagerank", "spmv", "bfs"]
ABBR = {"conv2d": "C2D", "fir": "FIR", "im2col": "I2C", "matrixtranspose": "MT",
        "stencil2d": "ST2D", "matrixmultiplication": "MM", "pagerank": "PR",
        "spmv": "SpMV", "bfs": "BFS"}

def db_sd(wl): return ROOT / f"results/superdirectory/rawdata/sql/{wl}_superdirectory.sqlite3"
def db_a0(wl): return ROOT / f"results_ablation/A0_no_promote_at_evict/rawdata/sql/{wl}_a0.sqlite3"
def db_a3(wl): return ROOT / f"results_ablation/A3_no_promote_at_evict/rawdata/sql/{wl}_a3.sqlite3"

def cohdir(db):
    c = sqlite3.connect(str(db)); cur = c.cursor()
    cur.execute("SELECT What, SUM(CAST(Value AS REAL)) FROM cohDir_metrics GROUP BY What")
    d = {w: (v or 0.0) for w, v in cur.fetchall()}; c.close(); return d

def bank_lookups(d):
    return sum(int(k.rsplit("-", 1)[1]) * v
               for k, v in d.items() if k.startswith("BankChecked - "))

def perbank(d, metric):
    return np.array([d.get(f"{metric} - {b}", 0.0) for b in range(NBANKS)])

def hide_gridline_at(ax, y_value=1.0):
    """y=y_value 의 점선 gridline 제거(같은 위치 solid axhline 과 겹침 방지). grid() 뒤 호출."""
    locs = ax.yaxis.get_majorticklocs()
    gls = ax.yaxis.get_gridlines()
    for i in range(min(len(locs), len(gls))):
        if abs(locs[i] - y_value) < 1e-9:
            gls[i].set_visible(False)
            gls[i].set_linewidth(0)

sd = {wl: cohdir(db_sd(wl)) for wl in WL_ORDER}
a0 = {wl: cohdir(db_a0(wl)) for wl in WL_ORDER}
a3 = {wl: cohdir(db_a3(wl)) for wl in WL_ORDER}

# ════════ Fig 1 — bank lookups per workload, BEC vs A0, norm to BEC ════════
bec_lu = np.array([bank_lookups(sd[wl]) for wl in WL_ORDER])
a0_lu  = np.array([bank_lookups(a0[wl]) for wl in WL_ORDER])
a0_norm = a0_lu / bec_lu

fig, ax = plt.subplots(figsize=(COL_W_IN, 2.0))
GAP, bw, cur, centers = 0.8, 1.0, 0.0, []
for i, wl in enumerate(WL_ORDER):
    ax.bar(cur + 0, 1.0, bw, color=BLUE, edgecolor=EDGE, linewidth=LW)
    ax.bar(cur + 1, a0_norm[i], bw, color=RED, edgecolor=EDGE, linewidth=LW)
    centers.append(cur + 0.5); cur += 2 + GAP
ax.axhline(1.0, color="black", linewidth=0.4, zorder=3)
ax.set_xticks(centers)
ax.set_xticklabels([ABBR[w] for w in WL_ORDER], rotation=45, ha="right", rotation_mode="anchor")
ax.set_ylabel(r"bank lookups / BEC")
ax.set_xlim(-0.7, cur - GAP - 0.3); ax.margins(y=0.12)
ax.grid(axis="y", linestyle="--", alpha=0.4)
hide_gridline_at(ax, 1.0)  # 1.0 의 점선 제거(solid axhline 과 겹침)
leg = [Patch(facecolor=BLUE, edgecolor=EDGE, linewidth=LW, label="BEC"),
       Patch(facecolor=RED, edgecolor=EDGE, linewidth=LW, label="no RSB/CBF")]
ax.legend(handles=leg, loc="lower center", bbox_to_anchor=(0.5, 1.01),
          ncol=2, frameon=False, handlelength=0.9, handletextpad=0.3,
          columnspacing=0.8, borderaxespad=0.0)
fig.subplots_adjust(left=0.13, right=0.97, top=0.88, bottom=0.24)
fig.savefig(FIGDIR / "fig_banklookup_per_workload.pdf")
fig.savefig(FIGDIR / "fig_banklookup_per_workload.png")
plt.close(fig)

# ════════ Fig 2+3 — BEC(SD) vs A3, per-bank, norm to BEC(SD), log ════════
inv_sd = sum((perbank(sd[wl], "InvalidateByEviction") for wl in WL_ORDER), np.zeros(NBANKS))
inv_a3 = sum((perbank(a3[wl], "InvalidateByEviction") for wl in WL_ORDER), np.zeros(NBANKS))
# Bank activation = per-bank coverage (per-window CSV cur_sd_coverage_cachelines):
# GPU 합산 → window 평균 → 전 워크로드 합산.
def coverage_perbank(path):
    if not path.exists():
        return np.zeros(NBANKS)
    cols = {b: [f"cur_sd_coverage_cachelines_GPU{g}_SuperDir_bank{b}" for g in (1, 2, 3, 4)]
            for b in range(NBANKS)}
    rows = list(csv.DictReader(open(path)))
    if not rows:
        return np.zeros(NBANKS)
    return np.array([np.mean([sum(float(r.get(c, 0) or 0) for c in cols[b]) for r in rows])
                     for b in range(NBANKS)])

def pw_path(v, wl):
    return (ROOT / f"results/per_window/{wl}/{wl}_SD_per_window.csv" if v == "SD"
            else ROOT / f"results_ablation/per_window/{wl}/{wl}_{v}_per_window.csv")

cov_sd = sum((coverage_perbank(pw_path("SD", wl)) for wl in WL_ORDER), np.zeros(NBANKS))
cov_a3 = sum((coverage_perbank(pw_path("a3", wl)) for wl in WL_ORDER), np.zeros(NBANKS))

def norm_to_sd_b4(sdv, a3v):
    """SD 의 bank4 값(단일 기준)으로 정규화. BEC=SD 분포(SD_b4=1.0), A3=A3/SD_b4."""
    ref = sdv[-1] if sdv[-1] > 0 else 1.0
    base = np.where(sdv > 0, sdv / ref, np.nan)
    rel = np.where(a3v > 0, a3v / ref, np.nan)
    return base, rel

banks = np.arange(NBANKS); w = 0.4
# (title, base, rel, ylim, yticks, ylabel) — 두 지표는 스케일이 달라 패널별 y축.
panels = [
    ("Inv. by eviction", *norm_to_sd_b4(inv_sd, inv_a3),
     (0.05, 2.0), [0.1, 1], r"count / SD$_{b4}$"),
    ("Bank activation", *norm_to_sd_b4(cov_sd, cov_a3),
     (0.5, 40.0), [1, 10], r"coverage / SD$_{b4}$"),
]

# 폭 8.5cm(=COL_W_IN, fig_a 동일). 폰트는 모두 rcParams font.size=9(=fig_a) 상속.
# 두 패널에 동일한 x축(xlim/ticks/labels)·y축을 명시적으로 설정해 형식 통일.
fig, axes = plt.subplots(1, 2, figsize=(COL_W_IN, 1.9))
for ax, (title, base, rel, ylim, yt, ylab) in zip(axes, panels):
    ax.bar(banks - w/2, base, w, color=BLUE, edgecolor=EDGE, linewidth=LW, label="BEC")
    ax.bar(banks + w/2, rel, w, color=RED, edgecolor=EDGE, linewidth=LW, label="no promote@Evict")
    ax.set_yscale("log")
    ax.axhline(1.0, color="black", linewidth=0.4, zorder=1)
    ax.set_title(title, pad=2)
    ax.set_xlim(-0.6, 4.6)
    ax.set_xticks(banks)
    ax.set_xticklabels([f"b{b}" for b in banks])
    ax.set_xlabel("bank", labelpad=1)
    ax.set_ylim(*ylim)
    ax.yaxis.set_major_locator(FixedLocator(yt))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.set_yticklabels([f"{t:g}" for t in yt])
    ax.set_ylabel(ylab, labelpad=1)
    ax.grid(axis="y", which="major", linestyle="--", alpha=0.35)
    hide_gridline_at(ax, 1.0)  # 1.0 의 점선 제거(solid axhline 과 겹침)
    ax.tick_params(length=2)
# fig_a 와 동일한 범례 스타일(폰트 9, frameon=False, 동일 spacing).
fig.legend(handles=[Patch(facecolor=BLUE, edgecolor=EDGE, linewidth=LW, label="BEC"),
                    Patch(facecolor=RED, edgecolor=EDGE, linewidth=LW, label="no promote@Evict")],
           loc="upper center", bbox_to_anchor=(0.5, 1.0), ncol=2, frameon=False,
           handlelength=0.8, handletextpad=0.25, columnspacing=0.6, borderaxespad=0.0)
fig.subplots_adjust(left=0.13, right=0.98, top=0.74, bottom=0.21, wspace=0.55)
fig.savefig(FIGDIR / "fig_perbank_bec_vs_a3.pdf")
fig.savefig(FIGDIR / "fig_perbank_bec_vs_a3.png")
plt.close(fig)

# ════════ Fig 4 — Bank activation(coverage) per workload, BEC(컬러) + A3(얇은 흰 막대 overlay) ════════
cov_wl = {wl: coverage_perbank(pw_path("SD", wl)) for wl in WL_ORDER}
cov_a3_wl = {wl: coverage_perbank(pw_path("a3", wl)) for wl in WL_ORDER}
bank_cmap = mcolors.LinearSegmentedColormap.from_list("br", [BLUE, RED])
bank_colors = [bank_cmap(b / (NBANKS - 1)) for b in range(NBANKS)]

fig, ax = plt.subplots(figsize=(COL_W_IN, 2.0))
GAP, bw, cur, centers = 0.8, 1.0, 0.0, []
for wl in WL_ORDER:
    c, a = cov_wl[wl], cov_a3_wl[wl]
    for b in range(NBANKS):
        # BEC: bank 색 풀 막대
        ax.bar(cur + b, c[b] if c[b] > 0 else np.nan, bw,
               color=bank_colors[b], edgecolor=EDGE, linewidth=LW)
        # A3: 얇은 흰 막대 overlay (fig_b 의 'Write total' 스타일, 같은 y축)
        ax.bar(cur + b, a[b] if a[b] > 0 else np.nan, 0.5,
               color="white", edgecolor="black", linewidth=0.5, zorder=5)
    centers.append(cur + (NBANKS - 1) / 2.0); cur += NBANKS + GAP
ax.set_yscale("log")
ax.set_xticks(centers)
ax.set_xticklabels([ABBR[w] for w in WL_ORDER], rotation=45, ha="right", rotation_mode="anchor")
ax.set_ylabel("coverage (cachelines)")
ax.set_xlim(-0.7, cur - GAP - 0.3)
ax.set_ylim(20, 2e6)
ax.yaxis.set_major_locator(FixedLocator([1e2, 1e4, 1e6]))
ax.yaxis.set_minor_locator(NullLocator())
ax.set_yticklabels([r"$10^2$", r"$10^4$", r"$10^6$"])
ax.grid(axis="y", linestyle="--", alpha=0.4)
leg = [Patch(facecolor=bank_colors[b], edgecolor=EDGE, linewidth=LW, label=f"b{b}")
       for b in range(NBANKS)]
leg.append(Patch(facecolor="white", edgecolor="black", linewidth=0.6, label="A3"))
ax.legend(handles=leg, loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=NBANKS + 1,
          frameon=False, handlelength=0.8, handletextpad=0.25,
          columnspacing=0.5, borderaxespad=0.0)
fig.subplots_adjust(left=0.14, right=0.97, top=0.88, bottom=0.24)
fig.savefig(FIGDIR / "fig_bankactivation_per_workload.pdf")
fig.savefig(FIGDIR / "fig_bankactivation_per_workload.png")
plt.close(fig)

# ════════ Fig 5 — coverage A3/BEC 비율 per workload (BEC vs A3 차이) ════════
# cov_a3_wl 은 Fig 4 에서 계산됨
fig, ax = plt.subplots(figsize=(COL_W_IN, 2.0))
GAP, bw, cur, centers = 0.8, 1.0, 0.0, []
for wl in WL_ORDER:
    sdc, a3c = cov_wl[wl], cov_a3_wl[wl]
    for b in range(NBANKS):
        r = a3c[b] / sdc[b] if sdc[b] > 0 else np.nan  # BEC=0 인 bank 은 막대 없음
        ax.bar(cur + b, r, bw, color=bank_colors[b], edgecolor=EDGE, linewidth=LW)
    centers.append(cur + (NBANKS - 1) / 2.0); cur += NBANKS + GAP
ax.set_yscale("log")
ax.axhline(1.0, color="black", linewidth=0.5, zorder=3)  # A3=BEC 기준선
ax.set_xticks(centers)
ax.set_xticklabels([ABBR[w] for w in WL_ORDER], rotation=45, ha="right", rotation_mode="anchor")
ax.set_ylabel(r"coverage  A3 / BEC")
ax.set_xlim(-0.7, cur - GAP - 0.3)
ax.set_ylim(0.2, 10)
ax.yaxis.set_major_locator(FixedLocator([0.5, 1, 2, 5]))
ax.yaxis.set_minor_locator(NullLocator())
ax.set_yticklabels(["0.5", "1", "2", "5"])
ax.grid(axis="y", linestyle="--", alpha=0.4)
hide_gridline_at(ax, 1.0)
leg = [Patch(facecolor=bank_colors[b], edgecolor=EDGE, linewidth=LW, label=f"b{b}")
       for b in range(NBANKS)]
ax.legend(handles=leg, loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=NBANKS,
          frameon=False, handlelength=0.8, handletextpad=0.25,
          columnspacing=0.5, borderaxespad=0.0)
fig.subplots_adjust(left=0.14, right=0.97, top=0.88, bottom=0.24)
fig.savefig(FIGDIR / "fig_coverage_a3_vs_bec_per_workload.pdf")
fig.savefig(FIGDIR / "fig_coverage_a3_vs_bec_per_workload.png")
plt.close(fig)

with open(FIGDIR / "fig_banklookup_per_workload_table.csv", "w", newline="") as f:
    wr = csv.writer(f); wr.writerow(["workload", "BEC_lookups", "A0_lookups", "A0/BEC"])
    for i, wl in enumerate(WL_ORDER):
        wr.writerow([wl, int(bec_lu[i]), int(a0_lu[i]), round(a0_norm[i], 4)])
with open(FIGDIR / "fig_perbank_bec_vs_a3_table.csv", "w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow(["panel", "variant"] + [f"b{b}" for b in range(NBANKS)])
    wr.writerow(["InvByEvict", "BEC(SD)"] + [int(x) for x in inv_sd])
    wr.writerow(["InvByEvict", "A3"] + [int(x) for x in inv_a3])
    wr.writerow(["Coverage", "BEC(SD)"] + [int(x) for x in cov_sd])
    wr.writerow(["Coverage", "A3"] + [int(x) for x in cov_a3])

print("Fig1 A0/BEC per wl:", {ABBR[w]: round(a0_norm[i], 2) for i, w in enumerate(WL_ORDER)})
print("P1 InvByEvict (norm SD_b4) BEC:", [round(x, 3) for x in inv_sd / (inv_sd[-1] or 1)],
      "A3:", [round(x, 3) for x in inv_a3 / (inv_sd[-1] or 1)])
print("P2 Coverage   (norm SD_b4) BEC:", [round(x, 2) for x in cov_sd / (cov_sd[-1] or 1)],
      "A3:", [round(x, 2) for x in cov_a3 / (cov_sd[-1] or 1)])
print(f"written to {FIGDIR}")
