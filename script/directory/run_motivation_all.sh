#!/bin/bash

MAX_PARALLEL=4

trap 'echo "중단 중..."; kill 0; exit 1' INT TERM

run_bg() {
    local benchmark=$1
    local script_path=$2
    echo "  [${benchmark}] 실행 중..."
    bash "${script_path}" &
    while [ "$(jobs -rp | wc -l)" -ge "${MAX_PARALLEL}" ]; do
        wait -n 2>/dev/null || wait
    done
}

echo "=== [motivation] 전체 벤치마크 시작 ==="
run_bg "matrixmultiplication" "/root/mgpusim_home/mgpusim/amd/samples/matrixmultiplication/motivation/run_matrixmultiplication_motivation.sh"
run_bg "pagerank" "/root/mgpusim_home/mgpusim/amd/samples/pagerank/motivation/run_pagerank_motivation.sh"
wait
echo "=== [motivation] 전체 벤치마크 완료 ==="
