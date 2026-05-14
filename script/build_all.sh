#!/usr/bin/env bash
# build_all.sh — go build all workloads under amd/samples/
# 1_compile_benchmarks.py 와 차이:
#   - 빌드 에러를 터미널에 그대로 출력 (devnull 아님)
#   - amd/samples/ 하위 `package main` 선언 디렉토리를 자동 탐색 (하드코딩 없음)
#     ※ entry 파일이 main.go 가 아닌 워크로드(fir.go, matrixtranspose.go 등)도 포착
#   - lenet/minerva/vgg16 처럼 데이터셋 패키지 누락으로 빌드 불가한 항목은 SKIP
#   - 빌드 성공/실패 요약 + 소요 시간 + binary 크기 표시
#   - 실패한 workload 목록을 마지막에 한 번에 출력
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAMPLES_DIR="${SCRIPT_DIR}/../mgpusim/amd/samples"

# 과거 버전의 mgpusim에는 dataset 패키지가 빠져 빌드 불가했지만 현재
# benchmarks/dnn/training_benchmarks/{lenet,minerva,vgg16}/ 가 모두 존재해
# 일반 빌드가 가능하다. 따라서 SKIP_LIST 비움. 빌드 실패 시 다시 추가.
SKIP_LIST=()

pass=()
fail=()
skip=()

echo "=== build_all.sh ==="
echo "Target: ${SAMPLES_DIR}"
echo ""

is_skipped() {
    local name="$1"
    for s in "${SKIP_LIST[@]}"; do
        [ "$name" = "$s" ] && return 0
    done
    return 1
}

# samples/ 의 직속 하위 디렉토리 중 `package main` 선언이 있는 것만 빌드 대상
for dir in "$SAMPLES_DIR"/*/; do
    name="$(basename "$dir")"

    # package main 파일이 없으면 라이브러리/스크립트 디렉토리이므로 스킵
    if ! grep -lE '^package[[:space:]]+main([[:space:]]|$)' "$dir"*.go >/dev/null 2>&1; then
        continue
    fi

    if is_skipped "$name"; then
        printf "%-25s ... SKIP (dataset 패키지 누락)\n" "$name"
        skip+=("$name")
        continue
    fi

    printf "%-25s ... " "$name"
    t_start=$(date +%s%3N)

    # -buildvcs=false: skip VCS stamping. Without this, Go 1.18+ runs
    # `git status` in the workspace, which fails with "dubious ownership"
    # when the repo is owned by a different UID than the current user
    # (common when running as root on a non-root checkout).
    if err=$(cd "$dir" && go build -buildvcs=false 2>&1); then
        t_end=$(date +%s%3N)
        elapsed=$(( t_end - t_start ))

        bin="${dir}${name}"
        if [ -f "$bin" ]; then
            size=$(du -sh "$bin" | awk '{print $1}')
        else
            size="?"
        fi

        echo "OK  (${elapsed}ms, ${size})"
        pass+=("$name")
    else
        t_end=$(date +%s%3N)
        elapsed=$(( t_end - t_start ))
        echo "FAIL (${elapsed}ms)"
        echo "$err" | sed 's/^/    /'
        fail+=("$name")
    fi
done

echo ""
echo "=== Summary ==="
echo "  PASS: ${#pass[@]}  SKIP: ${#skip[@]}  FAIL: ${#fail[@]}"

if [ ${#fail[@]} -gt 0 ]; then
    echo ""
    echo "Failed workloads:"
    for w in "${fail[@]}"; do
        echo "  - $w"
    done
    exit 1
fi
