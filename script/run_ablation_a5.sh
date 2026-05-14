#!/bin/bash
# A5: numBanks sweep (2~8)
# Usage: bash run_ablation_a5.sh
#
# Prerequisites:
#   - WithNumBanks() implemented in superdirectory builder
#   - -sd-num-banks CLI flag added to runner/flag.go
#   - Binaries rebuilt with ablation flags
#
# Note: does NOT touch the main sweep results directory.

set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "${SCRIPT_DIR}")"
RESULTS_DIR="${BASE_DIR}/results_ablation/A5_nbank"
BIN_DIR="${BASE_DIR}/mgpusim/amd/samples"
LOG_DIR="${RESULTS_DIR}/logs"
PARALLEL=4

mkdir -p "${LOG_DIR}"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "${LOG_DIR}/a5_master.log"; }

log "=== A5: numBanks sweep (2~8) ==="
log "Results: ${RESULTS_DIR}"
log ""

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
NUM_BANKS_LIST=(2 3 4 5 6 7 8)
WORKLOADS=("matrixmultiplication" "pagerank")

MATMUL_ARGS="-x=1400 -y=1400 -z=1400"
PAGERANK_ARGS="-node=16384 -sparsity=0.005 -iterations=4"
GPU_ARGS="-unified-gpus=1,2,3,4,5"
COMMON_ARGS="-timing -use-unified-memory -coherence-directory=SuperDirectory -log2-page-size=12 -report-all"

declare -A WORKLOAD_ARGS
WORKLOAD_ARGS["matrixmultiplication"]="${MATMUL_ARGS}"
WORKLOAD_ARGS["pagerank"]="${PAGERANK_ARGS}"

# ------------------------------------------------------------------
# Pre-flight
# ------------------------------------------------------------------
log "=== Pre-flight checks ==="
for wl in "${WORKLOADS[@]}"; do
    BIN="${BIN_DIR}/${wl}/${wl}"
    if [ ! -f "${BIN}" ]; then
        log "  [ERROR] Binary not found: ${BIN}"
        log "  Rebuild after implementing WithNumBanks and -sd-num-banks flag."
        exit 1
    fi
    # Check that binary accepts -sd-num-banks flag
    if ! "${BIN}" -sd-num-banks=5 -h 2>&1 | grep -q "sd-num-banks\|flag provided"; then
        log "  [WARN] ${wl} binary may not support -sd-num-banks. Verify build."
    fi
done

log "  [OK] Binaries found"
log ""

# ------------------------------------------------------------------
# Build run list
# ------------------------------------------------------------------
PIDS=()
RUNNING=0

run_one() {
    local wl="$1"
    local nb="$2"
    local out_dir="${RESULTS_DIR}/n=${nb}"
    mkdir -p "${out_dir}/text" "${out_dir}/sql" "${out_dir}/events"

    local bin="${BIN_DIR}/${wl}/${wl}"
    local wl_args="${WORKLOAD_ARGS[${wl}]}"
    local event_path="${out_dir}/events/${wl}_events.parquet"
    local text_out="${out_dir}/text/${wl}_nb${nb}.txt"
    local sql_out="${out_dir}/sql/${wl}_nb${nb}.sqlite3"

    log "  START: ${wl} numBanks=${nb}"

    (
        cd "${BIN_DIR}/${wl}" || exit 1
        export EVENT_LOG_PATH="${event_path}"
        # shellcheck disable=SC2086
        "${bin}" \
            ${COMMON_ARGS} \
            ${GPU_ARGS} \
            ${wl_args} \
            -sd-num-banks="${nb}" \
            > "${text_out}" 2>&1
        STATUS=$?
        mv akita_sim_*.sqlite3 "${sql_out}" 2>/dev/null
        if [ ${STATUS} -eq 0 ]; then
            log "  DONE:  ${wl} numBanks=${nb}"
        else
            log "  FAIL:  ${wl} numBanks=${nb} (exit ${STATUS})"
        fi
    ) &
    PIDS+=($!)
}

# ------------------------------------------------------------------
# Main loop (parallel=4)
# ------------------------------------------------------------------
log "=== Running A5 (numBanks sweep) ==="
log "  Workloads: ${WORKLOADS[*]}"
log "  numBanks: ${NUM_BANKS_LIST[*]}"
log "  Parallel: ${PARALLEL}"
log ""

for nb in "${NUM_BANKS_LIST[@]}"; do
    for wl in "${WORKLOADS[@]}"; do
        run_one "${wl}" "${nb}"
        RUNNING=$(( RUNNING + 1 ))

        if [ "${RUNNING}" -ge "${PARALLEL}" ]; then
            wait "${PIDS[0]}"
            PIDS=("${PIDS[@]:1}")
            RUNNING=$(( RUNNING - 1 ))
        fi
    done
done

# wait remaining
for pid in "${PIDS[@]}"; do
    wait "${pid}"
done

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
log ""
log "=== A5 Summary ==="
for nb in "${NUM_BANKS_LIST[@]}"; do
    for wl in "${WORKLOADS[@]}"; do
        f="${RESULTS_DIR}/n=${nb}/text/${wl}_nb${nb}.txt"
        if [ -f "${f}" ]; then
            kt=$(grep -m1 "kernel_time\|KernelTime\|kernel time" "${f}" 2>/dev/null | head -1)
            log "  n=${nb} ${wl}: ${kt:-[no kernel_time found]}"
        else
            log "  n=${nb} ${wl}: MISSING"
        fi
    done
done

log ""
log "Results: ${RESULTS_DIR}"
log "Done."
