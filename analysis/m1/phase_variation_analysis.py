"""
phase_variation_analysis.py — phase-level variation of optimal region size.
Usage: python3 phase_variation_analysis.py <events.parquet> [workload_label]
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

N_PHASES = 10

df = pq.read_table(path).to_pandas()
promo = df[df["event_type"] == "promote"].copy().sort_values("time_sec").reset_index(drop=True)
demote = df[df["event_type"] == "demote"].copy()

# Use time as the ordering dimension (all events, sorted)
all_sorted = df.sort_values("time_sec").reset_index(drop=True)

print(f"=== Phase Variation Analysis: {label} ===")
print(f"Total events    : {len(df):,}")
print(f"Promotions      : {len(promo):,}")
print(f"N phases        : {N_PHASES}")

# ── Option 1: time-based equal-width buckets ─────────────────────────────────
t_min, t_max = all_sorted["time_sec"].min(), all_sorted["time_sec"].max()
t_edges = np.linspace(t_min, t_max, N_PHASES + 1)
all_sorted["phase_time"] = pd.cut(all_sorted["time_sec"], bins=t_edges,
                                   labels=range(N_PHASES), include_lowest=True).astype(int)

# ── Option 2: equal-count buckets (on promotions) ───────────────────────────
promo["phase_count"] = pd.qcut(promo.index, q=N_PHASES, labels=range(N_PHASES)).astype(int)

# Map count phases back to time ranges for display
phase_time_ranges = []
for p in range(N_PHASES):
    ph = promo[promo["phase_count"] == p]
    phase_time_ranges.append((ph["time_sec"].min(), ph["time_sec"].max()))

# ── Per-phase analysis (Option 2: equal-count) ──────────────────────────────
print(f"\n=== Per-phase stats (equal-count, promotions only) ===")
print(f"{'Phase':>6} {'Events':>8} {'DomToBank':>10} {'B0%':>6} {'B1%':>6} {'B2%':>6} {'B3%':>6} {'AvgSC':>7}")

phase_stats = []
all_banks = sorted(df["to_bank"].unique())

for p in range(N_PHASES):
    ph = promo[promo["phase_count"] == p]
    n = len(ph)
    if n == 0:
        continue
    dom_bank = ph["to_bank"].mode()[0]
    bank_fracs = {b: len(ph[ph["to_bank"] == b]) / n for b in all_banks}
    avg_sc = ph["sharer_count"].mean()

    fracs_str = "  ".join(f"{100*bank_fracs.get(b,0):.0f}%" for b in sorted(all_banks))
    print(f"  {p:>4}  {n:>8,}  {dom_bank:>10}  " +
          "  ".join(f"{100*bank_fracs.get(b,0):>5.1f}" for b in sorted(all_banks)) +
          f"  {avg_sc:>7.2f}")

    phase_stats.append({
        "phase": p,
        "n_events": n,
        "dom_to_bank": dom_bank,
        "avg_sharer_count": avg_sc,
        **{f"frac_bank_{b}": bank_fracs.get(b, 0) for b in all_banks},
    })

ps = pd.DataFrame(phase_stats)

unique_dom = ps["dom_to_bank"].nunique()
print(f"\n=== Phase Variation Summary ===")
print(f"  Unique dominant ToBank across phases : {unique_dom}")
print(f"  Dominant banks seen                  : {sorted(ps['dom_to_bank'].unique().tolist())}")
print(f"  Phase variation (>= 2 dom banks)     : {'YES' if unique_dom >= 2 else 'NO'}")

# KL divergence between adjacent phases
bank_cols = [c for c in ps.columns if c.startswith("frac_bank_")]
eps = 1e-9
kl_divs = []
for i in range(len(ps) - 1):
    p_dist = ps.iloc[i][bank_cols].values.astype(float) + eps
    q_dist = ps.iloc[i+1][bank_cols].values.astype(float) + eps
    p_dist /= p_dist.sum()
    q_dist /= q_dist.sum()
    kl = float(np.sum(p_dist * np.log(p_dist / q_dist)))
    kl_divs.append(kl)

print(f"\n=== KL Divergence between adjacent phases ===")
for i, kl in enumerate(kl_divs):
    print(f"  Phase {i}→{i+1}: {kl:.4f}")
print(f"  Mean KL     : {np.mean(kl_divs):.4f}")
print(f"  Max KL      : {np.max(kl_divs):.4f}")

BANK_SIZES = {0: "16KB", 1: "4KB", 2: "1KB", 3: "256B", 4: "64B"}

# ── Figure 1: Stacked bar — ToBank distribution per phase ───────────────────
bank_colors = {0: "#1f77b4", 1: "#ff7f0e", 2: "#2ca02c", 3: "#d62728", 4: "#9467bd"}
fig, ax = plt.subplots(figsize=(8, 5))
bottom = np.zeros(len(ps))
for b in sorted(all_banks):
    col = f"frac_bank_{b}"
    if col in ps.columns:
        vals = ps[col].values
        size_str = BANK_SIZES.get(b, "?")
        ax.bar(ps["phase"], vals, bottom=bottom,
               label=f"Bank {b} ({size_str})", color=bank_colors.get(b, "gray"))
        bottom += vals
ax.set_xlabel("Phase (equal-count)")
ax.set_ylabel("Fraction of promotions")
ax.set_title(f"{label}: Phase-level ToBank Distribution")
ax.set_xticks(range(N_PHASES))
ax.legend(loc="upper right", fontsize=9)
plt.tight_layout()
out = os.path.join(fig_dir, f"phase_bank_timeline_{label}.png")
plt.savefig(out, dpi=150)
plt.close()
print(f"\n[figure] {out}")

# ── Figure 2: Dominant ToBank per phase ──────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(ps["phase"], ps["dom_to_bank"], "o-", color="steelblue", linewidth=2, markersize=8)
ax.set_xlabel("Phase")
ax.set_ylabel("Dominant ToBank")
ax.set_title(f"{label}: Dominant ToBank per Phase")
ax.set_xticks(range(N_PHASES))
ax.set_yticks(sorted(all_banks))
ax.set_yticklabels([f"Bank {b} ({BANK_SIZES.get(b,'?')})" for b in sorted(all_banks)])
ax.grid(axis="y", linestyle="--", alpha=0.5)
plt.tight_layout()
out = os.path.join(fig_dir, f"phase_dominant_bank_{label}.png")
plt.savefig(out, dpi=150)
plt.close()
print(f"[figure] {out}")

# ── M1 exit criteria judgment ────────────────────────────────────────────────
print(f"\n=== M1 Exit Criteria Judgment ({label}) ===")
if unique_dom >= 2:
    print(f"  PASS: {unique_dom} distinct dominant banks across {N_PHASES} phases.")
    print(f"  → Phase-level variation in optimal region size CONFIRMED for {label}.")
else:
    print(f"  FAIL: only {unique_dom} dominant bank(s) — no variation.")
    print(f"  → No phase-level variation detected for {label}.")
