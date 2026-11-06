"""Tiptoe-baseline evaluation driver:
    python tbench.py --dataset sift --N 100000 --m 4 --bits 4 --nq 1000 --nperf 8
    python tbench.py --dataset synth --N 20000 --d 32 --nq 200 --nperf 4          (no dataset files needed)
    python tbench.py --dataset sift --N 1000000 --sweep_bits 3,4,5            (recall vs bits only, no secure runs)

Stage 1  server build (k-means, boundary duplication, quantised ranking matrix, id/norm matrix)
Stage 2  accuracy on all queries: plain emulation vs exact kNN
Stage 3  secure runs of nperf queries over additive ring shares among the m clients (server holds the corpus), full metering,
         with the check secure == plain emulation
Results -> tiptoe/results/<tag>.json"""
import argparse
import json
import multiprocessing as mp
import os
import time

import numpy as np

import _path  # noqa: F401
from datasets import load, exact_knn
from tserver import TParams, TServer
from tproto import plain_search
from tengine import run_query

HERE = os.path.dirname(os.path.abspath(__file__))
G = {}


def load_any(name, N, nq, k, seed, d):
    if name != "synth":
        return load(name, N, nq, k, seed)
    rng = np.random.default_rng(seed)
    cen = rng.integers(0, 256, (32, d))
    gen = lambda n: np.clip(cen[rng.integers(0, 32, n)] + rng.normal(0, 18, (n, d)), 0, 255).round().astype(np.int64)
    X, Q = gen(N), gen(nq)
    return dict(name=name, N=N, d=d, X=X, Q=Q, Xf=X.astype(np.float32), Qf=Q.astype(np.float32),
                gt_f=exact_knn(X.astype(np.float32), Q.astype(np.float32), k), gt_q=exact_knn(X, Q, k))


def _acc_worker(qi):
    return qi, plain_search(G["srv"], G["D"]["Q"][qi])


def _perf_worker(qi):
    res, mt, wall = run_query(G["srv"], G["D"]["Q"][qi], 1000 + qi)
    return qi, res, wall, pack(mt)


def pack(mt):
    f = lambda d: {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in d.items()}
    return dict(sent=f(mt.sent), recv=f(mt.recv), fl=f(mt.fl), cnt=f(mt.cnt), gc={n: dict(g) for n, g in mt.gc.items()},
                shape=mt.shape)


def pmap(fn, args, workers, chunk):
    if "fork" in mp.get_all_start_methods() and workers > 1:
        with mp.get_context("fork").Pool(workers) as pool:
            return pool.map(fn, args, chunksize=chunk)
    return [fn(a) for a in args]


def recall(res, gt, k):
    return len(set(x - 1 for x in res) & set(gt.tolist())) / k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="sift")
    ap.add_argument("--N", type=int, default=100000)
    ap.add_argument("--d", type=int, default=32, help="only for --dataset synth")
    ap.add_argument("--nq", type=int, default=1000)
    ap.add_argument("--nperf", type=int, default=8)
    ap.add_argument("--m", type=int, default=4)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--C", type=int, default=0, help="clusters; 0 -> round(sqrt(N))")
    ap.add_argument("--bits", type=int, default=4, help="embedding precision (paper: 4)")
    ap.add_argument("--dup", type=float, default=0.2, help="fraction of vectors stored in two clusters (paper: 0.2)")
    ap.add_argument("--cap", type=float, default=1.5, help="cluster capacity factor over the mean size")
    ap.add_argument("--no_drop_low", action="store_true", help="disable the low-order-bit dropping of App. A.3")
    ap.add_argument("--sweep_bits", default="", help="comma list: print recall for each precision and exit")
    ap.add_argument("--workers", type=int, default=min(16, os.cpu_count() or 1))
    ap.add_argument("--tag", default="")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    D = load_any(a.dataset, a.N, a.nq, a.k, a.seed, a.d)
    bs = [int(x) for x in a.sweep_bits.split(",")] if a.sweep_bits else [a.bits]
    for bt in bs:
        tag = a.tag or f"tiptoe_{a.dataset}_N{a.N}_m{a.m}_b{bt}"
        prm = TParams(N=D["N"], d=D["d"], m=a.m, k=a.k, C=a.C, bits=bt, dup=a.dup, cap=a.cap, seed=a.seed, drop_low=not a.no_drop_low)
        out = {"args": dict(vars(a), N=D["N"], d=D["d"], bits=bt, C=prm.C), "tag": tag, "protocol": "tiptoe"}
        print(f"[{tag}] N={D['N']} d={D['d']} server + {a.m} clients, C={prm.C} clusters, {bt}-bit embeddings, p=2^{prm.lt}", flush=True)
        srv = TServer(D["X"], prm)
        info = srv.size_info()
        print(f"[server] {info} build {srv.t['total']:.1f}s", flush=True)
        out["server_build"] = dict(times=srv.t, sizes=info)
        G.update(srv=srv, D=D)
        t0 = time.time()
        accres = dict(pmap(_acc_worker, range(len(D["Q"])), a.workers, 4))
        r = [recall(accres[i], D["gt_f"][i], a.k) for i in range(len(D["Q"]))]
        out["accuracy"] = dict(k=a.k, nq=len(r), recall_secure_vs_float_gt=float(np.mean(r)),
                               frac_queries_recall1=float(np.mean(np.array(r) == 1)), min_recall=float(min(r)),
                               frac_ge_0_9=float(np.mean(np.array(r) >= 0.9)))
        print(f"[accuracy] {len(r)} queries in {time.time() - t0:.1f}s recall@{a.k} = {np.mean(r):.4f}", flush=True)
        if a.sweep_bits:
            continue
        nperf = min(a.nperf, len(D["Q"]))
        t0 = time.time()
        perf = sorted(pmap(_perf_worker, range(nperf), min(a.workers, nperf), 1))
        same = sum(perf[i][1] == accres[perf[i][0]] for i in range(nperf))
        print(f"[secure] {nperf} queries, wall {time.time() - t0:.1f}s, identical to plain emulation: {same}/{nperf}", flush=True)
        out["secure"] = dict(nperf=nperf, identical=int(same), meters=[p[3] for p in perf], wall=[p[2] for p in perf],
                             recall_on_sample=float(np.mean([recall(p[1], D["gt_f"][p[0]], a.k) for p in perf])))
        os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
        with open(os.path.join(HERE, "results", f"{tag}.json"), "w") as f:
            json.dump(out, f, default=lambda o: o.item() if hasattr(o, "item") else str(o))
        print(f"wrote tiptoe/results/{tag}.json")


if __name__ == "__main__":
    main()
