"""Cost of the Sec. 4 Lagrange/binomial ID -> one-hot conversion (vsann.SecureANN.onehot,
onehot='lagrange') as a function of the domain size n. Each client performs the O(n^2) local
linear algebra on its own shares, so the measured call time is a (single-core) estimate of the
per-client cost of ONE conversion."""
import json
import time

import numpy as np

from vsann import MPC, Params, SecureANN, lag_tables

rows = []
for n in (32, 64, 128, 256, 512, 1024, 2048, 4096):
    mpc = MPC(4, seed=1)
    sec = SecureANN.__new__(SecureANN)
    sec.c, sec.prm = mpc, Params(N=10, d=4, m=4, onehot="lagrange")
    t0 = time.perf_counter()
    lag_tables(n)
    t_pre = time.perf_counter() - t0
    Z = mpc.share(n // 3)
    reps = 3 if n <= 1024 else 1
    t0 = time.perf_counter()
    for _ in range(reps):
        e = mpc.reveal(sec.onehot(Z, n))
    t = (time.perf_counter() - t0) / reps
    assert e[n // 3] == 1 and e.sum() == 1
    rows.append(dict(n=n, call_s=t, table_precompute_s=t_pre, table_bytes=3 * n * n * 8))
    print(rows[-1], flush=True)
x = np.log([r["n"] for r in rows[3:]])
y = np.log([r["call_s"] for r in rows[3:]])
slope = np.polyfit(x, y, 1)[0]
print("empirical exponent of time vs n:", slope)
json.dump(dict(rows=rows, exponent=float(slope)), open("results/lagrange_onehot.json", "w"))
