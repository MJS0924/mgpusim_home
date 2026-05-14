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

echo "=== [atax] 시작 ==="
run_bg "superdirectory" "/root/mgpusim_home/mgpusim/amd/samples/atax/superdirectory/run_atax_superdirectory.sh"
run_bg "REC" "/root/mgpusim_home/mgpusim/amd/samples/atax/REC/run_atax_REC.sh"
run_bg "HMG" "/root/mgpusim_home/mgpusim/amd/samples/atax/HMG/run_atax_HMG.sh"
run_bg "CD_0" "/root/mgpusim_home/mgpusim/amd/samples/atax/CD/run_0/run_atax_CD_0.sh"
run_bg "CD_1" "/root/mgpusim_home/mgpusim/amd/samples/atax/CD/run_1/run_atax_CD_1.sh"
run_bg "CD_2" "/root/mgpusim_home/mgpusim/amd/samples/atax/CD/run_2/run_atax_CD_2.sh"
run_bg "CD_4" "/root/mgpusim_home/mgpusim/amd/samples/atax/CD/run_4/run_atax_CD_4.sh"
run_bg "CD_6" "/root/mgpusim_home/mgpusim/amd/samples/atax/CD/run_6/run_atax_CD_6.sh"
run_bg "CD_8" "/root/mgpusim_home/mgpusim/amd/samples/atax/CD/run_8/run_atax_CD_8.sh"
run_bg "CD_ideal" "/root/mgpusim_home/mgpusim/amd/samples/atax/CD/run_ideal/run_atax_CD_ideal.sh"
wait
echo "=== [atax] 완료 ==="
