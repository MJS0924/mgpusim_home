"""
event_log_schema.py — parquet schema + basic statistics reporter.
Usage: python3 event_log_schema.py <path_to_events.parquet>
"""
import sys
import pyarrow.parquet as pq
import pandas as pd

path = sys.argv[1]
print(f"File: {path}")

pf = pq.read_table(path)
df = pf.to_pandas()

print(f"\n=== Schema ===")
for col in df.columns:
    print(f"  {col:<30} {str(df[col].dtype):<15} nulls={df[col].isna().sum()}")

print(f"\n=== Basic Stats ===")
print(f"  Total rows          : {len(df):,}")

if "IsPromotion" in df.columns:
    n_prom = int(df["IsPromotion"].sum())
    n_dem  = len(df) - n_prom
    print(f"  Promotions          : {n_prom:,}")
    print(f"  Demotions           : {n_dem:,}")

if "Time" in df.columns:
    print(f"  Time min            : {df['Time'].min()}")
    print(f"  Time max            : {df['Time'].max()}")
elif "Cycle" in df.columns:
    print(f"  Cycle min           : {df['Cycle'].min():,}")
    print(f"  Cycle max           : {df['Cycle'].max():,}")

print(f"\n=== First 5 rows ===")
print(df.head(5).to_string())

print(f"\n=== Last 5 rows ===")
print(df.tail(5).to_string())

print(f"\n=== Value Counts (all categorical columns) ===")
for col in df.columns:
    if df[col].dtype == object or str(df[col].dtype).startswith("int") or str(df[col].dtype).startswith("uint") or str(df[col].dtype).startswith("bool"):
        vc = df[col].value_counts()
        if len(vc) <= 20:
            print(f"\n  [{col}]")
            for val, cnt in vc.items():
                print(f"    {str(val):<20} {cnt:>8,}")
