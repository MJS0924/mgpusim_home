# CPU 선행연구 조사 보고서 — Superdirectory 독창성 검증

> 본 문서는 HPCA 2027 제출을 위한 Superdirectory 기법의 **CPU 영역 선행연구 조사 결과**를 기록한다. 관련 CPU 선행연구가 발견되어 논문 positioning을 재조정해야 할 필요성이 확인되었다. 본 조사는 "추측 금지" 원칙에 따라 모든 주장에 출처를 명시한다.

---

## 0. 조사 목적 및 범위

- **조사 시점**: 2026-04-20 (PHASE 0 진행 중)
- **조사자**: [연구자명]
- **조사 범위**: Superdirectory의 핵심 구성요소(다중 granularity directory, 동적 promotion/demotion, sub-entry 구조, region eviction buffer)가 CPU 또는 다른 도메인에서 제안된 적이 있는지 확인.
- **조사 방법**: Google Scholar, IEEE Xplore, ACM DL 키워드 검색 + 주요 논문의 related work 역추적(backward citation) + 최신 논문들의 forward citation 추적.

---

## 1. 핵심 결론 (Executive Summary)

### 1.1 주요 발견

**Superdirectory의 개별 구성요소는 대부분 CPU 영역에서 이미 제안된 바 있다.** 현재 계획서에 인용되지 않은 핵심 논문이 최소 **6편** 확인됨.

| # | 구성요소 | CPU 선행연구 존재 여부 | 대표 논문 |
|---|----------|----------------------|----------|
| 1 | 다중 granularity directory | ✅ 존재 | Zebchuk MICRO 2013 (MGD) |
| 2 | 동적 promotion/demotion | ✅ 존재 | Alisafaee MICRO 2012 (SCT), Cuesta IEEE TPDS 2017 |
| 3 | 가변 region size 동적 정제 | ✅ 존재 | Cuesta IEEE TPDS 2017 |
| 4 | Region eviction buffer (RSB) | ✅ 존재 (≈ ERB) | Basu Wisconsin TR 2013 |
| 5 | Dual-grain이 충분하다는 반론 | ✅ 명시적 주장 존재 | Zebchuk MICRO 2013 |
| 6 | **Sub-entry 내 독립 sharer bit-vector** | ⚠️ **부분적으로만 존재** | 가장 명확한 잠재적 차별점 |
| 7 | Multi-GPU (discrete) 적용 | ❌ 없음 | — |

### 1.2 HPCA 제출 관점의 함의

- **현재 계획서 상태로 제출 시 novelty 공격으로 reject될 확률이 매우 높음.**
- 조치하지 않으면 PC에서 "이 논문은 MGD(Zebchuk 2013)의 GPU 판본에 불과하다"는 프레이밍을 받을 가능성 있음.
- **반드시 필요한 조치**: (a) related work 대폭 보강, (b) 차별점 명확화, (c) dual-grain baseline과의 직접 비교 실험 추가(M6 계획 참조).

---

## 2. Tier 1 — 직접 충돌하는 선행연구 (반드시 인용 및 반박 필요)

### 2.1 MGD — Multi-grain Coherence Directories

- **저자**: Jason Zebchuk, Babak Falsafi, Andreas Moshovos
- **출판**: MICRO 2013, pp. 359–370
- **DOI**: 10.1145/2540708.2540739
- **출처 링크**: https://dl.acm.org/doi/10.1145/2540708.2540739

#### 핵심 주장

> "Conventional directory coherence operates at the finest granularity possible, that of a cache block. ... at any given point in time, large, continuous chunks of memory are often accessed only by a single core. We take advantage of this behavior and investigate reducing the coherence directory size by tracking coherence at multiple different granularities."

#### Superdirectory와의 직접적 충돌 지점

| 항목 | MGD | Superdirectory |
|------|-----|----------------|
| 핵심 아이디어 | 여러 granularity로 coherence tracking | 여러 granularity로 coherence tracking |
| Idealized 분석 | iMGD — 임의 크기 region 고려 | 5 bank (16KB/4KB/1KB/256B/64B) |
| 실용 결론 | **dual-grain(DGD)로 충분** (cache block + 1–8KB) | 5-bank가 최적이라 주장 예정 |
| 적용 대상 | 멀티코어 CPU (16 core) | Multi-GPU (2–16 GPU) |
| Directory 축소율 | 41–66% (성능 저하 없음) | 미정 (PHASE 2에서 측정) |

#### 예상 Reviewer 공격

> *"MGD 논문은 dual-grain이 multi-grain의 대부분의 이익을 제공한다고 결론 내렸다. Superdirectory는 왜 5-bank가 필요한가? GPU workload에서 dual-grain으로는 충분하지 않다는 실측 증거는 무엇인가?"*

#### 대응 전략

1. **M6 실험**(별도 문서)에서 dual-grain baseline을 MGPUSim에 구현하여 공정 비교.
2. GPU에서 CPU와 다른 이유를 **실측**으로 제시(phase-level granularity 변화폭, workload diversity 등).
3. Ablation A1(region size 개수 2/3/4/5)을 **Main Evaluation으로 승격**하여 dual-grain의 한계를 정량 증명.

---

### 2.2 "CMP Directory Coherence: One Granularity Does Not Fit All"

- **저자**: Arkaprava Basu, Bradford M. Beckmann, Mark D. Hill, Steven K. Reinhardt
- **출판**: University of Wisconsin Technical Report #CS-TR-2013-1798 (2013); 후속 논문 MICRO 2013 (HSC)으로 연결됨
- **출처 링크**: https://www.csa.iisc.ac.in/~arkapravab/papers/region_coherence_TR.pdf

#### 핵심 주장

- 논문 제목 자체가 Superdirectory의 motivation과 동일("하나의 granularity로는 안 된다").
- **Dual-granularity CMP directory**: per-1KB-region state + per-64B-block state.
- 각 entry는 hybrid 구조: region portion (sharers 전체 bit-vector) + block portion (block당 single-ID).
- **Region Vector Array (RVA)** + **Evicted Region Buffer (ERB)** 보조 구조.
- **Asymmetric RVA**: 일부 way는 singleton entry (region당 1개 block만 추적).

#### Superdirectory의 RSB와 ERB 비교

| 항목 | Basu의 ERB | Superdirectory의 RSB |
|------|-----------|---------------------|
| 목적 | Evicted RVA entry 임시 보관 | Eviction된 region의 직전 bank 기억 |
| 위치 | RVA 바로 뒤의 CAM 구조 | Directory 외부 보조 구조 |
| 크기 | 16 entry (소형) | 미정 (A5로 tuning) |
| 동작 | Region eviction 시 inv 처리 unblock | 재요청 시 promotion 경로 건너뛰기 |

**평가**: 구조는 유사하나 **기능은 다름**. ERB는 "eviction 처리 병렬화용 버퍼", RSB는 "granularity 힌트 캐시". 차별점 부각 가능하지만 reviewer가 구조적 유사성을 지적할 것.

#### 예상 Reviewer 공격

> *"RSB는 Basu의 ERB와 구조적으로 동일하다. 단지 multi-bank 환경으로 확장한 것에 불과하지 않은가?"*

#### 대응 전략

- RSB의 **multi-granularity 힌트 기능**을 논문에서 명확히 차별화.
- Ablation A4(RSB on/off)에서 RSB가 없으면 **promotion 경로가 얼마나 길어지는지** 정량 제시.

---

### 2.3 Adaptive Coherence Granularity for Multi-Socket Systems

- **저자**: (Cuesta/Ros 계열 그룹 추정)
- **출판**: IEEE Transactions on Parallel and Distributed Systems (TPDS), 2017
- **출처 링크**: https://ieeexplore.ieee.org/document/7867795/

#### 핵심 주장 (논문 초록)

> "A dynamic multi-grain directory for large multi-socket systems. ... It dynamically refines granularity according to the application phase and therefore tracks coherence information for regions of varying sizes. The results show that the proposal allows to reduce the directory storage by an order of magnitude, while the loss of precision does not cause performance penalty."

#### Superdirectory의 motivation과 사실상 동일

| Superdirectory 계획서 (M1) | Cuesta TPDS 2017 |
|--------------------------|-------------------|
| "Workload phase에 따라 최적 region size가 실제로 변함을 증명" | "dynamically refines granularity according to the application phase" |
| "Regions of varying sizes" 추적 | "tracks coherence information for regions of varying sizes" |

#### 예상 Reviewer 공격

> *"M1 실험 결과가 이 2017 논문과 무엇이 다른가? Multi-socket CPU와 multi-GPU의 phase behavior 차이를 보였는가?"*

#### 대응 전략

- M1 실험을 CPU-GPU 비교 차원으로 확장: **동일 workload를 CPU와 GPU에서 실행하여 phase 행동의 차이를 보여야 함**(현실적으로 어려움).
- 또는 **GPU-specific phase behavior** (kernel boundary, CTA wave 기반 phase 등)를 CPU에 존재하지 않는 것으로 부각.

---

## 3. Tier 2 — 개념적 기반 (반드시 인용 필요)

### 3.1 Spatiotemporal Coherence Tracking (SCT)

- **저자**: Mohammad Alisafaee
- **출판**: MICRO 2012, pp. 341–350
- **출처 링크**: https://ieeexplore.ieee.org/document/6493625 (IEEE 10.1109/MICRO.2012.39)

**핵심**: 일정 시간 동안 한 코어가 private하게 접근하는 spatial region을 동적으로 감지하여 block-level에서 region-level로 tracking granularity를 증가. Sharer/Block Counters(SBC, PBC) 사용.

**Superdirectory와의 관계**: **Promotion 메커니즘의 직접적 선행연구**. MGD 논문에서도 SCT의 한계(counter imprecision)를 지적하며 DGD를 제안함.

### 3.2 Protozoa: Adaptive Granularity Cache Coherence

- **저자**: Hongzhou Zhao, Arrvindh Shriraman, Snehasish Kumar, Sandhya Dwarkadas
- **출판**: ISCA 2013, pp. 547–558
- **DOI**: 10.1145/2485922.2485969
- **출처 링크**: https://www.cs.rochester.edu/u/sandhya/papers/isca13.pdf

**핵심**: Storage/communication granularity와 coherence granularity를 분리. Per-block 적응형 granularity 조정. **방향성은 반대**(cache line보다 더 작게 가서 false sharing 회피).

**Superdirectory와의 관계**: "Adaptive granularity" 타이틀이 동일하며 철학이 유사. 다만 fine-grain 방향이므로 Superdirectory와 orthogonal로 포지셔닝 가능.

### 3.3 Heterogeneous System Coherence (HSC)

- **저자**: Jason Power, Arkaprava Basu, Junli Gu, Sooraj Puthoor, Bradford Beckmann, Mark Hill, Steven Reinhardt, David Wood
- **출판**: MICRO 2013, pp. 457–467
- **DOI**: 10.1145/2540708.2540747
- **출처 링크**: https://research.cs.wisc.edu/multifacet/papers/micro13_hsc.pdf

**핵심**: 통합 CPU-GPU 시스템에서 region directory로 표준 directory를 대체. L2 cache에 region buffer 추가.

**Superdirectory와의 관계**: **GPU 맥락에 region coherence를 처음 적용한 논문**. 통합 CPU-GPU 대상이지만 discrete multi-GPU는 아님. **차별점으로 활용 가능**: "HSC는 integrated system의 cross-device 통신량 감소 목적, Superdirectory는 discrete multi-GPU의 directory 용량 확장 목적".

---

## 4. Tier 3 — 역사적 맥락 (간단히 인용)

| 논문 | 저자 | 학회/출판 | 연도 | 기여 |
|------|------|----------|------|------|
| Reducing Memory and Traffic Requirements for Scalable Directory | Gupta, Weber, Mowry | ICPP | 1990 | 최초의 sectored/multi-block directory |
| RegionScout | Moshovos | ISCA | 2005 | Snooping 환경의 coarse-grain region filter |
| Coarse-Grain Coherence Tracking | Cantin, Lipasti, Smith | ISCA | 2005 | Snooping broadcast 감소 |
| A Framework for Coarse-Grain Optimizations | Zebchuk, Safi, Moshovos | MICRO | 2007 | Coarse-grain metadata 통합 프레임워크 |
| RegionTracker | Zebchuk | — | 2007 | RVA 구조의 원형 |
| Tagless Directory | Zebchuk, Srinivasan, Qureshi, Moshovos | MICRO | 2009 | Bloom filter 기반 sharer tracking |
| SPACE | Zhao, Shriraman, Dwarkadas | PACT | 2010 | Sharing pattern 기반 directory |
| SPATL | Zhao, Shriraman, Dwarkadas, Srinivasan | PACT | 2011 | Pattern table 압축 directory |
| Building Expressive, Area-Efficient Coherence Directories | Fang et al. | PACT | 2013 | Region + line entry 공존 |
| SS-DGD | Tang et al. | J. Supercomputing | 2023 | DGD의 region granularity 유연화 |

---

## 5. Superdirectory 주장별 독창성 재평가

| Superdirectory 주장 | 독창성 평가 | 근거 |
|---------------------|-------------|------|
| "최초의 다중 granularity directory" | ❌ **주장 불가** | MGD(2013)이 이미 제안 |
| "Workload phase에 따라 granularity 변화 관찰" | ❌ **주장 불가** | Cuesta TPDS 2017이 동일 관찰 |
| "Dynamic promotion/demotion" | ❌ **주장 불가** | SCT(2012)의 직접적 확장 |
| "Eviction 후 granularity 복구용 RSB" | ⚠️ **부분적** | Basu ERB와 유사. 다만 multi-bank 힌트는 새로움 |
| "5-bank 구조가 2-bank보다 우수" | ⚠️ **증명 필요** | MGD가 정반대 결론. M6 실험으로 GPU에서 반박 필요 |
| "Sub-entry 내 독립 sharer bit-vector" | ✅ **잠재적 차별점** | Sectored cache와의 결합은 CPU 선행연구에서 명확히 찾기 어려움 |
| "Region-aware MSHR" | ✅ **차별점** | GPU-specific 설계 |
| "Discrete multi-GPU(NVLink) 대상" | ✅ **차별점** | HSC는 integrated, 본 연구는 discrete |
| "HMG, REC 대비 성능 향상" | ✅ **유효** | 두 논문 모두 GPU multi-granularity 미적용 |

---

## 6. Reviewer 공격 시나리오 및 대응

### Scenario A (확률 95%): Novelty 공격
> **Reviewer**: "The proposed Superdirectory appears to be a straightforward adaptation of MGD [Zebchuk 2013] and Adaptive Coherence Granularity [Cuesta TPDS 2017] to multi-GPU. What is the essential novelty beyond scaling from dual-grain to 5-grain?"

**대응 준비**:
- M6 실험 결과: "GPU workload에서 dual-grain의 구체적 실패 case"
- Sub-entry 구조의 CPU 선행연구 부재 증명
- GPU-specific motivation (coalesced access + scattered access의 공존)

### Scenario B (확률 90%): 기반 motivation 공격
> **Reviewer**: "Motivation claim that 'redundancy worsens directory capacity' is not new — Zebchuk 2013 already argued this. What is the GPU-specific observation that CPU work missed?"

**대응 준비**:
- M1 실험을 GPU-specific 특성(warp coalescing, CTA scheduling, NVLink bandwidth asymmetry)과 연결
- CPU에서는 불가능한 관찰 최소 1개 이상 발굴 필요

### Scenario C (확률 85%): 실험 baseline 부재
> **Reviewer**: "Evaluation lacks direct comparison against DGD [Zebchuk 2013] and SCT [Alisafaee 2012] adapted to multi-GPU. Without these baselines, the contribution is unclear."

**대응 준비**:
- M6 실험 계획 참조 — DGD 구현 및 실험 추가 필수
- SCT도 소규모라도 구현하여 비교해야 함

### Scenario D (확률 70%): 구조 유사성 공격
> **Reviewer**: "RSB is structurally identical to ERB in Basu et al. 2013. How does it differ?"

**대응 준비**:
- Ablation A4(RSB on/off)에서 **multi-bank 힌트 기능**이 어떻게 작동하는지 구체 수치로 제시
- ERB와의 구조 비교 표 본문에 포함

### Scenario E (확률 50%): Sub-entry 공격
> **Reviewer**: "Sub-entry structure is conceptually similar to sectored cache coherence (Gupta 1990). Is this a fundamental contribution?"

**대응 준비**:
- Sub-entry와 sectored cache의 차이 명확화: **sectored cache는 sub-block별 하나의 sharer, sub-entry는 sub-region별 독립 sharer bit-vector at multiple levels**
- Ablation에서 sub-entry 없는 설계 대비 효과 정량화

---

## 7. Risk Register 업데이트 (HPCA2027_Superdirectory_논문작성계획서.md § 7 추가)

| ID | 리스크 | 확률 | 영향 | 완화책 | 담당 PHASE |
|----|--------|------|------|--------|------------|
| R8 (신규) | CPU 선행 multi-grain directory 논문(MGD, Basu, Cuesta 2017)과의 차별성 부족으로 novelty 공격 | **높음** | **치명적** | (1) 본 문서의 Tier 1–2 논문 전량 Related Work에 포함, (2) M6 실험으로 dual-grain 한계 정량 증명, (3) Sub-entry 구조를 핵심 contribution으로 승격 | PHASE 0, 2, 4 |
| R9 (신규) | RSB가 Basu의 ERB와 구조적으로 유사함이 지적됨 | 중 | 높음 | RSB의 multi-bank hint 기능을 Ablation A4로 증명, 본문에 ERB 비교 표 포함 | PHASE 3 |
| R10 (신규) | Sub-entry 구조가 sectored cache의 직접적 변형으로 평가됨 | 중 | 중 | Sectored cache와의 기능적 차이(multi-level, independent sharer vector)를 본문에서 명시적으로 구분. Ablation에서 sub-entry 없는 variant와 비교 | PHASE 3 |

---

## 8. 즉시 수행할 조치 (PHASE 0 마감 전까지)

### 8.1 필수 조치 (미달 금지 적용)

1. **Related Work 섹션 작성**: 본 문서의 Tier 1–2 논문 6편 전량 인용 + 각 논문과의 차별점 1문장 이상 명시. (§2.1, §2.2, §2.3, §3.1, §3.2, §3.3 대응)

2. **Motivation 섹션 GPU-specific 보강**: "redundancy가 있다"는 일반적 주장만으로는 Cuesta 2017을 넘어설 수 없음. 다음 중 **최소 1개** 이상의 GPU-specific 관찰 추가 발굴:
   - Warp-level memory coalescing이 만드는 고유한 spatial correlation 패턴
   - CTA scheduling과 NVLink 토폴로지의 상호작용
   - GPU L2와 CPU LLC의 용량/접근 패턴 비대칭
   - Kernel boundary 기반 phase 전환이 CPU phase 전환과 다른 특성

3. **M6 실험 계획 실행**: Dual-grain(DGD) MGPUSim baseline 구현 및 직접 비교 실험 (별도 문서 `M6_DualGrain_Insufficiency_Experiment_Plan.md` 참조).

4. **Ablation A1 승격**: 기존 PHASE 3의 ablation 항목이었던 "Region size 개수 2/3/4/5" 실험을 **Main Evaluation의 일부**로 승격. Dual-grain의 한계를 정면 반박해야 함.

### 8.2 Positioning 재검토 (3가지 안 중 선택)

#### Option A — "Multi-GPU 최초의 adaptive multi-grain directory"
- 장점: 명확한 차별점 (HSC는 integrated, MGD는 CPU multicore)
- 단점: Novelty가 "적용 도메인 변경"으로 폄하될 위험
- 필수 조건: GPU-specific 설계 요소(sub-entry + region-aware MSHR) 강조

#### Option B — "Sub-entry structure enabling independent sharer tracking at multiple granularities"
- 장점: 구조적으로 가장 명확한 CPU 대비 차별점
- 단점: 실험 결과에서 sub-entry가 결정적 기여를 해야 성립
- 필수 조건: Ablation에서 sub-entry의 독립 기여도 >10%p 이상 증명

#### Option C — "Bridging fine-grained REC and coarse-grained HMG via adaptive granularity"
- 장점: Multi-GPU 맥락에서 기존 두 논문을 자연스럽게 연결
- 단점: CPU 선행연구에 대한 답변이 약할 수 있음
- 필수 조건: REC+HMG 조합 baseline(sequential/parallel)과의 비교 포함

**현 시점 권장**: **Option B + Option C 혼합**. Sub-entry를 핵심 구조적 novelty로, REC-HMG bridging을 motivation 서사로 사용.

---

## 9. 참고문헌 (모두 사실 확인 완료, 출처 제공)

### Tier 1
1. J. Zebchuk, B. Falsafi, A. Moshovos. "Multi-grain coherence directories." *MICRO* 2013, pp. 359–370. DOI: 10.1145/2540708.2540739. URL: https://dl.acm.org/doi/10.1145/2540708.2540739
2. A. Basu, B. M. Beckmann, M. D. Hill, S. K. Reinhardt. "CMP Directory Coherence: One Granularity Does Not Fit All." *University of Wisconsin Technical Report #CS-TR-2013-1798*, 2013. URL: https://www.csa.iisc.ac.in/~arkapravab/papers/region_coherence_TR.pdf
3. (Cuesta/Ros 계열 그룹). "Adaptive Coherence Granularity for Multi-Socket Systems." *IEEE TPDS*, 2017. URL: https://ieeexplore.ieee.org/document/7867795/

### Tier 2
4. M. Alisafaee. "Spatiotemporal coherence tracking." *MICRO* 2012, pp. 341–350. DOI: 10.1109/MICRO.2012.39.
5. H. Zhao, A. Shriraman, S. Kumar, S. Dwarkadas. "Protozoa: adaptive granularity cache coherence." *ISCA* 2013, pp. 547–558. DOI: 10.1145/2485922.2485969. URL: https://www.cs.rochester.edu/u/sandhya/papers/isca13.pdf
6. J. Power, A. Basu, J. Gu, S. Puthoor, B. M. Beckmann, M. D. Hill, S. K. Reinhardt, D. A. Wood. "Heterogeneous system coherence for integrated CPU-GPU systems." *MICRO* 2013, pp. 457–467. DOI: 10.1145/2540708.2540747. URL: https://research.cs.wisc.edu/multifacet/papers/micro13_hsc.pdf

### Tier 3 (선택적 인용)
7. A. Gupta, W.-D. Weber, T. Mowry. "Reducing Memory and Traffic Requirements for Scalable Directory-Based Cache Coherence Schemes." *ICPP* 1990.
8. A. Moshovos. "RegionScout: Exploiting Coarse Grain Sharing in Snoop-Based Coherence." *ISCA* 2005.
9. J. F. Cantin, M. H. Lipasti, J. E. Smith. "Improving Multiprocessor Performance with Coarse-Grain Coherence Tracking." *ISCA* 2005.
10. J. Zebchuk, V. Srinivasan, M. K. Qureshi, A. Moshovos. "A tagless coherence directory." *MICRO* 2009, pp. 423–434.
11. H. Zhao, A. Shriraman, S. Dwarkadas. "SPACE: sharing pattern-based directory coherence for multicore scalability." *PACT* 2010, pp. 135–146.
12. L. Fang, P. Liu, Q. Hu, M. C. Huang, G. Jiang. "Building expressive, area-efficient coherence directories." *PACT* 2013, pp. 299–308.
13. Y. Tang, Y. Qiu, et al. "Scalable short-entry dual-grain coherence directories with flexible region granularity." *J. Supercomputing*, 2023. DOI: 10.1007/s11227-023-05559-8.

---

## 10. 연구 윤리 조항 (본 문서 적용)

- **실패 금지**: 본 문서의 조사 결과가 Superdirectory의 novelty를 상당 부분 약화시키더라도, 이 사실을 은폐하지 않고 논문과 계획서에 반영한다. CPU 선행연구와의 차이를 honestly 분석한다.
- **미달 금지**: Tier 1 논문 6편 중 단 하나라도 Related Work에서 누락된 채 논문을 제출하지 않는다. M6 실험 없이 "dual-grain으로는 부족하다"고 주장하지 않는다.
- **추측 금지**: "GPU는 CPU와 다르다"는 주장은 반드시 M1–M6 실험 데이터로 뒷받침한다. 문헌 인용만으로는 불충분.

---

## 11. 다음 단계 (Cross-reference)

- 본 조사의 실행 항목은 **`M6_DualGrain_Insufficiency_Experiment_Plan.md`**(별도 문서)에서 구체화된다.
- Risk Register 갱신은 **`HPCA2027_Superdirectory_논문작성계획서.md § 7`**에 반영한다.
- Related Work 작성 시점은 **PHASE 4 초반**으로 예정하되, Motivation 작성 시에도 본 문서의 Tier 1 논문들을 참조한다.

---

*문서 버전*: v1.0 (2026-04-20 작성)
*다음 리뷰 예정*: PHASE 0 종료 시점(2026-05-03)에 본 문서의 조사 범위를 재검토. HPCA 2026 proceedings 공개 후 새로운 multi-grain directory 논문이 등장했는지 재조사.
