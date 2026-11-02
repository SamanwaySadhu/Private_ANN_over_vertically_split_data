"""End-to-end evaluation driver:  python bench.py --dataset sift --N 100000 --nq 1000 --nperf 64

Stage 1  server preprocessing (hnswlib graph build, flattening, LSH/cuckoo tables)   -> times, sizes
Stage 2  accuracy on all queries (plain emulation of the bounded protocol == secure run; verified
         on the performance sample) vs exact kNN, hnswlib, exact-greedy HNSW + LSH failure stats
Stage 3  secure runs of nperf queries over additive shares (1 thread / worker, all cores busy):
         per-primitive metering, per-party compute, loaded-machine server time
Stage 4  single-query latency of the real server kernels with T threads."""
import argparse
import json
import multiprocessing as mp
import os
import sys
import time
from collections import Counter

import numpy as np

import fastops
from datasets import load
from vsann import Params, plain_protocol
from scaled import ServerScaled
from engine import prepare, run_query

G = {}


def _acc_worker(qi):
    srv, D = G["srv"], G["D"]
    q = D["Q"][qi]
    pres, trace, info = plain_protocol(srv, q)
    st = Counter()
    for tr in trace:
        if not tr["rounding_ok"]:
            st["rounding_fail"] += 1
        if not tr["act"]:
            continue
        st["active"] += 1
        st["empty_all_radii"] += tr["found"] == 0
        st["accepted"] += tr["gam"]
        if tr["improve"]:
            st["improve_exists"] += 1
            if not tr["gam"]:
                st["missed"] += 1
        else:
            st["local_min"] += 1
    st["upper_unfinished"] += info["upper_unfinished"]
    st["beam_live_end"] += info["beam_live_end"]
    exact_greedy = srv.hnsw_search(q, srv.prm.E, srv.prm.k)
    return qi, pres, exact_greedy, dict(st)


def _perf_worker(qi):
    fastops.PARALLEL = False
    srv, D, prep = G["srv"], G["D"], G["prep"]
    t0 = time.perf_counter()
    res, mt = run_query(srv, prep, D["Q"][qi], 1000 + qi, mode=G["mode"])
    wall = time.perf_counter() - t0
    return qi, res, wall, pack_meter(mt)


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
    ap.add_argument("--nperf", type=int, default=64, help="queries run through the secure engine")
    ap.add_argument("--m", type=int, default=4)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--M", type=int, default=8)
    ap.add_argument("--efc", type=int, default=100)
    ap.add_argument("--E", type=int, default=64)
    ap.add_argument("--s", type=int, default=6)
    ap.add_argument("--Tg", type=int, default=12)
    ap.add_argument("--Tb", type=int, default=0, help="0 -> 2*E")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--threads", default="1,8,64")
    ap.add_argument("--tag", default="")
    ap.add_argument("--mode", default="he", choices=["he", "mask"], help="mask: HE only in preprocessing (DELPHI-style)")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    Tb = a.Tb or 2 * a.E
    tag = a.tag or f"{a.dataset}_N{a.N}_m{a.m}_E{a.E}" + ("_mask" if a.mode == "mask" else "")
    out = {"args": vars(a), "tag": tag}

    D = load(a.dataset, a.N, a.nq, a.k, a.seed)
    prm = Params(N=D["N"], d=D["d"], m=a.m, M=a.M, efc=a.efc, k=a.k, E=a.E, s=a.s, Tg=a.Tg, Tb=Tb,
                 rho=tuple(0.5 * 2 ** r for r in range(a.s)), seed=a.seed)
    print(f"[{tag}] N={D['N']} d={D['d']} m={a.m} M={a.M} E={a.E} Tb={Tb}", flush=True)
    t0 = time.time()
    srv = ServerScaled(D["X"], prm, procs=a.workers)
    print(f"[server] built in {time.time() - t0:.1f}s  {srv.t}  U={srv.U} layers={srv.top + 1}", flush=True)
    prep = prepare(srv, mask=a.mode == "mask")
    bs = srv.build_stats
    layer_nodes = [int((srv.lev >= l).sum() - (1 if l == 0 else 0)) for l in range(srv.top + 1)]
    edges = [sum(len(x) for x in srv.nb[l]) for l in range(srv.top + 1)]
    sz = dict(
        graph_edges=edges, layer_nodes=layer_nodes,
        graph_bytes_ids=int(sum(edges) * 4),
        hnswlib_index_bytes=int(srv.hnswlib_index.index_file_size()),
        theta_bytes=int(srv.theta.size * 4), Dtab_bytes=int(sum(t.size for t in srv.Dtab) * 4),
        Avec_bytes=int(srv.Avec.size * 4), Aadj_bytes=int(srv.Aadj.size * 4),
        raw_vectors_bytes=int(D["N"] * D["d"] * 4), U=int(srv.U), ncol=prm.ncol, H=prm.H, A=int(srv.theta.shape[0]))
    sz["flattened_total_bytes"] = sz["theta_bytes"] + sz["Dtab_bytes"] + sz["Avec_bytes"] + sz["Aadj_bytes"]
    out["server_build"] = dict(times=srv.t, stats=dict(bs), sizes=sz, wmax=prep[3])

    # ---------------- accuracy (all queries) ----------------
    G.update(srv=srv, D=D, prep=prep, mode=a.mode)
    fastops.PARALLEL = False
    ctx = mp.get_context("fork")
    t0 = time.time()
    with ctx.Pool(a.workers) as pool:
        accres = sorted(pool.map(_acc_worker, range(len(D["Q"])), chunksize=1))
    print(f"[accuracy] {len(accres)} queries in {time.time() - t0:.1f}s", flush=True)
    rec = lambda res, gt: len(set(x - 1 for x in res) & set(gt.tolist())) / a.k
    r_sec_f = [rec(r[1], D["gt_f"][r[0]]) for r in accres]
    r_sec_q = [rec(r[1], D["gt_q"][r[0]]) for r in accres]
    r_ex_f = [rec(r[2], D["gt_f"][r[0]]) for r in accres]
    idx = srv.hnswlib_index
    idx.set_ef(a.E)
    lab, _ = idx.knn_query(D["X"][:0].astype(np.float32).reshape(0, D["d"]) if False else D["Q"].astype(np.float32), k=a.k)
    r_lib_q = [len(set(l.tolist()) & set(g.tolist())) / a.k for l, g in zip(lab, D["gt_q"])]
    agg = Counter()
    for r in accres:
        agg.update(r[3])
    out["accuracy"] = dict(
        k=a.k, nq=len(accres),
        recall_secure_vs_float_gt=float(np.mean(r_sec_f)), recall_secure_vs_quantized_gt=float(np.mean(r_sec_q)),
        recall_exact_greedy_hnsw_vs_float_gt=float(np.mean(r_ex_f)), recall_hnswlib_vs_quantized_gt=float(np.mean(r_lib_q)),
        frac_queries_recall1=float(np.mean(np.array(r_sec_f) == 1)), min_recall=float(min(r_sec_f)),
        lsh=dict(agg), quantization_note="sift: exact integers; gist: global 8-bit quantisation",
        lsh_failure_rate=agg["missed"] / max(1, agg["improve_exists"]),
        lsh_empty_rate=agg["empty_all_radii"] / max(1, agg["active"]),
        bucket_cap_loss=1 - bs["kept"] / max(1, bs["points"]))
    print("[accuracy]", {k: round(v, 4) for k, v in out["accuracy"].items() if isinstance(v, float)}, flush=True)

    # ---------------- secure runs, machine loaded ----------------
    nperf = min(a.nperf, len(D["Q"]))
    t0 = time.time()
    with ctx.Pool(min(a.workers, nperf)) as pool:
        perf = sorted(pool.map(_perf_worker, range(nperf), chunksize=1))
    wall_all = time.time() - t0
    same = sum(perf[i][1] == accres[perf[i][0]][1] for i in range(nperf))
    print(f"[secure] {nperf} queries, wall {wall_all:.1f}s, identical to plain emulation: {same}/{nperf}", flush=True)
    out["secure"] = dict(nperf=nperf, wall_total=wall_all, identical=int(same), workers=min(a.workers, nperf),
                         meters=[p[3] for p in perf], wall=[p[2] for p in perf])
    out["secure"]["recall_on_sample"] = float(np.mean([rec(p[1], D["gt_f"][p[0]]) for p in perf]))

    # ---------------- thread scaling of single-query latency (parent process, real kernels) ----------
    fastops.PARALLEL = True
    lat = {}
    for T in [int(x) for x in a.threads.split(",") if x]:
        fastops.set_threads(T)
        if T == 1:
            fastops.PARALLEL = False
        else:
            fastops.PARALLEL = True
        ts = []
        for qi in range(1 if D["N"] * D["d"] > 5e7 else 3):
            _, mt = run_query(srv, prep, D["Q"][qi], 7 + qi, mode=a.mode)
            ts.append(sum(mt.tsrv.values()))
        lat[T] = float(np.median(ts))
        print(f"[latency] server read1d compute with {T} threads: {lat[T]:.3f}s", flush=True)
    out["server_compute_by_threads"] = lat
    with open(f"results/{tag}.json", "w") as f:
        json.dump(out, f, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print(f"wrote results/{tag}.json")


if __name__ == "__main__":
    main()
