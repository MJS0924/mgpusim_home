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

echo "=== [matrixmultiplication] 시작 ==="
run_bg "superdirectory" "/root/mgpusim_home/mgpusim/amd/samples/matrixmultiplication/superdirectory/run_matrixmultiplication_superdirectory.sh"
run_bg "REC" "/root/mgpusim_home/mgpusim/amd/samples/matrixmultiplication/REC/run_matrixmultiplication_REC.sh"
run_bg "HMG" "/root/mgpusim_home/mgpusim/amd/samples/matrixmultiplication/HMG/run_matrixmultiplication_HMG.sh"
run_bg "CD" "/root/mgpusim_home/mgpusim/amd/samples/matrixmultiplication/CD/run_matrixmultiplication_CD.sh"
run_bg "motivation" "/root/mgpusim_home/mgpusim/amd/samples/matrixmultiplication/motivation/run_matrixmultiplication_motivation.sh"
wait
echo "=== [matrixmultiplication] 완료 ==="
