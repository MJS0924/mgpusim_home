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

echo "=== [REC] 전체 벤치마크 시작 ==="
run_bg "fir" "/root/mgpusim_home/mgpusim/amd/samples/fir/REC/run_fir_REC.sh"
run_bg "fft" "/root/mgpusim_home/mgpusim/amd/samples/fft/REC/run_fft_REC.sh"
run_bg "atax" "/root/mgpusim_home/mgpusim/amd/samples/atax/REC/run_atax_REC.sh"
run_bg "bfs" "/root/mgpusim_home/mgpusim/amd/samples/bfs/REC/run_bfs_REC.sh"
run_bg "simpleconvolution" "/root/mgpusim_home/mgpusim/amd/samples/simpleconvolution/REC/run_simpleconvolution_REC.sh"
run_bg "im2col" "/root/mgpusim_home/mgpusim/amd/samples/im2col/REC/run_im2col_REC.sh"
run_bg "kmeans" "/root/mgpusim_home/mgpusim/amd/samples/kmeans/REC/run_kmeans_REC.sh"
run_bg "matrixmultiplication" "/root/mgpusim_home/mgpusim/amd/samples/matrixmultiplication/REC/run_matrixmultiplication_REC.sh"
run_bg "matrixtranspose" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/REC/run_matrixtranspose_REC.sh"
run_bg "pagerank" "/root/mgpusim_home/mgpusim/amd/samples/pagerank/REC/run_pagerank_REC.sh"
run_bg "stencil2d" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/REC/run_stencil2d_REC.sh"
wait
echo "=== [REC] 전체 벤치마크 완료 ==="
