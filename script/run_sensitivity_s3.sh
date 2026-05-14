#!/bin/bash
# S3: Directory capacity sweep — 256KB / 512KB(default) / 1MB / 2MB
# Usage: bash run_sensitivity_s3.sh
#
# Prerequisites: -sd-byte-size CLI flag added and binaries rebuilt

set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "${SCRIPT_DIR}")"
RESULTS_DIR="${BASE_DIR}/results_ablation/S3_capacity"
BIN_DIR="${BASE_DIR}/mgpusim/amd/samples"
LOG_DIR="${RESULTS_DIR}/logs"
PARALLEL=4

mkdir -p "${LOG_DIR}"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "${LOG_DIR}/s3_master.log"; }

log "=== S3: Directory capacity sweep ==="
log ""

# Capacities in bytes
declare -A CAP_LABELS
CAP_LABELS[262144]="256k"
CAP_LABELS[524288]="512k"
CAP_LABELS[1048576]="1m"
CAP_LABELS[2097152]="2m"
CAP_BYTES=(262144 524288 1048576 2097152)

WORKLOADS=("matrixmultiplication" "pagerank")
declare -A WORKLOAD_ARGS
WORKLOAD_ARGS["matrixmultiplication"]="-x=1400 -y=1400 -z=1400"
WORKLOAD_ARGS["pagerank"]="-node=16384 -sparsity=0.005 -iterations=4"

declare -A MODEL_DIRS
MODEL_DIRS["HMG"]="HMG"
MODEL_DIRS["SD"]="SuperDirectory"

GPU_ARGS="-unified-gpus=1,2,3,4,5"
COMMON_ARGS="-timing -use-unified-memory -log2-page-size=12 -report-all"

PIDS=()
RUNNING=0

run_one() {
    local wl="$1"
    local model="$2"
    local cap="$3"
    local label="${CAP_LABELS[${cap}]}"
    local dir_flag="${MODEL_DIRS[${model}]}"
    local out_dir="${RESULTS_DIR}/${label}"
    mkdir -p "${out_dir}/text" "${out_dir}/sql" "${out_dir}/events"

    local bin="${BIN_DIR}/${wl}/${wl}"
    local text_out="${out_dir}/text/${wl}_${model}_${label}.txt"
    local sql_out="${out_dir}/sql/${wl}_${model}_${label}.sqlite3"
    local event_path="${out_dir}/events/${wl}_${model}_${label}_events.parquet"

    log "  START: ${wl} ${model} cap=${label}"
    (
        cd "${BIN_DIR}/${wl}" || exit 1
        export EVENT_LOG_PATH="${event_path}"
        EXTRA_ARGS=""
        # Only SD needs -sd-byte-size; HMG ignores it (kept for uniformity)
        # shellcheck disable=SC2086
        "${bin}" \
            ${COMMON_ARGS} \
            ${GPU_ARGS} \
            -coherence-directory="${dir_flag}" \
            ${WORKLOAD_ARGS[${wl}]} \
            -sd-byte-size="${cap}" \
            > "${text_out}" 2>&1
        STATUS=$?
        mv akita_sim_*.sqlite3 "${sql_out}" 2>/dev/null
        [ ${STATUS} -eq 0 ] && log "  DONE:  ${wl} ${model} ${label}" || log "  FAIL:  ${wl} ${model} ${label} (exit ${STATUS})"
    ) &
    PIDS+=($!)
}

log "=== Running S3 ==="
for cap in "${CAP_BYTES[@]}"; do
    for model in "${!MODEL_DIRS[@]}"; do
        for wl in "${WORKLOADS[@]}"; do
            BIN="${BIN_DIR}/${wl}/${wl}"
            [ -f "${BIN}" ] || { log "[SKIP] ${BIN} missing"; continue; }
            run_one "${wl}" "${model}" "${cap}"
            RUNNING=$(( RUNNING + 1 ))
            if [ "${RUNNING}" -ge "${PARALLEL}" ]; then
                wait "${PIDS[0]}"
                PIDS=("${PIDS[@]:1}")
                RUNNING=$(( RUNNING - 1 ))
            fi
        done
    done
done
for pid in "${PIDS[@]}"; do wait "${pid}"; done

log ""
log "=== S3 Summary ==="
for cap in "${CAP_BYTES[@]}"; do
    label="${CAP_LABELS[${cap}]}"
    for model in "${!MODEL_DIRS[@]}"; do
        for wl in "${WORKLOADS[@]}"; do
            f="${RESULTS_DIR}/${label}/text/${wl}_${model}_${label}.txt"
            if [ -f "${f}" ]; then
                kt=$(grep -m1 "kernel_time\|KernelTime" "${f}" 2>/dev/null | head -1)
                log "  ${label} ${model} ${wl}: ${kt:-[no kernel_time]}"
            else
                log "  ${label} ${model} ${wl}: MISSING"
            fi
        done
    done
done
log "Done."
