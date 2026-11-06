"""Why do some builds give much lower recall than plain HNSW on the same graph? Rebuild the SAME configuration
several times (hnswlib's multithreaded build is not deterministic, so each build is a different graph + new LSH draws) and
log, per build: plain hnswlib recall, protocol recall, protocol recall with the oracle entry point, and per-layer behaviour
of the LSH walk in the upper phase (E=64, m=8, mask-mode or pub-mode)."""
import dataclasses
import json
import multiprocessing as mp
import os
import sys
from collections import Counter, defaultdict

import numpy as np

import recall_study as R
from datasets import load

G = {}


def work(qi):
    srv, D, mode = G["srv"], G["D"], G["mode"]
    prm = dataclasses.replace(srv.prm, E=64, Tb=128)
    q = D["Q"][qi]
    rb, sb = R.run_query(srv, mode, q, prm, dict(trace=1))
    ro, _ = R.run_query(srv, mode, q, prm, dict(entry="oracle"))
    return qi, rb, sb, ro


if __name__ == "__main__":
    mode, nb, nq = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    D = load("sift", 1000000, nq, 10, 0)
    out = []
    for b in range(nb):
        class A: seed = int(sys.argv[4]) if len(sys.argv) > 4 else 1
        srv = R.build(mode, D, A, 8, os.cpu_count())
        G.update(srv=srv, D=D, mode=mode)
        with mp.get_context("fork").Pool(os.cpu_count()) as pool:
            res = pool.map(work, range(nq), chunksize=4)
        gt = D["gt_q"]
        rec = lambda r: np.mean([len(set(x - 1 for x in r[:10]) & set(gt[qi][:10].tolist())) / 10 for qi, r in enumerate(r)])
        rb = [x[1] for x in res]; ro = [x[3] for x in res]
        per = np.array([len(set(x - 1 for x in rb[i][:10]) & set(gt[i][:10].tolist())) / 10 for i in range(nq)])
        pero = np.array([len(set(x - 1 for x in ro[i][:10]) & set(gt[i][:10].tolist())) / 10 for i in range(nq)])
        srv.hnswlib_index.set_ef(64)
        lab, _ = srv.hnswlib_index.knn_query(D["Q"][:nq].astype(np.float32), k=10)
        lib = np.mean([len(set(l.tolist()) & set(g[:10].tolist())) / 10 for l, g in zip(lab, gt)])
        layer = defaultdict(lambda: Counter())
        for _, _, st, _ in res:
            seen_l = set()
            for (l, found, gam) in st["trace"]:
                layer[l]["steps"] += 1
                layer[l]["found"] += found
                layer[l]["moved"] += gam
                seen_l.add(l)
            for l in seen_l:
                layer[l]["queries_reaching"] += 1
        eps = Counter(st["ep"] for _, _, st, _ in res)
        hard = per < 0.5
        rec_line = dict(build=b, mode=mode, hnswlib=float(lib), protocol=float(per.mean()), oracle_entry=float(pero.mean()), top=int(srv.top),
                        layer_nodes=[int((srv.lev >= l).sum() - (1 if l == 0 else 0)) for l in range(srv.top + 1)],
                        frac_queries_recall_lt_half=float(hard.mean()), frac_oracle_lt_half=float((pero < 0.5).mean()),
                        top_entries=[(int(e), c / nq) for e, c in eps.most_common(5)], distinct_entries=len(eps),
                        layers={int(l): dict(queries_reaching=c["queries_reaching"] / nq, steps_per_query=c["steps"] / nq,
                                             found_rate=c["found"] / max(1, c["steps"]), move_rate=c["moved"] / max(1, c["steps"])) for l, c in sorted(layer.items())},
                        ep_ratio_hard=float(np.mean([st["ep_d_ratio"] for (_, _, st, _), h in zip(res, hard) if h])) if hard.any() else None,
                        ep_ratio_easy=float(np.mean([st["ep_d_ratio"] for (_, _, st, _), h in zip(res, hard) if not h])))
        out.append(rec_line)
        print(json.dumps(rec_line), flush=True)
        del srv
        json.dump(out, open(f"results/diag_bad_build_{mode}.json", "w"))
