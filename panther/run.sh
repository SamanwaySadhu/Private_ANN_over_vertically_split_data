#!/bin/bash
# Reproduce Panther-baseline results (same datasets / N / m as baseline/run.sh and hnsecw/run.sh). Needs the SIFT files (ANN_DATA, default ~/ann_data).
# u (clusters retrieved) is the recall knob: pick it from the sweep so recall@10 is comparable to the other protocols (~0.8-0.9).
cd "$(dirname "$0")"
PY=${PY:-python}
$PY pbench.py --dataset sift --N 100000 --m 4 --sweep_u 4,8,12,16,24 --nq 1000 | tee results/sweep_sift_N100000.txt
$PY pbench.py --dataset sift --N 1000000 --m 4 --sweep_u 4,8,12,16,24 --nq 1000 | tee results/sweep_sift_N1000000.txt
for cfg in "100000 4 ${U100K:-12}" "1000000 4 ${U1M:-12}"; do
  set -- $cfg
  tag=panther_sift_N$1_m$2_u$3
  $PY pbench.py --dataset sift --N $1 --m $2 --u $3 --nq 1000 --nperf 8 | tee results/log_$tag.txt
  $PY breakdown.py results/$tag.json > /dev/null
done
$PY compare.py
