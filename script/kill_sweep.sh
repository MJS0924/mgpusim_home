#!/usr/bin/env bash
# kill_sweep.sh — 실행 중인 sweep 프로세스 전부 강제종료 + 임시 파일 정리

set +e

echo "=== [1] 프로세스 종료 ==="

PIDS=$(ps aux | grep -E "run_sweep_safe|run_all\.sh|run_pagerank|run_matrixmultiplication|run_simpleconvolution|run_matrixtranspose|run_stencil2d|run_im2col|run_motivation|run_bfs|run_fft|run_fir|run_atax" | grep -v grep | awk '{print $2}')

BIN_PIDS=$(ps aux | grep -E "amd/samples/.*/[a-z]+ -timing" | grep -v grep | awk '{print $2}')

ALL_PIDS="$PIDS $BIN_PIDS"

if [ -z "$(echo $ALL_PIDS | tr -d ' ')" ]; then
    echo "  실행 중인 sweep 프로세스 없음"
else
    echo "  종료 대상 PID: $ALL_PIDS"
    kill $ALL_PIDS 2>/dev/null
    sleep 2
    # 아직 살아있으면 SIGKILL
    REMAINING=$(ps aux | grep -E "run_sweep_safe|run_all\.sh|amd/samples/.*/[a-z]+ -timing" | grep -v grep | awk '{print $2}')
    if [ -n "$REMAINING" ]; then
        echo "  SIGKILL: $REMAINING"
        kill -9 $REMAINING 2>/dev/null
    fi
    echo "  종료 완료"
fi

echo ""
echo "=== [2] 임시 파일 정리 ==="

# /tmp sweep 관련
for f in /tmp/sweep*.log /tmp/sweep*.pid /tmp/*events*.parquet /tmp/*.sqlite3 /tmp/post_restart*; do
    [ -f "$f" ] && rm -f "$f" && echo "  삭제: $f"
done

# amd/samples 하위 akita sqlite3
while IFS= read -r f; do
    rm -f "$f" && echo "  삭제: $f"
done < <(find /root/mgpusim_home/mgpusim/amd/samples -name "akita_sim_*.sqlite3" 2>/dev/null)

echo ""
echo "=== [3] 확인 ==="
REMAINING=$(ps aux | grep -E "run_sweep_safe|run_all\.sh|amd/samples/.*/[a-z]+ -timing" | grep -v grep)
if [ -z "$REMAINING" ]; then
    echo "  프로세스: 없음 (정상)"
else
    echo "  [경고] 아직 살아있는 프로세스:"
    echo "$REMAINING"
fi

LEFTOVER=$(find /root/mgpusim_home/mgpusim/amd/samples -name "akita_sim_*.sqlite3" 2>/dev/null)
[ -z "$LEFTOVER" ] && echo "  sqlite3 임시 파일: 없음 (정상)" || echo "  [경고] 남은 파일: $LEFTOVER"
