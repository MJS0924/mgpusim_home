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
run_bg "im2col" "/root/mgpusim_home/mgpusim/amd/samples/im2col/CD/run_im2col_CD.sh"
run_bg "matrixmultiplication" "/root/mgpusim_home/mgpusim/amd/samples/matrixmultiplication/CD/run_matrixmultiplication_CD.sh"
run_bg "matrixtranspose" "/root/mgpusim_home/mgpusim/amd/samples/matrixtranspose/CD/run_matrixtranspose_CD.sh"
run_bg "pagerank" "/root/mgpusim_home/mgpusim/amd/samples/pagerank/CD/run_pagerank_CD.sh"
run_bg "spmv" "/root/mgpusim_home/mgpusim/amd/samples/spmv/CD/run_spmv_CD.sh"
run_bg "stencil2d" "/root/mgpusim_home/mgpusim/amd/samples/stencil2d/CD/run_stencil2d_CD.sh"
run_bg "relu" "/root/mgpusim_home/mgpusim/amd/samples/relu/CD/run_relu_CD.sh"
run_bg "conv2d" "/root/mgpusim_home/mgpusim/amd/samples/conv2d/CD/run_conv2d_CD.sh"
run_bg "xor" "/root/mgpusim_home/mgpusim/amd/samples/xor/CD/run_xor_CD.sh"
run_bg "lenet" "/root/mgpusim_home/mgpusim/amd/samples/lenet/CD/run_lenet_CD.sh"
run_bg "minerva" "/root/mgpusim_home/mgpusim/amd/samples/minerva/CD/run_minerva_CD.sh"
run_bg "vgg16" "/root/mgpusim_home/mgpusim/amd/samples/vgg16/CD/run_vgg16_CD.sh"
wait
echo "=== [CD] 전체 벤치마크 완료 ==="
