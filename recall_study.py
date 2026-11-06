"""Controlled recall study on SIFT1M (plain emulation == secure protocol, verified in bench.py).

For one build seed it builds the HNSW graph + flattened LSH tables ONCE and replays the same queries under
many configurations (m, E, Tg, Tb and optimisation variants), so differences are paired (same graph, same
tables, same queries). Each query returns its whole final beam (E ids sorted by distance), so recall@k for
every k <= E comes from one run.

  python recall_study.py --seed 0 --nq 3000 --part sweep     # recall vs (mode, m, E, k)
  python recall_study.py --seed 0 --nq 3000 --part ablate    # why the gap to plain HNSW + optimisations
"""
import argparse
import dataclasses
import json
import multiprocessing as mp
import os
import time

import numpy as np

import vsann as V
from datasets import load
from scaled import ServerScaled
from server_pub import ServerPublic
from plain_pub import client_quantize

G = {}
KS = (1, 5, 10, 20, 50, 100)


# ------------------------------------------------------------------ candidate lookup (mode specific)
def matches_mask(srv, prm, ireq, q, v_unused=None):
    """All (radius,probe) matches of the query hash in the dictionary of row ireq, in priority order."""
    s, d = prm.s, prm.d
    th = srv.theta[:, ireq]
    blk = th[3:].reshape(s, d + 4)
    a, b, w = V.signed(blk[:, :d]), blk[:, d], blk[:, d + 1]
    s1, s2 = blk[:, d + 2], blk[:, d + 3]
    hh = V.hash_blocks(prm, a, b, w, q).sum(1) // prm.Bq
    out = []
    for r in range(s):
        j = 0
        row = []
        for eps in range(2):
            for sd in (s1[r], s2[r]):
                col = V.phi(int(sd), hh[r] + eps, prm.H)
                row.append([V.signed(srv.Dtab[r][f, ireq, col]) for f in range(4)])
        for qq in range(prm.sigma):
            row.append([V.signed(srv.Dtab[r][f, ireq, prm.H + qq]) for f in range(4)])
        for j, (valid, key, idv, nxt) in enumerate(row):
            ok = valid == 1 and ((key == hh[r] + (0 if j < 2 else 1)) if j < 4 else key in (hh[r], hh[r] + 1))
            if ok:
                out.append((int(idv), int(nxt)))
    return out, int(th[2])


def matches_pub(srv, prm, ireq, hh):
    pub = srv.pub
    out = []
    for r in range(prm.s):
        K, off = pub["K"][r], pub["off"][r]
        for eps in (0, 1):
            col = int(hh[r]) + eps - pub["kmin"][r]
            if 0 <= col < K and srv.theta[off + col, ireq] == 1:
                out.append((int(srv.theta[off + K + col, ireq]), int(srv.theta[off + 2 * K + col, ireq])))
    return out, int(srv.theta[2, ireq])


@dataclasses.dataclass
class ParamsB(V.Params):
    """Params with an explicit LSH quantisation precision B (default: 2^ceil(log2 m))."""
    bq_over: int = 0

    @property
    def Bq(self):
        return self.bq_over or V.Params.Bq.fget(self)


# ------------------------------------------------------------------ one query
def run_query(srv, mode, q, prm, var):
    if var.get("bfine") and mode == "mask":                      # finer quantisation: B = 2^ceil(log2(m / 0.1))
        prm = ParamsB(**dataclasses.asdict(prm), bq_over=1 << int(np.ceil(np.log2(max(2, prm.m / 0.1)))))
    X = srv.X
    q = q.astype(np.int64)
    d2 = lambda x: int(((q - x) ** 2).sum())
    i, v, l = srv.entry_state()[0], srv.ep, srv.top
    dv = d2(X[v])
    act = int(l > 0)
    # oracle entry point of layer 0 (plain HNSW greedy descent) -- always computed for diagnostics
    cur = [srv.ep]
    for lc in range(srv.top, 0, -1):
        cur = [srv.search_layer(q, cur, 1, lc)[0][1]]
    ep_or = cur[0]
    if mode == "pub":
        qi = client_quantize(prm, srv.pub, q)
        hh = qi.sum(0) // srv.pub["B"]
    seeds = {}
    st = dict(acc=0, steps=0, empty=0)
    tr = []
    if var.get("entry") == "oracle":
        v, dv, act = ep_or, d2(X[ep_or]), 0
    for it in range(prm.Tg):
        ireq = i if act else 0
        if mode == "pub":
            ms, down = matches_pub(srv, prm, ireq, hh)
        else:
            ms, down = matches_mask(srv, prm, ireq, q)
        if act:
            st["steps"] += 1
            st["empty"] += int(len(ms) == 0)
        if var.get("allr") and ms:
            seen, best = set(), None
            for c, nx in ms:
                if c == 0 or c in seen:
                    continue
                seen.add(c)
                dc = d2(X[c])
                if act:
                    seeds[c] = dc
                if best is None or dc < best[1]:
                    best = (c, dc, nx)
            c, dc, nx = best if best else (0, d2(X[0]), 0)
            found = int(best is not None)
        else:
            found = int(len(ms) > 0)
            c, nx = ms[0] if ms else (0, 0)
            dc = d2(X[c])
            if act and c:
                seeds[c] = dc
        nv, nd, ni, nl, na, gam = V.upper_transition(act, found, c, dc, dv, nx, v, l, down)
        if act:
            tr.append((int(l), int(found), int(gam)))
        st["acc"] += gam
        v, dv, i, l, act = nv, nd, ni, nl, na
    st["ep_is_oracle"] = int(v == ep_or)
    st["ep_d_ratio"] = float(np.sqrt(dv) / max(1.0, np.sqrt(d2(X[ep_or]))))
    st["unfinished"] = int(act)
    # beam init: single entry point, or the whole upper-phase trail (every candidate whose distance was computed)
    E = prm.E
    W = np.zeros((4, E), np.int64); W[1, :], W[2, :] = V.INF, 1
    seeds[v] = dv
    if var.get("seed"):
        items = sorted(((dd, u) for u, dd in seeds.items() if u))[:E]
    else:
        items = [(dv, v)]
    for j, (dd, u) in enumerate(items):
        W[:, j] = (u, dd, 0, 1)
    Vv = np.zeros((2, prm.LV + len(items)), np.int64)
    for j, (dd, u) in enumerate(items):
        Vv[:, 0 if j == 0 else prm.LV + j] = (u, 1)
    usel, live = items[0][1], 1
    for t in range(prm.Tb):
        ids = srv.Aadj[:prm.D0, usel]
        nu = srv.Aadj[prm.D0:, usel]
        cd = ((X[ids] - q) ** 2).sum(1)
        W, Vv, usel, live = V.beam_step(W, Vv, usel, live, ids, cd, nu, t, prm)
    st["live_end"] = int(live)
    res = [int(x) for x in np.where(W[3] == 1, W[0], 0) if x != 0]
    if var.get("trace"):
        st["trace"] = tr
        st["ep"] = int(v)
    return res, st


def _work(task):
    qi, cfg = task
    srv, D = G["srv"], G["D"]
    prm = dataclasses.replace(srv.prm, **cfg["prm"])
    return qi, run_query(srv, cfg["mode"], D["Q"][qi], prm, cfg["var"])


# ------------------------------------------------------------------ evaluation
def evaluate(pool, srv, D, cfg, nq, chunk=4):
    t0 = time.time()
    out = pool.map(_work, [(qi, cfg) for qi in range(nq)], chunksize=chunk)
    res = [None] * nq
    stats = {}
    for qi, (r, st) in out:
        res[qi] = r
        for k, x in st.items():
            stats[k] = stats.get(k, 0) + x
    gt = D["gt_q"]
    rec = {}
    per10 = np.zeros(nq)
    for k in KS:
        if k > cfg["prm"].get("E", srv.prm.E):
            continue
        r = np.array([len(set(x - 1 for x in res[qi][:k]) & set(gt[qi][:k].tolist())) / k for qi in range(nq)])
        rec[k] = float(r.mean())
        if k == 10:
            per10 = r
    return dict(recall=rec, stats={k: x / nq for k, x in stats.items()}, per10=per10.tolist(), secs=time.time() - t0)


def plain_ref(srv, D, E, nq):
    idx = srv.hnswlib_index
    idx.set_ef(E)
    lab, _ = idx.knn_query(D["Q"][:nq].astype(np.float32), k=E)
    gt = D["gt_q"]
    out = {}
    for k in KS:
        if k <= E:
            out[k] = float(np.mean([len(set(lab[qi][:k].tolist()) & set(gt[qi][:k].tolist())) / k for qi in range(nq)]))
    return out


def build(mode, D, a, m, procs):
    prm = V.Params(N=D["N"], d=D["d"], m=m, M=8, efc=100, k=10, E=64, s=6, Tg=12, Tb=128,
                   rho=tuple(0.5 * 2 ** r for r in range(6)), seed=a.seed)
    t0 = time.time()
    srv = (ServerPublic if mode == "pub" else ServerScaled)(D["X"], prm, procs=procs)
    ln = [int((srv.lev >= l).sum() - (1 if l == 0 else 0)) for l in range(srv.top + 1)]
    print(f"[build] {mode} seed={a.seed} m={m} {time.time()-t0:.0f}s U={srv.U} top={srv.top} layer_nodes={ln}", flush=True)
    json.dump(dict(mode=mode, seed=a.seed, m=m, U=int(srv.U), top=int(srv.top), layer_nodes=ln, ep=int(srv.ep),
                   stats={k: int(v) for k, v in srv.build_stats.items()}, times=srv.t),
              open(f"results/build_info_s{a.seed}_{mode}_m{m}.json", "w"))
    return srv


def run_set(mode, srv, D, cfgs, a, rec_out, part):
    G.update(srv=srv, D=D)
    with mp.get_context("fork").Pool(a.workers) as pool:
        for name, cfg in cfgs:
            r = evaluate(pool, srv, D, cfg, a.nq)
            r.update(part=part, mode=mode, seed=a.seed, name=name, m=cfg["prm"].get("m", srv.prm.m), E=cfg["prm"]["E"],
                     Tg=cfg["prm"].get("Tg", 12), Tb=cfg["prm"]["Tb"], var=cfg["var"], nq=a.nq)
            rec_out.append(r)
            print(f"[{part}] {mode} s{a.seed} {name:<22} m={r['m']:>2} E={r['E']:>3}: " +
                  " ".join(f"@{k}={v:.4f}" for k, v in r["recall"].items()) + f"  ({r['secs']:.0f}s)", flush=True)
            json.dump(rec_out, open(a.out, "w"))
    for E in sorted({cfg["prm"]["E"] for _, cfg in cfgs}):       # plain hnswlib on THIS build's own graph
        rec_out.append(dict(part=part, mode="hnswlib_build", build=f"{mode}_m{srv.prm.m}", seed=a.seed, name="plain hnswlib",
                            m=srv.prm.m, E=E, Tg=0, Tb=0, var={}, nq=a.nq, recall=plain_ref(srv, D, E, a.nq), stats={}, per10=[], secs=0))
    json.dump(rec_out, open(a.out, "w"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--nq", type=int, default=3000)
    ap.add_argument("--N", type=int, default=1000000)
    ap.add_argument("--part", default="sweep", choices=["sweep", "ablate", "both"])
    ap.add_argument("--Es", default="32,64,128,256")
    ap.add_argument("--ms", default="1,2,4,8,16")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    a.out = a.out or f"results/recall_study_s{a.seed}_{a.part}.json"
    D = load("sift", a.N, a.nq, 100, a.seed)
    Es = [int(x) for x in a.Es.split(",")]
    rec_out = []
    base = lambda E, **kw: dict(mode=kw.pop("mode"), prm=dict(E=E, Tb=kw.pop("Tb", 2 * E), **kw.pop("prm", {})), var=kw.pop("var", {}))

    if a.part in ("sweep", "both"):
        srv = build("mask", D, a, 8, a.workers)
        cfgs = []
        for m in [int(x) for x in a.ms.split(",")]:
            for E in Es:
                cfgs.append((f"base m{m}", base(E, mode="mask", prm=dict(m=m))))
        run_set("mask", srv, D, cfgs, a, rec_out, "sweep")
        for E in Es:      # reference: plain hnswlib at ef=E
            rec_out.append(dict(part="sweep", mode="hnswlib", seed=a.seed, name="plain hnswlib", m=0, E=E, Tg=0, Tb=0,
                                var={}, nq=a.nq, recall=plain_ref(srv, D, E, a.nq), stats={}, per10=[], secs=0))
        json.dump(rec_out, open(a.out, "w"))
        del srv
        for m in (2, 4, 8):
            srv = build("pub", D, a, m, a.workers)
            run_set("pub", srv, D, [(f"base m{m}", base(E, mode="pub")) for E in Es], a, rec_out, "sweep")
            del srv

    if a.part in ("ablate", "both"):
        variants = [("base", {}, {}), ("Tg=24", {}, dict(Tg=24)), ("Tg=48", {}, dict(Tg=48)),
                    ("Tb=4E", {}, "Tb4"), ("oracle entry", dict(entry="oracle"), {}),
                    ("trail seeding", dict(seed=1), {}), ("all-radii", dict(allr=1), {}),
                    ("trail+all-radii", dict(seed=1, allr=1), {}),
                    ("trail+all-radii+Tg24", dict(seed=1, allr=1), dict(Tg=24))]
        for mode, m in (("mask", 8), ("pub", 8)):
            srv = build(mode, D, a, m, a.workers)
            cfgs = []
            for E in [e for e in Es if e <= 128]:
                for name, var, pr in variants:
                    tb = 4 * E if pr == "Tb4" else 2 * E
                    pr = {} if pr == "Tb4" else dict(pr)
                    cfgs.append((name, dict(mode=mode, prm=dict(E=E, Tb=tb, m=m, **pr), var=var)))
            run_set(mode, srv, D, cfgs, a, rec_out, "ablate")
            del srv


if __name__ == "__main__":
    main()
