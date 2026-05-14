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

echo "=== [coalescability] 전체 벤치마크 시작 ==="
run_bg "fir" "/root/mgpusim_home/mgpusim/amd/samples/fir/coalescability/run_fir_coalescability.sh"
run_bg "im2col" "/root/mgpusim_home/mgpusim/amd/samples/im2col/coalescability/run_im2col_coalescability.sh"
run_bg "matrixmultiplication" "/root/mgpusim_home/mgpusim/amd/samples/matrixmultiplication/coalescability/run_matrixmultiplication_coalescability.sh"
run_bg "matrixtranspose" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/coalescability/run_matrixtranspose_coalescability.sh"
run_bg "pagerank" "/root/mgpusim_home/mgpusim/amd/samples/pagerank/coalescability/run_pagerank_coalescability.sh"
run_bg "spmv" "/root/mgpusim_home/mgpusim/amd/samples/spmv/coalescability/run_spmv_coalescability.sh"
run_bg "stencil2d" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/coalescability/run_stencil2d_coalescability.sh"
run_bg "relu" "/root/mgpusim_home/mgpusim/amd/samples/relu/coalescability/run_relu_coalescability.sh"
run_bg "conv2d" "/root/mgpusim_home/mgpusim/amd/samples/conv2d/coalescability/run_conv2d_coalescability.sh"
run_bg "xor" "/root/mgpusim_home/mgpusim/amd/samples/xor/coalescability/run_xor_coalescability.sh"
run_bg "lenet" "/root/mgpusim_home/mgpusim/amd/samples/lenet/coalescability/run_lenet_coalescability.sh"
run_bg "minerva" "/root/mgpusim_home/mgpusim/amd/samples/minerva/coalescability/run_minerva_coalescability.sh"
run_bg "vgg16" "/root/mgpusim_home/mgpusim/amd/samples/vgg16/coalescability/run_vgg16_coalescability.sh"
wait
echo "=== [coalescability] 전체 벤치마크 완료 ==="
