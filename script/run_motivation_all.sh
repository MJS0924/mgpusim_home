#!/bin/bash
# Motivation experiment: ideal directory coalescability measurement
# 각 벤치마크 종료 후 CSV를 results/motivation/rawdata/csv/ 에 자동 저장

MAX_PARALLEL=4

trap 'echo "중단 중..."; kill 0; exit 1' INT TERM

run_bg() {
    local benchmark=$1
    local script_path=$2
    echo "  [motivation][${benchmark}] 실행 중..."
    bash "${script_path}" &
    while [ "$(jobs -rp | wc -l)" -ge "${MAX_PARALLEL}" ]; do
        wait -n 2>/dev/null || wait
    done
}

echo "=== motivation (ideal directory) 실험 시작 ==="
run_bg "fir" "/root/mgpusim_home/mgpusim/amd/samples/fir/motivation/run_fir_motivation.sh"
run_bg "fft" "/root/mgpusim_home/mgpusim/amd/samples/fft/motivation/run_fft_motivation.sh"
run_bg "atax" "/root/mgpusim_home/mgpusim/amd/samples/atax/motivation/run_atax_motivation.sh"
run_bg "bfs" "/root/mgpusim_home/mgpusim/amd/samples/bfs/motivation/run_bfs_motivation.sh"
run_bg "simpleconvolution" "/root/mgpusim_home/mgpusim/amd/samples/simpleconvolution/motivation/run_simpleconvolution_motivation.sh"
run_bg "im2col" "/root/mgpusim_home/mgpusim/amd/samples/im2col/motivation/run_im2col_motivation.sh"
run_bg "kmeans" "/root/mgpusim_home/mgpusim/amd/samples/kmeans/motivation/run_kmeans_motivation.sh"
run_bg "matrixmultiplication" "/root/mgpusim_home/mgpusim/amd/samples/matrixmultiplication/motivation/run_matrixmultiplication_motivation.sh"
run_bg "matrixtranspose" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/motivation/run_matrixtranspose_motivation.sh"
run_bg "pagerank" "/root/mgpusim_home/mgpusim/amd/samples/pagerank/motivation/run_pagerank_motivation.sh"
run_bg "stencil2d" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/motivation/run_stencil2d_motivation.sh"
wait
echo "=== motivation 실험 완료 ==="
echo "CSV 결과 위치: /root/mgpusim_home/results/motivation/rawdata/csv/"
