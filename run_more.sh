#!/bin/bash
PY=~/miniconda3/envs/ann/bin/python
cd "$(dirname "$0")"
$PY bench.py --dataset sift --N 10000 --nq 1000 --nperf 64 --E 64 > results/log_sift10k.txt 2>&1
$PY bench.py --dataset gist --N 10000 --nq 1000 --nperf 64 --E 64 > results/log_gist10k.txt 2>&1
for m in 2 8; do $PY bench.py --dataset sift --N 100000 --nq 1000 --nperf 64 --E 64 --m $m > results/log_sift100k_m$m.txt 2>&1; done
for E in 32 128; do $PY bench.py --dataset sift --N 100000 --nq 1000 --nperf 64 --E $E > results/log_sift100k_E$E.txt 2>&1; done
$PY bench.py --dataset sift --N 1000000 --nq 1000 --nperf 64 --E 64 > results/log_sift1M.txt 2>&1
$PY bench.py --dataset gist --N 1000000 --nq 1000 --nperf 32 --E 64 > results/log_gist1M.txt 2>&1
