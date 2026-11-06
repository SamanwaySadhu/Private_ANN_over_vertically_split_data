"""Variance decomposition: ONE hnswlib graph, several independent draws of the LSH constants / dictionaries (only the
flattening is redone with a different seed). Compare with the build-to-build variance (new graph each time)."""
import dataclasses, json, multiprocessing as mp, os, sys, time
import numpy as np
import recall_study as R, vsann as V
from datasets import load

mode, ngraph, nlsh, nq = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
D = load("sift", 1000000, nq, 10, 0)
out = []
for g in range(ngraph):
    class A: seed = 10 + g
    srv = R.build(mode, D, A, 8, os.cpu_count())
    srv.hnswlib_index.set_ef(64)
    lab, _ = srv.hnswlib_index.knn_query(D["Q"][:nq].astype(np.float32), k=10)
    lib = float(np.mean([len(set(l.tolist()) & set(x[:10].tolist())) / 10 for l, x in zip(lab, D["gt_q"])]))
    for ls in range(nlsh):
        srv.prm = dataclasses.replace(srv.prm, seed=1000 + 7 * ls + g)
        srv.rng = np.random.default_rng(srv.prm.seed + 1)
        t0 = time.time(); srv.flatten_parallel(os.cpu_count())
        R.G.update(srv=srv, D=D)
        res = {}
        with mp.get_context("fork").Pool(os.cpu_count()) as pool:
            for name, var in (("base", {}), ("oracle", dict(entry="oracle")), ("all-radii+Tg24", dict(allr=1, seed=1)),):
                cfg = dict(mode=mode, prm=dict(E=64, Tb=128, Tg=24 if "Tg24" in name else 12), var=var)
                r = R.evaluate(pool, srv, D, cfg, nq)
                res[name] = r["recall"][10]
        line = dict(graph=g, lsh_seed=ls, hnswlib=lib, **res, flatten_s=time.time() - t0)
        out.append(line); print(json.dumps(line), flush=True)
        json.dump(out, open(f"results/lsh_seed_variance_{mode}.json", "w"))
