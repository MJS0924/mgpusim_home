#!/bin/bash
# S2: Workload size sweep — matmul N = 500/800/1000/1400/1700/2048
# Demonstrates existing-solution breakdown at large N.
# Usage: bash run_sensitivity_s2.sh
#
# No code changes needed: uses existing -x/-y/-z flags.
# Models: CD (best static), HMG, SuperDirectory

set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "${SCRIPT_DIR}")"
RESULTS_DIR="${BASE_DIR}/results_ablation/S2_size"
BIN_DIR="${BASE_DIR}/mgpusim/amd/samples/matrixmultiplication"
LOG_DIR="${RESULTS_DIR}/logs"
PARALLEL=3   # 3 models in parallel per size; run sizes sequentially

mkdir -p "${LOG_DIR}"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "${LOG_DIR}/s2_master.log"; }

log "=== S2: Workload size sweep (matmul) ==="
log ""

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
SIZES=(500 800 1000 1400 1700 2048)

# Models: coherence-directory flag value
declare -A MODEL_DIR
MODEL_DIR["CD"]="CoherenceDirectory"        # static CD (default)
MODEL_DIR["HMG"]="HMG"
MODEL_DIR["SD"]="SuperDirectory"

GPU_ARGS="-unified-gpus=1,2,3,4,5"
COMMON_ARGS="-timing -use-unified-memory -log2-page-size=12 -report-all"
BIN="${BIN_DIR}/matrixmultiplication"

# ------------------------------------------------------------------
# Pre-flight
# ------------------------------------------------------------------
log "=== Pre-flight ==="
[ -f "${BIN}" ] || { log "[ERROR] Binary not found: ${BIN}"; exit 1; }
log "  [OK] Binary found: ${BIN}"

AVAIL_GB=$(df -BG "${BASE_DIR}" | tail -1 | awk '{print $4}' | tr -d 'G')
log "  [INFO] Disk available: ${AVAIL_GB} GB"
[ "${AVAIL_GB}" -lt 20 ] && log "  [WARN] Low disk space. N=2048 may be large."
log ""

# ------------------------------------------------------------------
# Run
# ------------------------------------------------------------------
log "=== Running S2 ==="
log "  Sizes: ${SIZES[*]}"
log "  Models: ${!MODEL_DIR[*]}"
log ""

for N in "${SIZES[@]}"; do
    log "--- Size N=${N} ---"
    PIDS=()

    for model in "${!MODEL_DIR[@]}"; do
        dir_flag="${MODEL_DIR[${model}]}"
        out_dir="${RESULTS_DIR}/n=${N}"
        mkdir -p "${out_dir}/text" "${out_dir}/sql" "${out_dir}/events"

        text_out="${out_dir}/text/matmul_n${N}_${model}.txt"
        sql_out="${out_dir}/sql/matmul_n${N}_${model}.sqlite3"
        event_path="${out_dir}/events/matmul_n${N}_${model}_events.parquet"

        log "  START: N=${N} model=${model}"
        (
            cd "${BIN_DIR}" || exit 1
            export EVENT_LOG_PATH="${event_path}"
            # shellcheck disable=SC2086
            "${BIN}" \
                ${COMMON_ARGS} \
                ${GPU_ARGS} \
                -coherence-directory="${dir_flag}" \
                -x="${N}" -y="${N}" -z="${N}" \
                > "${text_out}" 2>&1
            STATUS=$?
            mv akita_sim_*.sqlite3 "${sql_out}" 2>/dev/null
            if [ ${STATUS} -eq 0 ]; then
                log "  DONE:  N=${N} model=${model}"
            else
                log "  FAIL:  N=${N} model=${model} (exit ${STATUS})"
            fi
        ) &
        PIDS+=($!)
    done

    # Wait for all models at this size before moving to next size
    for pid in "${PIDS[@]}"; do wait "${pid}"; done
    log "  All models done for N=${N}"
    log ""
done

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
log "=== S2 Summary ==="
for N in "${SIZES[@]}"; do
    for model in "${!MODEL_DIR[@]}"; do
        f="${RESULTS_DIR}/n=${N}/text/matmul_n${N}_${model}.txt"
        if [ -f "${f}" ]; then
            kt=$(grep -m1 "kernel_time\|KernelTime" "${f}" 2>/dev/null | head -1)
            log "  N=${N} ${model}: ${kt:-[no kernel_time]}"
        else
            log "  N=${N} ${model}: MISSING"
        fi
    done
done

log ""
log "Results: ${RESULTS_DIR}"
log "Done."
