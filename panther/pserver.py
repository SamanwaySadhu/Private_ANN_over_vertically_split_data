"""Server-side data of the Panther baseline (Li et al., CCS'25, "Panther: Private ANN Search in the Single Server Setting"),
adapted to a vertically split query.

Plaintext algorithm (clustering based ANNS, Sec. 3.2 of the paper): k-means partition into t clusters padded to mc points,
the u clusters with the closest centroids are retrieved (via approximate top-u over the t centroid distances), the exact top-k
is taken over all points of the retrieved clusters.

Per query the server shuffles the clusters (a random permutation of the *index map*, free because every cluster is encoded in
its own plaintext polynomials, Fig. 2 of the paper); the indices revealed later are positions in that shuffled order.
Batch PIR = 3-way cuckoo batch code with B = 1.5 u buckets (Angel et al.): every (shuffled) cluster is stored in 3 buckets.
"""
import math
import time
from dataclasses import dataclass

import numpy as np

import _path  # noqa: F401


@dataclass
class PParams:
    N: int
    d: int
    m: int = 4                # number of clients (query split vertically into m blocks)
    k: int = 10
    t: int = 0                # clusters; 0 -> round(sqrt(N))
    u: int = 8                # clusters retrieved (recall/cost knob, see pbench --u / --sweep_u)
    cap: float = 1.5          # cluster capacity = cap * N / t (0 = pad to the largest k-means cluster, as in the paper)
    iters: int = 10
    delta: float = 0.01       # ApproxTopK bin parameter: k' = u / delta bins (capped at t)
    seed: int = 0

    def __post_init__(self):
        if self.t <= 0:
            self.t = max(2, int(round(math.sqrt(self.N))))

    @property
    def n(self):          # MPC parties: server (index 0) + m clients (1..m); client 1 queries the PIR and evaluates the GCs
        return self.m + 1

    @property
    def blocks(self):
        return np.array_split(np.arange(self.d), self.m)

    @property
    def B(self):          # buckets of the batch code
        return int(math.ceil(1.5 * self.u))

    @property
    def kprime(self):
        return min(self.t, int(math.ceil(self.u / self.delta)))

    @property
    def DMAX(self):
        return self.d * 255 * 255 + 1


def _assign(Xf, Xn, C, chunk=50000, top=1):
    Cf = C.astype(np.float32)
    Cn = (Cf ** 2).sum(1)
    out = np.empty((len(Xf), top), np.int64)
    for s in range(0, len(Xf), chunk):
        D = Xn[s:s + chunk, None] - 2 * Xf[s:s + chunk] @ Cf.T + Cn[None]
        if top == 1:
            a = D.argmin(1)[:, None]
        else:
            a = np.argpartition(D, top - 1, axis=1)[:, :top]
            a = np.take_along_axis(a, np.argsort(np.take_along_axis(D, a, 1), 1), 1)
        out[s:s + chunk] = a
    return out


def kmeans(Xf, t, iters, seed):
    rng = np.random.default_rng(seed)
    Xn = (Xf ** 2).sum(1)
    C = Xf[rng.choice(len(Xf), t, replace=False)].copy()
    for _ in range(iters):
        a = _assign(Xf, Xn, C)[:, 0]
        cnt = np.bincount(a, minlength=t)
        S = np.stack([np.bincount(a, weights=Xf[:, j], minlength=t) for j in range(Xf.shape[1])], 1)
        nz = cnt > 0
        C[nz] = S[nz] / cnt[nz, None]
        if (~nz).any():
            C[~nz] = Xf[rng.choice(len(Xf), int((~nz).sum()), replace=False)]
    return C


class PServer:
    def __init__(self, Xdata, prm):
        self.prm = prm
        N, d = Xdata.shape
        t0 = time.time()
        self.t = {}
        self.X = np.vstack([np.zeros((1, d), np.int64), Xdata.astype(np.int64)])    # row 0 = padding
        self.nrm = (self.X ** 2).sum(1)
        self.nrm[0] = prm.DMAX                       # padding rows can never be among the nearest
        Xf = Xdata.astype(np.float32)
        Xn = (Xf ** 2).sum(1)
        C = kmeans(Xf, prm.t, prm.iters, prm.seed)
        self.C = np.clip(np.rint(C), 0, 255).astype(np.int64)   # integer centroids (HE works on integers)
        self.Cn = (self.C ** 2).sum(1)
        self.t["kmeans"] = time.time() - t0
        t = prm.t
        cand = _assign(Xf, Xn, self.C, top=min(8, t))
        a = cand[:, 0].copy()
        cap = int(math.ceil(prm.cap * N / t)) if prm.cap > 0 else N
        cnt = np.bincount(a, minlength=t)
        moved = 0
        if cnt.max() > cap:                          # capacity-constrained assignment: overflow goes to the next closest cluster
            d_own = ((Xf - self.C[a].astype(np.float32)) ** 2).sum(1)
            for c in np.nonzero(cnt > cap)[0]:
                mem = np.nonzero(a == c)[0]
                for p in mem[np.argsort(-d_own[mem])][:cnt[c] - cap]:
                    alt = next((int(x) for x in cand[p, 1:] if cnt[x] < cap), int(np.argmin(cnt)))
                    a[p] = alt
                    cnt[c] -= 1
                    cnt[alt] += 1
                    moved += 1
        self.mc = int(cnt.max())
        self.cluster = np.zeros((t, self.mc), np.int64)           # 1-based point ids, 0 = padding
        order = np.argsort(a, kind="stable")
        start = np.r_[0, np.cumsum(cnt)]
        for c in range(t):
            self.cluster[c, :cnt[c]] = order[start[c]:start[c + 1]] + 1
        self.sizes, self.moved = cnt, moved
        self.t["total"] = time.time() - t0
        self.W = d + 4                                # words per point in the PIR database: d coords, norm (2 limbs), id (2 limbs)

    # ---- batch code --------------------------------------------------------------------------------------------
    def buckets(self, hseed=12345):
        """3 distinct buckets per shuffled cluster position (public hash functions) and the content of every bucket."""
        t, B = self.prm.t, self.prm.B
        rng = np.random.default_rng(hseed)
        h = np.argsort(rng.random((t, B)), axis=1)[:, :3]
        content = [[] for _ in range(B)]
        for i in range(t):
            for b in h[i]:
                content[int(b)].append(i)
        return h, content

    def size_info(self):
        p = self.prm
        _, content = self.buckets()
        return dict(t=p.t, mc=self.mc, u=p.u, B=p.B, kprime=p.kprime, bucket_items=max(len(c) for c in content), W=self.W,
                    cluster_min=int(self.sizes.min()), cluster_max=int(self.sizes.max()), moved=int(self.moved),
                    db_words=int(p.t * self.mc * self.W))
