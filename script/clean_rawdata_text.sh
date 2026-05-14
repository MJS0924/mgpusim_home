#!/bin/bash

SCRIPTS_ROOT=$(cd "$(dirname "$0")"; pwd)
RESULTS_DIR="$SCRIPTS_ROOT/../results"

echo "=== CLEAN rawdata/text CONTENTS ==="

if [ ! -d "$RESULTS_DIR" ]; then
    echo "Note: Results directory does not exist: $RESULTS_DIR"
    exit 0
fi

shopt -s nullglob
found=0
for workload_dir in "$RESULTS_DIR"/*/; do
    text_dir="${workload_dir}rawdata/text"
    if [ -d "$text_dir" ]; then
        found=1
        echo "Cleaning: $text_dir"
        find "$text_dir" -mindepth 1 -delete
    fi
done

if [ "$found" -eq 0 ]; then
    echo "Note: No rawdata/text directories found under $RESULTS_DIR"
fi

echo "=== Cleanup Complete ==="
