# Workload Comparison — Matmul vs Pagerank

## Event Log Summary

| Metric | Matmul | Pagerank |
|--------|--------|----------|
| Total events | 38,510 | 54,814 |
| Promotions | 38,435 (99.8%) | 54,761 (99.9%) |
| Demotions | 75 (0.2%) | 53 (0.1%) |
| Prom/Dem ratio | 512.5× | 1,033.2× |
| Multi-GPU shared (sharer≥2) | **14.0%** | **0.6%** |
| Dominant promotion path | Bank4 (64B)→Bank3 (256B) (75.4%) | Bank4 (64B)→Bank3 (256B) (75.9%) |
| Promotion utilization | always 1.000 | always 1.000 |
| Demotion utilization mean | 0.400 | 0.500 |
| Sim. time span | 0.855–1.917 ms | 0.695–1.114 ms |

## Phase Variation (10 equal-count phases)

### Strict criterion (dominant bank changes)

| Workload | Unique Dominant Banks | Phase Variation? |
|----------|-----------------------|-----------------|
| Matmul | 1 (Bank 3) | **NO** |
| Pagerank | 1 (Bank 3) | **NO** |

### Distribution criterion (KL divergence)

| Workload | Mean KL | Max KL | Significant shift? |
|----------|---------|--------|-------------------|
| Matmul | 0.0001 | 0.0004 | **NO** (essentially flat) |
| Pagerank | **0.0227** | **0.0816** | **YES** (substantial drift) |

### Pagerank Phase Distribution Detail

| Phase | Bank0 (16KB)% | Bank1 (4KB)% | Bank2 (1KB)% | Bank3 (256B)% |
|-------|--------|--------|--------|--------|
| 0 | 0.0% | 0.5% | 8.9% | 90.5% |
| 2 | 0.3% | 1.8% | 13.4% | 84.5% |
| 4 | **0.9%** | **6.9%** | **25.9%** | 66.3% |
| 5 | **2.5%** | **8.7%** | 23.8% | 65.0% |
| 9 | **3.0%** | **9.3%** | 25.4% | 62.4% |

**Key observation**: In pagerank, the fraction of regions promoted to Bank 0 (16KB granularity)
grows from 0% → 3%, and Bank 1 (4KB) from 0.5% → 9.3% across phases. This reflects
BFS-level access expansion — early iterations access small concentrated neighborhoods
(256B optimal), while later iterations spread to larger, sparser regions (4KB–16KB optimal).

## Multi-GPU Sharing Contrast

| Workload | Private (sharer=1) | Shared 2 GPUs | Shared 3 GPUs |
|----------|--------------------|---------------|---------------|
| Matmul | 86.0% | 5.0% | 8.9% |
| Pagerank | 99.4% | 0.5% | 0.1% |

Matmul has **23× more multi-GPU sharing** than pagerank, consistent with:
- Matmul: matrix tiles explicitly distributed + accessed by multiple GPUs (RDMA traffic)
- Pagerank: node ownership is per-GPU; cross-GPU sharing is rare

## Paper §3.3 Narrative Implications

**Finding 1 (static benefit)**: Both workloads strongly prefer 256B (Bank 3) over the
default 64B (Bank 4) — a 4× region expansion. This validates the superdirectory's ability
to identify the optimal coherence granularity when the default is suboptimal.

**Finding 2 (dynamic adaptation — pagerank)**: Pagerank shows significant ToBank distribution
drift (max KL=0.0816) — later phases increasingly benefit from larger regions (1KB–16KB).
A static 256B configuration would be suboptimal for 20–35% of promotions in phases 4–9.
**This is the key motivation for phase-aware adaptive sizing.**

**Finding 3 (matmul stability)**: Matmul's extremely low KL (0.0001) confirms that
regular workloads with uniform access patterns do not require phase-aware adaptation —
a single optimal size suffices for the entire execution.

**Revised M1 narrative**: "While regular workloads (matmul) maintain a stable optimal
coherence granularity, irregular graph workloads (pagerank) exhibit significant phase-level
drift in their optimal region size distribution, motivating dynamic per-phase adaptation."
