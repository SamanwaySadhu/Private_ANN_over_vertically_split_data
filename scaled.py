"""Server preprocessing at real-dataset scale: HNSW graph imported from hnswlib (multi-threaded
build), LSH dictionaries / theta table built in parallel over all cores."""
import multiprocessing as mp
import os
import time
from collections import Counter

import numpy as np

from vsann import Server, Params, lsh_key, P
from hnsw_import import build_hnswlib, parse_index

_G = {}


def _rows_worker(task):
    cid, rows = task
    srv, prm = _G["srv"], _G["prm"]
    rng = np.random.default_rng([prm.seed + 11, cid])
    s, d, ncol, A = prm.s, prm.d, prm.ncol, 3 + prm.s * (prm.d + 4)
    n = len(rows)
    theta = np.zeros((A, n), np.int64)
    Dt = np.zeros((4, prm.s, n, ncol), np.int64)          # fields v,k,i,n
    st_ = Counter()
    for ri, row in enumerate(rows):
        st = srv.row_state.get(int(row))
        real = st is not None and st[1] >= 1
        if st is not None:
            theta[0, ri], theta[1, ri] = st[0], st[1]
            theta[2, ri] = srv.psi[(st[0], st[1] - 1)] if real else 0
        if real:
            u, l = st
            nbrs = srv.nb[l][u]
            S = [u] + list(nbrs)
            base = max(float(np.sqrt(srv.d2(srv.X[u], nbrs)).mean()) if nbrs else 1.0, 1.0)
            perm = rng.permutation(len(S))
            XS = srv.X[S]
            for r in range(s):
                c0 = 3 + r * (d + 4)
                a = np.rint(prm.Sa * rng.standard_normal(d)).astype(np.int64)
                w = base * prm.rho[r]
                wI = max(1, int(round(prm.Sw * w)))
                bI = int(rng.integers(0, max(1, int(prm.Sa * w))))
                keys = lsh_key(prm, a, bI, wI, XS)
                seen, items = set(), []
                for pi in perm:
                    kk = int(keys[pi])
                    if kk not in seen:
                        seen.add(kk)
                        items.append((kk, S[pi], srv.psi[(S[pi], l)]))
                st_["points"] += len(S)
                st_["kept"] += len(items)
                s1, s2, table, stash, att = srv.build_dict(items, rng)
                st_["cuckoo_retries"] += att - 1
                st_["stash_used"] += len(stash)
                for j, it in enumerate(table):
                    if it is not None:
                        Dt[0, r, ri, j], Dt[1, r, ri, j] = 1, it[0] % P
                        Dt[2, r, ri, j], Dt[3, r, ri, j] = it[1], it[2]
                for j, it in enumerate(stash):
                    cj = prm.H + j
                    Dt[0, r, ri, cj], Dt[1, r, ri, cj] = 1, it[0] % P
                    Dt[2, r, ri, cj], Dt[3, r, ri, cj] = it[1], it[2]
                theta[c0:c0 + d, ri] = a % P
                theta[c0 + d, ri], theta[c0 + d + 1, ri] = bI, wI
                theta[c0 + d + 2, ri], theta[c0 + d + 3, ri] = s1, s2
        else:                                   # dummy / terminal constants (a=0,b=0,w=1)
            for r in range(s):
                c0 = 3 + r * (d + 4)
                theta[c0 + d + 1, ri] = 1
                theta[c0 + d + 2, ri] = int(rng.integers(1, 1 << 29))
                theta[c0 + d + 3, ri] = int(rng.integers(1, 1 << 29))
    return cid, theta, Dt, st_


class ServerScaled(Server):
    """vsann.Server with an imported hnswlib graph and process-parallel table construction."""

    def __init__(self, Xdata, prm, procs=None):
        self.prm = prm
        self.rng = np.random.default_rng(prm.seed + 1)
        N, d = Xdata.shape
        self.X = np.vstack([np.zeros((1, d), np.int64), Xdata.astype(np.int64)])
        self.nrm = (self.X ** 2).sum(1)
        self.t = {}
        t0 = time.time()
        idx, t_add = build_hnswlib(Xdata, prm.M, prm.efc, prm.seed)
        self.t["hnsw_build"] = t_add
        self.hnswlib_index = idx
        t1 = time.time()
        labels, levels, nb, enter, maxlevel = parse_index(idx, d)
        self.t["graph_import"] = time.time() - t1
        lab2id = labels + 1                                    # protocol ids 1..N
        lev = np.zeros(N + 1, int)
        lev[lab2id] = levels
        self.lev = lev
        L = int(lev.max())
        self.nb = [[[] for _ in range(N + 1)] for _ in range(L + 1)]
        for l, dct in nb.items():
            for i, arr in dct.items():
                self.nb[l][int(lab2id[i])] = [int(lab2id[j]) for j in arr]
        self.ep, self.top = int(lab2id[enter]), int(maxlevel)
        t2 = time.time()
        self.flatten_parallel(procs or os.cpu_count())
        self.t["flatten_tables"] = time.time() - t2
        self.t["server_total"] = time.time() - t0

    def flatten_parallel(self, procs):
        prm, rng = self.prm, self.rng
        N, d, s, ncol = prm.N, prm.d, prm.s, prm.ncol
        top = self.top
        states = [(u, l) for l in range(top, 0, -1) for u in range(1, N + 1) if self.lev[u] >= l]
        term = [(u, 0) for u in range(1, N + 1) if self.lev[u] >= 1]
        allst = states + term
        rows = rng.permutation(len(allst)) + 1
        self.psi = {st: int(r) for st, r in zip(allst, rows)}
        U = len(allst) + 1
        self.U = U
        self.row_state = {v: k for k, v in self.psi.items()}
        A = 3 + s * (d + 4)
        self.theta = np.zeros((A, U), np.int64)
        Dt = np.zeros((4, s, U, ncol), np.int64)
        _G["srv"], _G["prm"] = self, prm
        chunk = max(8, U // (procs * 4) + 1)
        tasks = [(c, np.arange(a, min(a + chunk, U))) for c, a in enumerate(range(0, U, chunk))]
        self.build_stats = Counter()
        with mp.get_context("fork").Pool(procs) as pool:
            for cid, th, dt, st_ in pool.imap_unordered(_rows_worker, tasks):
                r0 = tasks[cid][1][0]
                r1 = r0 + th.shape[1]
                self.theta[:, r0:r1] = th
                Dt[:, :, r0:r1, :] = dt
                self.build_stats.update(st_)
        self.Dtab = [Dt[:, r] for r in range(s)]                           # each (4,U,ncol)
        self.Avec = np.vstack([self.X.T, self.nrm[None, :]]) % P           # (d+1, N+1)
        D0 = prm.D0
        adj = np.zeros((2 * D0, N + 1), np.int64)
        for u in range(1, N + 1):
            lst = self.nb[0][u]
            adj[:len(lst), u] = lst
            adj[D0:D0 + len(lst), u] = 1
        self.Aadj = adj
