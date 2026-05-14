# M6 Implementation Plan — DGD Baseline + Multi-Grain Directories for MGPUSim (v1.2)

> **v1.2 revision (2026-04-20)**: additionally addresses 3 new issues — (N1) DGD region:block way ratio defaults to **0.5** (Zebchuk 2013 equal split), with 0.25 preserved as a Basu-style asymmetric-RVA ablation; (N2) new **Contingency plan** section for MGD reproduction failure; (N3) MGD reproduction gate redefined from "±15% of 41–66%" to a sanity bound ("≥10% entry reduction vs baseline"), because Zebchuk's 41–66% is a CPU figure and a lower GPU reduction may itself be H1/H2 evidence.
>
> **v1.1 (2026-04-20)**: 4 critical issues (faithful MGD DGD, `-directory ideal` reuse of PlainVI, sub-entry grain = bank RegionSize/4, bit-based iso-storage with policy A as primary) + 4 major issues (FIFO+LRU dual support, region-aware MSHR DGD application, offline-oracle M6-2, ML workload availability check). M6-3 split out of the DGD critical path into PHASE 0 offline analysis of the existing 64B baseline trace.

## Context

The M6 experiment (H1/H2/H3 refutation of MGD MICRO'13 "dual-grain suffices") requires running
multiple competing directory configurations over MGPUSim workloads and comparing per-phase
metrics. The existing M1 harness at [cmd/m1/](mgpusim_home/mgpusim/cmd/m1/) only supports a
single-grain [PlainVIDirectory](mgpusim_home/mgpusim/coherence/plain_vi.go) with
`InfiniteCapacity=true`, a single workload (`simpleconvolution`), and no concept of
coarse/fine dual granularity, sub-entries, or finite eviction. M6 needs:

- A **faithful DGD** (MGD MICRO'13) implementation.
- **TGD / QGD / Superdirectory** multi-grain directories (optional sub-entry).
- A **finite-capacity** entry store with **bit-based iso-storage** fair comparison.
- A new `cmd/m6/` binary that reuses PlainVI for the `ideal` (infinite) mode and instantiates
  the other directories for the main sweep.
- Expanded workload wiring (≥15 benchmarks across AMD-APP-SDK / Heteromark / SHOC / Polybench /
  graph / optional ML).

This plan covers the code changes for experiments M6-1, M6-2, M6-4, M6-5 and the DGD
reproducibility check. **M6-3** (sub-region sharer divergence) does NOT require DGD and is
moved to PHASE 0 offline analysis of the existing 64B baseline Parquet trace — see §Schedule.

---

## Scope & non-goals

- **In scope**: faithful MGD DGD impl; TGD/QGD/Superdir with hierarchical sub-entries;
  finite bit-budget entry store with FIFO + LRU; `cmd/m6` runner; workload registration;
  MGD reproducibility harness; region-aware MSHR plumbing for DGD and multi-grain; offline
  oracle analysis script for M6-2.
- **Out of scope**: REC/HMG baselines, NoC modifications, paper figures, ML benchmark authoring
  (if ML workloads are absent from the repo, fall back to current 15 — see §Workload availability).

---

## Architecture

```
coherence/
├── directory.go            (existing — extend DirectoryConfig + DirectoryStats)
├── plain_vi.go             (existing — REUSED for -directory=ideal, no behaviour change)
├── dgd.go                  (NEW — faithful MGD MICRO'13 §3 DualGrainDirectory)
├── multigrain.go           (NEW — k-grain banks + hierarchical sub-entries = Superdir)
├── finite_store.go         (NEW — set-assoc store; FIFO + LRU eviction, asymmetric ways)
├── bit_budget.go           (NEW — bit-exact iso-storage allocator, policy A/B/C)
├── false_inv_counter.go    (NEW — M6-5 false-invalidation accounting)
├── region_mshr.go          (NEW — region-aware MSHR for DGD + multi-grain)
└── *_test.go               (unit tests)

instrument/adapter/
├── directory_adapter.go    (existing — extend SharerEvent handling)
└── phase_metrics.go        (existing — add sub-entry / promotion / false-inv counters)

cmd/
├── m1/                     (existing — unchanged)
├── m6/                     (NEW main experimental driver)
│   ├── main.go
│   ├── config.go           (-directory {ideal|baseline|dgd1k|dgd4k|dgd8k|tgd|qgd|superdir|superdir-nosub})
│   ├── runner.go
│   ├── workloads.go
│   ├── iso_storage.go      (bit-budget plumbing + CLI dump for verification)
│   └── mgd_repro.go
└── m6offline/              (NEW — M6-3 and M6-2 offline analysis over existing parquet traces)
    └── main.go
```

---

## Critical issues addressed

### C1. Faithful DGD per MGD MICRO'13 §3

[coherence/dgd.go](mgpusim_home/mgpusim/coherence/dgd.go) must match Zebchuk et al.'s
original design precisely:

- **Region entry semantics**: a region entry represents a coarse region that has been
  accessed **by exactly one sharer**. It stores `{Tag, SingleSharer GPUID, PresenceBitmap}`
  and NO per-block sharer vector.
- **Block entry**: identical to fine-grain cacheline directory entry (sharer bit-vector +
  dirty bit).
- **Split rule (second-sharer trigger)**: on `UpdateSharers(addr, gpu, op)`:
  - If coarse `RegionEntry` exists AND `gpu == SingleSharer` → update presence bit only.
  - If coarse `RegionEntry` exists AND `gpu != SingleSharer` → **split**: convert the region
    into N block entries, one per present cacheline, each inheriting `SingleSharer` as sole
    sharer, then apply the new op to the specific block. Fire
    `SharerEventKindSubEntrySplit`.
- **Merge rule**: on insert of a new region that would map into an existing area, never merge
  block entries back into a region (MGD is monotonic; matches Zebchuk §3.2).
- **Way allocation (Zebchuk default = equal split)**: region entries and block entries share
  a single set-associative array with per-set way caps. Partition ratio is a `DirectoryConfig`
  field `DGDRegionWayRatio float64` with **default 0.5** — i.e. half the ways are region ways,
  half are block ways (Zebchuk 2013 §3.3). For an 8-way set this yields 4 region ways + 4
  block ways. The 0.25 value (2 region + 6 block) is retained as an **optional ablation
  variant** labelled *"Basu-style asymmetric RVA"* (Basu et al. 2013), selectable via
  `-directory=dgdNk -dgd-region-way-ratio=0.25`. **MGD reproduction check (§Verification 5)
  runs with 0.5** — using 0.25 there would compare against the wrong prior art.
  [finite_store.go](mgpusim_home/mgpusim/coherence/finite_store.go) must honour per-entry-kind
  way caps inside each set.
- **Eviction policy**: defaults to LRU (MGD original). FIFO is available via
  `DirectoryConfig.EvictionPolicy = EvictionFIFO` (see §M2 below).

Parameterisation of the coarse region size (1K / 4K / 8K) selects between DGD-1K / -4K / -8K
at CLI `-directory=dgdNk`.

### C2. `-directory=ideal` reuses PlainVIDirectory

Rather than adding a redundant "ideal infinite" path to the new types, the `cmd/m6/runner.go`
factory function returns the existing `coherence.PlainVIDirectory` when `-directory=ideal`.
This guarantees bit-identical behaviour to M1 and gives us a free sanity check (same code path
as [cmd/m1/runner.go](mgpusim_home/mgpusim/cmd/m1/runner.go)). The `ideal` config does NOT
apply iso-storage — it is the per-workload upper bound used in M6-4.

### C3. Hierarchical 4-way uniform sub-entry law (β confirmed)

> **주의**: M1 static sweep은 sub-entry 없는 flat directory이다. Superdirectory의
> 4-sub-entry 구조는 PHASE 2 P1 iso-storage 비교에서만 적용된다. M1 trace를 PHASE 0
> offline analysis에 사용할 때 sub-entry 히스토그램을 추정하지 말 것.

β 해석(2026-04-20 user-confirmed)에 따라 `s_k`(sub-entry 추적 단위)와 `c_k`(엔트리 coverage)를 구별한다.
Invariant V8: `∀k: c_k = 4·s_k ∧ s_4 = DefaultBlockSizeBytes(64B) ∧ c_0 ≤ PageSize(64KB)`.

| Bank k  | Coverage c_k | Sub-entry s_k | 설명 |
|---------|--------------|---------------|------|
| Bank 0  | 64 KB        | 16 KB         | 최상위 regional tracking |
| Bank 1  | 16 KB        | 4 KB          |   |
| Bank 2  | 4 KB         | 1 KB          |   |
| Bank 3  | 1 KB         | 256 B         |   |
| Bank 4  | 256 B        | 64 B          | s_4=blockSize; 4-way law 유지 (Reviewer R-Q3 대응) |

각 sub-entry는 고유 sharer bit-vector를 유지한다. Sub-entry 간 sharer 집합이 분기하면 coarse
entry는 유지되지만 sub-entry vector가 달라진다 — 이 현상이 H3가 측정하는 대상이며 dual-grain이
표현할 수 없는 signal이다. `EnableSubEntries=false`는 "Superdir-w/o-SubEntry" ablation.

### C4. Bit-based iso-storage with three policies (A primary)

[coherence/bit_budget.go](mgpusim_home/mgpusim/coherence/bit_budget.go) computes entry bit
costs exactly per type. Superdir (β) per-entry cost is bank-indexed:

```
base_bits[k]        = PHYS_ADDR_BITS - log2(c_k)            # tag bits for Bank k
sub_entry_bits[k]   = 4 × ((N_gpus - 1) + 1 + STATE_BITS)   # 4 sub-entries per entry,
                                                            #   each holds sharer vector (N-1),
                                                            #   owner bit (1), state (STATE_BITS)
total_per_entry[k]  = base_bits[k] + sub_entry_bits[k] + BANK_ID_BITS
```

For the default configuration (N_gpus=4, PHYS_ADDR_BITS=40, STATE_BITS=2, BANK_ID_BITS=3):

| Bank k | c_k   | base_bits | sub_entry_bits | total_per_entry |
|--------|-------|-----------|----------------|-----------------|
| 0      | 64 KB | 24        | 24             | 51              |
| 1      | 16 KB | 26        | 24             | 53              |
| 2      | 4 KB  | 28        | 24             | 55              |
| 3      | 1 KB  | 30        | 24             | 57              |
| 4      | 256 B | 32        | 24             | 59              |

Other directory types:
- Block entry bits = `tag_bits + valid + dirty + N_gpus` (sharer vector).
- DGD region entry bits = `tag_bits + valid + log2(N_gpus) + cachelines_per_region`.

Three allocation policies expose `-iso-policy={A|B|C}`:
- **Policy A (primary)** — **Equal total bits** across all variants. Each variant's total
  stored metadata bits equal the baseline's `block_entries × block_entry_bits`. Way/set counts
  are derived to hit this budget.
- **Policy B** — Equal block-entry count. Variants have the same number of leaf block
  entries; coarse entries are added on top (gives DGD/Superdir a storage advantage).
- **Policy C** — Equal coverage. Sets/ways sized so that working-set coverage in bytes is
  equal (used for reference only).

Main M6-4 evaluation uses **Policy A**. B and C are reported in supplementary / ablation.

The CLI command `cmd/m6 -print-budget` prints per-variant bit totals and the derived
`(sets, ways, region_way_ratio)` — all must match within ±1% of the baseline total bits.

---

## Major issues addressed

### M1. FIFO + LRU dual support

`DirectoryConfig.EvictionPolicy EvictionPolicy` (new enum: `EvictionLRU`, `EvictionFIFO`).
Both policies implemented in [finite_store.go](mgpusim_home/mgpusim/coherence/finite_store.go).
Main M6-4 uses **LRU** (MGD original and strongest baseline). **FIFO** is swept in Ablation
A9 (PHASE 3) to verify robustness — the M6 sweep exposes `-eviction={lru|fifo}` so both
configurations can be generated from the same runner.

### M2. Region-aware MSHR for DGD + multi-grain

Superdirectory's region-aware MSHR (§3 of the Superdirectory proposal) must also be available
to DGD for fairness (per motivation plan §3.2 bullet 4). Implementation:

- [coherence/region_mshr.go](mgpusim_home/mgpusim/coherence/region_mshr.go) — a coalesced MSHR
  keyed by the coarsest active region tag.
- When a finer block miss hits a region currently being fetched, it attaches as a secondary
  miss (no new memory request).
- DGD uses the coarse region bank's tag; multi-grain uses the coarsest bank that contains a
  valid or in-flight entry; baseline uses block-grain (no coalescing).
- Wired through MGPUSim's L2 miss path via a new hook point `HookPosMissAttach` (akita addition
  guarded behind a build tag so M1 is unaffected). If adding a hook to akita is infeasible,
  fall back to intercepting L2 misses in the coherence layer only — document the limitation.

### M3. M6-2 offline oracle analysis

Phase-adaptive oracle is computed **offline** from Parquet traces rather than by running
additional on-the-fly switching experiments:

- [cmd/m6offline/main.go](mgpusim_home/mgpusim/cmd/m6offline/main.go) loads per-phase Parquet
  rows for DGD-1K, DGD-4K, DGD-8K, Superdir, and baseline, and emits:
  - Per-phase "best region size" trace (the oracle).
  - Oracle-vs-fixed-best gap per workload.
- This avoids adding dynamic-switching support to the on-line directory types during PHASE 2
  and keeps that complexity out of the critical path. Dynamic switching moves to Ablation A9
  (PHASE 3) if needed.

### M4. ML workload availability pre-check

Before wiring ML workloads (Transformer attention, Batched GEMM) into `cmd/m6/workloads.go`,
run a one-shot check:

```
find mgpusim_home/mgpusim/amd/benchmarks -iname '*attention*' -o -iname '*transformer*' -o -iname '*gemm*batch*'
```

Current `find` of [amd/benchmarks/](mgpusim_home/mgpusim/amd/benchmarks/) from Phase 1
exploration did NOT surface ML-specific benchmarks (dnn/ subdir exists but needs
inspection). **Decision rule**:
- If suitable ML kernels exist → add them to the sweep set.
- If not → document absence in limitations, stick with the 15 classical workloads, and
  optionally evaluate a single hand-written batched GEMM via existing matrixmultiplication.
- Do NOT block PHASE 2 Main Evaluation on unavailable ML benchmarks.

---

## Workload registration (§Step 6, extended)

Add to a new `setupWorkload` switch in [cmd/m6/workloads.go](mgpusim_home/mgpusim/cmd/m6/workloads.go):
simpleconvolution, matrixmultiplication, bitonicsort, nbody, matrixtranspose,
fastwalshtransform, floydwarshall, fir, kmeans, aes, pagerank, bfs, fft, spmv, stencil2d, nw
— plus any ML workloads that pass §M4. Each case instantiates the benchmark from
[amd/benchmarks/](mgpusim_home/mgpusim/amd/benchmarks/) with default sizes; a
`-workload-params` override supports the size-sweep variants needed for M6-2 phase analysis.

---

## Schedule (revised)

| Experiment | Phase | Dependencies |
|------------|-------|--------------|
| **M6-3** (sub-region sharer divergence) | **PHASE 0** | Only the existing M1 64B baseline Parquet trace — offline analysis via `cmd/m6offline`. No DGD needed. |
| DGD MGPUSim implementation + unit tests | PHASE 1 extended (1 wk) | After REC replication |
| DGD reproducibility check (§5.2) | PHASE 1 extended (3 d) | DGD impl |
| Multi-grain + bit-budget + region-MSHR | PHASE 1 extended (1 wk) | DGD impl landed |
| M6-1 (workload diversity) | PHASE 2 (4 d) | DGD variants implemented |
| M6-2 (phase-level, offline) | PHASE 2 (4 d) | M6-1 Parquet output |
| M6-4 (direct perf comparison) | PHASE 2 Main (5 d) | All directory types |
| M6-5 (false-inv analysis) | PHASE 3 (3 d) | M6-4 done |

M6-3 moving to PHASE 0 unblocks motivation data for the paper's first pass without waiting on
the DGD implementation path.

---

## Critical files

- [coherence/directory.go](mgpusim_home/mgpusim/coherence/directory.go) — add
  `CoarseRegionSizeBytes`, `RegionSizes []uint64`, `FiniteBitBudget`, `Ways`, `Sets`,
  `EnableSubEntries`, `DGDRegionWayRatio`, `EvictionPolicy`, `IsoPolicy`; extend
  `DirectoryStats` with `FalseInvalidations`, `SubEntrySplits`, `RegionPromotions`.
- [coherence/plain_vi.go](mgpusim_home/mgpusim/coherence/plain_vi.go) — only add new
  `SharerEventKind` constants (no behaviour change); reused unchanged by `-directory=ideal`.
- [instrument/adapter/directory_adapter.go](mgpusim_home/mgpusim/instrument/adapter/directory_adapter.go) —
  route new event kinds into metrics.
- **New** (non-exhaustive): `coherence/{dgd,multigrain,finite_store,bit_budget,false_inv_counter,region_mshr}.go`,
  `cmd/m6/{main,config,runner,workloads,iso_storage,mgd_repro}.go`,
  `cmd/m6offline/main.go`, plus matching `*_test.go`.

---

## Verification

1. `go test ./coherence/... ./instrument/...` — all existing M1 tests still pass; new
   directory-impl and bit-budget tests pass.
2. **M1 regression**: run the original `cmd/m1` binary on `simpleconvolution` and diff Parquet
   output against a golden file — must be byte-identical.
3. **`-directory=ideal` equivalence**: run `cmd/m6 -directory=ideal` and diff against the M1
   golden. Must be identical (proves PlainVI reuse is correct).
4. **Coherence safety regression**: replay a recorded access trace through PlainVI / DGD /
   Superdir; per-block final sharer sets must match PlainVI exactly (modulo representation).
5. **MGD reproduction sanity gate** (redefined): run `cmd/m6 -mode=mgd-repro` with
   `-dgd-region-way-ratio=0.5` on 3 pilot workloads, single GPU. **Pass criterion**: DGD
   exhibits **≥10% directory-entry reduction vs the 64B baseline** on at least 2 of the 3
   workloads — this is a **sanity check that the DGD impl is not broken**, not a match against
   Zebchuk's 41–66% figure. Zebchuk's range is from CPU SPEC/PARSEC workloads; GPU workloads
   may show materially less reduction.
   - If the gap vs Zebchuk is large (e.g. GPU reduction ≪ 41%), this is **not a reproduction
     failure** — it is potential indirect H1/H2 evidence ("GPU workload sharing patterns
     don't compress into region entries as cleanly as CPU workloads") and should be recorded
     as a motivation data point.
   - If ALL 3 pilot workloads show <10% reduction, invoke the Contingency plan below.
6. **Bit-exact iso-storage**: `cmd/m6 -print-budget` prints per-variant bit totals and
   derived (sets, ways) tuples. Policy A totals must be equal within ±1% across all variants.
7. **M6-3 offline**: `cmd/m6offline -mode=sub-region-divergence` on the M1 64B trace produces
   the Case A / Case B histogram; manual sanity check that % values are reasonable.
8. **Pilot sweep**: 3 workloads × 5 directory configs × 1 seed × (LRU, FIFO) → ≤60 min wall
   time. Inspect per-phase optimal-region-size trace before launching the full sweep.

---

## Contingency plan — MGD reproduction failure

If §Verification 5 fails (all 3 pilot workloads show <10% entry reduction at
`-dgd-region-way-ratio=0.5`), apply the following **sequential** responses. Do not skip
steps — each step tests a distinct hypothesis about why reproduction failed.

**Step (a) — Raise the region way ratio.** Re-run the sanity gate at ratios 0.625 and 0.75.
Rationale: some GPU working sets may require more region-entry headroom before single-sharer
regions appear. If ≥10% reduction appears at a higher ratio, continue the M6 sweep with two
DGD configurations (`0.5` as the strict Zebchuk reproduction and the ratio that passed as the
"GPU-tuned DGD"), and report both in the paper.

**Step (b) — Add optional block→region compression.** MGD is monotonic (no merge); the
motivation plan §5.1 followed this. If step (a) fails, extend DGD with an optional merge rule
(`DirectoryConfig.DGDEnableMerge=true`): on block-entry eviction, if all surviving block
entries in the region share a single sharer, merge into a region entry. This is a deviation
from the original paper and must be clearly labelled as *"DGD+merge (our extension)"* in the
paper and in the config variant name. Re-run the sanity gate.

**Step (c) — Negative result.** If both (a) and (b) fail to produce ≥10% reduction on any
workload, treat the result as **positive evidence that GPU workload sharing patterns do not
compress into coarse regions the way CPU workloads do**. Document explicitly in the paper's
Limitations / Discussion section:

- The exact ratios and merge settings tried.
- Per-workload reduction numbers, however small.
- The conclusion that DGD's CPU-era compression advantage does not transfer to multi-GPU.
- This outcome is compatible with Superdirectory's thesis (dual-grain is not just insufficient
  — it may not even provide its original benefit on GPU).

Do NOT silently drop DGD from the evaluation. A failing DGD is still a data point, reported
honestly per the motivation plan's §10 ethics clause.

---

## Open items before implementation starts

1. **Copy `design_document.md` into workspace on Day 0** — the sub-entry grain rule
   (bank RegionSize/4, §C3) and any Superdirectory structural details referenced in this
   plan come from user instruction. Before any code is written, the doc must be present in
   `/root/mgpusim_home/` (or equivalent) and cross-checked against this plan's §C3. Block
   implementation kick-off on this.
2. **Fetch Zebchuk et al. MICRO 2013 §3.3** to confirm the exact region:block way ratio
   (§N1). Default remains 0.5 in this plan; revise if the paper specifies differently.
3. **PHASE 1 Week 1 Day 1 tasks** (explicitly scheduled, must happen before any coherence/
   code is written):
   - **akita hook feasibility study**: inspect akita's L2 miss path to confirm
     `HookPosMissAttach` can be added cleanly for region-aware MSHR (§M2). If not feasible,
     fall back to coherence-layer interception and record the limitation.
   - **ML workload grep**: execute the §M4 find command across
     [amd/benchmarks/](mgpusim_home/mgpusim/amd/benchmarks/) (including `dnn/` and `mccl/`)
     and decide ML inclusion per §M4's decision rule.
4. **Locate and commit** any pre-existing project analysis files (`CPU_Prior_Work_Analysis.md`,
   `experiment_plan.md`, `HPCA2027_Superdirectory_논문작성계획서.md`) referenced by the
   motivation plan into the workspace for consistency.
