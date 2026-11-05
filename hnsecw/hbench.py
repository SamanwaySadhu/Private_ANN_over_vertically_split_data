"""HNSecW-baseline evaluation driver:
    python hbench.py --dataset sift --N 100000 --nq 1000 --nperf 8 --m 4 --E 64
    python hbench.py --dataset synth --N 20000 --d 32 --nq 200 --nperf 4        (no dataset files needed)

Stage 1  server tables (hnswlib build + import, per-layer padded/dummy tables)
Stage 2  accuracy on all queries: plain emulation of the bounded protocol vs exact kNN and vs hnswlib
Stage 3  secure runs of nperf queries over additive shares among server + m clients, full metering, with the check
         secure == plain emulation and the 'no physical row revealed twice' invariant
Results -> hnsecw/results/<tag>.json"""
import argparse
import json
import multiprocessing as mp
import os
import time

import numpy as np

import _path  # noqa: F401
from datasets import load, exact_knn
from hserver import HParams, HServer
from hproto import plain_search
from hengine import run_query

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
    res, mt, wall = run_query(G["srv"], G["D"]["Q"][qi], 5000 + qi)
    return qi, res, wall, pack(mt)


def pack(mt):
    f = lambda d: {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in d.items()}
    return dict(sent=f(mt.sent), recv=f(mt.recv), fl=f(mt.fl), cnt=f(mt.cnt), gc={n: dict(g) for n, g in mt.gc.items()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="sift")
    ap.add_argument("--N", type=int, default=100000)
    ap.add_argument("--d", type=int, default=32, help="only for --dataset synth")
    ap.add_argument("--nq", type=int, default=1000)
    ap.add_argument("--nperf", type=int, default=8)
    ap.add_argument("--m", type=int, default=4)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--M", type=int, default=8)
    ap.add_argument("--efc", type=int, default=100)
    ap.add_argument("--E", type=int, default=64, help="base-layer ef")
    ap.add_argument("--Tb", type=int, default=0, help="base-layer steps; 0 -> ceil(log2(N d/D0)) + E + 7")
    ap.add_argument("--workers", type=int, default=min(16, os.cpu_count()))
    ap.add_argument("--tag", default="")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    tag = a.tag or f"hnsecw_{a.dataset}_N{a.N}_m{a.m}_E{a.E}"
    D = load_any(a.dataset, a.N, a.nq, a.k, a.seed, a.d)
    prm = HParams(N=D["N"], d=D["d"], m=a.m, M=a.M, efc=a.efc, k=a.k, E=a.E, Tb=a.Tb, seed=a.seed)
    a.Tb = prm.T(0)
    out = {"args": dict(vars(a), N=D["N"], d=D["d"]), "tag": tag, "protocol": "hnsecw"}
    print(f"[{tag}] N={D['N']} d={D['d']} parties={prm.n} (server+{a.m} clients) M={a.M} E={a.E} Tb={a.Tb}", flush=True)
    srv = HServer(D["X"], prm)
    print(f"[server] {srv.t} layers={srv.top + 1} sizes={[L.R for L in srv.L]}", flush=True)
    shapes = srv.table_shapes()
    out["server_build"] = dict(times=srv.t, sizes=dict(
        layer_nodes=[int(L.R) for L in srv.L], top=int(srv.top), T=[int(L.T) for L in srv.L], tables=shapes,
        tables_bytes_per_party=int(sum(r * w * 4 for _, r, w in shapes)), raw_vectors_bytes=int(D["N"] * D["d"] * 4)))
    G.update(srv=srv, D=D)
    ctx = mp.get_context("fork")
    t0 = time.time()
    with ctx.Pool(a.workers) as pool:
        accres = dict(pool.map(_acc_worker, range(len(D["Q"])), chunksize=4))
    print(f"[accuracy] {len(accres)} queries in {time.time() - t0:.1f}s", flush=True)
    rec = lambda res, gt: len(set(x - 1 for x in res) & set(gt.tolist())) / a.k
    r_f = [rec(accres[i], D["gt_f"][i]) for i in range(len(D["Q"]))]
    idx = srv.hnswlib_index
    idx.set_ef(a.E)
    lab, _ = idx.knn_query(D["Q"].astype(np.float32), k=a.k)
    r_lib = [len(set(l.tolist()) & set(g.tolist())) / a.k for l, g in zip(lab, D["gt_q"])]
    out["accuracy"] = dict(k=a.k, nq=len(r_f), recall_secure_vs_float_gt=float(np.mean(r_f)),
                           recall_hnswlib_vs_quantized_gt=float(np.mean(r_lib)), frac_queries_recall1=float(np.mean(np.array(r_f) == 1)),
                           min_recall=float(min(r_f)), frac_ge_0_9=float(np.mean(np.array(r_f) >= 0.9)))
    print("[accuracy]", {k: round(v, 4) for k, v in out["accuracy"].items() if isinstance(v, float)}, flush=True)
    nperf = min(a.nperf, len(D["Q"]))
    t0 = time.time()
    with ctx.Pool(min(a.workers, nperf)) as pool:
        perf = sorted(pool.map(_perf_worker, range(nperf), chunksize=1))
    same = sum(perf[i][1] == accres[perf[i][0]] for i in range(nperf))
    print(f"[secure] {nperf} queries, wall {time.time() - t0:.1f}s, identical to plain emulation: {same}/{nperf}", flush=True)
    out["secure"] = dict(nperf=nperf, identical=int(same), meters=[p[3] for p in perf], wall=[p[2] for p in perf],
                         recall_on_sample=float(np.mean([rec(p[1], D["gt_f"][p[0]]) for p in perf])))
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    with open(os.path.join(HERE, "results", f"{tag}.json"), "w") as f:
        json.dump(out, f, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(f"wrote hnsecw/results/{tag}.json")


if __name__ == "__main__":
    main()
