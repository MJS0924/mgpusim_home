# M1 실험 구현 프롬프트 — Workload Intrinsic Characterization (Phase × DS)

> **대상:** Claude Code (MGPUSim Go repo 작업 중)
> **근거 문서:** `M1_Simulation_Modification_Plan.md`, `experiment_plan.md`, `design_document.md`
> **제출 목표:** HPCA 2027 (2026년 7월 마감)
> **버전:** v1.2 (2026-04-19)

## ⚠️ v1.1 → v1.2 주요 변경 (철학 전환)

| 항목 | v1.1 | v1.2 |
|------|------|------|
| 실험 플랫폼 | REC-like directory + static region sweep | **Baseline + infinite directory** (REC 미사용) |
| 목적 | System-level optimal (eviction 효과 포함) | 📌📌 **Workload intrinsic** optimal (eviction 효과 제거) |
| 원칙 | Iso-storage (5 config 동일 bits) | 📌📌 **Iso-coverage** (directory 가 L2 cache 전체 cover) |
| Metric 세트 | L2 hit + dir eviction + evict-init inv | 📌📌 L2 hit + **region utilization** + **sharer consistency rate** (intrinsic 2종) |
| Track A vs B 비중 | A primary, B sanity | 📌📌 A primary, **B 격상** (intrinsic 은 trace 로도 독립 관찰 가능해야 함) |
| Reviewer 방어 포인트 | "REC eviction 이 phase variation 만든 거 아니냐" | 📌📌 "M1 은 intrinsic upper bound; 실제 이득은 P1/A9 이 iso-storage 로 증명" |

**본 v1.2 는 M1 을 "workload 의 공유 패턴 자체가 adaptive 를 요구하는가" 라는 더 순수한 질문으로 재정의한다. 결과가 positive 면 "어떤 directory 구현에서도 유효한 motivation", negative 면 Appendix A 플로우.**

---

## 0. Role & Stance

당신은 **HPCA 제출을 목표로 하는 컴퓨터 아키텍처 연구자 겸 MGPUSim 개발자**이다. 모든 결정에 대해 다음 두 축으로 비판적으로 사고한다.

1. **Reviewer 시뮬레이션**: 모든 파라미터/metric/workload/phase/DS 정의에 대해 "공격 → 방어 근거" 를 코드 주석과 commit message 에 기록.
2. **자기 검열**: "실패/미달/추측 금지" 3종 세트.

### 연구 윤리 공통 원칙

| 원칙 | 본 작업에서의 구체화 |
|------|----------------------|
| **실패 금지 (No Fabrication)** | 실패한 run, 가설과 반대되는 workload, oscillation 원본, 불편한 DS 분포, Track A↔B 불일치 모두 그대로 기록 |
| **미달 금지 (No Inflation)** | Sensitivity sweep "결과가 좋은 값"으로 crop 금지. Clustering hyperparameter 를 결과 보고 튜닝 금지. 📌📌 Intrinsic metric 을 결과 보고 임의 선택 금지 |
| **추측 금지 (No Speculation)** | "likely", "expected", "should" 금지. 수치만. 📌📌 "intrinsic 하니까 어떤 directory 에서도 성립할 것" 추측 금지 — 실제 시스템 효과는 PHASE 2/3 에서 증명 |

**각 PHASE 는 자체 "실패/미달/추측 금지" 조항을 가지며 작업 전·후 체크.**

---

## 1. 프로젝트 Context

- **제안 기법**: Adaptive Region-Size Directory ("Superdirectory"). Coherence 관리 단위 64B~16KB 5 bank 가변.
- **대조군 (PHASE 2/3 에서 비교)**: REC, HMG. **📌📌 M1 에서는 대조군 비교 없음 — baseline 단일 플랫폼.**
- **시뮬레이터**: MGPUSim (Go). 기본 VI directory 확장.
- **M1 역할 (v1.2 재정의)**: 
  - **Workload 의 sharing pattern 이 phase × DS 축으로 heterogeneous 하다** 는 것을 directory 구현 상세와 무관하게 증명.
  - System 효과 (directory eviction, capacity pressure) 는 **의도적으로 제거**.
  - 산출물: (a) phase timeline plot, (b) address × phase heatmap, (c) (phase × DS) joint heatmap, (d) DS-only bar chart, (e) window sensitivity, (f) 📌📌 **Track A ↔ B 일치도 plot**.

- **📌📌 M1 의 범위 제한 (중요)**:
  - M1 은 "adaptive 의 motivation" 까지만 증명.
  - **"실제 이득"** 은 PHASE 2 P1 (iso-storage 비교) + A9 (static vs dynamic) 합쳐져야 증명됨.
  - 따라서 M1 결과 작성 시 "adaptive is beneficial" 대신 **"adaptive has intrinsic signal"** 로 한정된 표현 사용.

---

## 2. M1 목표의 측정 가능한 명제 (reviewer-proof)

| # | 명제 | 성공 기준 | 축 |
|---|------|-----------|-----|
| M1-P1 | Window 2× 변화에서 "optimal 이 변한다" robust | {50K, 100K, 500K, 1M} 전체 entropy ≥ 0.5 bits | 시간 |
| M1-P2 | 📌📌 **3 intrinsic metric** (L2 hit rate, region utilization, sharer consistency) agreement ≥ 70% | 3 metric 교차 | 시간 |
| M1-P3 | 최소 3 workload 에서 phase 별 optimal 최빈값 ≤ 60% | 6 중 3 | 시간 |
| M1-P4 | 최소 3 workload 에서 DS 별 optimal 최빈값 ≤ 60% | 6 중 3 | 공간 (DS) |
| M1-P5 | Joint (phase × DS) 가 marginal 보다 conditional entropy 감소 ≥ 15% | workload 평균 | 시공간 |
| 📌📌 **M1-P6** | **Track A (simulation) 와 Track B (trace-only) 가 phase 별 optimal 을 지목하는 일치율 ≥ 80%** | 두 track 독립 산출, cross-validation | intrinsic consistency |

**📌📌 M1-P6 의미**: Intrinsic 특성이라면 timing-heavy simulation 없이 trace analysis 로도 동일 결론이 나와야 한다. 일치율이 높으면 "이 결론은 simulator-specific artifact 가 아니다" 는 강력한 근거. 80% 는 "동일 한 phase 에서 두 track 이 같은 region size 를 optimal 로 지목하는 비율". Pilot 후 사용자 승인 시에만 조정.

---

## 2.4 Data Structure 정의 — 이중 접근 (v1.1 유지)

### 2.4.1 정의 1 (주): Allocation-based
- Driver memory allocation hook → `(base, size, ds_id, ds_name, alloc_cycle)`.
- `MGPUSIM_DS_BEGIN(name) / _END()` 매크로 지원. 없으면 순서대로 `DS_001` ..

### 2.4.2 정의 2 (보조): Access-clustering
- Page bucket (64KB) → hierarchical clustering (linkage=average, cosine).
- Feature: `[per-CU freq norm, R/W ratio, remote ratio, avg interval]`.
- Cluster 수 = silhouette max, range `[2, 16]`.

### 2.4.3 결합
- Primary = 정의 1. Main figure.
- Supplement = 정의 2. **ARI ≥ 0.6** 이면 consistent. 미만이면 그대로 명시, allocation-based 만 primary.

### 2.4.4 Reviewer 공격 대비 (v1.1 과 동일)
- "Driver hook 이 H/W 에서 보이냐?" → M1 simulation-only, 제안 기법 PHASE 1~2 는 annotation 없이 promotion/demotion 으로 DS 효과 자동 근사.
- "Clustering 이 결과 만든 거 아니냐?" → Allocation primary, clustering cross-check + sensitivity.
- "같은 DS 내 pattern 다양할 수 있음" → intra-DS entropy 를 sanity_report 에 기록.

---

## 📌📌 2.5 Intrinsic 정의와 실험 플랫폼 (v1.2 핵심)

### 2.5.1 "Intrinsic" 의 operational 정의

본 실험에서 "intrinsic 특성" = **directory 구현 상세 (capacity, eviction policy, coalescing, hierarchy) 에 독립적으로 workload 의 memory access pattern 만으로 결정되는 특성.**

측정 대상:
1. **Region utilization rate** — fetch 된 region (R bytes) 중 실제 접근된 바이트 비율. Trace 로도 계산 가능.
2. **Sharer set consistency rate** — region 내 모든 cacheline 이 동일 sharer 를 갖는 phase × region 비율. Trace 로도 계산 가능.
3. **L2 hit rate (semi-intrinsic)** — simulation timing 반영하되 directory eviction 효과 제거.

### 2.5.2 Baseline platform 명세

- **Coherence protocol**: Standard VI (MGPUSim 기본). REC coalescing 로직 **비활성화**.
- **Directory capacity**: 📌📌 **Infinite** (또는 "L2 전체 + 10× 여유" 의 large enough).
- **Directory eviction**: **Never** (infinite 면 자동, large-enough 면 runtime assertion 으로 eviction = 0 검증).
- **Region size**: `{64B, 256B, 1KB, 4KB, 16KB}` 5 config sweep.
- **Subentry**: 없음 (PHASE 1 소관).
- **Promotion/demotion**: 없음 (PHASE 1~2 소관).

### 2.5.3 📌📌 Iso-coverage 원칙 (iso-storage 대체)

- v1.1 의 iso-storage ("5 config 총 bits 동일") 는 **폐기**. Infinite directory 에서는 의미 없음.
- 대신 **iso-coverage**: 각 config 에서 directory 가 L2 cache 전체의 coherent data 를 100% cover. Eviction 이 0 임을 runtime 에서 검증.
- 이는 v1.1 의 reviewer 공격 "storage 크기가 달라서 이긴 것" 을 원천 차단 — storage 는 모든 config 에서 "충분히 큼" 으로 통일.

### 2.5.4 📌📌 Track A / B 재정의 (v1.1 에서 격상)

| Track | v1.1 | v1.2 |
|-------|------|------|
| A | Primary (simulation) | Primary (simulation + infinite dir) |
| B | Secondary sanity | **Co-primary — trace-only analysis, intrinsic validation** |

**Track A (simulation):**
- Infinite directory 에서 5 config 각각 시뮬레이션.
- 반영: timing, L2 cache pollution, coherence traffic, invalidation cascade.
- 제거: directory eviction (infinite).

**Track B (trace analysis):**
- Baseline (R=64B) 1 run 의 remote access trace 수집.
- Post-processing 으로 각 region size 의 intrinsic metric (utilization, sharer consistency) 을 counterfactual 계산.
- 반영: 순수 workload access pattern.
- 제거: 모든 timing, cache, directory 효과.

**두 Track 의 일치율 = M1-P6.** 높으면 "결론이 simulator-robust", 낮으면 "어느 metric 이 simulation 효과에 의존하는지" 를 분해 분석.

### 2.5.5 Reviewer 공격 대비

| Reviewer Question | 대응 |
|-------------------|------|
| "Infinite directory 는 비현실적. 이 결론이 실제 시스템에서 유효하냐?" | 📌📌 "M1 은 intrinsic signal 의 존재 여부 증명 (upper bound). 실제 유한 directory 에서의 성능 이득은 PHASE 2 P1 (iso-storage proposed vs REC vs HMG) + A9 (static vs dynamic) 이 증명. M1 의 변동이 있다 → 실제 시스템에서도 변동을 capture 할 여지가 있다는 필요조건." |
| "왜 REC 위에서 하지 않았나? Reader 가 REC 를 baseline 으로 기대할 텐데" | 📌📌 "REC 의 coalescing 은 phase × DS 변동을 eviction 패턴으로 혼동시킴. 본 실험은 workload intrinsic 만 분리하려 REC 를 제외. REC 위에서의 직접 비교는 PHASE 2 P1 이 담당." |
| "Simulation 없이 trace 로도 결론 나면 M1 에 simulation 이 왜 필요한가?" | 📌📌 "Track A (simulation) 는 (a) L2 cache pollution 과 (b) coherence message cascade 처럼 trace 만으로 안 잡히는 효과를 반영. Track B 와의 **일치율 자체가** 결론의 robustness 증거 (M1-P6)." |
| "3 intrinsic metric 도 서로 상관관계 있는 것 아니냐? Independent signal 이 맞냐?" | 📌📌 "실제 공분산 행렬을 sanity_report 에 기록. 상관계수 > 0.9 면 하나는 redundant 로 supplement 이동. 70% agreement 는 단순 상관관계보다 '같은 region size 를 optimal 로 지목하는가' 의 stronger criterion." |

---

## 3. 구현 Phase

### PHASE A — Baseline Directory (Infinite) + Region Size Parameterization

**목표:** Baseline VI directory 를 `RegionSizeBytes` + **`InfiniteCapacity` flag** 로 확장. 📌📌 **REC coalescing 로직 비활성화 경로 확보.**

**Task:**
- [ ] A-1. `coherence/directory.go`, `coherence/entry.go` → `DirectoryConfig` 에 `RegionSizeBytes uint64`, 📌📌 `InfiniteCapacity bool` 추가.
- [ ] A-2. `addrToTag` 를 `addr >> log2(RegionSize)` 로 일반화.
- [ ] A-3. `coherence/address_mapper.go` 신규.
- [ ] A-4. L1→L2→Directory 호출 경로 region-aligned tag 통일.
- [ ] 📌📌 **A-5. Infinite capacity 경로**:
  - `InfiniteCapacity=true` 시 `Insert()` 가 eviction 을 절대 트리거하지 않음 (capacity 무제한).
  - Eviction counter 는 유지하되 runtime 에 `evictions == 0` assertion.
  - Memory footprint 제한 위해 hash map 기반 entry store. Pilot 에서 peak memory 측정해 사용자 보고.
- [ ] 📌📌 **A-6. REC coalescing 로직 제거 경로**:
  - REC-specific base+offset 구조를 쓰지 않는 "plain VI" 경로 명시. `CoalescingEnabled bool = false` default.
  - 기존 REC 코드가 있다면 dead-code-flag 로 우회 (삭제 아님 — PHASE 2 P1 에서 REC baseline 으로 필요).
- [ ] A-7. **[SANITY]** `R=64B`, `InfiniteCapacity=true`, `CoalescingEnabled=false` 에서 coherence 정확성 unit test (모든 access 가 올바른 sharer set 으로 routing).
- [ ] 📌📌 **A-8. [SANITY] V11 (신규)**: 모든 config 에서 runtime eviction count == 0 검증.
- [ ] A-9. Sub-entry 구현 금지 (PHASE 1).
- [ ] A-10. Commit message "Why reviewer-safe" 한 줄.

**실패 금지 (A):**
- Unit test 실패 시 `// TODO` skip 금지.
- 📌📌 **"Infinite directory 가 실제로 infinite 인지" 를 mock data 로 가장하지 않음.** 5 config × 6 workload 전체에서 eviction=0 검증.
- 📌📌 Memory overflow 로 인한 simulation crash 발생 시, "부분 결과만 사용" 금지. Large-enough alternative 로 전환하고 eviction=0 재검증.

**미달 금지 (A):**
- 5 region size 전부 동작. 📌📌 5 config 모두에서 infinite capacity mode 동작.
- 📌📌 Iso-storage assertion 제거, **iso-coverage assertion 추가**: "directory entry 수 ≥ ceil(L2_capacity / region_size) × safety_factor(=2)".

**추측 금지 (A):**
- 📌📌 "Infinite 이니까 timing 은 R=64B 와 동일할 것" 추측 금지. 5 config 의 total cycle count 를 pilot 에서 비교하고 차이 수치를 기록.
- 주석에 "보통", "관례적으로" 금지.

---

### PHASE B — Phase Clock, Metric Collector, DS Tracker, 📌📌 **Intrinsic Metric Hooks** (v1.2 확장)

**목표:** Phase × DS 측정 인프라 + 📌📌 **intrinsic metric (region utilization, sharer consistency) 측정 hook**.

**Task:**
- [ ] B-1. `instrument/phase_clock.go` — `PhaseClock` + `Tick` + `OnKernelBoundary`. Window/kernel 별도 channel.
- [ ] B-2. `instrument/phase_metrics.go` — counter:
  - L2Hits, L2Misses
  - 📌📌 ~~DirectoryEvictions, EvictInitInvalidations~~ (infinite dir 에서 의미 없음, 제거 — 단 runtime assertion 용으로 DirectoryEvictions 만 유지)
  - WriteInitInvalidations (true invalidation)
  - 📌📌 **RegionFetchedBytes** (신규) — region 단위로 fetch 된 총 바이트
  - 📌📌 **RegionAccessedBytes** (신규) — fetch 된 region 중 실제 접근된 바이트 (byte-level bitmap)
  - 📌📌 **SharerConsistentRegions** (신규) — 이 phase 에 활성화된 region 중 내부 모든 cacheline 이 동일 sharer 를 가진 region 수
  - 📌📌 **ActiveRegions** (신규) — 이 phase 에 접근된 총 region 수
  - RetiredInstructions
  - AddrBucketAccesses
- [ ] B-3. L2 controller / directory / CU retirement 에 counter hook.
- [ ] 📌📌 **B-4. Intrinsic metric hook 상세:**
  - `RegionFetchedBytes += R` on each region fetch.
  - `RegionAccessedBytes += popcount(access_bitmap)` on region eviction or phase boundary (bitmap 은 region 당 8~2048 bits, region size 에 따라).
  - Sharer consistency 계산: region 내 각 cacheline 의 sharer set 을 수집 → set equality check. Phase 종료 시 batch 계산 (per-access 계산 과부하 방지).
  - **Region utilization rate (phase 단위)** = `RegionAccessedBytes / RegionFetchedBytes`.
  - **Sharer consistency rate (phase 단위)** = `SharerConsistentRegions / ActiveRegions`.
- [ ] B-5. Critical path 영향 최소화 (per-CU local + 1000 cycle batched flush). Overhead 수치 commit message.
- [ ] B-6. **[SANITY]** Invariant V1, V3, V5, V6 runtime assertion. 📌📌 V11 (no eviction) 도.
- [ ] B-7. **DS tracker (v1.1 유지):** `instrument/ds_tracker.go` — allocation hook, `AddrToDSID`, overlap assertion.
- [ ] B-8. **PhaseMetrics DS 확장 (v1.1 유지):** `DSAccesses` + `phase_ds_snapshot.parquet` append (컬럼에 📌📌 **region utilization, sharer consistency** 도 포함).
- [ ] B-9. **[SANITY]** V7 (DS 합 = page 합), V8 (DS_UNKNOWN ≤ 10%), V9 (overlap 0), 📌📌 **V12 (신규): `RegionAccessedBytes ≤ RegionFetchedBytes` per region per phase** (utilization ≤ 100%).

**실패 금지 (B):**
- Counter 누락 시 phase 전체 폐기 후 재실행.
- 📌📌 **Intrinsic metric bitmap 이 부정확** (예: sub-cacheline 접근을 놓침) 하면 "통계적으로 영향 없음" 판단 금지. Microbenchmark 로 ground-truth 대비 < 1% 오차 검증 후 release.
- DS tracker overlap → assertion fail.

**미달 금지 (B):**
- Kernel boundary + fixed-cycle window 모두.
- Overhead 미측정 시 종료 금지.
- 📌📌 **3 intrinsic metric (L2 hit, utilization, consistency) 모두 구현** 후 PHASE C 진입. 2개만 구현하고 "나머지는 Python post-processing" 금지 — 이 3 metric 은 simulator 내부에서 직접 집계되어야 정확함.
- DS Go-side tracker + Python clustering 모두 준비.

**추측 금지 (B):**
- `batched flush` sensitivity 수치.
- 📌📌 "Utilization 은 항상 region size 에 monotone" 추측 금지. Pilot 에서 실제 monotonicity 검증 (반례 workload 가 있을 수 있음 — access pattern 이 region 경계에 묘하게 걸리는 경우).

---

### PHASE C — Config Sweep, 📌📌 **Track B Trace Logger 격상**, DS Annotation

**목표:** 5 config 실행 파이프라인 + 📌📌 **Track B 가 Track A 와 동등한 infrastructure 수준으로 격상** + DS annotation 확보.

**Task:**
- [ ] 📌📌 **C-1. `config/m1_configs.yaml`:** 5 config 모두 `InfiniteCapacity=true`, `CoalescingEnabled=false`. Iso-storage 항목 제거, **iso-coverage 검증 필드 추가**: `min_entries = ceil(L2_bytes / region_size) * 2`.
- [ ] 📌📌 **C-2. `instrument/trace_logger.go` — Track B primary-level 격상:**
  - Baseline (R=64B) run 에서 **모든** remote access 와 local-to-shared-cacheline access 를 수집.
  - 컬럼 확장: `cycle, src_gpu, home_gpu, addr, op_type, access_bytes_in_cacheline (bitmap), sharer_set_before, sharer_set_after, ds_id`.
  - Access bitmap (64-bit per cacheline) 을 포함해 intrinsic utilization 을 trace-only 로 계산 가능하게.
  - Ring buffer + batched flush. Overhead < 1% 유지.
- [ ] C-3. `instrument/csv_dumper.go` — per-run metric parquet.
- [ ] C-4. `scripts/run_m1.sh` — 병렬 실행.
- [ ] 📌📌 **C-5. Pilot (확장)**: 1 workload × 5 config. 추가로 `R=64B` run 에서 trace 도 수집. 전 파이프라인 + Track B 오프라인 재현까지 end-to-end 확인.
- [ ] 📌📌 **C-6. [SANITY] V4 재정의**: Track B 가 region size R 에서 계산한 **intrinsic metric (utilization, consistency)** 값이 Track A 의 해당 config 값과 **±5% 이내**. L2 hit rate 은 ±3% (timing 효과 포함하므로 약간 더 엄격).
- [ ] C-7. **DS table dump (v1.1 유지)**: `results/m1/ds_table/{workload}.csv`.
- [ ] C-8. **DS annotation 커버리지 (v1.1 유지):** `DS_UNKNOWN` < 10% 확보. 부족 workload 는 매크로 PR 제안 (사용자 승인 후).
- [ ] C-9. **Pilot DS sanity (v1.1 유지).**

**실패 금지 (C):**
- Pilot 2× 초과 시 사용자 보고.
- 📌📌 **Track B trace overhead > 1%** 여도 "simulation 결과가 예쁘니까 overhead 는 감수" 금지. Ring buffer 조정 후 재실행.
- DS coverage 정직 기록.

**미달 금지 (C):**
- 📌📌 Iso-storage config 금지 (v1.1 잔재 제거). Iso-coverage 만 사용.
- Workload 일부만 run 후 PHASE D 진입 금지.
- 📌📌 **Track B trace 수집을 "시간 부족" 이유로 subset workload 만** 하지 않음. 6 workload 전체에서 R=64B trace 필수.

**추측 금지 (C):**
- 시간/I/O "대략" 금지.
- 📌📌 "Trace 와 simulation 결과가 intrinsic 이면 일치할 것" 추측 금지. 실제 M1-P6 수치를 sanity_report 에 기록.

---

### PHASE D — Post-processing, Joint Analysis, 📌📌 **Track A↔B Cross-validation**

**목표:** Phase별 + DS별 + joint optimal 산출 + 📌📌 **Track A ↔ B 일치도 정량화** + figure / sanity report.

**Task:**
- [ ] D-1. `01_load.py` — Parquet/CSV 로드.
- [ ] D-2. `02_align.py` — phase alignment (cycle + retired-insts).
- [ ] 📌📌 **D-3. `03_optimal.py`**: phase별 argmax 를 **3 intrinsic metric 기준** 으로:
  - `L2HitRate`, `RegionUtilization`, `SharerConsistency`.
  - 각 metric 에서 argmax region size 를 지목.
- [ ] D-4. `04_heatmap.py` — address × phase heatmap.
- [ ] D-5. `05_timeline.py` — timeline plot (3 metric marker).
- [ ] D-6. `06_sensitivity.py` — window size sensitivity entropy.
- [ ] 📌📌 **D-7. `07_consistency.py`**: 3 metric agreement + **metric 간 Pearson 상관행렬** 도 계산 (상관 > 0.9 이면 redundancy 경고 → supplement 이동).
- [ ] D-8. `08_sanity.py` — V1~V12 전수 검사.
- [ ] D-9. `09_ds_optimal.py` — DS 별 optimal + (phase, DS) joint optimal.
- [ ] D-10. `10_entropy.py` — `H(opt)`, `H(opt|phase)`, `H(opt|DS)`, `H(opt|phase,DS)`, M1-P5 판정. V10 assertion.
- [ ] D-11. `11_clustering.py` — clustering + ARI + cluster 수 sensitivity.
- [ ] 📌📌 **D-12. `12_track_consistency.py` (신규)**: 
  - Track A 의 per-phase optimal vs Track B 의 per-phase optimal 일치율 (M1-P6 판정, ≥ 80%).
  - Metric 별 분해 (L2 hit 은 timing 때문에 Track 간 덜 일치해도 되지만, utilization/consistency 는 매우 높아야 함).
  - 불일치 phase 를 metric × workload 축으로 breakdown.
- [ ] D-13. Plot 1: phase timeline (6 subplot, 3 metric marker).
- [ ] D-14. Plot 2: address × phase heatmap.
- [ ] D-15. Plot 3: window size sensitivity.
- [ ] D-16. Plot 4: (phase × DS) joint heatmap.
- [ ] D-17. Plot 5: DS-only bar chart.
- [ ] D-18. Plot 6: Allocation vs Clustering ARI.
- [ ] 📌📌 **D-19. Plot 7 (신규): Track A ↔ B agreement heatmap**. X=workload, Y=metric, color=per-phase agreement %.
- [ ] D-20. `sanity_report.md` — V1~V12, M1-P1~P6, DS coverage, ARI, metric 상관, 📌📌 **Track A↔B 불일치 분석**, oscillation, 이탈 workload.
- [ ] D-21. `reproduce.sh`.

**실패 금지 (D):**
- Phase variation 약한 workload 제외 금지. "static 충분" 명시.
- Oscillation 원본 primary.
- 📌📌 **Track A ↔ B 불일치 phase 를 "outlier" 로 제외 금지.** 불일치 자체가 분석 대상.
- Joint heatmap 특정 DS merge/제외 금지.
- Clustering cluster 수 결과 보고 고정 금지.

**미달 금지 (D):**
- M1-P2 agreement < 70% 여도 3 metric 전부 supplement.
- M1-P3/P4/P5 미달 시 workload 추가/임계 재조정 금지. Appendix A.
- 📌📌 **M1-P6 미달 시** "simulation 이 더 정확하니 Track A 만 쓴다" 결론 금지. 낮은 일치율 자체가 "결론이 directory 구현에 의존한다" 는 증거 — 이건 motivation 약화이므로 정직하게 보고.
- Window sensitivity 모든 window 플롯.
- 📌📌 Metric 상관 > 0.9 발견 시 해당 metric 을 primary set 에서 제외하되, 제외 사실과 상관계수 명시.

**추측 금지 (D):**
- "expected", "likely" 금지.
- 해석은 측정 utilization/consistency 수치 또는 REC Fig. b 인용에 연결.
- **M1 단독 "adaptive 가 이긴다" 주장 금지.**
- "이 DS 는 matrix 라서" 추측 금지.
- 📌📌 **"Intrinsic 하므로 실제 시스템에서도 성립"** 추측 금지 — 실제 시스템 이득은 P1/A9 가 증명. M1 보고에는 **"intrinsic signal exists"** 까지만 기술.

---

## 4. 전역 Deliverables

```
mgpusim/
├─ coherence/{directory.go, entry.go, address_mapper.go, directory_test.go}
│   📌📌 InfiniteCapacity flag, CoalescingEnabled=false 경로, V11 assertion
├─ mem/cache/l2_controller.go          (수정)
├─ instrument/
│   ├─ phase_clock.go
│   ├─ phase_metrics.go                📌📌 region util / sharer consistency 추가
│   ├─ trace_logger.go                 📌📌 primary-level 격상, bitmap/ds_id 포함
│   ├─ csv_dumper.go
│   └─ ds_tracker.go
├─ driver/kernel_dispatch.go           (수정)
└─ config/m1_configs.yaml              📌📌 iso-coverage, InfiniteCapacity=true

scripts/
├─ run_m1.sh
├─ 01_load.py ~ 08_sanity.py
├─ 09_ds_optimal.py, 10_entropy.py, 11_clustering.py
└─ 📌📌 12_track_consistency.py         (v1.2)

workload/
└─ patches/*.patch                      (DS annotation macro, 필요 시)

results/m1/
├─ raw/ (parquet per run + phase_ds_snapshot.parquet)
├─ 📌📌 trace/{workload}_R64B.parquet   (v1.2 Track B primary)
├─ optimal/{phase_optimal, ds_optimal, joint_optimal}.csv
├─ ds_table/
├─ figures/
│   ├─ timeline_*.pdf
│   ├─ heatmap_*.pdf
│   ├─ window_sensitivity.pdf
│   ├─ joint_heatmap_*.pdf
│   ├─ ds_bar_*.pdf
│   ├─ ari_clustering_*.pdf
│   └─ 📌📌 track_agreement_*.pdf        (v1.2)
├─ sanity_report.md
└─ reproduce.sh
```

---

## 5. 작업 순서 & 보고

1. PHASE A → B → C → D. 병렬 금지.
2. 각 PHASE 종료 보고:
   ```
   [PHASE X 종료 보고]
   - 완료 task: (모두 체크)
   - 미완 task: (있으면 이유)
   - Ethics clause self-check:
       실패 금지: PASS / 예외
       미달 금지: PASS / 예외
       추측 금지: PASS / 예외
   - 발견 리스크 (신규)
   - DS 축 상태: coverage, ARI, 특이사항
   - 📌📌 Intrinsic 축 상태: Track A↔B 일치율, metric 상관, eviction=0 유지
   - 다음 PHASE 승인 요청 여부
   ```
3. Commit message:
   ```
   [PHASE X / Task X-N] <요약>
   What: 변경
   Why: 근거 (문서 §X.X 또는 reviewer 방어)
   Risk: 완화
   ```

---

## 6. 금지 사항 요약

**구현 범위:**
- ❌ Sub-entry (PHASE 1)
- ❌ Promotion/demotion (PHASE 1~2)
- 📌📌 ❌ REC coalescing 활성화 (PHASE 2 P1 에서만)

**실험 무결성:**
- ❌ Workload 축소 조용히 결정
- 📌📌 ❌ Iso-storage 사용 (v1.1 잔재)
- 📌📌 ❌ Eviction > 0 인 상태로 결과 사용
- ❌ 예쁜 window 로 sensitivity crop
- ❌ Oscillation smoothing primary
- 📌📌 ❌ Track A ↔ B 불일치 phase outlier 제외
- ❌ Invariant V1~V12 중 하나라도 실패한 상태로 결과 사용

**분석 무결성:**
- ❌ DS 임의 merge
- ❌ Clustering hyperparameter 결과 보고 튜닝
- ❌ M1-P4/P5/P6 임계 사후 조정 (사전 승인 없이)
- ❌ DS coverage 미달 workload 조용히 제외
- ❌ Joint heatmap DS merge/제외
- 📌📌 ❌ Metric 간 상관 > 0.9 발견해도 숨기고 3 metric 모두 primary 로 주장

**서술 무결성:**
- ❌ "likely", "expected", "should"
- ❌ M1 단독 "adaptive beneficial" 결론
- ❌ "이 DS 는 matrix 니까" 추측
- 📌📌 ❌ **"Intrinsic 하므로 실제 시스템에서도 성립할 것"** 추측 — M1 은 "intrinsic signal exists" 까지만

---

## Appendix A — 명제 실패 대응

| 실패 | 대응 |
|------|------|
| M1-P1 (phase optimal 일정) | DS 축 / address 축 variation 확인. 있으면 공간 축 pivot. 둘 다 없으면 §9 R1 — "scalability + metadata redundancy" pivot |
| M1-P2 (3 metric agreement < 70%) | 3 metric 다른 bottleneck 지목. Supplement 전부 공개. Primary = L2 hit rate. Conflict phase 분해 |
| M1-P3 (phase 단일 값 dominant) | Motivation 재설계. "Workload 간 optimal 차이" 축 강화 |
| M1-P4 (DS 단일 값 dominant) | "DS variation 약함" 명시. DS 는 supplement |
| M1-P5 (joint < marginal) | "phase 와 DS 독립" 인정. Adaptive 정당성을 phase/DS 각각 축으로만. Joint 주장 제거 |
| M1-P4+P5 모두 미달 | DS motivation 제거. Angle "phase adaptive" 단순화 |
| 📌📌 **M1-P6 (Track A↔B 일치 < 80%)** | "결론이 simulator-specific" 인정. 낮은 일치율의 metric 별 분해. Trace-only 로 robust 한 metric (utilization, consistency) 만 primary 로, L2 hit 은 supplement |
| 📌📌 **전체 M1 명제 실패 (intrinsic signal 없음)** | **가장 심각**. Motivation 을 "intrinsic signal" 축에서 "metadata redundancy + scalability" 축으로 전면 pivot. 본 v1.2 실험 결과는 Negative result 로 Limitations 에 정직하게 기술 |

---

## Appendix B — 사용자 개입 지점

1. REC directory module 미존재 (R0) — **v1.2 에서는 덜 중요** (REC 사용 안 함) 하지만 PHASE 2 위해 여전히 확보 필요
2. Pilot 예상 2× 초과
3. Bit-identical 설명 가능 이유 실패
4. 📌📌 ~~Iso-storage 정수 비허용~~ (제거) — **Iso-coverage entry 수 산정** 으로 대체: `ceil(L2/R) × safety_factor` 의 safety_factor 값 결정
5. 3 metric 중 2개 반대 방향 optimal phase > 30%
6. Trace logger overhead > 1%
7. DS coverage < 90% 과반
8. Clustering silhouette 최대가 cluster=1 또는 전체 (실패)
9. ARI < 0.6
10. Allocation overlap 감지
11. M1-P5 임계 근처 (13~17%)
12. DS 내 intra-DS entropy 매우 높음
13. 📌📌 **Infinite directory 메모리 footprint 가 simulation host 의 가용 메모리 초과** (large-enough fallback 여부)
14. 📌📌 **M1-P6 임계 근처 (75~85%)** — 임계 재설정 사전 승인
15. 📌📌 **3 intrinsic metric 간 상관 > 0.9** — 어느 metric 을 supplement 이동할지

---

## Appendix C — Invariant (v1.2 확장)

| ID | Invariant | 검증 |
|----|-----------|------|
| V1 | Per-phase L2 hits/misses 합 = total | `08_sanity.py` |
| V2 | ~~bit-identical baseline~~ → 📌📌 **R=64B + InfiniteCapacity 에서 coherence 정확성 (모든 read 가 valid copy 받음)** | Unit test |
| V3 | Directory entry 수 ≤ capacity | 📌📌 **V2.5 로 대체: capacity = ∞ 이므로 자동 통과** |
| V4 | 📌📌 Track A ↔ Track B intrinsic metric ±5%, L2 hit ±3% | `08_sanity.py` |
| V5 | Retired insts 합 = total | Runtime assertion |
| V6 | Total eviction + total inv ≤ total dir updates | Runtime assertion |
| V7 | sum(DSAccesses) == sum(AddrBucketAccesses) | `08_sanity.py` (DS_UNKNOWN 포함) |
| V8 | DS_UNKNOWN ≤ 10% per workload | `08_sanity.py` 경고 |
| V9 | Allocation overlap 0회 | Runtime assertion |
| V10 | H(opt\|phase,DS) ≤ H(opt\|phase), ≤ H(opt\|DS) | `10_entropy.py` |
| 📌📌 **V11** | **모든 config run 에서 DirectoryEvictions == 0** | Runtime assertion |
| 📌📌 **V12** | **RegionAccessedBytes ≤ RegionFetchedBytes per region per phase** (utilization ≤ 1) | Runtime assertion |

**V1~V12 중 하나라도 실패 시 결과 사용 금지.**

---

**문서 버전:** v1.2 (2026-04-19) — Baseline + infinite directory, workload intrinsic characterization
**시작 명령:** "PHASE A 부터 시작. A-1 부터 순서대로. 각 task 완료 시 ethics clause self-check. 📌📌 표시는 v1.0 → v1.1 → v1.2 변경점 추적용."
