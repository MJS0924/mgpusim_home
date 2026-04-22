# Promotion/Demotion Analysis — Matmul

## Summary

| Metric | Value |
|--------|-------|
| Total events | 38,510 |
| Promotions | 38,435 (99.8%) |
| Demotions | 75 (0.2%) |
| Prom/Dem ratio | 512.5× |
| Multi-GPU shared promotions (sharer≥2) | 5,364 (14.0%) |
| Private promotions (sharer=1) | 33,071 (86.0%) |
| Promotion utilization (mean) | 1.000 |
| Demotion utilization (mean) | 0.400 |

## Bank Transition Matrix (Promotions)

All promotions are **strictly diagonal** — each promotion raises exactly one bank level:

| From\To | Bank 0 (16KB) | Bank 1 (4KB) | Bank 2 (1KB) | Bank 3 (256B) |
|---------|--------|--------|--------|--------|
| Bank 1 (4KB) | 452 | — | — | — |
| Bank 2 (1KB) | — | 1,790 | — | — |
| Bank 3 (256B) | — | — | 7,194 | — |
| Bank 4 (64B) | — | — | — | 28,999 |

**Dominant path**: Bank 4 (64B) → Bank 3 (256B) — 75.4% of all promotions, **4× region expansion**

## Bank Transition Matrix (Demotions)

| From\To | Bank 2 (1KB) | Bank 3 (256B) | Bank 4 (64B) |
|---------|--------|--------|--------|
| Bank 1 (4KB) | 6 | — | — |
| Bank 2 (1KB) | — | 18 | — |
| Bank 3 (256B) | — | — | 51 |

Demotions also strictly diagonal (one level down). Most: Bank 3 (256B) → Bank 4 (64B) (68% of demotions).

## SharerCount Distribution

| SharerCount | Count | % | Interpretation |
|-------------|-------|---|----------------|
| 0 | 75 | 0.2% | Demotions (evicted, no sharers) |
| 1 | 33,071 | 85.9% | Private region (single GPU) |
| 2 | 1,935 | 5.0% | Shared by 2 GPUs |
| 3 | 3,429 | 8.9% | Shared by 3 GPUs |

Multi-GPU sharing evidence: **14.0%** of promotions involve ≥2 GPUs sharing the region.

## Interpretation (§3.3 narrative)

Matmul exhibits a **highly regular, promotion-dominated** adaptive behavior:
- 99.8% of events are promotions — the superdirectory is almost entirely in up-scaling mode,
  indicating that 256B granularity (Bank 3) is consistently more efficient than the default 64B (Bank 4) — a 4× region expansion.
- Utilization at promotion is always 1.0 (full utilization of the region before promoting),
  confirming the promotion trigger is working correctly.
- 14% of promoted regions are multi-GPU shared — these are the matrix data tiles that
  multiple GPUs access concurrently, confirming cross-GPU coherence activity.
- The demotion trigger fires at utilization ~0.40, meaning roughly 60% of a region's
  cachelines are unused when demotion occurs — expected for boundary/padding regions.

## Figures
- `analysis/m1/figures/bank_transition_heatmap_matmul.png`
- `analysis/m1/figures/sharer_count_distribution_matmul.png`
- `analysis/m1/figures/utilization_distribution_matmul.png`
