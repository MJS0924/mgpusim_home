#!/bin/bash
# P1+P2 wrapper: A5 (numBanks) + S2 (workload size) + A0 (no RSB+CBF)
# Runs in priority order: A5 → S2 → A0
#
# Usage:
#   nohup bash run_ablation_p1p2.sh > /tmp/ablation_p1p2.log 2>&1 &
#   echo $! > /tmp/ablation_p1p2.pid
#
# Total estimated time: ~38 hours
# Prerequisite check list (see ablation_planning/builder_options_plan.md):
#   [P1] A5: WithNumBanks + -sd-num-banks flag + binary rebuild
#   [P1] S2: no code change needed
#   [P2] A0: WithDisableRSB + WithDisableCBF + flags + binary rebuild

set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/tmp/ablation_p1p2_master.log"
START_TIME=$(date +%s)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

log "================================================================"
log "P1+P2 Ablation sweep started"
log "Scripts: ${SCRIPT_DIR}"
log "Log: ${LOG_FILE}"
log "================================================================"
log ""

# ------------------------------------------------------------------
# Helper: run a study script and report elapsed time
# ------------------------------------------------------------------
run_study() {
    local name="$1"
    local script="$2"
    shift 2
    local t0
    t0=$(date +%s)
    log ">>> START ${name}"
    bash "${script}" "$@" 2>&1 | tee -a "${LOG_FILE}"
    local status=$?
    local elapsed=$(( $(date +%s) - t0 ))
    log ">>> END ${name} — elapsed ${elapsed}s (status ${status})"
    log ""
}

# ------------------------------------------------------------------
# Pre-flight: check all required binaries and flags exist
# ------------------------------------------------------------------
BASE_DIR="$(dirname "${SCRIPT_DIR}")"
BIN_DIR="${BASE_DIR}/mgpusim/amd/samples"
PASS=true

log "=== Pre-flight ==="
for wl in matrixmultiplication pagerank; do
    BIN="${BIN_DIR}/${wl}/${wl}"
    if [ ! -f "${BIN}" ]; then
        log "  [ERROR] Binary missing: ${BIN}"
        PASS=false
    else
        log "  [OK]    ${BIN}"
    fi
done

# Check A5 flag availability (sd-num-banks)
if "${BIN_DIR}/matrixmultiplication/matrixmultiplication" --help 2>&1 | grep -q "sd-num-banks"; then
    log "  [OK]    -sd-num-banks flag available (A5 ready)"
    A5_READY=true
else
    log "  [WARN]  -sd-num-banks flag NOT found — A5 will be skipped"
    log "          Implement WithNumBanks + plumbing, then rebuild."
    A5_READY=false
fi

# Check A0 flags (sd-disable-rsb, sd-disable-cbf)
if "${BIN_DIR}/matrixmultiplication/matrixmultiplication" --help 2>&1 | grep -q "sd-disable-rsb"; then
    log "  [OK]    -sd-disable-rsb/-sd-disable-cbf available (A0 ready)"
    A0_READY=true
else
    log "  [WARN]  RSB/CBF disable flags NOT found — A0 will be skipped"
    log "          Implement WithDisableRSB/CBF + plumbing, then rebuild."
    A0_READY=false
fi

if ! ${PASS}; then
    log "[ERROR] Pre-flight failed. Aborting."
    exit 1
fi
log ""

# ------------------------------------------------------------------
# Phase 1: A5 — numBanks sweep (~10h)
# ------------------------------------------------------------------
if ${A5_READY}; then
    run_study "A5 (numBanks 2~8)" "${SCRIPT_DIR}/run_ablation_a5.sh"
else
    log ">>> SKIP A5 (prerequisite not met)"
fi

# ------------------------------------------------------------------
# Phase 2: S2 — Workload size sweep (~25h)
# ------------------------------------------------------------------
run_study "S2 (matmul size N=500~2048)" "${SCRIPT_DIR}/run_sensitivity_s2.sh"

# ------------------------------------------------------------------
# Phase 3: A0 — No RSB + No CBF (~3h)
# ------------------------------------------------------------------
if ${A0_READY}; then
    run_study "A0 (no RSB + no CBF)" "${SCRIPT_DIR}/run_ablation_a0_a1_a2.sh" "a0"
else
    log ">>> SKIP A0 (prerequisite not met)"
fi

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
ELAPSED=$(( $(date +%s) - START_TIME ))
ELAPSED_H=$(( ELAPSED / 3600 ))
ELAPSED_M=$(( (ELAPSED % 3600) / 60 ))

log "================================================================"
log "P1+P2 sweep complete"
log "Elapsed: ${ELAPSED_H}h ${ELAPSED_M}m"
log "Results: ${BASE_DIR}/results_ablation/"
log "================================================================"
