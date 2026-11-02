"""Recall@10 vs beam width E (Tb = 2E), mean over 3 builds, plain emulation of the bounded protocol."""
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
    name, N = sys.argv[1], int(sys.argv[2])
    D = load(name, N, 500)
    rows = []
    for E in (32, 64, 128, 256):
        sec, lib = [], []
        for seed in range(3):
            prm = Params(N=D["N"], d=D["d"], m=4, M=8, efc=100, E=E, Tb=2 * E, s=6,
                         rho=tuple(0.5 * 2 ** r for r in range(6)), seed=seed)
            srv = ServerScaled(D["X"], prm, procs=64)
            G.update(srv=srv, D=D)
            with mp.get_context("fork").Pool(32) as p:
                sec.append(float(np.mean(p.map(work, range(len(D["Q"]))))))
            lb = srv.hnswlib_index; lb.set_ef(E)
            lab, _ = lb.knn_query(D["Q"].astype(np.float32), k=10)
            lib.append(float(np.mean([len(set(l.tolist()) & set(g.tolist())) / 10 for l, g in zip(lab, D["gt_q"])])))
        rows.append(dict(E=E, secure_mean=np.mean(sec), secure_std=np.std(sec), hnswlib_mean=np.mean(lib)))
        print(rows[-1], flush=True)
    json.dump(rows, open(f"results/recall_vs_E_{name}_{N}.json", "w"))
