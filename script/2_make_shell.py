#!/usr/bin/python3
import os

# 1. 설정값 초기화
benchmarks = [
    'fir',
    'fft',
    'atax',
    'bfs',
    # 'conv2d',
    'simpleconvolution',
    'im2col',
    'kmeans',
    'matrixmultiplication',
    'matrixtranspose',
    'pagerank',
    'stencil2d'
]

# 벤치마크별 전용 인자 매핑
bench_args_map = {
    'fir': "-length=655360",
    'fft': "-MB=10 -passes=64",
    'atax': "-x=8192 -y=8192",
    'bfs': "-node=262144 -degree=16",
    'conv2d': "-N=1 -C=3 -H=500 -W=500 -output-channel=3 -kernel-height=7 -kernel-width=7",
    'im2col': "-N=1 -C=3 -H=128 -W=128 -kernel-height=3 -kernel-width=3",
    'kmeans': "-points=30000 -features=32 -clusters=100 -max-iter=5",
    'matrixmultiplication': "-x=1000 -y=1000 -z=1000",
    'matrixtranspose': "-width=4096",
    'pagerank': "-node=16384 -sparsity=0.005 -iterations=4",
    'stencil2d': "-row=2048 -col=2048 -iter=20"
}

# 현재 위치 (scripts 폴더)
current_dir = os.getcwd()

# 2. Results 폴더 경로 설정 (scripts와 같은 레벨의 results 폴더)
results_base = os.path.abspath(os.path.join(current_dir, "..", "results"))

# 마스터 스크립트 저장 폴더
workload_master_dir  = os.path.join(current_dir, "workload")   # run_{benchmark}_all.sh
directory_master_dir = os.path.join(current_dir, "directory")  # run_{config}_all.sh
os.makedirs(workload_master_dir,  exist_ok=True)
os.makedirs(directory_master_dir, exist_ok=True)

print("Generating runner scripts...")

all_benchmark_scripts = {}  # benchmark  -> [(config_name, script_path), ...]
all_dir_scripts       = {}  # config_name -> [(benchmark,  script_path), ...]
all_workload_masters  = []  # [(benchmark, workload_master_path), ...]

for benchmark in benchmarks:
    bench_args = bench_args_map.get(benchmark, "")
    sample_dir = os.path.abspath(os.path.join(current_dir, "..", "mgpusim", "amd", "samples", benchmark))
    all_benchmark_scripts[benchmark] = []

    # ---------------------------------------------------------
    # [1] LBC 스크립트 및 경로 생성
    # ---------------------------------------------------------
    # result_dir_lbc = os.path.join(results_base, "LBC")
    # lbc_text_dir = os.path.join(result_dir_lbc, "rawdata", "text")
    # lbc_sql_dir  = os.path.join(result_dir_lbc, "rawdata", "sql")
    # os.makedirs(lbc_text_dir, exist_ok=True)
    # os.makedirs(lbc_sql_dir,  exist_ok=True)

    # lbc_dir = os.path.join(sample_dir, "LBC")
    # os.makedirs(lbc_dir, exist_ok=True)
    # lbc_sh_path = os.path.join(lbc_dir, f"run_{benchmark}_LBC.sh")

    # with open(lbc_sh_path, "w") as f:
    #     f.write("#!/bin/bash\n\n")
    #     f.write(f"cd {lbc_dir}\n\n")

    #     lbc_configs = [
    #         {"id": "0",     "dir_arg": "",                                                    "unit_arg": "-coherence-unit-size=0 \\\n", "ideal_arg": ""},
    #         {"id": "1",     "dir_arg": "-coherence-directory=LargeBlockCache \\\n    ",       "unit_arg": "-coherence-unit-size=1 \\\n", "ideal_arg": ""},
    #         {"id": "2",     "dir_arg": "-coherence-directory=LargeBlockCache \\\n    ",       "unit_arg": "-coherence-unit-size=2 \\\n", "ideal_arg": ""},
    #         {"id": "3",     "dir_arg": "-coherence-directory=LargeBlockCache \\\n    ",       "unit_arg": "-coherence-unit-size=3 \\\n", "ideal_arg": ""},
    #         {"id": "4",     "dir_arg": "-coherence-directory=LargeBlockCache \\\n    ",       "unit_arg": "-coherence-unit-size=4 \\\n", "ideal_arg": ""},
    #         {"id": "ideal", "dir_arg": "",                                                    "unit_arg": "-coherence-unit-size=0 \\\n", "ideal_arg": "    -ideal-directory=true \\\n"},
    #     ]

    #     for cfg in lbc_configs:
    #         if cfg['id'] == "ideal":
    #             out_txt = os.path.join(lbc_text_dir, f"{benchmark}_ideal.txt")
    #             out_sql = os.path.join(lbc_sql_dir,  f"{benchmark}_ideal.sqlite3")
    #         else:
    #             out_txt = os.path.join(lbc_text_dir, f"{benchmark}_LBC_{cfg['id']}.txt")
    #             out_sql = os.path.join(lbc_sql_dir,  f"{benchmark}_LBC_{cfg['id']}.sqlite3")

    #         f.write(f"../{benchmark} \\\n")
    #         f.write("    -timing \\\n")
    #         f.write("    -unified-gpus=1,2,3,4,5 \\\n")
    #         f.write("    -use-unified-memory \\\n")
    #         f.write("    -page-migration-policy=AccessCounter \\\n")
    #         if cfg['dir_arg']:
    #             f.write(f"    {cfg['dir_arg']}")
    #         f.write("    -log2-page-size=12 \\\n")
    #         f.write(f"    {cfg['unit_arg']}")
    #         f.write(f"    {bench_args} \\\n")
    #         if cfg['ideal_arg']:
    #             f.write(f"{cfg['ideal_arg']}")
    #         f.write("    -report-all \\\n")
    #         f.write(f"    > {out_txt}\n\n")
    #         f.write("# 결과 파일(SQLite) 이동 및 이름 변경\n")
    #         f.write(f"mv akita_sim_*.sqlite3 {out_sql} 2>/dev/null\n\n")

    # os.chmod(lbc_sh_path, 0o744)
    # all_benchmark_scripts[benchmark].append(("LBC", lbc_sh_path))
    # all_dir_scripts.setdefault("LBC", []).append((benchmark, lbc_sh_path))

    # ---------------------------------------------------------
    # [2] superdirectory 스크립트 및 경로 생성
    # ---------------------------------------------------------
    result_dir_sd = os.path.join(results_base, "superdirectory")
    sd_text_dir = os.path.join(result_dir_sd, "rawdata", "text")
    sd_sql_dir  = os.path.join(result_dir_sd, "rawdata", "sql")
    os.makedirs(sd_text_dir, exist_ok=True)
    os.makedirs(sd_sql_dir,  exist_ok=True)

    sd_dir = os.path.join(sample_dir, "superdirectory")
    os.makedirs(sd_dir, exist_ok=True)
    sd_sh_path = os.path.join(sd_dir, f"run_{benchmark}_superdirectory.sh")

    with open(sd_sh_path, "w") as f:
        out_txt = os.path.join(sd_text_dir, f"{benchmark}_superdirectory.txt")
        out_sql = os.path.join(sd_sql_dir,  f"{benchmark}_superdirectory.sqlite3")

        f.write("#!/bin/bash\n\n")
        f.write(f"cd {sd_dir}\n\n")
        f.write(f"../{benchmark} \\\n")
        f.write("    -timing \\\n")
        f.write("    -unified-gpus=1,2,3,4,5 \\\n")
        f.write("    -use-unified-memory \\\n")
        f.write("    -page-migration-policy=AccessCounter \\\n")
        f.write("    -coherence-directory=SuperDirectory \\\n")
        f.write("    -log2-page-size=12 \\\n")
        f.write(f"    {bench_args} \\\n")
        f.write("    -report-all \\\n")
        f.write(f"    > {out_txt}\n\n")
        f.write("# 결과 파일(SQLite) 이동 및 이름 변경\n")
        f.write(f"mv akita_sim_*.sqlite3 {out_sql} 2>/dev/null\n\n")

    os.chmod(sd_sh_path, 0o744)
    all_benchmark_scripts[benchmark].append(("superdirectory", sd_sh_path))
    all_dir_scripts.setdefault("superdirectory", []).append((benchmark, sd_sh_path))

    # ---------------------------------------------------------
    # [3] REC 스크립트 및 경로 생성
    # ---------------------------------------------------------
    result_dir_rec = os.path.join(results_base, "REC")
    rec_text_dir = os.path.join(result_dir_rec, "rawdata", "text")
    rec_sql_dir  = os.path.join(result_dir_rec, "rawdata", "sql")
    os.makedirs(rec_text_dir, exist_ok=True)
    os.makedirs(rec_sql_dir,  exist_ok=True)

    rec_dir = os.path.join(sample_dir, "REC")
    os.makedirs(rec_dir, exist_ok=True)
    rec_sh_path = os.path.join(rec_dir, f"run_{benchmark}_REC.sh")

    with open(rec_sh_path, "w") as f:
        out_txt = os.path.join(rec_text_dir, f"{benchmark}_REC.txt")
        out_sql = os.path.join(rec_sql_dir,  f"{benchmark}_REC.sqlite3")

        f.write("#!/bin/bash\n\n")
        f.write(f"cd {rec_dir}\n\n")
        f.write(f"../{benchmark} \\\n")
        f.write("    -timing \\\n")
        f.write("    -unified-gpus=1,2,3,4,5 \\\n")
        f.write("    -use-unified-memory \\\n")
        f.write("    -page-migration-policy=AccessCounter \\\n")
        f.write("    -coherence-directory=REC \\\n")
        f.write("    -log2-page-size=12 \\\n")
        f.write(f"    {bench_args} \\\n")
        f.write("    -report-all \\\n")
        f.write(f"    > {out_txt}\n\n")
        f.write("# 결과 파일(SQLite) 이동 및 이름 변경\n")
        f.write(f"mv akita_sim_*.sqlite3 {out_sql} 2>/dev/null\n\n")

    os.chmod(rec_sh_path, 0o744)
    all_benchmark_scripts[benchmark].append(("REC", rec_sh_path))
    all_dir_scripts.setdefault("REC", []).append((benchmark, rec_sh_path))

    # ---------------------------------------------------------
    # [4] HMG 스크립트 및 경로 생성
    # ---------------------------------------------------------
    result_dir_hmg = os.path.join(results_base, "HMG")
    hmg_text_dir = os.path.join(result_dir_hmg, "rawdata", "text")
    hmg_sql_dir  = os.path.join(result_dir_hmg, "rawdata", "sql")
    os.makedirs(hmg_text_dir, exist_ok=True)
    os.makedirs(hmg_sql_dir,  exist_ok=True)

    hmg_dir = os.path.join(sample_dir, "HMG")
    os.makedirs(hmg_dir, exist_ok=True)
    hmg_sh_path = os.path.join(hmg_dir, f"run_{benchmark}_HMG.sh")

    with open(hmg_sh_path, "w") as f:
        out_txt = os.path.join(hmg_text_dir, f"{benchmark}_HMG.txt")
        out_sql = os.path.join(hmg_sql_dir,  f"{benchmark}_HMG.sqlite3")

        f.write("#!/bin/bash\n\n")
        f.write(f"cd {hmg_dir}\n\n")
        f.write(f"../{benchmark} \\\n")
        f.write("    -timing \\\n")
        f.write("    -unified-gpus=1,2,3,4,5 \\\n")
        f.write("    -use-unified-memory \\\n")
        f.write("    -page-migration-policy=AccessCounter \\\n")
        f.write("    -coherence-directory=HMG \\\n")
        f.write("    -coherence-unit-size=2 \\\n")
        f.write("    -log2-page-size=12 \\\n")
        f.write(f"    {bench_args} \\\n")
        f.write("    -report-all \\\n")
        f.write(f"    > {out_txt}\n\n")
        f.write("# 결과 파일(SQLite) 이동 및 이름 변경\n")
        f.write(f"mv akita_sim_*.sqlite3 {out_sql} 2>/dev/null\n\n")

    os.chmod(hmg_sh_path, 0o744)
    all_benchmark_scripts[benchmark].append(("HMG", hmg_sh_path))
    all_dir_scripts.setdefault("HMG", []).append((benchmark, hmg_sh_path))

    # ---------------------------------------------------------
    # [5] CD (CoherenceDirectory) 스크립트 및 경로 생성
    # ---------------------------------------------------------
    result_dir_cd = os.path.join(results_base, "CD")
    cd_text_dir = os.path.join(result_dir_cd, "rawdata", "text")
    cd_sql_dir  = os.path.join(result_dir_cd, "rawdata", "sql")
    os.makedirs(cd_text_dir, exist_ok=True)
    os.makedirs(cd_sql_dir,  exist_ok=True)

    cd_dir = os.path.join(sample_dir, "CD")
    os.makedirs(cd_dir, exist_ok=True)
    cd_sh_path = os.path.join(cd_dir, f"run_{benchmark}_CD.sh")

    with open(cd_sh_path, "w") as f:
        f.write("#!/bin/bash\n\n")
        f.write(f"cd {cd_dir}\n\n")

        cd_configs = [
            {"id": "0",     "dir_arg": "-coherence-directory=CoherenceDirectory \\\n",      "unit_arg": "-coherence-unit-size=0 \\\n", "ideal_arg": ""},
            {"id": "1",     "dir_arg": "-coherence-directory=CoherenceDirectory \\\n    ",  "unit_arg": "-coherence-unit-size=1 \\\n", "ideal_arg": ""},
            {"id": "2",     "dir_arg": "-coherence-directory=CoherenceDirectory \\\n    ",  "unit_arg": "-coherence-unit-size=2 \\\n", "ideal_arg": ""},
            {"id": "3",     "dir_arg": "-coherence-directory=CoherenceDirectory \\\n    ",  "unit_arg": "-coherence-unit-size=3 \\\n", "ideal_arg": ""},
            {"id": "4",     "dir_arg": "-coherence-directory=CoherenceDirectory \\\n    ",  "unit_arg": "-coherence-unit-size=4 \\\n", "ideal_arg": ""},
            {"id": "ideal", "dir_arg": "-coherence-directory=CoherenceDirectory \\\n",      "unit_arg": "-coherence-unit-size=0 \\\n", "ideal_arg": "    -ideal-directory=true \\\n"},
        ]

        for cfg in cd_configs:
            if cfg['id'] == "ideal":
                out_txt = os.path.join(cd_text_dir, f"{benchmark}_ideal.txt")
                out_sql = os.path.join(cd_sql_dir,  f"{benchmark}_ideal.sqlite3")
            else:
                out_txt = os.path.join(cd_text_dir, f"{benchmark}_CD_{cfg['id']}.txt")
                out_sql = os.path.join(cd_sql_dir,  f"{benchmark}_CD_{cfg['id']}.sqlite3")

            f.write(f"../{benchmark} \\\n")
            f.write("    -timing \\\n")
            f.write("    -unified-gpus=1,2,3,4,5 \\\n")
            f.write("    -use-unified-memory \\\n")
            f.write("    -page-migration-policy=AccessCounter \\\n")
            f.write(f"    {cfg['dir_arg']}")
            f.write("    -log2-page-size=12 \\\n")
            f.write(f"    {cfg['unit_arg']}")
            f.write(f"    {bench_args} \\\n")
            if cfg['ideal_arg']:
                f.write(f"{cfg['ideal_arg']}")
            f.write("    -report-all \\\n")
            f.write(f"    > {out_txt}\n\n")
            f.write("# 결과 파일(SQLite) 이동 및 이름 변경\n")
            f.write(f"mv akita_sim_*.sqlite3 {out_sql} 2>/dev/null\n\n")

    os.chmod(cd_sh_path, 0o744)
    all_benchmark_scripts[benchmark].append(("CD", cd_sh_path))
    all_dir_scripts.setdefault("CD", []).append((benchmark, cd_sh_path))

    # ---------------------------------------------------------
    # [6] motivation (ideal directory — coalescability experiment)
    #     실험 전용 설정: -ideal-directory=true, CoherenceDirectory, unit-size=0
    #     생성물: stdout text, sqlite3, coalescability CSV per GPU
    # ---------------------------------------------------------
    result_dir_motiv = os.path.join(results_base, "motivation")
    motiv_text_dir = os.path.join(result_dir_motiv, "rawdata", "text")
    motiv_sql_dir  = os.path.join(result_dir_motiv, "rawdata", "sql")
    motiv_csv_dir  = os.path.join(result_dir_motiv, "rawdata", "csv")
    os.makedirs(motiv_text_dir, exist_ok=True)
    os.makedirs(motiv_sql_dir,  exist_ok=True)
    os.makedirs(motiv_csv_dir,  exist_ok=True)

    motiv_dir = os.path.join(sample_dir, "motivation")
    os.makedirs(motiv_dir, exist_ok=True)
    motiv_sh_path = os.path.join(motiv_dir, f"run_{benchmark}_motivation.sh")

    with open(motiv_sh_path, "w") as f:
        out_txt = os.path.join(motiv_text_dir, f"{benchmark}_motivation.txt")
        out_sql = os.path.join(motiv_sql_dir,  f"{benchmark}_motivation.sqlite3")

        f.write("#!/bin/bash\n\n")
        f.write(f"cd {motiv_dir}\n\n")
        f.write(f"../{benchmark} \\\n")
        f.write("    -timing \\\n")
        f.write("    -unified-gpus=1,2,3,4,5 \\\n")
        f.write("    -use-unified-memory \\\n")
        f.write("    -page-migration-policy=AccessCounter \\\n")
        f.write("    -coherence-directory=CoherenceDirectory \\\n")
        f.write("    -coherence-unit-size=0 \\\n")
        f.write("    -ideal-directory=true \\\n")
        f.write("    -log2-page-size=12 \\\n")
        f.write(f"    {bench_args} \\\n")
        f.write("    -report-all \\\n")
        f.write(f"    > {out_txt}\n\n")
        f.write("# SQLite 이동\n")
        f.write(f"mv akita_sim_*.sqlite3 {out_sql} 2>/dev/null\n\n")
        f.write("# Coalescability CSV 수집: GPU별 파일 → benchmark 이름 포함 경로로 이동\n")
        f.write("for csv_file in motivation_coalescability_GPU*.csv motivation_cumulative_GPU*.csv; do\n")
        f.write(f"    [ -f \"$csv_file\" ] && mv \"$csv_file\" \"{motiv_csv_dir}/{benchmark}_$csv_file\"\n")
        f.write("done\n\n")

    os.chmod(motiv_sh_path, 0o744)
    all_benchmark_scripts[benchmark].append(("motivation", motiv_sh_path))
    all_dir_scripts.setdefault("motivation", []).append((benchmark, motiv_sh_path))

    # ---------------------------------------------------------
    # [7] 벤치마크별 마스터 스크립트 생성 (최대 4개 병렬)
    #     저장 위치: script/workload/run_{benchmark}_all.sh
    # ---------------------------------------------------------
    workload_master_sh_path = os.path.join(workload_master_dir, f"run_{benchmark}_all.sh")

    with open(workload_master_sh_path, "w") as f:
        f.write("#!/bin/bash\n\n")
        f.write("MAX_PARALLEL=4\n\n")
        f.write("trap 'echo \"중단 중...\"; kill 0; exit 1' INT TERM\n\n")
        f.write("run_bg() {\n")
        f.write("    local config_name=$1\n")
        f.write("    local script_path=$2\n")
        f.write("    echo \"  [${config_name}] 실행 중...\"\n")
        f.write("    bash \"${script_path}\" &\n")
        f.write("    while [ \"$(jobs -rp | wc -l)\" -ge \"${MAX_PARALLEL}\" ]; do\n")
        f.write("        wait -n 2>/dev/null || wait\n")
        f.write("    done\n")
        f.write("}\n\n")
        f.write(f"echo \"=== [{benchmark}] 시작 ===\"\n")
        for config_name, script_path in all_benchmark_scripts[benchmark]:
            f.write(f"run_bg \"{config_name}\" \"{script_path}\"\n")
        f.write("wait\n")
        f.write(f"echo \"=== [{benchmark}] 완료 ===\"\n")

    os.chmod(workload_master_sh_path, 0o744)
    all_workload_masters.append((benchmark, workload_master_sh_path))

    print(f"  [완료] {benchmark}")

print(f"\nAll runner scripts have been generated.")
print(f"Results will be collected in:\n"
    #   f"  - {os.path.join(results_base, 'LBC', 'rawdata')}\n"
      f"  - {os.path.join(results_base, 'superdirectory', 'rawdata')}\n"
      f"  - {os.path.join(results_base, 'REC', 'rawdata')}\n"
      f"  - {os.path.join(results_base, 'HMG', 'rawdata')}\n"
      f"  - {os.path.join(results_base, 'CD', 'rawdata')}\n"
      f"  - {os.path.join(results_base, 'motivation', 'rawdata')} (coalescability CSVs)")

# ---------------------------------------------------------
# directory별 마스터 스크립트 생성 (최대 4개 병렬)
#   저장 위치: script/directory/run_{config}_all.sh
# ---------------------------------------------------------
for config_name, bench_script_list in all_dir_scripts.items():
    dir_master_sh_path = os.path.join(directory_master_dir, f"run_{config_name}_all.sh")

    with open(dir_master_sh_path, "w") as f:
        f.write("#!/bin/bash\n\n")
        f.write("MAX_PARALLEL=4\n\n")
        f.write("trap 'echo \"중단 중...\"; kill 0; exit 1' INT TERM\n\n")
        f.write("run_bg() {\n")
        f.write("    local benchmark=$1\n")
        f.write("    local script_path=$2\n")
        f.write("    echo \"  [${benchmark}] 실행 중...\"\n")
        f.write("    bash \"${script_path}\" &\n")
        f.write("    while [ \"$(jobs -rp | wc -l)\" -ge \"${MAX_PARALLEL}\" ]; do\n")
        f.write("        wait -n 2>/dev/null || wait\n")
        f.write("    done\n")
        f.write("}\n\n")
        f.write(f"echo \"=== [{config_name}] 전체 벤치마크 시작 ===\"\n")
        for bench, script_path in bench_script_list:
            f.write(f"run_bg \"{bench}\" \"{script_path}\"\n")
        f.write("wait\n")
        f.write(f"echo \"=== [{config_name}] 전체 벤치마크 완료 ===\"\n")

    os.chmod(dir_master_sh_path, 0o744)
    print(f"  [directory master] {dir_master_sh_path}")

# ---------------------------------------------------------
# 글로벌 마스터 스크립트 생성 (벤치마크별 마스터를 순차 호출)
#   저장 위치: script/run_all.sh
# ---------------------------------------------------------
master_sh_path = os.path.join(current_dir, "run_all.sh")

with open(master_sh_path, "w") as f:
    f.write("#!/bin/bash\n\n")
    for benchmark, master_path in all_workload_masters:
        f.write(f"bash {master_path}\n")
    f.write("\necho \"모든 실험이 완료되었습니다.\"\n")

os.chmod(master_sh_path, 0o744)

# ---------------------------------------------------------
# motivation 전용 마스터 스크립트 생성 (벤치마크 병렬 실행)
#   저장 위치: script/run_motivation_all.sh
#   목적: ideal directory coalescability 실험만 단독으로 실행
# ---------------------------------------------------------
motiv_master_sh_path = os.path.join(current_dir, "run_motivation_all.sh")
motiv_bench_scripts  = all_dir_scripts.get("motivation", [])

with open(motiv_master_sh_path, "w") as f:
    f.write("#!/bin/bash\n")
    f.write("# Motivation experiment: ideal directory coalescability measurement\n")
    f.write("# 각 벤치마크 종료 후 CSV를 results/motivation/rawdata/csv/ 에 자동 저장\n\n")
    f.write("MAX_PARALLEL=4\n\n")
    f.write("trap 'echo \"중단 중...\"; kill 0; exit 1' INT TERM\n\n")
    f.write("run_bg() {\n")
    f.write("    local benchmark=$1\n")
    f.write("    local script_path=$2\n")
    f.write("    echo \"  [motivation][${benchmark}] 실행 중...\"\n")
    f.write("    bash \"${script_path}\" &\n")
    f.write("    while [ \"$(jobs -rp | wc -l)\" -ge \"${MAX_PARALLEL}\" ]; do\n")
    f.write("        wait -n 2>/dev/null || wait\n")
    f.write("    done\n")
    f.write("}\n\n")
    f.write("echo \"=== motivation (ideal directory) 실험 시작 ===\"\n")
    for bench, script_path in motiv_bench_scripts:
        f.write(f"run_bg \"{bench}\" \"{script_path}\"\n")
    f.write("wait\n")
    f.write("echo \"=== motivation 실험 완료 ===\"\n")
    csv_out = os.path.join(results_base, "motivation", "rawdata", "csv")
    f.write(f"echo \"CSV 결과 위치: {csv_out}/\"\n")

os.chmod(motiv_master_sh_path, 0o744)

print(f"\nGlobal master      : {master_sh_path}")
print(f"Motivation master  : {motiv_master_sh_path}  ({len(motiv_bench_scripts)} benchmarks)")
print(f"Workload masters   : {len(all_workload_masters)} files  →  {workload_master_dir}/")
print(f"Directory masters  : {len(all_dir_scripts)} files  →  {directory_master_dir}/")
