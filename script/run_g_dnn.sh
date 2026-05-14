#!/bin/bash
# G_DNN Sweep Script
# DNN workload 전체 config 실행 (workload master 호출 → 평탄 4-병렬)
#
# 사용법:
#   bash /root/mgpusim_home/script/run_g_dnn.sh [workload_list]
#
# 기본 실행:
#   bash /root/mgpusim_home/script/run_g_dnn.sh
#
# 전체 6종 실행:
#   WORKLOADS="relu conv2d lenet minerva vgg16 xor" bash /root/mgpusim_home/script/run_g_dnn.sh
#
# 주의:
#   - 워크로드 마스터(run_{wl}_all.sh)는 leaf script들을 MAX_PARALLEL=4 로
#     평탄 큐잉하므로, 전체 동시 실행은 항상 ≤4 (CD wrapper 통한 중첩 병렬 없음)
#   - workload 단위는 순차 실행 — start_sweep.sh / run_all.sh 와 동일 패턴
#   - vgg16 은 시뮬레이션 시간이 매우 길 수 있음 (수 시간 per config)
#   - xor 은 EnableVerification() 으로 인한 오버헤드 있음

WORKLOADS="${WORKLOADS:-lenet minerva vgg16}"  # 기본 DNN 워크로드 목록 (공백 구분)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKLOAD_MASTER_DIR="${SCRIPT_DIR}/workload"

trap 'echo "중단 중..."; kill 0; exit 1' INT TERM

echo "=== G_DNN Sweep 시작 ==="
echo "Workloads: ${WORKLOADS}"
echo "Start: $(date)"
echo ""

for wl in ${WORKLOADS}; do
    master="${WORKLOAD_MASTER_DIR}/run_${wl}_all.sh"
    if [ ! -x "${master}" ]; then
        echo "  [SKIP] ${wl}: ${master} 없음 (먼저 'python3 2_make_shell.py' 실행 필요)"
        continue
    fi
    echo "--- [${wl}] 시작 ($(date)) ---"
    bash "${master}"
    echo "--- [${wl}] 완료 ($(date)) ---"
    echo ""
done

echo "=== G_DNN Sweep 완료: $(date) ==="