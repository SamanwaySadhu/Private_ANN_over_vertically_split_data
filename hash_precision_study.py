"""Mask-mode quantisation precision B vs m on fixed graphs: base (B = 2^ceil(log2 m)) vs finer B = 2^ceil(log2(m/0.1)),
alone and combined with the all-radii candidate evaluation. Same graph + tables + queries within a graph."""
import json, multiprocessing as mp, os, sys
import numpy as np
import recall_study as R
from datasets import load

ngraph, nq, E = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
D = load("sift", 1000000, nq, 10, 0)
out = []
for g in range(ngraph):
    class A: seed = 20 + g
    srv = R.build("mask", D, A, 8, os.cpu_count())
    R.G.update(srv=srv, D=D)
    srv.hnswlib_index.set_ef(E)
    lab, _ = srv.hnswlib_index.knn_query(D["Q"][:nq].astype(np.float32), k=10)
    lib = float(np.mean([len(set(l.tolist()) & set(x[:10].tolist())) / 10 for l, x in zip(lab, D["gt_q"])]))
    with mp.get_context("fork").Pool(os.cpu_count()) as pool:
        for m in (1, 2, 8, 16):
            for name, var in (("base", {}), ("fine B", dict(bfine=1)), ("all-radii", dict(allr=1)), ("all-radii + fine B", dict(allr=1, bfine=1)), ("oracle entry", dict(entry="oracle"))):
                r = R.evaluate(pool, srv, D, dict(mode="mask", prm=dict(E=E, Tb=2 * E, m=m), var=var), nq)
                line = dict(graph=g, m=m, E=E, variant=name, recall10=r["recall"][10], hnswlib=lib)
                out.append(line); print(json.dumps(line), flush=True)
                json.dump(out, open("results/hash_precision_study.json", "w"))
    del srv
