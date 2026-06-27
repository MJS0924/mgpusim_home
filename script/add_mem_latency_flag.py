#!/usr/bin/env python3
"""Insert the -mem-latency-trace flag (+ output path) into existing workload
run scripts, right before the -report-all line. Skips scripts that are
currently running (passed via --skip) and scripts that already have the flag.
The mem-path output mirrors the per-window / rawdata-text tree into a mem_path
tree. The tracer is timing-neutral, so enabling it does not change results."""
import os
import re
import subprocess
import sys

SAMPLES = "/root/mgpusim_home/mgpusim/amd/samples"


def currently_running():
    out = subprocess.run(["ps", "-ef"], capture_output=True, text=True).stdout
    return set(re.findall(r"/root/\S+/run_\S+\.sh", out))


def derive_output(lines, script_path):
    # Prefer the per-window-output path.
    for ln in lines:
        m = re.search(r"-per-window-output=(\S+)", ln)
        if m:
            p = m.group(1).rstrip("\\").strip()
            p = p.replace("/per_window/", "/mem_path/")
            if p.endswith("_per_window.csv"):
                p = p[: -len("_per_window.csv")] + "_mem_path.csv"
            return p
    # Fall back to the stdout redirect target.
    for ln in lines:
        m = re.search(r">\s*(\S+\.txt)", ln)
        if m:
            p = m.group(1)
            p = p.replace("/rawdata/text/", "/rawdata/mem_path/")
            return p[:-4] + "_mem_path.csv"
    # Last resort: alongside the script.
    return os.path.join(os.path.dirname(script_path), "metrics_mem_path.csv")


def process(script_path):
    with open(script_path) as f:
        lines = f.readlines()

    if any("-mem-latency-trace" in ln for ln in lines):
        return "already"
    idx = next((i for i, ln in enumerate(lines)
                if ln.strip() == "-report-all \\"), None)
    if idx is None:
        return "no-report-all"

    out = derive_output(lines, script_path)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    indent = lines[idx][: len(lines[idx]) - len(lines[idx].lstrip())]
    inject = [
        f"{indent}-mem-latency-trace \\\n",
        f"{indent}-mem-latency-trace-output={out} \\\n",
    ]
    lines[idx:idx] = inject
    with open(script_path, "w") as f:
        f.writelines(lines)
    return "edited"


def main():
    skip = currently_running()
    scripts = []
    for root, _, files in os.walk(SAMPLES):
        for fn in files:
            if re.match(r"run_.*\.sh$", fn):
                scripts.append(os.path.join(root, fn))

    counts = {"edited": 0, "already": 0, "no-report-all": 0, "skipped-running": 0}
    for s in sorted(scripts):
        if s in skip:
            counts["skipped-running"] += 1
            print("SKIP (running):", s)
            continue
        counts[process(s)] += 1

    print("\n=== summary ===")
    for k, v in counts.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
