#!/bin/bash
# h4_relu_4x_parallel_cd.sh — Step C-1 (parallel CD batch only).
# Launches CD_0/1/2/4/6/8 with MAX_PARALLEL=4. SD sim is assumed
# already running (started by the prior sequential launcher attempt
# and preserved when that launcher was killed).

set -uo pipefail

MAX_PARALLEL=4
OUT_DIR=/root/mgpusim_home/results/per_window/relu_4x
LOG_DIR=/root/mgpusim_home/results/.h4_relu_4x_logs
EVT_DIR=/root/mgpusim_home/results/.h4_relu_4x_events
METRIC_DIR=/root/mgpusim_home/results/.h4_relu_4x_metrics
mkdir -p "$OUT_DIR" "$LOG_DIR" "$EVT_DIR" "$METRIC_DIR"

BIN=/root/mgpusim_home/mgpusim/amd/samples/relu/relu
LENGTH=15360000

LAUNCH_LOG="$LOG_DIR/parallel_cd_launch.log"
echo "[$(date '+%F %T')] === Parallel CD batch launch (max=$MAX_PARALLEL) ===" > "$LAUNCH_LOG"
echo "BIN: $BIN, LENGTH: $LENGTH" >> "$LAUNCH_LOG"
echo "" >> "$LAUNCH_LOG"

trap 'echo "[$(date "+%F %T")] received TERM/INT — killing children" | tee -a "$LAUNCH_LOG"; kill 0; exit 1' INT TERM

run_variant_bg() {
    local var=$1
    local cu=${var#CD_}

    local out_csv="$OUT_DIR/relu_4x_${var}_per_window.csv"
    local logf="$LOG_DIR/relu_4x_${var}.log"
    local metric_pfx="$METRIC_DIR/relu_4x_${var}_metrics"
    local evt_pq="$EVT_DIR/relu_4x_${var}_events.parquet"

    echo "[$(date '+%F %T')] Start $var (bg)" | tee -a "$LAUNCH_LOG"

    (
        cd /tmp
        EVENT_LOG_PATH="$evt_pq" "$BIN" \
            -timing \
            -unified-gpus=1,2,3,4,5 \
            -use-unified-memory \
            -coherence-directory=CoherenceDirectory \
            -log2-page-size=12 \
            -coherence-unit-size="$cu" \
            -length=$LENGTH \
            -per-window-snapshot \
            -window-instructions=50000 \
            -per-window-output="$out_csv" \
            -metric-file-name="$metric_pfx" \
            -report-all > "$logf" 2>&1
        rc=$?
        nrows="?"
        [ -f "$out_csv" ] && nrows=$(($(wc -l < "$out_csv") - 1))
        echo "[$(date '+%F %T')] Done  $var  (exit=$rc, windows=$nrows)" >> "$LAUNCH_LOG"
    ) &

    # Throttle: wait until below MAX_PARALLEL background jobs of this script
    while [ "$(jobs -rp | wc -l)" -ge "$MAX_PARALLEL" ]; do
        wait -n 2>/dev/null || wait
    done
}

# 6 CD variants only (SD is running independently from prior launcher)
for var in CD_0 CD_1 CD_2 CD_4 CD_6 CD_8; do
    run_variant_bg "$var"
done

# Wait for the rest to drain
wait
echo "[$(date '+%F %T')] === ALL CD VARIANTS COMPLETE ===" | tee -a "$LAUNCH_LOG"
