#!/bin/bash

# 1. 경로 설정 (현재 스크립트 위치 기준)
SCRIPTS_ROOT=$(cd "$(dirname "$0")"; pwd)
RESULTS_DIR="$SCRIPTS_ROOT/../results"
BENCHMARK_DIR="$SCRIPTS_ROOT/../mgpusim/amd/samples"

echo "=== MGPUSIM ENVIRONMENT CLEANUP ==="

# 2. 결과 디렉토리 삭제 (DB 파일 등)
echo "[1/3] Cleaning results directory: $RESULTS_DIR..."
if [ -d "$RESULTS_DIR" ]; then
    rm -rf "$RESULTS_DIR"
    echo "Done: Results directory deleted."
else
    echo "Note: Results directory does not exist, nothing to clean."
fi

# 3. 생성된 실행 스크립트 삭제
echo "[2/3] Removing generated runner scripts in $BENCHMARK_DIR..."
if [ -d "$BENCHMARK_DIR" ]; then
    find "$BENCHMARK_DIR" -name "run_*.sh" -delete
    echo "Done: run_*.sh files deleted."
else
    echo "Note: Benchmark directory not found."
fi

# 4. 하위 디렉토리의 sqlite3 DB 파일 삭제
echo "[3/3] Removing sqlite3 files in $BENCHMARK_DIR..."
if [ -d "$BENCHMARK_DIR" ]; then
    find "$BENCHMARK_DIR" -name "*.sqlite3" -delete
    echo "Done: *.sqlite3 files deleted."
else
    echo "Note: Benchmark directory not found."
fi

echo "=== Cleanup Complete ==="