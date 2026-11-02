#!/bin/bash
# Reproduce the baseline results (run from anywhere). Interpreter: the same conda env as the main protocol.
cd "$(dirname "$0")"
PY=${PY:-$HOME/miniconda3/envs/ann/bin/python}
for cfg in "100000 4 64" "1000000 4 32" "1000000 4 64" "1000000 4 128" "1000000 2 64"; do
  set -- $cfg
  tag=base_sift_N$1_m$2_E$3
  $PY bbench.py --dataset sift --N $1 --m $2 --E $3 --nq 1000 --nperf 8 --workers 16 | tee results/log_$tag.txt
  $PY breakdown.py results/$tag.json > /dev/null
done
