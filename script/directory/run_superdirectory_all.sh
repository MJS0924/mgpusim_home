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
run_bg "im2col" "/root/mgpusim_home/mgpusim/amd/samples/im2col/superdirectory/run_im2col_superdirectory.sh"
run_bg "matrixmultiplication" "/root/mgpusim_home/mgpusim/amd/samples/matrixmultiplication/superdirectory/run_matrixmultiplication_superdirectory.sh"
run_bg "matrixtranspose" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/superdirectory/run_matrixtranspose_superdirectory.sh"
run_bg "pagerank" "/root/mgpusim_home/mgpusim/amd/samples/pagerank/superdirectory/run_pagerank_superdirectory.sh"
run_bg "spmv" "/root/mgpusim_home/mgpusim/amd/samples/spmv/superdirectory/run_spmv_superdirectory.sh"
run_bg "stencil2d" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/superdirectory/run_stencil2d_superdirectory.sh"
run_bg "relu" "/root/mgpusim_home/mgpusim/amd/samples/relu/superdirectory/run_relu_superdirectory.sh"
run_bg "conv2d" "/root/mgpusim_home/mgpusim/amd/samples/conv2d/superdirectory/run_conv2d_superdirectory.sh"
run_bg "xor" "/root/mgpusim_home/mgpusim/amd/samples/xor/superdirectory/run_xor_superdirectory.sh"
run_bg "lenet" "/root/mgpusim_home/mgpusim/amd/samples/lenet/superdirectory/run_lenet_superdirectory.sh"
run_bg "minerva" "/root/mgpusim_home/mgpusim/amd/samples/minerva/superdirectory/run_minerva_superdirectory.sh"
run_bg "vgg16" "/root/mgpusim_home/mgpusim/amd/samples/vgg16/superdirectory/run_vgg16_superdirectory.sh"
wait
echo "=== [superdirectory] 전체 벤치마크 완료 ==="
