#!/usr/bin/python3
import os

# 1. 설정값 초기화
# benchmarks = [
#     'matrixmultiplication',
#     'fir',
#     'fft',
#     'atax',
#     'bfs',
#     # 'conv2d',
#     'simpleconvolution',
#     'im2col',
#     'kmeans',
#     'matrixmultiplication',
#     'matrixtranspose',
#     'pagerank',
#     'spmv',
#     'stencil2d'
#     # DNN layer benchmarks
#     'relu',
#     'conv2d',
#     # DNN training benchmarks (dataset 없음: xor 만 활성화)
#     'xor',
#     'lenet',
#     'minerva',
#     'vgg16',
# ]

benchmarks = [
    # 'fir',
    # 'fft',
    # 'atax',
    # 'bfs',
    # 'simpleconvolution',
    'im2col',
    # 'kmeans',
    'matrixmultiplication',
    'matrixtranspose',
    'pagerank',
    'spmv',
    'stencil2d',

    # # DNN layer benchmarks
    'relu',
    'conv2d',

    # # DNN training benchmarks (dataset 없음: xor 만 활성화)
    # 'xor',
    # 'lenet',
    # 'minerva',
    # 'vgg16',
]

# Per-window snapshot 을 활성화할 workload 목록 (§3.3 R-sweep 대상)
PW_BENCHMARKS = {
    'im2col',
    'matrixmultiplication',
    'matrixtranspose',
    'pagerank',
    'spmv',
    'stencil2d',
    'relu',
    'conv2d'
}
PW_WINDOW_INST = 50000

# stdout 저장 여부. False면 text 파일로도 저장하지 않고 터미널에도 출력하지 않음.
# (sqlite은 그대로 저장되므로 sqlite 기반 분석은 정상 동작)
# stderr는 항상 터미널로 흘림 (에러/경고 확인용)
SAVE_STDOUT = True

STDOUT_REDIRECT = "> /dev/null"

# 벤치마크별 전용 인자 매핑
# 메모리 사용량을 matmul 1600^3 (= 3 × 1600² × 4B float32 ≈ 30.72 MB) 에
# 맞춰 스케일 조정. 각 항목의 메모리 공식과 계산값은 주석으로 표기.
#
# 메모리 공식 (모두 디바이스 GPU 메모리 기준):
#   matmul    : 12 × X² (X=Y=Z 가정, A+B+C 세 행렬 float32)
#   fir       : 8L (input + output float32)
#   fft       : MB × 1024² (직접 매핑, complex64 = 8B)
#   atax      : (N² + 3N) × 4 (NX=NY=N 가정)
#   bfs       : N × (D+2) × 4
#   simpleconv: ((W+m-1)² + W² + m²) × 4 (W=H, mask m=3)
#   im2col    : 24HW + 216(H-2)(W-2) (input float64 + im2col output)
#   kmeans    : (2pf + p + cf) × 4
#   transpose : 8W² (input + output float32)
#   pagerank  : (3N + 2 × N²×sparsity) × 4 ≈ 8 × N² × sparsity
#   spmv      : (2 × Dim²×s + 3 × Dim + 1) × 4 ≈ 8 × Dim² × s
#   stencil2d : 2 × R × pad16(C) × 4 ≈ 8RC
#   conv2d    : 24HW + 1176(H-6)² (input + im2col 내부 버퍼, KH=KW=7)
#   relu      : 8L (input + output float32)
bench_args_map = {
    # 30.72 MB: 8 × 3,840,000
    'fir': "-length=3840000",
    # 30.00 MiB ≈ 31.46 MB
    'fft': "-MB=30 -passes=64",
    # 30.75 MB: (2771² + 3×2771) × 4
    'atax': "-x=2771 -y=2771",
    # 30.72 MB: 225882 × 34 × 4
    'bfs': "-node=225882 -degree=32",
    # 30.40 MB: 1×3×165²×8 + 1176×159² (im2col 내부 버퍼 지배)
    'conv2d': "-N=1 -C=3 -H=165 -W=165 -output-channel=3 -kernel-height=7 -kernel-width=7",
    # 30.80 MB: 24×360² + 216×358²
    'im2col': "-N=1 -C=3 -H=360 -W=360 -kernel-height=3 -kernel-width=3",
    # 31.21 MB: (2×120000×32 + 120000 + 100×32) × 4
    'kmeans': "-points=120000 -features=32 -clusters=100 -max-iter=5",
    # 30.72 MB (기준): 3 × 1600² × 4
    'matrixmultiplication': "-x=1600 -y=1600 -z=1600",
    # 30.73 MB: 2 × 1960² × 4
    'matrixtranspose': "-width=8192",
    # 30.71 MB: 27713² × 0.005 ≈ 3.84M edges, × 8B
    'pagerank': "-node=27713 -sparsity=0.005 -iterations=3",
    # 30.72 MB: 65536² × 0.000871 × 8 + 12 × 65536
    # numWGX = 65536/128 = 512 → 4 real GPU 균등 분배 (각 128 WGs)
    'spmv': "-dim=65536 -sparsity=0.000871",
    # 30.86 MB: 2 × 1960 × 1968 × 4 (16B padding)
    'stencil2d': "-row=1960 -col=1960 -iter=40",
    # DNN
    # 30.72 MB: 8 × 3,840,000
    'relu':    "-length=3840000",
    'xor':     "",
    'lenet':   "-epoch=1 -max-batch-per-epoch=2 -batch-size=32",
    'minerva': "-epoch=1 -max-batch-per-epoch=2 -batch-size=32",
    'vgg16':   "-epoch=1 -max-batch-per-epoch=2 -batch-size=8",
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
    # [2] superdirectory sweep 스크립트 및 경로 생성
    #     - default  : sequential bank search (기존 baseline)
    #     - parallel : -sd-parallel-bank-search
    #                  (모든 directory bank를 dirLatency 한 번에 동시 lookup,
    #                   bank stage queue도 단일 점유. BF query 생략, RSB는
    #                   miss-time entry 할당 시에만 참조)
    #     각 config는 별개의 subdirectory에서 실행 (sqlite3 충돌 방지).
    #     default config의 출력 이름은 기존과 동일하여 분석 파이프라인 호환.
    # ---------------------------------------------------------
    result_dir_sd = os.path.join(results_base, "superdirectory")
    sd_text_dir = os.path.join(result_dir_sd, "rawdata", "text")
    sd_sql_dir  = os.path.join(result_dir_sd, "rawdata", "sql")
    sd_event_dir = os.path.join(result_dir_sd, "rawdata", "events")
    os.makedirs(sd_text_dir, exist_ok=True)
    os.makedirs(sd_sql_dir,  exist_ok=True)
    os.makedirs(sd_event_dir, exist_ok=True)

    sd_dir = os.path.join(sample_dir, "superdirectory")
    os.makedirs(sd_dir, exist_ok=True)
    sd_sh_path = os.path.join(sd_dir, f"run_{benchmark}_superdirectory.sh")

    sd_configs = [
        {"id": "default",  "extra_arg": ""},
        {"id": "parallel", "extra_arg": "    -sd-parallel-bank-search \\\n"},
    ]

    sd_sub_scripts = {}  # {config_id: sub_sh_path}

    for cfg in sd_configs:
        cfg_run_dir = os.path.join(sd_dir, f"run_{cfg['id']}")
        os.makedirs(cfg_run_dir, exist_ok=True)
        cfg_sh_path = os.path.join(cfg_run_dir, f"run_{benchmark}_superdirectory_{cfg['id']}.sh")

        if cfg['id'] == "default":
            out_txt = os.path.join(sd_text_dir, f"{benchmark}_superdirectory.txt")
            out_sql = os.path.join(sd_sql_dir,  f"{benchmark}_superdirectory.sqlite3")
            out_events = os.path.join(sd_event_dir, f"{benchmark}_events.parquet")
        else:
            out_txt = os.path.join(sd_text_dir, f"{benchmark}_superdirectory_{cfg['id']}.txt")
            out_sql = os.path.join(sd_sql_dir,  f"{benchmark}_superdirectory_{cfg['id']}.sqlite3")
            out_events = os.path.join(sd_event_dir, f"{benchmark}_{cfg['id']}_events.parquet")

        # per-window snapshot 경로 (default에만 — 기존 분석 호환 유지)
        pw_csv = ""
        if cfg['id'] == "default" and benchmark in PW_BENCHMARKS:
            pw_out_dir = os.path.join(results_base, "per_window", benchmark)
            os.makedirs(pw_out_dir, exist_ok=True)
            pw_csv = os.path.join(pw_out_dir, f"{benchmark}_SD_per_window.csv")

        with open(cfg_sh_path, "w") as f:
            f.write("#!/bin/bash\n\n")
            f.write(f"cd {cfg_run_dir}\n\n")           # 전용 디렉토리로 이동
            f.write(f"export EVENT_LOG_PATH={out_events}\n\n")
            f.write(f"../../{benchmark} \\\n")          # 바이너리는 superdirectory의 두 단계 위
            f.write("    -timing \\\n")
            f.write("    -unified-gpus=1,2,3,4,5 \\\n")
            f.write("    -use-unified-memory \\\n")
            f.write("    -coherence-directory=SuperDirectory \\\n")
            f.write("    -log2-page-size=12 \\\n")
            f.write(f"    {bench_args} \\\n")
            if cfg['extra_arg']:
                f.write(cfg['extra_arg'])
            if pw_csv:
                f.write(f"    -per-window-snapshot \\\n")
                f.write(f"    -window-instructions={PW_WINDOW_INST} \\\n")
                f.write(f"    -per-window-output={pw_csv} \\\n")
            f.write("    -report-all \\\n")
            f.write(f"    {f'> {out_txt}' if SAVE_STDOUT else STDOUT_REDIRECT}\n\n")
            f.write("# 결과 파일(SQLite) 이동 및 이름 변경\n")
            f.write(f"mv akita_sim_*.sqlite3 {out_sql} 2>/dev/null\n\n")

        os.chmod(cfg_sh_path, 0o744)
        sd_sub_scripts[cfg['id']] = cfg_sh_path

    # 메인 SD 스크립트 (run_<bench>_superdirectory.sh): default 전용.
    # parallel은 비교군과 분리해 별도 directory master로만 실행하므로
    # 이 wrapper에는 포함하지 않는다.
    with open(sd_sh_path, "w") as f:
        f.write("#!/bin/bash\n\n")
        f.write(f"bash \"{sd_sub_scripts['default']}\"\n")

    os.chmod(sd_sh_path, 0o744)
    # directory master(run_superdirectory_all.sh)용: default 전용 wrapper
    all_dir_scripts.setdefault("superdirectory", []).append((benchmark, sd_sh_path))
    # 별도 directory master(run_superdirectory_parallel_all.sh): parallel sub-script만
    all_dir_scripts.setdefault("superdirectory_parallel", []).append(
        (benchmark, sd_sub_scripts["parallel"])
    )
    # workload master(run_{benchmark}_all.sh)용: 기존 비교군 baseline인 default만 등록.
    # parallel은 다른 directory configs와 섞이지 않게 의도적으로 제외.
    all_benchmark_scripts[benchmark].append(
        ("superdirectory", sd_sub_scripts["default"])
    )

    # ---------------------------------------------------------
    # [3] REC sweep 스크립트 및 경로 생성
    #     - default : numSet=1024 (다른 directory와 동일)
    #     - halfset : numSet=512  (REC 고유의 2x entry-size overhead 반영)
    #     각 config는 별개의 subdirectory에서 실행 (sqlite3 충돌 방지)
    # ---------------------------------------------------------
    result_dir_rec = os.path.join(results_base, "REC")
    rec_text_dir = os.path.join(result_dir_rec, "rawdata", "text")
    rec_sql_dir  = os.path.join(result_dir_rec, "rawdata", "sql")
    os.makedirs(rec_text_dir, exist_ok=True)
    os.makedirs(rec_sql_dir,  exist_ok=True)

    rec_dir = os.path.join(sample_dir, "REC")
    os.makedirs(rec_dir, exist_ok=True)
    rec_sh_path = os.path.join(rec_dir, f"run_{benchmark}_REC.sh")

    rec_configs = [
        {"id": "default", "halfset_arg": ""},
        {"id": "halfset", "halfset_arg": "    -rec-half-set \\\n"},
    ]

    rec_sub_scripts = []  # [(config_id, sub_sh_path), ...]

    for cfg in rec_configs:
        cfg_run_dir = os.path.join(rec_dir, f"run_{cfg['id']}")
        os.makedirs(cfg_run_dir, exist_ok=True)
        cfg_sh_path = os.path.join(cfg_run_dir, f"run_{benchmark}_REC_{cfg['id']}.sh")

        if cfg['id'] == "default":
            out_txt = os.path.join(rec_text_dir, f"{benchmark}_REC.txt")
            out_sql = os.path.join(rec_sql_dir,  f"{benchmark}_REC.sqlite3")
        else:
            out_txt = os.path.join(rec_text_dir, f"{benchmark}_REC_{cfg['id']}.txt")
            out_sql = os.path.join(rec_sql_dir,  f"{benchmark}_REC_{cfg['id']}.sqlite3")

        with open(cfg_sh_path, "w") as f:
            f.write("#!/bin/bash\n\n")
            f.write(f"cd {cfg_run_dir}\n\n")           # 전용 디렉토리로 이동
            f.write(f"../../{benchmark} \\\n")          # 바이너리는 REC의 두 단계 위
            f.write("    -timing \\\n")
            f.write("    -unified-gpus=1,2,3,4,5 \\\n")
            f.write("    -use-unified-memory \\\n")
            # f.write("    -page-migration-policy=AccessCounter \\\n")
            f.write("    -coherence-directory=REC \\\n")
            f.write("    -log2-page-size=12 \\\n")
            f.write(f"    {bench_args} \\\n")
            if cfg['halfset_arg']:
                f.write(cfg['halfset_arg'])
            f.write("    -report-all \\\n")
            f.write(f"    {f'> {out_txt}' if SAVE_STDOUT else STDOUT_REDIRECT}\n\n")
            f.write("# 결과 파일(SQLite) 이동 및 이름 변경\n")
            f.write(f"mv akita_sim_*.sqlite3 {out_sql} 2>/dev/null\n\n")

        os.chmod(cfg_sh_path, 0o744)
        rec_sub_scripts.append((cfg['id'], cfg_sh_path))

    # 메인 REC 스크립트: sub-script를 최대 MAX_PARALLEL개 병렬 실행
    with open(rec_sh_path, "w") as f:
        f.write("#!/bin/bash\n\n")
        f.write("MAX_PARALLEL=4\n\n")
        f.write("trap 'echo \"중단 중...\"; kill 0; exit 1' INT TERM\n\n")
        f.write("run_bg() {\n")
        f.write("    local config_id=$1\n")
        f.write("    local script_path=$2\n")
        f.write(f"    echo \"  [REC-{benchmark}][${{config_id}}] 실행 중...\"\n")
        f.write("    bash \"${script_path}\" &\n")
        f.write("    while [ \"$(jobs -rp | wc -l)\" -ge \"${MAX_PARALLEL}\" ]; do\n")
        f.write("        wait -n 2>/dev/null || wait\n")
        f.write("    done\n")
        f.write("}\n\n")
        f.write(f"echo \"=== [REC][{benchmark}] 시작 (병렬 최대 ${{MAX_PARALLEL}}) ===\"\n")
        for cfg_id, sub_sh_path in rec_sub_scripts:
            f.write(f"run_bg \"{cfg_id}\" \"{sub_sh_path}\"\n")
        f.write("wait\n")
        f.write(f"echo \"=== [REC][{benchmark}] 완료 ===\"\n")

    os.chmod(rec_sh_path, 0o744)
    # directory master(run_REC_all.sh)용: benchmark당 REC wrapper 하나
    all_dir_scripts.setdefault("REC", []).append((benchmark, rec_sh_path))
    # workload master(run_{benchmark}_all.sh)용: 개별 sub-script를 직접 큐에 등록
    # (REC wrapper를 통하면 wrapper가 내부에서 또 병렬 실행해 동시 실행 수가 늘어남)
    for cfg_id, sub_sh_path in rec_sub_scripts:
        all_benchmark_scripts[benchmark].append((f"REC_{cfg_id}", sub_sh_path))

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
        # f.write("    -page-migration-policy=AccessCounter \\\n")
        f.write("    -coherence-directory=HMG \\\n")
        f.write("    -coherence-unit-size=2 \\\n")
        f.write("    -log2-page-size=12 \\\n")
        f.write(f"    {bench_args} \\\n")
        f.write("    -report-all \\\n")
        f.write(f"    {f'> {out_txt}' if SAVE_STDOUT else STDOUT_REDIRECT}\n\n")
        f.write("# 결과 파일(SQLite) 이동 및 이름 변경\n")
        f.write(f"mv akita_sim_*.sqlite3 {out_sql} 2>/dev/null\n\n")

    os.chmod(hmg_sh_path, 0o744)
    all_benchmark_scripts[benchmark].append(("HMG", hmg_sh_path))
    all_dir_scripts.setdefault("HMG", []).append((benchmark, hmg_sh_path))

    # ---------------------------------------------------------
    # [5] CD (CoherenceDirectory) 스크립트 및 경로 생성
    #     각 config는 별개의 subdirectory에서 실행 (sqlite3 충돌 방지)
    #     메인 스크립트는 최대 MAX_PARALLEL개 병렬 launcher
    # ---------------------------------------------------------
    result_dir_cd = os.path.join(results_base, "CD")
    cd_text_dir = os.path.join(result_dir_cd, "rawdata", "text")
    cd_sql_dir  = os.path.join(result_dir_cd, "rawdata", "sql")
    os.makedirs(cd_text_dir, exist_ok=True)
    os.makedirs(cd_sql_dir,  exist_ok=True)

    # motivation 결과 경로 (ideal 실험 결과를 여기에도 저장)
    result_dir_motiv = os.path.join(results_base, "motivation")
    motiv_sql_dir  = os.path.join(result_dir_motiv, "rawdata", "sql")
    motiv_csv_dir  = os.path.join(result_dir_motiv, "rawdata", "csv")
    os.makedirs(motiv_sql_dir,  exist_ok=True)
    os.makedirs(motiv_csv_dir,  exist_ok=True)

    cd_dir = os.path.join(sample_dir, "CD")
    os.makedirs(cd_dir, exist_ok=True)
    cd_sh_path = os.path.join(cd_dir, f"run_{benchmark}_CD.sh")

    # coherence-unit-size = log2(blocks per region); region = 64B × 2^unit
    #   0 → 64B, 1 → 128B, 2 → 256B, 4 → 1KB, 6 → 4KB, 8 → 16KB
    cd_configs = [
        {"id": "0",     "unit_arg": "-coherence-unit-size=0 \\\n", "ideal_arg": ""},
        {"id": "1",     "unit_arg": "-coherence-unit-size=1 \\\n", "ideal_arg": ""},
        {"id": "2",     "unit_arg": "-coherence-unit-size=2 \\\n", "ideal_arg": ""},
        {"id": "4",     "unit_arg": "-coherence-unit-size=4 \\\n", "ideal_arg": ""},
        {"id": "6",     "unit_arg": "-coherence-unit-size=6 \\\n", "ideal_arg": ""},
        {"id": "8",     "unit_arg": "-coherence-unit-size=8 \\\n", "ideal_arg": ""},
        {"id": "ideal", "unit_arg": "-coherence-unit-size=0 \\\n", "ideal_arg": "    -ideal-directory=true \\\n"},
    ]

    cd_sub_scripts = []  # [(config_id, sub_sh_path), ...]

    for cfg in cd_configs:
        # config 전용 subdirectory
        cfg_run_dir = os.path.join(cd_dir, f"run_{cfg['id']}")
        os.makedirs(cfg_run_dir, exist_ok=True)
        cfg_sh_path = os.path.join(cfg_run_dir, f"run_{benchmark}_CD_{cfg['id']}.sh")

        if cfg['id'] == "ideal":
            out_txt = os.path.join(cd_text_dir, f"{benchmark}_ideal.txt")
            out_sql = os.path.join(cd_sql_dir,  f"{benchmark}_ideal.sqlite3")
        else:
            out_txt = os.path.join(cd_text_dir, f"{benchmark}_CD_{cfg['id']}.txt")
            out_sql = os.path.join(cd_sql_dir,  f"{benchmark}_CD_{cfg['id']}.sqlite3")

        # per-window snapshot 경로 (CD_0~4 만, ideal 제외)
        pw_csv = ""
        if cfg['id'] != "ideal" and benchmark in PW_BENCHMARKS:
            pw_out_dir = os.path.join(results_base, "per_window", benchmark)
            os.makedirs(pw_out_dir, exist_ok=True)
            pw_csv = os.path.join(pw_out_dir, f"{benchmark}_CD_{cfg['id']}_per_window.csv")

        with open(cfg_sh_path, "w") as f:
            f.write("#!/bin/bash\n\n")
            f.write(f"cd {cfg_run_dir}\n\n")           # 전용 디렉토리로 이동
            f.write(f"../../{benchmark} \\\n")          # 바이너리는 CD의 두 단계 위
            f.write("    -timing \\\n")
            f.write("    -unified-gpus=1,2,3,4,5 \\\n")
            f.write("    -use-unified-memory \\\n")
            f.write("    -coherence-directory=CoherenceDirectory \\\n")
            f.write("    -log2-page-size=12 \\\n")
            f.write(f"    {cfg['unit_arg']}")
            f.write(f"    {bench_args} \\\n")
            if cfg['ideal_arg']:
                f.write(f"{cfg['ideal_arg']}")
            if pw_csv:
                f.write(f"    -per-window-snapshot \\\n")
                f.write(f"    -window-instructions={PW_WINDOW_INST} \\\n")
                f.write(f"    -per-window-output={pw_csv} \\\n")
            f.write("    -report-all \\\n")
            f.write(f"    {f'> {out_txt}' if SAVE_STDOUT else STDOUT_REDIRECT}\n\n")
            f.write("# 결과 파일(SQLite) 이동 및 이름 변경\n")
            f.write(f"mv akita_sim_*.sqlite3 {out_sql} 2>/dev/null\n\n")
            if cfg['id'] == "ideal":
                # motivation/rawdata/sql 에도 복사 (summarize.py 호환)
                motiv_sql = os.path.join(motiv_sql_dir, f"{benchmark}_motivation.sqlite3")
                f.write("# motivation 경로에도 복사 (summarize.py 호환)\n")
                f.write(f"cp {out_sql} {motiv_sql} 2>/dev/null\n\n")
                # Coalescability CSV 수집
                f.write("# Coalescability CSV 수집\n")
                f.write("for csv_file in motivation_coalescability_GPU*.csv motivation_cumulative_GPU*.csv; do\n")
                f.write(f"    [ -f \"$csv_file\" ] && mv \"$csv_file\" \"{motiv_csv_dir}/{benchmark}_$csv_file\"\n")
                f.write("done\n\n")

        os.chmod(cfg_sh_path, 0o744)
        cd_sub_scripts.append((cfg['id'], cfg_sh_path))

    # 메인 CD 스크립트: 6개 sub-script를 최대 MAX_PARALLEL개 병렬 실행
    with open(cd_sh_path, "w") as f:
        f.write("#!/bin/bash\n\n")
        f.write("MAX_PARALLEL=4\n\n")
        f.write("trap 'echo \"중단 중...\"; kill 0; exit 1' INT TERM\n\n")
        f.write("run_bg() {\n")
        f.write("    local config_id=$1\n")
        f.write("    local script_path=$2\n")
        f.write(f"    echo \"  [CD-{benchmark}][${{config_id}}] 실행 중...\"\n")
        f.write("    bash \"${script_path}\" &\n")
        f.write("    while [ \"$(jobs -rp | wc -l)\" -ge \"${MAX_PARALLEL}\" ]; do\n")
        f.write("        wait -n 2>/dev/null || wait\n")
        f.write("    done\n")
        f.write("}\n\n")
        f.write(f"echo \"=== [CD][{benchmark}] 시작 (병렬 최대 ${{MAX_PARALLEL}}) ===\"\n")
        for cfg_id, sub_sh_path in cd_sub_scripts:
            f.write(f"run_bg \"{cfg_id}\" \"{sub_sh_path}\"\n")
        f.write("wait\n")
        f.write(f"echo \"=== [CD][{benchmark}] 완료 ===\"\n")

    os.chmod(cd_sh_path, 0o744)
    # directory master(run_CD_all.sh)용: benchmark당 CD wrapper 하나
    all_dir_scripts.setdefault("CD", []).append((benchmark, cd_sh_path))
    # workload master(run_{benchmark}_all.sh)용: 개별 sub-script를 직접 큐에 등록
    # (CD wrapper를 통하면 wrapper가 내부에서 또 병렬 실행해 7개 동시 실행 문제 발생)
    for cfg_id, sub_sh_path in cd_sub_scripts:
        all_benchmark_scripts[benchmark].append((f"CD_{cfg_id}", sub_sh_path))

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
      f"  - {os.path.join(results_base, 'motivation', 'rawdata')} (ideal 실험 결과 복사)")

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

print(f"\nGlobal master      : {master_sh_path}")
print(f"Workload masters   : {len(all_workload_masters)} files  →  {workload_master_dir}/")
print(f"Directory masters  : {len(all_dir_scripts)} files  →  {directory_master_dir}/")
