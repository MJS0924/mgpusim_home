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

echo "=== [bfs] 시작 ==="
run_bg "superdirectory" "/root/mgpusim_home/mgpusim/amd/samples/bfs/superdirectory/run_bfs_superdirectory.sh"
run_bg "REC" "/root/mgpusim_home/mgpusim/amd/samples/bfs/REC/run_bfs_REC.sh"
run_bg "HMG" "/root/mgpusim_home/mgpusim/amd/samples/bfs/HMG/run_bfs_HMG.sh"
run_bg "CD_0" "/root/mgpusim_home/mgpusim/amd/samples/bfs/CD/run_0/run_bfs_CD_0.sh"
run_bg "CD_1" "/root/mgpusim_home/mgpusim/amd/samples/bfs/CD/run_1/run_bfs_CD_1.sh"
run_bg "CD_2" "/root/mgpusim_home/mgpusim/amd/samples/bfs/CD/run_2/run_bfs_CD_2.sh"
run_bg "CD_3" "/root/mgpusim_home/mgpusim/amd/samples/bfs/CD/run_3/run_bfs_CD_3.sh"
run_bg "CD_4" "/root/mgpusim_home/mgpusim/amd/samples/bfs/CD/run_4/run_bfs_CD_4.sh"
run_bg "CD_ideal" "/root/mgpusim_home/mgpusim/amd/samples/bfs/CD/run_ideal/run_bfs_CD_ideal.sh"
wait
echo "=== [bfs] 완료 ==="
