"""Server tables of the baseline protocol: plain HNSW graph (imported from hnswlib), no LSH, no
cuckoo dictionaries, no (theta, D) tables.

  upper layers : one row per (node, level>=1) pair, row ids 1..U-1 (0 = dummy), random enumeration
        Aup_adj  (M+1, U)   M neighbour row ids (same level, 0 = padding) + one 'down' row id
        Aup_vec  (d+2, U)   vector, squared norm, global node id of the row's node
  layer 0      : Avec (d+1, N+1) and Aadj (2*D0, N+1) exactly as in vsann.Server."""
import os
import time

import numpy as np

import _path  # noqa: F401
from hnsw_import import build_hnswlib, parse_index
from vsann import P


class BaselineServer:
    def __init__(self, Xdata, prm, build_tables=True):
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
        self.flatten()
        self.t["flatten_tables"] = time.time() - t2
        self.t["server_total"] = time.time() - t0

    def flatten(self):
        prm, rng = self.prm, self.rng
        N, d, M, D0 = prm.N, prm.d, prm.M, prm.D0
        states = [(u, l) for l in range(self.top, 0, -1) for u in np.nonzero(self.lev >= l)[0].tolist() if u >= 1]
        rows = rng.permutation(len(states)) + 1
        self.psi = {st: int(r) for st, r in zip(states, rows)}
        U = len(states) + 1
        self.U = U
        adj = np.zeros((M + 1, U), np.int64)
        vec = np.zeros((d + 2, U), np.int64)
        for (u, l), r in self.psi.items():
            for j, v in enumerate(self.nb[l][u][:M]):
                adj[j, r] = self.psi[(v, l)]
            adj[M, r] = self.psi.get((u, l - 1), 0)                 # down pointer (0 at level 1: search leaves the upper part)
            vec[:d, r] = self.X[u]
            vec[d, r] = self.nrm[u]
            vec[d + 1, r] = u
        self.Aup_adj, self.Aup_vec = adj, vec
        self.Avec = np.vstack([self.X.T, self.nrm[None, :]]) % P     # (d+1, N+1)
        a0 = np.zeros((2 * D0, N + 1), np.int64)
        for u in range(1, N + 1):
            lst = self.nb[0][u]
            a0[:len(lst), u] = lst
            a0[D0:D0 + len(lst), u] = 1
        self.Aadj = a0

    def entry_state(self):
        if self.top >= 1:
            return self.psi[(self.ep, self.top)], self.ep, self.top, self.X[self.ep], int(self.nrm[self.ep])
        return 0, self.ep, 0, self.X[self.ep], int(self.nrm[self.ep])

    def hnsw_exact(self, q, ef, k):
        """Plaintext HNSW reference (exact greedy upper layers + beam)."""
        import heapq

        def search_layer(eps, ef_, l):
            visited = set(eps)
            ds = ((self.X[list(eps)] - q) ** 2).sum(1)
            cand = [(int(dd), e) for dd, e in zip(ds, eps)]
            heapq.heapify(cand)
            res = [(-dd, e) for dd, e in cand]
            heapq.heapify(res)
            while cand:
                dd, c = heapq.heappop(cand)
                if len(res) >= ef_ and dd > -res[0][0]:
                    break
                nbrs = [n for n in self.nb[l][c] if n not in visited]
                if not nbrs:
                    continue
                visited.update(nbrs)
                for e, de in zip(nbrs, ((self.X[nbrs] - q) ** 2).sum(1)):
                    de = int(de)
                    if len(res) < ef_ or de < -res[0][0]:
                        heapq.heappush(cand, (de, e))
                        heapq.heappush(res, (-de, e))
                        if len(res) > ef_:
                            heapq.heappop(res)
            return sorted((-nd, e) for nd, e in res)
        cur = [self.ep]
        for lc in range(self.top, 0, -1):
            cur = [search_layer(cur, 1, lc)[0][1]]
        return [e for _, e in search_layer(cur, ef, 0)[:k]]
