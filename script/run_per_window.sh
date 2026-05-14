#!/bin/bash
# run_per_window.sh — per-window snapshot sweep for §3.3 R-sweep analysis
#
# Runs matrixmultiplication + pagerank across CD_0..CD_4 + SD.
# Outputs: results/per_window/<workload>/<config>_per_window.csv
#
# Usage: bash run_per_window.sh [--window-inst N] [--dry-run]
#
# Requires: binaries already built under amd/samples/<workload>/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

WINDOW_INST=50000
DRY_RUN=0
MAX_PARALLEL=4

while [[ $# -gt 0 ]]; do
    case "$1" in
        --window-inst) WINDOW_INST="$2"; shift 2 ;;
        --dry-run)     DRY_RUN=1; shift ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

RESULTS_DIR="${REPO_ROOT}/results/per_window"
SAMPLES_DIR="${REPO_ROOT}/amd/samples"

declare -A WL_FLAGS
WL_FLAGS["matrixmultiplication"]="-x=1600 -y=1600 -z=1600"
WL_FLAGS["pagerank"]="-num-nodes=4096"

WORKLOADS=("matrixmultiplication" "pagerank")
CD_INDICES=(0 1 2 3 4)

run_one() {
    local workload=$1
    local config=$2      # e.g. "CD_0", "SD"
    local extra_flags=$3 # coherence flags

    local out_dir="${RESULTS_DIR}/${workload}"
    mkdir -p "${out_dir}"

    local csv_out="${out_dir}/${workload}_${config}_per_window.csv"
    local log_out="${out_dir}/${workload}_${config}_per_window.log"
    local binary="${SAMPLES_DIR}/${workload}/${workload}"

    if [[ ! -x "${binary}" ]]; then
        echo "[ERROR] binary not found: ${binary}" >&2
        return 1
    fi

    local cmd="${binary} \
        -timing \
        -unified-gpus=1,2,3,4,5 \
        -use-unified-memory \
        -log2-page-size=12 \
        ${extra_flags} \
        ${WL_FLAGS[${workload}]} \
        -per-window-snapshot \
        -window-instructions=${WINDOW_INST} \
        -per-window-output=${csv_out}"

    echo "[per-window] ${workload} ${config} → ${csv_out}"
    if [[ "${DRY_RUN}" -eq 1 ]]; then
        echo "  DRY-RUN: ${cmd}"
        return 0
    fi

    # Run in a temp dir so akita sqlite files don't collide
    local tmp_dir
    tmp_dir=$(mktemp -d)
    pushd "${tmp_dir}" > /dev/null
    eval "${cmd}" > "${log_out}" 2>&1
    popd > /dev/null
    rm -rf "${tmp_dir}"
    echo "[per-window] done: ${workload} ${config}"
}

trap 'echo "Interrupted — killing children"; kill 0; exit 1' INT TERM

job_count() { jobs -rp | wc -l; }

submit() {
    run_one "$@" &
    while [[ "$(job_count)" -ge "${MAX_PARALLEL}" ]]; do
        wait -n 2>/dev/null || wait
    done
}

echo "=== per-window sweep: window=${WINDOW_INST} inst, workloads=${WORKLOADS[*]} ==="

for wl in "${WORKLOADS[@]}"; do
    # CD_0..CD_4  (-coherence-unit-size = index, -coherence-directory=CoherenceDirectory)
    for i in "${CD_INDICES[@]}"; do
        submit "${wl}" "CD_${i}" \
            "-coherence-directory=CoherenceDirectory -coherence-unit-size=${i}"
    done

    # SuperDirectory
    submit "${wl}" "SD" \
        "-coherence-directory=SuperDirectory"
done

wait
echo "=== per-window sweep complete ==="
echo "Output directory: ${RESULTS_DIR}"
