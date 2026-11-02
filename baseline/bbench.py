"""Baseline evaluation driver:  python bbench.py --dataset sift --N 100000 --nq 1000 --nperf 16

Stage 1  server preprocessing (hnswlib graph build + import, flat upper/lower tables)  -> times, sizes
Stage 2  accuracy on all queries: plain emulation of the bounded baseline (== secure run, verified on the
         performance sample) vs exact kNN, and vs the unbounded plaintext HNSW
Stage 3  secure runs of nperf queries over additive shares with full metering
Results -> baseline/results/<tag>.json  (read by bcost.py / breakdown.py)."""
import argparse
import json
import multiprocessing as mp
import os
import time

import numpy as np

import _path  # noqa: F401
from datasets import load
from vsann import Params
from bserver import BaselineServer
from bproto import plain_baseline
from bengine import run_query

HERE = os.path.dirname(os.path.abspath(__file__))
G = {}


def _acc_worker(qi):
    srv, D = G["srv"], G["D"]
    q = D["Q"][qi]
    res, info = plain_baseline(srv, q)
    return qi, res, srv.hnsw_exact(q, srv.prm.E, srv.prm.k), info


def _perf_worker(qi):
    srv, D = G["srv"], G["D"]
    t0 = time.perf_counter()
    res, mt = run_query(srv, D["Q"][qi], 1000 + qi)
    return qi, res, time.perf_counter() - t0, pack_meter(mt)


def pack_meter(mt):
    f = lambda d: {f"{k[0]}|{k[1]}" if isinstance(k, tuple) else str(k): (v.tolist() if hasattr(v, "tolist") else v)
                   for k, v in d.items()}
    return dict(cs=f(mt.cs), cr=f(mt.cr), ss=f(mt.ss), sr=f(mt.sr), fl=f(mt.fl), tsrv=f(mt.tsrv),
                tcli=f(mt.tcli), tsim=f(mt.tsim), cnt=f(mt.cnt),
                gc={n: dict(c) for n, c in mt.gc.items()}, gc_max=mt.gc_max)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="sift")
    ap.add_argument("--N", type=int, default=100000)
    ap.add_argument("--nq", type=int, default=1000, help="queries for accuracy")
    ap.add_argument("--nperf", type=int, default=16, help="queries run through the metered secure engine")
    ap.add_argument("--m", type=int, default=4)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--M", type=int, default=8)
    ap.add_argument("--efc", type=int, default=100)
    ap.add_argument("--E", type=int, default=64)
    ap.add_argument("--Tg", type=int, default=0, help="upper-phase step budget (moves + descents); 0 -> 3*top+3")
    ap.add_argument("--Tb", type=int, default=0, help="0 -> 2*E")
    ap.add_argument("--workers", type=int, default=min(64, os.cpu_count()))
    ap.add_argument("--tag", default="")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    Tb = a.Tb or 2 * a.E
    tag = a.tag or f"base_{a.dataset}_N{a.N}_m{a.m}_E{a.E}"
    out = {"args": vars(a), "tag": tag, "protocol": "baseline"}

    D = load(a.dataset, a.N, a.nq, a.k, a.seed)
    prm = Params(N=D["N"], d=D["d"], m=a.m, M=a.M, efc=a.efc, k=a.k, E=a.E, s=1, Tg=a.Tg, Tb=Tb, seed=a.seed)
    print(f"[{tag}] N={D['N']} d={D['d']} m={a.m} M={a.M} E={a.E} Tb={Tb}", flush=True)
    srv = BaselineServer(D["X"], prm)
    if a.Tg == 0:
        prm.Tg = 3 * srv.top + 3
        a.Tg = prm.Tg
        out["args"]["Tg"] = a.Tg
    print(f"[server] {srv.t} U={srv.U} layers={srv.top + 1}", flush=True)
    layer_nodes = [int((srv.lev >= l).sum() - (1 if l == 0 else 0)) for l in range(srv.top + 1)]
    sz = dict(layer_nodes=layer_nodes, U=int(srv.U), top=int(srv.top),
              raw_vectors_bytes=int(D["N"] * D["d"] * 4),
              Aup_bytes=int((srv.Aup_adj.size + srv.Aup_vec.size) * 4), Avec_bytes=int(srv.Avec.size * 4),
              Aadj_bytes=int(srv.Aadj.size * 4), hnswlib_index_bytes=int(srv.hnswlib_index.index_file_size()))
    sz["flattened_total_bytes"] = sz["Aup_bytes"] + sz["Avec_bytes"] + sz["Aadj_bytes"]
    out["server_build"] = dict(times=srv.t, sizes=sz)

    G.update(srv=srv, D=D)
    ctx = mp.get_context("fork")
    t0 = time.time()
    with ctx.Pool(a.workers) as pool:
        accres = sorted(pool.map(_acc_worker, range(len(D["Q"])), chunksize=4))
    print(f"[accuracy] {len(accres)} queries in {time.time() - t0:.1f}s", flush=True)
    rec = lambda res, gt: len(set(x - 1 for x in res) & set(gt.tolist())) / a.k
    r_f = [rec(r[1], D["gt_f"][r[0]]) for r in accres]
    r_x = [rec(r[2], D["gt_f"][r[0]]) for r in accres]
    idx = srv.hnswlib_index
    idx.set_ef(a.E)
    lab, _ = idx.knn_query(D["Q"].astype(np.float32), k=a.k)
    r_lib = [len(set(l.tolist()) & set(g.tolist())) / a.k for l, g in zip(lab, D["gt_q"])]
    out["accuracy"] = dict(
        k=a.k, nq=len(accres), recall_secure_vs_float_gt=float(np.mean(r_f)),
        recall_secure_vs_quantized_gt=float(np.mean([rec(r[1], D["gt_q"][r[0]]) for r in accres])),
        recall_exact_greedy_hnsw_vs_float_gt=float(np.mean(r_x)), recall_hnswlib_vs_quantized_gt=float(np.mean(r_lib)),
        frac_queries_recall1=float(np.mean(np.array(r_f) == 1)), min_recall=float(min(r_f)),
        upper_unfinished_rate=float(np.mean([r[3]["upper_unfinished"] for r in accres])),
        mean_upper_moves=float(np.mean([r[3]["moves"] for r in accres])),
        beam_live_end_rate=float(np.mean([r[3]["beam_live_end"] for r in accres])))
    print("[accuracy]", {k: round(v, 4) for k, v in out["accuracy"].items() if isinstance(v, float)}, flush=True)

    nperf = min(a.nperf, len(D["Q"]))
    t0 = time.time()
    with ctx.Pool(min(a.workers, nperf)) as pool:
        perf = sorted(pool.map(_perf_worker, range(nperf), chunksize=1))
    same = sum(perf[i][1] == accres[perf[i][0]][1] for i in range(nperf))
    print(f"[secure] {nperf} queries, wall {time.time() - t0:.1f}s, identical to plain emulation: {same}/{nperf}", flush=True)
    out["secure"] = dict(nperf=nperf, identical=int(same), meters=[p[3] for p in perf], wall=[p[2] for p in perf],
                         recall_on_sample=float(np.mean([rec(p[1], D["gt_f"][p[0]]) for p in perf])))
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    with open(os.path.join(HERE, "results", f"{tag}.json"), "w") as f:
        json.dump(out, f, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(f"wrote baseline/results/{tag}.json")


if __name__ == "__main__":
    main()
