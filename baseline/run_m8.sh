#!/bin/bash
# baseline (no LSH / Lagrange / offline HE): SIFT1M, m=8, E=32,64,128 (same driver settings as run.sh)
cd "$(dirname "$0")"
PY=${PY:-$HOME/miniconda3/envs/ann/bin/python}
for E in 32 64 128; do
  tag=base_sift_N1000000_m8_E$E
  [ -s results/$tag.json ] || $PY bbench.py --dataset sift --N 1000000 --m 8 --E $E --nq 1000 --nperf 8 --workers 16 | tee results/log_$tag.txt
  $PY breakdown.py results/$tag.json > /dev/null
done
echo done > results/m8_done.txt
