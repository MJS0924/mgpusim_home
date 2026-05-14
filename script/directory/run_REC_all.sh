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
run_bg "im2col" "/root/mgpusim_home/mgpusim/amd/samples/im2col/REC/run_im2col_REC.sh"
run_bg "matrixmultiplication" "/root/mgpusim_home/mgpusim/amd/samples/matrixmultiplication/REC/run_matrixmultiplication_REC.sh"
run_bg "matrixtranspose" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/REC/run_matrixtranspose_REC.sh"
run_bg "pagerank" "/root/mgpusim_home/mgpusim/amd/samples/pagerank/REC/run_pagerank_REC.sh"
run_bg "spmv" "/root/mgpusim_home/mgpusim/amd/samples/spmv/REC/run_spmv_REC.sh"
run_bg "stencil2d" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/REC/run_stencil2d_REC.sh"
run_bg "relu" "/root/mgpusim_home/mgpusim/amd/samples/relu/REC/run_relu_REC.sh"
run_bg "conv2d" "/root/mgpusim_home/mgpusim/amd/samples/conv2d/REC/run_conv2d_REC.sh"
run_bg "xor" "/root/mgpusim_home/mgpusim/amd/samples/xor/REC/run_xor_REC.sh"
run_bg "lenet" "/root/mgpusim_home/mgpusim/amd/samples/lenet/REC/run_lenet_REC.sh"
run_bg "minerva" "/root/mgpusim_home/mgpusim/amd/samples/minerva/REC/run_minerva_REC.sh"
run_bg "vgg16" "/root/mgpusim_home/mgpusim/amd/samples/vgg16/REC/run_vgg16_REC.sh"
wait
echo "=== [REC] 전체 벤치마크 완료 ==="
