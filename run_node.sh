#!/bin/bash
# per-node public-LSH variant (no GC hash): SIFT1M, m=8, E=32,64,128
PY=~/miniconda3/envs/ann/bin/python
cd "$(dirname "$0")"
for E in 32 64 128; do
  tag=sift_N1000000_m8_E${E}_node
  [ -s results/${tag}.json ] || $PY bench.py --dataset sift --N 1000000 --nq 10000 --nperf 32 --m 8 --E $E --mode node --threads "" > results/log_${tag}.txt 2>&1 &
done
wait
echo done > results/node_done.txt
