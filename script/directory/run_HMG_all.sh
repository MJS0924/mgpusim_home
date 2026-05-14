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

echo "=== [HMG] 전체 벤치마크 시작 ==="
run_bg "fir" "/root/mgpusim_home/mgpusim/amd/samples/fir/HMG/run_fir_HMG.sh"
run_bg "im2col" "/root/mgpusim_home/mgpusim/amd/samples/im2col/HMG/run_im2col_HMG.sh"
run_bg "matrixmultiplication" "/root/mgpusim_home/mgpusim/amd/samples/matrixmultiplication/HMG/run_matrixmultiplication_HMG.sh"
run_bg "matrixtranspose" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/HMG/run_matrixtranspose_HMG.sh"
run_bg "pagerank" "/root/mgpusim_home/mgpusim/amd/samples/pagerank/HMG/run_pagerank_HMG.sh"
run_bg "spmv" "/root/mgpusim_home/mgpusim/amd/samples/spmv/HMG/run_spmv_HMG.sh"
run_bg "stencil2d" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/HMG/run_stencil2d_HMG.sh"
run_bg "relu" "/root/mgpusim_home/mgpusim/amd/samples/relu/HMG/run_relu_HMG.sh"
run_bg "conv2d" "/root/mgpusim_home/mgpusim/amd/samples/conv2d/HMG/run_conv2d_HMG.sh"
run_bg "xor" "/root/mgpusim_home/mgpusim/amd/samples/xor/HMG/run_xor_HMG.sh"
run_bg "lenet" "/root/mgpusim_home/mgpusim/amd/samples/lenet/HMG/run_lenet_HMG.sh"
run_bg "minerva" "/root/mgpusim_home/mgpusim/amd/samples/minerva/HMG/run_minerva_HMG.sh"
run_bg "vgg16" "/root/mgpusim_home/mgpusim/amd/samples/vgg16/HMG/run_vgg16_HMG.sh"
wait
echo "=== [HMG] 전체 벤치마크 완료 ==="
