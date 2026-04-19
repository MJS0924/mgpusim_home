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

echo "=== [superdirectory] 전체 벤치마크 시작 ==="
run_bg "fir" "/root/mgpusim_home/mgpusim/amd/samples/fir/superdirectory/run_fir_superdirectory.sh"
run_bg "fft" "/root/mgpusim_home/mgpusim/amd/samples/fft/superdirectory/run_fft_superdirectory.sh"
run_bg "atax" "/root/mgpusim_home/mgpusim/amd/samples/atax/superdirectory/run_atax_superdirectory.sh"
run_bg "bfs" "/root/mgpusim_home/mgpusim/amd/samples/bfs/superdirectory/run_bfs_superdirectory.sh"
run_bg "simpleconvolution" "/root/mgpusim_home/mgpusim/amd/samples/simpleconvolution/superdirectory/run_simpleconvolution_superdirectory.sh"
run_bg "im2col" "/root/mgpusim_home/mgpusim/amd/samples/im2col/superdirectory/run_im2col_superdirectory.sh"
run_bg "kmeans" "/root/mgpusim_home/mgpusim/amd/samples/kmeans/superdirectory/run_kmeans_superdirectory.sh"
run_bg "matrixmultiplication" "/root/mgpusim_home/mgpusim/amd/samples/matrixmultiplication/superdirectory/run_matrixmultiplication_superdirectory.sh"
run_bg "matrixtranspose" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/superdirectory/run_matrixtranspose_superdirectory.sh"
run_bg "pagerank" "/root/mgpusim_home/mgpusim/amd/samples/pagerank/superdirectory/run_pagerank_superdirectory.sh"
run_bg "stencil2d" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/superdirectory/run_stencil2d_superdirectory.sh"
wait
echo "=== [superdirectory] 전체 벤치마크 완료 ==="
