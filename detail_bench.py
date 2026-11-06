"""Per-operation timing of every client-side and server-side step of the reads / Beaver products, with all cores.

For each distinct read shape (a, n, K) of the executed run, and each thread count T, measure (best of 5):
  client (ONE client's work):  mask  = (e_i - r_i) mod p over K*n entries        [fastops sub_mod]
                               post  = [y] + [h]  over a*K entries
  server:                      prep  = add the m shares of (e - r), split in 16-bit halves   [_prep]
                               tiled = cache-tiled A @ q                                      [_tiled]
                               reduce= sum of chunk partials                                  [_reduce]
For each Beaver call size L:   open  = x-A, y-B (client)   finish = C + eB + fA (+ef) (client)   dsum = sum over d
For each Lagrange conversion R: lag = build binomial*tau^k table + 2 mat-vecs (one client)
Usage: python detail_bench.py <tag> [T1,T2,...]"""
import json
import sys
import time

import numba as nb
import numpy as np

import fastops
from fastops import P, _prep, _tiled, _reduce, JB

TAG = sys.argv[1]
TS = [int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "8,448").split(",")]
r = json.load(open(f"results/{TAG}.json"))
m = r["args"]["m"]
cnt = r["secure"]["meters"][0]["cnt"]
reads = {tuple(int(x) for x in k.split(":")[1:]): v for k, v in cnt.items() if k.startswith("rs:")}
bv = {}
for k, v in cnt.items():
    if k.startswith("bv:"):
        _, cat, L = k.split(":")
        bv[(cat, int(L))] = v
lag = {int(k.split(":")[1]): v for k, v in cnt.items() if k.startswith("lag_conv:")}
rng = np.random.default_rng(0)


def best(fn, reps=5):
    fn()
    b = 1e30
    for _ in range(reps):
        t0 = time.perf_counter(); fn(); b = min(b, time.perf_counter() - t0)
    return b


out = dict(tag=TAG, m=m, reads={}, bv={}, lag={}, sel={}, node_q={}, T=TS)
fastops.PARALLEL = True
subm, bopen, bfin, slast, lagtm, mm = fastops._KP
for T in TS:
    nb.set_num_threads(T)
    for (a, n, K), calls in reads.items():
        A = rng.integers(0, 256, (a, n), dtype=np.uint32)
        q = rng.integers(0, P, (m, K, n), dtype=np.uint64)
        E1 = rng.integers(0, P, K * n).astype(np.int64); R1 = rng.integers(0, P, K * n).astype(np.int64); o1 = np.empty(K * n, np.int64)
        t_mask = best(lambda: subm(E1, R1, o1))
        Qlo = np.empty((n, K), np.uint32); Qhi = np.empty((n, K), np.uint32)
        t_prep = best(lambda: _prep(q, K, n, Qlo, Qhi))
        nch = (n + JB - 1) // JB
        o = np.zeros((a, nch, K), np.uint64)
        t_tiled = best(lambda: _tiled(A, Qlo, Qhi, nch, o))
        res = np.empty((a, K), np.uint64)
        t_red = best(lambda: _reduce(o, res))
        y = rng.integers(0, P, (a, K)); h = rng.integers(0, P, (a, K))
        t_post = best(lambda: np.mod(y + h, P), 20)
        out["reads"].setdefault(f"{a}:{n}:{K}", dict(calls=calls))[str(T)] = dict(mask=t_mask, prep=t_prep, tiled=t_tiled, reduce=t_red, post=t_post)
        del A, q
    for (cat, L), calls in bv.items():
        X = rng.integers(0, P, (1, L)).astype(np.int64); A_ = rng.integers(0, P, (1, L)).astype(np.int64)
        Y = rng.integers(0, P, (1, L)).astype(np.int64); B_ = rng.integers(0, P, (1, L)).astype(np.int64)
        C_ = rng.integers(0, P, (1, L)).astype(np.int64)
        e = np.empty(L, np.int64); f = np.empty(L, np.int64); Z = np.empty((1, L), np.int64)
        t_open = best(lambda: bopen(X, A_, Y, B_, e, f), 20)
        t_fin = best(lambda: bfin(C_, e, f, A_, B_, Z), 20)
        t_sum = 0.0
        if cat == "beaver_dist":
            d = r["server_build"]["sizes"]["A"]
            Kd = max(1, L // 128)
            Zd = rng.integers(0, P, (1, Kd, L // Kd)).astype(np.int64); od = np.empty((1, Kd), np.int64)
            t_sum = best(lambda: slast(Zd, od), 20)
        out["bv"].setdefault(f"{cat}:{L}", dict(calls=calls))[str(T)] = dict(open=t_open, finish=t_fin, dsum=t_sum)
    for (cat, L), calls in bv.items():
        if cat != "beaver_sel":
            continue
        s_ = 6
        U_ = L // s_
        nq_, sopen, spart = fastops._NP[0], fastops._NP[1], fastops._NP[2]
        E1 = rng.integers(0, P, (1, U_)).astype(np.int64); SA1 = rng.integers(0, P, (1, U_)).astype(np.int64)
        Q1 = rng.integers(0, P, (1, s_, U_)).astype(np.int64); SB1 = rng.integers(0, P, (1, s_, U_)).astype(np.int64)
        ee = np.empty(U_, np.int64); ff = np.empty((s_, U_), np.int64)
        t_open = best(lambda: sopen(E1, SA1, Q1, SB1, ee, ff), 10)
        CH = 4096
        part = np.empty(1 * s_ * ((U_ + CH - 1) // CH), np.int64)
        t_part = best(lambda: spart(ee, ff, SA1, SB1, part, CH), 10)
        out["sel"].setdefault(str(L), dict(calls=calls))[str(T)] = dict(open=t_open, part=t_part)
        dd = 128
        A_all = rng.integers(-60, 60, (U_, s_, dd)).astype(np.int16)
        bb = rng.integers(0, 5000, (U_, s_)).astype(np.int64); ww = rng.integers(1000, 9000, (U_, s_)).astype(np.int64); km = rng.integers(-50, 0, (U_, s_)).astype(np.int64)
        xq = rng.integers(0, 256, dd).astype(np.int64); oq = np.empty((s_, U_), np.int64)
        lo_, hi_ = dd // m, 2 * (dd // m)
        out["node_q"][str(T)] = best(lambda: nq_(A_all, lo_, hi_, xq, bb, ww, km, 0, 128, 16, 16, 1, oq), 3)
        del A_all
    for R, nconv in lag.items():
        from vsann import lag_tables
        Cl, Bn, Dm = lag_tables(R)
        B_ = 1 << int(np.ceil(np.log2(max(2, m / 0.1))))
        tp = rng.integers(0, P, R).astype(np.int64); Tm = np.empty((R, R), np.int64)
        Ap = rng.integers(0, P, (R, 1)).astype(np.int64); zh = np.empty((R, 1), np.int64)
        Cg = Cl[:max(1, R // B_)].copy(); eh = np.empty((Cg.shape[0], 1), np.int64)
        t = best(lambda: (lagtm(Bn, Dm, tp, Tm), mm(Tm, Ap, zh), mm(Cg, zh, eh)), 3)
        out["lag"].setdefault(str(R), dict(calls=nconv))[str(T)] = dict(lag=t)
    print("T", T, "done", flush=True)
json.dump(out, open(f"results/detail_{TAG}.json", "w"))
print("wrote", f"results/detail_{TAG}.json")
