#!/bin/bash
# A0/A1/A2: RSB/CBF disable sweep
#   A0: no RSB + no CBF (combined)
#   A1: no RSB only
#   A2: no CBF only
# Usage: bash run_ablation_a0_a1_a2.sh [a0|a1|a2|all]
#
# Prerequisites:
#   - WithDisableRSB / WithDisableCBF implemented
#   - -sd-disable-rsb / -sd-disable-cbf CLI flags added
#   - Binaries rebuilt

set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "${SCRIPT_DIR}")"
BIN_DIR="${BASE_DIR}/mgpusim/amd/samples"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

WORKLOADS=("matrixmultiplication" "pagerank")
declare -A WORKLOAD_ARGS
WORKLOAD_ARGS["matrixmultiplication"]="-x=1400 -y=1400 -z=1400"
WORKLOAD_ARGS["pagerank"]="-node=16384 -sparsity=0.005 -iterations=4"

GPU_ARGS="-unified-gpus=1,2,3,4,5"
COMMON_ARGS="-timing -use-unified-memory -coherence-directory=SuperDirectory -log2-page-size=12 -report-all"

TARGET="${1:-all}"

run_study() {
    local study="$1"     # A0, A1, A2
    local rsb_flag="$2"  # true / false
    local cbf_flag="$3"  # true / false

    local out_base="${BASE_DIR}/results_ablation/${study}_no_rsb_cbf"
    [ "${study}" = "A1" ] && out_base="${BASE_DIR}/results_ablation/A1_no_rsb"
    [ "${study}" = "A2" ] && out_base="${BASE_DIR}/results_ablation/A2_no_cbf"

    mkdir -p "${out_base}/text" "${out_base}/sql" "${out_base}/events" "${out_base}/logs"
    log "=== ${study}: disable_rsb=${rsb_flag} disable_cbf=${cbf_flag} ==="

    PIDS=()
    for wl in "${WORKLOADS[@]}"; do
        BIN="${BIN_DIR}/${wl}/${wl}"
        [ -f "${BIN}" ] || { log "[ERROR] Missing binary: ${BIN}"; continue; }

        text_out="${out_base}/text/${wl}_${study,,}.txt"
        sql_out="${out_base}/sql/${wl}_${study,,}.sqlite3"
        event_path="${out_base}/events/${wl}_${study,,}_events.parquet"

        log "  START: ${wl} (${study})"
        (
            cd "${BIN_DIR}/${wl}" || exit 1
            export EVENT_LOG_PATH="${event_path}"
            # shellcheck disable=SC2086
            "${BIN}" \
                ${COMMON_ARGS} \
                ${GPU_ARGS} \
                ${WORKLOAD_ARGS[${wl}]} \
                -sd-disable-rsb="${rsb_flag}" \
                -sd-disable-cbf="${cbf_flag}" \
                > "${text_out}" 2>&1
            STATUS=$?
            mv akita_sim_*.sqlite3 "${sql_out}" 2>/dev/null
            [ ${STATUS} -eq 0 ] && log "  DONE:  ${wl} ${study}" || log "  FAIL:  ${wl} ${study} (exit ${STATUS})"
        ) &
        PIDS+=($!)
    done
    for pid in "${PIDS[@]}"; do wait "${pid}"; done
    log ""
}

case "${TARGET}" in
    a0|A0|all) run_study "A0" "true"  "true"  ;;&
    a1|A1|all) run_study "A1" "true"  "false" ;;&
    a2|A2|all) run_study "A2" "false" "true"  ;;
esac

log "Done. Compare against baseline from main sweep results."
