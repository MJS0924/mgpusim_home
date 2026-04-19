#!/usr/bin/python3

import subprocess
import os
import sys
import argparse
import re
import csv

path = "../mgpusim/"
benchmarks_path = path + "amd/samples/"


class Test(object):
    """ define a benchmark to test """

    def __init__(self, path):
        self.path = path

    def compile(self):
        fp = open(os.devnull, 'w')
        p = subprocess.Popen('go build', shell=True,
                             cwd=self.path, stdout=fp, stderr=fp)
        p.wait()
        if p.returncode == 0:
            print("Compiled " + self.path, 'green')
            return False
        else:
            print("Compile failed " + self.path, 'red')
            return True



def main():

    fir                     = Test(benchmarks_path + 'fir')
    fft                     = Test(benchmarks_path + 'fft')
    atax                    = Test(benchmarks_path + 'atax')
    bfs                     = Test(benchmarks_path + 'bfs')
    # conv2d                  = Test(benchmarks_path + 'conv2d')
    simpleconvolution       = Test(benchmarks_path + 'simpleconvolution')
    im2col                  = Test(benchmarks_path + 'im2col')
    kmeans                  = Test(benchmarks_path + 'kmeans')
    matrixmultiplication    = Test(benchmarks_path + 'matrixmultiplication')
    matrixtranspose         = Test(benchmarks_path + 'matrixtranspose')
    pagerank                = Test(benchmarks_path + 'pagerank')
    stencil2d               = Test(benchmarks_path + 'stencil2d')

    err = False 

    err |= fir.compile()
    err |= fft.compile()
    err |= atax.compile()
    err |= bfs.compile()
    # err |= conv2d.compile()
    err |= simpleconvolution.compile()
    err |= fft.compile()
    err |= im2col.compile()     
    err |= kmeans.compile()
    err |= matrixmultiplication.compile()
    err |= matrixtranspose.compile()
    err |= pagerank.compile()
    err |= stencil2d.compile()
    

#    aes = Test(benchmarks_path + 'aes')
#    atax = Test(benchmarks_path + 'atax')
#    bfs = Test(benchmarks_path + 'bfs')
#    bicg = Test(benchmarks_path + 'bicg')
#    bitonicsort = Test(benchmarks_path + 'bitonicsort')
#    concurrentkernel = Test(benchmarks_path + 'concurrentkernel')
#    conv2d = Test(benchmarks_path + 'conv2d')
#    fastwalshtransform = Test(benchmarks_path + 'fastwalshtransform')
#    fft = Test(benchmarks_path + 'fft')
#    fir = Test(benchmarks_path + 'fir')
#    floydwarshall = Test(benchmarks_path + 'floydwarshall')
#    im2col = Test(benchmarks_path + 'im2col')
#    kmeans = Test(benchmarks_path + 'kmeans')
#    matrixmultiplication = Test(benchmarks_path + 'matrixmultiplication')
#    matrixtranspose = Test(benchmarks_path + 'matrixtranspose')
#    mineva = Test(benchmarks_path + 'mineva')
#    nbody = Test(benchmarks_path + 'nbody')
#    pagerank = Test(benchmarks_path + 'pagerank')
#    relu = Test(benchmarks_path + 'relu')
#    simpleconvolution = Test(benchmarks_path + 'simpleconvolution')
#    spmv = Test(benchmarks_path + 'spmv')
#    stencil2d = Test(benchmarks_path + 'stencil2d')
#    vgg16 = Test(benchmarks_path + 'vgg16')
#    xor = Test(benchmarks_path + 'xor')
#    lenet = Test(benchmarks_path + 'lenet')


#    err = False

#    err |= aes.compile()
#    err |= atax.compile()
#    err |= bfs.compile()
#    err |= bicg.compile()
#    err |= bitonicsort.compile()
#    err |= concurrentkernel.compile()
#    err |= conv2d.compile()
#    err |= fastwalshtransform.compile()
#    err |= fft.compile()
#    err |= fir.compile()
#    err |= floydwarshall.compile()
#    err |= im2col.compile()
#    err |= kmeans.compile()
#    err |= matrixmultiplication.compile()
#    err |= matrixtranspose.compile()
#    err |= mineva.compile()
#    err |= nbody.compile()
#    err |= pagerank.compile()
#    err |= relu.compile()
#    err |= simpleconvolution.compile()
#    err |= spmv.compile()
#    err |= stencil2d.compile()
#    err |= vgg16.compile()
#    err |= xor.compile()
#    err |= lenet.compile()


    print(err)

if __name__ == '__main__':
    main()
