#!/bin/bash

bash /root/mgpusim_home/script/workload/run_fir_all.sh
bash /root/mgpusim_home/script/workload/run_fft_all.sh
bash /root/mgpusim_home/script/workload/run_atax_all.sh
bash /root/mgpusim_home/script/workload/run_bfs_all.sh
bash /root/mgpusim_home/script/workload/run_simpleconvolution_all.sh
bash /root/mgpusim_home/script/workload/run_im2col_all.sh
bash /root/mgpusim_home/script/workload/run_kmeans_all.sh
bash /root/mgpusim_home/script/workload/run_matrixmultiplication_all.sh
bash /root/mgpusim_home/script/workload/run_matrixtranspose_all.sh
bash /root/mgpusim_home/script/workload/run_pagerank_all.sh
bash /root/mgpusim_home/script/workload/run_stencil2d_all.sh

echo "모든 실험이 완료되었습니다."
