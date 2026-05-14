# REC Implementation Audit — Phase B

This audit cross-checks the current REC implementation against the contract in `analysis/rec_paper_spec.md`. Every claim is anchored to a `file:line` citation.

**Implementation root:** `/root/mgpusim_home/akita/mem/cache/REC/`

**Conclusion (TL;DR):**
- Five of the six paper-mandated operations (OP1, OP2, OP3, OP4, OP6) match the spec — including the three previously-known bugs (Bug 1 dead-Lookup, Bug 2 missing IsValid, Bug 3 zombie entry) which are **already fixed** and covered by passing unit tests.
- **OP5b (remote-write hit on valid offset) materially deviates from the paper.** The implementation clears all sharers including the writer and marks the offset invalid; the paper says only other sharers should be cleared and the writer should remain as the sole sharer with the position bit still set.
- **OP5a (local-write hit, ≤1 sharer) silently skips invalidation** when the lone sharer is *not* the writer. The paper requires the invalidation to fire.
- **OP4 broadcast iterates all 16 sub-entries blindly**, but is saved by the inner-loop `len(Sharer)>0` filter from sending spurious messages — correct behaviour, fragile code.
- B4 micro-test (newly added in this audit, see [§B4](#b4-sanity-micro-test)) **PASSES**: a single-region 3-address remote-read sequence yields exactly one entry with three valid position bits and the source GPU recorded in each.

---

## B1. REC File Inventory

| File                                             | Role                                                                                                              |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| `internal/directory.go`                          | Authoritative `RECDirectoryImpl`: set-associative storage, `Lookup`, `FindVictim`, `Visit` (LRU bookkeeping).     |
| `internal/victimfinder.go`                       | `LRUVictimFinder` — picks an invalid entry first, else first non-locked, else `LRUQueue[0]`.                      |
| `internal/mshr.go`                               | MSHR keyed at 64 B granularity (line, not region).                                                                |
| `internal/regionSizeBuffer.go` / `bloomfilter.go`| Auxiliary structures (region-size adaptation in superdirectory variant; not consulted by the REC paper protocol). |
| `topparser.go`                                   | Routes incoming requests: classifies fromLocal / toLocal; bypasses directory for local reads + remote-data reads. |
| `directorystage.go`                              | Directory pipeline: `doWrite` (the "incoming request handler"), `doWriteHit`, `doWriteMiss`, `writeToBank`.       |
| `bankstage.go`                                   | Mutates entry/sub-entry bits per `trans.action` (`InsertNewEntry`, `EvictAndInsertNewEntry`, `UpdateEntry`, `InvalidateAndUpdateEntry`, `InvalidateEntry`). |
| `bottomSender.go`                                | Sends DRAM fetch requests and per-(line, sharer) invalidation messages — implements OP4 broadcast and OP5 invalidations. |
| `mshrstage.go`                                   | MSHR follow-up handling for late responses.                                                                       |
| `transaction.go`                                 | Per-request state object (`fromLocal`, `toLocal`, `read`/`write`, `action`, `block`, `blockIdx`, `victim`).       |
| `flusher.go`                                     | Migration / flush handling; orthogonal to the per-request protocol.                                               |
| `builder.go`                                     | Wires `wayAssociativity`, `log2BlockSize`, `log2NumSubEntry`, `LRUVictimFinder`, half-set count comment.          |
| `bankstage_test.go`                              | Pre-existing unit tests demonstrating Bug 1/2/3 and their fixes.                                                  |
| `directory_microtest_test.go`                    | **New**, written for this audit's B4: directory-level OP1 coalescing micro-test.                                  |

---

## B2. Entry Struct vs Paper Layout

Paper layout per [`rec_paper_spec.md` A1](rec_paper_spec.md#a1-entry-layout-specification). Implementation's `CohEntry` lives at [internal/directory.go:23-32](../akita/mem/cache/REC/internal/directory.go#L23-L32). Field-by-field:

| Paper field            | Code field                                                       | File:Line                                                                                                                            | Match?      | Notes                                                                                                                                                                                                                                  |
| ---------------------- | ---------------------------------------------------------------- | -----------------------------------------------------------------------------------------------------------------------------------  | ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Valid bit (1 b)        | `CohEntry.IsValid bool`                                          | [internal/directory.go:30](../akita/mem/cache/REC/internal/directory.go#L30)                                                         | OK          | Cleared in `Reset()` and `InvalidateAndUpdateEntry` when the last live sub-entry departs.                                                                                                                                              |
| Base address (38 b)    | `CohEntry.Tag uint64`                                            | [internal/directory.go:26](../akita/mem/cache/REC/internal/directory.go#L26)                                                         | OK          | Stored as full 64-bit value; logical width = 48 − `log2BlockSize+log2NumSubEntry`. With log2Block=6, log2Sub=4 → 38 effective bits, matching paper. Set via `block.Tag = cachelineID >> maskLen << maskLen` ([directorystage.go:387](../akita/mem/cache/REC/directorystage.go#L387)). |
| Position bits (16)     | Per-slot `CohSubEntry.IsValid bool` × 16                         | [internal/directory.go:13-21](../akita/mem/cache/REC/internal/directory.go#L13-L21), [internal/directory.go:29](../akita/mem/cache/REC/internal/directory.go#L29) | OK (semantic) | Stored as 16 distinct booleans inside `SubEntry [16]CohSubEntry` (a fixed array). Logically equivalent to a 16-bit position vector; storage cost is wider than paper but functionally identical. |
| Sharer bits (16·(n−1)) | `CohSubEntry.Sharer []sim.RemotePort`                            | [internal/directory.go:17](../akita/mem/cache/REC/internal/directory.go#L17)                                                         | TYPE_MISMATCH (semantic-OK) | Stored as a Go slice of port handles, *not* a bit-vector of (n−1) bits per slot. Functionally equivalent for correctness; **does not enforce the paper's storage cost claim** (A4). The simulator counts entries, not bits, so this does not affect the directory-eviction count metric. |
| —                      | `CohSubEntry.IsDirty`, `IsLocked`, `ReadCount`, `VAddr`, `DirtyMask`, `Accessed` | [internal/directory.go:13-21](../akita/mem/cache/REC/internal/directory.go#L13-L21)                                                  | EXTRA       | Not in paper: pipelining bookkeeping (`IsLocked`, `ReadCount`), virtual address (`VAddr`), per-byte dirty mask, telemetry. None affects coherence semantics; needed by the `bankstage`/`mshrstage` machinery.                          |
| —                      | `CohEntry.WayID`, `SetID`, `CacheAddress`                        | [internal/directory.go:27-28](../akita/mem/cache/REC/internal/directory.go#L27-L28)                                                  | EXTRA       | Position-in-storage bookkeeping (helps `Visit` move the entry within `LRUQueue`).                                                                                                                                                      |
| —                      | `CohEntry.PID vm.PID`                                            | [internal/directory.go:24](../akita/mem/cache/REC/internal/directory.go#L24)                                                         | EXTRA       | Per-address-space tagging. Paper assumes a single physical address space.                                                                                                                                                              |

**Verdict:** Layout is **semantically equivalent**. Storage cost differs from paper because sharer slices grow on demand instead of using fixed `(n−1)` bits per slot. This is acceptable for a simulator — the coalescing/eviction *behaviour* is what determines invalidation counts and miss rates.

### Position bit calculation (A3) cross-check

Paper formula: `p = (Tag mod m / 64) × (n+1)` with `m=1024`, packing position+sharers into one bit-vector.

Implementation computes only the offset slot index, not a bit position, and stores sharers in a separate Go slice:

- Offset slot: `index = (addr >> log2BlockSize) % (1 << log2NumSubEntry)` ([directorystage.go:223](../akita/mem/cache/REC/directorystage.go#L223), [internal/directory.go:186](../akita/mem/cache/REC/internal/directory.go#L186)) — equivalent to `(addr mod 1024) / 64` for the configured constants.
- Sharer storage: `SubEntry[idx].Sharer []sim.RemotePort` — separate per-slot list, no `(n+1)` stride needed.

This is a faithful reformulation of the paper formula for the simulator's data model. It does not affect coalescing behaviour.

---

## B3. Operation-by-Operation Audit

For each of the six paper operations from [`rec_paper_spec.md` A2](rec_paper_spec.md#a2-operation-specifications), the table lists the code paths exercised, whether behaviour matches, and any discrepancy with citations.

### OP1 — Remote read, base matches existing entry (coalescing)

| Field                  | Citation                                                                                                                                |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------|
| Entry path             | `topparser.processReq` ([topparser.go:117](../akita/mem/cache/REC/topparser.go#L117)) routes `!fromLocal && toLocal` reads to `directoryStage`. |
| Lookup                 | `directorystage.doWrite` calls `directory.Lookup` ([directorystage.go:170](../akita/mem/cache/REC/directorystage.go#L170)). On region-match but sub-entry invalid, `Lookup` returns `(nil, -1)` ([internal/directory.go:187-189](../akita/mem/cache/REC/internal/directory.go#L187-L189)). On region-match AND sub-entry valid, it returns `(block, idx)`. |
| Hit, sub-entry valid   | `doWriteHit` ([directorystage.go:234](../akita/mem/cache/REC/directorystage.go#L234)) → `readPermission` decides; if requester is already a sharer → `action = Nothing` (skip directory mutation). Otherwise `action = UpdateEntry` → `bankstage.UpdateEntry` ([bankstage.go:297-334](../akita/mem/cache/REC/bankstage.go#L297-L334)) calls `appendSharer` (idempotent on duplicates). |
| Hit, sub-entry invalid | `Lookup` returns nil; falls into `doWriteMiss`; `FindVictim` returns existing entry with `alloc=false` ([internal/directory.go:202-206](../akita/mem/cache/REC/internal/directory.go#L202-L206)) → `action = UpdateEntry` ([directorystage.go:316](../akita/mem/cache/REC/directorystage.go#L316)). `writeToBank` flips this slot's `IsValid=true` and locks it ([directorystage.go:385-403](../akita/mem/cache/REC/directorystage.go#L385-L403)). |
| Behaviour matches?     | **YES.** Bitwise-OR semantics replicated by `appendSharer`'s idempotency; coalescing replicated by `FindVictim`'s region-first match. |
| Discrepancy            | None.                                                                                                                                   |

**Evidence:** `TestREC_MultiSharer_NoDuplication`, `TestREC_MultiSharer_TwoDistinctSharers`, `TestREC_OP1_CoalescingMicrotest` (B4 below) — all PASS.

### OP2 — Remote read, new base, free way available (entry insertion)

| Field              | Citation                                                                                                                                |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------|
| Code path          | `doWriteMiss` → `FindVictim` returns invalid entry with `alloc=true` (third return path: `victimFinder.FindVictim` picks first invalid block in `LRUQueue`, [internal/victimfinder.go:21-25](../akita/mem/cache/REC/internal/victimfinder.go#L21-L25)). `needEviction=false` ([directorystage.go:406-418](../akita/mem/cache/REC/directorystage.go#L406-L418)) → `action = InsertNewEntry` ([directorystage.go:335](../akita/mem/cache/REC/directorystage.go#L335)). `victim.Reset()` ([directorystage.go:349](../akita/mem/cache/REC/directorystage.go#L349)) wipes residual state; `writeToBank` then sets `Tag`, `IsValid`, and the slot's bits. |
| Behaviour matches? | **YES.** State invalid → valid as required.                                                                                             |
| Discrepancy        | Cosmetic: `evictingAddr = block.Tag + index*(1<<log2NumSubEntry)` ([directorystage.go:263](../akita/mem/cache/REC/directorystage.go#L263)) uses the wrong stride (`16`, not `64`). Field is set but **never read** anywhere (`grep evictingAddr` returns only assignments and the field declaration). Dead code; no functional impact. Should be removed or fixed for clarity. |

**Evidence:** `TestREC_InsertNewEntry_DoesNotSetSubEntryIsValid` PASSES (Bug 2 fixed).

### OP3 — Remote read, eviction-forcing replacement (LRU-like)

| Field              | Citation                                                                                                                                |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------|
| Code path          | `LRUVictimFinder.FindVictim` ([internal/victimfinder.go:18-34](../akita/mem/cache/REC/internal/victimfinder.go#L18-L34)) prefers invalid entries; then any non-locked entry; then `LRUQueue[0]` (the least-recently-`Visit`ed entry). `Visit` moves the entry to the end of `LRUQueue` ([internal/directory.go:224-235](../akita/mem/cache/REC/internal/directory.go#L224-L235)). |
| Replacement policy | **LRU**, matching paper §4.2 "REC adopts the replacement policy, similar to LRU".                                                       |
| Behaviour matches? | **YES.** This is the single biggest divergence from the user's task brief (which said "FIFO-based eviction"); the implementation correctly follows the paper, not the brief. |
| Discrepancy        | None vs paper. (Brief was wrong.)                                                                                                       |

### OP4 — Eviction broadcast (per-line, per-sharer invalidations)

| Field              | Citation                                                                                                                                |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------|
| Code path          | `doWriteMiss` → `needEviction(victim)` ([directorystage.go:406-418](../akita/mem/cache/REC/directorystage.go#L406-L418)) returns true iff any sub-entry has both `IsValid` and a non-empty sharer list. If so: `action = EvictAndInsertNewEntry`; victim is `DeepCopy`'d into `trans.victim` ([directorystage.go:330](../akita/mem/cache/REC/directorystage.go#L330)) so the bank can wipe the live entry while the bottom-sender broadcasts from the snapshot. `bottomSender.sendInvalidationRequest` ([bottomSender.go:282-423](../akita/mem/cache/REC/bottomSender.go#L282-L423)) iterates all 16 sub-entries and, for each non-empty sharer, builds an `InvReq` with `Address = victim.Tag + i<<log2BlockSize` and `DstRDMA = sh`. |
| Granularity        | Per 64 B cache line (i.e., per slot index `i`), per recorded sharer. **No range-broadcast.**                                            |
| Address recipe     | `addr = victim.Tag + uint64(i << blkSize)` with `blkSize = log2BlockSize = 6` ([bottomSender.go:362](../akita/mem/cache/REC/bottomSender.go#L362)). Stride is 64 B, matching A4 of the paper. |
| Behaviour matches? | **YES** — but the *iteration* visits all 16 slots regardless of sub-entry validity. This is harmless because the inner sharer loop is empty for invalid slots (no `Sharer` entries), so no spurious invalidations are sent. Fragile: if a future change ever populates `Sharer` on an invalid slot (e.g., the "defensive cleanup" path in OP5a), spurious sends would happen. |
| Discrepancy        | Iteration form is loose but observed behaviour is correct.                                                                              |

**Evidence:** `TestREC_InvalidateEntry_ClearsAllSubEntries` PASSES (full-eviction sub-entry clear); broadcast counters `actEvictInsert`, `invSentCount` are wired and emitted via the existing reports path.

### OP5a — Local write (home-GPU stores its own data)

| Field                      | Citation                                                                                                                                |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------|
| Code path                  | `topparser.processReq` routes `fromLocal && toLocal` writes to the directory ([topparser.go:140-184](../akita/mem/cache/REC/topparser.go#L140-L184)); `doWrite` → `doWriteHit` ([directorystage.go:234](../akita/mem/cache/REC/directorystage.go#L234)); `writePermission` decides, then either `Nothing` or `InvalidateAndUpdateEntry` → `bankstage.InvalidateAndUpdateEntry` ([bankstage.go:336-367](../akita/mem/cache/REC/bankstage.go#L336-L367)) → `bottomSender.sendInvalidationRequestByWrite` ([bottomSender.go:425-512](../akita/mem/cache/REC/bottomSender.go#L425-L512)). |
| Hit, partial invalidation  | `bankstage.InvalidateAndUpdateEntry` clears only `block.SubEntry[blockIdx].Sharer`, sets `block.SubEntry[blockIdx].IsValid=false`, and only sets `blk.IsValid=false` if `IsValidEntry()==false` (no other live sub-entry). Other sub-entries are untouched (apart from the defensive-cleanup pass that zeros sharer slices on already-invalid slots). |
| Last-offset transition     | `if !blk.IsValidEntry() { blk.IsValid = false; … }` ([bankstage.go:348](../akita/mem/cache/REC/bankstage.go#L348)) — entry → invalid. **Match.** |
| Miss                       | `doWriteMiss` early-returns with `action=Nothing` and no entry insertion ([directorystage.go:290-298](../akita/mem/cache/REC/directorystage.go#L290-L298)). **Match.**                                                |
| Behaviour matches?         | **PARTIAL.** Last-offset transition, partial invalidation, and miss handling all match. **The hit-with-≤1-sharer case is wrong (see Discrepancy).** |
| Discrepancy                | `writePermission` for local writes: `if len(sharer) > 1 { return false }; return true` ([directorystage.go:449-455](../akita/mem/cache/REC/directorystage.go#L449-L455)). When a local write hits an offset with exactly **one** sharer who is *not* the writer (it's a remote GPU that previously read this line), `writePermission` returns true → `action = Nothing` → **no invalidation is sent and the position bit is NOT cleared**. The remote GPU now has a stale L2 copy and the directory still records it. The paper says: "If found and the offset is valid, the invalidation request is generated and propagated to the recorded sharers immediately." Severity: silent coherence violation in the worst case (workloads where home GPU writes after a remote read of the same offset, with no other sharer). |

### OP5b — Remote write (some other GPU writes to home-GPU data)

| Field                       | Citation                                                                                                                                |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------|
| Hit, target offset invalid  | Cannot happen via `Lookup`/`doWriteHit` — `Lookup` returns nil when sub-entry invalid. Falls to `doWriteMiss` → `FindVictim` returns existing entry with `alloc=false` → `action = UpdateEntry` → `bankstage.UpdateEntry` adds writer as sharer, `IsValid=true`. **Match** (treats like OP1). |
| Hit, target offset valid    | `doWriteHit` → `writePermission` for remote: returns true only if sharer list is exactly `[requester]`. Otherwise `action = InvalidateAndUpdateEntry`. `bankstage.InvalidateAndUpdateEntry` then sets `entry.Sharer = nil` (clearing **everyone including the writer**), `entry.IsValid = false`. **Mismatch with paper.** |
| Miss                        | `doWriteMiss` for `!fromLocal` allocates via `FindVictim` → `InsertNewEntry` (or `EvictAndInsertNewEntry` if needEviction). `bankstage.InsertNewEntry` records writer as sharer. **Match.** |
| Behaviour matches?          | **PARTIAL.**                                                                                                                            |
| Discrepancy                 | Paper §4.2 "Remote writes" (p. 7): on a hit-with-valid-target-offset, the writer's sharer bit must remain set, the *other* sharers' bits must be cleared, and **the entry must remain valid**. Implementation instead clears the entire offset (writer included), and may transition the whole entry → invalid if this was the last live offset. Effects: (a) future invalidations to the writer are not generated even though the writer still caches the data via write-through; (b) directory loses the ability to enforce coherence on subsequent writes to the same line by yet another GPU; (c) under workloads with a write-then-read-by-writer pattern, the next read becomes a miss and refetches data the writer already has — minor performance loss unless the workload is dominated by this pattern. **Severity: moderate.** Correctness defensible if the writer is treated as always-cacheable and remote invalidations are conservative, but the directory will under-track sharers compared to the paper. |

### OP6 — Sharer GPU's L2 cache eviction notification

| Field              | Citation                                                                                                                                |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------|
| Trigger            | A sharer GPU's L2 cache evicts a clean line that the home GPU's directory still records as a sharer.                                    |
| Code path          | None. `topparser.processReq` only handles `mem.InvReq`, `mem.InvRsp`, `mem.ReadReq`, `mem.WriteReq` ([topparser.go:67-185](../akita/mem/cache/REC/topparser.go#L67-L185)) — there is no message type for "I evicted line X" sent from a sharer back to home. |
| Behaviour          | **Silent eviction.** Sharer-side evictions are not communicated to the home directory. The directory may carry stale sharer bits until the next write or directory-eviction event invalidates them. |
| Match?             | **YES (PAPER-AMBIGUOUS).** The paper does not specify a notification mechanism (see [`rec_paper_spec.md` A2 OP6](rec_paper_spec.md#op6--sharer-gpus-silent--non-silent-l2-eviction-notification)). Silent eviction is one of the two reviewer-defensible choices. Document the choice in any external write-up. |
| Discrepancy        | None vs paper. Note: this means OP4's eviction broadcasts will sometimes target sharers whose L2 already evicted the line — generating "harmless" invalidations that miss in the sharer's L2. The paper measures these (§3.2 "evict-initiated invalidations that hit in the sharer-side L2") so the simulator's behaviour is consistent with the methodology. |

---

## B3 Summary Table

| OP  | What                       | Match?                  | Severity if wrong | Action                                                                                                            |
| --- | -------------------------- | ----------------------- | ----------------- | ----------------------------------------------------------------------------------------------------------------- |
| OP1 | Remote read, coalesce      | **YES**                 | —                 | None.                                                                                                             |
| OP2 | Remote read, new entry     | **YES**                 | —                 | Optional: delete dead `evictingAddr` assignment in `doWriteHit`.                                                  |
| OP3 | Eviction policy            | **YES** (LRU, not FIFO) | —                 | Brief was wrong; code is correct.                                                                                 |
| OP4 | Eviction broadcast         | **YES** (per-line/per-sharer) | —           | Optional: tighten `for i := 0; i < len(victim.SubEntry); i++` to skip `!IsValid` slots — defensive only.          |
| OP5a| Local write hit            | **PARTIAL**             | **HIGH** (silent stale data on a remote sharer when local write has exactly 1 sharer ≠ writer)         | **Fix in PHASE C.** Drop the `len(sharer)<=1` shortcut for local writes; always invalidate non-writer sharers.   |
| OP5b| Remote write hit, valid    | **PARTIAL**             | **MODERATE** (under-tracks writer as sharer; minor performance + scalability loss on write-then-read patterns) | **Fix in PHASE C.** After the invalidation broadcast, retain the writer's sharer bit and leave `IsValid=true`. |
| OP6 | Sharer-side L2 eviction    | **YES (PAPER-AMBIGUOUS)** | —             | None. Document choice if asked.                                                                                   |

---

## B4. Sanity Micro-test

### Setup
- Test file: [`directory_microtest_test.go`](../akita/mem/cache/REC/directory_microtest_test.go) (added by this audit).
- Configuration: 1 set, 4 ways, `log2BlockSize=6`, `log2NumSubEntry=4` (16 sub-entries → 1 kB region), single PID, single source GPU `"GPU1.RDMA"`.
- Sequence: three back-to-back "remote reads" at addresses `0x1000`, `0x1040`, `0x1080`. All three lie inside the 1 kB region whose base is `0x1000` (`0x1000 >> 10 == 0x1080 >> 10 == 0x4`).
- Each iteration: `Lookup → FindVictim → set sub-entry → append sharer → Visit` — the same call sequence used by `directorystage.doWrite` + `bankstage.InsertNewEntry`/`UpdateEntry`.

### Expected (per spec)
- Exactly 1 valid entry, `Tag = 0x1000`.
- `SubEntry[0].IsValid = true`, `SubEntry[1].IsValid = true`, `SubEntry[2].IsValid = true`. All other slots invalid.
- Each of those three slots has `Sharer = ["GPU1.RDMA"]`.

### Result
```
=== RUN   TestREC_OP1_CoalescingMicrotest
[Directory]	Build new coherence directory: 1 sets, 4 ways, 4 entries
    directory_microtest_test.go:130: Entry{Tag=0x1000, Valid=true,
        [p0=1{GPU1.RDMA} p1=1{GPU1.RDMA} p2=1{GPU1.RDMA} ]}
--- PASS: TestREC_OP1_CoalescingMicrotest (0.00s)
PASS
```

### Interpretation
**OP1 PASSES.** The "did coalescing actually happen?" question is answered: yes, three same-region reads produce exactly one entry with three position bits set, no extra entries allocated. This is the central correctness invariant of REC — the implementation honours it.

### Other operations covered by pre-existing unit tests (all PASS)
- `TestREC_Lookup_IgnoresSubEntryIsValid` — Bug 1: Lookup returns nil when sub-entry invalid. PASS.
- `TestREC_Lookup_ValidSubEntry` — Lookup returns the entry when fully valid. PASS.
- `TestREC_InsertNewEntry_DoesNotSetSubEntryIsValid` — Bug 2: InsertNewEntry sets sub-entry IsValid. PASS.
- `TestREC_UpdateEntry_DoesNotSetSubEntryIsValid` — Bug 2 for UpdateEntry. PASS.
- `TestREC_InvalidateAndUpdateEntry_ZombieEntry` — Bug 3: blk.IsValid clears on last-offset invalidation. PASS.
- `TestREC_InvalidateAndUpdateEntry_PartialInvalidation` — only target offset cleared on partial invalidation. PASS.
- `TestREC_MultiSharer_NoDuplication` / `TwoDistinctSharers` — sharer set semantics. PASS.
- `TestREC_InvalidateEntry_ClearsAllSubEntries` — full-entry invalidation. PASS.

### Operations NOT covered by automated tests (audit-by-inspection only)
- **OP5a hit-with-1-sharer-not-writer.** The current writePermission shortcut means the bug is exercised only at the simulator-pipeline level, not by the bankstage unit tests (which call the action directly, bypassing writePermission). A new test should construct a `transaction` with `fromLocal=true`, an entry hit with `Sharer=["GPU1.RDMA"]` ≠ writer, run `directorystage.doWriteHit`, and assert that `trans.action == InvalidateAndUpdateEntry` (currently it would assert `Nothing`).
- **OP5b hit-with-valid-target-offset.** A new test should populate Sharer with multiple GPUs, exercise the remote-write hit path, and assert that after `InvalidateAndUpdateEntry` the writer remains the sole sharer and `block.SubEntry[idx].IsValid` stays true. Currently both assertions would fail.

These two tests are the natural deliverables of PHASE C — they should be written **before** the fixes so each fix has a deterministic regression check.

---

## Recommended PHASE C Plan (one operation per commit)

1. **OP5a fix.** In `directoryStage.writePermission`, remove the `len(sharer) <= 1 → true` shortcut for local writes. Always return false unless the sharer list is empty (no remote sharer needs invalidating) or the only sharer is the writer (cannot be the case for local writes since the writer is the home GPU itself, which is excluded from the sharer list per paper §2.3). Add a regression test mirroring the audit-by-inspection note above.
2. **OP5b fix.** Add a new bank action `UpdateAndInvalidateOthers` (or rename `InvalidateAndUpdateEntry` and split paths) that, on remote write to a hit-valid-offset:
   - Sends invalidations to every sharer except the writer.
   - Sets `entry.Sharer = [writer]` (instead of `nil`).
   - Leaves `entry.IsValid = true` and `block.IsValid = true`.
   Add a regression test asserting writer-survives semantics.
3. **OP4 defensive tightening (optional).** Skip `!IsValid` slots in `bottomSender.sendInvalidationRequest`'s outer loop. Behaviour-preserving; protects against future bugs where Sharer might be populated on an invalid slot.

After each fix:
- B4 micro-test must still PASS.
- A new test specific to that fix must PASS.
- Smoke-run a small benchmark (PHASE D's stencil N=200, 4 GPUs) to confirm no regression in `Evictions`, `evict-initiated invalidation count`, or IPC.
