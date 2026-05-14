# REC Paper Specification — Phase A

**Source:** Ko et al., "REC: Enhancing fine-grained cache coherence protocol in multi-GPU systems," *Journal of Systems Architecture* 160 (2025) 103339.
**PDF path:** `/root/mgpusim_home/archive/REC Enhancing fine-grained cache coherence protocol in multi-GPU systems.pdf`
**Sections cited:** §4.1 (Hardware overview), §4.2 (REC protocol flows), §4.3 (Discussion / Scalability), Fig. 8 (high-level overview), Fig. 9 (entry structure), Fig. 10 (protocol flow), Table 1 (range-vs-storage trade-offs).

This is a **paper-to-implementation contract**. Every claim below is anchored to a paper page/figure/table. No inference beyond what is printed. Items the paper does not specify are explicitly marked **PAPER-AMBIGUOUS**.

---

## A1. Entry Layout Specification

**Source:** §4.1, Fig. 9, Table 1.

For a directory configured with **1 kB coalescing range** (the paper's chosen design point), each entry contains the following fields, in order:

| Field             | Width (bits) | Derivation                                                            |
| ----------------- | -----------: | --------------------------------------------------------------------- |
| Valid bit         |            1 | Single bit per entry; "indicates whether the entire entry is valid"   |
| Base address      |           38 | 48-bit physical tag − 10 offset bits (2¹⁰ = 1 kB range, 64 B aligned) |
| Position bits     |           16 | One bit per coalesceable 64 B line within the 1 kB range (1024/64)    |
| Sharer bits       |  16 × (n − 1)| `n` = number of GPUs in the system; home GPU excluded                 |

The paper packs position + sharer bits into "the lower 64 bits" for the 4-GPU configuration: 16 position + 16×3 sharer = 64. For >4 GPUs the bit-vector grows beyond 64 (see §4.3 *Scalability*: 8-GPU = (8−1)×16 = 112 sharer bits → 112 + 38 + 16 + 1 = **167 bits**).

### Per-GPU-count entry size (1 kB range)

| # GPUs (n) | Sharers (n − 1) | Sharer bits = 16·(n−1) | Total bits = 1 + 38 + 16 + 16·(n−1) | Source                            |
| ---------: | --------------: | ---------------------: | ----------------------------------: | --------------------------------- |
|          4 |               3 |                     48 |                            **103** | Table 1, §4.3 ("103 bits")        |
|          6 |               5 |                     80 |                            **135** | Derived using §4.3 formula        |
|          8 |               7 |                    112 |                            **167** | §4.3 ("167 bits")                 |
|         16 |              15 |                    240 |                            **295** | §4.3 ("295 bits")                 |

**6-GPU entry total: 135 bits.**

The valid bit is conceptually the OR of all position bits ("the position bit can also function as the valid bit for each coalesced entry, meaning only one valid bit is necessary to indicate whether the entire entry is valid or not." — §4.1). An implementation may either (i) carry an explicit valid bit, or (ii) treat "any position bit set ⇒ valid". Both are spec-compatible.

---

## A2. Operation Specifications

The paper describes REC's protocol behavior in §4.2 with hooks (A)–(M) keyed to Fig. 10. Below, each operation lists its trigger, action, state transition, and the verbatim paper source (page/marker).

### OP1 — Remote read, base address matches existing valid entry (coalescing)

| Field             | Specification                                                                                                                                                                                                                                                                                          |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Trigger           | Remote read request arrives at home GPU; base address (high-order tag bits) of request matches an existing entry whose valid bit is set.                                                                                                                                                              |
| Action            | Compute position `p = (Tag mod m / 64) × (n + 1)` (see A3). **Bitwise-OR** position bit `p` and sharer bit for source GPU into the matched entry. "It can happen that the position bit is already set; nevertheless, the controller still performs a bitwise OR on the bits at the corresponding positions." |
| State transition  | Entry remains **valid**. No new entry allocated.                                                                                                                                                                                                                                                       |
| Side effects      | None outside the directory (no invalidation, no inter-GPU traffic).                                                                                                                                                                                                                                    |
| Paper source      | §4.2 "Remote reads" (p. 7), Fig. 10 markers (A)(B)(C).                                                                                                                                                                                                                                                 |
| Verification hook | After a sequence of remote reads to the *same* 1 kB region from the same source GPU, the directory must hold **exactly 1 entry** with the correct position bits set.                                                                                                                                  |

### OP2 — Remote read, new base address, free way available (entry insertion)

| Field             | Specification                                                                                                                                          |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Trigger           | Remote read; no entry with matching base address found; an invalid (or unused) way exists in the indexed set.                                         |
| Action            | Allocate the free way; write base address; set position bit `p` and sharer bit for source GPU.                                                         |
| State transition  | Entry transitions **invalid → valid**.                                                                                                                  |
| Side effects      | None.                                                                                                                                                   |
| Paper source      | §4.2 "Remote reads" (p. 7): "Otherwise, if no valid entry is found, a new entry is created with the base address, and the position and sharer bits are set. With the insertion of a new entry, the state transitions from invalid to valid." |

### OP3 — Remote read, entry insertion forces replacement (eviction)

| Field             | Specification                                                                                                                                                                                                                                                                  |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Trigger           | Remote read with no matching base address; **all ways in the indexed set are valid**.                                                                                                                                                                                          |
| Action            | Select a victim using a replacement policy that is **LRU-like** (the paper's explicit choice for REC; the *baseline* directory uses FIFO). "REC adopts the replacement policy, similar to LRU, to better retain entries that are more likely to be accessed again." Then proceed to OP4 for the victim. |
| State transition  | Victim entry → **invalid**; new entry created (per OP2 mechanics) in the freed way.                                                                                                                                                                                            |
| Side effects      | Triggers OP4 (eviction broadcast) for the victim.                                                                                                                                                                                                                              |
| Paper source      | §4.2 "Directory entry eviction/replacement" (p. 7), Fig. 10 markers (J)(K)(L).                                                                                                                                                                                                 |
| Note              | The user-provided task description said "FIFO-based eviction" for REC. **This contradicts the paper.** The paper explicitly distinguishes baseline=FIFO from REC=LRU-like. This is a spec extraction; the implementation must match LRU-like (or carry a documented justification for a deviation). |

### OP4 — Eviction broadcast (invalidation scope)

| Field             | Specification                                                                                                                                                                                                                                                                                                  |
| ----------------- | -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Trigger           | Triggered by OP3 (a directory entry is being evicted to make room for a new entry).                                                                                                                                                                                                                            |
| Action            | "the controller retrieves the base address, every merged offset from the evicting entry and reconstructs the original tag addresses. Invalidation requests are propagated to every recorded sharer associated with each tag address." Concretely: for each position bit `p_i` set in the victim, reconstruct cache-line address `base ‖ (p_i / (n+1)) × 64`, and for each sharer bit set in that offset's slot, send an invalidation message to that GPU naming **that single 64 B cache line**. |
| Granularity       | **Per-cache-line (64 B), not per-region.** REC does **not** broadcast a 1 kB-range invalidation. It enumerates all (offset, sharer) pairs from the victim and sends individual line-granularity invalidations. This is the entire correctness reason REC works: writes and evictions retain fine-grained tracking; only directory storage is compressed. |
| State transition  | Victim entry → **invalid**.                                                                                                                                                                                                                                                                                     |
| Paper source      | §4.2 "Directory entry eviction/replacement" (p. 7), Fig. 10 marker (M).                                                                                                                                                                                                                                         |
| Verification hook | After a forced eviction of an entry holding `k` set position bits with `s` total sharer-bit settings, exactly `s` invalidation messages are sent (one per (offset, sharer) pair), each naming a 64 B line address.                                                                                              |

### OP5 — Write request handling (partial / fine-grained invalidation)

The paper splits writes into two distinct cases. Both share the property that REC's compression must **not** degrade write-side coherence to coarse granularity.

#### OP5a — Local write (home GPU writes its own data)

| Field             | Specification                                                                                                                                                                                                                                              |
| ----------------- | -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Trigger           | Local store at home GPU to a line whose base address may be in the directory.                                                                                                                                                                              |
| Lookup            | Compute base + offset; look up directory by base address.                                                                                                                                                                                                  |
| Hit, offset valid | Send invalidation to every sharer recorded **for that offset only**. Then **clear only the position bit and the sharer bits for that specific offset**; do **not** touch other offsets in the same entry.                                                  |
| Hit, last offset  | "If the cleared bits are the last ones, the entire directory entry transitions to an invalid state to make room for new entries."                                                                                                                          |
| Miss              | No directory action. (The paper does not describe write-miss insertion for local writes, since locally-generated writes do not create remote sharers.)                                                                                                      |
| Paper source      | §4.2 "Local writes" (p. 7), Fig. 10 markers (D)(E)(F).                                                                                                                                                                                                     |
| Verification hook | A local write to one offset, when the entry holds *other* valid offsets, must (i) send invalidations only for that one offset, (ii) leave other offset position bits unchanged, (iii) leave entry valid.                                                   |

#### OP5b — Remote write (some other GPU writes to home GPU's data)

| Field                                | Specification                                                                                                                                                                                                                                                              |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Trigger                              | Remote write request arrives at home GPU. Source GPU also caches the data (write-through to local L2 per §2.2).                                                                                                                                                          |
| Hit, target offset **invalid**       | Treat like OP1/OP2: set the target offset's position bit and the source GPU's sharer bit. (No invalidation needed — no other sharers for this offset.)                                                                                                                    |
| Hit, target offset **valid**         | Set source GPU's sharer bit. **Clear every other sharer bit** for this offset. Send invalidation to each *cleared* sharer. Entry remains valid; the target offset's position bit remains set; only the source GPU is now recorded as sharer for that offset.             |
| Miss                                 | Allocate new entry; record base + offset + source-GPU sharer bit. State invalid → valid.                                                                                                                                                                                  |
| Paper source                         | §4.2 "Remote writes" (p. 7), Fig. 10 markers (G)(H)(I).                                                                                                                                                                                                                   |
| Verification hook                    | A remote write from GPU X to an offset previously read by GPUs Y, Z must (i) send invalidations to Y and Z (not to X), (ii) leave X's sharer bit set and Y, Z's cleared, (iii) leave the offset's position bit set, (iv) leave other offsets in the entry untouched.       |

### OP6 — Sharer GPU's silent / non-silent L2 eviction notification

| Field             | Specification                                                                                                                                                                                                                                          |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Trigger           | A sharer GPU's L2 cache evicts a clean line that the home GPU's directory still records as a sharer.                                                                                                                                                  |
| Status            | **PAPER-AMBIGUOUS.** The paper does not describe whether sharer-side evictions are silent (no notification) or non-silent (sent back to home for sharer-bit clearing). It also does not describe a mechanism by which home GPU would learn of such evictions for clean lines. |
| Implication       | Either implementation is reviewer-defensible: (a) silent eviction (no notification, directory may hold stale sharer bits — wasted invalidations on next write/evict but correct), (b) non-silent (extra inter-GPU message). The paper's results are consistent with (a), since §3.2 explicitly characterizes "evict-initiated invalidations that hit in the sharer-side L2 caches" — implying some misses too — but the paper does not call this out as a notification mechanism. |
| Verification hook | None — the implementation may take either path. Document the choice in the audit.                                                                                                                                                                       |

---

## A3. Position Bit Calculation

**Source:** §4.1 formula and the worked example in §4.2 "Remote reads" (p. 7).

**Formula (verbatim from paper):**

```
p = ( (Tag mod m) / 64 ) × (n + 1)
```

Where:
- `Tag` is the 48-bit physical line tag (the address with its low 6 cache-line-offset bits already conceptually removed; `Tag` is at byte granularity per the paper's example below).
- `m` = coalescing range in bytes = **1024** (1 kB) for the chosen design.
- `64` is the cache line size in bytes.
- `n` is the **number of sharers** = (number of GPUs) − 1 = **3 for 4-GPU**, **5 for 6-GPU**.
- `p` is the bit index of the position bit within the per-entry bit-vector (counting from the low end of the position+sharer field).

**Stride:** Each (position, sharers) slot is `(n+1)` bits wide: 1 position bit followed by `n` sharer bits.

**Worked example from paper (4-GPU, n = 3):**

> "the position bit is `340 mod 16 / 64 × 4 = 52` representing the 14th cache line within the specified 1 kB range. … Therefore, bit 52 and 53 are set to 1." (§4.2, p. 7)

The paper's notation `340 mod 16` is a typesetting artifact for `(0x340 mod 0x400)` = `(832 mod 1024)` = `832`. Then `832 / 64 = 13` (the 14th line, counting from 0). `13 × 4 = 52`. Bit 52 = position bit; bit 53 = GPU1's sharer bit (assuming source = GPU1, the first non-home GPU index).

**Per-GPU-count stride:**

| # GPUs | Sharers (n) | Stride (n + 1) | Cache lines per 1 kB | Position bit indices  |
| -----: | ----------: | -------------: | -------------------: | --------------------- |
|      4 |           3 |              4 |                   16 | 0, 4, 8, …, 60        |
|      6 |           5 |              6 |                   16 | 0, 6, 12, …, 90       |
|      8 |           7 |              8 |                   16 | 0, 8, 16, …, 120      |

**Decoding (for OP4 reconstruction):** Given a set position bit at index `p`, the offset within the 1 kB region is `(p / (n+1)) × 64` bytes, and the cache line address is `base ‖ offset`.

**Implementation matching test (for Phase B):**

```
For 4 GPUs, m = 1024:
  Tag = 0x1000 → (0x1000 mod 0x400)/64 × 4 = 0/64 × 4 = 0   → position bit 0
  Tag = 0x1040 → (0x1040 mod 0x400)/64 × 4 = 64/64 × 4 = 4  → position bit 4
  Tag = 0x1080 → (0x1080 mod 0x400)/64 × 4 = 128/64 × 4 = 8 → position bit 8
  Tag = 0x13C0 → (0x13C0 mod 0x400)/64 × 4 = 960/64 × 4 = 60 → position bit 60 (last slot)
  Tag = 0x1400 → (0x1400 mod 0x400)/64 × 4 = 0  → position bit 0 of *next* base (0x1400/0x400 = base 5)
```

---

## A4. Storage Cost

**Source:** §4.3 "Overheads" (p. 7), Table 1.

### Reference (4-GPU, paper baseline)

- Entry: 103 bits (Table 1, 1 kB range column).
- Directory size: 8 192 entries × 103 bits / 8 bits per byte / 1024 bytes per kB = **103 kB per GPU**.
- "the directory is 3.94% area and has 3.28% power consumption compared to GPU L2 cache" (CACTI 7.0 estimate, §4.3).

### 6-GPU recalculation (this study's interest)

- Per-entry width: 1 (valid) + 38 (base) + 16 (position) + 16×5 (sharers) = **135 bits**.
- 8 192 entries × 135 / 8 / 1024 = **135 kB per GPU**.
- Ratio vs 4-GPU: 135 / 103 = **1.31×** larger directory storage.
- Ratio vs 4-GPU baseline (HMG-style 52 bits, see §3.3): 135 / 52 = **2.60×**, but storing 16× the addresses per entry.

### 8-GPU sanity (cross-check against §4.3)

- 1 + 38 + 16 + 16×7 = 167 bits ✓ (matches paper's "112 + 38 + 16 + 1 = 167 bits").

---

## Summary of paper-mandated invariants for Phase B

The Phase B audit must verify, with code citations, all of the following:

1. **Entry layout** has the four fields of A1, with widths matching the configured GPU count.
2. **Position bit formula** matches A3 exactly; same for sharer bit indexing (`p+1` … `p+n`).
3. **OP1 coalescing**: same-base remote reads do **not** allocate new entries; bitwise OR semantics; idempotent on already-set bits.
4. **OP2 insertion**: new base allocates one entry; state invalid → valid.
5. **OP3 eviction policy**: LRU-like (not FIFO; not random).
6. **OP4 eviction broadcast**: per-line, per-sharer invalidations reconstructed from base + each set position bit; **no** range-broadcast.
7. **OP5a local write**: clears only the affected offset's position + sharer bits; entry stays valid if other offsets remain; entry → invalid only when last offset cleared.
8. **OP5b remote write**: hit-valid case clears other sharers, sets source sharer; hit-invalid case behaves like OP1/OP2; miss allocates new entry.
9. **OP6**: no constraint from paper; document choice.

Anything not listed above (e.g., L2 fetch granularity, prefetch, request scheduling) is **out of scope for REC**. The user has explicitly noted: REC does not change L1 behavior, does not change L2 fetch granularity, and does not require the L2 cache controller to know the unit size. The directory module is the only modified component. Adding 16-line fetch is **not** REC.
