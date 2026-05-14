# Adaptive Region-Size Directory 실험 계획 및 Motivation 분석

> Multi-GPU Cache Coherence를 위한 적응형 Region-Size Directory 설계에 대한 실험 계획과 Motivation 보강 방안을 정리한 문서입니다.

---

## 📑 목차

1. [논문 핵심 요약](#1-논문-핵심-요약)
2. [Motivation 실험 계획](#2-motivation-실험-계획)
3. [Main 실험 계획](#3-main-실험-계획)
4. [Ablation Study](#4-ablation-study)
5. [성능 변화 원인 분석 실험](#5-성능-변화-원인-분석-실험)
6. [Motivation 충분성 판단 및 보강 제안](#6-motivation-충분성-판단-및-보강-제안)
7. [실험 우선순위 및 타임라인](#7-실험-우선순위-및-타임라인)

---

## 1. 논문 핵심 요약

### 🎯 핵심 아이디어
- **Adaptive Region-Size Directory**: 고정 크기(64B/128B cacheline)가 아닌 **가변 크기(64B~16KB)** region 단위로 coherence 관리
- Region size list: `[16KB, 4KB, 1KB, 256B, 64B]` (5개 bank)
- **Promotion/Demotion** 메커니즘으로 런타임에 접근 패턴에 적응

### 🔑 해결하고자 하는 문제
| 문제 | 기존 솔루션 | 한계 |
|------|-------------|------|
| Directory 용량 부족 | REC (16개 entry 병합) | Coherence unit은 여전히 cache line |
| 네트워크 오버헤드 | HMG (4 cacheline 정적 그룹) | False sharing, cache pollution |
| Workload별 다른 최적 단위 | — | 고정 단위로는 대응 불가 |

---

## 2. Motivation 실험 계획

### 2.1 ✅ 논문에 이미 계획된 실험

#### (Figure a) Coherence Unit Size별 성능 변화
- **목적**: 관리 단위가 커질 때 성능이 향상/감소하는 양극단 존재 증명
- **측정**: Normalized IPC (또는 speedup)
- **X축**: Coherence unit size (64B, 128B, 256B, 1KB, 4KB, 16KB)
- **워크로드**: PageRank (큰 차이), 기타 graph/ML/HPC workloads
- **예상 결과**: PageRank처럼 spatial locality 높은 경우 성능↑, 반대는 성능↓

#### (Figure b) Cacheline Utilization
- **목적**: 성능 차이의 원인이 fetch된 데이터의 활용도임을 증명
- **측정**: Fetch된 바이트 중 실제 사용된 바이트 비율
- **분석**: Utilization 낮음 → cache pollution, false sharing 발생 근거

#### (Figure c) 인접 Cacheline의 Sharer Set 동일성
- **목적**: Spatial correlation of sharing patterns 증명
- **측정**: 인접한 N개 cacheline이 동일 sharer set을 가지는 비율
- **X축**: 인접 cacheline 개수 (2, 4, 8, 16, ...)

#### (Figure d) Directory 내 Redundant Entry 비율
- **목적**: 메타데이터 중복으로 인한 디렉토리 용량 낭비 증명
- **측정**: 완전히 동일한 state/sharer 정보를 가진 entry 비율

#### (Baseline vs Infinite Directory) 실험
- **목적**: Directory 용량이 실제 병목임을 증명
- **측정**: Application 성능, L2 cache utilization, L2 hit rate
- **추가 측정**: L2 cache 중 공유 data 비율

### 2.2 🔧 보충이 필요한 Motivation 실험

#### [보충 실험 M1] **Optimal Region Size의 동적 변화**
- **필요성**: "동적 조절이 필요하다"는 주장의 근거 부족
- **측정 방식**:
  - 워크로드 실행 중 시간(kernel/phase) 단위로 optimal region size 추적
  - Memory 영역(address range)별 optimal region size 분포
- **기대 결과**: 동일 워크로드 내에서도 phase/영역에 따라 optimal size가 달라짐을 보임
- **그래프**: Timeline plot (시간 축) + Heatmap (address × time → optimal size)

#### [보충 실험 M2] **False Sharing 빈도 정량화**
- **필요성**: HMG의 false sharing 문제를 정성적으로만 언급 중
- **측정 방식**:
  - HMG(4-line 고정 unit) 환경에서 동일 region 내 서로 다른 GPU의 unique access 발생 횟수
  - 불필요한 invalidation 횟수 / 전체 invalidation 횟수
- **기대 결과**: HMG에서 false sharing으로 인한 invalidation이 baseline 대비 X배 증가

#### [보충 실험 M3] **Directory Eviction으로 인한 Forced Miss 비율**
- **필요성**: Directory capacity 병목의 직접적 증거
- **측정 방식**:
  - 전체 cache miss 중 "directory eviction으로 인한 invalidation으로 유발된 miss" 비율
  - Directory eviction rate vs. cache miss rate 상관관계
- **기대 결과**: Directory 용량 한계가 cache miss를 증폭시킴을 증명

#### [보충 실험 M4] **Spatial Correlation의 정량적 분석**
- **필요성**: Figure c를 더 구체화 (어느 크기까지 correlation 유지되는지)
- **측정 방식**:
  - 64B부터 16KB까지 region size별 "full sharer overlap" 비율
  - 워크로드별 비교
- **기대 결과**: Region size list `[64B, 256B, 1KB, 4KB, 16KB]` 선택의 근거

#### [보충 실험 M5] **Invalidation Traffic Breakdown**
- **필요성**: 네트워크 오버헤드의 주요 원인 파악
- **측정 방식**:
  - Invalidation 발생 원인별 분류: (1) local write, (2) directory eviction, (3) acquire/release
  - 각 원인이 전체 network traffic에서 차지하는 비율

---

## 3. Main 실험 계획

### 3.1 성능 비교 실험

#### [실험 P1] **종합 성능 평가**
| 비교 대상 | 설명 |
|-----------|------|
| Baseline | 일반 VI directory (cacheline 단위) |
| REC | Entry 병합 기법 |
| HMG | 4-cacheline 정적 그룹 |
| **Proposed** | Adaptive region-size directory |
| Ideal | Infinite directory |

- **측정 지표**: Normalized IPC, Speedup, Execution time
- **워크로드**: 최소 15개 이상 (graph, ML, HPC, scientific simulation)
- **GPU 구성**: 4-GPU, 8-GPU

#### [실험 P2] **네트워크 트래픽 감소 효과**
- **측정**: 
  - Total inter-GPU messages
  - Breakdown: read requests, write requests, invalidations, data responses
- **목적**: Region 단위 관리로 인한 message reduction 증명

#### [실험 P3] **Directory Effective Capacity**
- **측정**:
  - Directory가 커버하는 L2 cache의 비율 (%)
  - Directory eviction rate
- **기대 결과**: 동일 하드웨어 용량으로 더 넓은 범위 커버

#### [실험 P4] **Cache 성능 지표**
- **측정**: L2 hit rate, L2 utilization
- **목적**: False sharing/pollution 감소 증명

### 3.2 확장성 실험

#### [실험 P5] **GPU 개수에 따른 확장성**
- **구성**: 2, 4, 8, 16 GPU
- **목적**: Sharer 수 증가에도 제안 기법이 유효함을 증명

#### [실험 P6] **다양한 Directory 용량에서의 성능**
- **X축**: Directory size (L2의 1%, 2%, 3%, 5%, 10%)
- **목적**: 제한된 용량일수록 제안 기법의 효과가 큼을 증명

---

## 4. Ablation Study

구성 요소별 기여도를 분리해서 측정. 각각 **해당 요소만 제거** 혹은 **해당 요소만 추가**한 configuration을 비교.

### 4.1 🧩 구조적 요소 Ablation

#### [A1] **Region Size 개수의 영향**
| Config | Region Sizes |
|--------|--------------|
| A1-2 | [64B, 16KB] (2단계) |
| A1-3 | [64B, 1KB, 16KB] |
| A1-4 | [64B, 256B, 4KB, 16KB] |
| A1-5 (**proposed**) | [64B, 256B, 1KB, 4KB, 16KB] |

- **목적**: 5개 bank 구성의 타당성 검증

#### [A2] **Region Size 비율 (4배 vs 16배)**
| Config | Region Sizes |
|--------|--------------|
| 4x ratio | 64B, 256B, 1KB, 4KB, 16KB |
| 16x ratio | 64B, 1KB, 16KB, 256KB, 4MB |

- **목적**: 논문에서 열린 질문인 "4배씩 vs 16배씩" 해결

#### [A3] **Bloom Filter 유무**
- **목적**: Serial lookup latency 증가와 Bloom filter의 filter 효과 trade-off 분석
- **측정**: Lookup latency, unnecessary bank access 감소율

#### [A4] **Region Size Buffer 유무**
- **목적**: Eviction 후 재할당 시 region size hint의 효과 검증
- **측정**: Misallocation 횟수, promotion 빈도

#### [A5] **Region Size Buffer 크기**
- **비교**: 0, 16, 64, 256, 1024 entries
- **목적**: Optimal buffer size 결정

#### [A6] **MSHR 수정 유무**
- **Region-aware MSHR** vs **기존 MSHR**
- **목적**: Masking 기반 주소 비교의 효과 검증

### 4.2 🔄 정책적 요소 Ablation

#### [A7] **Promotion 기준 변경**
- **Sharer 일치 기준**: 4개 중 4개 동일 / 3개 이상 동일 / 임의 일치 수
- **목적**: Promotion의 aggressiveness 최적화

#### [A8] **Demotion Threshold (7/8) 변경**
- **비교**: 1/2, 5/8, 3/4, **7/8**, 15/16
- **목적**: Utilization-based demotion threshold 최적화

#### [A9] **Static vs Dynamic 비교**
- **Static-Small** (64B only), **Static-Large** (16KB only), **Static-Mid** (1KB only)
- **목적**: 동적 조절이 각 정적 설정보다 우월함을 증명

---

## 5. 성능 변화 원인 분석 실험

### 5.1 🔍 행동 분석 (Behavior Analysis)

#### [B1] **Region Size Distribution**
- **측정**: 워크로드별 각 bank에 할당된 entry 비율 (시간 평균)
- **결과 해석**: 어떤 워크로드가 주로 어떤 region size를 선호하는지
- **그래프**: Stacked bar chart (워크로드 × region size)

#### [B2] **Promotion/Demotion 빈도**
- **측정**:
  - Promotion 횟수, Demotion 횟수
  - Promotion → Demotion의 반복 횟수 (oscillation)
- **목적**: 정책이 stable한지, thrashing이 없는지 확인

#### [B3] **Region Lifetime 분석**
- **측정**:
  - 각 region size별 entry의 평균 lifetime
  - Promotion 전까지의 시간, Demotion까지의 시간
- **목적**: 각 region size의 효용성 검증

#### [B4] **Bloom Filter Hit/Miss 분석**
- **측정**: 각 bank별 BF positive rate, false positive rate
- **목적**: Serial lookup 회피 효과 정량화

### 5.2 📊 오버헤드 분석 (Overhead Analysis)

#### [O1] **Lookup Latency Breakdown**
- **측정**:
  - 평균 directory lookup latency
  - Bank 순회 수 분포 (1회 hit / 2회 / 3회 / ...)
- **목적**: Serial lookup의 실제 latency 영향 분석

#### [O2] **Hardware 오버헤드 분석**
- **측정**:
  - Total directory storage (bits)
  - Bloom filter storage
  - Region size buffer storage
  - MSHR 추가 필드 storage
- **기준**: Baseline, REC, HMG 대비 overhead 비교
- **표**: 각 구성 요소별 bits 정리

#### [O3] **Energy 분석** *(optional but strong)*
- **측정**: Directory 접근 energy, NoC energy, HBM energy
- **목적**: 성능뿐 아니라 에너지 효율 주장

### 5.3 🔬 Deep-Dive Case Study

#### [C1] **성능 향상 최대 워크로드 분석**
- 예: PageRank에서 왜 크게 좋아지는지
- **분석**: Access pattern timeline, region transition 그래프

#### [C2] **성능 저하/미미한 워크로드 분석**
- 오히려 성능이 악화되거나 개선이 미미한 경우의 원인 분석
- **분석**: 어떤 종류의 접근 패턴이 기법의 약점인지 파악

#### [C3] **Race Condition 시나리오**
- **Case 1**: Promotion 중 동일 entry에 request 도착
- **Case 2**: Demotion 중 동일 entry에 request 도착
- **Case 3**: Remote read + remote write 동시 발생
- **측정**: MSHR 기반 처리의 정확성, 발생 빈도
- **목적**: 논문에서 열린 질문(MSHR으로 해결?)에 대한 정량적 검증

---

## 6. Motivation 충분성 판단 및 보강 제안

### 6.1 Motivation 섹션별 평가

#### ✅ `6.2.1 Optimum Coherence Unit Size` — **대체로 충분**
- Figure a, b로 논리 전개 명확함
- **보강 필요**:
  - Figure에 **region size별 optimal 점이 달라짐을 하나의 그래프로 시각화**
  - **phase-level 변화** (동일 워크로드 내에서 optimal이 변함)을 추가 그래프로 증명 ← **보충 실험 M1**

#### ⚠️ `6.2.2 Metadata Redundancy due to Spatial Correlation` — **정량적 증거 부족**
- Figure c, d는 좋은 시작이지만 **수치가 논문 본문에 명확히 언급되어야 함**
- **보강 필요**:
  - 전체 directory entry 중 redundant entry 비율을 구체적 % 수치로 제시 (예: "평균 57%가 중복")
  - Region size별 correlation 변화를 그래프로 명시 ← **보충 실험 M4**
  - REC가 이를 공간적으로 압축하지만 coherence 단위가 여전히 cacheline인 것을 여기서 한 번 더 강조

#### ⚠️ `6.2.3 Limitation of Directory Capacity` — **실험 결과 누락**
- "실험을 통해 확인할 수 있음"으로 끝나는데 실제 결과 수치/그래프 자리만 있고 분석이 없음
- **보강 필요**:
  - Baseline vs Inf. directory의 구체적 성능 차이 %
  - Directory eviction으로 인한 forced invalidation이 cache miss에서 차지하는 비율 ← **보충 실험 M3**
  - L2 cache utilization이 얼마나 낮아지는지 정량화

#### ✅ `6.2.4 Limitations of Prior GPU Coherence Works` — **충분**
- REC, HMG의 한계가 앞서 제시한 observation과 잘 연결됨
- **보강 필요**:
  - HMG의 false sharing을 정량적으로 보이는 데이터 추가 ← **보충 실험 M2**

#### ❌ `6.2.5 Design Goal` — **대폭 보강 필요**
- 현재 "contributions 3개"만 placeholder로 있음
- **필요 내용**:
  - 3가지 design goal을 명확히 서술 (예: Dynamic Adaptation, Storage Efficiency, Low Latency)
  - 각 goal이 앞서 제시한 observation과 1:1 매칭되도록 연결
  - Contribution 항목을 구체화 (예: "가변 region size directory 구조 제안", "경량 promotion/demotion 정책", "하드웨어 오버헤드 X% 미만")

### 6.2 🧭 Motivation 전체 논리 흐름 점검

현재 흐름:
```
Optimum Unit이 있음 (O1)
  → 인접 cacheline은 공유 패턴이 유사 (O2)
    → 하지만 directory 용량 한정 (O3)
      → 기존 기법들은 trade-off에 갇힘 (O4)
        → 따라서 adaptive 솔루션 필요
```

**강화 포인트**:
- O1 → O2 연결에서 "왜 spatial correlation이 optimal unit 문제와 연결되는지" 한 문장 추가 필요
- O2 → O3에서 "redundancy가 directory 용량 문제를 악화시킨다"는 문장은 있으나 **수치적 증거 필요**
- 최종 "adaptive 솔루션 필요"가 **design goal과 직접 연결**되어야 함

### 6.3 🆕 추가 고려 가능한 Motivation 주제

#### [추가 1] Coherence 관리 단위 > cache block 시 문제 분석
- 논문 design.txt에서도 언급됨 ("negligible한 문제임 설명")
- **필요 내용**:
  - Coherence 단위 > cache line인 경우의 잠재적 문제 (partial write, partial invalidation)
  - 이를 어떻게 해결했는지 (sub-entry 구조) 미리 언급
  - **위치**: Sub-subsection 형태로 간단히 한 문단 정도 (design 직전에 배치 권장)

#### [추가 2] Workload Diversity 강조
- 현대 GPU 워크로드가 얼마나 다양한 접근 패턴을 가지는지
- ML training vs inference, graph algorithm, physics simulation 등 서로 다른 패턴

---

## 7. 실험 우선순위 및 타임라인

### 🥇 Priority 1 (필수, 가장 먼저)

1. **Motivation 실험 완성** (Figure a, b, c, d) — 논문의 근간
2. **보충 실험 M1, M3** — Motivation의 dynamic 필요성 논리 보강
3. **Main 실험 P1 (종합 성능)** — 주요 contribution 증명
4. **Ablation A9 (Static vs Dynamic)** — 핵심 아이디어 검증

### 🥈 Priority 2 (강력한 뒷받침)

5. **Main 실험 P2, P3, P4** — 네트워크/디렉토리/캐시 지표
6. **Ablation A1, A2** — Region size 구성 선택 근거
7. **분석 실험 B1, B2** — 행동 분석으로 결과 해석력 강화
8. **Overhead 실험 O1, O2** — 현실성 증명

### 🥉 Priority 3 (있으면 좋음)

9. **Main 실험 P5, P6** — 확장성
10. **Ablation A3~A8** — 세부 정책/구조 튜닝
11. **Case Study C1~C3** — Reviewer를 설득하는 깊이
12. **Overhead O3 (Energy)** — 에너지 분석

### 🗓️ 권장 타임라인 (예시)

| 주차 | 작업 |
|------|------|
| 1~2주 | Simulator setup, baseline/REC/HMG 구현, 워크로드 선정 |
| 3~4주 | Motivation 실험 완료 (Fig a~d + 보충 M1~M5) |
| 5~6주 | Proposed 기법 구현 |
| 7~8주 | Main 실험 (P1~P4) |
| 9주 | 확장성 실험 (P5, P6) |
| 10~11주 | Ablation study (A1~A9) |
| 12주 | 분석 실험 + Case study |
| 13주 | Overhead 분석 + Energy |
| 14주 | 논문 작성 및 그래프 정리 |

---

## 📌 체크리스트 요약

### Motivation 실험
- [ ] Figure a: Coherence unit size별 성능
- [ ] Figure b: Cacheline utilization
- [ ] Figure c: 인접 cacheline sharer 일치율
- [ ] Figure d: Redundant entry 비율
- [ ] Baseline vs Inf. directory 성능/utilization/hit rate
- [ ] **[보충] M1**: Optimal region size 동적 변화
- [ ] **[보충] M2**: False sharing 빈도 정량화
- [ ] **[보충] M3**: Directory eviction → forced miss 비율
- [ ] **[보충] M4**: Spatial correlation 정량 분석
- [ ] **[보충] M5**: Invalidation traffic breakdown

### Main 실험
- [ ] P1: 종합 성능 (vs Baseline/REC/HMG/Ideal)
- [ ] P2: 네트워크 트래픽 breakdown
- [ ] P3: Directory effective capacity
- [ ] P4: L2 hit rate, utilization
- [ ] P5: GPU 확장성 (2/4/8/16)
- [ ] P6: Directory 용량에 따른 성능

### Ablation
- [ ] A1: Region size 개수
- [ ] A2: Region size 비율 (4x vs 16x)
- [ ] A3: Bloom filter 유무
- [ ] A4: Region size buffer 유무
- [ ] A5: Region size buffer 크기
- [ ] A6: MSHR 수정 유무
- [ ] A7: Promotion 기준
- [ ] A8: Demotion threshold
- [ ] A9: Static vs Dynamic

### 분석 실험
- [ ] B1: Region size distribution
- [ ] B2: Promotion/demotion 빈도
- [ ] B3: Region lifetime
- [ ] B4: Bloom filter hit/miss
- [ ] O1: Lookup latency breakdown
- [ ] O2: Hardware overhead
- [ ] O3: Energy analysis
- [ ] C1: 최대 개선 워크로드 분석
- [ ] C2: 저조 워크로드 분석
- [ ] C3: Race condition 시나리오

### Motivation 보강
- [ ] 6.2.2에 redundancy 수치 추가
- [ ] 6.2.3에 실제 실험 결과 추가
- [ ] 6.2.5 Design Goal 작성
- [ ] Observation → Design Goal 1:1 매칭
- [ ] Coherence unit > cacheline 문제 언급 추가
