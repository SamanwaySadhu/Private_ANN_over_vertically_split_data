"""Server tables for the PUBLIC-LSH variant (doc: private_selection_preprocessing_lsh, Sec. 2-4, and
protocol spec Sec. 6.4).

  * one global projection (a_r, b_r, w_r) per radius r, identical for every upper node (public);
  * the dictionary of each (node-state row, radius) is DIRECTLY ADDRESSED by the integer LSH key:
    column = key - kmin_r, record = (valid, id, next).  No cuckoo placement, no secondary hash, no key check;
  * the combined table  theta  has per row:  [v, l, down] ++ for r: valid_r(K_r) ++ id_r(K_r) ++ next_r(K_r).
"""
import multiprocessing as mp
import os
import time
from collections import Counter

import numpy as np

from scaled import ServerScaled
from vsann import lsh_key, P

_G = {}


def _rows_worker(task):
    cid, rows = task
    srv, prm, pub = _G["srv"], _G["prm"], _G["pub"]
    rng = np.random.default_rng([prm.seed + 21, cid])
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
            keys = lsh_key(prm, pub["a"][r], int(pub["b"][r]), int(pub["w"][r]), XS)
            K, off = pub["K"][r], pub["off"][r]
            seen = set()
            for pi in perm:
                kk = int(keys[pi])
                st_["points"] += 1
                if kk in seen:
                    continue
                seen.add(kk)
                col = kk - pub["kmin"][r]
                th[off + col, ri] = 1
                th[off + K + col, ri] = S[pi]
                th[off + 2 * K + col, ri] = srv.psi[(S[pi], l)]
                st_["kept"] += 1
    return cid, th, st_


class ServerPublic(ServerScaled):
    HASH_EPS = float(os.environ.get("PUB_EPS", 0.1))      # normalised projection error: B = 2^ceil(log2(m/eps))

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
        # ---- global public LSH constants ----
        samp = [states[i] for i in rng.choice(len(states), min(20000, len(states)), replace=False)]
        bases = []
        for (u, l) in samp:
            nb_ = self.nb[l][u]
            if nb_:
                bases.append(float(np.sqrt(self.d2(self.X[u], nb_)).mean()))
        base_g = max(float(np.median(bases)), 1.0)
        a = np.stack([np.rint(prm.Sa * rng.standard_normal(d)).astype(np.int64) for _ in range(s)])
        w = np.array([max(1, int(round(prm.Sw * base_g * prm.rho[r]))) for r in range(s)], np.int64)
        b = np.array([int(rng.integers(0, max(1, int(prm.Sa * base_g * prm.rho[r])))) for r in range(s)], np.int64)
        kmin, K = [], []
        for r in range(s):
            keys = lsh_key(prm, a[r], int(b[r]), int(w[r]), self.X[1:])
            kmin.append(int(keys.min()) - 2)
            K.append(int(keys.max()) + 2 - kmin[-1] + 1)
        off, o = [], 3
        for r in range(s):
            off.append(o)
            o += 3 * K[r]
        B = 1 << int(np.ceil(np.log2(max(2, prm.m / self.HASH_EPS))))
        self.pub = dict(a=a, b=b, w=w, kmin=kmin, K=K, off=off, A=o, base_g=base_g, B=B)
        _G.update(srv=self, prm=prm, pub=self.pub)
        chunk = max(8, U // (procs * 4) + 1)
        tasks = [(c, np.arange(x, min(x + chunk, U))) for c, x in enumerate(range(0, U, chunk))]
        self.theta = np.zeros((o, U), np.int64)
        self.build_stats = Counter()
        with mp.get_context("fork").Pool(procs) as pool:
            for cid, th, st_ in pool.imap_unordered(_rows_worker, tasks):
                r0 = tasks[cid][1][0]
                self.theta[:, r0:r0 + th.shape[1]] = th
                self.build_stats.update(st_)
        self.Dtab = []
        self.Avec = np.vstack([self.X.T, self.nrm[None, :]]) % P
        D0 = prm.D0
        adj = np.zeros((2 * D0, N + 1), np.int64)
        for u in range(1, N + 1):
            lst = self.nb[0][u]
            adj[:len(lst), u] = lst
            adj[D0:D0 + len(lst), u] = 1
        self.Aadj = adj
