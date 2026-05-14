#!/bin/bash

MAX_PARALLEL=4

trap 'echo "중단 중..."; kill 0; exit 1' INT TERM

run_bg() {
    local config_name=$1
    local script_path=$2
    echo "  [${config_name}] 실행 중..."
    bash "${script_path}" &
    while [ "$(jobs -rp | wc -l)" -ge "${MAX_PARALLEL}" ]; do
        wait -n 2>/dev/null || wait
    done
}

echo "=== [im2col] 시작 ==="
run_bg "superdirectory" "/root/mgpusim_home/mgpusim/amd/samples/im2col/superdirectory/run_im2col_superdirectory.sh"
run_bg "REC_default" "/root/mgpusim_home/mgpusim/amd/samples/im2col/REC/run_default/run_im2col_REC_default.sh"
run_bg "REC_halfset" "/root/mgpusim_home/mgpusim/amd/samples/im2col/REC/run_halfset/run_im2col_REC_halfset.sh"
run_bg "HMG" "/root/mgpusim_home/mgpusim/amd/samples/im2col/HMG/run_im2col_HMG.sh"
run_bg "CD_0" "/root/mgpusim_home/mgpusim/amd/samples/im2col/CD/run_0/run_im2col_CD_0.sh"
run_bg "CD_1" "/root/mgpusim_home/mgpusim/amd/samples/im2col/CD/run_1/run_im2col_CD_1.sh"
run_bg "CD_2" "/root/mgpusim_home/mgpusim/amd/samples/im2col/CD/run_2/run_im2col_CD_2.sh"
run_bg "CD_4" "/root/mgpusim_home/mgpusim/amd/samples/im2col/CD/run_4/run_im2col_CD_4.sh"
run_bg "CD_6" "/root/mgpusim_home/mgpusim/amd/samples/im2col/CD/run_6/run_im2col_CD_6.sh"
run_bg "CD_8" "/root/mgpusim_home/mgpusim/amd/samples/im2col/CD/run_8/run_im2col_CD_8.sh"
run_bg "CD_ideal" "/root/mgpusim_home/mgpusim/amd/samples/im2col/CD/run_ideal/run_im2col_CD_ideal.sh"
run_bg "coalescability" "/root/mgpusim_home/mgpusim/amd/samples/im2col/coalescability/run_im2col_coalescability.sh"
wait
echo "=== [im2col] 완료 ==="
