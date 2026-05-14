#!/usr/bin/env bash
# start_sweep.sh — sweep 시작 wrapper
# 이전 log 보존 후 run_sweep_safe.sh 를 백그라운드로 실행하고 60초 후 시작 확인.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG=/tmp/sweep_master.log
PID_FILE=/tmp/sweep.pid

# 이전 log 보존
[ -f "$LOG" ] && mv "$LOG" /tmp/sweep_master_prev.log && echo "[start_sweep] 이전 log → /tmp/sweep_master_prev.log"
[ -f "$PID_FILE" ] && rm "$PID_FILE"

# 백그라운드 실행
cd "$SCRIPT_DIR"
nohup bash run_sweep_safe.sh > "$LOG" 2>&1 &
echo $! > "$PID_FILE"
echo "[start_sweep] Sweep PID: $(cat "$PID_FILE") — log: $LOG"

# 60초 대기 후 시작 확인
echo "[start_sweep] 60초 대기 중..."
sleep 60

echo ""
echo "=== tail -30 $LOG ==="
tail -30 "$LOG"

echo ""
echo "=== 실행 중인 프로세스 ==="
ps aux | grep -E "run_sweep_safe|run_all|matrixmultiplication|pagerank|simpleconvolution|matrixtranspose|stencil2d|im2col" | grep -v grep || echo "  없음"

echo ""
echo "=== 디스크 ==="
df -h /root/mgpusim_home | tail -1
