#!/bin/bash
# h4_spmv_4x_launch.sh — Step C-2: spmv 4× input × 7 variants
# 4× scaling: -dim=131072 (was 65536) keeps -sparsity=0.000871 → 4× nonzeros
# (SpMV work ≈ O(nonzeros)). MAX_PARALLEL=4.

set -uo pipefail

MAX_PARALLEL=4
WORKLOAD=spmv_4x
OUT_DIR=/root/mgpusim_home/results/per_window/$WORKLOAD
LOG_DIR=/root/mgpusim_home/results/.h4_${WORKLOAD}_logs
EVT_DIR=/root/mgpusim_home/results/.h4_${WORKLOAD}_events
METRIC_DIR=/root/mgpusim_home/results/.h4_${WORKLOAD}_metrics
mkdir -p "$OUT_DIR" "$LOG_DIR" "$EVT_DIR" "$METRIC_DIR"

BIN=/root/mgpusim_home/mgpusim/amd/samples/spmv/spmv

LAUNCH_LOG="$LOG_DIR/launch.log"
echo "[$(date '+%F %T')] === Step C-2 launch: spmv 4× (max=$MAX_PARALLEL) ===" > "$LAUNCH_LOG"
echo "BIN: $BIN  -dim=131072 -sparsity=0.000871" >> "$LAUNCH_LOG"
echo "" >> "$LAUNCH_LOG"

trap 'echo "[$(date "+%F %T")] received TERM/INT — killing children" | tee -a "$LAUNCH_LOG"; kill 0; exit 1' INT TERM

run_variant_bg() {
    local var=$1
    local cflag extra
    if [ "$var" = "SD" ]; then
        cflag="SuperDirectory"; extra=""
    else
        cflag="CoherenceDirectory"; extra="-coherence-unit-size=${var#CD_}"
    fi

    local out_csv="$OUT_DIR/${WORKLOAD}_${var}_per_window.csv"
    local logf="$LOG_DIR/${WORKLOAD}_${var}.log"
    local metric_pfx="$METRIC_DIR/${WORKLOAD}_${var}_metrics"
    local evt_pq="$EVT_DIR/${WORKLOAD}_${var}_events.parquet"

    echo "[$(date '+%F %T')] Start $var" | tee -a "$LAUNCH_LOG"

    (
        cd /tmp
        EVENT_LOG_PATH="$evt_pq" "$BIN" \
            -timing \
            -unified-gpus=1,2,3,4,5 \
            -use-unified-memory \
            -coherence-directory="$cflag" \
            -log2-page-size=12 \
            -dim=131072 -sparsity=0.000871 \
            $extra \
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

    while [ "$(jobs -rp | wc -l)" -ge "$MAX_PARALLEL" ]; do
        wait -n 2>/dev/null || wait
    done
}

for var in SD CD_0 CD_1 CD_2 CD_4 CD_6 CD_8; do
    run_variant_bg "$var"
done
wait
echo "[$(date '+%F %T')] === C-2 ALL DONE ===" | tee -a "$LAUNCH_LOG"
