# Cross-Model OP5a/OP5b Audit — Phase C-1

This audit determines whether the OP5a (correctness) and OP5b (fidelity) deviations identified in REC also exist in the other directory variants used in this codebase. Output drives the per-issue, per-model fix queue in [Phase C-2](#phase-c-2-fix-queue) — no fixes are made in this phase.

**Scope:**
- `optdirectory` — backs the runner's `CoherenceDirectory` (Baseline CD, model-id 0), `LargeBlockCache` (id 1), and `HMG` (id 4). Confirmed in [`amd/samples/runner/timingconfig/r9nano/builder.go:847-1017`](../mgpusim/amd/samples/runner/timingconfig/r9nano/builder.go#L847).
- `REC` — backs `REC` (id 3). Already audited in `rec_implementation_audit.md`; included here for cross-comparison.
- `superdirectory` — backs `SuperDirectory` (id 2).

**HMG / CD_4 question:** The runner exposes only one HMG path, which uses `optdirectory` with a different config tweak. If "CD_4" in the user's task brief refers to "CD with log2NumSubEntry=4" (or any other optdirectory variant), it shares the same code paths and therefore the same fix profile as Baseline CD. **Confirm before Phase D** whether CD_4 means the optdirectory variant or some other setup; this audit assumes it equals optdirectory.

---

## C1.1 Code-Sharing Structure

### Inter-package import graph

A cross-package grep (`grep -h '^	"' */* | grep akita.*cache | sort -u`) confirms each model is **standalone**:

```
REC/             → imports REC/internal           (no import of optdirectory or superdirectory)
optdirectory/    → imports optdirectory/internal  (no import of REC or superdirectory)
superdirectory/  → imports superdirectory/internal (no import of REC or optdirectory)
```

All three additionally import `akita/v4/sim`, `mem`, `mem/vm`, `pipelining`, `tracing` — generic infrastructure, **not** coherence logic.

**Implication:** A change in any one model's `directorystage.go` / `bankstage.go` does **not** propagate to the others. Each fix must be made independently in each model's own files. The Korean comments and parallel file structure make it obvious that REC and superdirectory were forked from optdirectory; the divergent OP5b behaviour (see §C1.3) confirms they have since drifted.

### Per-model role-of-file mapping

| File pattern in each pkg     | Role                                                                                                                     |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `topparser.go`               | Routes incoming `ReadReq`/`WriteReq`/`InvReq`/`InvRsp`. Decides bypass vs. directory-pipeline.                           |
| `directorystage.go`          | Lookup-and-decide stage. Houses `doWriteHit`, `doWriteMiss`, `writePermission` — the **OP5a decision points**.            |
| `bankstage.go`               | Mutates entry/sub-entry bits per `trans.action`. Houses `InvalidateAndUpdateEntry` — the **OP5b mutation points**.       |
| `bottomSender.go`            | Builds and ships `InvReq` messages; filters out writer-self from the invalidation target list.                           |
| `internal/directory.go`      | Storage class (`Block` for optdirectory, `CohEntry` for REC and superdirectory).                                         |
| `internal/victimfinder.go`   | Replacement policy.                                                                                                      |

The OP5a code path in every model is `topparser → directorystage.doWrite → doWriteHit → writePermission`. The OP5b code path is `... → InvalidateAndUpdateEntry (in bankstage)`. These two control points are the audit's focus.

---

## C1.2 OP5a Per-Model Matrix

OP5a = "Local write, hit on a valid offset, ≤1 sharer that is *not* the writer" → does the model send an invalidation, or skip it?

Paper expectation: invalidate. Spec ref: [`rec_paper_spec.md` OP5a](rec_paper_spec.md#op5a--local-write-home-gpu-writes-its-own-data) and the underlying §2.3 baseline statement: "Local writes to data mapped to the home GPU memory look up the directory … If found, invalidations are propagated to the recorded sharers in the background, and the directory entry becomes invalid."

| Model                        | OP5a code path                                                                                                                                                                                                                                                                                                                                                       | Has shortcut?              | Causes silent stale?     | Verdict                       |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- | ------------------------ | ----------------------------- |
| **Baseline CD / HMG**<br>(`optdirectory`) | `directoryStage.writePermission` at [optdirectory/directorystage.go:367-383](../akita/mem/cache/optdirectory/directorystage.go#L367-L383): `} else { // local access\n\tif len(sharer) > 1 { return false }\n\treturn true\n}`                                                                                                                                       | **YES** (line 376-382)     | **YES**                  | **FIX_NEEDED**                |
| **REC**                      | `directoryStage.writePermission` at [REC/directorystage.go:434-456](../akita/mem/cache/REC/directorystage.go#L434-L456): `} else { // local access\n\tif len(sharer) > 1 { return false }\n\treturn true\n}` (identical pattern, copied)                                                                                                                            | **YES** (line 449-455)     | **YES** (Phase B confirmed) | **FIX_NEEDED**                |
| **Superdirectory**           | `directoryStage.writePermission` at [superdirectory/directorystage.go:817-839](../akita/mem/cache/superdirectory/directorystage.go#L817-L839): `} else { // local access\n\tif len(sharer) > 1 { return false }\n\treturn true\n}` (identical pattern, copied)                                                                                                       | **YES** (line 832-838)     | **YES**                  | **FIX_NEEDED**                |

**Cross-model finding:** All three models share the **identical** OP5a flaw — the same three lines of code, copy-pasted. When local-writes hit an entry with exactly one sharer who is not the writer (e.g., `[GPU1.RDMA]` after a remote read by GPU1, with the home GPU now writing locally), `writePermission` returns true → `trans.action = Nothing` → the invalidation message is never built and the directory's sharer list is not cleared. GPU1 retains a stale L2 line.

**Severity for comparison fairness:** all three models have the *same* under-counting of write-initiated invalidations (specifically, exactly-one-non-writer cases), so per-model invalidation totals are biased downward by the same systematic amount. This means the *relative* comparison between models is approximately preserved, but the **absolute** counts (and the absolute IPC delta vs. an idealised oracle) understate the cost of the missing invalidations. Workloads dominated by single-reader-then-home-write patterns will show the worst absolute distortion.

### How the bug manifests in code (worked walk-through, optdirectory)

1. Remote GPU1 issues a read of address `A`, home GPU0 directory:
   - `doWriteMiss` → `InsertNewEntry` → `block.Sharer = [GPU1.RDMA]`.
2. Home GPU0 issues a local write to address `A`:
   - `doWriteHit` → `writePermission(trans, [GPU1.RDMA])`.
   - `!fromLocal`? **false** (local). Falls to the local branch.
   - `len(sharer) > 1`? **false** (it's 1). Returns **true**.
   - `trans.action = Nothing`.
   - In the `Nothing` branch (line 235-249), the trans is pushed to `bottomSenderBuffer`; `bottomSender.processNewTransaction` for `Nothing` calls `sendRequestToBottom` (data write to DRAM), **not** `sendInvalidationRequest`.
3. GPU1's L2 still holds the old value. No `InvReq` was ever sent. Subsequent reads on GPU1 hit stale data.

REC and superdirectory have the same path; only the file:line numbers differ.

### Counter to add for measurement (PHASE C-2 requirement)

A new counter `writes_with_sole_sharer_writer_count` (better named **`local_writes_skipped_with_remote_sharer`**) should be incremented in the OP5a hit path **before** the `writePermission` shortcut so the pre-fix and post-fix counts can be compared. Implementation:

```go
// Inside doWriteHit, after subEntry sharer is fetched, before writePermission:
if trans.fromLocal && len(subEntry.Sharer) == 1 &&
        subEntry.Sharer[0] != trans.accessReq().GetSrcRDMA() {
    ds.cache.localWriteSkipsWithRemoteSharerCount++
}
```

Each model adds the counter in its own `directorystage.go`. PHASE C-2 commits report this count before/after.

---

## C1.3 OP5b Per-Model Matrix

OP5b = "Remote write, hit on an entry with the target offset valid, multiple sharers including remotes other than the writer" → after invalidation, does the writer remain as a recorded sharer with the position bit still set?

Paper expectation: yes. Set the source GPU's sharer bit, clear every other sharer bit, send invalidation to each *cleared* sharer, **leave the position bit set and the entry valid**. Spec ref: [`rec_paper_spec.md` OP5b](rec_paper_spec.md#op5b--remote-write-some-other-gpu-writes-to-home-gpus-data) (REC paper §4.2 "Remote writes", p. 7).

| Model                        | OP5b code path (`InvalidateAndUpdateEntry`)                                                                                                                                                                                                                                                                                                                       | Clears writer's sharer bit? | Invalidates whole entry? | Verdict                                                                                          |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------ |
| **Baseline CD / HMG**<br>(`optdirectory`) | [optdirectory/bankstage.go:324-343](../akita/mem/cache/optdirectory/bankstage.go#L324-L343): `blk.Sharer = []sim.RemotePort{trans.accessReq().GetSrcRDMA()}` — explicitly sets writer as sole sharer. `Visit(blk)` keeps it MRU. `IsLocked = false`. **`blk.IsValid` is left `true`** (no clearing logic).                                                            | **NO**                      | **NO**                   | **NO_DEVIATION** — paper-correct.                                                                |
| **REC**                      | [REC/bankstage.go:336-367](../akita/mem/cache/REC/bankstage.go#L336-L367): `entry.Sharer = nil; entry.IsValid = false; entry.ReadCount = 0` — clears writer too; sets sub-entry's position bit invalid. Then `if !blk.IsValidEntry() { blk.IsValid = false; … }` may transition the **entire region** entry → invalid when the cleared offset was the last live one. | **YES**                     | **POSSIBLE** (last-offset case) | **FIX_NEEDED** — Phase B confirmed.                                                              |
| **Superdirectory**           | [superdirectory/bankstage.go:333-361](../akita/mem/cache/superdirectory/bankstage.go#L333-L361): two paths controlled by `trans.bankID == numBanks-1`. **Path A (lowest/finest bank, line 339-345):** `entry.Sharer = [writer]; entry.IsValid = true; blk.IsValid = true; needToDemotion = false`. **Path B (coarser banks, line 347-355):** `entry.Sharer = nil; entry.IsValid = false; needToDemotion = true` — triggers a follow-up `EvictAndDemotionEntry` action that re-creates the entry at a finer bank ([directorystage.go:358](../akita/mem/cache/superdirectory/directorystage.go#L358), [bankstage.go:407 FinalizeDemotionEntry](../akita/mem/cache/superdirectory/bankstage.go#L407)).             | Path A: **NO**. Path B: **YES** (intentional — followed by demotion).  | Path A: **NO**. Path B: **YES** (followed by re-allocation at finer granularity). | **NO_DEVIATION (PROTOCOL-INTENTIONAL)** — paper-correct at the lowest bank; coarser banks demote *by design* (see Justification below).  |

### Superdirectory N/A justification

Superdirectory is a multi-bank hierarchical design (banks ordered finest → coarsest at `[0]`…`[numBanks-1]`). On a remote-write hit at a coarse bank, the protocol's **intentional** response is to demote the entry to a finer bank (the `needToDemotion=true` path). This preserves the writer's information in the eventual finer-bank entry produced by `FinalizeDemotionEntry`. Treating this as an OP5b deviation would conflate "paper REC OP5b" with "superdirectory's own coarsening/demotion protocol", which would be incorrect — superdirectory is not required to follow REC's OP5b verbatim.

**Caveat for fairness:** For the comparison against REC and Baseline to be honest, superdirectory's demotion path **must** ultimately leave the writer as a tracked sharer of the finer-bank entry (otherwise it has the same fidelity loss as REC's OP5b bug). A spot-check of `FinalizeDemotionEntry` confirms it sets `blk.SubEntry[index].IsValid = true` and `IsLocked = false` ([bankstage.go:384-385](../akita/mem/cache/superdirectory/bankstage.go#L384-L385)) and the demotion plumbing in `EvictAndDemotionEntry` re-records the writer as the source-RDMA sharer in the demoted entry. Full verification of this chain is outside this audit's scope but should be a Phase C-3 check if any divergence is found.

### Counter to add for measurement (PHASE C-2 requirement)

A new counter `writes_clearing_writer_sharer_bit_count` (better named **`remote_write_hit_cleared_writer_count`**) should be incremented in the OP5b path **only when the bug actually fires**:

```go
// Inside InvalidateAndUpdateEntry's "clear writer" branch:
if /* this is the sub-entry that was the writer's */ {
    s.cache.remoteWriteHitClearedWriterCount++
}
```

For optdirectory, this counter must remain **0** at all times (the code never clears the writer). For REC, it should be non-zero pre-fix and 0 post-fix. For superdirectory, it should be 0 in Path A; Path B clears the writer by intent, and should be tracked under a separate counter `remote_write_hit_demoted_count` to keep accounting clean.

---

## Phase C-2 Fix Queue

The audit produces the following ordered queue. Each row is one commit. **Skipped rows** are marked with their justification and contribute zero commits.

| # | Issue | Model         | Plan                                                                                                                                                                                  | Will produce a commit? |
| - | ----- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| 1 | OP5a  | REC           | Add failing regression test (`TestREC_OP5a_LocalWriteSingleRemoteSharer`); fix `writePermission` for local writes to invalidate any non-writer sharer; verify counter delta.           | **YES**                |
| 2 | OP5a  | Baseline CD   | Add failing regression test in `optdirectory/`; same fix pattern in `optdirectory/directorystage.go:367-383`; verify counter delta. Same fix automatically covers HMG (model id 4).   | **YES**                |
| 3 | OP5a  | Superdirectory| Add failing regression test in `superdirectory/`; same fix pattern in `superdirectory/directorystage.go:817-839`; verify counter delta.                                                | **YES**                |
| 4 | OP5b  | REC           | Add failing regression test (`TestREC_OP5b_RemoteWriteHitWriterSurvives`); modify `bankstage.InvalidateAndUpdateEntry` to set `entry.Sharer = [writer]` and keep `entry.IsValid = true` instead of clearing both; preserve current "InvalidateAndUpdateEntry transitions to invalid only when no other sub-entry is valid" semantics for the local-write case via a new action distinguishing remote-write hit from local-write hit. | **YES**                |
| 5 | OP5b  | Baseline CD   | **SKIP — NO_DEVIATION.** `optdirectory/bankstage.go:326` already does `blk.Sharer = []sim.RemotePort{writer}` with no entry-clearing path. Verified by inspection of the sole `InvalidateAndUpdateEntry` body.  | **NO**                 |
| 6 | OP5b  | Superdirectory| **SKIP — NO_DEVIATION (PROTOCOL-INTENTIONAL).** Path A (lowest bank) is paper-correct; Path B (coarser banks) demotes by design. Add a *non-failing* sanity test that verifies Path A's writer-survives invariant; that test is informational, not a fix.                                                          | **NO** (or 1 informational test commit, at user's discretion) |

**Total commits expected:** 4 (or 5 if the superdirectory informational test is included).

The ordering enforces the rules from the user brief: OP5a (correctness) before OP5b (fidelity); within each issue, REC first (paper spec is most precise) → Baseline → Superdirectory.

---

## Phase C-3 Cross-Model Regression Plan (preview)

After all fixes:

| Model            | Core micro-test                                                                                                       |
| ---------------- | --------------------------------------------------------------------------------------------------------------------- |
| Baseline CD      | Add `optdirectory/directory_microtest_test.go`: 3 remote reads to *different* lines, 1 entry per line, 0 evictions.   |
| REC              | `TestREC_OP1_CoalescingMicrotest` (added in PHASE B); must still PASS after fixes.                                    |
| Superdirectory   | Add `superdirectory/directory_microtest_test.go`: insertion + Visit-LRU sanity (no full protocol re-test).            |

Plus all pre-existing tests:
- REC `bankstage_test.go` (9 cases) — must still PASS.
- optdirectory `directory_test.go`, `cache_suite_test.go` — must still PASS.
- superdirectory `directorystage_test.go`, `latency_test.go`, `event_log_test.go` — must still PASS.

Phase C-3 deliverable (`analysis/cross_model_parity.md`) will record the parity matrix with FIXED/N/A per cell and the regression-test pass list.

---

## Open question for the user (gate to Phase C-2)

1. **CD_4 confirmation.** The user's brief mentions "CD_4". This audit assumes it's a `coherenceDirectory=0` (CoherenceDirectory) variant of `optdirectory` with a specific config (perhaps `log2NumSubEntry=4`, perhaps "CD with 4 GPUs"). If CD_4 is in fact a separate code path I haven't located, the OP5a/b coverage above is incomplete. **Please confirm** what backs CD_4 before Phase C-2 begins.

2. **Approval to proceed with the 4-commit plan above** (or 5 with the superdirectory informational test).

3. **OP5b for REC fix scope.** The cleanest fix introduces a new bank action distinguishing "remote write hit on valid offset" (writer survives) from "local write hit on valid offset" (writer is the home and is excluded from sharer set). This adds a new value to the `actionType` enum and a new method on bankstage. Acceptable, or prefer a flag-on-existing-action approach to minimise API churn?
