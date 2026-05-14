#!/bin/bash
# 중단된 실험으로 생긴 akita_sim_*.sqlite3 및 akita_sim_*.sqlite3-journal 임시 파일을 일괄 삭제합니다.

SAMPLES_DIR="$(cd "$(dirname "$0")/.." && pwd)/mgpusim/amd/samples"

mapfile -t files < <(find "$SAMPLES_DIR" \( -name "akita_sim_*.sqlite3" -o -name "akita_sim_*.sqlite3-journal" \) 2>/dev/null)

if [ ${#files[@]} -eq 0 ]; then
    echo "삭제할 임시 파일이 없습니다."
    exit 0
fi

echo "발견된 임시 파일 (${#files[@]}개):"
for f in "${files[@]}"; do
    echo "  $f"
done

echo ""
read -r -p "위 파일을 모두 삭제하시겠습니까? [y/N] " answer
if [[ "$answer" =~ ^[Yy]$ ]]; then
    for f in "${files[@]}"; do
        rm -f "$f"
    done
    echo "${#files[@]}개 파일이 삭제되었습니다."
else
    echo "취소되었습니다."
fi
