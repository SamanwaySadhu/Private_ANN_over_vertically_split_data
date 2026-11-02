#!/bin/bash
# Runs the HE benchmark: full table (OMP_NUM_THREADS=1) + thread scaling (largest m=8) and merges into he_calib.json
set -e
cd "$(dirname "$0")"
REPS=${REPS:-20}
OMP_NUM_THREADS=1 ./he_bench full $REPS > he_full.tmp.json
for t in 1 8 64; do OMP_NUM_THREADS=$t ./he_bench scale $REPS > he_scale_$t.tmp.json; done
python3 -I - <<'PY'
import json
out = {"description": "OpenFHE BFVRNS m-of-m threshold calibration. configs[batch].by_m[m]; times in ms (median of reps), sizes in bytes (cereal binary).",
       "full_run": json.load(open("he_full.tmp.json")), "thread_scaling_m8": {}}
for t in (1, 8, 64):
    out["thread_scaling_m8"][str(t)] = json.load(open(f"he_scale_{t}.tmp.json"))
json.dump(out, open("he_calib.json", "w"), indent=1)
PY
rm -f he_full.tmp.json he_scale_*.tmp.json
