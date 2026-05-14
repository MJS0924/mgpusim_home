#!/bin/bash
# S1: GPU count sweep — 4 GPU (default), 8 GPU (attempt), fallback 1/2/4
# Usage: bash run_sensitivity_s1.sh [--try-8gpu]
# No code changes needed.

set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "${SCRIPT_DIR}")"
RESULTS_DIR="${BASE_DIR}/results_ablation/S1_gpu_count"
BIN_DIR="${BASE_DIR}/mgpusim/amd/samples"
LOG_DIR="${RESULTS_DIR}/logs"

mkdir -p "${LOG_DIR}"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "${LOG_DIR}/s1_master.log"; }

TRY_8GPU=false
for arg in "$@"; do [ "${arg}" = "--try-8gpu" ] && TRY_8GPU=true; done

log "=== S1: GPU count sweep ==="
log "  try-8gpu: ${TRY_8GPU}"
log ""

WORKLOADS=("matrixmultiplication" "pagerank")
declare -A WORKLOAD_ARGS
WORKLOAD_ARGS["matrixmultiplication"]="-x=1400 -y=1400 -z=1400"
WORKLOAD_ARGS["pagerank"]="-node=16384 -sparsity=0.005 -iterations=4"

declare -A MODEL_DIRS
MODEL_DIRS["CD"]="CoherenceDirectory"
MODEL_DIRS["HMG"]="HMG"
MODEL_DIRS["SD"]="SuperDirectory"

# GPU ID lists (IDs 1..N for N GPUs; ID 0 = CPU)
declare -A GPU_ID_ARGS
GPU_ID_ARGS[1]="1,2"
GPU_ID_ARGS[2]="1,2,3"
GPU_ID_ARGS[4]="1,2,3,4,5"
GPU_ID_ARGS[8]="1,2,3,4,5,6,7,8,9"

COMMON_ARGS="-timing -use-unified-memory -log2-page-size=12 -report-all"

# Determine GPU list
if ${TRY_8GPU}; then
    GPU_LIST=(1 2 4 8)
else
    GPU_LIST=(1 2 4)
fi

run_one() {
    local wl="$1"
    local model="$2"
    local ngpu="$3"
    local gpu_ids="${GPU_ID_ARGS[${ngpu}]}"
    local dir_flag="${MODEL_DIRS[${model}]}"
    local out_dir="${RESULTS_DIR}/${ngpu}gpu"
    mkdir -p "${out_dir}/text" "${out_dir}/sql" "${out_dir}/events"

    local bin="${BIN_DIR}/${wl}/${wl}"
    local text_out="${out_dir}/text/${wl}_${model}_${ngpu}gpu.txt"
    local sql_out="${out_dir}/sql/${wl}_${model}_${ngpu}gpu.sqlite3"
    local event_path="${out_dir}/events/${wl}_${model}_${ngpu}gpu_events.parquet"

    log "  START: ${wl} ${model} ${ngpu}GPU"
    (
        cd "${BIN_DIR}/${wl}" || exit 1
        export EVENT_LOG_PATH="${event_path}"
        # shellcheck disable=SC2086
        "${bin}" \
            ${COMMON_ARGS} \
            -unified-gpus="${gpu_ids}" \
            -coherence-directory="${dir_flag}" \
            ${WORKLOAD_ARGS[${wl}]} \
            > "${text_out}" 2>&1
        STATUS=$?
        mv akita_sim_*.sqlite3 "${sql_out}" 2>/dev/null
        if [ ${STATUS} -eq 0 ]; then
            log "  DONE:  ${wl} ${model} ${ngpu}GPU"
        else
            log "  FAIL:  ${wl} ${model} ${ngpu}GPU (exit ${STATUS})"
            # If 8 GPU failed, record reason
            if [ "${ngpu}" = "8" ]; then
                log "  [NOTE] 8-GPU run failed. See ${text_out} for details."
                log "         Fallback: use 1/2/4 GPU results only."
            fi
        fi
    ) &
}

PIDS=()
RUNNING=0
PARALLEL=4

for ngpu in "${GPU_LIST[@]}"; do
    log "--- ${ngpu} GPU ---"
    for model in "${!MODEL_DIRS[@]}"; do
        for wl in "${WORKLOADS[@]}"; do
            BIN="${BIN_DIR}/${wl}/${wl}"
            [ -f "${BIN}" ] || { log "[SKIP] Binary missing: ${BIN}"; continue; }
            run_one "${wl}" "${model}" "${ngpu}"
            PIDS+=($!)
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
log "=== S1 Summary ==="
for ngpu in "${GPU_LIST[@]}"; do
    for model in "${!MODEL_DIRS[@]}"; do
        for wl in "${WORKLOADS[@]}"; do
            f="${RESULTS_DIR}/${ngpu}gpu/text/${wl}_${model}_${ngpu}gpu.txt"
            if [ -f "${f}" ]; then
                kt=$(grep -m1 "kernel_time\|KernelTime" "${f}" 2>/dev/null | head -1)
                log "  ${ngpu}GPU ${model} ${wl}: ${kt:-[no kernel_time]}"
            else
                log "  ${ngpu}GPU ${model} ${wl}: MISSING"
            fi
        done
    done
done
log "Done."
