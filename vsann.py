"""
Private HNSW over vertically split queries -- simulation of the protocol in
Vertically_split_ANN.pdf.

What is real here
  * additive secret sharing over F_p (p = 2147352577), Beaver multiplication,
  * the Lagrange/binomial ID -> shared one-hot conversion (Sec. 4),
  * the masked matrix 1-D read (Sec. 5.2), shared outputs,
  * 2-D read as encrypted-selector contraction (Sec. 5.3),
  * node-specific secret LSH, multi-radius, cuckoo dictionary with stash and
    full-key check (Sec. 2, 6, 7), fixed budgets, dummy rounds,
  * beam search with one bounded set W + separate visited history (Sec. 9),
  * MYao circuits with the all-client output-mask wrapper (Sec. 3.3).

What is simulated (ideal functionality, NOT cryptography)
  * threshold HE (Ct objects hold plaintext inside the HE class; the server
    code only touches them through HE operations),
  * dealer offline phase (Beaver triples, alpha powers, (r,s,h) correlations,
    which the paper generates with HE),
  * garbled circuits: a "MYao circuit" reconstructs its inputs inside one
    function call and returns freshly masked shares. No garbling is done.
"""
import math
import hashlib
import heapq
from collections import Counter
from dataclasses import dataclass

import numpy as np

P = 2147352577         # field prime, = 1 mod 2^16 so it is also a BFV batching modulus
INF = 1 << 29          # sentinel distance  Delta_inf


# --------------------------------------------------------------------------
# field helpers
# --------------------------------------------------------------------------
def signed(x):
    x = np.mod(x, P)
    return np.where(x > P // 2, x - P, x)


def matmul_mod(A, B):
    """(A @ B) mod P without int64 overflow (B split in 16-bit halves)."""
    A = np.mod(A, P).astype(np.int64)
    B = np.mod(B, P).astype(np.int64)
    lo, hi = B & 0xFFFF, B >> 16
    r1 = np.mod(A @ lo, P)
    r2 = np.mod(np.mod(A @ hi, P) << 16, P)
    return np.mod(r1 + r2, P)


@dataclass
class Params:
    N: int
    d: int
    m: int = 4
    M: int = 8                 # upper-layer degree cap
    efc: int = 64              # construction ef
    k: int = 10
    E: int = 32                # efSearch / beam capacity
    s: int = 6                 # number of LSH radii
    sigma: int = 4             # stash size
    Tg: int = 12               # upper-phase budget
    Tb: int = 48               # beam budget
    Sa: int = 16               # fixed-point scale of a, b
    Sw: int = 16               # fixed-point scale of w
    Sq: int = 1                # fixed-point scale of query / data
    rho: tuple = (0.5, 1, 2, 4, 8, 16)   # radius multipliers (R_r)
    seed: int = 0
    onehot: str = "ideal"      # "lagrange" (Sec. 4, real) or "ideal"

    @property
    def D0(self):
        return 2 * self.M

    @property
    def H(self):
        h = 1
        while h < 4 * (self.M + 1):
            h *= 2
        return h

    @property
    def ncol(self):
        return self.H + self.sigma

    @property
    def Bq(self):              # B = 2^tau >= m
        b = 1
        while b < self.m:
            b *= 2
        return b

    @property
    def blocks(self):
        return np.array_split(np.arange(self.d), self.m)

    @property
    def LV(self):
        return 1 + self.Tb * self.D0

    @property
    def Pn(self):
        return 4 + self.sigma


def phi(seed, key, H):
    """Seed-defined dictionary hash (stands in for AES-based addressing)."""
    h = hashlib.blake2b(f"{seed}|{int(key)}".encode(), digest_size=8).digest()
    return int.from_bytes(h, "little") % H


def lsh_num(prm, a, b, x):
    return prm.Sw * (x @ a + b * prm.Sq)


def lsh_key(prm, a, b, w, x):
    return lsh_num(prm, a, b, x) // (prm.Sa * prm.Sq * w)


# --------------------------------------------------------------------------
# server: HNSW, flattening, local LSH dictionaries, tables
# --------------------------------------------------------------------------
class Server:
    def __init__(self, Xdata, prm):
        self.prm = prm
        self.rng = np.random.default_rng(prm.seed + 1)
        N, d = Xdata.shape
        assert N == prm.N and d == prm.d
        self.X = np.vstack([np.zeros((1, d), np.int64), Xdata.astype(np.int64)])
        self.nrm = (self.X ** 2).sum(1)
        self.build_hnsw()
        self.flatten_and_tables()

    # ---- HNSW (ids 1..N, 0 = dummy) ----
    def d2(self, q, ids):
        diff = self.X[ids] - q
        return (diff * diff).sum(1)

    def search_layer(self, q, eps, ef, l):
        visited = set(eps)
        ds = self.d2(q, list(eps))
        cand = [(int(dd), e) for dd, e in zip(ds, eps)]
        heapq.heapify(cand)
        res = [(-dd, e) for dd, e in cand]
        heapq.heapify(res)
        while cand:
            dd, c = heapq.heappop(cand)
            if len(res) >= ef and dd > -res[0][0]:
                break
            nbrs = [n for n in self.nb[l][c] if n not in visited]
            if not nbrs:
                continue
            visited.update(nbrs)
            for e, de in zip(nbrs, self.d2(q, nbrs)):
                de = int(de)
                if len(res) < ef or de < -res[0][0]:
                    heapq.heappush(cand, (de, e))
                    heapq.heappush(res, (-de, e))
                    if len(res) > ef:
                        heapq.heappop(res)
        return sorted((-nd, e) for nd, e in res)

    def select_heuristic(self, cands, mmax):
        """HNSW Alg. 4 (diversity heuristic) with keepPrunedConnections.
        cands: [(dist_to_base, id)] sorted ascending."""
        sel, pruned = [], []
        for dd, e in cands:
            if len(sel) >= mmax:
                break
            if all(dd < int(self.d2(self.X[e], [r])[0]) for r in sel):
                sel.append(e)
            else:
                pruned.append(e)
        for e in pruned:
            if len(sel) >= mmax:
                break
            sel.append(e)
        return sel

    def build_hnsw(self):
        prm, rng = self.prm, self.rng
        N, M, M0 = prm.N, prm.M, 2 * prm.M
        mL = 1.0 / math.log(M)
        lev = np.zeros(N + 1, int)
        lev[1:] = [int(-math.log(1 - rng.random()) * mL) for _ in range(N)]
        self.lev = lev
        L = int(lev.max())
        self.nb = [[[] for _ in range(N + 1)] for _ in range(L + 1)]
        ep, top = None, -1
        for u in rng.permutation(np.arange(1, N + 1)):
            u = int(u)
            l = int(lev[u])
            if ep is None:
                ep, top = u, l
                continue
            cur = [ep]
            for lc in range(top, l, -1):
                cur = [self.search_layer(self.X[u], cur, 1, lc)[0][1]]
            for lc in range(min(top, l), -1, -1):
                W = self.search_layer(self.X[u], cur, prm.efc, lc)
                mmax = M0 if lc == 0 else M
                sel = self.select_heuristic(W, mmax)
                self.nb[lc][u] = list(sel)
                for e in sel:
                    self.nb[lc][e].append(u)
                    if len(self.nb[lc][e]) > mmax:
                        lst = self.nb[lc][e]
                        dd = self.d2(self.X[e], lst)
                        cl = sorted(zip(dd.tolist(), lst))
                        self.nb[lc][e] = self.select_heuristic(cl, mmax)
                cur = [e for _, e in W]
            if l > top:
                ep, top = u, l
        self.ep, self.top = ep, top

    def hnsw_search(self, q, ef, k):
        """Plain (non-private) HNSW reference: exact upper greedy + beam."""
        cur = [self.ep]
        for lc in range(self.top, 0, -1):
            cur = [self.search_layer(q, cur, 1, lc)[0][1]]
        W = self.search_layer(q, cur, ef, 0)
        return [e for _, e in W[:k]]

    # ---- flatten + LSH dictionaries ----
    def build_dict(self, items, seeds_rng):
        """Static 2-choice cuckoo + stash. items: [(key, id, next)]."""
        prm = self.prm
        H, sg = prm.H, prm.sigma
        for attempt in range(1, 200):
            s1, s2 = (int(x) for x in seeds_rng.integers(1, 1 << 29, size=2))
            table, stash, ok = [None] * H, [], True
            for it in items:
                cur = it
                pos = phi(s1, cur[0], H)
                for _ in range(60):
                    if table[pos] is None:
                        table[pos] = cur
                        cur = None
                        break
                    table[pos], cur = cur, table[pos]
                    p1, p2 = phi(s1, cur[0], H), phi(s2, cur[0], H)
                    pos = p2 if pos == p1 else p1
                if cur is not None:
                    if len(stash) < sg:
                        stash.append(cur)
                    else:
                        ok = False
                        break
            if ok:
                return s1, s2, table, stash, attempt
        raise RuntimeError("cuckoo build failed; enlarge H/sigma")

    def flatten_and_tables(self):
        prm, rng = self.prm, self.rng
        N, d, s, H, ncol = prm.N, prm.d, prm.s, prm.H, prm.ncol
        top = self.top
        states = [(u, l) for l in range(top, 0, -1) for u in range(1, N + 1) if self.lev[u] >= l]
        term = [(u, 0) for u in range(1, N + 1) if self.lev[u] >= 1]
        allst = states + term
        rows = rng.permutation(len(allst)) + 1          # arbitrary server enumeration
        self.psi = {st: int(r) for st, r in zip(allst, rows)}
        U = len(allst) + 1
        self.U = U
        self.row_state = {v: k for k, v in self.psi.items()}
        A = 3 + s * (d + 4)
        theta = np.zeros((A, U), np.int64)
        Dv = np.zeros((s, U, ncol), np.int64)
        Dk, Di, Dn = Dv.copy(), Dv.copy(), Dv.copy()
        self.build_stats = Counter()
        for row in range(U):
            st = self.row_state.get(row)
            real = st is not None and st[1] >= 1
            if st is not None:
                theta[0, row] = st[0]
                theta[1, row] = st[1]
                theta[2, row] = self.psi[(st[0], st[1] - 1)] if real else 0
            if real:
                u, l = st
                S = [u] + list(self.nb[l][u])
                nbrs = self.nb[l][u]
                base = float(np.sqrt(self.d2(self.X[u], nbrs)).mean()) if nbrs else 1.0
                base = max(base, 1.0)
                perm = rng.permutation(len(S))
                XS = self.X[S]
            for r in range(s):
                c0 = 3 + r * (d + 4)
                if not real:
                    continue            # dummy/terminal constants set below
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
                        items.append((kk, S[pi], self.psi[(S[pi], l)]))
                self.build_stats["points"] += len(S)
                self.build_stats["kept"] += len(items)
                s1, s2, table, stash, att = self.build_dict(items, rng)
                self.build_stats["cuckoo_retries"] += att - 1
                self.build_stats["stash_used"] += len(stash)
                for j, it in enumerate(table):
                    if it is not None:
                        Dv[r, row, j], Dk[r, row, j] = 1, it[0] % P
                        Di[r, row, j], Dn[r, row, j] = it[1], it[2]
                for j, it in enumerate(stash):
                    cj = H + j
                    Dv[r, row, cj], Dk[r, row, cj] = 1, it[0] % P
                    Di[r, row, cj], Dn[r, row, cj] = it[1], it[2]
                theta[c0:c0 + d, row] = a % P
                theta[c0 + d, row] = bI
                theta[c0 + d + 1, row] = wI
                theta[c0 + d + 2, row] = s1
                theta[c0 + d + 3, row] = s2
        # fix dummy/terminal constants (a=0,b=0,w=1, valid seeds)
        for row in range(U):
            st = self.row_state.get(row)
            if st is None or st[1] == 0:
                for r in range(s):
                    c0 = 3 + r * (d + 4)
                    theta[c0:c0 + d + 4, row] = 0
                    theta[c0 + d + 1, row] = 1
                    theta[c0 + d + 2, row] = int(rng.integers(1, 1 << 29))
                    theta[c0 + d + 3, row] = int(rng.integers(1, 1 << 29))
        self.theta = theta
        self.Dtab = [np.stack([Dv[r], Dk[r], Di[r], Dn[r]]) for r in range(s)]   # (4,U,ncol)
        # vectors / norms and layer-0 adjacency (column = vertex id, col 0 = dummy)
        self.Avec = np.vstack([self.X.T, self.nrm[None, :]]) % P                  # (d+1, N+1)
        D0 = prm.D0
        adj = np.zeros((2 * D0, N + 1), np.int64)
        for u in range(1, N + 1):
            lst = self.nb[0][u]
            adj[:len(lst), u] = lst
            adj[D0:D0 + len(lst), u] = 1
        self.Aadj = adj

    def entry_state(self):
        prm = self.prm
        if self.top >= 1:
            i0, l0 = self.psi[(self.ep, self.top)], self.top
        else:
            i0, l0 = 0, 0
        return i0, self.ep, l0, self.X[self.ep], int(self.nrm[self.ep])


# --------------------------------------------------------------------------
# Lagrange one-hot tables (Sec. 4)
# --------------------------------------------------------------------------
_LAG = {}


def lag_tables(n):
    if n in _LAG:
        return _LAG[n]
    poly = np.zeros(n + 1, np.int64)
    poly[0] = 1
    for t in range(n):
        new = np.zeros(n + 1, np.int64)
        new[1:] = poly[:-1]
        poly = np.mod(new - t * poly, P)
    js = np.arange(n, dtype=np.int64)
    q = np.zeros((n, n), np.int64)
    q[n - 1] = 1
    for h in range(n - 1, 0, -1):
        q[h - 1] = np.mod(poly[h] + js * q[h], P)
    fact = [1] * (n + 1)
    for i in range(1, n + 1):
        fact[i] = fact[i - 1] * i % P
    inv = np.array([pow(((-1) ** (n - 1 - j)) * fact[j] * fact[n - 1 - j] % P, P - 2, P)
                    for j in range(n)], np.int64)
    C = np.mod(q.T * inv[:, None], P)                    # C[j,h]
    Bn = np.zeros((n, n), np.int64)
    Bn[0, 0] = 1
    for h in range(1, n):
        Bn[h, 0] = 1
        Bn[h, 1:] = np.mod(Bn[h - 1, 1:] + Bn[h - 1, :-1], P)
    hh, tt = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    Dm = np.clip(hh - tt, 0, None)
    _LAG[n] = (C, Bn, Dm)
    return _LAG[n]


# --------------------------------------------------------------------------
# MPC context: sharing, Beaver, MYao wrapper, HE simulation
# --------------------------------------------------------------------------
class MPC:
    def __init__(self, m, seed=123, debug=False):
        self.m = m
        self.rng = np.random.default_rng(seed)
        self.stats = Counter()
        self.debug = debug
        self.trace = []
        self.cur = {}

    def rint(self, shape):
        return self.rng.integers(0, P, size=shape, dtype=np.int64)

    def share(self, x):
        x = np.mod(np.asarray(x, dtype=np.int64), P)
        sh = self.rint((self.m - 1,) + x.shape)
        first = np.mod(x - sh.sum(0), P)
        return np.concatenate([first[None], sh])

    def reveal(self, S):
        return np.mod(S.sum(0), P)

    def pub(self, x):
        x = np.mod(np.asarray(x, dtype=np.int64), P)
        S = np.zeros((self.m,) + x.shape, np.int64)
        S[0] = x
        return S

    def mul(self, X, Y):
        """Elementwise Beaver multiplication of shared arrays (m, ...)."""
        shape = X.shape[1:]
        A, B = self.rint(shape), self.rint(shape)
        SA, SB, SC = self.share(A), self.share(B), self.share(np.mod(A * B, P))
        e, f = self.reveal(X - SA), self.reveal(Y - SB)       # opened to clients
        Z = np.mod(SC + np.mod(e * SB, P) + np.mod(f * SA, P), P)
        Z[0] = np.mod(Z[0] + np.mod(e * f, P), P)
        self.stats["beaver_products"] += A.size
        return Z

    # ---- MYao with the all-client output mask wrapper (Sec. 3.3) ----
    def myao(self, fn, inputs, name="circ"):
        vals = [signed(self.reveal(I)) for I in inputs]      # inside the circuit only
        outs = []
        for y in fn(*vals):
            y = np.mod(np.asarray(y, dtype=np.int64), P)
            eta = self.rint((self.m,) + y.shape)             # every client's fresh mask
            z = np.mod(y - eta.sum(0), P)                    # the only public output
            sh = eta.copy()
            sh[0] = np.mod(z + eta[0], P)
            outs.append(sh)
        self.stats["myao"] += 1
        self.stats["myao:" + name] += 1
        return outs

    def myao_open(self, fn, inputs, name="final"):
        vals = [signed(self.reveal(I)) for I in inputs]
        self.stats["myao"] += 1
        self.stats["myao:" + name] += 1
        return fn(*vals)


class SimHE:
    """Toy threshold-HE (ideal functionality): a ciphertext wraps a plaintext.
    Interface shared with real_he.OpenFHEThreshold."""

    class Ct:
        __slots__ = ("_v",)

        def __init__(self, v):
            self._v = v

    def __init__(self, mpc, Dtab):
        self.mpc, self.Dtab = mpc, Dtab

    def begin_row(self, Ush):                        # clients encrypt shares, server sums
        return SimHE.Ct(np.mod(Ush.sum(0), P))

    def read2d(self, cu, r, Vsh):
        """Cout = sum_t Enc(u_t) (.) (sum_b D[t,b] Enc(v_b)) then Enc2Share."""
        cv = np.mod(Vsh.sum(0), P)
        Dtab = self.Dtab[r]
        F, n1, n2 = Dtab.shape
        Ct = matmul_mod(Dtab.reshape(F * n1, n2), cv).reshape(F, n1)
        out = np.mod(np.mod(Ct * cu._v[None, :], P).sum(1), P)
        self.mpc.stats["he_ct_mults"] += n1
        self.mpc.stats["he_pt_scalar_mults"] += F * n1 * n2
        return self.mpc.share(out)


# --------------------------------------------------------------------------
# pure functions shared by the circuits and the plain reference
# --------------------------------------------------------------------------
def upper_match(T, hh, prm):
    """T (s,Pn,4) = valid,key,id,next. First match in (radius, probe) order."""
    found, c, crow, rad = 0, 0, 0, -1
    for r in range(prm.s):
        for j in range(prm.Pn):
            valid, key, idv, nxt = (int(x) for x in T[r, j])
            if j < 4:
                mt = valid == 1 and key == hh[r] + (0 if j < 2 else 1)
            else:
                mt = valid == 1 and key in (hh[r], hh[r] + 1)
            if mt and not found:
                c, crow, rad = idv, nxt, r
            found = found or int(mt)
    return found, c, crow, rad


def upper_transition(act, found, c, dc, dv, crow, v, l, down):
    gam = bool(act == 1 and found == 1 and c != 0 and dc < dv)
    if act == 1:
        nv, nd, ni, nl = (c, dc, crow, l) if gam else (v, dv, down, l - 1)
    else:
        nv, nd, ni, nl = v, dv, 0, l
    nact = int(act == 1 and nl > 0)
    return nv, nd, ni, nl, nact, int(gam)


def beam_step(W, V, usel, live, cu, cd, cv, t, prm):
    """One fused update (Sec. 9.3). W (4,E)=(u,d,p,nu); V (2,LV)=(h,omega)."""
    E, D0 = prm.E, prm.D0
    Wu, Wd, Wp, Wv = (x.copy() for x in W)
    Vh, Vw = V[0].copy(), V[1].copy()
    live = int(live)
    Wp = Wp | (live & Wv & (Wu == usel))
    seen = ((Vw[None, :] == 1) & (cu[:, None] == Vh[None, :])).any(1)
    dup = np.array([bool(((cv[:j] == 1) & (cu[:j] == cu[j])).any()) for j in range(D0)])
    new = live & cv & (cu != 0) & (~seen) & (~dup)
    b0 = 1 + t * D0
    Vh[b0:b0 + D0] = cu
    Vw[b0:b0 + D0] = live & cv & (cu != 0)
    Bu = np.concatenate([Wu, cu])
    Bd = np.concatenate([Wd, cd])
    Bp = np.concatenate([Wp, np.zeros(D0, np.int64)])
    Bv = np.concatenate([Wv, new])
    Bd = np.where(Bv == 1, Bd, INF)
    order = np.lexsort((Bu, Bd, 1 - Bv))[:E]
    Wu, Wd, Wp, Wv = Bu[order], Bd[order], Bp[order], Bv[order]
    inv = Wv == 0
    Wu = np.where(inv, 0, Wu)
    Wd = np.where(inv, INF, Wd)
    Wp = np.where(inv, 1, Wp)
    elig = (Wv == 1) & (Wp == 0)
    if elig.any():
        key = np.where(elig, Wd, INF + 1)
        a = np.lexsort((Wu, key))[0]
        unext, lnext = int(Wu[a]), 1
    else:
        unext, lnext = 0, 0
    return np.stack([Wu, Wd, Wp, Wv]), np.stack([Vh, Vw]), unext, lnext


def beam_init(ep0, dep0, prm):
    E, LV = prm.E, prm.LV
    W = np.zeros((4, E), np.int64)
    W[1, :], W[2, :] = INF, 1
    W[:, 0] = (ep0, dep0, 0, 1)
    V = np.zeros((2, LV), np.int64)
    V[:, 0] = (ep0, 1)
    return W, V


def hash_blocks(prm, th_a, th_b, th_w, qI):
    """Plain version of the block-wise hash: returns Q_{r,i'} (s,m) and total t numerator."""
    s, m = prm.s, prm.m
    Q = np.zeros((s, m), np.int64)
    for r in range(s):
        for i, blk in enumerate(prm.blocks):
            num = prm.Sw * (int(th_a[r][blk] @ qI[blk]) + (th_b[r] * prm.Sq if i == 0 else 0))
            Q[r, i] = (prm.Bq * num) // (prm.Sa * prm.Sq * th_w[r])
    return Q


# --------------------------------------------------------------------------
# clients: query sharing
# --------------------------------------------------------------------------
def share_query(mpc, blocks, prm):
    """blocks[i] = client i's coordinates (only its own). Returns [q] and [||q||^2]."""
    Q = np.zeros((prm.m, prm.d), np.int64)
    nq = np.zeros(prm.m, np.int64)
    for i, idx in enumerate(prm.blocks):
        Q[:, idx] = mpc.share(blocks[i])
        nq = np.mod(nq + mpc.share(int((blocks[i].astype(np.int64) ** 2).sum())), P)
    return Q, nq


# --------------------------------------------------------------------------
# the secure protocol
# --------------------------------------------------------------------------
class SecureANN:
    def __init__(self, srv, mpc, he=None):
        self.srv, self.c, self.prm = srv, mpc, srv.prm
        self.he = he if he is not None else SimHE(mpc, srv.Dtab)

    # ---- Sec. 4 ----
    def onehot(self, Z, n):
        c = self.c
        c.stats[f"onehot_{self.prm.onehot}"] += 1
        if self.prm.onehot == "ideal":
            z = int(c.reveal(Z))
            assert 0 <= z < n
            e = np.zeros(n, np.int64)
            e[z] = 1
            return c.share(e)
        C, Bn, Dm = lag_tables(n)
        alpha = int(c.rng.integers(1, P))
        apow = np.array([pow(alpha, t, P) for t in range(n)], np.int64)
        Ap = c.share(apow)                                  # dealer / HE offline
        tau = int(c.reveal(Z - Ap[:, 1]))                   # opened to the server
        c.stats["onehot_openings"] += 1
        tp = np.array([pow(tau, i, P) for i in range(n)], np.int64)
        Tm = np.mod(Bn * tp[Dm], P)
        zh = matmul_mod(Tm, Ap.T)                           # (n,m): shares of z^h
        return matmul_mod(C, zh).T                          # (m,n)

    # ---- Sec. 5.2 ----
    def read1d(self, A, Esh):
        c = self.c
        a, n = A.shape
        r, s = c.rint(n), c.rint(a)                         # offline correlation
        Rsh, Hsh = c.share(r), c.share(np.mod(matmul_mod(A, r) + s, P))
        qA = c.reveal(Esh - Rsh)                            # to the server
        y = np.mod(matmul_mod(A, qA) - s, P)                # server, broadcast to clients
        out = Hsh.copy()
        out[0] = np.mod(out[0] + y, P)
        c.stats["read1d"] += 1
        return out

    # ---- Sec. 8 ----
    def dist(self, X, Nn):
        c = self.c
        m, K, d = X.shape
        Qb = np.broadcast_to(self.Q[:, None, :], (m, K, d)).copy()
        z = np.mod(c.mul(X, Qb).sum(-1), P)
        return np.mod(self.nq[:, None] + Nn - 2 * z, P)

    # ---------------- upper phase ----------------
    def upper(self):
        prm, srv, c, he = self.prm, self.srv, self.c, self.he
        s, d, m, U, ncol = prm.s, prm.d, prm.m, srv.U, prm.ncol
        i0, v0, l0, xv0, nv0 = srv.entry_state()
        i, v, l = c.share(i0), c.share(v0), c.share(l0)
        xs = c.share(xv0[None, :])
        dv = self.dist(xs, c.share(np.array([nv0])))[:, 0]
        act = c.share(1 if l0 > 0 else 0)
        pubcol = [c.pub(np.eye(ncol, dtype=np.int64)[prm.H + j]) for j in range(prm.sigma)]
        for it in range(prm.Tg):
            ireq, = c.myao(lambda a, b: [np.where(a == 1, b, 0)], [act, i], "mux_row")
            e = self.onehot(ireq, U)
            th = self.read1d(srv.theta, e)                       # (m, 3+s(d+4))
            down = th[:, 2]
            blk = th[:, 3:].reshape(m, s, d + 4)
            a_sh, b_sh, w_sh = blk[:, :, :d], blk[:, :, d], blk[:, :, d + 1]
            s1_sh, s2_sh = blk[:, :, d + 2], blk[:, :, d + 3]
            # Sec. 6.1: shared coefficient x shared query (s*d Beaver products)
            Qb = np.broadcast_to(self.Q[:, None, :], (m, s, d)).copy()
            prod = c.mul(a_sh, Qb)
            Nb = np.stack([np.mod(prod[:, :, bk].sum(-1), P) for bk in prm.blocks], -1)
            Nb[:, :, 0] = np.mod(Nb[:, :, 0] + b_sh * prm.Sq, P)
            Nb = np.mod(Nb * prm.Sw, P)

            def fnA(Nn, w):
                return [(prm.Bq * Nn) // (prm.Sa * prm.Sq * w)[:, None]]
            Qrb, = c.myao(fnA, [Nb, w_sh], "div_floor")
            Qr = np.mod(Qrb.sum(-1), P)                          # (m,s)

            def fnB(Q, s1, s2):
                hh = Q // prm.Bq
                loc = np.zeros((s, 2, 2), np.int64)
                for r in range(s):
                    for eps in range(2):
                        loc[r, eps, 0] = phi(s1[r], hh[r] + eps, prm.H)
                        loc[r, eps, 1] = phi(s2[r], hh[r] + eps, prm.H)
                return [hh, loc]
            hh_sh, loc_sh = c.myao(fnB, [Qr, s1_sh, s2_sh], "hash_probe")
            # 4 main-cell + sigma stash 2D reads per radius, one shared row selector
            ct_u = he.begin_row(e)
            Tsh = np.zeros((m, s, prm.Pn, 4), np.int64)
            for r in range(s):
                j = 0
                for eps in range(2):
                    for t in range(2):
                        col = self.onehot(loc_sh[:, r, eps, t], ncol)
                        Tsh[:, r, j] = he.read2d(ct_u, r, col)
                        j += 1
                for q in range(prm.sigma):
                    Tsh[:, r, 4 + q] = he.read2d(ct_u, r, pubcol[q])

            def fnC(T, hh):
                found, cc, crow, rad = upper_match(T, hh, prm)
                if c.debug:
                    c.cur = dict(found=found, c=int(cc), rad=rad)
                return [cc, crow, found]
            cand, crow, found = c.myao(fnC, [Tsh, hh_sh], "match_priority")
            ec = self.onehot(cand, srv.prm.N + 1)
            vec = self.read1d(srv.Avec, ec)
            dc = self.dist(vec[:, None, :d], vec[:, None, d])[:, 0]

            def fnD(act_, found_, c_, dc_, dv_, crow_, v_, l_, down_):
                nv, nd, ni, nl, na, gam = upper_transition(
                    int(act_), int(found_), int(c_), int(dc_), int(dv_), int(crow_),
                    int(v_), int(l_), int(down_))
                if c.debug:
                    c.trace.append(dict(act=int(act_), l=int(l_), v=int(v_), gam=gam,
                                        dv=int(dv_), **c.cur))
                return [nv, nd, ni, nl, na]
            v, dv, i, l, act = c.myao(fnD, [act, found, cand, dc, dv, crow, v, l, down], "transition")
        return v, dv

    # ---------------- beam phase ----------------
    def beam(self, ep0, dep0):
        prm, srv, c = self.prm, self.srv, self.c
        D0, d, N = prm.D0, prm.d, prm.N

        def fnI(ep, dd):
            W, V = beam_init(int(ep), int(dd), prm)
            return [W, V, int(ep), 1]
        W, V, usel, live = c.myao(fnI, [ep0, dep0], "beam_init")
        for t in range(prm.Tb):
            e = self.onehot(usel, N + 1)
            adj = self.read1d(srv.Aadj, e)
            ids, nu = adj[:, :D0], adj[:, D0:]
            vecs = np.stack([self.read1d(srv.Avec, self.onehot(ids[:, j], N + 1)) for j in range(D0)], 1)
            dj = self.dist(vecs[:, :, :d], vecs[:, :, d])

            def fnU(W_, V_, us_, lv_, ids_, dj_, nu_, _t=t):
                Wn, Vn, un, ln = beam_step(W_, V_, int(us_), int(lv_), ids_, dj_, nu_, _t, prm)
                if c.debug and _t == prm.Tb - 1:
                    c.cur["beam_live_end"] = ln
                return [Wn, Vn, un, ln]
            W, V, usel, live = c.myao(fnU, [W, V, usel, live, ids, dj, nu], "beam_update")

        def fnF(W_):
            valid = W_[3] == 1
            out = np.where(valid, W_[0], 0)[:prm.k]
            return [out, int(valid[:prm.k].sum())]
        return c.myao_open(fnF, [W], "final")

    def search(self, Q, nq):
        self.Q, self.nq = Q, nq
        ep0, dep0 = self.upper()
        ids, nvalid = self.beam(ep0, dep0)
        return [int(x) for x in ids if x != 0]


# --------------------------------------------------------------------------
# plain reference implementing the same bounded algorithm (oracle + checks)
# --------------------------------------------------------------------------
def plain_protocol(srv, q):
    prm = srv.prm
    s, d = prm.s, prm.d
    X = srv.X
    q = q.astype(np.int64)
    i, v, l, xv = srv.entry_state()[0], srv.ep, srv.top, srv.X[srv.ep]
    dv = int(((q - xv) ** 2).sum())
    act = int(l > 0)
    trace = []
    for it in range(prm.Tg):
        ireq = i if act else 0
        th = srv.theta[:, ireq]
        blk = th[3:].reshape(s, d + 4)
        a = signed(blk[:, :d])
        b, w = blk[:, d], blk[:, d + 1]
        s1, s2 = blk[:, d + 2], blk[:, d + 3]
        Qb = hash_blocks(prm, a, b, w, q)
        hh = Qb.sum(1) // prm.Bq
        true_h = np.array([lsh_key(prm, a[r], int(b[r]), int(w[r]), q) for r in range(s)])
        rounding_ok = bool(np.all((true_h - hh >= 0) & (true_h - hh <= 1)))
        T = np.zeros((s, prm.Pn, 4), np.int64)
        for r in range(s):
            j = 0
            for eps in range(2):
                for t, sd in enumerate((s1[r], s2[r])):
                    col = phi(int(sd), hh[r] + eps, prm.H)
                    T[r, j] = [signed(srv.Dtab[r][f, ireq, col]) for f in range(4)]
                    j += 1
            for qq in range(prm.sigma):
                T[r, 4 + qq] = [signed(srv.Dtab[r][f, ireq, prm.H + qq]) for f in range(4)]
        found, c, crow, rad = upper_match(T, hh, prm)
        dc = int(((q - X[c]) ** 2).sum())
        down = int(th[2])
        improve = False
        if act:
            nbl = srv.nb[l][v]
            improve = bool(len(nbl) and ((X[nbl] - q) ** 2).sum(1).min() < dv)
        nv, nd, ni, nl, na, gam = upper_transition(act, found, c, dc, dv, crow, v, l, down)
        trace.append(dict(act=act, l=l, v=v, gam=gam, dv=dv, found=found, c=int(c), rad=rad,
                          improve=improve, rounding_ok=rounding_ok))
        v, dv, i, l, act = nv, nd, ni, nl, na
    W, V = beam_init(v, dv, prm)
    usel, live = v, 1
    for t in range(prm.Tb):
        ids = srv.Aadj[:prm.D0, usel]
        nu = srv.Aadj[prm.D0:, usel]
        cd = ((X[ids] - q) ** 2).sum(1)
        W, V, usel, live = beam_step(W, V, usel, live, ids, cd, nu, t, prm)
    valid = W[3] == 1
    out = [int(x) for x in np.where(valid, W[0], 0)[:prm.k] if x != 0]
    return out, trace, dict(ep0=v, beam_live_end=int(live), upper_unfinished=int(act))
