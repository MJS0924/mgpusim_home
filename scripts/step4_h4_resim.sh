#!/bin/bash
# Step 4 (H4 검증) — relu / spmv / conv2d 를 4× 큰 input/iteration 으로 재시뮬.
# 목적: window 길이 sensitivity 측정. spmv는 양수 capture, relu/conv2d는 음수.
# 4× 후 capture가 어떻게 변하는지로 H4 (window too short) 영향 정량화.
#
# 실행:
#   bash /root/mgpusim_home/scripts/step4_h4_resim.sh    # 순차 (12시간+)
#   nohup bash /root/mgpusim_home/scripts/step4_h4_resim.sh > step4.log 2>&1 &
#                                                         # 백그라운드
#
# 사전 조건:
#   - 모든 sample binary가 최신 코드로 빌드되어 있어야 함 (build_all.sh 결과)
#   - results/per_window/{relu,spmv,conv2d}_4x/ 디렉토리에 결과 저장
#
# 주의:
#   - SD event log (parquet) 도 새로 생성됨 → 기존 events/{name}_events.parquet
#     을 백업할 것
set -euo pipefail

ROOT=/root/mgpusim_home
RESULTS_DIR="$ROOT/results/per_window"
EVENTS_DIR="$ROOT/results/superdirectory/rawdata/events"
SQL_DIR="$ROOT/results/superdirectory/rawdata/sql"
BACKUP_DIR="$ROOT/results/.step4_backup_$(date +%Y%m%d_%H%M%S)"

echo "=== Step 4 H4 verification: 4× input/iteration re-sim ==="
echo "Backup dir: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR/events" "$BACKUP_DIR/per_window"

# Backup current 50K window CSVs and event logs
for w in relu spmv conv2d; do
    cp -r "$RESULTS_DIR/$w" "$BACKUP_DIR/per_window/$w"
    [ -f "$EVENTS_DIR/${w}_events.parquet" ] && \
        cp "$EVENTS_DIR/${w}_events.parquet" "$BACKUP_DIR/events/"
done
echo "Backup complete."

# relu  (4× input) — input flag depends on benchmark; check fir.go pattern
# spmv  (4× input)
# conv2d (4× iteration)
#
# WARNING: input-size flags differ per benchmark. The exact flag for each
# is in the corresponding sample's main .go file. Examples below assume:
#   relu:    -length=N
#   spmv:    -dim=N
#   conv2d:  -iter=N (or run-length flag)
# Adjust to match the actual benchmark CLI before launching.

# Example commands (UNCOMMENT and adjust flags after verifying CLI):
#
# cd "$ROOT/mgpusim/amd/samples/relu/superdirectory"
# ../relu -timing -unified-gpus=1,2,3,4,5 -use-unified-memory \
#         -coherence-directory=SuperDirectory -log2-page-size=12 \
#         -length=$((262144 * 4)) \
#         -per-window-snapshot -window-instructions=50000 \
#         -per-window-output="$RESULTS_DIR/relu_4x/relu_SD_per_window.csv" \
#         -report-all
# (repeat for CD_0, CD_1, CD_2, CD_4, CD_6, CD_8 with -coherence-directory=CoherenceDirectory)
#
# cd "$ROOT/mgpusim/amd/samples/spmv/superdirectory"
# (similar)
#
# cd "$ROOT/mgpusim/amd/samples/conv2d/superdirectory"
# (similar)

echo ""
echo "TODO: uncomment and tailor the CLI block above to your benchmark flags."
echo "Then run: bash $0  (or via nohup for background)."
echo ""
echo "After re-sim completes, run:"
echo "  python3 $ROOT/scripts/oracle_relative_stats.py"
echo "  (modify WORKLOADS in script to point at *_4x/ subdirs, or"
echo "   set PER_WINDOW_DIR via env var if you wire it up.)"
echo ""
echo "Compare oracle_relative_stats.csv before vs after — sd_headroom_capture"
echo "shift quantifies H4 contribution."
