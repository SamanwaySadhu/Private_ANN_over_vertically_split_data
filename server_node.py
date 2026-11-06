"""Server tables for the PER-NODE PUBLIC-LSH variant ("node" mode).

Like the baseline every upper-layer node-state row has its OWN random projection (a, b, w) per radius (w scaled to the node's
neighbour distances), but now the parameters are PUBLIC: the server hands the whole table (a,b,w, key offset) to all clients once.
Which row is visited stays secret (shared row index), so the clients
  1. quantise their own block for ALL rows once per query  (q_i[row, r] = floor(B t_i), doc private_selection_preprocessing_lsh Sec. 2),
  2. select the visited row's value privately in every upper iteration (Beaver dot product with the shared one-hot of the row),
  3. open tau = Q' - alpha and evaluate the fused truncation + one-hot by Lagrange interpolation locally (doc Sec. 4, 6).
The dictionary of each (row, radius) is directly addressed by  col = key - kmin[row, r]  inside a window of K_r columns
(K_r = max window over all rows), record = (valid, id, next); theta per row = [v, l, down] ++ per radius valid(K) ++ id(K) ++ next(K).
"""
import multiprocessing as mp
import os
import time
from collections import Counter

import numpy as np

from scaled import ServerScaled
from vsann import lsh_key, P

_G = {}
NSAMP = 3000                      # data sample used to size every row's key window
PAD = 0.25                        # window margin (fraction of the sampled key span) on each side
BFLOOR = float(os.environ.get("NODE_BFLOOR", 0.5))      # w >= BFLOOR * median(base) * rho_r  (bounds the key domain)


def _p1_worker(task):
    """Pass 1: per-row public parameters and key window."""
    cid, rows = task
    srv, prm = _G["srv"], _G["prm"]
    rng = np.random.default_rng([prm.seed + 31, cid])
    s, d, n = prm.s, prm.d, len(rows)
    a = np.zeros((n, s, d), np.int16)
    b = np.zeros((n, s), np.int64)
    w = np.full((n, s), prm.Sw, np.int64)
    lo = np.zeros((n, s), np.int64)
    W = np.ones((n, s), np.int64)
    Xs = _G["Xs"]
    for ri, row in enumerate(rows):
        st = srv.row_state.get(int(row))
        if st is None or st[1] < 1:
            continue
        u, l = st
        nbrs = srv.nb[l][u]
        base = max(float(np.sqrt(srv.d2(srv.X[u], nbrs)).mean()) if nbrs else 1.0, 1.0)
        base = max(base, BFLOOR * _G["base_med"])
        for r in range(s):
            av = np.rint(prm.Sa * rng.standard_normal(d)).astype(np.int64)
            wf = base * prm.rho[r]
            wI = max(1, int(round(prm.Sw * wf)))
            bI = int(rng.integers(0, max(1, int(prm.Sa * wf))))
            ks = lsh_key(prm, av, bI, wI, Xs)
            k0, k1 = int(ks.min()), int(ks.max())
            pad = max(2, int(np.ceil(PAD * (k1 - k0))))
            a[ri, r], b[ri, r], w[ri, r] = av, bI, wI
            lo[ri, r], W[ri, r] = k0 - pad, k1 - k0 + 2 * pad + 1
    return cid, a, b, w, lo, W


def _p2_worker(task):
    """Pass 2: directly addressed dictionaries."""
    cid, rows = task
    srv, prm, pub, nd = _G["srv"], _G["prm"], _G["pub"], _G["node"]
    rng = np.random.default_rng([prm.seed + 41, cid])
    s, A, n = prm.s, pub["A"], len(rows)
    th = np.zeros((A, n), np.int64)
    st_ = Counter()
    for ri, row in enumerate(rows):
        st = srv.row_state.get(int(row))
        if st is None:
            continue
        u, l = st
        th[0, ri], th[1, ri] = u, l
        if l < 1:
            continue
        th[2, ri] = srv.psi[(u, l - 1)]
        nbrs = srv.nb[l][u]
        S = [u] + list(nbrs)
        perm = rng.permutation(len(S))
        XS = srv.X[S]
        for r in range(s):
            keys = lsh_key(prm, nd["a"][row, r].astype(np.int64), int(nd["b"][row, r]), int(nd["w"][row, r]), XS)
            K, off = pub["K"][r], pub["off"][r]
            seen = set()
            for pi in perm:
                kk = int(keys[pi])
                st_["points"] += 1
                if kk in seen:
                    continue
                seen.add(kk)
                col = kk - int(nd["kmin"][row, r])
                if not (0 <= col < K):
                    st_["oor_items"] += 1
                    continue
                th[off + col, ri] = 1
                th[off + K + col, ri] = S[pi]
                th[off + 2 * K + col, ri] = srv.psi[(S[pi], l)]
                st_["kept"] += 1
    return cid, th, st_


class ServerNodePub(ServerScaled):
    HASH_EPS = float(os.environ.get("PUB_EPS", 0.1))      # B = 2^ceil(log2(m / eps))

    def flatten_parallel(self, procs):
        prm, rng = self.prm, self.rng
        N, d, s = prm.N, prm.d, prm.s
        top = self.top
        states = [(u, l) for l in range(top, 0, -1) for u in range(1, N + 1) if self.lev[u] >= l]
        term = [(u, 0) for u in range(1, N + 1) if self.lev[u] >= 1]
        allst = states + term
        rows = rng.permutation(len(allst)) + 1
        self.psi = {st: int(r) for st, r in zip(allst, rows)}
        U = len(allst) + 1
        self.U = U
        self.row_state = {v: k for k, v in self.psi.items()}
        samp = [states[i] for i in rng.choice(len(states), min(20000, len(states)), replace=False)]
        bases = [float(np.sqrt(self.d2(self.X[u], self.nb[l][u])).mean()) for (u, l) in samp if self.nb[l][u]]
        _G.update(srv=self, prm=prm, Xs=self.X[1:][rng.choice(N, min(NSAMP, N), replace=False)], base_med=max(float(np.median(bases)), 1.0))
        chunk = max(8, U // (procs * 4) + 1)
        tasks = [(c, np.arange(x, min(x + chunk, U))) for c, x in enumerate(range(0, U, chunk))]
        a = np.zeros((U, s, d), np.int16)
        b = np.zeros((U, s), np.int64)
        w = np.full((U, s), prm.Sw, np.int64)
        lo = np.zeros((U, s), np.int64)
        W = np.ones((U, s), np.int64)
        t0 = time.time()
        with mp.get_context("fork").Pool(procs) as pool:
            for cid, a_, b_, w_, lo_, W_ in pool.imap_unordered(_p1_worker, tasks):
                r0 = tasks[cid][1][0]
                r1 = r0 + a_.shape[0]
                a[r0:r1], b[r0:r1], w[r0:r1], lo[r0:r1], W[r0:r1] = a_, b_, w_, lo_, W_
        self.t["node_params"] = time.time() - t0
        real = np.zeros(U, bool)
        for r_, (u, l) in self.row_state.items():
            real[r_] = l >= 1
        K = [int(W[real, r].max()) for r in range(s)]
        kmin = lo - (np.array(K)[None, :] - W) // 2
        kmin[~real, :] = -(np.array(K) // 2)
        off, o = [], 3
        for r in range(s):
            off.append(o)
            o += 3 * K[r]
        B = 1 << int(np.ceil(np.log2(max(2, prm.m / self.HASH_EPS))))
        self.node = dict(a=a, b=b, w=w, kmin=kmin, W=W, real=real)
        self.pub = dict(K=K, off=off, A=o, B=B, w=w.max(0), kmin=None)
        _G.update(pub=self.pub, node=self.node)
        t0 = time.time()
        self.theta = np.zeros((o, U), np.int64)
        self.build_stats = Counter()
        with mp.get_context("fork").Pool(procs) as pool:
            for cid, th, st_ in pool.imap_unordered(_p2_worker, tasks):
                r0 = tasks[cid][1][0]
                self.theta[:, r0:r0 + th.shape[1]] = th
                self.build_stats.update(st_)
        self.t["node_dicts"] = time.time() - t0
        self.build_stats["win_max"] = max(K)
        self.Dtab = []
        self.Avec = np.vstack([self.X.T, self.nrm[None, :]]) % P
        D0 = prm.D0
        adj = np.zeros((2 * D0, N + 1), np.int64)
        for u in range(1, N + 1):
            lst = self.nb[0][u]
            adj[:len(lst), u] = lst
            adj[D0:D0 + len(lst), u] = 1
        self.Aadj = adj
