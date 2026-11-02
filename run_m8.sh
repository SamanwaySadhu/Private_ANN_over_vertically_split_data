#!/bin/bash
PY=~/miniconda3/envs/ann/bin/python
cd "$(dirname "$0")"
for E in 64 32 128; do
  tag=sift_N1000000_m8_E${E}_pub
  [ -s results/${tag}.json ] || $PY bench.py --dataset sift --N 1000000 --nq 1000 --nperf 32 --m 8 --E $E --mode pub --threads "" > results/log_${tag}.txt 2>&1
done
echo done > results/m8_bench_done.txt
