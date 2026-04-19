# SuperDir Evaluation Report (DRAFT for HPCA 2026)

**Generated**: 2026-04-19 | **Status**: DRAFT — FAIL items must be resolved before submission.

---

## 1. Executive Summary

- **Workloads evaluated**: 4 (bfs, im2col, matrixmultiplication, pagerank)
- **GPU configuration**: 5 GPUs total — GPU[1] host/control (kernel_time=0), GPU[2-5] compute
- **Schemes**: CD (CoherenceDirectory, unit-size=0, 64B baseline), REC, HMG, SuperDir
- **Baseline**: CD_0 (coherence-unit-size=0) = standard 64B cache-line directory
- **Single run per (scheme, workload) — no variance/error bars; state in all figure captions**

### Available comparison pairs (CD baseline required for speedup):

| Workload | CD | REC | HMG | SuperDir | CD-baseline speedup available? |
|----------|:--:|:---:|:---:|:--------:|:---:|
| bfs | ✗ MISSING | ✗ MISSING | ✗ MISSING | ✓ | NO |
| im2col | ✓ | ✓ | ✓ | ✓ | YES |
| matrixmultiplication | ✓ | ✓ | ✓ | ✓ | YES |
| pagerank | ✗ MISSING | ✓ | ✓ | ✓ | NO |

**2 of 4 workloads usable for cross-scheme performance comparison** (im2col, matrixmultiplication).

### Geomean speedup vs CD (2 workloads: im2col + matrixmultiplication):

| Scheme | Geomean speedup vs CD | Min | Max |
|--------|----------------------|-----|-----|
| REC | **1.0904×** | 1.0113× (im2col) | 1.1756× (MM) |
| HMG | **1.0518×** | 0.9985× (im2col) | 1.1079× (MM) |
| **SuperDir** | **0.9167×** ⚠ | 0.8489× (MM) | 0.9901× (im2col) |

**SuperDir is slower than CD on both available workloads. Geomean 8.3% regression vs CD.**

---

## 2. Performance (PHASE 2)

**Definition used**: `Driver|kernel_time` (wall-clock, single GPU[0] perspective).

Cross-check with `max(GPU[2-5].CommandProcessor|kernel_time)`: matches within 1% for all cases except:
- REC/pagerank: 1.09% divergence (⚠ WARN — PHASE 6 escalation)
- SuperDir/bfs: 1.27% divergence (⚠ WARN — PHASE 6 escalation)

All times in seconds:

| Workload | CD | REC | HMG | SuperDir | SuperDir speedup vs CD |
|----------|--------|--------|--------|----------|------------------------|
| im2col | 0.000297 | 0.000294 | 0.000297 | 0.000300 | **0.9901×** ← regression |
| matrixmultiplication | 0.000986 | 0.000839 | 0.000890 | 0.001162 | **0.8489×** ← regression |
| bfs | MISSING | MISSING | MISSING | 0.000987 | N/A |
| pagerank | MISSING | 0.001618 | 0.001454 | 0.001566 | N/A |

⚠ **SuperDir regression on matrixmultiplication: 17.8% slower than CD.**

### Reviewer pre-emption (PHASE 2):
- **R2-1** (Driver.kernel_time scope): MGPUSim `Driver|kernel_time` = end-to-end simulation wall time including MemCpy. All schemes use identical workload parameters (bfs: node=262144 degree=16; im2col: N=1 C=3 H=128 W=128; MM: 1000×1000×1000; pagerank: node=16384 sparsity=0.005 iter=4).
- **R2-2** (Input size consistency): Same `-log2-page-size=12` and workload arguments for all schemes (verified in `2_make_shell.py`).
- **R2-3** (Warm-up): Single-kernel workloads — cold-start effects present uniformly across all schemes. No differential bias.

---

## 3. Cache & Memory Behavior (PHASE 3, 6)

### L2 Cache hit rates (compute GPUs 2-5, MSHR-hits excluded from numerator/denominator):

| Workload | Scheme | Local HR | Remote HR | read-miss count |
|----------|--------|:--------:|:---------:|----------------:|
| im2col | CD | 0.5852 | 0.5428 | 23,641 |
| im2col | REC | 0.6313 | 0.6202 | 23,642 |
| im2col | HMG | 0.5858 | 0.5438 | 23,640 |
| im2col | **SuperDir** | **0.5895** | **0.5567** | **23,066** |
| matrixmultiplication | CD | 0.5487 | 0.3436 | 280,694 |
| matrixmultiplication | REC | 0.5208 | 0.2314 | 272,135 |
| matrixmultiplication | HMG | 0.5228 | 0.2354 | 272,123 |
| matrixmultiplication | **SuperDir** | **0.6102** | **0.5199** | **272,192** |

**SuperDir has equal or better L2 hit rate than CD for both workloads**, yet is slower. Root cause: L2Cache req_average_latency increase.

### L2 Cache request average latency (ns):

| Workload | CD | REC | HMG | SuperDir |
|----------|----|-----|-----|----------|
| im2col | 346.14 | 215.37 | 343.11 | 340.83 |
| matrixmultiplication | 728.63 | 690.16 | 739.31 | **998.89** ← +37% |

**SuperDir adds 270ns/request L2 latency for matrixmultiplication vs CD (+37%).**
This directly explains the 17.8% slowdown despite a 6.1% better L2 hit rate.

### False sharing (L2Cache RW:true/true ratio, matrixmultiplication):
- CD: 4,458 / 153,954 total = 2.8%
- REC: 478 / 15,840 = 3.0%
- HMG: 647 / 29,732 = 2.2%
- **SuperDir: 1,474 / 31,165 = 4.7%** ← highest false-sharing ratio

SuperDir's coarser region granularity in practice (bank4 = 64B, same as CD) does not reduce false sharing, and the 4.7% vs CD 2.8% ratio indicates marginally more pollution.

### Reviewer pre-emption (PHASE 3):
- **R3-1** (Hit rate improvement source): SuperDir's hit rate improvement is NOT from prefetch (no prefetch mechanism exists in the data). It comes from larger region tracking that allows more sharers. However, the tracking overhead exceeds the benefit for matrixmultiplication.
- **R3-2** (vs HMG): HMG already groups 4 cachelines; for im2col it's marginally slower (0.9985×) vs CD but for MM it's 10.8% faster. SuperDir does NOT outperform HMG on either workload (SuperDir im2col: 0.9901×, HMG im2col: 0.9985× — HMG is actually closer to CD; SuperDir MM: 0.8489×, HMG MM: 1.1079× — HMG is 30% faster than SuperDir on MM).
- **R3-3** (DRAM vs L2 check): L2ToDRAM.read_trans_count = 0 for all schemes (MGPUSim simulator artifact — L2 to DRAM path does not populate this counter). DRAM read_trans_count is valid at DRAM module level. This check could not be performed.

---

## 4. Network Traffic (PHASE 4)

All payload sizes verified from data: Read Req=12B, Read Rsp=68B, Write Req=76B, Write Rsp=4B, Inv Req=12B, Inv Rsp=4B.

### Total RDMA bytes, compute GPUs 2-5 (matrixmultiplication):

| Scheme | Total (MB) | Read Rsp (MB) | Write Req (MB) | Inv Req (MB) | Inv ratio |
|--------|:----------:|:-------------:|:--------------:|:------------:|:---------:|
| CD | 44.68 | 27.74 | 7.45 | **3.12** | **6.98%** |
| REC | 37.69 | 27.74 | 4.85 | 0.00 | 0.00% |
| HMG | 40.46 | 27.74 | 7.43 | 0.00 | 0.00% |
| **SuperDir** | **44.54** | **32.20** | **7.56** | 0.00 | 0.00% |

- CD has significant invalidation overhead (6.98% of traffic = 3.12MB).
- SuperDir eliminates invalidation traffic (0%) but has **16% more Read Rsp** than CD (32.20MB vs 27.74MB) — more cross-GPU data movement.
- Net: SuperDir sends as much total traffic as CD despite no Inv overhead, because it fetches more data remotely.

Per-GPU traffic imbalance (max/avg): CD=1.67×, REC=1.72×, HMG=1.65×, SuperDir=1.69× — all schemes similar.

### Reviewer pre-emption (PHASE 4):
- **R4-1** (Byte vs message count): SuperDir reduces Inv message count to ~0 but the saved 3.12MB is offset by +4.46MB extra Read Rsp. Net byte outcome: SuperDir traffic ≈ CD (44.54MB vs 44.68MB). Message-count reduction exists, byte-level savings do NOT.
- **R4-2** (vs REC per-entry bytes): REC sends 37.69MB (15.7% less than CD) because REC compresses 16 entries and avoids many invalidations AND reduces write traffic. SuperDir does not achieve this reduction.
- **R4-3** (NVLink congestion): L2Cache mean latency is 37% higher for SuperDir/MM, suggesting network congestion from extra Read Rsp traffic (read_rsp=32.20MB vs 27.74MB) is likely contributing to the latency increase.

---

## 5. SuperDir Attribution (PHASE 5)

**Source code verified**: bank size mapping confirmed from `akita/mem/cache/superdirectory/builder.go`:
- `regionLen = [14, 12, 10, 8, 6]` → [16KB, 4KB, 1KB, 256B, 64B] = banks 0, 1, 2, 3, 4

### Bank utilization (UpdateEntry per bank, sum over GPU 2-5):

| Workload | bank0 16KB | bank1 4KB | bank2 1KB | bank3 256B | bank4 64B |
|----------|:----------:|:---------:|:---------:|:----------:|:---------:|
| bfs | 0.0% | 0.0% | 0.0% | 0.0% | **99.9%** |
| im2col | 0.0% | 0.0% | 0.1% | 0.3% | **99.6%** |
| matrixmultiplication | 0.2% | 0.2% | 0.4% | 1.6% | **97.6%** |
| pagerank | 0.0% | 0.0% | 0.1% | 0.2% | **99.7%** |

**97.6–99.9% of all directory entries are in bank4 (64B = standard cacheline size).** SuperDir is functioning as a standard cacheline directory with multi-bank lookup overhead.

### Adaptation activity:

| Workload | Promotion | Demotion | Eviction | Write-Inv |
|----------|:---------:|:--------:|:--------:|:---------:|
| bfs | **0** | **0** | 0 | 0 |
| im2col | **0** | **0** | 0 | 12 |
| matrixmultiplication | **0** | **0** | 6 | 0 |
| pagerank | **0 (bank4)** | **0** | 593 | 4,038 |

⚠ **Promotion = 0, Demotion = 0 for ALL workloads. Dynamic adaptation NEVER triggered.**

Note: pagerank has 118 Promotions in bank3 per the bank-split data (not reflected in aggregate counter which is 0 — aggregate counter discrepancy documented in FAIL_LOG). This represents 118/130,945 total entries = 0.09% of entries experienced any promotion event.

### Lookup depth:

| Workload | BankChecked[1] | avg depth | BankChecked[1] > 90%? |
|----------|:--------------:|:---------:|:----------------------:|
| matrixmultiplication | 47.1% | **2.55** | NO |
| pagerank | 39.9% | **2.95** | NO |

**Only 40-47% of lookups complete in 1 bank check** (R5-3 defense fails: avg 2.55-2.95 » 1). 21.1% (MM) and 34.5% (PR) require all 5 banks. This serial lookup overhead is the primary cause of L2Cache latency increase.

### Reviewer pre-emption (PHASE 5) — highest-risk section:
- **R5-1** (Overkill design): 97-99% entries in bank4 = **confirmed**: SuperDir provides no region-size benefit over CD for these workloads. 0/5 banks have >10% occupancy simultaneously. The multi-bank design is not exercised.
- **R5-2** (Promotion/Demotion cost-benefit): Promotion=0, Demotion=0. There is zero adaptation activity to defend. No cost-benefit analysis is possible — adaptation produced no observable events.
- **R5-3** (Serial bank check overhead): avg depth 2.55-2.95 with 20-34% of requests needing all 5 banks. This matches the observed 37% L2Cache latency increase for matrixmultiplication. Paper's claim of low serial lookup penalty is **NOT supported by data**.

---

## 6. Cross-check Summary (PHASE 6)

| Check | PASS | WARN | FAIL |
|-------|:----:|:----:|:----:|
| L2ToDRAM vs DRAM balance | 0 | 0 | 48 |
| RDMA ReadReq vs L2 remote | 4 | 8 | 0 |
| SuperDir FromRemote vs RDMA in | 4 | 0 | 0 |
| Monotone (miss↓ → time↓) | 4 | 1 | 2 |
| PHASE2 escalations | 0 | 2 | 0 |
| **Total** | **12** | **11** | **50** |

### FAIL explanations:
- **L2ToDRAM balance (48 FAILs)**: ALL systematic. L2ToDRAM.read_trans_count = 0 by simulator design (bridge component doesn't populate this counter). Not a simulation error; does not affect validity of other metrics.
- **Monotone SuperDir/im2col**: SuperDir miss_rate=0.4105 < CD=0.4148 (5.9% fewer misses) but SuperDir is 1% SLOWER. Root cause: multi-bank lookup latency.
- **Monotone SuperDir/MM**: SuperDir miss_rate=0.3898 < CD=0.4513 (13.6% fewer misses) but SuperDir is 17.8% SLOWER. Root cause: 37% L2Cache latency increase from avg 2.55 serial bank checks.

### WARN explanations:
- REC/pagerank driver vs cp_max: 1.09% — marginal; use cp_max for pagerank if re-running.
- SuperDir/bfs driver vs cp_max: 1.27% — bfs has no baseline anyway (MISSING).
- RDMA/MM 8 WARNs: RDMA ReadReq count vs L2 remote-read total ratio = 0.2-0.5 — different counting granularities (RDMA counts per-message, L2 counts per-cacheline-hit).

---

## 7. Threats to Validity

1. **Single run, no variance**: All results are single-run simulations. No statistical confidence intervals. State explicitly in every figure caption.
2. **Severely limited workload coverage**: Only 2 of 4 workloads allow CD-baseline speedup comparison. bfs and pagerank baselines are MISSING for CD. Geomean over 2 workloads is not representative.
3. **Adaptation mechanism did not trigger**: All 4 workloads land 97-99% in bank4 (64B). The core innovation of SuperDir (dynamic region-size adaptation) was NOT exercised. These results test SuperDir at 64B granularity only, which is the same as CD plus overhead.
4. **MGPUSim modeling limitations**:
   - L2ToDRAM.read_trans_count = 0 (simulator artifact)
   - NVLink latency modeled as simple latency; contention model may underestimate at scale
   - Directory req_average_latency reports 2.00ns for ALL schemes (possibly fixed-latency model, not reflecting actual BankChecked depth)
5. **Workload sizes are small**: pagerank: 16K nodes, MM: 1000×1000. Working sets fit mostly in GPU cache. Results may differ at production scale where conflict misses increase and adaptation might trigger more frequently.

---

## 8. Open Questions for Co-authors

### Critical — must resolve before submission:

1. **Why does adaptation never trigger?** Promotion/Demotion = 0 for all 4 workloads. Is the threshold set too conservatively? Is there a bug in the promotion/demotion trigger condition? Check `bankstage.go` → `InvalidateAndUpdateEntry()` and `FinalizePromotionEntry()` call paths.

2. **Re-run with larger workload sizes**: Try MM: 4096×4096, pagerank: 1M nodes, bfs: 1M nodes with higher degree. These may increase working sets beyond L2 and trigger inter-bank pressure.

3. **CD baseline for bfs and pagerank**: Run `bfs_CD_0` and `pagerank_CD_0` simulations. Without these, speedup comparison covers only 2 workloads.

4. **UpdateEntry aggregate counter = 0**: The aggregate (non-bank-split) `SuperDir|UpdateEntry` = 0.0 in all data files, while per-bank sums are large (up to 130K entries). This is a counter instrumentation discrepancy. Verify that `GetStepCount("UpdateEntry")` is being called correctly in `reportCohDir()`.

5. **L2Cache latency source**: Directory `req_average_latency = 2.00ns` for ALL schemes (fixed). But L2Cache latency is 37% higher for SuperDir/MM. Determine whether the latency overhead comes from: (a) RDMA network congestion (extra Read Rsp bytes), (b) multi-bank lookup stalls causing backpressure on L2 request queue, or (c) false sharing causing more invalidations than counted.

6. **Banks 5 and 6 in data**: The SQLite files contain `SuperDir|UpdateEntry - 5` and `UpdateEntry - 6` rows (all zero). Source code only loops to bankID < 5. Investigate whether these are stale DB entries or a DB schema mismatch.

### Lower priority:

7. **Payload byte size source**: Inv Rsp = 4B. Confirm from `RDMA` source (ack-only message). Currently validated from data, not from Go source.

8. **HMG component name**: HMG uses `cohDir_metrics` table under component name `HMGDir`, while HMG uses `coherenceDirectory=4` (same `optdirectory.Comp` as CD_0). Verify that bank configuration parameters differ correctly.

---

## 9. Files Generated

```
analysis/
├── FAIL_LOG.md            — all failures/warnings from all phases
├── REPORT.md              — this file
├── parsed/
│   ├── long.csv           — 151,619 rows, 15 columns
│   └── long.csv.gz        — compressed version
├── tables/
│   ├── 00_inventory.csv   — (scheme × workload) availability matrix
│   ├── 02_exec_time.csv   — execution times (driver + cp_max)
│   ├── 02_speedup.csv     — speedup vs CD, with geomeans
│   ├── 02_regressions.csv — SuperDir regressions
│   ├── 03_cache_summary.csv — L2/L1 hit rates, miss counts
│   ├── 03_cache_per_gpu.csv — per-GPU hit rate breakdown
│   ├── 03_false_sharing.csv — RW:T/T false sharing counts
│   ├── 04_network_bytes.csv — RDMA traffic by type
│   ├── 04_inv_ratio.csv   — invalidation traffic ratio
│   ├── 04_per_gpu_traffic.csv — per-GPU RDMA breakdown
│   ├── 05_superdir_breakdown.csv — bank utilization + invalidation
│   └── 06_crosscheck.csv  — 72 cross-validation checks
└── figures/
    ├── FP1_speedup.pdf/.png/.csv
    ├── FP2_network_bytes.pdf/.png/.csv
    ├── FP3_L2_miss_rate.pdf/.png/.csv
    ├── FP4_bank_utilization.pdf/.png/.csv
    ├── FP6_bankchecked_cdf.pdf/.png/.csv
    └── attribution_L2latency.csv
```

---

*⚠ PHASE 6 has 2 FAIL items (Monotone violations) and 48 systematic FAILs (L2ToDRAM simulator artifact). The 2 Monotone FAILs indicate a fundamental performance issue with SuperDir on these workloads. Resolution requires either (a) demonstrating that the adaptation mechanism works on different/larger workloads, or (b) fundamental redesign. Do NOT submit figures from this draft without resolving Open Questions 1-5.*
