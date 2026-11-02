"""Server thread scaling of the read set of one query (shapes taken from the executed run's meter)."""
import json
import sys

import numpy as np

import fastops
from kernel_scaling import one_read

tag = sys.argv[1]
r = json.load(open(f"results/{tag}.json"))
m = r["args"]["m"]
reads = {}
for k, v in r["secure"]["meters"][0]["cnt"].items():
    if k.startswith("rs:"):
        _, a, n, K = k.split(":")
        reads[(int(a), int(n), int(K))] = v
rng = np.random.default_rng(0)
out = {}
for T in (8, 64, 128):
    out[T] = sum(cnt * one_read(a, n, K, m, T, rng) for (a, n, K), cnt in reads.items())
    print(tag, T, round(out[T], 2), flush=True)
json.dump(out, open(f"results/kernel_{tag}.json", "w"))
