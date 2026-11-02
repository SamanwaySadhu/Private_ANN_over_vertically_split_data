"""Server-side thread scaling of ONE query's 1-D reads, measured on synthetic data of the exact shapes
used by the protocol: server adds the m shares of (e - r) (numba, parallel) and computes A @ (e - r) mod p.
(In bench.py the share-summation ran in single-threaded numpy inside the simulator, which hides
multi-core scaling; this measures the real server step with all of it parallel.)"""
import glob
import json
import sys
import time

import numba as nb
import numpy as np
from numba import njit, prange

import fastops
from fastops import P, matvec_mod


@njit(parallel=True, cache=True)
def sum_mod(q):
    m, L = q.shape
    out = np.empty(L, np.uint64)
    for i in prange(L):
        s = np.uint64(0)
        for j in range(m):
            s += q[j, i]
        out[i] = s % np.uint64(P)
    return out


def one_read(a, n, K, m, T, rng):
    nb.set_num_threads(T)
    fastops.PARALLEL = T > 1
    A = rng.integers(0, 256, (a, n), dtype=np.uint32)
    q = rng.integers(0, P, (m, K * n), dtype=np.uint64)
    reps = 1
    best = 1e30
    for _ in range(3):
        t0 = time.perf_counter()
        qa = sum_mod(q).reshape(K, n)
        matvec_mod(A, qa.T)
        best = min(best, time.perf_counter() - t0)
    return best


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    for f in sorted(glob.glob("results/*_N*_m*_E*.json")):
        r = json.load(open(f))
        a_ = r["args"]
        sz = r["server_build"]["sizes"]
        N, m, s, Tg = a_["N"], a_["m"], a_["s"], a_["Tg"]
        Tb = a_["Tb"] or 2 * a_["E"]
        d = (sz["A"] - 3) // s - 4
        D0 = 2 * a_["M"]
        U = sz["U"]
        reads = [(sz["A"], U, 1, Tg), (d + 1, N + 1, 1, Tg), (2 * D0, N + 1, 1, Tb), (d + 1, N + 1, D0, Tb)]
        out = {}
        for T in (1, 8, 32, 64, 128, 448):
            if T == 1 and N * d > 2e8:
                continue
            tot = 0.0
            for a, n, K, cnt in reads:
                tot += cnt * one_read(a, n, K, m, T, rng)
            out[T] = tot
            print(r["tag"], T, round(tot, 3), flush=True)
        json.dump(out, open(f"results/kernel_{r['tag']}.json", "w"))
