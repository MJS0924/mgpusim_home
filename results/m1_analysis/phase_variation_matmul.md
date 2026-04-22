# Phase Variation Analysis — Matmul

## Configuration
- Method: equal-count phase split on promotions, N=10 phases
- Ordering: time_sec ascending

## Per-Phase Statistics (Equal-Count, Promotions)

| Phase | Events | Dom ToBank | Bank0 (16KB)% | Bank1 (4KB)% | Bank2 (1KB)% | Bank3 (256B)% | Avg Sharer |
|-------|--------|------------|--------|--------|--------|--------|------------|
| 0 | 3,844 | 3 | 1.3% | 4.8% | 17.8% | 76.0% | 1.74 |
| 1 | 3,843 | 3 | 1.1% | 4.6% | 18.5% | 75.8% | 1.74 |
| 2 | 3,844 | 3 | 1.1% | 4.6% | 19.0% | 75.3% | 1.59 |
| 3 | 3,843 | 3 | 1.2% | 4.7% | 18.8% | 75.2% | 1.07 |
| 4 | 3,844 | 3 | 1.1% | 4.6% | 18.7% | 75.5% | 1.03 |
| 5 | 3,843 | 3 | 1.1% | 4.5% | 18.7% | 75.6% | 1.03 |
| 6 | 3,843 | 3 | 1.2% | 4.7% | 18.9% | 75.3% | 1.02 |
| 7 | 3,844 | 3 | 1.2% | 4.8% | 18.8% | 75.2% | 1.02 |
| 8 | 3,843 | 3 | 1.1% | 4.6% | 18.9% | 75.3% | 1.02 |
| 9 | 3,844 | 3 | 1.2% | 4.7% | 18.8% | 75.3% | 1.03 |

## Phase Variation Summary

| Metric | Value |
|--------|-------|
| Unique dominant ToBank | **1** (Bank 3 only) |
| Mean KL divergence (adjacent phases) | 0.0001 |
| Max KL divergence | 0.0004 |
| Phase variation judgment | **NO** |

## M1 Exit Criteria Judgment (Matmul)

**FAIL** — Bank 3 is the dominant ToBank in all 10 phases with essentially zero variation.
KL divergence between adjacent phases is ~0.0001 (effectively zero).

### Interpretation

Matmul has a **stable, non-varying** optimal region size across its execution.
The 256B granularity (Bank 3) is optimal throughout the entire kernel, which reflects
matmul's highly regular tiled access pattern — each tile is accessed uniformly, and
the optimal coherence granularity does not change across computation phases.

**This does NOT invalidate the M1 motivation.** It means matmul is a baseline case
where adaptive region sizing provides a consistent benefit (always 256B is better than 64B,
a 4× improvement), but the *dynamic* adaptation story must come from other workloads
(pagerank, irregular graphs, etc.).

## Figures
- `analysis/m1/figures/phase_bank_timeline_matmul.png`
- `analysis/m1/figures/phase_dominant_bank_matmul.png`
