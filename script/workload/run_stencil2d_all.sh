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

echo "=== [stencil2d] 시작 ==="
run_bg "superdirectory" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/superdirectory/run_stencil2d_superdirectory.sh"
run_bg "REC_default" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/REC/run_default/run_stencil2d_REC_default.sh"
run_bg "REC_halfset" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/REC/run_halfset/run_stencil2d_REC_halfset.sh"
run_bg "HMG" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/HMG/run_stencil2d_HMG.sh"
run_bg "CD_0" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/CD/run_0/run_stencil2d_CD_0.sh"
run_bg "CD_1" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/CD/run_1/run_stencil2d_CD_1.sh"
run_bg "CD_2" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/CD/run_2/run_stencil2d_CD_2.sh"
run_bg "CD_4" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/CD/run_4/run_stencil2d_CD_4.sh"
run_bg "CD_6" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/CD/run_6/run_stencil2d_CD_6.sh"
run_bg "CD_8" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/CD/run_8/run_stencil2d_CD_8.sh"
run_bg "CD_ideal" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/CD/run_ideal/run_stencil2d_CD_ideal.sh"
run_bg "coalescability" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/coalescability/run_stencil2d_coalescability.sh"
wait
echo "=== [stencil2d] 완료 ==="
