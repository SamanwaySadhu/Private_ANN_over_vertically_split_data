#!/bin/bash
# sequential so that timings are not disturbed by other runs
PY=~/miniconda3/envs/ann/bin/python
cd "$(dirname "$0")"
$PY bench.py --dataset sift --N 100000 --nq 1000 --nperf 128 --E 64 > results/log_sift100k.txt 2>&1
$PY bench.py --dataset gist --N 100000 --nq 1000 --nperf 128 --E 64 > results/log_gist100k.txt 2>&1
