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

echo "=== [CD] 전체 벤치마크 시작 ==="
run_bg "fir" "/root/mgpusim_home/mgpusim/amd/samples/fir/CD/run_fir_CD.sh"
run_bg "fft" "/root/mgpusim_home/mgpusim/amd/samples/fft/CD/run_fft_CD.sh"
run_bg "atax" "/root/mgpusim_home/mgpusim/amd/samples/atax/CD/run_atax_CD.sh"
run_bg "bfs" "/root/mgpusim_home/mgpusim/amd/samples/bfs/CD/run_bfs_CD.sh"
run_bg "simpleconvolution" "/root/mgpusim_home/mgpusim/amd/samples/simpleconvolution/CD/run_simpleconvolution_CD.sh"
run_bg "im2col" "/root/mgpusim_home/mgpusim/amd/samples/im2col/CD/run_im2col_CD.sh"
run_bg "kmeans" "/root/mgpusim_home/mgpusim/amd/samples/kmeans/CD/run_kmeans_CD.sh"
run_bg "matrixmultiplication" "/root/mgpusim_home/mgpusim/amd/samples/matrixmultiplication/CD/run_matrixmultiplication_CD.sh"
run_bg "matrixtranspose" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/CD/run_matrixtranspose_CD.sh"
run_bg "pagerank" "/root/mgpusim_home/mgpusim/amd/samples/pagerank/CD/run_pagerank_CD.sh"
run_bg "stencil2d" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/CD/run_stencil2d_CD.sh"
wait
echo "=== [CD] 전체 벤치마크 완료 ==="
