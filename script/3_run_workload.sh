#!/bin/bash

# 1. 실행 권한 부여
echo "Setting execution permissions for all runner scripts..."
find ../mgpusim/amd/samples -name "run_*.sh" -exec chmod +x {} \;

# 2. 배열 정의
PAGESIZES=("4KB" "64KB" "2MB")
COHERENCE_DIRS=("CoherenceDirectory" "SuperDirectory")
BENCHMARKS=("matrixmultiplication" "atax" "im2col")

# AccessCounter는 고정값이므로 폴더명(하위 디렉토리)에 쓰일 약어를 미리 지정
POL_ABBR="AC"

# 루프 순서: 벤치마크 -> Coherence Directory -> 페이지사이즈
for bench in "${BENCHMARKS[@]}"; do
    for dir in "${COHERENCE_DIRS[@]}"; do
        
        # Coherence Directory 이름 약어 매핑
        if [ "$dir" == "CoherenceDirectory" ]; then
            dir_abbr="CD"
        elif [ "$dir" == "SuperDirectory" ]; then
            dir_abbr="SD"
        elif [ "$dir" == "REC" ]; then
            dir_abbr="REC"
        else
            dir_abbr="$dir"
        fi

        echo "----------------------------------------------------------"
        echo "Building: $bench | Coherence Dir: $dir"
        echo "Running 4KB, 64KB, 2MB simultaneously..."
        echo "----------------------------------------------------------"
        
        # 해당 벤치마크 폴더로 이동하여 빌드
        cd ../mgpusim/amd/samples/$bench || exit 1
        go build
        
        # 3. 각 페이지 사이즈에 대해 백그라운드(&)로 동시 실행
        for pg in "${PAGESIZES[@]}"; do
            echo "  -> Starting $pg for $bench with $dir..."
            
            # 경로: 하위 폴더({pagesize}_AC) / 파일명(run_{bench}_{pagesize}_{dir_abbr}.sh)
            ./${pg}_${POL_ABBR}/run_${bench}_${pg}_${dir_abbr}.sh &
        done
        
        # 4. 방금 실행한 3개의 백그라운드 프로세스가 모두 종료될 때까지 대기
        wait
        echo "Finished all page sizes for $bench with $dir!"
        
        # 다시 원래 스크립트 실행 위치(scripts 폴더)로 복귀
        cd - > /dev/null
    done
done

echo "----------------------------------------------------------"
echo "All parallel simulations finished! Check your results/ folder."