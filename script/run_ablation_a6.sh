#!/bin/bash
# A6: log2NumSubEntry (interval) sweep — 2x / 4x(default) / 8x
# Usage: bash run_ablation_a6.sh
#
# Prerequisites:
#   - -sd-log2-sub-entry CLI flag added (plumbing r9nano hardcode → variable)
#   - Binaries rebuilt

set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "${SCRIPT_DIR}")"
RESULTS_DIR="${BASE_DIR}/results_ablation/A6_interval"
BIN_DIR="${BASE_DIR}/mgpusim/amd/samples"
LOG_DIR="${RESULTS_DIR}/logs"
PARALLEL=4

mkdir -p "${LOG_DIR}"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "${LOG_DIR}/a6_master.log"; }

log "=== A6: interval (log2NumSubEntry) sweep ==="
log ""

# ------------------------------------------------------------------
# Config
# log2NumSubEntry: 1=2x, 2=4x(default), 3=8x
# ------------------------------------------------------------------
declare -A INTERVAL_MAP
INTERVAL_MAP[1]="2x"
INTERVAL_MAP[2]="4x"
INTERVAL_MAP[3]="8x"
LOG2_LIST=(1 2 3)

WORKLOADS=("matrixmultiplication" "pagerank")
declare -A WORKLOAD_ARGS
WORKLOAD_ARGS["matrixmultiplication"]="-x=1400 -y=1400 -z=1400"
WORKLOAD_ARGS["pagerank"]="-node=16384 -sparsity=0.005 -iterations=4"

GPU_ARGS="-unified-gpus=1,2,3,4,5"
COMMON_ARGS="-timing -use-unified-memory -coherence-directory=SuperDirectory -log2-page-size=12 -report-all"

# ------------------------------------------------------------------
# Pre-flight
# ------------------------------------------------------------------
log "=== Pre-flight ==="
for wl in "${WORKLOADS[@]}"; do
    BIN="${BIN_DIR}/${wl}/${wl}"
    [ -f "${BIN}" ] || { log "[ERROR] Binary missing: ${BIN}"; exit 1; }
done
log "  [OK] Binaries found"
log ""

# Region size reference (numBanks=5 default):
# log2=1 (2x):  1KB, 512B, 256B, 128B, 64B
# log2=2 (4x):  16KB, 4KB, 1KB, 256B, 64B   <- default
# log2=3 (8x):  256KB, 32KB, 4KB, 512B, 64B

PIDS=()
RUNNING=0

run_one() {
    local wl="$1"
    local log2="$2"
    local label="${INTERVAL_MAP[${log2}]}"
    local out_dir="${RESULTS_DIR}/${label}"
    mkdir -p "${out_dir}/text" "${out_dir}/sql" "${out_dir}/events"

    local bin="${BIN_DIR}/${wl}/${wl}"
    local event_path="${out_dir}/events/${wl}_events.parquet"
    local text_out="${out_dir}/text/${wl}_${label}.txt"
    local sql_out="${out_dir}/sql/${wl}_${label}.sqlite3"

    log "  START: ${wl} interval=${label} (log2=${log2})"
    (
        cd "${BIN_DIR}/${wl}" || exit 1
        export EVENT_LOG_PATH="${event_path}"
        # shellcheck disable=SC2086
        "${bin}" \
            ${COMMON_ARGS} \
            ${GPU_ARGS} \
            ${WORKLOAD_ARGS[${wl}]} \
            -sd-log2-sub-entry="${log2}" \
            > "${text_out}" 2>&1
        STATUS=$?
        mv akita_sim_*.sqlite3 "${sql_out}" 2>/dev/null
        if [ ${STATUS} -eq 0 ]; then
            log "  DONE:  ${wl} interval=${label}"
        else
            log "  FAIL:  ${wl} interval=${label} (exit ${STATUS})"
        fi
    ) &
    PIDS+=($!)
}

log "=== Running A6 ==="
for log2 in "${LOG2_LIST[@]}"; do
    for wl in "${WORKLOADS[@]}"; do
        run_one "${wl}" "${log2}"
        RUNNING=$(( RUNNING + 1 ))
        if [ "${RUNNING}" -ge "${PARALLEL}" ]; then
            wait "${PIDS[0]}"
            PIDS=("${PIDS[@]:1}")
            RUNNING=$(( RUNNING - 1 ))
        fi
    done
done
for pid in "${PIDS[@]}"; do wait "${pid}"; done

log ""
log "=== A6 Summary ==="
for log2 in "${LOG2_LIST[@]}"; do
    label="${INTERVAL_MAP[${log2}]}"
    for wl in "${WORKLOADS[@]}"; do
        f="${RESULTS_DIR}/${label}/text/${wl}_${label}.txt"
        if [ -f "${f}" ]; then
            kt=$(grep -m1 "kernel_time\|KernelTime" "${f}" 2>/dev/null | head -1)
            log "  ${label} ${wl}: ${kt:-[no kernel_time]}"
        else
            log "  ${label} ${wl}: MISSING"
        fi
    done
done
log "Done."
