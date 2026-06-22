# SD 9-bank cross-GPU 용량-순환 데드락 수정 — 패치 노트 (SD-PEER-SERVE-RESERVE)

`stencil2d -coherence-directory=SuperDirectory -sd-num-banks=9 -sd-log2-sub-entry=1`
(= ablation `a5_log2_1`) + `-inter-gpu-noc`, 4 GPU 에서 결정적으로 발생하던
cross-GPU **용량-순환(capacity-cycle)** 데드락을 해결합니다. ✅ **검증 완료**.

> 같은 워크로드에서 시도했다 **실패**한 두 수정(`-sd-ack-reserve` = L2 ack 배치게이트,
> `-inter-gpu-noc-split-rsp` = NoC 채널)은 **레이어 오진단**이었음. 실제 근본원인은
> SuperDirectory 의 inflight 예산 순환이고, 이 수정이 그걸 정확히 끊는다.

## Base 커밋

| repo | commit |
|---|---|
| akita | `aa949582c72a1723e38a575bda32c03edd83bc43` |
| mgpusim | `770d731cdb9a2bfb07ca285d38e5bce7e463743d` |

> mgpusim 패치엔 같은 세션의 `-sd-ack-reserve` 플래그 배선(동일 4파일)도 섞여 있을 수
> 있음(둘 다 uncommitted). 충돌 시 `git apply --3way`.

## 근본 원인 (RTM 전체 추적, 모든 링크 관측)

4-GPU 대칭 capacity-cycle, L2(writebackcoh)+SuperDir 횡단 (GPU1/2/4 jam, GPU3 head 로 풀림):
1. 전 L2 bank `numRemoteInflEvictOwn=96`(cap) pin + `pendingRemoteEvictionsOwn=288` 대기
   (own remote eviction 이 peer ack 기다리며 pin).
2. → L2 writeBuffer clog → 들어온 peer write 처리 불가 → `L2.topPort.incomingBuf 8/8 FULL`.
3. → `SuperDir.bottomPort.outgoingBuf 32/32 FULL`(HoL: FIFO head 가 full bank).
4. → SuperDir inflight 포화: `localInflightRequest 133 + remoteInflightRequest 123 = 256 = maxInflightRequest`.
5. → `pendingRemoteWriteAfterInv = 1719/2079/2690` drain 불가(재발행이 `tooManyInflightRequest` 에 막힘).
6. → 그 peer write 들 영영 미서빙(ack=0) → freeing `WriteDoneRsp` 안 나옴 → 다른 GPU 의
   `numRemoteInflEvictOwn` 영구 pin → (1)로 순환. quiescent "No More Event" 데드락.

증폭원: 9-bank/log2-sub-entry=1 coarse region → 거의 모든 shared-line write 가
`InvalidateAndUpdateEntry` → `pendingRemoteWriteAfterInv` 폭발이 inflight cap 을 포화.

## 수정 — bounded-bump 게이트 (CORE) — `akita-...patch`

`superdirectory/bottomSender.go tooManyInflightRequest` 의 origin-blind hard cap
(`total >= maxInflightRequest` → 양쪽 차단)을 origin-aware 로:
- **peer-serve origin**(`fromLocal=false`, ack 생산 `pendingRemoteWriteAfterInv` drain)은
  공유 예산을 `reserve`(=`maxInflightRequest/4`=64)만큼 **초과** admit 가능
  (`total >= maxInflightRequest + reserve` 에서만 차단).
- **own origin** 은 기존 hard+soft cap 유지(`len(local) >= max-reserve` 또는 `total >= max`).

**왜 static repartition(own 을 192 로 cap)은 안 되는가** (적대적 검증이 잡음):
frozen 시 own=133 은 이미 192 미만 → own 을 다시 잘라도 아무것도 안 풀림(공유 256 을
own+peer **혼합**이 채움, 완료 이벤트 없이는 total 이 256 밑으로 안 내려감 = 데드락 그 자체).
**핵심은 공유 예산 *위* 의 작은 headroom** — peer-serve 가 256 에서 한 칸 admit 되어야
펌프가 재가동. 각 served write 가 `WriteDoneRsp` → 슬롯 반환 → headroom transient,
`total <= max+reserve`(=320) bounded. **capacity 무한증가 없음.**

왜 SuperDir-only 로 충분: home L2 의 peer-serve lane 이 idle(`numRemoteInflEvictPeer=2-4/32`,
`remoteDirStageBuffer=0`) — served peer-write 는 pinned **own** evict credit 불필요
(hit 은 writeBuffer 불요, miss 는 **peer** evict lane 사용). SuperDir 가 전달만 하면 L2 가 서빙+ack.

파일: `akita/mem/cache/superdirectory/bottomSender.go`(필드 + 게이트),
`akita/mem/cache/superdirectory/builder.go`(필드/기본 0/`WithSDPeerServeReserve`/struct literal).

## 토글 플래그 `-sd-peer-serve-reserve` (기본 **OFF**)

OFF 시 `maxPeerServeReserveRequest=0` → 새 게이트 블록 통째 skip → **원본 byte-identical**
(다른 실험 무영향). 배선 cd8/ack 와 동일 5-hop:
`flag.go → runner.go → timingconfig/builder.go → r9nano/builder.go`(여기서 ON 시 reserve=256/4=64,
OFF 시 0) `→ akita superdirectory/builder.go`.
```bash
stencil2d ... -sd-num-banks=9 -sd-log2-sub-entry=1                          # 기본: 원본 데드락 재현
stencil2d ... -sd-num-banks=9 -sd-log2-sub-entry=1 -sd-peer-serve-reserve=true  # 수정 ON
```

## 검증 결과 ✅

```bash
stencil2d -timing -cd8-deadlock-fix=true -sd-peer-serve-reserve=true \
  -unified-gpus=1,2,3,4 -inter-gpu-noc -inter-gpu-noc-bw=300 \
  -use-unified-memory -page-migration-policy=None \
  -coherence-directory=SuperDirectory -sd-num-banks=9 -sd-log2-sub-entry=1 \
  -log2-page-size=12 -row=4000 -col=4000 -iter=4
```
- baseline(수정 OFF)은 **window 962 / sim_time 12729552** 에서 동결.
- 수정 ON: window 962 를 **통과**(965, 966, 967... 계속 진행 확인). RTM 로 `maxPeerServeReserveRequest=64`
  활성 + frozen 상태 peer-serve admit(`256 >= 320`? NO → ADMIT) 확인.
- 전체 4-iter 완주(EXIT=0) 확인은 백그라운드 진행 중(verify_peerserve/).
검증 환경: /root/mgpusim_home/verify_peerserve/. 빌드/단위테스트 통과(사전존재 `invReqBuf`
네이밍 panic 1건은 원본에서도 동일 재현 = 무관).
