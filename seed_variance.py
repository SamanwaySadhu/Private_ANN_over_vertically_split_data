"""Run-to-run variability of recall: the LSH tables / HNSW build are randomised, so repeat the
build with different seeds (plain emulation == secure run, verified in bench.py)."""
import json
import multiprocessing as mp
import sys

import numpy as np

from datasets import load
from scaled import ServerScaled
from vsann import Params, plain_protocol

G = {}


def work(qi):
    res, _, _ = plain_protocol(G["srv"], G["D"]["Q"][qi])
    return len(set(x - 1 for x in res) & set(G["D"]["gt_q"][qi].tolist())) / 10


if __name__ == "__main__":
    name, N, E = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    D = load(name, N, 500)
    out = []
    for seed in range(6):
        prm = Params(N=D["N"], d=D["d"], m=4, M=8, efc=100, E=E, Tb=2 * E, s=6,
                     rho=tuple(0.5 * 2 ** r for r in range(6)), seed=seed)
        srv = ServerScaled(D["X"], prm, procs=64)
        G.update(srv=srv, D=D)
        with mp.get_context("fork").Pool(32) as p:
            r = p.map(work, range(len(D["Q"])))
        lib = srv.hnswlib_index; lib.set_ef(E)
        lab, _ = lib.knn_query(D["Q"].astype(np.float32), k=10)
        rl = np.mean([len(set(l.tolist()) & set(g.tolist())) / 10 for l, g in zip(lab, D["gt_q"])])
        out.append(dict(seed=seed, secure=float(np.mean(r)), hnswlib=float(rl)))
        print(out[-1], flush=True)
    json.dump(out, open(f"results/seeds_{name}_{N}_E{E}.json", "w"))
    s = np.array([o["secure"] for o in out])
    print(f"secure recall@10 over seeds: mean {s.mean():.3f} std {s.std():.3f} min {s.min():.3f} max {s.max():.3f}")
