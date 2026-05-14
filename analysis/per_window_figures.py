"""per_window_figures.py — visualization for per-window optimal-R analysis.

Usage:
    python per_window_figures.py --workload <name> --opt-dir <dir> --out-dir <dir>

Reads:
    <opt-dir>/<workload>_optimal_R_per_window.csv   (from per_window_optimal_R.py)

Writes 3 figures per workload into <out-dir>/:
    per_window_IPC_comparison_<workload>.png
    best_R_timeline_<workload>.png
    per_window_variation_<workload>.png
"""

import sys
import os
import argparse
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

R_ORDER = ["64B", "256B", "1KB", "4KB", "16KB", "SD"]
R_COLORS = {
    "64B":   "#1f77b4",
    "256B":  "#ff7f0e",
    "1KB":   "#2ca02c",
    "4KB":   "#d62728",
    "16KB":  "#9467bd",
    "SD":    "#8c564b",
}


def ipc_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.endswith("_IPC") and not c.startswith("best")]


def hit_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.endswith("_L2_read_hit_rate")]


def rdma_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.endswith("_RDMA_rate")]


def r_label_from_col(col: str) -> str:
    return col.rsplit("_", 1)[0] if "_" in col else col


def figure1_ipc_comparison(df: pd.DataFrame, workload: str, out_dir: str):
    cols = ipc_cols(df)
    if not cols:
        print(f"[figures] no IPC columns found, skipping figure1")
        return
    fig, ax = plt.subplots(figsize=(12, 5))
    x = df["window_idx"].values

    best_r_series = df["best_R_IPC"] if "best_R_IPC" in df.columns else None

    # Shaded background per best-R region
    if best_r_series is not None:
        prev_r, prev_x = None, 0
        for i, r in enumerate(best_r_series):
            if r != prev_r:
                if prev_r is not None:
                    ax.axvspan(prev_x, i, alpha=0.08,
                               color=R_COLORS.get(prev_r, "#aaaaaa"), lw=0)
                prev_r, prev_x = r, i
        if prev_r is not None:
            ax.axvspan(prev_x, len(best_r_series), alpha=0.08,
                       color=R_COLORS.get(prev_r, "#aaaaaa"), lw=0)

    for col in cols:
        label = r_label_from_col(col)
        color = R_COLORS.get(label, None)
        ax.plot(x, df[col], label=label, color=color, linewidth=1.2)

    ax.set_xlabel("Window index")
    ax.set_ylabel("IPC (instructions / ns)")
    ax.set_title(f"Per-window IPC comparison: {workload}")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    path = os.path.join(out_dir, f"per_window_IPC_comparison_{workload}.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"[figures] → {path}")


def figure2_best_r_timeline(df: pd.DataFrame, workload: str, out_dir: str):
    if "best_R_IPC" not in df.columns:
        print(f"[figures] no best_R_IPC column, skipping figure2")
        return

    labels_present = [r for r in R_ORDER if r in df["best_R_IPC"].values]
    y_map = {r: i for i, r in enumerate(labels_present)}

    fig, ax = plt.subplots(figsize=(12, 4))
    x = df["window_idx"].values
    y = df["best_R_IPC"].map(y_map).values
    ax.step(x, y, where="post", linewidth=1.5, color="#333333")
    ax.set_yticks(range(len(labels_present)))
    ax.set_yticklabels(labels_present)
    ax.set_xlabel("Window index")
    ax.set_title(f"Best R over execution time: {workload}")
    ax.grid(True, axis="x", alpha=0.3)
    plt.tight_layout()
    path = os.path.join(out_dir, f"best_R_timeline_{workload}.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"[figures] → {path}")


def figure3_variation(df: pd.DataFrame, workload: str, out_dir: str):
    ipc = ipc_cols(df)
    hit = hit_cols(df)
    rdma = rdma_cols(df)
    if not ipc:
        print(f"[figures] no IPC columns, skipping figure3")
        return

    n_sub = sum(bool(c) for c in [ipc, hit, rdma])
    fig, axes = plt.subplots(n_sub, 1, figsize=(12, 4 * n_sub), sharex=True)
    if n_sub == 1:
        axes = [axes]

    ax_idx = 0
    x = df["window_idx"].values

    def _plot_group(cols, ax, ylabel):
        for col in cols:
            label = r_label_from_col(col)
            color = R_COLORS.get(label, None)
            ax.plot(x, df[col], label=label, color=color, linewidth=1.2)
        ax.set_ylabel(ylabel)
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(True, alpha=0.3)

    if ipc:
        _plot_group(ipc, axes[ax_idx], "IPC (inst/ns)")
        ax_idx += 1
    if hit:
        _plot_group(hit, axes[ax_idx], "L2 read hit rate")
        ax_idx += 1
    if rdma:
        _plot_group(rdma, axes[ax_idx], "RDMA rate (B/ns)")
        ax_idx += 1

    axes[-1].set_xlabel("Window index")
    fig.suptitle(f"Per-window metric variation: {workload}", y=1.01)
    plt.tight_layout()
    path = os.path.join(out_dir, f"per_window_variation_{workload}.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[figures] → {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", required=True)
    parser.add_argument("--opt-dir", required=True,
                        help="Directory containing optimal_R_per_window.csv")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    csv_path = os.path.join(args.opt_dir, f"{args.workload}_optimal_R_per_window.csv")
    if not os.path.exists(csv_path):
        print(f"[figures] ERROR: {csv_path} not found", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(csv_path)
    figure1_ipc_comparison(df, args.workload, args.out_dir)
    figure2_best_r_timeline(df, args.workload, args.out_dir)
    figure3_variation(df, args.workload, args.out_dir)


if __name__ == "__main__":
    main()
