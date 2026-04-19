#!/bin/bash

MAX_PARALLEL=4

run_bg() {
    local benchmark=$1
    local script_path=$2
    echo "  [${benchmark}] 실행 중..."
    bash "${script_path}" &
    while [ "$(jobs -rp | wc -l)" -ge "${MAX_PARALLEL}" ]; do
        wait -n 2>/dev/null || wait
    done
}

echo "=== [LBC] 전체 벤치마크 시작 ==="
run_bg "fir" "/root/mgpusim_home/mgpusim/amd/samples/fir/LBC/run_fir_LBC.sh"
run_bg "fft" "/root/mgpusim_home/mgpusim/amd/samples/fft/LBC/run_fft_LBC.sh"
run_bg "atax" "/root/mgpusim_home/mgpusim/amd/samples/atax/LBC/run_atax_LBC.sh"
run_bg "bfs" "/root/mgpusim_home/mgpusim/amd/samples/bfs/LBC/run_bfs_LBC.sh"
run_bg "simpleconvolution" "/root/mgpusim_home/mgpusim/amd/samples/simpleconvolution/LBC/run_simpleconvolution_LBC.sh"
run_bg "im2col" "/root/mgpusim_home/mgpusim/amd/samples/im2col/LBC/run_im2col_LBC.sh"
run_bg "kmeans" "/root/mgpusim_home/mgpusim/amd/samples/kmeans/LBC/run_kmeans_LBC.sh"
run_bg "matrixmultiplication" "/root/mgpusim_home/mgpusim/amd/samples/matrixmultiplication/LBC/run_matrixmultiplication_LBC.sh"
run_bg "matrixtranspose" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/LBC/run_matrixtranspose_LBC.sh"
run_bg "pagerank" "/root/mgpusim_home/mgpusim/amd/samples/pagerank/LBC/run_pagerank_LBC.sh"
run_bg "stencil2d" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/LBC/run_stencil2d_LBC.sh"
wait
echo "=== [LBC] 전체 벤치마크 완료 ==="
