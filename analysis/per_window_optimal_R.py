"""per_window_optimal_R.py — cross-R comparison to find optimal region size per window.

Usage:
    python per_window_optimal_R.py --workload <name> --delta-dir <dir> --out-dir <dir>

Expects per_window_analysis.py output files named:
    <workload>_CD_<R>_per_window_delta.csv   for R in 0..4
    <workload>_SD_per_window_delta.csv        (optional)

R label mapping (CoherenceUnitSize index → human-readable):
    CD_0 → 64B
    CD_1 → 256B
    CD_2 → 1KB
    CD_3 → 4KB
    CD_4 → 16KB
"""

import sys
import os
import argparse
import pandas as pd

R_LABELS = {
    "CD_0": "64B",
    "CD_1": "256B",
    "CD_2": "1KB",
    "CD_3": "4KB",
    "CD_4": "16KB",
    "SD": "SD",
}

METRIC_COLS = {
    "IPC": "IPC",
    "L2_read_hit_rate": "L2_read_hit_rate",
    "RDMA_rate_bytes_per_ns": "RDMA_rate",
    "invalidation_rate": "invalidation_rate",
}


def load_deltas(delta_dir: str, workload: str) -> dict[str, pd.DataFrame]:
    dfs = {}
    for key in R_LABELS:
        fname = f"{workload}_{key}_per_window_delta.csv"
        path = os.path.join(delta_dir, fname)
        if os.path.exists(path):
            dfs[key] = pd.read_csv(path)
    if not dfs:
        raise FileNotFoundError(
            f"No delta CSVs found for workload '{workload}' in {delta_dir}"
        )
    return dfs


def align_windows(dfs: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    max_win = min(len(df) for df in dfs.values())
    return {k: df.iloc[:max_win].reset_index(drop=True) for k, df in dfs.items()}


def build_comparison(dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    keys = list(dfs.keys())
    n_win = len(next(iter(dfs.values())))
    rows = []
    for i in range(n_win):
        row = {"window_idx": i}
        for key in keys:
            label = R_LABELS.get(key, key)
            df = dfs[key]
            if i >= len(df):
                for col in METRIC_COLS:
                    row[f"{label}_{col}"] = float("nan")
                continue
            for col, short in METRIC_COLS.items():
                val = df.at[i, col] if col in df.columns else float("nan")
                row[f"{label}_{short}"] = val

        # Best R by IPC
        ipc_vals = {k: dfs[k].at[i, "IPC"] if i < len(dfs[k]) and "IPC" in dfs[k].columns
                    else float("nan") for k in keys}
        best_ipc = max(ipc_vals, key=lambda k: ipc_vals[k] if not pd.isna(ipc_vals[k]) else -1)
        row["best_R_IPC"] = R_LABELS.get(best_ipc, best_ipc)

        # Best R by L2 read hit rate
        hit_vals = {k: dfs[k].at[i, "L2_read_hit_rate"]
                    if i < len(dfs[k]) and "L2_read_hit_rate" in dfs[k].columns
                    else float("nan") for k in keys}
        best_hit = max(hit_vals, key=lambda k: hit_vals[k] if not pd.isna(hit_vals[k]) else -1)
        row["best_R_L2_hit"] = R_LABELS.get(best_hit, best_hit)

        rows.append(row)

    return pd.DataFrame(rows)


def write_summary(df: pd.DataFrame, workload: str, out_dir: str, keys: list[str]) -> str:
    total = len(df)
    ipc_dist = df["best_R_IPC"].value_counts()
    hit_dist = df["best_R_L2_hit"].value_counts()
    n_changed_ipc = (df["best_R_IPC"] != df["best_R_IPC"].shift()).sum()

    lines = [
        f"# Per-Window Optimal R Summary: {workload}",
        "",
        f"Total windows: {total}",
        f"Configs compared: {', '.join(R_LABELS.get(k, k) for k in keys)}",
        "",
        "## Best R by IPC (window count / %)",
    ]
    for r, cnt in ipc_dist.items():
        lines.append(f"  {r}: {cnt} ({cnt/total*100:.1f}%)")
    lines += [
        f"  Windows where best R changes: {n_changed_ipc}",
        "",
        "## Best R by L2 read hit rate (window count / %)",
    ]
    for r, cnt in hit_dist.items():
        lines.append(f"  {r}: {cnt} ({cnt/total*100:.1f}%)")

    # IPC gap between best and worst per window
    ipc_cols = [f"{R_LABELS.get(k,k)}_IPC" for k in keys if f"{R_LABELS.get(k,k)}_IPC" in df.columns]
    if ipc_cols:
        ipc_mat = df[ipc_cols].dropna()
        if not ipc_mat.empty:
            gap = ipc_mat.max(axis=1) - ipc_mat.min(axis=1)
            lines += [
                "",
                "## IPC gap (best − worst per window)",
                f"  max: {gap.max():.4f}",
                f"  mean: {gap.mean():.4f}",
                f"  median: {gap.median():.4f}",
            ]

    md_path = os.path.join(out_dir, f"{workload}_optimal_R_summary.md")
    with open(md_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return md_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", required=True)
    parser.add_argument("--delta-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    dfs = load_deltas(args.delta_dir, args.workload)
    dfs = align_windows(dfs)
    comparison = build_comparison(dfs)

    csv_path = os.path.join(args.out_dir, f"{args.workload}_optimal_R_per_window.csv")
    comparison.to_csv(csv_path, index=False)
    print(f"[per_window_optimal_R] {len(comparison)} windows → {csv_path}")

    md_path = write_summary(comparison, args.workload, args.out_dir, list(dfs.keys()))
    print(f"[per_window_optimal_R] summary → {md_path}")


if __name__ == "__main__":
    main()
