#!/usr/bin/python3

import subprocess
import os
import sys

path = "../mgpusim/"
benchmarks_path = path + "amd/samples/"


class Test(object):
    """ define a benchmark to test """

    def __init__(self, path):
        self.path = path

    def compile(self):
        p = subprocess.Popen(
            'go build', shell=True,
            cwd=self.path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out, err = p.communicate()
        if p.returncode == 0:
            print(f"  [OK  ] {self.path}")
            return False
        else:
            print(f"  [FAIL] {self.path}")
            if err:
                print(err.decode(errors='replace').rstrip())
            return True


# 빌드 대상 — 2_make_shell.py가 사용할 가능성이 있는 모든 워크로드.
# lenet/minerva/vgg16은 데이터셋 패키지 누락으로 컴파일 불가하므로 제외.
BENCHMARKS = [
    'fir',
    'fft',
    'atax',
    'bfs',
    'simpleconvolution',
    'im2col',
    'kmeans',
    'matrixmultiplication',
    'matrixtranspose',
    'pagerank',
    'spmv',
    'stencil2d',
    # DNN layer benchmarks
    'conv2d',
    'relu',
    # DNN training benchmarks
    'xor',
    # 'lenet',    # dataset/mnist 패키지 누락으로 컴파일 불가
    # 'minerva',  # dataset/mnist 패키지 누락으로 컴파일 불가
    # 'vgg16',    # dataset/imagenet 패키지 누락으로 컴파일 불가
]


def main():
    err = False
    failed = []
    for name in BENCHMARKS:
        bench = Test(benchmarks_path + name)
        if bench.compile():
            err = True
            failed.append(name)

    if err:
        print(f"\n빌드 실패: {failed}")
        sys.exit(1)
    else:
        print(f"\n모든 벤치마크 ({len(BENCHMARKS)}개) 빌드 완료.")


if __name__ == '__main__':
    main()
