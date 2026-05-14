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

echo "=== [matrixtranspose] 시작 ==="
run_bg "superdirectory" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/superdirectory/run_matrixtranspose_superdirectory.sh"
run_bg "REC_default" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/REC/run_default/run_matrixtranspose_REC_default.sh"
run_bg "REC_halfset" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/REC/run_halfset/run_matrixtranspose_REC_halfset.sh"
run_bg "HMG" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/HMG/run_matrixtranspose_HMG.sh"
run_bg "CD_0" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/CD/run_0/run_matrixtranspose_CD_0.sh"
run_bg "CD_1" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/CD/run_1/run_matrixtranspose_CD_1.sh"
run_bg "CD_2" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/CD/run_2/run_matrixtranspose_CD_2.sh"
run_bg "CD_4" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/CD/run_4/run_matrixtranspose_CD_4.sh"
run_bg "CD_6" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/CD/run_6/run_matrixtranspose_CD_6.sh"
run_bg "CD_8" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/CD/run_8/run_matrixtranspose_CD_8.sh"
run_bg "CD_ideal" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/CD/run_ideal/run_matrixtranspose_CD_ideal.sh"
run_bg "coalescability" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/coalescability/run_matrixtranspose_coalescability.sh"
wait
echo "=== [matrixtranspose] 완료 ==="
