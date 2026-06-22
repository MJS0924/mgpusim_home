# SD 9-bank cross-GPU eviction-credit 데드락 수정 — 패치 노트 (SD-ACK-RESERVE)

`stencil2d -coherence-directory=SuperDirectory -sd-num-banks=9 -sd-log2-sub-entry=1`
(= ablation `a5_log2_1`, 64B→16KB region 폴딩) + `-inter-gpu-noc`, 4 GPU 에서
결정적으로 발생하던 cross-GPU **eviction-credit** 데드락을 해결합니다.

> **CD_8 데드락(`cd8-deadlock-fix`)과도, win79 silent-loss 와도 다른 별개 데드락.**
> CD_8 은 invalidation-driven dirty-flush 의 InvRsp 차단(InvRsp edge)이었고, 이건
> peer-incoming write 의 **WriteDoneRsp(ack) 차단**(ack edge)이다. 두 수정은 독립적
> 으로 토글되며 같이 켜도 무방하다.

## Base 커밋 (다른 환경이 맞춰야 할 기준)

| repo | commit |
|---|---|
| akita | `aa949582c72a1723e38a575bda32c03edd83bc43` |
| mgpusim | `770d731cdb9a2bfb07ca285d38e5bce7e463743d` |

> 패치는 위 두 커밋 기준. 같은 커밋이면 깨끗하게 적용됨. 다르면 `git apply --3way`.

## 적용 방법

```bash
# akita (서브모듈) — 핵심 수정
cd <repo>/akita
git apply --check /path/to/akita-sd-ack-reserve.patch
git apply         /path/to/akita-sd-ack-reserve.patch

# mgpusim — 토글 플래그 배선
cd <repo>/mgpusim
git apply --check /path/to/mgpusim-sd-ack-reserve.patch
git apply         /path/to/mgpusim-sd-ack-reserve.patch

# 재빌드 (stencil2d 만)
cd <repo>/mgpusim/amd/samples/stencil2d && go build -o stencil2d .
```

## 근본 원인 (RTM `/api/field` 로 확정)

홈 L2 가 peer GPU 로부터 받은 write(`writeToHomeNode`, `fromLocal=false`)를 처리하면
그 즉시 `WriteDoneRsp`(ack)를 sender 로 보낸다(`finalizeWriteHit`/
`finalizeBankWriteFetched` → `remoteTopPort.Send`, **RESPONSE-DECOUPLE**: victim 이
*드레인*될 때가 아니라 *배치*되는 순간 ack). 이 ack 가 sender L2 의
`numRemoteInflEvictOwn` credit 을 푼다 (cross-GPU eviction credit 은 오직 ack 로만 회수).

문제: ack 를 보내려면 그 write 가 밀어낸 displacement victim 을 어딘가에 **배치**해야
하는데, 배치 대상이 단 두 개의 작은 공유 레인뿐이다:
- `writeBufferBufferRemote` (cap = `numReqPerCycle` = **4**)
- `deferredFlushPeer` (cap = `maxDeferredFlush/2` = `numReqPerCycle` = **4**)

즉 peer-ack victim 의 배치 슬롯이 총 **8 개**이고, 이마저 bulk peer-bypass 쓰기와
공유한다. SD 9-bank 의 fine-granularity invalidation flood(작은 region → 잦은
remote write/invalidation, `pendingRemoteWriteAfterInv` 2690 수준)에서 두 레인이 모두
차면 → victim 배치 불가 → `finalizeWriteHit` 이 `return false` → **ack 미발행** →
sender 의 `numRemoteInflEvictOwn` credit 영구 pinned. 4 GPU 가 대칭으로 서로의 ack 를
기다려 **cross-GPU eviction-credit 순환 대기**가 닫힌다.

RTM 로 확정된 동결 상태: `numRemoteInflEvictOwn`=96(cap), `tooManyOutgoingRemote`
exhausted(288 pending + 96~114 inflight ≥ 384), own dirty-flush 거부, peer write 처리
정지. (이 게이트는 own-only 라 peer 경로가 절대 소비하지 않음 → maxOutgoingRemotePending
예약은 NO-OP, 실제 자원은 위 8 슬롯이었음.)

## 수정 — `ackDisplaceReserve` (CORE) — `akita-sd-ack-reserve.patch`

peer-incoming ack victim **전용** 3 번째 배치 레인. own/bulk 작업은 절대 점유 못 함
(게이트가 `!trans.fromLocal` 일 때만 예약 여유를 인정). victim 이 예약에 배치되는 순간
ack 가 나가 → remote credit 회수 → 순환 차단. 예약된 victim 은 `tryWriteOne` 이
목적지(`toLocal(evictingAddr)`)로 라우팅해 드레인. **bounded**(`maxInflightEviction`
= 128, cd8 예약과 동일 스케일) → 메모리 무한 증가 없음. **write 완료 순서/정합성
무변**(early-ack 아님 — ack 는 원래도 victim *배치* 시점에 나갔고, 그 배치처를 보장만 함).

파일:
- `akita/mem/cache/writebackcoh/writebufferstage.go`: `ackDisplaceReserve` 필드 +
  `ackDisplaceReserveCanPush/Push` + `tryWriteOne` 최우선 드레인(목적지 라우팅) + Reset clear
- `akita/mem/cache/writebackcoh/bankstage.go`: ack 게이트가 peer victim 에 한해 예약
  여유 인정(`finalizeWriteHit`+`finalizeBankWriteFetched` 둘 다) + 배치 블록 last-resort
  로 `ackDisplaceReservePush`(own 은 도달 불가 — own 게이트는 두 레인 full 시 return false)
- `akita/mem/cache/writebackcoh/builder.go`: `ackReserveFix` 토글 + 예약 cap =
  `maxInflightEviction` + `if !ackReserveFix { maxAckDisplaceReserve = 0 }` 비활성 가드

## 토글 플래그 `-sd-ack-reserve` (기본 **OFF**) — `akita` + `mgpusim`

cd8 와 달리 **기본 꺼짐**. 켜야만 예약이 생긴다(끄면 `maxAckDisplaceReserve=0` →
`ackDisplaceReserveCanPush()` 항상 false → 게이트 4번째 항이 `true` 로 붕괴 → **원본
코드경로와 비트 동일**, 다른 실험 무영향 보장). 배선은 cd8 와 동일 패턴:
`flag.go → runner.go → timingconfig/builder.go → r9nano/builder.go → writebackcoh/builder.go`.

```bash
stencil2d ... -sd-num-banks=9 -sd-log2-sub-entry=1                    # 기본: 원본 데드락 재현
stencil2d ... -sd-num-banks=9 -sd-log2-sub-entry=1 -sd-ack-reserve=true  # 수정 ON
```

## 검증 방법

```bash
# 수정 ON: window 962(sim_time 12729552 ns, baseline 동결점) 통과 + 4 iter 완주해야 함
stencil2d -timing -cd8-deadlock-fix=true -sd-ack-reserve=true \
  -unified-gpus=1,2,3,4 -inter-gpu-noc -inter-gpu-noc-bw=300 \
  -use-unified-memory -page-migration-policy=None \
  -coherence-directory=SuperDirectory -sd-num-banks=9 -sd-log2-sub-entry=1 \
  -log2-page-size=12 -row=4000 -col=4000 -iter=4
# baseline(= -sd-ack-reserve 없음)은 window 962 / sim_time 12729552 ns 에서 동결.
```

검증 상태: **❌ 실패 — 수정이 데드락을 막지 못함** (2026-06-21).
a5_log2_1 + `-sd-ack-reserve=true` 가 window 962 부근에서 동일 데드락("No More Event /
Engine stops"). 정지 프로세스 RTM 라이브 진단 결과 **이 수정은 레이어가 틀렸음**:
ackDisplaceReserve 는 켜졌으나(maxAckDisplaceReserve=128) **전 GPU empty** — 데드락
시점에 한 번도 사용 안 됨. 전 L2 receive 파이프라인 idle(numPeerIncomingPending=0,
remoteBottomPort.incomingBuf 0/8, mshr~0) 인데 numRemoteInflEvictOwn=96(cap) 고갈,
그리고 **RDMA 가 수신요청 6437개(transactionsFromOutside)를 들고 idle L2 로 forward 안 함**.
→ 실제 데드락은 **RDMA/inter-GPU NoC 레이어의 cross-GPU eviction-credit 순환**이고,
peer write 가 L2 ack-production 게이트(본 수정 타겟)에 도달하기 *전에* 막힌다.
다음 방향: `-inter-gpu-noc-split-rsp` 재시도 / RDMA admission+응답 용량 예약.
상세 증거는 `verify_ackreserve/VERIFY_RESULT.txt`. (본 수정 코드는 default OFF 라 무해하나
a5_log2_1 미해결 — 보관/참고용.)

## 정정성 안전성 논거

- **flag OFF == 원본**: 게이트의 4번째 항 `!(!fromLocal && ackDisplaceReserveCanPush())`
  은 예약 비활성 시 `!(... && false)` = `true` → AND 무영향. 배치 블록의 새 `else if`/
  `else` 도 cap 0 이면 예약 분기 unreachable. **OFF 일 때 코드 경로 변화 0.**
- **own write 무영향(ON 일 때도)**: 게이트 4번째 항이 `!trans.fromLocal` 로 막혀 own 은
  예약 여유를 못 봄 → own 의 ack/배치 의미 그대로. 배치 last-resort `else` 도 own 은
  도달 불가(own 게이트는 두 레인 full 이면 이미 return false).
- **liveness**: 예약에 victim 이 N 개 쌓였다는 건 ack N 개가 이미 나가 remote credit N 개를
  풀었다는 뜻 → 시스템이 *해소 중*. 예약은 full absorber 가 아니라 credit 이 흐르기
  시작하게 하는 slack. bounded(128) 라 무한 증가 없음.
