#!/bin/bash
# Safe long-running sweep wrapper for HPCA 2027 motivation experiments
# Usage:
#   nohup bash run_sweep_safe.sh > /tmp/sweep_master.log 2>&1 &
#   echo $! > /tmp/sweep.pid
#
# Runs ./run_all.sh with safety checks, logging, and result summary.

set +e  # 개별 run 실패 시에도 계속

# ---------------------------------------------------------
# Setup
# ---------------------------------------------------------
SCRIPT_DIR="/root/mgpusim_home/script"
RESULTS_DIR="/root/mgpusim_home/results"
LOG_DIR="${RESULTS_DIR}/sweep_log"
mkdir -p ${LOG_DIR}

START_TIME=$(date +%s)
START_STR=$(date '+%Y%m%d_%H%M%S')
LOG_FILE="${LOG_DIR}/sweep_${START_STR}.log"

# Helper for dual output
log() {
    echo "$@" | tee -a ${LOG_FILE}
}

log "================================================================"
log "Sweep started at $(date '+%Y-%m-%d %H:%M:%S')"
log "Log file: ${LOG_FILE}"
log "================================================================"
log ""

# ---------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------
log "=== Pre-flight checks ==="

# Check 1: EVENT_LOG_PATH in superdirectory script
SD_SCRIPT="${SCRIPT_DIR}/../mgpusim/amd/samples/matrixmultiplication/superdirectory/run_matrixmultiplication_superdirectory.sh"
if [ -f "${SD_SCRIPT}" ]; then
    if grep -q "export EVENT_LOG_PATH" ${SD_SCRIPT}; then
        log "  [OK] EVENT_LOG_PATH set in superdirectory script"
    else
        log "  [WARN] EVENT_LOG_PATH not in script. Default /tmp will be used."
        log "       Event logs will overwrite each other across workloads!"
    fi
else
    log "  [ERROR] Superdirectory script not found: ${SD_SCRIPT}"
    log "  Did you run 'python 2_make_shell.py'?"
    exit 1
fi

# Check 2: Binary build time vs Track B-0 fix commit
BINARY_PATH="${SCRIPT_DIR}/../mgpusim/amd/samples/matrixmultiplication/matrixmultiplication"
if [ -f "${BINARY_PATH}" ]; then
    BINARY_TIME=$(stat -c %Y ${BINARY_PATH})
    NOW=$(date +%s)
    AGE_HOURS=$(( (NOW - BINARY_TIME) / 3600 ))
    log "  [INFO] matmul binary age: ${AGE_HOURS} hours"
    
    if [ ${AGE_HOURS} -gt 48 ]; then
        log "  [WARN] Binary older than 48 hours. Consider rebuild if code changed."
    fi
else
    log "  [ERROR] matmul binary not found. Build first."
    exit 1
fi

# Check 3: Disk space (sweep generates ~수백 MB)
AVAIL_GB=$(df -BG /root/mgpusim_home | tail -1 | awk '{print $4}' | tr -d 'G')
log "  [INFO] Available disk space: ${AVAIL_GB} GB"
if [ ${AVAIL_GB} -lt 10 ]; then
    log "  [WARN] Disk space low (<10GB). May fail mid-sweep."
fi

# Check 4: Workload list
log "  [INFO] Will run sweep for workloads:"
ls -d ${SCRIPT_DIR}/../mgpusim/amd/samples/*/superdirectory/ 2>/dev/null | \
    awk -F'/' '{print "          - " $(NF-2)}' | tee -a ${LOG_FILE}

log ""

# ---------------------------------------------------------
# Pre-existing result check
# ---------------------------------------------------------
log "=== Pre-existing results (will be OVERWRITTEN) ==="
for cfg in CD HMG REC superdirectory motivation; do
    count=$(find ${RESULTS_DIR}/${cfg}/rawdata/text -name "*.txt" 2>/dev/null | wc -l)
    if [ ${count} -gt 0 ]; then
        log "  ${cfg}: ${count} existing result files"
    fi
done
log ""
log "  Continuing in 5 seconds (Ctrl-C to abort)..."
sleep 5

# ---------------------------------------------------------
# Main sweep
# ---------------------------------------------------------
log ""
log "================================================================"
log "Starting main sweep"
log "================================================================"
log ""

cd ${SCRIPT_DIR}
bash ./run_all.sh 2>&1 | tee -a ${LOG_FILE}
SWEEP_STATUS=$?

# ---------------------------------------------------------
# Post-sweep summary
# ---------------------------------------------------------
END_TIME=$(date +%s)
ELAPSED=$(( END_TIME - START_TIME ))
ELAPSED_H=$(( ELAPSED / 3600 ))
ELAPSED_M=$(( (ELAPSED % 3600) / 60 ))

log ""
log "================================================================"
log "Sweep completed at $(date '+%Y-%m-%d %H:%M:%S')"
log "Status: ${SWEEP_STATUS}"
log "Elapsed: ${ELAPSED_H}h ${ELAPSED_M}m"
log "================================================================"
log ""

# Output file count per config
log "=== Output file counts ==="
TOTAL_TEXT=0
for cfg in CD HMG REC superdirectory motivation; do
    text_count=$(find ${RESULTS_DIR}/${cfg}/rawdata/text -name "*.txt" 2>/dev/null | wc -l)
    sql_count=$(find ${RESULTS_DIR}/${cfg}/rawdata/sql -name "*.sqlite3" 2>/dev/null | wc -l)
    log "  ${cfg}: ${text_count} text, ${sql_count} sqlite"
    TOTAL_TEXT=$(( TOTAL_TEXT + text_count ))
done

# Event log files (superdirectory only)
event_count=$(find ${RESULTS_DIR}/superdirectory/rawdata/events -name "*.parquet" 2>/dev/null | wc -l)
log "  Event logs (superdirectory): ${event_count} parquet files"

# Coalescability CSV files (motivation only)
csv_count=$(find ${RESULTS_DIR}/motivation/rawdata/csv -name "*.csv" 2>/dev/null | wc -l)
log "  Coalescability CSVs (motivation): ${csv_count} files"

log ""
log "Total text outputs: ${TOTAL_TEXT}"
log ""

# Sanity check on event log
log "=== Event log sanity ==="
EVENT_DIR="${RESULTS_DIR}/superdirectory/rawdata/events"
if [ -d "${EVENT_DIR}" ]; then
    for evt in ${EVENT_DIR}/*.parquet; do
        if [ -f "${evt}" ]; then
            size=$(stat -c %s "${evt}")
            wl=$(basename ${evt} _events.parquet)
            log "  ${wl}: ${size} bytes"
        fi
    done
fi

# Check for any panic/error in logs
log ""
log "=== Error/panic scan ==="
ERROR_COUNT=$(grep -l -i "panic\|error\|fatal" ${RESULTS_DIR}/*/rawdata/text/*.txt 2>/dev/null | wc -l)
if [ ${ERROR_COUNT} -gt 0 ]; then
    log "  [WARN] ${ERROR_COUNT} files contain error/panic. Review:"
    grep -l -i "panic\|error\|fatal" ${RESULTS_DIR}/*/rawdata/text/*.txt 2>/dev/null | head -10 | tee -a ${LOG_FILE}
else
    log "  [OK] No panic/error found in result files"
fi

# Check default path event log (should NOT be used)
log ""
if [ -f "/tmp/superdirectory_events.parquet" ]; then
    log "  [INFO] Default path /tmp/superdirectory_events.parquet exists"
    log "         (last write — may have been overwritten by latest superdirectory run)"
fi

log ""
log "================================================================"
log "DONE. Full log: ${LOG_FILE}"
log "================================================================"
