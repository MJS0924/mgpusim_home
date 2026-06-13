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
    'matrixmultiplication',
    'matrixtranspose',
    'pagerank',
    'spmv',
    'stencil2d',
    'conv2d',
    'fir',
    'bfs',
    'im2col',

    # # DNN training benchmarks (dataset 없음: xor 만 활성화)
    # 'xor',
    'lenet',
    'minerva',
    # 'vgg16',

    # 아래는 비활성화 (요청 실행 순서에서 제외)
    # 'fft',
    # 'simpleconvolution',
    # 'relu',          # DNN layer benchmark
    # 'atax',
    # 'kmeans',
    # 'nbody',
    # 'floydwarshall',
]

# Per-window snapshot 을 활성화할 workload 목록 (§3.3 R-sweep 대상)
PW_BENCHMARKS = {
    'fir',
    'bfs',
    'im2col',
    'kmeans',
    'matrixmultiplication',
    'matrixtranspose',
    'nbody',
    'floydwarshall',
    'pagerank',
    'spmv',
    'stencil2d',
    'relu',
    'conv2d',
    'xor',
    'lenet',
    'minerva',
    'vgg16',
}
PW_WINDOW_INST = 50000

# DNN training workload는 시뮬레이션 비용이 매우 커서 CD fine-grained
# sweep (unit-size 1/2/4/6/8) 와 coalescability heatmap을 생략한다.
# 마스터 스크립트 (`run_{benchmark}_all.sh`) 에는 아래 6개 config 만
# 등록된다. 개별 sub-script (CD_1.sh 등) 와 wrapper (run_{wl}_CD.sh)
# 자체는 그대로 생성되므로 필요 시 수동 실행 가능.
# relu / conv2d / xor 는 DNN layer/소형 워크로드이므로 full sweep 유지.
DNN_BENCHMARKS = {'lenet', 'minerva'}
DNN_ALLOWED_CONFIGS = {
    'superdirectory',
    'superdirectory_FE',
    'REC_default',
    'REC_halfset',
    'HMG',
    'CD_0',
    'CD_ideal',
}

# stdout 저장 여부. False면 text 파일로도 저장하지 않고 터미널에도 출력하지 않음.
# (sqlite은 그대로 저장되므로 sqlite 기반 분석은 정상 동작)
# stderr는 항상 터미널로 흘림 (에러/경고 확인용)
SAVE_STDOUT = True

STDOUT_REDIRECT = "> /dev/null"

# 벤치마크별 전용 인자 매핑
# 메모리 사용량을 matmul 3266³ (= 3 × 3266² × 4B float32 ≈ 128.0 MB) 에
# 맞춰 스케일 조정 (이전 30 MB → 128 MB, 약 4.17×). 각 항목의 메모리 공식과
# 계산값은 주석으로 표기.
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
#   transpose : 8W² (input + output float32, uint32)
#   nbody     : 64P (4 unified buffers × 4 float32-vec × P particles)
#   floyd     : 8N² (2 uint32 matrices: dist + path)
#   pagerank  : (3N + 2 × N²×sparsity) × 4 ≈ 8 × N² × sparsity
#   spmv      : (2 × Dim²×s + 3 × Dim + 1) × 4 ≈ 8 × Dim² × s
#   stencil2d : 2 × R × pad16(C) × 4 ≈ 8RC
#   conv2d    : 24HW + 1176(H-6)² (input + im2col 내부 버퍼, KH=KW=7)
#   relu      : 8L (input + output float32)
# Coalescability heatmap 실험은 sharer pattern 만 캡처하면 되므로 main
# 실험 (~128 MB footprint) 의 절반인 ~64 MB 로 축소한다. Linear-scale
# 워크로드는 1/2, square-scale 워크로드는 1/√2 ≈ 0.707 로 차원을 줄인다.
# 메모리 공식은 main 의 bench_args_map 주석과 동일.
#
# 메모리 추정 (모두 ~64 MB 부근):
#   fir       : 8 × 8,000,000               = 64.0 MB
#   im2col    : 24 × 520² + 216 × 518²      ≈ 64.5 MB
#   matmul    : 12 × 1800²                  = 38.9 MB (75 MB → 38.9, ~½)
#   transpose : 8 × 2828²                   ≈ 64.0 MB
#   nbody     : 64 × 1,048,576              = 64.0 MB
#   floyd     : 8 × 2896²                   ≈ 64.0 MB
#   pagerank  : 40000² × 0.005 × 8          ≈ 64.0 MB
#   spmv      : 8 × 92681² × 0.000931       ≈ 64.0 MB
#   stencil2d : 8 × 2828 × 2832             ≈ 64.0 MB
#   conv2d    : 24 × 236² + 1176 × 230²     ≈ 63.5 MB
#   relu      : 8 × 8,000,000               = 64.0 MB
#   DNN train : batch-size 절반
bench_args_map_coal = {
    'fir':                    "-length=8000000",
    'fft':                    "-MB=64 -passes=64",
    'atax':                   "-x=4000 -y=4000",
    'bfs':                    "-node=470000 -degree=32",
    'conv2d':                 "-N=1 -C=3 -H=236 -W=236 -output-channel=3 -kernel-height=7 -kernel-width=7",
    'floydwarshall':          "-node=2896 -iter=2",
    'im2col':                 "-N=1 -C=3 -H=520 -W=520 -kernel-height=3 -kernel-width=3",
    'kmeans':                 "-points=250000 -features=32 -clusters=100 -max-iter=2",
    'matrixmultiplication':   "-x=1800 -y=1800 -z=1800",
    'matrixtranspose':        "-width=2828",
    'nbody':                  "-particles=1048576 -iter=4",
    'pagerank':               "-node=40000 -sparsity=0.005 -iterations=3",
    'spmv':                   "-dim=92681 -sparsity=0.000931",
    'stencil2d':              "-row=2828 -col=2828 -iter=2",
    'relu':                   "-length=8000000",
    'xor':                    "",
    'lenet':                  "-epoch=1 -max-batch-per-epoch=1 -batch-size=256",
    'minerva':                "-epoch=1 -max-batch-per-epoch=1 -batch-size=256",
    'vgg16':                  "-epoch=1 -max-batch-per-epoch=1 -batch-size=16",
}

bench_args_map = {
    # 128.0 MB: 8 × 16,000,000
    'fir': "-length=16000000",
    # 128.0 MiB ≈ 134.2 MB
    'fft': "-MB=128 -passes=64",
    # 128.0 MB: (5657² + 3×5657) × 4
    'atax': "-x=8000 -y=8000",
    # 127.8 MB: 940000 × 34 × 4
    'bfs': "-node=940000 -degree=32",
    # 128.4 MB: 1×3×333²×8 + 1176×327² (im2col 내부 버퍼 지배)
    'conv2d': "-N=1 -C=3 -H=333 -W=333 -output-channel=3 -kernel-height=7 -kernel-width=7",
    # 129.0 MB: 24×735² + 216×733²
    'im2col': "-N=1 -C=3 -H=735 -W=735 -kernel-height=3 -kernel-width=3",
    # 128.0 MB: (2×500000×32 + 500000 + 100×32) × 4
    'kmeans': "-points=500000 -features=32 -clusters=100 -max-iter=2",
    # 128.0 MB (기준): 3 × 3266² × 4
    'matrixmultiplication': "-x=2500 -y=2500 -z=2500",
    # 128.0 MB: 2 × 4000² × 4 (uint32)
    # 이전 -width=8192는 사실 ~537 MB로 코멘트(30.73 MB)와 불일치하던 버그.
    'matrixtranspose': "-width=4000",
    # 128.0 MB: 64 × 2,097,152 (4 unified-mem float4 버퍼)
    # groupSize=256 의 배수 (2097152 = 8192 × 256)
    'nbody': "-particles=2097152 -iter=4",
    # 128.0 MB: 8 × 4096² (uint32 path + dist 행렬 2개)
    # blockSize=8 의 배수. 기본 iter = numNodes 라 매우 무거워 4 로 고정.
    'floydwarshall': "-node=4096 -iter=4",
    # 128.1 MB: 56600² × 0.005 ≈ 16.0M edges, × 8B
    'pagerank': "-node=80000 -sparsity=0.005 -iterations=3",
    # 128.0 MB: 131072² × 0.000931 × 8 + 12 × 131072
    # numWGX = 131072/128 = 1024 → 4 real GPU 균등 분배 (각 256 WGs)
    'spmv': "-dim=131072 -sparsity=0.000931",
    # 128.5 MB: 2 × 4000 × 4016 × 4 (16B padding)
    'stencil2d': "-row=4000 -col=4000 -iter=4",
    # DNN
    # 128.0 MB: 8 × 16,000,000
    'relu':    "-length=16000000",
    'xor':     "",
    'lenet':   "-epoch=1 -max-batch-per-epoch=2 -batch-size=512",
    'minerva': "-epoch=1 -max-batch-per-epoch=1 -batch-size=512",
    'vgg16':   "-epoch=1 -max-batch-per-epoch=2 -batch-size=32",
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
    #         f.write("    -unified-gpus=1,2,3,4 \\\n")
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
    sd_event_dir = os.path.join(result_dir_sd, "rawdata", "events")  # 추가
    os.makedirs(sd_text_dir, exist_ok=True)
    os.makedirs(sd_sql_dir,  exist_ok=True)
    os.makedirs(sd_event_dir, exist_ok=True)  # 추가

    sd_dir = os.path.join(sample_dir, "superdirectory")
    os.makedirs(sd_dir, exist_ok=True)
    sd_sh_path = os.path.join(sd_dir, f"run_{benchmark}_superdirectory.sh")

    with open(sd_sh_path, "w") as f:
        out_txt = os.path.join(sd_text_dir, f"{benchmark}_superdirectory.txt")
        out_sql = os.path.join(sd_sql_dir,  f"{benchmark}_superdirectory.sqlite3")
        out_events = os.path.join(sd_event_dir, f"{benchmark}_events.parquet")  # 추가

        # per-window snapshot 경로
        pw_csv = ""
        if benchmark in PW_BENCHMARKS:
            pw_out_dir = os.path.join(results_base, "per_window", benchmark)
            os.makedirs(pw_out_dir, exist_ok=True)
            pw_csv = os.path.join(pw_out_dir, f"{benchmark}_SD_per_window.csv")

        f.write("#!/bin/bash\n\n")
        f.write(f"cd {sd_dir}\n\n")
        f.write(f"export EVENT_LOG_PATH={out_events}\n\n")  # 추가 — workload 별 분리
        f.write(f"../{benchmark} \\\n")
        f.write("    -timing \\\n")
        f.write("    -unified-gpus=1,2,3,4 \\\n")
        f.write("    -inter-gpu-noc \\\n")
        f.write("    -inter-gpu-noc-bw=300 \\\n")
        f.write("    -use-unified-memory \\\n")
        f.write("    -page-migration-policy=None \\\n")
        f.write("    -coherence-directory=SuperDirectory \\\n")
        f.write("    -log2-page-size=12 \\\n")
        f.write(f"    {bench_args} \\\n")
        if pw_csv:
            f.write(f"    -per-window-snapshot \\\n")
            f.write(f"    -window-instructions={PW_WINDOW_INST} \\\n")
            f.write(f"    -per-window-output={pw_csv} \\\n")
        f.write("    -report-all \\\n")
        f.write(f"    {f'> {out_txt}' if SAVE_STDOUT else STDOUT_REDIRECT}\n\n")
        f.write("# 결과 파일(SQLite) 이동 및 이름 변경\n")
        f.write(f"mv akita_sim_*.sqlite3 {out_sql} 2>/dev/null\n\n")

    os.chmod(sd_sh_path, 0o744)
    all_benchmark_scripts[benchmark].append(("superdirectory", sd_sh_path))
    all_dir_scripts.setdefault("superdirectory", []).append((benchmark, sd_sh_path))

    # ---------------------------------------------------------
    # [2b] SD_FE 스크립트 (SD + -sd-fe). 기본 SD와 같은 인자에 -sd-fe만 추가.
    #      coarser 3개 bank의 #set을 1/4로 줄여 hardware overhead를 ~16% 절감
    #      (storage: 398K → 334K bits 수준, increment 0.246 → 0.045).
    # ---------------------------------------------------------
    result_dir_sdfe = os.path.join(results_base, "SD_FE")
    sdfe_text_dir = os.path.join(result_dir_sdfe, "rawdata", "text")
    sdfe_sql_dir  = os.path.join(result_dir_sdfe, "rawdata", "sql")
    os.makedirs(sdfe_text_dir, exist_ok=True)
    os.makedirs(sdfe_sql_dir,  exist_ok=True)

    sdfe_dir = os.path.join(sample_dir, "SD_FE")
    os.makedirs(sdfe_dir, exist_ok=True)
    sdfe_sh_path = os.path.join(sdfe_dir, f"run_{benchmark}_SD_FE.sh")

    with open(sdfe_sh_path, "w") as f:
        out_txt = os.path.join(sdfe_text_dir, f"{benchmark}_SD_FE.txt")
        out_sql = os.path.join(sdfe_sql_dir,  f"{benchmark}_SD_FE.sqlite3")

        pw_csv = ""
        if benchmark in PW_BENCHMARKS:
            pw_out_dir = os.path.join(results_base, "per_window", benchmark)
            os.makedirs(pw_out_dir, exist_ok=True)
            pw_csv = os.path.join(pw_out_dir, f"{benchmark}_SD_FE_per_window.csv")

        f.write("#!/bin/bash\n\n")
        f.write(f"cd {sdfe_dir}\n\n")
        f.write(f"../{benchmark} \\\n")
        f.write("    -timing \\\n")
        f.write("    -unified-gpus=1,2,3,4 \\\n")
        f.write("    -inter-gpu-noc \\\n")
        f.write("    -inter-gpu-noc-bw=300 \\\n")
        f.write("    -use-unified-memory \\\n")
        f.write("    -page-migration-policy=None \\\n")
        f.write("    -coherence-directory=SuperDirectory \\\n")
        f.write("    -sd-fe \\\n")
        f.write("    -log2-page-size=12 \\\n")
        f.write(f"    {bench_args} \\\n")
        if pw_csv:
            f.write(f"    -per-window-snapshot \\\n")
            f.write(f"    -window-instructions={PW_WINDOW_INST} \\\n")
            f.write(f"    -per-window-output={pw_csv} \\\n")
        f.write("    -report-all \\\n")
        f.write(f"    {f'> {out_txt}' if SAVE_STDOUT else STDOUT_REDIRECT}\n\n")
        f.write("# 결과 파일(SQLite) 이동 및 이름 변경\n")
        f.write(f"mv akita_sim_*.sqlite3 {out_sql} 2>/dev/null\n\n")

    os.chmod(sdfe_sh_path, 0o744)
    all_benchmark_scripts[benchmark].append(("superdirectory_FE", sdfe_sh_path))
    all_dir_scripts.setdefault("superdirectory_FE", []).append((benchmark, sdfe_sh_path))

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
            pw_label = "REC"
        else:
            out_txt = os.path.join(rec_text_dir, f"{benchmark}_REC_{cfg['id']}.txt")
            out_sql = os.path.join(rec_sql_dir,  f"{benchmark}_REC_{cfg['id']}.sqlite3")
            pw_label = f"REC_{cfg['id']}"

        # per-window snapshot path (one CSV per REC sub-config)
        pw_csv = ""
        if benchmark in PW_BENCHMARKS:
            pw_out_dir = os.path.join(results_base, "per_window", benchmark)
            os.makedirs(pw_out_dir, exist_ok=True)
            pw_csv = os.path.join(pw_out_dir, f"{benchmark}_{pw_label}_per_window.csv")

        with open(cfg_sh_path, "w") as f:
            f.write("#!/bin/bash\n\n")
            f.write(f"cd {cfg_run_dir}\n\n")           # 전용 디렉토리로 이동
            f.write(f"../../{benchmark} \\\n")          # 바이너리는 REC의 두 단계 위
            f.write("    -timing \\\n")
            f.write("    -unified-gpus=1,2,3,4 \\\n")
            f.write("    -inter-gpu-noc \\\n")
            f.write("    -inter-gpu-noc-bw=300 \\\n")
            f.write("    -use-unified-memory \\\n")
            f.write("    -page-migration-policy=None \\\n")
            # f.write("    -page-migration-policy=AccessCounter \\\n")
            f.write("    -coherence-directory=REC \\\n")
            f.write("    -log2-page-size=12 \\\n")
            f.write(f"    {bench_args} \\\n")
            if cfg['halfset_arg']:
                f.write(cfg['halfset_arg'])
            if pw_csv:
                f.write(f"    -per-window-snapshot \\\n")
                f.write(f"    -window-instructions={PW_WINDOW_INST} \\\n")
                f.write(f"    -per-window-output={pw_csv} \\\n")
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

        # per-window snapshot path
        pw_csv = ""
        if benchmark in PW_BENCHMARKS:
            pw_out_dir = os.path.join(results_base, "per_window", benchmark)
            os.makedirs(pw_out_dir, exist_ok=True)
            pw_csv = os.path.join(pw_out_dir, f"{benchmark}_HMG_per_window.csv")

        f.write("#!/bin/bash\n\n")
        f.write(f"cd {hmg_dir}\n\n")
        f.write(f"../{benchmark} \\\n")
        f.write("    -timing \\\n")
        f.write("    -unified-gpus=1,2,3,4 \\\n")
        f.write("    -inter-gpu-noc \\\n")
        f.write("    -inter-gpu-noc-bw=300 \\\n")
        f.write("    -use-unified-memory \\\n")
        f.write("    -page-migration-policy=None \\\n")
        # f.write("    -page-migration-policy=AccessCounter \\\n")
        f.write("    -coherence-directory=HMG \\\n")
        f.write("    -coherence-unit-size=2 \\\n")
        f.write("    -log2-page-size=12 \\\n")
        f.write(f"    {bench_args} \\\n")
        if pw_csv:
            f.write(f"    -per-window-snapshot \\\n")
            f.write(f"    -window-instructions={PW_WINDOW_INST} \\\n")
            f.write(f"    -per-window-output={pw_csv} \\\n")
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

        # per-window snapshot 경로 (CD_* 와 ideal 모두). ideal은 CD_ prefix
        # 없이 {benchmark}_ideal_per_window.csv 로 저장하여 다른 분석 스크립트
        # (perf_check.py 등)와 명명 규칙을 일치시킴.
        pw_csv = ""
        if benchmark in PW_BENCHMARKS:
            pw_out_dir = os.path.join(results_base, "per_window", benchmark)
            os.makedirs(pw_out_dir, exist_ok=True)
            if cfg['id'] == "ideal":
                pw_csv = os.path.join(pw_out_dir, f"{benchmark}_ideal_per_window.csv")
            else:
                pw_csv = os.path.join(pw_out_dir, f"{benchmark}_CD_{cfg['id']}_per_window.csv")

        with open(cfg_sh_path, "w") as f:
            f.write("#!/bin/bash\n\n")
            f.write(f"cd {cfg_run_dir}\n\n")           # 전용 디렉토리로 이동
            f.write(f"../../{benchmark} \\\n")          # 바이너리는 CD의 두 단계 위
            f.write("    -timing \\\n")
            f.write("    -unified-gpus=1,2,3,4 \\\n")
            f.write("    -inter-gpu-noc \\\n")
            f.write("    -inter-gpu-noc-bw=300 \\\n")
            f.write("    -use-unified-memory \\\n")
            f.write("    -page-migration-policy=None \\\n")
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
    # [6] Coalescability heatmap 스크립트 및 경로 생성
    #     optdirectory 가 access pattern 을 관찰만 하므로 baseline (CD_0)
    #     1회 실행으로 sharer heatmap CSV 가 생성됨. RLE 압축 + per-window
    #     dump (instruction window 단위) 가 포함됨.
    #     Workload 크기는 main 의 ~½ (≈ 64 MB footprint) — visualization
    #     용도이므로 큰 입력이 필요 없음.
    # ---------------------------------------------------------
    result_dir_coal = os.path.join(results_base, "coalescability")
    coal_text_dir   = os.path.join(result_dir_coal, "rawdata", "text")
    coal_sql_dir    = os.path.join(result_dir_coal, "rawdata", "sql")
    coal_heatmap_dir = os.path.join(result_dir_coal, "rawdata", "heatmap", benchmark)
    coal_pw_dir     = os.path.join(result_dir_coal, "rawdata", "per_window")
    os.makedirs(coal_text_dir,    exist_ok=True)
    os.makedirs(coal_sql_dir,     exist_ok=True)
    os.makedirs(coal_heatmap_dir, exist_ok=True)
    os.makedirs(coal_pw_dir,      exist_ok=True)

    coal_dir = os.path.join(sample_dir, "coalescability")
    os.makedirs(coal_dir, exist_ok=True)
    coal_sh_path = os.path.join(coal_dir, f"run_{benchmark}_coalescability.sh")

    # 64 MB footprint 용 인자 (main 의 절반 정도 크기). Coalescability
    # heatmap 시각화 목적상 대표 access pattern 만 포착되면 충분함.
    bench_args_coal = bench_args_map_coal.get(benchmark, bench_args)

    with open(coal_sh_path, "w") as f:
        out_txt     = os.path.join(coal_text_dir,    f"{benchmark}_coalescability.txt")
        out_sql     = os.path.join(coal_sql_dir,     f"{benchmark}_coalescability.sqlite3")
        out_pw_csv  = os.path.join(coal_pw_dir,      f"{benchmark}_coalescability_per_window.csv")

        f.write("#!/bin/bash\n\n")
        f.write(f"cd {coal_dir}\n\n")
        f.write(f"../{benchmark} \\\n")
        f.write("    -timing \\\n")
        f.write("    -unified-gpus=1,2,3,4 \\\n")
        f.write("    -inter-gpu-noc \\\n")
        f.write("    -inter-gpu-noc-bw=300 \\\n")
        f.write("    -use-unified-memory \\\n")
        f.write("    -page-migration-policy=None \\\n")
        # CD_0 (64B baseline): no aggregation, optdirectory observes raw
        # access pattern. Heatmap is workload-characteristic and independent
        # of which directory variant we run alongside.
        f.write("    -coherence-directory=CoherenceDirectory \\\n")
        f.write("    -coherence-unit-size=0 \\\n")
        f.write("    -log2-page-size=12 \\\n")
        f.write(f"    {bench_args_coal} \\\n")
        # Sharer heatmap (RLE-compressed per-window dump)
        f.write("    -coalescability-heatmap \\\n")
        f.write(f"    -coalescability-heatmap-dir={coal_heatmap_dir} \\\n")
        # -coalescability-heatmap implies -per-window-snapshot; supply the
        # window-instructions and per-window output path explicitly so the
        # CSV ends up in our coalescability tree.
        f.write(f"    -window-instructions={PW_WINDOW_INST} \\\n")
        f.write(f"    -per-window-output={out_pw_csv} \\\n")
        f.write("    -report-all \\\n")
        f.write(f"    {f'> {out_txt}' if SAVE_STDOUT else STDOUT_REDIRECT}\n\n")
        f.write("# 결과 파일(SQLite) 이동 및 이름 변경\n")
        f.write(f"mv akita_sim_*.sqlite3 {out_sql} 2>/dev/null\n\n")

    os.chmod(coal_sh_path, 0o744)
    all_benchmark_scripts[benchmark].append(("coalescability", coal_sh_path))
    all_dir_scripts.setdefault("coalescability", []).append((benchmark, coal_sh_path))

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
        # DNN 워크로드는 reduced config set만 등록 (CD fine-grained sweep 생략).
        if benchmark in DNN_BENCHMARKS:
            cfgs_to_register = [
                (n, p) for (n, p) in all_benchmark_scripts[benchmark]
                if n in DNN_ALLOWED_CONFIGS
            ]
        else:
            cfgs_to_register = all_benchmark_scripts[benchmark]

        f.write(f"echo \"=== [{benchmark}] 시작 ===\"\n")
        for config_name, script_path in cfgs_to_register:
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
      f"  - {os.path.join(results_base, 'motivation', 'rawdata')} (ideal 실험 결과 복사)\n"
      f"  - {os.path.join(results_base, 'coalescability', 'rawdata')} (sharer heatmap RLE)")

# =========================================================
# [ABLATION] SuperDirectory ablation studies.
#   a0 : no RSB + no CBF
#   a3 : a0 + promote-at-evict OFF
#   a6 : numBanks sweep {3,7,9} @ fixed 4x/bank (log2-sub-entry=2)
#        region(bank i) = 64B * 4^i ; coarsest grows with bank count
#        (3 banks -> 1KB, 7 -> 256KB, 9 -> 4MB).
#
# Workload settings are IDENTICAL to the general experiments: same
# bench_args_map sizes, -unified-gpus=1,2,3,4, -page-migration-policy=None,
# -log2-page-size=12, -report-all, and per-window snapshot for PW_BENCHMARKS
# (the SD block above, with only the ablation flags added).
#
# Run on all general-experiment workloads EXCEPT the DNN-training
# benchmarks (lenet, minerva) — derived from the main `benchmarks` list so
# it tracks any change there automatically.
# Results go to results_ablation/ (does NOT touch the main sweep).
# =========================================================
ABLATION_BENCHMARKS = [b for b in benchmarks if b not in ('lenet', 'minerva')]

# (study_id, results_subdir, [extra SuperDirectory flags])
ablation_configs = [
    ("a0",        "A0_no_rsb_cbf",          ["-sd-disable-rsb=true", "-sd-disable-cbf=true"]),
    ("a3",        "A3_no_promote_at_evict", ["-sd-disable-rsb=true", "-sd-disable-cbf=true",
                                             "-sd-promote-at-evict=false"]),
    ("a6_3banks", "A6_nbank/3banks",        ["-sd-num-banks=3", "-sd-log2-sub-entry=2"]),
    ("a6_7banks", "A6_nbank/7banks",        ["-sd-num-banks=7", "-sd-log2-sub-entry=2"]),
    ("a6_9banks", "A6_nbank/9banks",        ["-sd-num-banks=9", "-sd-log2-sub-entry=2"]),
]

# a5 : hold the region-size SPAN fixed at 64B .. 64B*2^8 (16KB) while sweeping
# the per-bank granularity step (log2-sub-entry). numBanks is NOT free — it
# follows from  log2 * (numBanks-1) = 8, so it changes with log2:
#   log2=1 (2x/bank)  -> 9 banks      log2=4 (16x/bank)  -> 3 banks
#   log2=8 (256x/bank) -> 2 banks
# log2=2 (4x/bank, 5 banks) is OMITTED — it is the default config (= baseline).
# (Orthogonal to a6, which fixes 4x/bank and sweeps numBanks.)
for _log2, _nb in [(1, 9), (4, 3), (8, 2)]:
    ablation_configs.append(
        (f"a5_log2_{_log2}", f"A5_log2sweep/log2_{_log2}",
         [f"-sd-num-banks={_nb}", f"-sd-log2-sub-entry={_log2}"]))

results_ablation_base = os.path.abspath(os.path.join(current_dir, "..", "results_ablation"))
ablation_master_entries = []  # [(label, script_path), ...]

for benchmark in ABLATION_BENCHMARKS:
    bench_args = bench_args_map.get(benchmark, "")
    sample_dir = os.path.abspath(os.path.join(current_dir, "..", "mgpusim", "amd", "samples", benchmark))
    abl_base_dir = os.path.join(sample_dir, "ablation")
    os.makedirs(abl_base_dir, exist_ok=True)

    for study_id, results_subdir, extra_flags in ablation_configs:
        result_dir = os.path.join(results_ablation_base, results_subdir)
        text_dir  = os.path.join(result_dir, "rawdata", "text")
        sql_dir   = os.path.join(result_dir, "rawdata", "sql")
        event_dir = os.path.join(result_dir, "rawdata", "events")
        os.makedirs(text_dir,  exist_ok=True)
        os.makedirs(sql_dir,   exist_ok=True)
        os.makedirs(event_dir, exist_ok=True)

        # Per-config subdirectory so each run gets its own akita_sim_*.sqlite3
        # (binary is two levels up: samples/{benchmark}/{benchmark}).
        run_dir = os.path.join(abl_base_dir, study_id)
        os.makedirs(run_dir, exist_ok=True)
        sh_path = os.path.join(run_dir, f"run_{benchmark}_{study_id}.sh")

        out_txt    = os.path.join(text_dir,  f"{benchmark}_{study_id}.txt")
        out_sql    = os.path.join(sql_dir,   f"{benchmark}_{study_id}.sqlite3")
        out_events = os.path.join(event_dir, f"{benchmark}_{study_id}_events.parquet")

        pw_csv = ""
        if benchmark in PW_BENCHMARKS:
            pw_out_dir = os.path.join(results_ablation_base, "per_window", benchmark)
            os.makedirs(pw_out_dir, exist_ok=True)
            pw_csv = os.path.join(pw_out_dir, f"{benchmark}_{study_id}_per_window.csv")

        with open(sh_path, "w") as f:
            f.write("#!/bin/bash\n\n")
            f.write(f"cd {run_dir}\n\n")
            f.write(f"export EVENT_LOG_PATH={out_events}\n\n")
            f.write(f"../../{benchmark} \\\n")          # 바이너리는 ablation/{study}의 두 단계 위
            f.write("    -timing \\\n")
            f.write("    -unified-gpus=1,2,3,4 \\\n")
            f.write("    -inter-gpu-noc \\\n")
            f.write("    -inter-gpu-noc-bw=300 \\\n")
            f.write("    -use-unified-memory \\\n")
            f.write("    -page-migration-policy=None \\\n")
            f.write("    -coherence-directory=SuperDirectory \\\n")
            for flag in extra_flags:
                f.write(f"    {flag} \\\n")
            f.write("    -log2-page-size=12 \\\n")
            f.write(f"    {bench_args} \\\n")
            if pw_csv:
                f.write(f"    -per-window-snapshot \\\n")
                f.write(f"    -window-instructions={PW_WINDOW_INST} \\\n")
                f.write(f"    -per-window-output={pw_csv} \\\n")
            f.write("    -report-all \\\n")
            f.write(f"    {f'> {out_txt}' if SAVE_STDOUT else STDOUT_REDIRECT}\n\n")
            f.write("# 결과 파일(SQLite) 이동 및 이름 변경\n")
            f.write(f"mv akita_sim_*.sqlite3 {out_sql} 2>/dev/null\n\n")

        os.chmod(sh_path, 0o744)
        ablation_master_entries.append((f"{benchmark}_{study_id}", sh_path))

# ablation 마스터 스크립트 (최대 4개 병렬). 저장 위치: script/run_ablation_all.sh
ablation_master_sh_path = os.path.join(current_dir, "run_ablation_all.sh")
with open(ablation_master_sh_path, "w") as f:
    f.write("#!/bin/bash\n\n")
    f.write("MAX_PARALLEL=4\n\n")
    f.write("trap 'echo \"중단 중...\"; kill 0; exit 1' INT TERM\n\n")
    f.write("run_bg() {\n")
    f.write("    local label=$1\n")
    f.write("    local script_path=$2\n")
    f.write("    echo \"  [${label}] 실행 중...\"\n")
    f.write("    bash \"${script_path}\" &\n")
    f.write("    while [ \"$(jobs -rp | wc -l)\" -ge \"${MAX_PARALLEL}\" ]; do\n")
    f.write("        wait -n 2>/dev/null || wait\n")
    f.write("    done\n")
    f.write("}\n\n")
    f.write("echo \"=== [ablation] 시작 (a0/a3/a6, 일반 실험 workload 세팅) ===\"\n")
    for label, script_path in ablation_master_entries:
        f.write(f"run_bg \"{label}\" \"{script_path}\"\n")
    f.write("wait\n")
    f.write("echo \"=== [ablation] 완료 ===\"\n")
os.chmod(ablation_master_sh_path, 0o744)
print(f"  [ablation master] {ablation_master_sh_path}  ({len(ablation_master_entries)} runs)")

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
