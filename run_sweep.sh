#!/bin/bash
# SIFT1M, DELPHI-style protocol, sequential runs
PY=~/miniconda3/envs/ann/bin/python
cd "$(dirname "$0")"
for m in 4 2 8; do for E in 64 32 128; do
  tag=sift_N1000000_m${m}_E${E}_mask
  if [ ! -s results/breakdown_${tag}.json ]; then
    if [ ! -s results/${tag}.json ]; then
      $PY bench.py --dataset sift --N 1000000 --nq 1000 --nperf 32 --m $m --E $E --mode mask --threads "" > results/log_${tag}.txt 2>&1
    fi
    $PY kernel_scaling_mask.py $tag > results/log_kernel_${tag}.txt 2>&1
    $PY mask_model.py $tag > /dev/null 2>&1
  fi
done; done
echo done > results/sweep_done.txt
