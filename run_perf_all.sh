#!/bin/bash
# remaining performance runs: pub-mode m=2,4 (all E) and k-dependence checks (m=8, E=128, k=1 and k=100)
PY=~/miniconda3/envs/ann/bin/python
cd "$(dirname "$0")"
run() { # tag, extra args...
  tag=$1; shift
  [ -s results/${tag}.json ] || $PY bench.py --dataset sift --N 1000000 --nq 1000 --nperf 32 --mode pub --threads "" "$@" > results/log_${tag}.txt 2>&1
}
for m in 2 4; do for E in 32 64 128; do
  run sift_N1000000_m${m}_E${E}_pub --m $m --E $E &
done; done
run sift_N1000000_m8_E128_pub_k1 --m 8 --E 128 --k 1 --tag sift_N1000000_m8_E128_pub_k1 &
run sift_N1000000_m8_E128_pub_k100 --m 8 --E 128 --k 100 --tag sift_N1000000_m8_E128_pub_k100 &
wait
echo done > results/perf_all_done.txt
