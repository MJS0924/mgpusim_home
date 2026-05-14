#!/bin/bash
# h4_extra_variants_4x_launch.sh — relu/spmv/conv2d × {HMG, REC, REC_halfset, CD_ideal}
# at 4× input. Existing per_window/SD/CD_X variants already done.
# MAX_PARALLEL=4 across 12 sims.

set -uo pipefail

MAX_PARALLEL=4
LOG_DIR=/root/mgpusim_home/results/.h4_extra_variants_logs
mkdir -p "$LOG_DIR"
LAUNCH_LOG="$LOG_DIR/launch.log"
echo "[$(date '+%F %T')] === extra-variants 4× launch (max=$MAX_PARALLEL) ===" > "$LAUNCH_LOG"

trap 'echo "[$(date "+%F %T")] received TERM/INT — killing children" | tee -a "$LAUNCH_LOG"; kill 0; exit 1' INT TERM

# Per-workload 4× input flags
INPUT_relu="-length=15360000"
INPUT_spmv="-dim=98304 -sparsity=0.000871"
INPUT_conv2d="-N=4 -C=3 -H=165 -W=165 -output-channel=3 -kernel-height=7 -kernel-width=7"

run_variant_bg() {
    local wl=$1     # relu / spmv / conv2d
    local variant=$2  # HMG / REC / REC_halfset / CD_ideal

    local bin=/root/mgpusim_home/mgpusim/amd/samples/${wl}/${wl}
    local input_flags
    case "$wl" in
        relu)   input_flags="$INPUT_relu" ;;
        spmv)   input_flags="$INPUT_spmv" ;;
        conv2d) input_flags="$INPUT_conv2d" ;;
        *) echo "unknown wl $wl"; return 1 ;;
    esac

    local logf="$LOG_DIR/${wl}_${variant}.log"
    local cwd_dir
    local cflag_args
    local sql_dest
    local txt_dest

    case "$variant" in
        HMG)
            cwd_dir=/root/mgpusim_home/mgpusim/amd/samples/${wl}/HMG
            cflag_args="-coherence-directory=HMG -coherence-unit-size=2"
            sql_dest=/root/mgpusim_home/results/HMG/rawdata/sql/${wl}_HMG.sqlite3
            txt_dest=/root/mgpusim_home/results/HMG/rawdata/text/${wl}_HMG.txt
            ;;
        REC)
            cwd_dir=/root/mgpusim_home/mgpusim/amd/samples/${wl}/REC/run_default
            cflag_args="-coherence-directory=REC"
            sql_dest=/root/mgpusim_home/results/REC/rawdata/sql/${wl}_REC.sqlite3
            txt_dest=/root/mgpusim_home/results/REC/rawdata/text/${wl}_REC.txt
            ;;
        REC_halfset)
            cwd_dir=/root/mgpusim_home/mgpusim/amd/samples/${wl}/REC/run_halfset
            cflag_args="-coherence-directory=REC -rec-half-set"
            sql_dest=/root/mgpusim_home/results/REC/rawdata/sql/${wl}_REC_halfset.sqlite3
            txt_dest=/root/mgpusim_home/results/REC/rawdata/text/${wl}_REC_halfset.txt
            ;;
        CD_ideal)
            cwd_dir=/root/mgpusim_home/mgpusim/amd/samples/${wl}/CD/run_ideal
            cflag_args="-coherence-directory=CoherenceDirectory -coherence-unit-size=0 -ideal-directory=true"
            sql_dest=/root/mgpusim_home/results/CD/rawdata/sql/${wl}_ideal.sqlite3
            txt_dest=/root/mgpusim_home/results/CD/rawdata/text/${wl}_ideal.txt
            ;;
    esac

    mkdir -p "$cwd_dir"
    mkdir -p "$(dirname "$sql_dest")" "$(dirname "$txt_dest")"
    # Clean any stale akita_sim sqlite in CWD to avoid mv collisions
    rm -f "$cwd_dir"/akita_sim_*.sqlite3 2>/dev/null

    echo "[$(date '+%F %T')] Start ${wl}/${variant}" | tee -a "$LAUNCH_LOG"
    (
        cd "$cwd_dir"
        "$bin" \
            -timing \
            -unified-gpus=1,2,3,4,5 \
            -use-unified-memory \
            $cflag_args \
            -log2-page-size=12 \
            $input_flags \
            -report-all > "$txt_dest" 2>"$logf"
        rc=$?
        # move generated sqlite to standard location
        sql_src=$(ls -t akita_sim_*.sqlite3 2>/dev/null | head -1)
        if [ -n "$sql_src" ]; then
            mv "$sql_src" "$sql_dest"
        fi
        # CD_ideal also copies to motivation path (per existing convention)
        if [ "$variant" = "CD_ideal" ]; then
            cp "$sql_dest" /root/mgpusim_home/results/motivation/rawdata/sql/${wl}_motivation.sqlite3 2>/dev/null
        fi
        echo "[$(date '+%F %T')] Done  ${wl}/${variant}  (exit=$rc)" >> "$LAUNCH_LOG"
    ) &

    while [ "$(jobs -rp | wc -l)" -ge "$MAX_PARALLEL" ]; do
        wait -n 2>/dev/null || wait
    done
}

# 3 workloads × 4 variants = 12 sims, max 4 in flight
for wl in conv2d relu spmv; do
    for variant in CD_ideal HMG REC REC_halfset; do
        run_variant_bg "$wl" "$variant"
    done
done
wait
echo "[$(date '+%F %T')] === ALL extra variants complete ===" | tee -a "$LAUNCH_LOG"
