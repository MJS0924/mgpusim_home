# M6 실험 계획 — Dual-Grain Directory의 Multi-GPU 불충분성 증명

> 본 계획서는 HPCA 2027 제출 Superdirectory 논문의 핵심 반박 실험을 설계한다. **MGD [Zebchuk MICRO 2013]이 "dual-grain으로 충분하다"고 결론 내린 CPU 환경과 달리, multi-GPU 환경에서는 dual-grain이 불충분함을 정량적으로 증명**하는 것을 목표로 한다. 본 계획은 `CPU_Prior_Work_Analysis.md`의 Tier 1 선행연구에 대한 직접적 반박 근거를 생산한다.

---

## 1. 배경 및 필요성

### 1.1 반박해야 하는 선행연구 주장

MGD 논문(Zebchuk, Falsafi, Moshovos. MICRO 2013)의 결론:
> "A simple dual-grain directory (DGD) obtains the majority of the benefit while tracking individual cache blocks and coarse-grain regions of 1KB to 8KB."

즉, CPU 환경에서는 (cache block + 단일 region) 두 단계로 multi-grain directory의 이익을 거의 모두 얻을 수 있다는 주장. 이 주장은 Superdirectory의 5-bank 설계(16KB/4KB/1KB/256B/64B)의 존재 이유를 직접적으로 위협한다.

### 1.2 HPCA 2027 Reviewer의 예상 공격

> *"MGD paper already showed that dual-grain is sufficient. Why do you need 5 grains for multi-GPU? Where is the evidence that GPU workloads fundamentally require more than 2 granularities?"*

**공격에 대한 증명 부재 상태로 제출하면 novelty 공격으로 reject될 가능성이 매우 높다.**

### 1.3 본 실험의 역할

- **M1~M5 (기존 motivation 실험)**: "multi-granularity가 유용하다"는 점을 증명.
- **M6 (본 실험)**: "dual-grain으로는 부족하고 multi-grain이 꼭 필요하다"는 점을 증명 — **MGD 결론을 multi-GPU 맥락에서 반박**.

---

## 2. 실험 가설 (Hypothesis)

본 실험은 다음 **3개의 hypothesis**를 실측으로 검증한다. 각 hypothesis는 실험 ID와 1:1 매칭된다.

### H1 (Workload Diversity Hypothesis)
> Multi-GPU workload 집합 내에서 **최적 region size의 분산이 CPU 대비 현저히 크다**. Single fixed region size(dual-grain 전제)로는 전체 workload의 성능을 최적화할 수 없다.

### H2 (Phase-Level Variance Hypothesis)
> **동일 workload 내에서도 phase에 따라 최적 region size가 2단계 이상 이동**한다. Dual-grain은 하나의 coarse region size를 고정하므로 phase에 적응할 수 없다.

### H3 (Sub-Region Sharer Divergence Hypothesis)
> Dual-grain의 coarse region 내부에서도 **sub-region별 sharer 집합이 서로 다른 경우**가 상당수 존재한다. Sub-entry 구조 없이 single sharer vector만 유지하면 false invalidation 또는 directory coverage 손실이 필연적이다.

**3개 hypothesis 중 최소 2개가 positive로 증명되어야 Superdirectory의 5-bank + sub-entry 설계가 정당화됨.**

---

## 3. 실험 구성 (Experimental Setup)

### 3.1 비교 대상 (Competing Configurations)

| ID | 구성 | Region sizes | Sub-entry | 비고 |
|----|------|--------------|-----------|------|
| **Baseline** | 단일 bank | 64B only | ❌ | REC 논문의 baseline과 동일 (8K entry) |
| **DGD-1K** | Dual-grain | 64B + 1KB | ❌ | MGD 논문의 best-case dual-grain |
| **DGD-4K** | Dual-grain | 64B + 4KB | ❌ | MGD 논문의 다른 dual-grain 선택지 |
| **DGD-8K** | Dual-grain | 64B + 8KB | ❌ | MGD가 제안한 상한 region size |
| **TGD** | Triple-grain | 64B + 1KB + 16KB | ❌ | 3-level 보간 |
| **QGD** | Quad-grain | 64B + 256B + 1KB + 16KB | ❌ | 4-level |
| **Superdir-w/o-SubEntry** | 5-bank, sub-entry 없음 | 64B + 256B + 1KB + 4KB + 16KB | ❌ | H3 검증용 |
| **Superdirectory** | 5-bank + sub-entry | 64B + 256B + 1KB + 4KB + 16KB | ✅ | 제안 기법 |
| **Ideal** | 무한 directory | 64B | — | 상한선 |

### 3.2 공정 비교 원칙 (Fair Comparison Requirements)

**미달 금지 조항 적용**: 아래 조건을 만족하지 못하면 결과를 main evaluation에 포함하지 않는다.

1. **동일 storage 비교(Iso-Storage)**: 모든 구성을 동일한 하드웨어 bit 예산에서 비교. Dual-grain의 region entry가 단일 bank보다 크다면 entry 수를 그에 맞춰 감소시킴.
2. **동일 promotion/demotion 메커니즘**: DGD 계열도 Superdirectory와 동일한 heuristic(sharer 일치 기반 promotion) 사용. Superdirectory에만 유리한 policy 적용 금지.
3. **동일 Eviction 정책**: 모든 구성 FIFO 또는 LRU 동일 적용.
4. **동일 NoC/MSHR 설정**: Region-aware MSHR은 Superdirectory에만 적용되지만, DGD 계열에도 region size에 맞춘 coalesced MSHR 허용.
5. **DGD의 공정 구현 검증**: MGD 논문의 CPU 수치와 공정 비교 가능한 재현 실험 먼저 수행(§5 재현 실험 참조).

### 3.3 Workload Set

| 카테고리 | Workload | 비고 |
|---------|----------|------|
| AMD APP SDK | ATAX, GEMM, GEMV, 2DCONV 등 | REC 논문에서 사용 |
| Heteromark | — | REC 재현을 위해 동일 사용 |
| Polybench | — | REC 재현 |
| SHOC | — | REC 재현 |
| Graph workload | PageRank (PR), BFS, ST | 불규칙 접근 — HMG 논문에서 고난이도 |
| ML/AI (신규) | Transformer attention, Batched GEMM | HPCA 심사 대비 최신 workload |

**최소 15개 이상** 확보. 단일 region size로 최적화 불가능한 workload가 **최소 5개 이상** 포함되어야 H1 검증 가능.

---

## 4. 실험 항목 (Experiments)

### M6-1 — Workload별 최적 Region Size 분산 (H1 검증)

**목적**: 단일 dual-grain region size로는 multi-GPU workload를 커버할 수 없음을 증명.

**방법**:
1. 각 workload를 DGD-1K, DGD-4K, DGD-8K 세 가지 구성에서 실행.
2. 각 workload마다 **세 구성 중 최적 성능을 내는 region size**를 기록.
3. Workload set 전체에서 "최적 region size"의 분포 히스토그램 작성.

**Metric**:
- Per-workload optimal region size
- 각 region size가 "최적"이 되는 workload 비율

**H1 검증 기준 (Exit Criteria)**:
- 단일 region size가 전체 workload의 **80% 미만**에서만 최적이면 **H1 성립**.
- 즉, 어느 dual-grain 선택도 20% 이상의 workload에서 suboptimal이면 multi-grain 필요성 증명.
- 반대로 단일 region size(예: 1KB)가 90% 이상 workload에서 최적이면 **H1 실패**, Superdirectory 설계 재검토 필요.

**예상 결과**: GPU workload는 CPU 대비 working set 크기와 sharing pattern이 다양하므로 최적 region size가 workload마다 다를 것으로 가설하나, **실험 전에 단정 금지**.

---

### M6-2 — Phase-Level 최적 Region Size 변화 (H2 검증)

**목적**: 동일 workload 내에서도 phase마다 최적 region size가 변하여 fixed dual-grain이 phase에 적응 불가함을 증명.

**방법**:
1. 대표 workload 3~5개 선정 (M6-1에서 region size 선호가 뚜렷한 workload).
2. Workload 실행을 **1000개 이상의 time window(또는 kernel invocation)**로 분할.
3. 각 phase별로 DGD-1K, DGD-4K, DGD-8K, Superdir 네 구성을 "on-the-fly"로 전환하여 phase별 성능 측정(또는 오프라인 분석).
4. Phase별 "최적 region size"의 시계열 graph 작성.

**Metric**:
- Phase별 optimal region size trace
- Phase 전환 빈도 (phase transition rate)
- 단일 fixed region size가 달성하는 성능 대비 "oracle(phase-adaptive)" 성능 gap

**H2 검증 기준**:
- 최소 3개 workload에서 **phase별 최적 region size가 2단계 이상 변화**하고, 변화가 전체 실행의 **20% 이상의 시간**을 차지하면 **H2 성립**.
- Oracle phase-adaptive 대비 best fixed dual-grain의 성능 gap이 **10% 이상**이면 강한 증거.

**예상 결과**: 동일 워크로드 내에서 init phase(큰 region 선호) → compute phase(작은 region 선호) → reduction phase(중간) 같은 패턴이 관찰될 것으로 가설. **실측으로 확인 전 단정 금지**.

---

### M6-3 — Sub-Region Sharer Divergence (H3 검증)

**목적**: Dual-grain의 coarse region 내부에서 sub-region별 sharer가 갈라지는 경우가 흔함을 증명, sub-entry 구조의 필요성 정당화.

**방법**:
1. Baseline을 64B cacheline 단위 directory로 설정하고, 각 cacheline의 sharer 집합을 fully 추적.
2. 가상의 1KB region(16 cacheline)마다 내부 sub-region(256B = 4 cacheline)을 정의.
3. Region eviction 시점에 각 sub-region의 sharer 집합을 비교:
   - **Case A (fully agreeing)**: 모든 sub-region이 동일 sharer → dual-grain에 적합
   - **Case B (partially agreeing)**: sub-region마다 sharer가 다름 → sub-entry 없이는 false invalidation 또는 coverage 손실 발생
4. Case B의 비율 측정.

**Metric**:
- % of regions in Case A (fully agreeing sub-regions)
- % of regions in Case B (diverging sub-regions)
- Case B에서 dual-grain이 유발하는 false invalidation 수 (추정)

**H3 검증 기준**:
- Case B 비율이 평균 **20% 이상** → sub-entry의 필요성 정당화.
- Case B 비율이 10% 미만이면 sub-entry 설계의 가치 재검토 필요.

**예상 결과**: 1KB region 내부에서 sub-region별 sharer 차이가 상당할 것으로 가설(특히 sparse access, graph workload). **실험으로 확인 전 단정 금지**.

---

### M6-4 — 직접 성능 비교 (Main Result)

**목적**: Baseline / DGD variants / Superdirectory의 실질적 성능을 직접 비교하여 multi-grain의 우위를 증명.

**방법**:
1. §3.1의 모든 구성을 동일 iso-storage 조건에서 비교.
2. 각 구성에서 15개 workload의 normalized IPC 측정.
3. Geometric mean speedup 산출.

**Metric**:
- Per-workload normalized IPC
- Geometric mean speedup (normalized to baseline)
- Speedup distribution (min, median, max across workloads)

**Exit Criteria**:
- **Superdirectory > best DGD variant**: geometric mean speedup에서 최소 **5% 이상** 우위.
- **Superdirectory > DGD-1K**: MGD의 best-case dual-grain보다 반드시 우위.
- 열위 workload가 있다면 **원인을 분석하고 논문에 명시**(실패 금지 조항 적용).

**음성 결과 처리 (Negative Result Handling)**:
- Superdirectory가 DGD 대비 geometric mean 5% 미만 차이면, **Superdirectory의 5-bank 설계가 multi-GPU에서도 overkill**일 가능성을 인정해야 한다.
- 이 경우 설계를 3-bank 또는 4-bank로 축소하거나, **contribution을 sub-entry 구조와 multi-GPU 적용으로 재포지셔닝**한다.
- 결과를 숨기지 않고 논문 Limitations 섹션에 명시한다.

---

### M6-5 — False Invalidation 분석 (Ablation 보조)

**목적**: Dual-grain에서 coarse region 단위 invalidation이 만드는 false invalidation을 정량화하여 Superdirectory의 sub-entry가 해결하는 문제 크기를 제시.

**방법**:
1. DGD-1K, DGD-4K, Superdirectory 세 구성에서 write 발생 시 invalidation 대상 cacheline 수를 집계.
2. "실제로 write된 cacheline"과 "같은 region의 다른 cacheline"의 비율 분석.
3. 불필요하게 invalidate된 cacheline의 전체 L2 traffic 기여도 측정.

**Metric**:
- False invalidation rate = (불필요 inv cacheline 수) / (총 inv cacheline 수)
- False invalidation으로 유발된 추가 L2 miss 수
- NoC traffic 중 false inv가 차지하는 비율

**Exit Criteria**:
- DGD-4K에서 false invalidation rate가 평균 **15% 이상**이면 coarse region의 부작용 증명 성립.
- Superdirectory가 이 rate를 **5% 미만**으로 감소시키면 sub-entry의 효과 증명.

---

## 5. DGD Baseline 공정 구현 절차

**미달 금지 조항 강력 적용**: DGD를 부정확하게 구현하여 Superdirectory가 우위를 보이는 것처럼 만들지 않는다.

### 5.1 구현 단계

1. **MGD/DGD 원 논문 재숙지**: Zebchuk 2013 MICRO 논문의 §3 (DGD design) 정밀 재독.
2. **MGPUSim에 DGD 모듈 구현**:
   - Region entry 구조: common base + per-block present bit + region-level sharer bit-vector
   - Block entry 구조: 기존 cacheline directory entry
   - Region↔Block 전환 로직: block이 처음 shared되면 region entry를 일반 block entry로 split
3. **단위 테스트**: Region eviction, block promotion, 동시 race case 모두 단위 테스트 통과.

### 5.2 MGD 재현 검증 (Reproducibility Check)

- DGD 구현이 MGPUSim에서 동작하는 경우, **단일 GPU 구성**(MGD 논문 환경 유사)에서 baseline 대비 directory entry 수 감소율 측정.
- MGD 논문의 수치(41–66% entry 감소) 대비 **±15% 이내** 재현되어야 DGD 구현이 타당하다고 판단.
- 재현 불가 시 구현 점검 후 재시도. **부정확한 DGD로 Superdirectory 우위를 주장하는 것은 연구 윤리 위반**.

---

## 6. 일정 및 PHASE 매핑

| 항목 | 소요 기간 | PHASE | 의존 관계 |
|------|----------|-------|----------|
| DGD MGPUSim 구현 | 1주 | PHASE 1 확장 | REC 재현 이후 |
| DGD 재현 검증 | 3일 | PHASE 1 확장 | DGD 구현 완료 후 |
| M6-1 (workload별 최적) | 4일 | PHASE 0 (확장) 또는 PHASE 2 | DGD 구현 완료 후 |
| M6-2 (phase-level) | 4일 | PHASE 2 | M6-1 이후 |
| M6-3 (sub-region divergence) | 3일 | PHASE 0 (확장) | baseline만 필요 |
| M6-4 (직접 성능 비교) | 5일 | PHASE 2 Main | DGD/TGD/QGD/Superdir 모두 구현 후 |
| M6-5 (false inv 분석) | 3일 | PHASE 3 Ablation | M6-4 이후 |

**권장 조정**:
- 현재 계획서의 PHASE 1(2026-05-04 ~ 2026-05-24) 3주를 **4주로 연장**하여 DGD 구현 및 재현 검증 포함.
- PHASE 2(2026-05-25 ~ 2026-06-14)의 Main Evaluation에 M6-4를 필수 포함.
- PHASE 0에서는 M6-3(sub-region divergence)만 선제적으로 수행하여 motivation 섹션 보강.

---

## 7. 성공/실패 판정 매트릭스

### 7.1 성공 시나리오 (Superdirectory 설계 정당화)

| H1 | H2 | H3 | 판정 | 대응 |
|----|-----|-----|------|------|
| ✅ | ✅ | ✅ | **완전한 정당화** | Superdirectory를 원안 그대로 논문화 |
| ✅ | ✅ | ❌ | Sub-entry 약화 | Sub-entry를 optional 구성으로, bank 다중화가 핵심 |
| ✅ | ❌ | ✅ | Phase 적응 불필요 | Multi-grain + sub-entry는 유지, promotion/demotion은 단순화 |
| ❌ | ✅ | ✅ | Workload diversity 약화 | Phase 적응 중심으로 재포지셔닝 |

### 7.2 부분 실패 시나리오 (재설계 필요)

| H1 | H2 | H3 | 판정 | 대응 |
|----|-----|-----|------|------|
| ✅ | ❌ | ❌ | 단순 fixed dual-grain도 충분 | **5-bank 설계 포기**, workload별 고정 region size 선택 기법으로 재포지셔닝 |
| ❌ | ✅ | ❌ | Phase 적응만 유효 | 2-level adaptive로 재설계 |
| ❌ | ❌ | ✅ | Sub-entry만 유효 | Fixed single-grain + sub-entry만으로 축소 |

### 7.3 완전 실패 시나리오

| H1 | H2 | H3 | 판정 | 대응 |
|----|-----|-----|------|------|
| ❌ | ❌ | ❌ | **Superdirectory 설계 전면 재검토** | 논문 positioning 완전 변경: dual-grain DGD의 GPU 적용 + GPU-specific 최적화로 축소. HPCA 제출 자체 재고. |

**연구 윤리 조항 적용**: 완전 실패 시에도 결과를 숨기지 않는다. PHASE 0 완료 시점에 부분/완전 실패 시나리오로 판정되면 즉시 지도교수와 논의하여 논문 방향을 honestly 조정한다.

---

## 8. Reviewer 대응 준비 (예상 추가 질문)

### Q1. "DGD-1K, DGD-4K, DGD-8K 외 다른 region size를 시도했는가?"
→ 사전에 2KB, 16KB 등을 parameter sweep으로 측정하여 supplementary에 포함.

### Q2. "MGD 논문의 수치와 왜 다른가?"
→ §5.2 재현 검증 결과를 본문에 명시. Multi-GPU 환경의 고유 특성이 수치 차이를 만드는 원인임을 설명.

### Q3. "왜 5-bank인가? 6-bank, 7-bank는?"
→ Ablation A1 결과(PHASE 3)에서 2/3/4/5/6/7-bank 전체 sweep 결과 제시. 본 실험에서는 A1의 예비 결과를 참조.

### Q4. "SCT[Alisafaee 2012] baseline도 필요하지 않은가?"
→ SCT의 counter 기반 promotion을 Superdirectory 프레임워크에 이식한 variant를 optional baseline으로 준비. 시간 제약 시 Limitations에 포함.

### Q5. "Phase 전환 오버헤드는?"
→ M6-2에서 phase transition rate을 측정하여 promotion/demotion overhead와 비교. Ablation B2(oscillation)와 연계.

---

## 9. 산출물 (Deliverables)

- `dgd_baseline/`: DGD MGPUSim 구현 코드
- `m6_results/M6-1_workload_diversity.pdf` + raw data
- `m6_results/M6-2_phase_level_variance.pdf` + raw data
- `m6_results/M6-3_sub_region_divergence.pdf` + raw data
- `m6_results/M6-4_direct_performance.pdf` + raw data (Main Evaluation 그래프)
- `m6_results/M6-5_false_invalidation.pdf` + raw data
- `m6_results/mgd_reproduction_check.pdf` (DGD 재현 검증)
- `m6_results/hypothesis_decision_matrix.md` (H1/H2/H3 판정 결과)

---

## 10. 연구 윤리 조항 (M6 전용)

### 10.1 실패 금지
- M6의 세 hypothesis(H1, H2, H3) 중 어느 것이 실패하든 결과를 삭제하지 않고 `logs/m6/` 디렉터리에 전량 보존한다.
- Hypothesis 실패 시 Risk Register의 R8 업데이트 및 논문 positioning 재검토 기록을 남긴다.
- Negative result도 논문에 포함될 수 있음을 전제로 실험을 설계한다.

### 10.2 미달 금지
- DGD baseline이 MGD 원 논문 수치와 ±15% 이내로 재현되지 않으면, Main Evaluation에 DGD 결과를 **포함하지 않는다**. 재현 검증 통과 전까지는 M6-4의 Superdirectory vs DGD 비교를 본문 결과로 사용하지 않는다.
- Iso-storage 조건이 불성립한 상태로 "Superdirectory가 더 빠르다"는 주장을 하지 않는다.

### 10.3 추측 금지
- 본 계획서의 "예상 결과" 문구는 모두 **가설**일 뿐이며, 실험 결과로 확정되기 전까지 논문 본문에 서술하지 않는다.
- "GPU는 CPU와 다르다"는 일반론을 H1/H2/H3 실측 데이터 없이 사용하지 않는다.
- MGD/Cuesta 등 CPU 선행연구의 결론을 근거 없이 "GPU에 적용되지 않는다"고 단정하지 않는다.

---

## 11. Cross-Reference

- 본 실험의 motivation 배경: `CPU_Prior_Work_Analysis.md` §2 (Tier 1 선행연구).
- Risk Register 업데이트: `HPCA2027_Superdirectory_논문작성계획서.md § 7`의 R8 항목 참조.
- Main Evaluation 통합: `experiment_plan.md §3 Main 실험 계획` 내 P1과 M6-4 연계.
- Ablation 연계: 본 실험의 결과는 Ablation A1(region size 개수)과 A9(static vs dynamic)의 핵심 근거를 제공.

---

*문서 버전*: v1.0 (2026-04-20 작성)
*다음 리뷰 예정*: PHASE 1 종료 시점(2026-05-24)에 DGD 재현 검증 결과 기반으로 실험 항목 조정 재검토.
