#!/bin/bash
# Reproduce the Tiptoe-baseline results (same datasets / N / m as baseline/run.sh, hnsecw/run.sh, panther/run.sh).
# Needs the SIFT files (ANN_DATA, default ~/ann_data); use --dataset synth for a smoke test without them.
# scan/MAC calibration (once):  g++ -std=c++17 -O3 -march=native -fopenmp calib/scan_bench.cpp -o calib/scan_bench && calib/scan_bench 1500 128000 2048 16000 > calib/scan_calib.json
cd "$(dirname "$0")"
PY=${PY:-python}
$PY tlwe_check.py
$PY tbench.py --dataset sift --N 100000 --m 4 --sweep_bits 3,4 --nq 1000 | tee results/sweep_sift_N100000.txt
$PY tbench.py --dataset sift --N 1000000 --m 4 --sweep_bits 3,4 --nq 1000 | tee results/sweep_sift_N1000000.txt
for cfg in "100000 4 4" "1000000 4 4"; do
  set -- $cfg
  tag=tiptoe_sift_N$1_m$2_b$3
  $PY tbench.py --dataset sift --N $1 --m $2 --bits $3 --nq 1000 --nperf 8 | tee results/log_$tag.txt
  $PY breakdown.py results/$tag.json > /dev/null
done
$PY compare.py
