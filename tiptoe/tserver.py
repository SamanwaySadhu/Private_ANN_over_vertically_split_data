"""Server-side data of the Tiptoe baseline (Henzinger et al., SOSP'23, "Private Web Search with Tiptoe"), adapted to a
vertically split query.

What the server builds (paper Sec. 3.2 / 7, batch jobs):
  * embeddings = the ANN vectors themselves (no text model needed); quantised to `bits`-bit signed integers (paper: 4 bit),
    L2 distance of the quantised vectors is the ranking function:  score(x) = ||x||^2 - 2<x, q>   (smaller = closer)
  * k-means into C ~ sqrt(N) clusters (centroids are PUBLIC: clients download them once, Sec. 3.2),
    20% of the vectors closest to a cluster boundary are stored in two clusters (Sec. 7), clusters padded to mc rows
  * ranking matrix M (mc rows x (C*d) columns, int8): column block c holds the vectors of cluster c, one per row (Fig. 3)
  * id/norm matrix M_id ((limbs+1)*mc rows x C columns): the (padded) vector ids of cluster c split into 12-bit limbs, plus the row
    norms ||x||^2 (padding rows: 2^(lt-1)-1). Linear in the secret selector e, so ids and norms of the secret cluster are
    retrieved by the same LWE machinery (the paper's URL service is replaced by this linear lookup, see README)
The LWE hint H = M*A (SimplePIR preprocessing) is never materialised: only its shape enters the cost model."""
import math
import time
from dataclasses import dataclass

import numpy as np

import _path  # noqa: F401

LIMB_BITS = 12


@dataclass
class TParams:
    N: int
    d: int
    m: int = 4                 # clients (query split vertically into m blocks)
    k: int = 10
    C: int = 0                 # clusters; 0 -> round(sqrt(N))
    bits: int = 4              # embedding precision (signed)
    dup: float = 0.2           # fraction of vectors stored in a second cluster
    cap: float = 1.5           # cluster capacity = cap * (1+dup) * N / C
    iters: int = 8
    train: int = 100000        # k-means training sample (paper: 10M of 360M)
    seed: int = 0
    lwe_n: int = 2048          # LWE secret dimension (paper App. C)
    rlwe_n: int = 2048         # outer (RLWE/BFV) ring dimension
    rlwe_logq: int = 38
    drop_low: bool = True      # paper A.3: server drops low-order bits of the hint (halves token work and download)

    def __post_init__(self):
        if self.C <= 0:
            self.C = max(2, int(round(math.sqrt(self.N))))

    @property
    def n(self):               # parties holding shares: the m clients (the server holds none; it garbles)
        return self.m

    @property
    def blocks(self):
        return np.array_split(np.arange(self.d), self.m)

    @property
    def lt(self):              # bits of the plaintext ring Z_{2^lt} (paper: p = 2^17)
        bound = 2 * self.d * 4 ** (self.bits - 1) + 1
        return max(17, int(math.ceil(math.log2(bound))))

    @property
    def pt(self):
        return 1 << self.lt

    @property
    def DMAX(self):            # upper bound of an L2 distance between two original (0..255) vectors
        return self.d * 255 * 255 + 1


def p_max_table12(upload_dim):
    """Largest plaintext modulus (log2) that App. C Table 12 allows for the ciphertext modulus 2^64 at upload dimension m."""
    t = {13: 19, 14: 18, 15: 18, 16: 18, 17: 17, 18: 17, 19: 17, 20: 17, 21: 17, 22: 19, 23: 18, 24: 18}
    e = min(24, max(13, int(math.ceil(math.log2(upload_dim)))))
    return t[e]


def _assign(Xf, C, chunk=50000, top=1):
    Cn = (C ** 2).sum(1)
    out = np.empty((len(Xf), top), np.int64)
    dist = np.empty((len(Xf), top), np.float32)
    for s in range(0, len(Xf), chunk):
        x = Xf[s:s + chunk]
        D = (x ** 2).sum(1)[:, None] - 2 * x @ C.T + Cn[None]
        if top == 1:
            a = D.argmin(1)[:, None]
        else:
            a = np.argpartition(D, top - 1, axis=1)[:, :top]
            a = np.take_along_axis(a, np.argsort(np.take_along_axis(D, a, 1), 1), 1)
        out[s:s + chunk] = a
        dist[s:s + chunk] = np.take_along_axis(D, a, 1)
    return out, dist


def kmeans(Xf, C, iters, seed):
    rng = np.random.default_rng(seed)
    Cen = Xf[rng.choice(len(Xf), C, replace=False)].copy()
    for _ in range(iters):
        a = _assign(Xf, Cen)[0][:, 0]
        cnt = np.bincount(a, minlength=C)
        S = np.stack([np.bincount(a, weights=Xf[:, j], minlength=C) for j in range(Xf.shape[1])], 1)
        nz = cnt > 0
        Cen[nz] = (S[nz] / cnt[nz, None]).astype(np.float32)
        if (~nz).any():
            Cen[~nz] = Xf[rng.choice(len(Xf), int((~nz).sum()), replace=False)]
    return Cen


class TServer:
    def __init__(self, Xdata, prm):
        self.prm = prm
        N, d = Xdata.shape
        assert N == prm.N and d == prm.d
        t0 = time.time()
        self.t = {}
        # ---- quantisation (uniform scale, per-dimension shift: both are public parameters of the 'embedding function') ----
        Xf = Xdata.astype(np.float32)
        self.mu = Xf.mean(0)
        half = 2 ** (prm.bits - 1)
        self.scale = float(np.percentile(np.abs(Xf - self.mu), 99.9)) / (half - 1 if half > 1 else 1)
        self.scale = max(self.scale, 1e-6)
        self.Xq = self.quant(Xdata)                                     # (N, d) int64 in [-half, half-1]
        # ---- clustering on the original vectors; public centroids rounded to integers (clients compute exact int distances) ----
        rng = np.random.default_rng(prm.seed)
        tr = Xf if N <= prm.train else Xf[rng.choice(N, prm.train, replace=False)]
        Cen = kmeans(tr, prm.C, prm.iters, prm.seed)
        self.cent = np.clip(np.rint(Cen), 0, 255).astype(np.int64)      # public (C, d)
        self.t["kmeans"] = time.time() - t0
        C = prm.C
        top = min(8, C)
        cand, dc = _assign(Xf, self.cent.astype(np.float32), top=top)
        a = cand[:, 0].copy()
        ndup = int(round(prm.dup * N))
        ratio = (dc[:, 1] + 1e-3) / (dc[:, 0] + 1e-3) if top > 1 else np.ones(N)
        dupset = np.argsort(ratio, kind="stable")[:ndup] if ndup else np.zeros(0, np.int64)
        second = cand[dupset, 1] if ndup else np.zeros(0, np.int64)
        cap = int(math.ceil(prm.cap * (1 + prm.dup) * N / C))
        # entries (point, cluster, is_dup, distance)
        pt_e = np.concatenate([np.arange(N), dupset])
        cl_e = np.concatenate([a, second])
        isd = np.concatenate([np.zeros(N, bool), np.ones(ndup, bool)])
        de = np.concatenate([dc[:, 0], dc[dupset, 1]]) if ndup else dc[:, 0].copy()
        cnt = np.bincount(cl_e, minlength=C)
        self.moved = self.dropped = 0
        keep = np.ones(len(pt_e), bool)
        for c in np.nonzero(cnt > cap)[0]:                               # overflow: drop duplicates first, then move primaries
            mem = np.nonzero((cl_e == c) & keep)[0]
            order = mem[np.lexsort((-de[mem], ~isd[mem]))]               # duplicates (isd) first, farthest first
            for e in order[:cnt[c] - cap]:
                if isd[e]:
                    keep[e] = False
                    self.dropped += 1
                else:
                    alt = next((int(x) for x in cand[pt_e[e], 1:] if cnt[x] < cap), int(np.argmin(cnt)))
                    cl_e[e] = alt
                    cnt[alt] += 1
                    self.moved += 1
                cnt[c] -= 1
        pt_e, cl_e = pt_e[keep], cl_e[keep]
        cnt = np.bincount(cl_e, minlength=C)
        self.mc = int(cnt.max())
        order = np.argsort(cl_e, kind="stable")
        start = np.r_[0, np.cumsum(cnt)]
        self.ids = np.zeros((C, self.mc), np.int64)                      # 1-based ids, 0 = padding
        for c in range(C):
            self.ids[c, :cnt[c]] = pt_e[order[start[c]:start[c + 1]]] + 1
        self.sizes = cnt
        self.X8 = np.zeros((C, self.mc, d), np.int8)                     # the ranking matrix, column block c = X8[c]^T
        Xq8 = self.Xq.astype(np.int8)
        for c in range(C):
            m_ = self.ids[c] > 0
            self.X8[c, m_] = Xq8[self.ids[c, m_] - 1]
        nrm = (self.Xq ** 2).sum(1)
        self.nu = np.full((C, self.mc), (1 << (prm.lt - 1)) - 1, np.int64)  # padded rows: nu = 2^(lt-1)-1 > any real score, ip = 0 -> never win
        for c in range(C):
            m_ = self.ids[c] > 0
            self.nu[c, m_] = nrm[self.ids[c, m_] - 1]
        self.limbs = max(1, math.ceil(math.log2(N + 2) / LIMB_BITS))
        self.t["total"] = time.time() - t0
        # ---- parameter sanity (paper App. C Table 12) ----
        pm = p_max_table12(d * C)
        if prm.lt > pm:
            raise ValueError(f"plaintext modulus 2^{prm.lt} exceeds 2^{pm}, the largest the paper's LWE parameters support at "
                             f"upload dimension d*C={d * C} (reduce --bits or --C)")

    def quant(self, X):
        half = 2 ** (self.prm.bits - 1)
        return np.clip(np.rint((X.astype(np.float32) - self.mu) / self.scale), -half, half - 1).astype(np.int64)

    # ---- shapes for the cost model --------------------------------------------------------------------------
    def size_info(self):
        p = self.prm
        return dict(C=p.C, mc=self.mc, d=p.d, bits=p.bits, lt=p.lt, limbs=self.limbs, rows=self.mc, id_rows=(self.limbs + 1) * self.mc,
                    upload_dim=p.d * p.C, cluster_min=int(self.sizes.min()), cluster_max=int(self.sizes.max()),
                    cluster_mean=float(self.sizes.mean()), stored=int(self.sizes.sum()), moved=int(self.moved),
                    dropped_dups=int(self.dropped), M_bytes=int(p.C * self.mc * p.d), Mid_bytes=int((self.limbs + 1) * self.mc * p.C * 2))
