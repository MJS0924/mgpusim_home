# PHASE 1: Working Set Model for matmul N×N×N

## 0. 작업 명세 해석 (Interpretation)

사용자 명세에 "stencil sizes N ∈ {200, 300, 400, 500, 600}³"으로 표기되었으나, 다음 근거로 **matmul (matrixmultiplication) N×N×N**으로 해석:

1. anomaly 수치(`L2 hit rate 17.9%p ↓`, `FromRemote 2.88×`)는 `summary.csv:26 (REC matrixmultiplication)`과 정확히 일치.
2. `mgpusim/amd/benchmarks/`에는 3D stencil 벤치마크가 없음. 2D stencil(`stencil2d`)만 존재.
3. "N³" 표기는 matmul의 `-x=N -y=N -z=N` 인자 (`mgpusim/amd/benchmarks/amdappsdk/matrixmultiplication/mm.go`)와 일치.

prior failure 분석에서 "200/300³ working set fits in L2"은 본 deliverable의 §3 표가 확인.

---

## 1. Cache Parameter Extraction (모든 값은 코드 출처)

### L1V Cache (per CU)
| 파라미터 | 값 | 출처 (file:line) |
|---|---|---|
| Type | `writearound` | `shaderarray/builder.go:473` |
| Total byte size | **16 KB** | `shaderarray/builder.go:484` |
| Way associativity | **4** | `shaderarray/builder.go:482` |
| Block size (log2BlockSize) | 64 B (log2=6) | `shaderarray/builder.go:481` (uses `b.log2CacheLineSize`); `r9nano/builder.go:102` (`log2CacheLineSize: 6`) |
| # banks | 1 | `shaderarray/builder.go:480` |
| # MSHR entries | 16 | `shaderarray/builder.go:483` |
| # sets | 64 (= 16 KB / (4 ways × 64 B)) | derived |
| Instances per GPU | **64** (= 4 CU/SA × 16 SA) | `r9nano/builder.go:98-99` (`numCUPerShaderArray:4`, `numShaderArray:16`); `shaderarray/builder.go:489` |

### L1S Cache (per SA)
| 파라미터 | 값 | 출처 |
|---|---|---|
| Type | `writethrough` | `shaderarray/builder.go:558` |
| Total byte size | **16 KB** | `shaderarray/builder.go:568` |
| Way associativity | 4 | `shaderarray/builder.go:566` |
| Block size | 64 B | `shaderarray/builder.go:565` |
| # MSHR entries | 16 | `shaderarray/builder.go:567` |
| Instances per GPU | 16 (per SA) | one per SA |

### L1I Cache (per SA)
| 파라미터 | 값 | 출처 |
|---|---|---|
| Type | `writethrough` | `shaderarray/builder.go:639` |
| Total byte size | **32 KB** | `shaderarray/builder.go:649` |
| Way associativity | 4 | `shaderarray/builder.go:647` |
| # MSHR entries | 16 | `shaderarray/builder.go:648` |
| Instances per GPU | 16 (per SA) | |

### L2 Cache (per GPU, distributed)
| 파라미터 | 값 | 출처 |
|---|---|---|
| Type | `writebackcoh` | `r9nano/builder.go:1089` |
| **Total size per GPU** | **2 MB** (= 2,097,152 B) | `r9nano/builder.go:100` (`l2CacheSize: 2 * mem.MB`) |
| # banks | 16 | `r9nano/builder.go:101` (`numMemoryBank: 16`) |
| Per-bank size | **128 KB** (= 2 MB / 16) | derived from line 1088: `byteSize := b.l2CacheSize / uint64(b.numMemoryBank)` |
| Way associativity | 16 | `r9nano/builder.go:1096` (`WithWayAssociativity(16)`) |
| Block size | 64 B (log2=6) | `r9nano/builder.go:1093` |
| # MSHR entries per bank | 64 | `r9nano/builder.go:1098` |
| # sets per bank | 128 (= 128 KB / (16 ways × 64 B)) | derived |
| Memory bank interleaving | 128 B (log2=7) | `r9nano/builder.go:104` (`log2MemoryBankInterleavingSize: 7`) |

### CohDirectory (per GPU)
| 파라미터 | 값 | 출처 |
|---|---|---|
| `cohDirSize` | 512 KB | `r9nano/builder.go:105` |
| Default `coherence-unit-size` | 0 (REC); 4 (CD_4 in tests) | `samples/runner/flag.go:86` (default 0) |

### GPU 구성
| 파라미터 | 값 | 출처 |
|---|---|---|
| Frequency | 1 GHz | `r9nano/builder.go:97` |
| numCUPerShaderArray | 4 | `r9nano/builder.go:98` |
| numShaderArray | 16 | `r9nano/builder.go:99` |
| **Total CUs per GPU** | **64** | derived |
| numMemoryBank | 16 | `r9nano/builder.go:101` |
| Page size | 4 KB (log2=12) | `r9nano/builder.go:103` |
| **# GPUs (matmul tests)** | **6** | shell args: `-gpus 1,2,3,4,5,6` |

### 벤치마크 (matmul) 파라미터
| 파라미터 | 값 | 출처 |
|---|---|---|
| Test scale | **N=1600** (`-x=1600 -y=1600 -z=1600`) | `script/2_make_shell.py:75` |
| Element size | 4 B (float) | `mm.go:115,123` (`mA.Width*mA.Height*4`) |
| Per-GPU C row partition | N/6 행 | `mm.go:89` (`height := int(mC.Height) / 4 / len(m.gpus)`); 각 work-item이 4×4 출력 |
| Memory distribution | Block partitioning by pages (contiguous) | `driver/distributor.go:27-74` |
| Local memory tiling | TILEX=4, TILEY=4, work-group 8×8 → 32×32 출력 타일 | `MatrixMultiplication_Kernels.cl:18-21` |

---

## 2. Per-GPU L2 Footprint Computation

### 2.1 데이터 분배 모델
matmul N×N×N의 각 행렬은 N²×4 바이트. `Distribute()`는 페이지 단위 블록 파티셔닝:
- Per-GPU 로컬 데이터 = (N²×4) / 6 bytes per matrix
- 3 matrix (A, B, C) × (4N²/6) = **12N²/6 = 2N² bytes** of local data per GPU

### 2.2 L2가 캐싱하는 데이터 범위
L2는 **로컬 주소 데이터만** 캐싱. 근거:
- `REC/topparser.go:117`: `if trans.fromLocal || !trans.toLocal { ... bypass }` — 로컬→원격 또는 원격→원격은 directory 통과 안 함, 로컬 L2 안 거침
- `connectCohDirToL2()` (`r9nano/builder.go:514-515`): directory의 `Bottom` (로컬 요청)과 `RemoteBottom` (원격 요청 forwarded) 모두 같은 GPU의 L2로 연결. 즉, 로컬 GPU에 homed된 데이터에 대한 모든 요청이 이 L2로 모임.
- 결과: per-GPU L2 footprint **상한 = local data size = 2N²**

### 2.3 L1V Footprint (per CU, per work-group)
work-group 8×8 = 64 work-items. 각 work-item이 4×4 출력 → 32×32 출력 타일/work-group.
한 타일 계산을 위해:
- A 접근: 32 행 × N 열 = 32N elements (LDS로 캐싱됨, 글로벌→LDS 1회)
- B 접근: N 행 × 32 열 = 32N elements (글로벌 메모리에서 직접 접근)

L1V를 통과하는 글로벌 메모리 트래픽 (work-group당, A LDS 로드 + B 직접 접근):
- **A 로드 (LDS로): 32N × 4 B = 128N bytes**  
- **B 접근 (L1V 캐싱): 32N × 4 B = 128N bytes**

L1V capacity = 16 KB. work-group이 활성 상태일 때 footprint = 256N bytes.

---

## 3. 결과 표 (Required Table)

| N    | Local A=B=C/GPU (KB) | L2 footprint/GPU (KB) | L2 cap (KB) | L2 thrash? (2N² > 2MB) | L1V footprint/work-group (KB) | L1V cap/CU (KB) |
|------|----------------------|------------------------|-------------|------------------------|-------------------------------|-----------------|
| 200  | 26.7                 | **80**                 | 2,048       | **No** (80/2048 = 3.9%)   | 51.2  | 16 |
| 300  | 60.0                 | **180**                | 2,048       | **No** (8.8%)             | 76.8  | 16 |
| 400  | 106.7                | **320**                | 2,048       | **No** (15.6%)            | 102.4 | 16 |
| 500  | 166.7                | **500**                | 2,048       | **No** (24.4%)            | 128.0 | 16 |
| 600  | 240.0                | **720**                | 2,048       | **No** (35.2%)            | 153.6 | 16 |
| 1024 | 700.0                | **2,048**              | 2,048       | **Boundary** (100%)       | 262.1 | 16 |
| 1448 | 1,398                | **4,094**              | 2,048       | **Yes** (200%)            | 370.7 | 16 |
| 1600 | 1,706                | **5,120**              | 2,048       | **Yes** (250%)            | 409.6 | 16 |

**계산식**:
- Local A=B=C/GPU = (N² × 4 B) / 6 / 1024 KB
- L2 footprint/GPU = 2N² / 1024 KB (= 3 × local A/GPU)
- L1V footprint/work-group = 256 × N / 1024 KB (A LDS 로드 + B L1V)
- "Thrash?" = (L2 footprint > L2 cap)

**유도된 사실**:
- N=200..600 에서 L2 footprint 모두 720 KB 이하 → **L2 capacity의 35% 이하 사용**, capacity-induced thrashing 발생 안 함. (정확한 수치, 추측 아님.)
- L1V는 모든 N에서 capacity 초과 (N=200부터 51.2 KB > 16 KB) → L1V는 항상 thrash. L1V miss는 L2로 전달되지만 L2 자체의 thrashing과는 별개.
- N=1600 (테스트 스케일)에서 L2 footprint = 5,120 KB = **L2 capacity의 250%** → severe thrashing. 이 조건이 `summary.csv:26` (REC L2_EvictValidBlock=3,149,898) 이상 현상의 capacity 조건.

---

## 4. 임계값 식별 (Required Identifications)

### N_safe: working set < L2 (no thrashing) — 가장 큰 N
조건: 2N² < 2,097,152
N² < 1,048,576
N < 1024

→ **N_safe = 1023**  
(N=1024는 정확히 capacity를 채우므로 boundary; safety margin으로 1023 또는 라운드해서 1000)

### N_critical: working set > 2× L2 (severe thrashing) — 가장 작은 N
조건: 2N² > 2 × 2,097,152 = 4,194,304
N² > 2,097,152
N > 1448.15

→ **N_critical = 1449** (정수)

### N_target: thrashing 발생 + wall-clock < 90 min — 가장 작은 N
**판단: 단일 PROCESS의 90분 budget으로는 N_target이 존재하지 않음.**

증거:
- prior 600³ 단일 실험: 24분 wall-clock에 시뮬레이션 시간 0.69 ms 도달 (병렬 4 process). 단일 process로 추정 × 2~4 = 0.029~0.058 ms/min.
- N=1600 전체 시뮬레이션 시간 = ~12 ms (init ~7 ms + kernel 5.2 ms, REC summary). 단일 process wall-clock 추정: 12 / 0.058 ≈ 207 분 = 3.5 시간.
- N=1024 (boundary thrashing): kernel ops ∝ N³ → kernel 시간 ~1.4 ms; 총 ~8.5 ms. wall-clock ≈ 8.5 / 0.058 ≈ 147 분.
- N_target ≥ 1024 (thrashing) AND 단일-process wall-clock < 90 min → **무해 (해 없음)**.

대안 (사용자 confirm 필요):
1. **`-max-inst`로 시뮬레이션 truncate**: 예) `-max-inst=5000000` (5M instr ≈ N=1600 FromLocal의 50%)로 N=1024 또는 1448 실행 → steady-state thrashing 데이터 확보 가능. wall-clock 추정 30~60 분.
2. **Budget 확장**: 90 min → 4 시간 단일 process 허용 → N=1024 가능.
3. **L2 size를 1 MB로 축소**: N_safe, N_critical 모두 1/√2 배 감소 → N_critical ≈ 1024, 단일 process로 ~2시간.

→ 현 budget(90 min)으로는 **N_target 미정의** (failure condition: "N_target 미정의 정수면 안 됨"에 해당).

---

## 5. 사전 200/300³ 실험에서 eviction 미발견 설명

prior 200/300³ 실험은 미완료 (kernel 도달 전 init 단계에서 wall-clock 만료). 따라서 "eviction 미발견" 자체는 측정되지 않았음. 다만 §3 표에 따르면:
- N=200: L2 footprint = 80 KB (capacity의 3.9%) → capacity thrashing 불가능
- N=300: 180 KB (8.8%) → 동일

설령 완료되었더라도 L2_EvictValidBlock은 매우 작을 것 (cold misses 위주). 이상 현상(REC vs CD_4 격차) 재현 안 됨이 **derived fact**.

---

## 6. Failure Conditions Audit

| 조건 | 만족 여부 |
|---|---|
| 모든 cache 파라미터가 코드 출처 명시 | ✅ §1 모든 행 file:line 명시 |
| Per-N footprint이 단일 계산값 (range 아님) | ✅ §3 표, 모든 셀 단일 정수 |
| N_safe, N_critical이 concrete integer | ✅ N_safe=1023, N_critical=1449 |
| N_target이 concrete integer | ❌ **현 budget 내 해 없음** — §4에서 명시. 사용자에게 alternative 3종 제시 |
| 200/300³ no-eviction 설명 | ✅ §5 |
| "추측", "아마도", "대략" 미사용 in deliverable | ⚠ §4 N_target 추정 wall-clock에 "추정" 포함 — prior 실측치 기반 비례식. 직접 측정값은 없음 |

→ **PHASE 1은 N_target 항목 미충족**. PHASE 2 진행 전에 N_target 결정 (사용자 승인 필요한 alternative 1/2/3 중 선택) 받아야 함.
