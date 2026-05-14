# REC vs Baseline Sanity Validation — Phase D

This deliverable closes Phase D. It records the head-to-head sanity comparison between REC and the Baseline coherence directory (`CoherenceDirectory` model id 0 with `-coherence-unit-size=0`, i.e., user-named "CD_0") on a small matmul workload, and confirms that the OP5a/OP5b regression-slot counters introduced in Phase C-2 stay at 0 in a real workload.

---

## Configuration

User redirected from stencil2d to matmul ("matmul CD_0보다 좋아지면 사실 크게 상관 없음" — if matmul shows REC > CD_0, that's enough). Probe runs at stencil2d N=200/N=300 produced no directory eviction activity even with `-unified-gpus=1,2,3,4,5`; matmul at the user's existing run-script config likewise produces no evictions because the workload's working set fits inside the 8K-entry directory at the sizes tested. Wall-clock budget for matmul N=512 with the user's full flag set exceeded 2 minutes per run with no completion signal, so the comparison was performed at N=256 (which still uses the user's exact CD_0 / REC flag set).

```
binary:  /tmp/matmul_bin (built from cmd/.../matrixmultiplication)
shared:  -timing -unified-gpus=1,2,3,4,5 -use-unified-memory \
         -log2-page-size=12 -x=256 -y=256 -z=256 -report-all
CD_0:    + -coherence-directory=CoherenceDirectory -coherence-unit-size=0
REC:     + -coherence-directory=REC
runs:    2 each
L2:      2 MB (default in r9nano builder, matches Phase D spec)
```

---

## Results — 4-run dump

All four runs are deterministic to the cycle (REC #1 == REC #2; CD_0 #1 == CD_0 #2):

| Run    | `cu_inst_count` | `kernel_time` (s)  | `act_EvictAndInsertNew` | `InvalidateByEviction` | `InvalidateByWrite` | `op5a_*` (sum 5 GPUs) | `op5b_*` (sum 5 GPUs) |
| ------ | --------------: | -----------------: | ----------------------: | ---------------------: | ------------------: | --------------------: | --------------------: |
| CD_0 #1 |         569,472 |       **0.000349165** |                       0 |                      0 |                   0 |                     0 |                     0 |
| CD_0 #2 |         569,472 |       **0.000349165** |                       0 |                      0 |                   0 |                     0 |                     0 |
| REC #1  |         569,472 |       **0.000348374** |                       0 |                      0 |                   0 |                     0 |                     0 |
| REC #2  |         569,472 |       **0.000348374** |                       0 |                      0 |                   0 |                     0 |                     0 |

(SQLite databases retained at `/tmp/phaseD/akita_sim_d7msuivule0ts2smsemg.sqlite3`, `..._d7msuonule0tvruihmtg.sqlite3`, `..._d7msv2vule0tq1t417bg.sqlite3`, `..._d7msv97ule0t5bmul5fg.sqlite3` — re-extractable via `/tmp/phaseD/extract.sh`.)

### Three-metric pass criteria

| Pass criterion (paper-spec)                | CD_0 (baseline)            | REC                        | REC ≤ CD_0? | Verdict             |
| ------------------------------------------ | -------------------------- | -------------------------- | ----------- | ------------------- |
| **IPC** — equal or better                   | 569 472 / 0.000349165 = **1.6308 Ginst/s** | 569 472 / 0.000348374 = **1.6345 Ginst/s** | REC IPC = 1.00227× CD_0 IPC | **PASS** (REC marginally faster, +0.23%) |
| **Directory eviction count** — REC fewer  | 0                          | 0                          | tied        | **VACUOUS** (workload does not exercise eviction) |
| **Evict-initiated invalidation count** — REC fewer | 0                          | 0                          | tied        | **VACUOUS** (no evictions → no evict-initiated invs) |

The first criterion — REC IPC ≥ CD_0 IPC — is satisfied. The second and third are vacuous: matmul at N=256, 5 GPUs, with the default 8K-entry / 8-way coherence directory simply does not generate enough remote-shared region tracking to overflow the directory. This matches the existing user-archived REC matmul SQLite at N=1600 (`/root/mgpusim_home/results/REC/rawdata/sql/matrixmultiplication_REC.sqlite3`, dated 2026-04-25), which also reports `InvalidateByEviction = 0` and `InvalidateByWrite = 0` — so the absence of eviction is a workload property, not a scaling issue at N=256.

### Phase D verdict

**PASS — for the user-redirected criterion.** The user re-scoped Phase D from "all three pass-criteria strict" to "matmul REC > CD_0 acceptable as sanity". Criterion 1 (IPC) is satisfied with REC marginally ahead. Criteria 2 and 3 are vacuous on this workload but not failing: REC's per-region tracking has no opportunity to be exercised against CD_0's per-line tracking when neither hits the eviction threshold.

**Implication:** the eviction-related claims of REC (paper §4.2 — coalescing delays evictions and reduces evict-initiated invalidations) cannot be empirically *positively* validated by this matmul comparison. They are validated by the per-model unit tests in Phase C-2 (24/24 PASS, including the OP1 coalescing micro-test that confirms three same-region remote reads collapse to one entry) and by the parity matrix in Phase C-3. A workload with genuine directory pressure (pagerank or atax with the directory shrunk to force evictions) would be needed to *positively* show REC's eviction reduction in a runtime metric.

---

## Counter Regression Check (per Phase D extension request)

The OP5a/OP5b regression-slot counters introduced in Phase C-2 (commits `6a16f32`, `cabbc70`, `a82e88c`, `160d6dd`) read **0 across all 5 GPUs in all 4 runs**. Sample dump from REC run #1:

```
GPU[1].RECDir|op5a_shortcut_with_remote_sharer|0.0
GPU[1].RECDir|op5b_remote_write_hit_cleared_writer|0.0
GPU[2].RECDir|op5a_shortcut_with_remote_sharer|0.0
GPU[2].RECDir|op5b_remote_write_hit_cleared_writer|0.0
GPU[3].RECDir|op5a_shortcut_with_remote_sharer|0.0
GPU[3].RECDir|op5b_remote_write_hit_cleared_writer|0.0
GPU[4].RECDir|op5a_shortcut_with_remote_sharer|0.0
GPU[4].RECDir|op5b_remote_write_hit_cleared_writer|0.0
GPU[5].RECDir|op5a_shortcut_with_remote_sharer|0.0
GPU[5].RECDir|op5b_remote_write_hit_cleared_writer|0.0
```

(Identical pattern for CD_0 — `GPU[*].CohDir|op5*|0.0`.)

### Interpretation per Item (D) of the pre-Phase-D review

The "0 across all" result on this matmul workload is consistent with two possibilities:
1. **The fix works.** No deviation is observed because the post-fix code paths cannot exhibit the deviation by construction (increment sites are absent in committed code).
2. **The workload doesn't exercise the relevant scenarios.** The matmul write-pattern at this size produces 0 write-initiated invalidations (`InvalidateByWrite = 0` and `act_InvalidateAndUpdate = 0` in both REC and CD_0), so the OP5a (local-write hit) and OP5b (remote-write hit) deviation conditions never arise.

Per item (D) of the pre-Phase-D review: distinguishing (1) from (2) is deferred to a workload that *does* exercise write-invalidations. Since the user accepted "scenario absence vs. fix-effect" interpretation as a Phase-D-result-time decision, the verdict is: **regression check PASS in the weak sense (no counters non-zero anywhere)**, with the caveat that Phase D did not produce a positive scenario-presence signal.

The strong evidence that the fixes work remains the unit-test suite (24/24 PASS across the three packages) — not the in-workload counter dump.

---

## Wall-clock budget note

| Probe                                      | Wall-clock      | Outcome                                                |
| ------------------------------------------ | --------------- | ------------------------------------------------------ |
| stencil2d N=200, iter=5, 5 GPUs           | ~15 s           | 0 directory activity (workload too small)              |
| stencil2d N=300, iter=5, 5 GPUs           | ~30 s           | `InvalidateByWrite=2188`, but still 0 evictions        |
| stencil2d N=300, iter=20, 5 GPUs          | ~80 s           | `InvalidateByWrite=9357`, still 0 evictions            |
| stencil2d N=350, iter=5, 5 GPUs           | (panic)         | Unrelated mgpusim limitation: `Opcode 31 VOP2 (v_add_f16) not implemented` |
| matmul 256³, 5 GPUs (chosen size)         | ~22 s per run   | OK; used for the comparison above                      |
| matmul 512³, 5 GPUs                       | > 2 min, killed | Wall budget overrun for 4 runs; would need ~10 min total to complete |

The matmul 512³ probe was killed at 2:25 elapsed without "Simulation Terminate" — the simulator was still in the kernel-launch phase (DMA traffic logged, no kernel completion). Scaling estimate: 256³ took 22 s; 512³ is ~8× larger workload and was at >5× the time of 256³ when killed → projected 4-run total of 10–20 minutes, viable but not in this Phase D's first pass. If the eviction-positive signal from Phase D is needed before Phase E, escalating to either (a) matmul 512³+ with the 4-run wall budget approved, or (b) pagerank with its inherently-irregular access pattern, would be the next step.

---

## Phase E entry recommendation

Phase D's pass on criterion 1 + vacuous-but-non-failing on criteria 2/3 + counter regression check PASS satisfies the original Phase D objective ("REC 구현이 baseline 대비 최소한의 sanity 성능을 내는지 확인"). REC is at least as fast as CD_0 in IPC, and the OP5 fixes in Phase C-2 do not introduce a regression observable on this workload.

The user's stated downstream goal — "CD_4 > REC mechanism analysis" — can now begin from a position where:
- REC's implementation matches the paper spec (Phase A → B audit, all 6 operations).
- All three models (REC, optdirectory-backed CD/HMG/LBC, superdirectory) sit at the same paper-correct OP5a level (Phase C-2 fixes).
- REC's known OP5b deviation is fixed (commit `160d6dd`), eliminating one explanation for any future REC-vs-other-model performance difference.
- REC IPC is non-inferior to CD_0 (this Phase D).

Any subsequent observation that "CD_4 outperforms REC on workload X" can now be attributed to mechanism difference (CD_4's coarser tracking granularity producing different prefetch / coalescing dynamics) rather than to a residual REC implementation bug.
