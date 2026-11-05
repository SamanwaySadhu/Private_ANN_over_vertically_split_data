#!/bin/bash
# Reproduce HNSecW-baseline results (same configurations as baseline/run.sh). Interpreter: the venv used for the main code.
cd "$(dirname "$0")"
PY=${PY:-python}
for cfg in "100000 4 64" "1000000 4 64"; do
  set -- $cfg
  tag=hnsecw_sift_N$1_m$2_E$3
  $PY hbench.py --dataset sift --N $1 --m $2 --E $3 --nq 1000 --nperf 8 | tee results/log_$tag.txt
  $PY breakdown.py results/$tag.json > /dev/null
done
$PY compare.py
