"""per_window_analysis.py — compute per-window delta metrics from cumulative CSV.

Usage:
    python per_window_analysis.py <input_csv> [<output_csv>]

If output_csv is omitted, writes <stem>_delta.csv next to the input file.
"""

import sys
import os
import pandas as pd

CUM_COLS = [
    "cum_instructions",
    "cum_L2_read_hit", "cum_L2_read_miss",
    "cum_L2_write_hit", "cum_L2_write_miss",
    "cum_L2_remote_read_hit", "cum_L2_remote_read_miss",
    "cum_L2_EvictValid", "cum_L2_EvictInvalid",
    "cum_L2_InvalidateValid", "cum_L2_InvalidateInvalid",
    "cum_L2_InvalidateValid_Write", "cum_L2_InvalidateInvalid_Write",
    "cum_L2_InvalidateValid_Evict", "cum_L2_InvalidateInvalid_Evict",
    "cum_RDMA_read_bytes", "cum_RDMA_write_bytes", "cum_RDMA_inv_bytes",
]


def compute_deltas(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["window_idx"] = df["window_idx"]
    out["sim_time_ns_start"] = df["sim_time_ns"].shift(1, fill_value=0.0)
    out["sim_time_ns_end"] = df["sim_time_ns"]

    for col in CUM_COLS:
        if col not in df.columns:
            continue
        short = col[len("cum_"):]  # strip "cum_" prefix
        out[short] = df[col].diff().fillna(df[col]).astype("int64")

    dt = (out["sim_time_ns_end"] - out["sim_time_ns_start"]).replace(0, float("nan"))

    # IPC (instructions per ns)
    out["IPC"] = out["instructions"] / dt

    # L2 hit rates
    read_total = out["L2_read_hit"] + out["L2_read_miss"]
    out["L2_read_hit_rate"] = (out["L2_read_hit"] / read_total.replace(0, float("nan"))).round(4)

    write_total = out["L2_write_hit"] + out["L2_write_miss"]
    out["L2_write_hit_rate"] = (out["L2_write_hit"] / write_total.replace(0, float("nan"))).round(4)

    remote_total = out["L2_remote_read_hit"] + out["L2_remote_read_miss"]
    out["L2_remote_hit_rate"] = (out["L2_remote_read_hit"] / remote_total.replace(0, float("nan"))).round(4)

    # RDMA bandwidth (bytes/ns)
    rdma_total = out["RDMA_read_bytes"] + out["RDMA_write_bytes"] + out["RDMA_inv_bytes"]
    out["RDMA_rate_bytes_per_ns"] = (rdma_total / dt).round(4)

    # Invalidation rate (per instruction)
    out["invalidation_rate"] = (
        out["L2_InvalidateValid"] / out["instructions"].replace(0, float("nan"))
    ).round(6)

    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    in_path = sys.argv[1]
    if len(sys.argv) >= 3:
        out_path = sys.argv[2]
    else:
        stem, _ = os.path.splitext(in_path)
        out_path = stem + "_delta.csv"

    df = pd.read_csv(in_path)
    result = compute_deltas(df)
    result.to_csv(out_path, index=False)
    print(f"[per_window_analysis] {len(result)} windows → {out_path}")


if __name__ == "__main__":
    main()
