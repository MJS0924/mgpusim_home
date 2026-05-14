# Superdirectory: Multi-GPU Cache Coherence Directory의 용량 한계 극복을 위한 계층적 적응형 Directory 구조

## HPCA 2027 제출 목표 논문 작성 계획서

---

## 0. 프로젝트 개요

### 0.1 타겟 학회 및 제출 일정

| 항목 | 내용 | 근거 |
|------|------|------|
| 타겟 학회 | HPCA 2027 (33rd IEEE Int'l Symposium on High-Performance Computer Architecture) | hpca-conf.org |
| 예상 제출 마감 | 2026년 7월 하순 ~ 8월 초 | HPCA 2026은 2025-08-01 마감. HPCA는 관례적으로 7월 말~8월 초 마감 유지 |
| 회의 개최 | 2027년 2월 (장소 TBD) | casys-kaist deadline tracker |
| 양식 | 본문 12p + 확장 2p = 14p, references 무제한 | HPCA 2026 규정(2027도 유지 가능성 매우 높음, 마감 직전 CFP 재확인 필수) |

> **주의:** HPCA 2027 CFP가 공지되는 즉시(통상 4~5월) 페이지 수, 포맷, 리뷰어 연속성 정책 등을 재확인한다. CFP가 확정되기 전까지는 HPCA 2026 규정을 기준으로 작업한다.

### 0.2 연구 One-line Summary

> **Multi-GPU coherence directory의 용량 한계는 단순 확장(REC의 base+offset 압축, HMG의 4-CL 고정 그룹핑)으로는 스케일링에 한계가 있으므로, workload phase에 따라 coherence 관리 단위를 16KB ~ 64B 사이에서 동적으로 조절하는 Superdirectory를 제안하여 동일 하드웨어 용량으로 directory effective coverage를 크게 확장한다.**

### 0.3 핵심 Contribution (초안 — PHASE 진행 중 계속 refine)

1. **문제 정량화:** 기존 최신 기법(REC, HMG)이 GPU 개수 증가 시 sharer 비트 선형 증가로 인해 entry당 storage가 급격히 커져(REC: 4-GPU 52b → 16-GPU 295b, 약 5.7×), 확장성 병목이 발생함을 정량적으로 입증.
2. **설계:** 5개 bank(16KB/4KB/1KB/256B/64B)의 hierarchical directory + sub-entry 구조로 **coarse base + fine-grained sharer tracking**을 동시에 제공하여 coherence의 정확성을 유지하면서 메타데이터 redundancy를 제거.
3. **정책:** Sharer 일치 기반 Promotion과 사용량 기반 Demotion, Region Size Buffer를 통한 과거 경험 재사용으로 thrashing을 억제.
4. **구현/평가:** MGPUSim을 확장하여 4/8/16-GPU 환경에서 15개 이상의 workload로 REC/HMG/Baseline/Ideal 대비 성능·NoC traffic·L2 hit rate·directory eviction·하드웨어 오버헤드를 종합적으로 평가.

---

## 1. 연구 목적 및 배경

### 1.1 문제 맥락

- AI 및 HPC workload의 연산·메모리 수요 증가로 단일 GPU의 능력을 초과하는 multi-GPU 시스템(NVIDIA DGX, AMD MI-series 등)이 주류가 되고 있다.
- Multi-GPU 시스템에서는 workload의 공유 특성 때문에 원격 GPU 메모리에 접근하는 **NUMA 오버헤드**가 성능의 주요 병목이 된다. 이를 완화하기 위해 원격 데이터를 L2 cache까지 캐싱하는 기법들이 연구되어 왔다.
- 원격 L2 캐싱을 활성화하려면 cacheline 단위의 coherence를 유지해야 하며, 최신 연구들은 **coherence directory**를 도입하여 sharer를 추적하고 write 발생 시 invalidation을 전파한다(REC, HMG 등).

### 1.2 기존 기법의 한계

기존 fine-grained coherence directory는 다음과 같은 근본적 한계를 가진다:

1. **용량 한계:** Directory 용량이 L2 capacity의 몇 %에 불과해 빈번한 eviction이 발생하고, 이는 sharer 측 L2 cacheline의 premature invalidation을 유발해 L2 miss rate를 악화시킨다. REC 논문은 premature invalidation을 모두 제거하려면 directory 크기를 baseline 대비 **최대 12×까지 키워야 하며, 이는 L2 면적의 30% 이상**을 차지함을 보였다(Fig. 6, 7).
2. **스케일링 오버헤드:** REC는 16개 연속 cacheline을 하나의 entry에 묶지만, GPU 수 증가 시 sharer 비트가 선형 증가하여 entry 크기가 급증한다. 저자들은 8-GPU에서 167b(≈3×), 16-GPU에서 295b(≈5×)가 됨을 명시했다(§4.4 Scalability).
3. **고정 granularity:** HMG는 4-cacheline을 정적으로 묶어 directory 효율을 높이지만, 각 sub-cacheline의 sharer를 분리 추적하지 못해 false invalidation과 cache pollution을 야기한다. REC는 base+offset으로 압축하지만 **coherence 관리 단위는 여전히 cacheline**이며, workload별로 최적 관리 단위가 다른 점을 활용하지 못한다.

### 1.3 연구 질문

- **RQ1:** Workload phase에 따라 최적 coherence 관리 단위(region size)가 실제로 달라지는가? (Motivation)
- **RQ2:** Directory entry들 사이의 공간적 중복(spatial metadata redundancy)이 어느 정도 존재하며, 정적 그룹핑(HMG)이나 압축(REC)만으로는 왜 충분하지 않은가?
- **RQ3:** 동적 region size 조절이 fine-grained correctness(정확한 write invalidation)를 유지하면서 directory effective coverage를 확장할 수 있는가?
- **RQ4:** Lookup latency·race condition·하드웨어 복잡도의 overhead를 통제한 상태에서, iso-storage 비교 시 REC/HMG 대비 얼마의 성능 이득을 얻을 수 있는가?

---

## 2. 선행 연구 비교 분석 (Reviewer 관점)

HPCA 심사위원은 제안 기법이 **SAC·HMG·REC**와 어떻게 차별화되는지를 가장 먼저 확인한다. Day-one에 이 표를 정면 돌파할 수 있어야 한다.

| 기준 | Baseline VI | HMG [HPCA'20] | REC [JSA'25] | SAC [MICRO'20] | **Superdirectory (Ours)** |
|------|-------------|---------------|--------------|----------------|---------------------------|
| 관리 단위 | Cacheline (64B) | 4-cacheline 정적 그룹 | Cacheline (base+offset 압축) | Cacheline (LLC-partition) | **적응형 64B~16KB (5 bank)** |
| Sharer 추적 granularity | 각 CL 독립 | 4-CL 공유 (false inv 발생) | 각 CL 독립 | 각 CL 독립 | **Sub-entry로 각 sub-region 독립** |
| 용량 효율 (entry 당 cover) | 64B | 256B (정적 4×) | ≤ 1KB (base+offset 16 CL) | N/A (LLC 재구성) | **64B~16KB 동적** |
| GPU scalability (sharer bits) | N×1b | N×1b | N×16b (entry당) | N×1b | N×4b (sub-entry당) |
| 적응성 | 없음 | 없음 | 없음 | sharing-aware 재구성 | **Runtime promotion/demotion** |
| 추가 HW | 없음 | 없음 | 미미 | LLC 재구성 로직 | BF + RSB + Region-aware MSHR |
| 주 혁신 | — | 계층적 sharer 추적 | Spatial 압축 | LLC 공유 인식 재구성 | **Hierarchical directory + adaptive granularity** |

### 2.1 반드시 구축해야 할 "Delta argument"

Reviewer가 "REC에 그냥 adaptive granularity 얹은 거 아닌가"라고 물었을 때의 대답:

- **REC는 coherence 단위가 cacheline으로 고정**되어 있어 workload가 큰 단위의 공유를 선호할 때에도 16개의 sharer 비트 벡터를 유지해야 한다. Superdirectory는 coherence 단위 자체를 확장하되, **sub-entry 구조로 sub-region별 독립 sharer를 유지**하여 false invalidation을 피한다.
- **HMG는 정적 4-CL**이지만 Superdirectory는 5단계 중 workload가 선택. 또한 HMG의 고정 4-CL은 sub-entry별 독립 sharer가 없어 false invalidation이 필연적이다 (REC 논문 §2.3에서도 지적됨).
- **SAC는 LLC capacity 재배분** 기법이지 directory 스케일링 기법이 아니다. Orthogonal하며, 원칙적으로 SAC + Superdirectory 결합 가능 (future work).

---

## 3. 제안 기법: Superdirectory

### 3.1 구조 개요

```
┌──────────────────────────────────────────────────────────────┐
│              Superdirectory (home GPU당 1개)                   │
│                                                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Bank 0   │  │ Bank 1   │  │ Bank 2   │  │ Bank 3   │  │ Bank 4   │  │
│  │ 16KB     │  │ 4KB      │  │ 1KB      │  │ 256B     │  │ 64B      │  │
│  │ region   │  │ region   │  │ region   │  │ region   │  │ region   │  │
│  │ (coarse) │  │          │  │          │  │          │  │ (fine)   │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
│                                                                │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────┐     │
│  │ Bloom Filter │   │ Region Size  │   │ Region-aware   │     │
│  │ (per bank)   │   │ Buffer (RSB) │   │ MSHR (shared)  │     │
│  └──────────────┘   └──────────────┘   └────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Entry / Sub-Entry 구조

- 각 Bank의 Entry는 **공통 base address + 4개의 sub-entry**로 구성된다.
- 각 sub-entry는 자신만의 **sharer bit-vector (N-1비트, N = GPU 수)**와 상태 비트를 독립적으로 유지한다.
- 이 구조는 REC의 "공통 base + per-address sharer" 아이디어를 계층화한 것으로, 한 단계 coarse bank로 promotion하면 1개 entry가 직전 bank의 4개 entry를 대체한다.

| Bank | Region size | 커버 주소 범위 | Sub-entry당 단위 | Entry 당 sub-entry 수 |
|------|-------------|----------------|------------------|-----------------------|
| 0 | 16KB | 16KB | 4KB | 4 |
| 1 | 4KB | 4KB | 1KB | 4 |
| 2 | 1KB | 1KB | 256B | 4 |
| 3 | 256B | 256B | 64B | 4 |
| 4 | 64B | 64B | 16B | 4 |

> 설계 근거: 4×씩 증가는 ablation으로 검증 필요(실험 A2). 16×씩 vs 4×씩 중 최적값은 workload별로 다를 수 있다. **실험 전에는 4× 우세라고 단정하지 않는다**(추측 금지 원칙).

### 3.3 Entry 할당 / 승격 / 강등 정책

1. **최초 할당 원칙:** 모든 entry는 가장 fine-grained인 Bank 4(64B)에서 시작한다. RSB 또는 페이지 테이블 힌트가 있을 경우만 예외적으로 상위 bank에 직접 할당.
2. **Promotion 조건:** Bank k의 1 entry에서 4개 sub-entry의 sharer가 모두 동일해지면 Bank k-1로 승격. 승격 시 Bank k-1에 1 entry를 할당하고 Bank k의 4 entry를 invalid 처리(데이터는 그대로, 메타데이터만).
3. **Demotion 조건:** Eviction 시점에 **실제 사용된(sharer가 1 이상인) sub-entry 비율이 7/8 미만이면 Bank k+1로 강등**. 강등 후 남은 valid sub-entry만 fine-grained bank에 재삽입.
4. **Demotion threshold (7/8) 선정 근거:** 가정이므로 ablation으로 반드시 검증(A8). 1/2, 5/8, 3/4, 7/8, 15/16을 비교한 뒤 근거를 기술한다.

### 3.4 Auxiliary 구조

#### 3.4.1 Region Size Buffer (RSB)

- **목적:** (1) Eviction/Invalidation된 region의 직전 bank를 기억하여 재요청 시 fine-grained bank부터 다시 promotion되는 과정을 회피. (2) Kernel boundary burst flush에서도 capacity thrashing 없이 hint를 보존하며, kernel 전환 시 stale hint 억제.
- **구조:** **Sectored set-associative** 버퍼 (기본 S=32, W=8, K=4). 각 entry는 공통 `Base Tag` + `Kernel ID (16b)` + K개 sub-slot `(offset, region_id, conf)`로 구성. Sub-slot의 `conf`는 HIGH/MEDIUM/LOW/INVALID 4단계. 상세 설계는 `design_document.md §4.1` 참조.
- **Kernel identity 획득:** HSA AQL kernel dispatch packet의 `kernel_object` 필드 (kernel entry PC)를 command processor가 16-bit hash로 축약하여 directory controller에 broadcast. Programmer/compiler/ISA 변경 없음.
- **Inter-kernel 제어 (§design_document §4.1.4):** Kernel dispatch 시 RSB entry의 `kernel_id`와 새 kernel_id를 비교하여 (동일 → 유지) / (recent-N window 내 → confidence decay) / (window 밖 → invalidate) 로 분기.
- **사용 규칙:** (1) Directory lookup 시 가장 먼저 조회 → (2) Hit 시 confidence level에 따라 처리 (HIGH: 정상 hint + BF staleness defense / MEDIUM: hint + fine-grained fallback / LOW: hint 무시) → (3) 사용된 sub-slot은 consume.
- **파라미터 고정:** Main evaluation은 기본값 (S=32, W=8, K=4, coalescing=4KB, hash=16b, recent-N=4)으로 고정. Parameter sweep은 optional ablation A5로 격하.

#### 3.4.2 Per-bank Counting Bloom Filter (BF)

- **목적:** Serial bank lookup에서 불필요한 bank 접근을 조기 차단.
- **구조:** Bank당 counting BF. Counter 비트 수 기본 8b.
- **Lookup 정책:** RSB miss 시 BF를 조회하여 finer 순 정렬된 candidate list 반환. Hint 없으면 Bank 4부터 탐색.

#### 3.4.3 Region-aware MSHR (Shared)

- **목적:** Promotion/Demotion 진행 중 동일 region에 대한 요청을 region size 필드 + masking으로 merge.
- **설계 결정:** Shared(통합) 방식 채택. Per-bank 방식은 promotion/demotion 시 entry 이관 비용이 커서 race condition 처리가 복잡해지기 때문.

### 3.5 Scenario

#### 3.5.1 Remote Read

```
1. GPU_req → GPU_home: Read(addr)
2. home: RSB.search(addr)
     hit  → bank_id 확정, RSB.delete
     miss → BF.get_banks(addr)
              hit  → candidate list (finer-first)
              miss → Bank 4 (default)
3. Directory probe (candidate list 순서대로)
     hit  → region size 단위로 batch response 전송
     miss → 결정된 bank에 신규 allocation
4. Sharer update, response → GPU_req
```

#### 3.5.2 Remote Write

```
1. GPU_req → GPU_home: Write(addr, data, [region_size_hint from PTE])
2. Directory lookup (동일 경로)
3. Case A (Hit, unique sharer): 즉시 write
   Case B (Hit, multiple sharers):
       - 해당 sub-region에 invalidation 전파
       - Demotion 발생: 나머지 sub-region은 fine-grained bank로 이동
       - RSB update
   Case C (Miss):
       - RSB hint > PTE hint > BF finest > Bank 4 순으로 할당 bank 결정
4. Write ack → GPU_req
```

> **Open question:** GPU workload에서 read/write가 서로 다른 bank에 동시 발생하는 빈도가 매우 낮다면, write-evict 단순화 가능성 있음. 실험 M2/C3에서 검증.

---

## 4. 실험 방법론

### 4.1 시뮬레이터 / 환경

- **MGPUSim** 확장 구현. REC 논문과 동일 환경을 재현하여 공정 비교. REC은 MGPUSim에 directory 및 hardware coherence를 추가 구현한 확장판을 사용했다.
- 시뮬레이터 확장 모듈: (1) 5-bank Superdirectory, (2) BF/RSB, (3) Region-aware MSHR, (4) Promotion/Demotion FSM.

### 4.2 기준 아키텍처 (Baseline 및 비교 대상)

| Config | 설명 |
|--------|------|
| Baseline | 8K-entry 단일 bank VI directory (REC 논문 baseline과 동일) |
| Baseline(2×) | 16K-entry (동일 storage 비교용) |
| HMG | 4-CL static grouping |
| REC | Base+offset coalescing, 1KB range |
| **Superdirectory** | 제안 기법 |
| Ideal | Infinite directory (no eviction-initiated invalidation) |

### 4.3 Workload Set (최소 15개)

- REC가 사용한 세트: AMDAPPSDK(ATAX, GEMM, GEMV, 2DCONV 등), Heteromark, Polybench, SHOC → 이를 모두 재현.
- 추가 필요: **ML inference kernel** (transformer attention, GEMM with batching) — HPCA 심사에서 "최신 AI workload" 요구에 대응.
- 최종 선정은 PHASE 1에서 확정(미달 금지: 15개 미만 시 일정 조정해서라도 수집).

### 4.4 Metric

| Metric | 정의 | 확인하려는 가설 |
|--------|------|----------------|
| Normalized IPC / Speedup | 대비 Baseline | 전체 성능 이득 |
| L2 hit rate | L2 cache access 중 hit 비율 | Premature invalidation 감소 |
| L2 miss rate | | 동일 |
| Directory eviction count | | Effective coverage 확대 |
| Evict-initiated invalidation ratio | (REC Fig. 5와 동일 정의) | Unnecessary invalidation 감소 |
| NoC traffic breakdown | Read/Write/Inv/Data | 네트워크 효율 |
| Directory effective coverage | 1 entry가 cover하는 L2 address 평균 | 저장 효율 |
| Avg. lookup latency / bank probe count | | Serial lookup 오버헤드 |
| Hardware overhead | bits + CACTI area/power | Net positive 증명 |

---

## 5. PHASE별 실행 계획 (연구 윤리 조항 포함)

> 모든 PHASE에 공통으로 적용되는 **연구 윤리 조항(Integrity Clause)**
>
> - **실패 금지(No Fabrication):** 실험이 기대와 다르게 나오면 **원인을 명시적으로 기록하고 다음 PHASE로 은폐된 채 넘어가지 않는다.** 실패한 실험은 삭제하지 않고 logs/ 디렉터리에 보존한다. 실패 결과는 Risk Register에 업데이트한다.
> - **미달 금지(No Inflation):** 각 PHASE의 exit criteria를 충족하지 못한 상태로 다음 PHASE를 시작하지 않는다. 불가피하게 일정 조정이 필요하면 계획서를 공식 revise하고 원인/대안을 기록한다.
> - **추측 금지(No Speculation):** 모든 수치·비교·주장은 (a) 본인 실험 데이터, (b) 동료평가를 거친 문헌 인용, (c) 시뮬레이터/모델의 검증된 출력 중 하나의 근거를 반드시 제시한다. "예상된다", "~일 것으로 보인다" 같은 근거 없는 서술을 논문에 넣지 않는다.

---

### PHASE 0 — 설계 확정 및 Motivation 실증 (2026-04-20 ~ 2026-05-03, 약 2주)

#### 목표
- 설계 문서(design_document.md)를 PHASE 1에서 구현 가능한 수준으로 lock.
- Motivation 섹션을 지지할 실측 실험(M1~M5)을 완료.

#### 작업 항목 (WBS)
1. MGPUSim REC 확장 코드 확보 또는 재구현 착수(가능하면 원 저자에게 코드 요청, 미확보 시 재구현).
2. Motivation 실험 M1~M5 완수:
   - M1: Workload phase에 따라 최적 region size가 실제로 변함을 증명 (동일 워크로드 내 phase-level 변화 graph).
   - M2: False sharing 빈도 정량화 (HMG 스타일 4-CL 그룹핑 대비).
   - M3: Directory eviction에 의한 강제 miss 비율.
   - M4: Spatial correlation 정량 분석 (REC Fig. 12 스타일).
   - M5: Invalidation traffic breakdown (evict-initiated vs write-initiated).
3. Entry/sub-entry/promotion/demotion pseudocode finalize.
4. Open question 중 "region size 비율 4× vs 16×"는 PHASE 3 A2로 넘기되, 기본값 4×로 고정.

#### 산출물
- `motivation_results/M1-M5.pdf` 및 raw data
- `spec/superdirectory_v1.md` (구현용 동결 스펙)
- PHASE 1 구현 WBS

#### 검증 기준 (Exit Criteria)
- M1: 최소 3개 워크로드에서 optimal region size의 phase-level 변화 관찰.
- M4: Baseline directory entry 중 "spatially coalescable" 비율이 평균 **30% 이상**이어야 함 (미달 시 motivation 재정비).
- 설계 스펙의 의사결정 가능한 모든 항목 값 확정 (단, A1~A4, A6~A9 ablation 대상은 기본값만 고정; A5 관련 RSB 파라미터는 design_document §7.5 기본값 사용).

#### PHASE 0 윤리 조항
- 실패 금지: M1~M5 중 하나라도 motivation을 뒷받침하지 못하면 **이유를 기록**하고 논문 positioning을 재고한다. Motivation이 부정되는 결과를 숨기지 않는다.
- 미달 금지: Exit criteria 미달 시 PHASE 1을 시작하지 않고 연장.
- 추측 금지: 모든 motivation 주장에는 해당 실험 ID(M1~M5)를 인용한다. "일반적으로 그렇다"는 표현 금지.

---

### PHASE 1 — Superdirectory Core 구현 (2026-05-04 ~ 2026-05-24, 약 3주)

#### 목표
- MGPUSim에 Superdirectory의 **5-bank 구조 + Promotion/Demotion**을 구현.
- 단위 테스트 + REC 재현(정합성 확인).

#### 작업 항목
1. `DirectoryBank`, `Entry`, `SubEntry` 자료구조 구현.
2. Lookup (bank 우선순위, sub-entry 매칭) 구현.
3. Promotion FSM (sharer 일치 탐지 → bank 이동) 구현.
4. Demotion FSM (eviction 시 utilization 측정 → 재배치) 구현.
5. **REC 재구현 및 원 논문 수치와 대조** (공정 비교를 위한 기준선).
6. 단위 테스트: 4-cacheline promotion, 7/8 demotion, write에 의한 partial invalidation.

#### 산출물
- 시뮬레이터 소스 + 단위 테스트 리포트
- REC 재현 결과 vs 논문 수치 비교 표

#### 검증 기준
- 모든 단위 테스트 통과.
- REC 재현 성능이 원 논문(Speedup 1.327, L2 miss 감소 53.5%)과 **±10% 이내**.

#### PHASE 1 윤리 조항
- 실패 금지: 단위 테스트 실패 시 해당 기능 disable로 우회하지 않고 근본 원인 수정.
- 미달 금지: REC 재현이 ±10%를 초과하면 MGPUSim 파라미터 재검토 후 재실행. 미달 상태로 PHASE 2 착수 금지.
- 추측 금지: 구현 결정 근거를 commit message/design log에 기록. 심사 중 "왜 이 결정?"에 전부 답할 수 있도록 추적성 확보.

---

### PHASE 2 — Auxiliary 구조 통합 및 Main 성능 실험 (2026-05-25 ~ 2026-06-14, 약 3주)

#### 목표
- BF, RSB, Region-aware MSHR 통합.
- Main 실험 P1~P6 완수.

#### 작업 항목
1. Counting BF 구현 (counter 비트 기본 8b).
2. RSB 구현 — **sectored + set-associative** 구조 (기본 S=32, W=8, K=4). `design_document.md §4.1.1–4.1.3`을 따름. Sub-slot confidence 4단계 전이 구현.
3. **Kernel identity hook 구현** — Command processor의 kernel dispatch event에서 `kernel_object` 필드를 16-bit hash로 축약, directory controller broadcast. M1의 `driver/kernel_dispatch.go` hook을 재활용.
4. **Inter-kernel RSB 제어 로직** — `kernel_id` 비교 기반 유지/감쇠/무효화 (§design_document §4.1.4 (b)).
5. Region-aware MSHR 구현 (shared, masking 비교).
6. 15개 이상 workload로 Main 실험:
   - P1: IPC (Baseline / Baseline×2 / HMG / REC / Superdirectory / Ideal)
   - P2: NoC traffic breakdown (Read/Write/Inv/Data)
   - P3: Directory effective capacity
   - P4: L2 hit rate, utilization
   - P5: Scalability (2/4/8/16 GPU)
   - P6: Directory 용량별 성능 (L2의 1%, 2%, 3%, 5%, 10%)

#### 산출물
- `main_results/P1-P6.pdf` + raw data
- 최초 성능 비교 표

#### 검증 기준
- 평균 speedup이 REC 대비 **양의 값(0% 이상)**; REC 대비 양의 값이 아닌 경우에도 **어떤 workload에서 그러한지와 원인을 기록**.
- Iso-storage 비교(Baseline×2)에서 제안 기법 우세를 보이거나, 열위라면 **그 이유를 명시**.
- 최소 1개 workload에서 8/16 GPU 확장 시 REC 대비 우위 확인.

#### PHASE 2 윤리 조항
- 실패 금지: Superdirectory가 REC 대비 열위인 결과가 나온 워크로드를 drop하지 않는다. 논문 Limitations 섹션에 포함하고 원인을 분석.
- 미달 금지: Iso-storage 비교를 생략한 채 "우리 기법이 좋다"고 주장하지 않는다. 이 비교를 반드시 P1에 포함.
- 추측 금지: "REC보다 클 것이므로 당연히 낫다"는 식의 서술 금지. 모든 비교는 실측.

---

### PHASE 3 — Ablation, 분석, 오버헤드 (2026-06-15 ~ 2026-07-05, 약 3주)

#### 목표
- Reviewer가 물을 모든 "왜 이 값인가" 질문에 실험으로 답할 수 있도록 ablation 및 분석 완료.
- 하드웨어 오버헤드를 CACTI로 정량화.

#### 작업 항목
1. **Ablation (필수, A1~A4, A6~A9):**
   - A1 Region size 개수(2/3/4/5단계)
   - A2 Ratio(4× vs 16×)
   - A3 BF on/off
   - A4 RSB on/off (sectored + kernel-id 구조 포함)
   - A6 MSHR 수정 on/off
   - A7 Promotion criterion (full match vs 3-of-4 vs ≥2)
   - A8 Demotion threshold (1/2, 5/8, 3/4, 7/8, 15/16)
   - A9 Static vs Dynamic (64B-only, 1KB-only, 16KB-only)
2. **Optional Ablation (A5, 실험 여력 허용 시에만):**
   - RSB 세부 파라미터 sensitivity: S/W/K, coalescing range, kernel hash bits, recent-N FIFO 깊이 중 1차원씩 단일 변수 sweep. Main evaluation은 기본값으로 고정되므로 A5 미수행도 논문 proceeding에 영향 없음.
3. **행동 분석 (B1~B4):**
   - B1 Region size distribution
   - B2 Promotion/Demotion 빈도 + oscillation
   - B3 Region lifetime
   - B4 BF hit/miss
4. **오버헤드 (O1~O3):**
   - O1 Lookup latency breakdown (1-probe/2-probe/…)
   - O2 하드웨어 overhead (bits + CACTI area/power) — REC 논문 §4.4처럼 CACTI 7.0 사용
   - O3 Energy (directory + NoC + HBM)
5. **Deep-dive Case Study (C1~C3):**
   - C1 최대 개선 워크로드 (예: PageRank) 분석
   - C2 저조/열위 워크로드 원인 분석
   - C3 Race condition 시나리오 시뮬레이션

#### 산출물
- Ablation/분석/오버헤드 raw data + 그래프
- "모든 open question 해소" 보고서 (A1~A4, A6~A9, O1~O3, C1~C3). A5는 optional로 수행 여부 기록.

#### 검증 기준
- A1~A4, A6~A9 전부 완료 (미완료 항목은 논문에서 Limitations로 명시). A5는 optional이므로 생략 가능.
- O1: 평균 bank probe 횟수가 **2.0 미만**이어야 serial lookup overhead 주장 성립. 초과 시 설계 문제로 간주하고 보완.
- O2: 총 storage가 REC의 12× baseline 대비 현저히 작아야 함 (구체 목표치는 PHASE 2 결과로 산정).

#### PHASE 3 윤리 조항
- 실패 금지: A8의 7/8 threshold가 최적이 아니면 최적값으로 교체하고 본문을 수정. 원래 값 유지 정당화 금지.
- 미달 금지: Ablation 항목 중 누락이 있으면 Limitations에 명시적으로 기술. 조용한 생략 금지.
- 추측 금지: "이 설계가 좋은 이유는 ~일 것이다"라는 정성적 주장은 반드시 B1~B4 데이터를 인용. 각 설계 선택의 근거로 ablation 실험 ID를 모두 참조.

---

### PHASE 4 — 논문 초고 작성 및 내부 리뷰 (2026-07-06 ~ 2026-07-26, 약 3주)

#### 목표
- 14p 본문 + unlimited references 완성.
- 최소 2회 내부 리뷰 + 반영.

#### 작업 항목
1. Section draft 작성 순서:
   - Abstract (마지막) → Introduction → Background → Motivation (PHASE 0 결과) → Design → Implementation → Evaluation → Related Work → Conclusion.
2. 그림·표 finalize (Figure 10개 내외, Table 3~4개).
3. Related work: SAC, HMG, REC, HBM-side 최신 작업, scope memory model 관련 HPCA/ISCA/MICRO 2022~2026 논문 서베이 (최소 40편).
4. Internal review round 1: 동료 2명 (reviewer persona 1: GPU 전문가, persona 2: coherence 전문가)에게 읽힌 후 피드백 반영.
5. Internal review round 2: 전체 flow + figure clarity 점검.

#### 산출물
- `paper_v1.pdf` (round 1), `paper_v2.pdf` (round 2)
- Reviewer persona별 feedback log

#### 검증 기준
- Round 2 피드백에서 critical issue(주장 약함, 비교 누락, 데이터 모순) 0건.
- HPCA 포맷 규정 준수 (본문 14p 이내 — HPCA 2026 규정 기준; 2027 CFP 확인 시 재점검).

#### PHASE 4 윤리 조항
- 실패 금지: Reviewer가 지적한 문제를 "공간 부족"을 이유로 미해결 상태로 두지 않는다. 공간이 부족하면 내용의 우선순위를 다시 정한다.
- 미달 금지: 수치/단위/그래프 라벨 불일치 0건. 본문과 그림이 모순되는 것은 rejection 사유.
- 추측 금지: 모든 claim에 (a) 섹션·그림 번호, 또는 (b) 인용 번호가 달려 있어야 함. 심사 중 "데이터 어디?"에 전부 답할 수 있도록.

---

### PHASE 5 — 최종 polish 및 제출 (2026-07-27 ~ 제출일, 약 1주)

#### 목표
- Camera-ready 수준 polish 후 HPCA 2027 submission site 제출.
- Double-blind 규정 준수(저자 정보 제거, self-citation 중립화).

#### 작업 항목
1. Abstract 최종 재작성 (numbers-first style).
2. Double-blind 최종 점검.
3. Artifact Evaluation 신청 여부 결정 (코드 + 스크립트 공개 준비 포함).
4. HotCRP 제출 전 체크리스트:
   - PDF express 검증(규정 상 요구, HPCA 2026 참고).
   - References 완전성(et al. 금지, 전체 저자).
   - Conflict list 정확성.
5. Abstract 사전 등록(제출 1주 전).
6. 제출.

#### 산출물
- 제출된 PDF + HotCRP submission ID

#### 검증 기준
- 마감 **24시간 이전** 제출 (서버 혼잡·형식 거부 대비).
- 모든 checklist 항목 통과.

#### PHASE 5 윤리 조항
- 실패 금지: 제출 서버 오류 등 불가항력 제외, 마감 24h 이전 제출 미달성 시 복기.
- 미달 금지: Double-blind 누락·포맷 위반 등 desk reject 사유는 0건이어야 함.
- 추측 금지: "이 정도면 괜찮겠지"라는 판단으로 checklist 항목을 skip하지 않는다.

---

## 6. 예상 Reviewer Critique 및 사전 대응

Paper rejection의 단골 사유를 선제적으로 시뮬레이션해둔다.

### 6.1 "What is your delta over REC?" (Novelty)

**대응:** §2.1의 Delta argument. 핵심: REC은 **spatial 압축**이지만 coherence 단위는 cacheline으로 고정. Superdirectory는 **coherence 단위 자체를 adaptive하게 확장**하되 sub-entry로 fine-grained correctness 유지. 표 2 (본문)에 명시.

### 6.2 "Serial lookup latency is 5×" (Performance concern)

**대응:** O1에서 평균 bank probe 수가 기대 1~2회임을 데이터로 증명. RSB hit rate + BF filtering 효과 정량화. Parallel probe 대안도 설계 대안으로 제시.

### 6.3 "Your storage overhead is high" (Cost concern)

**대응:** Iso-storage (Baseline×2 = 16K entries) 비교 포함. O2에서 CACTI 기반 area/power 제시. REC의 12× ideal directory(30.4% L2 면적)와 비교해 얼마나 작은지 명시.

### 6.4 "False sharing at 16KB granularity" (Correctness/Perf concern)

**대응:** Sub-entry 구조로 sub-region별 독립 sharer → write가 와도 해당 sub-region만 invalidate. A8 (demotion threshold)과 C1/C2에서 실측으로 검증.

### 6.5 "Workload set is narrow, missing LLM" (Evaluation concern)

**대응:** Attention kernel, large GEMM batch 등 AI inference workload 포함. 단, 시뮬레이션 시간 제약 시 "어떤 workload 몇 개 추가"를 PHASE 0 마지막에 확정.

### 6.6 "Scalability to 16 GPU" (Scalability concern)

**대응:** P5에서 2/4/8/16 GPU 실험. Sub-entry 당 N-1b 사용으로 REC의 entry 전체 N-1b 대비 sharer bit 비율이 작음을 설계상 입증. 단, 16-GPU MGPUSim 시뮬레이션은 시간이 매우 오래 걸릴 수 있으므로 PHASE 2에서 선제적 kick-off.

### 6.7 "Correctness of promotion/demotion under race"

**대응:** C3 race condition 시나리오 + Region-aware MSHR 설계 근거. 가능하면 간단한 formal property sketch(예: TLA+ high-level).

### 6.8 "Memory consistency model interaction"

**대응:** GPU의 scoped, non-multi-copy-atomic model을 baseline 그대로 준수. Superdirectory는 sharer tracking layer이며 consistency는 GPU-VI 레벨에서 유지. Release/Acquire flow는 기존과 동일 (Background에 명시).

---

## 7. Risk Register

| ID | 리스크 | 확률 | 영향 | 완화책 | 담당 PHASE |
|----|--------|------|------|--------|------------|
| R1 | MGPUSim에서 REC 재현이 어려움 | 중 | 높음 | 원저자 코드 요청 병행, 최소 기능부터 재구현 | PHASE 1 |
| R2 | 16-GPU 시뮬레이션 시간 초과 | 중 | 중 | 축소 트레이스 + sampling | PHASE 2 |
| R3 | Promotion/Demotion oscillation | 중 | 중 | Hysteresis 추가, A8로 threshold 조정 | PHASE 3 |
| R4 | CACTI 결과가 불리(면적 초과) | 저 | 높음 | BF/RSB 크기 조정, promotion FSM 간소화 | PHASE 3 |
| R5 | HPCA 2027 CFP가 페이지 수 감축 | 저 | 중 | 보조 결과를 appendix나 artifact로 분리 | PHASE 4 |
| R6 | Motivation M4의 redundancy 비율 < 30% | 중 | 치명적 | Motivation 재정비, 다른 angle(eviction 감소, scalability)로 pivot 고려 | PHASE 0 |
| R7 | Iso-storage에서 REC 대비 열위 | 중 | 높음 | 열위 원인 분석 후 design refinement, 공개적 Limitation 기술 | PHASE 2 |

> **중요:** R6, R7이 "실패 금지" 조항과 가장 직접 충돌할 수 있는 리스크이다. 결과가 negative라도 **숨기지 않고**, 원인을 분석하여 논문 positioning을 honest하게 조정한다. HPCA 심사는 negative result를 포함한 충실한 분석을 선호하는 편이다.

---

## 8. 일정 요약 (Gantt-style)

```
2026
Apr      |████| PHASE 0 (설계 + Motivation)
May 04   |      ████████████| PHASE 1 (Core 구현)
May 25   |                   ████████████| PHASE 2 (Aux + Main 실험)
Jun 15   |                                ████████████| PHASE 3 (Ablation + 분석)
Jul 06   |                                             ████████████| PHASE 4 (논문 작성)
Jul 27   |                                                          ████| PHASE 5 (Polish + 제출)
         └──────────────────────────────────────────────────────────────┘
         Apr 20                                         Jul 27  제출 D-day
```

> **버퍼:** 약 10% 일정 여유를 확보. PHASE 0 또는 PHASE 1이 1주 연장될 경우 PHASE 3의 optional ablation(A5) 및 하위 우선순위 항목(O3 energy 일부)을 appendix/future work로 연기.

---

## 9. 참고 문헌 (우선 정리 — 계속 보강)

선행 연구 및 배경 자료:

1. **REC** — G. Ko et al., "Enhancing fine-grained cache coherence protocol in multi-GPU systems," *Journal of Systems Architecture*, 2025. (본 연구의 직접 비교 대상)
2. **HMG** — X. Ren et al., "HMG: Extending Cache Coherence Protocols Across Modern Hierarchical Multi-GPU Systems," *HPCA 2020*, pp. 582–595.
3. **SAC** — "Sharing-Aware Caching in Multi-Chip GPUs," *MICRO 2020*. (LLC level sharing-aware caching; orthogonal)
4. **NUMA-aware GPUs** — U. Milic et al., "Beyond the socket: NUMA-aware GPUs," MICRO 2017.
5. **HW/SW NUMA** — V. Young et al., "Combining HW/SW mechanisms to improve NUMA performance of multi-GPU systems," MICRO 2018.
6. **MGPUSim** — Y. Sun et al., "MGPUSim: Enabling Multi-GPU Performance Modeling and Optimization," ISCA 2019.
7. **GPU-VI** — cited in HMG as baseline VI-like protocol.
8. **CACTI 7.0** — for hardware overhead estimation (REC §5 also used this).

> PHASE 4에서 최소 40편으로 확장. 최신(2024–2026) coherence/multi-GPU 관련 HPCA/MICRO/ISCA/ASPLOS 논문 서베이 필수.

---

## 10. 부록: 제출 전 최종 체크리스트

- [ ] Abstract ≤ 250 words 추정(HPCA 템플릿 기준)
- [ ] 본문 14 pages (figures/tables 포함), references 무제한
- [ ] Double-blind: 저자명·기관·grant 번호·개인 리포지토리 URL 제거
- [ ] 모든 figure가 본문에서 인용됨
- [ ] 모든 table이 본문에서 인용됨
- [ ] Numbers in abstract = numbers in evaluation section
- [ ] Reviewer persona 2명 round 2 피드백 반영 완료
- [ ] 공정 비교: REC·HMG·Baseline·Baseline×2·Ideal 모두 포함
- [ ] Iso-storage 비교 포함
- [ ] Scalability (최소 2/4/8 GPU) 포함
- [ ] Hardware overhead (CACTI) 포함
- [ ] Limitations 섹션 존재
- [ ] References 전체 저자 기재 (et al. 금지)
- [ ] HotCRP 사전 abstract 등록 (제출 1주 전)
- [ ] PDF express 검증(HPCA 2026 규정 기준)
- [ ] 마감 24시간 이전 업로드

---

**문서 버전:** v1.0 (2026-04-19 작성)
**다음 revise 예정:** PHASE 0 종료 시점에 M1~M5 결과로 Motivation 섹션 update; HPCA 2027 CFP 공지 직후 포맷 규정 재검증.
