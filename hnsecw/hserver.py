"""Tables of the HNSecW-style baseline (Zhang et al., "HNSecW"), adapted to the vertically split setting.

Per HNSW layer l (0 = base) the database owner (the server) prepares, in a canonical *logical* order:
  vector table  Rv rows = real nodes | A (T*deg replacement dummies, one per (iteration, neighbour slot))
                                     | B (2*deg dummies reachable from dummy graph rows)
                columns: vector, squared norm, ga (graph-table row of the node), vb (row of the same node in the table
                of layer l-1; for l = 0: row in the auxiliary output table D_-1), flag (1 = dummy)
  graph table   Rg rows = real nodes | GA (graph row of every A dummy) | GB (of every B dummy) | GI (T initial candidates)
                columns: deg vector-table row ids. Real lists are padded to deg with random nodes of the same layer.
                Dummy graph rows point into B (repeat hits are caught by the visited check).
All tables are additively secret-shared among the n = m+1 parties (server + m clients) and, per query, jointly shuffled.
The simulator keeps the plaintext logical tables and draws a fresh permutation per query (class Layout); protocol code
only touches a row through its (revealed, uniformly random) physical address.
Invariant checked by the engine: no physical row of any table is revealed twice within a query."""
import math
import time
from dataclasses import dataclass

import numpy as np

import _path  # noqa: F401
from hnsw_import import build_hnswlib, parse_index


@dataclass
class HParams:
    N: int
    d: int
    m: int = 4
    M: int = 8
    efc: int = 100
    k: int = 10
    E: int = 64            # base-layer ef (result set size)
    Tb: int = 0            # base-layer steps; 0 -> ceil(log2(N d / D0)) + E + C  (paper's rule)
    C: int = 7             # paper's residual slack constant
    seed: int = 0

    @property
    def D0(self):
        return 2 * self.M

    def deg(self, l):
        return self.D0 if l == 0 else self.M

    def ef(self, l):
        return self.E if l == 0 else 1

    def T(self, l):
        if l > 0:
            return 1 + self.C
        return self.Tb or (math.ceil(math.log2(self.N * self.d / self.D0)) + self.E + self.C)

    @property
    def n(self):           # MPC parties: server (index 0) + m clients (1..m)
        return self.m + 1

    @property
    def blocks(self):
        return np.array_split(np.arange(self.d), self.m)

    @property
    def DMAX(self):
        return self.d * 255 * 255 + 1


class Layer:
    pass


class HServer:
    def __init__(self, Xdata, prm):
        self.prm = prm
        rng = np.random.default_rng(prm.seed + 7)
        N, d = Xdata.shape
        self.X = np.vstack([np.zeros((1, d), np.int64), Xdata.astype(np.int64)])
        self.nrm = (self.X ** 2).sum(1)
        self.t = {}
        t0 = time.time()
        idx, self.t["hnsw_build"] = build_hnswlib(Xdata, prm.M, prm.efc, prm.seed)
        self.hnswlib_index = idx
        labels, levels, nb, enter, maxlevel = parse_index(idx, d)
        lab2id = labels + 1
        lev = np.zeros(N + 1, int)
        lev[lab2id] = levels
        self.lev, self.top, self.ep = lev, int(maxlevel), int(lab2id[enter])
        nbl = [dict() for _ in range(self.top + 1)]
        for l, dct in nb.items():
            for i, arr in dct.items():
                nbl[l][int(lab2id[i])] = [int(lab2id[j]) for j in arr]
        t1 = time.time()
        self.L = [self._layer(l, nbl[l], rng) for l in range(self.top + 1)]
        self._finish_vb()
        l0 = self.L[0]
        # auxiliary output table D_-1: N real rows | dummies for A0, B0 and the W initialisation
        self.D1_real = N
        self.D1_rows = N + l0.A + l0.B + max(prm.E, 1)
        self.t["tables"] = time.time() - t1
        self.t["server_total"] = time.time() - t0

    def _layer(self, l, nbd, rng):
        prm = self.prm
        L = Layer()
        L.l, L.deg, L.ef, L.T = l, prm.deg(l), prm.ef(l), prm.T(l)
        nodes = np.nonzero(self.lev >= l)[0]
        nodes = nodes[nodes >= 1]
        L.nodes, L.R = nodes, len(nodes)
        pos = np.full(prm.N + 1, -1, np.int64)
        pos[nodes] = np.arange(L.R)
        L.pos = pos
        L.A, L.B, L.I = L.T * L.deg, 2 * L.deg, L.T
        R, A, B, I, deg = L.R, L.A, L.B, L.I, L.deg
        L.Rv, L.Rg = R + A + B, R + A + B + I
        L.offA, L.offB, L.offI = R, R + A, R + A + B
        GT = np.zeros((L.Rg, deg), np.int64)
        for r, u in enumerate(nodes.tolist()):
            lst = [int(pos[v]) for v in nbd.get(u, [])][:deg]
            while len(lst) < deg:                         # pad with random nodes of the same layer
                lst.append(int(rng.integers(R)) if R > 1 else r)
            GT[r] = lst
        for j in range(A + B + I):
            GT[R + j] = R + A + (j + np.arange(deg)) % B   # dummy graph rows -> B dummies
        L.GT = GT
        L.ga = np.arange(L.Rv)                             # real r -> graph row r, A_j -> GA_j, B_j -> GB_j
        L.flag = np.r_[np.zeros(R, np.int64), np.ones(A + B, np.int64)]
        return L

    def _finish_vb(self):
        prm = self.prm
        for l, L in enumerate(self.L):
            vb = np.zeros(L.Rv, np.int64)
            if l == 0:
                vb[:L.R] = L.nodes - 1
                vb[L.offA:L.offA + L.A] = prm.N + np.arange(L.A)
                vb[L.offB:L.offB + L.B] = prm.N + L.A + np.arange(L.B)
            else:
                lo = self.L[l - 1]
                vb[:L.R] = lo.pos[L.nodes]
                vb[L.offA:L.offA + L.A] = lo.offA + np.arange(L.A) % lo.A
                vb[L.offB:L.offB + L.B] = lo.offB + np.arange(L.B) % lo.B
            L.vb = vb

    def wdummy_b(self, l, j):
        """Lower-table row used as b of the j-th initial dummy result entry (j >= 1)."""
        if l == 0:
            L0 = self.L[0]
            return self.prm.N + L0.A + L0.B + j
        lo = self.L[l - 1]
        return lo.offB + j % lo.B

    def rows(self, l, idx):
        """Plaintext (vectors, squared norms) of logical vector-table rows idx of layer l."""
        L = self.L[l]
        idx = np.asarray(idx)
        node = np.where(idx < L.R, L.nodes[np.minimum(idx, L.R - 1)], 0)
        return self.X[node], self.nrm[node]

    def d1_rows(self, idx):
        idx = np.asarray(idx)
        node = np.where(idx < self.D1_real, idx + 1, 0)
        return self.X[node], node

    def entry(self):
        L = self.L[self.top]
        return int(L.pos[self.ep])

    def table_shapes(self):
        """(name, rows, words) of every secret-shared, per-query reshuffled table."""
        d, out = self.prm.d, []
        for l, L in enumerate(self.L):
            out.append((f"vec{l}", L.Rv, d + 4))
            out.append((f"graph{l}", L.Rg, L.deg))
        out.append(("D-1", self.D1_rows, d + 1))
        return out


class Layout:
    """Per-query random physical layout (what the joint offline reshuffle produces)."""

    def __init__(self, srv, seed):
        rng = np.random.default_rng(seed)
        self.pv = [rng.permutation(L.Rv) for L in srv.L]
        self.pg = [rng.permutation(L.Rg) for L in srv.L]
        self.pD = rng.permutation(srv.D1_rows)
        self.iv = [np.argsort(p) for p in self.pv]
        self.ig = [np.argsort(p) for p in self.pg]
        self.iD = np.argsort(self.pD)
