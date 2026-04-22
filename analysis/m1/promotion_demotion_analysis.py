"""
promotion_demotion_analysis.py — promotion/demotion pattern analysis.
Usage: python3 promotion_demotion_analysis.py <events.parquet> [workload_label]
"""
import sys
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pyarrow.parquet as pq

path = sys.argv[1]
label = sys.argv[2] if len(sys.argv) > 2 else os.path.basename(path).replace("_events.parquet", "")
fig_dir = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(fig_dir, exist_ok=True)

df = pq.read_table(path).to_pandas()
promo = df[df["event_type"] == "promote"].copy()
demote = df[df["event_type"] == "demote"].copy()

print(f"=== Promotion/Demotion Analysis: {label} ===")
print(f"Total events    : {len(df):,}")
print(f"Promotions      : {len(promo):,}  ({100*len(promo)/len(df):.1f}%)")
print(f"Demotions       : {len(demote):,}  ({100*len(demote)/len(df):.1f}%)")
print(f"Prom/Dem ratio  : {len(promo)/max(1,len(demote)):.1f}x")

# ── Bank transition matrix ───────────────────────────────────────────────────
banks = sorted(df["from_bank"].unique().tolist() + df["to_bank"].unique().tolist())
banks = sorted(set(banks))

print(f"\n=== Promotion: FromBank → ToBank transition matrix ===")
prom_matrix = pd.crosstab(promo["from_bank"], promo["to_bank"])
print(prom_matrix.to_string())

print(f"\n=== Demotion: FromBank → ToBank transition matrix ===")
if len(demote) > 0:
    dem_matrix = pd.crosstab(demote["from_bank"], demote["to_bank"])
    print(dem_matrix.to_string())
else:
    print("  (no demotions)")

# ── Promotion bank frequencies ───────────────────────────────────────────────
print(f"\n=== Promotion: FromBank frequency ===")
fb = promo["from_bank"].value_counts().sort_index()
for b, c in fb.items():
    print(f"  Bank {b}: {c:>8,}  ({100*c/len(promo):.1f}%)")

print(f"\n=== Promotion: ToBank frequency ===")
tb = promo["to_bank"].value_counts().sort_index()
for b, c in tb.items():
    print(f"  Bank {b}: {c:>8,}  ({100*c/len(promo):.1f}%)")

# ── SharerCount distribution ─────────────────────────────────────────────────
print(f"\n=== Promotion: SharerCount distribution ===")
sc = promo["sharer_count"].value_counts().sort_index()
for s, c in sc.items():
    print(f"  SharerCount={s}: {c:>8,}  ({100*c/len(promo):.1f}%)")

shared_ratio = len(promo[promo["sharer_count"] >= 2]) / max(1, len(promo))
private_ratio = len(promo[promo["sharer_count"] == 1]) / max(1, len(promo))
print(f"\n  Multi-GPU shared (sharer>=2): {100*shared_ratio:.1f}%")
print(f"  Private         (sharer==1): {100*private_ratio:.1f}%")

# ── Utilization distribution ─────────────────────────────────────────────────
print(f"\n=== Promotion: Utilization stats ===")
print(f"  mean={promo['utilization'].mean():.3f}  "
      f"median={promo['utilization'].median():.3f}  "
      f"min={promo['utilization'].min():.3f}  "
      f"max={promo['utilization'].max():.3f}")

if len(demote) > 0:
    print(f"\n=== Demotion: Utilization stats ===")
    print(f"  mean={demote['utilization'].mean():.3f}  "
          f"median={demote['utilization'].median():.3f}  "
          f"min={demote['utilization'].min():.3f}  "
          f"max={demote['utilization'].max():.3f}")

# ── Figure 1: Bank transition heatmap ────────────────────────────────────────
all_banks = sorted(set(df["from_bank"].tolist() + df["to_bank"].tolist()))
mat = np.zeros((len(all_banks), len(all_banks)), dtype=int)
for _, row in promo.iterrows():
    if row["from_bank"] in all_banks and row["to_bank"] in all_banks:
        i = all_banks.index(row["from_bank"])
        j = all_banks.index(row["to_bank"])
        mat[i, j] += 1

BANK_SIZES = {0: "16KB", 1: "4KB", 2: "1KB", 3: "256B", 4: "64B"}

def bank_label(b):
    return f"Bank {b} ({BANK_SIZES.get(b, '?')})"

fig, ax = plt.subplots(figsize=(7, 6))
im = ax.imshow(mat, cmap="Blues", aspect="auto")
ax.set_xticks(range(len(all_banks)))
ax.set_yticks(range(len(all_banks)))
ax.set_xticklabels([bank_label(b) for b in all_banks], rotation=30, ha="right")
ax.set_yticklabels([bank_label(b) for b in all_banks])
ax.set_xlabel("To Bank")
ax.set_ylabel("From Bank")
ax.set_title(f"{label}: Promotion FromBank→ToBank Heatmap")
plt.colorbar(im, ax=ax, label="Count")
for i in range(len(all_banks)):
    for j in range(len(all_banks)):
        if mat[i, j] > 0:
            ax.text(j, i, f"{mat[i,j]:,}", ha="center", va="center",
                    fontsize=8, color="white" if mat[i,j] > mat.max()*0.5 else "black")
plt.tight_layout()
out = os.path.join(fig_dir, f"bank_transition_heatmap_{label}.png")
plt.savefig(out, dpi=150)
plt.close()
print(f"\n[figure] {out}")

# ── Figure 2: SharerCount histogram ─────────────────────────────────────────
fig, ax = plt.subplots(figsize=(6, 4))
sc_all = df["sharer_count"].value_counts().sort_index()
ax.bar([str(k) for k in sc_all.index], sc_all.values, color="steelblue", edgecolor="black")
ax.set_xlabel("SharerCount")
ax.set_ylabel("Events")
ax.set_title(f"{label}: SharerCount Distribution (all events)")
for i, (k, v) in enumerate(sc_all.items()):
    ax.text(i, v + sc_all.max()*0.01, f"{v:,}", ha="center", fontsize=9)
plt.tight_layout()
out = os.path.join(fig_dir, f"sharer_count_distribution_{label}.png")
plt.savefig(out, dpi=150)
plt.close()
print(f"[figure] {out}")

# ── Figure 3: Utilization histogram for demotions ──────────────────────────
if len(demote) > 0:
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(demote["utilization"], bins=20, color="tomato", edgecolor="black")
    ax.set_xlabel("Utilization at demotion")
    ax.set_ylabel("Count")
    ax.set_title(f"{label}: Demotion Utilization Distribution")
    plt.tight_layout()
    out = os.path.join(fig_dir, f"utilization_distribution_{label}.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"[figure] {out}")
