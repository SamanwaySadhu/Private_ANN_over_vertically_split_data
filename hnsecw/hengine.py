"""Instrumented secure execution of the HNSecW-style baseline over additive shares among n = m+1 parties
(party 0 = server, parties 1..m = the clients, party 1 is the GC evaluator).

Per iteration of a layer (Algorithm 2 of the paper, with the shared state kept as additive shares):
  open C[0] (graph row)  ->  each party reads its share of the graph row locally  ->  GC `visit`
  (visited check against the public list V, dummy replacement; opens the physical vector rows u')
  ->  each party reads its share of the vector rows locally  ->  Beaver squared distances  ->  GC `update`
  (mask, stable sort + truncate of C and W).
Garbled circuits are ideal functionalities (evaluated on reconstructed values inside one call, outputs re-shared with
fresh masks) but metered exactly; Beaver products are executed. Every revealed physical address is recorded and the run
asserts that no row of any table is revealed twice (the obliviousness invariant of the paper's access pattern)."""
import time
from collections import defaultdict

import numpy as np

import _path  # noqa: F401
from vsann import MPC, P
from hgc import HGC
from hproto import visit_fn, merge_trunc
from hserver import Layout

BPE = 4


class HMeter:
    def __init__(self, n):
        self.n = n
        self.phase = "online"
        self.sent = defaultdict(lambda: np.zeros(n))
        self.recv = defaultdict(lambda: np.zeros(n))
        self.fl = defaultdict(int)
        self.cnt = defaultdict(float)
        self.gc = defaultdict(lambda: defaultdict(float))
        self.gc_max = {}

    def key(self, cat):
        return f"{self.phase}|{cat}"

    def send(self, cat, src, dst, nbytes):
        self.sent[self.key(cat)][src] += nbytes
        self.recv[self.key(cat)][dst] += nbytes

    def open_all(self, cat, L):
        """every party broadcasts L field elements to all others"""
        b = L * BPE * (self.n - 1)
        self.sent[self.key(cat)] += b
        self.recv[self.key(cat)] += b

    def flights(self, cat, k):
        self.fl[self.key(cat)] += k


class HMPC(MPC):
    def __init__(self, n, meter, seed):
        super().__init__(n, seed=seed)
        self.mt = meter

    def mul(self, X, Y, cat="beaver"):
        shape = X.shape[1:]
        L = int(np.prod(shape, dtype=np.int64))
        Z = super().mul(X, Y)
        self.mt.open_all(cat, 2 * L)                 # e = x-a and f = y-b
        self.mt.flights(cat, 1)
        self.mt.cnt["triples"] += L
        return Z

    def gc(self, hgc, name, core, in_shared, fn, n_shared_out, n_open_out, in_public=()):
        """Ideal GC. in_shared: list of share arrays (n,...). fn(*values, *in_public) -> (open_list, shared_list)."""
        mt, n = self.mt, self.m
        vals = [np.mod(self.reveal(I), P) for I in in_shared]
        opens, shareds = fn(*vals, *in_public)
        in_el = sum(int(np.prod(I.shape[1:], dtype=np.int64)) for I in in_shared)
        c = hgc.cost(core, in_el, n_shared_out, n_open_out)
        g = mt.gc[name]
        g["calls"] += 1
        g["and_core"] += c["core"]
        g["and_io"] += c["io"]
        g["in_bits"] += c["in_bits"]
        g["mask_bits"] += c["mask_bits"]
        g["ands"] += c["ands"]
        mt.gc_max[name] = c["ands"]
        mt.cnt["ands"] += c["ands"]
        l = hgc.l
        mt.send("gc_tables", 0, 1, c["table_bytes"])
        mt.send("gc_labels", 0, 1, 16 * l * in_el)                       # garbler's own input labels
        bits_cl = (in_el + n_shared_out) * l                             # per client: input share bits + mask bits
        for j in range(1, n):
            mt.send("gc_ot", j, 0, bits_cl / 8)
            mt.send("gc_ot", 0, j, bits_cl * 32)
            if j != 1:
                mt.send("gc_labels", j, 1, bits_cl * 16)
        outb = (n_shared_out + n_open_out) * BPE
        for j in range(n):
            if j != 1:
                mt.send("gc_out", 1, j, outb)
        mt.flights("gc", 4)
        out_sh = []
        for y in shareds:
            y = np.mod(np.asarray(y, np.int64), P)
            out_sh.append(self.share(y))
        return list(opens), out_sh


class HSecure:
    def __init__(self, srv, seed):
        self.srv, self.prm = srv, srv.prm
        self.n = self.prm.n
        self.mt = HMeter(self.n)
        self.c = HMPC(self.n, self.mt, seed)
        self.hgc = HGC(self.prm, srv)
        self.lay = Layout(srv, seed + 99991)
        self.revealed = defaultdict(set)

    # ---- revealed physical addresses must be distinct per table ------------------------------------
    def note(self, table, addr):
        for a in np.atleast_1d(addr).tolist():
            assert a not in self.revealed[table], f"physical row {a} of {table} revealed twice"
            self.revealed[table].add(a)

    def open(self, S, cat):
        self.mt.open_all(cat, int(np.size(S[0])))
        self.mt.flights(cat, 1)
        return np.mod(S.sum(0), P)

    # ---- local share reads from the (shared, shuffled) tables -------------------------------------------
    def read_vec(self, l, phys):
        """phys: physical vector-table rows of layer l (public). Each party reads its own share: no communication."""
        srv, lay = self.srv, self.lay
        L = srv.L[l]
        lg = lay.iv[l][phys]
        vec, nr = srv.rows(l, lg)
        low = lay.pv[l - 1] if l > 0 else lay.pD
        return dict(vec=self.c.share(vec), norm=self.c.share(nr), ga=self.c.share(lay.pg[l][L.ga[lg]]),
                    vb=self.c.share(low[L.vb[lg]]), flag=self.c.share(L.flag[lg]))

    def read_graph(self, l, phys):
        lg = self.lay.ig[l][phys]
        return self.c.share(self.lay.pv[l][self.srv.L[l].GT[lg]])

    def dist(self, vec, norm):
        c = self.c
        K, d = vec.shape[1:]
        Qb = np.broadcast_to(self.Q[:, None, :], (self.n, K, d)).copy()
        z = np.mod(c.mul(vec, Qb).sum(-1), P)
        return np.mod(self.nq[:, None] + norm - 2 * z, P)

    # ---- one layer ---------------------------------------------------------------------------------------
    def layer(self, l, ep_phys):
        srv, prm, c, hgc, lay = self.srv, self.prm, self.c, self.hgc, self.lay
        L = srv.L[l]
        deg, T, ef, DMAX = L.deg, L.T, L.ef, prm.DMAX
        self.note(("v", l), ep_phys)
        r = self.read_vec(l, np.array([ep_phys]))
        dep = self.dist(r["vec"], r["norm"])                                   # (n,1)
        pgI = lay.pg[l][L.offI + np.arange(T - 1)]
        Cg = np.concatenate([r["ga"], c.share(pgI)], 1)
        Cd = np.concatenate([dep, c.share(np.full(T - 1, DMAX))], 1)
        low = lay.pv[l - 1] if l > 0 else lay.pD
        Wb = np.concatenate([r["vb"], c.share(low[[srv.wdummy_b(l, j) for j in range(1, ef)]] if ef > 1 else np.zeros(0, np.int64))], 1)
        Wd = np.concatenate([dep, c.share(np.full(ef - 1, DMAX))], 1)
        V = [int(ep_phys)]
        lu_cat = f"L{l}"
        for t in range(T):
            cg = self.open(Cg[:, :1], "open_cand")[0]
            self.note(("g", l), cg)
            Cg, Cd = Cg[:, 1:], Cd[:, 1:]
            nbS = self.read_graph(l, np.array([cg]))[:, 0, :]                   # (n,deg) shared row ids
            dumS = c.share(lay.pv[l][L.offA + t * deg + np.arange(deg)])

            def visit(nb, dm, Vpub):
                u, vis = visit_fn(nb, Vpub, dm)
                return [u], [vis]
            (u,), (visS,) = c.gc(hgc, f"visit:L{'up' if l else '0'}", hgc.visit_core(l, t), [nbS, dumS], visit,
                                 deg, deg, in_public=(np.array(V, np.int64),))
            self.note(("v", l), u)
            V += u.tolist()
            r = self.read_vec(l, u)
            dj = self.dist(r["vec"], r["norm"])                                 # (n,deg)

            def update(cg_, cd_, wb_, wd_, ng, dj_, vis_, flag_, nbb):
                d2 = np.where((vis_ == 1) | (flag_ == 1), DMAX, dj_)
                cd2, (cg2,) = merge_trunc(np.r_[cd_, d2], [np.r_[cg_, ng]], T)
                wd2, (wb2,) = merge_trunc(np.r_[wd_, d2], [np.r_[wb_, nbb]], ef)
                return [], [cg2, cd2, wb2, wd2]
            _, (Cg, Cd, Wb, Wd) = c.gc(hgc, f"update:L{'up' if l else '0'}", hgc.core("update", l),
                                       [Cg, Cd, Wb, Wd, r["ga"], dj, visS, r["flag"], r["vb"]], update, T * 2 + ef * 2, 0)
        return Wb, Wd

    def search(self, q):
        srv, prm, c, mt = self.srv, self.prm, self.c, self.mt
        n, m, d = self.n, prm.m, prm.d
        mt.phase = "online"
        # ---- query sharing: client i shares its block (and its block norm) among all n parties
        Q = np.zeros((n, d), np.int64)
        nq = np.zeros(n, np.int64)
        for i, idx in enumerate(prm.blocks):
            blk = q[idx].astype(np.int64)
            Q[:, idx] = c.share(blk)
            nq = np.mod(nq + c.share(int((blk ** 2).sum())), P)
            for j in range(n):
                if j != i + 1:
                    mt.send("share_query", i + 1, j, (len(idx) + 1) * BPE)
        mt.flights("share_query", 1)
        self.Q, self.nq = Q, nq
        ep = int(self.lay.pv[srv.top][srv.entry()])
        mt.cnt["open_ep0"] += 1
        for l in range(srv.top, 0, -1):
            Wb, Wd = self.layer(l, ep)
            ep = int(self.open(Wb[:, :1], "open_ep")[0])
        Wb, Wd = self.layer(0, ep)
        # ---- output: open the k physical rows of D_-1, read, deliver the rows to the clients only
        k = prm.k
        addr = self.open(Wb[:, :k], "open_out")
        self.note("D", addr)
        lg = self.lay.iD[addr]
        vecs, ids = srv.d1_rows(lg)
        for j in range(n):                                                      # shares of k rows -> every client
            for i in range(1, n):
                if j != i:
                    mt.send("output", j, i, k * (d + 1) * BPE)
        mt.flights("output", 1)
        out = [int(x) for x in ids if x != 0]
        return out


def run_query(srv, q, seed):
    sec = HSecure(srv, seed)
    t0 = time.perf_counter()
    res = sec.search(q)
    return res, sec.mt, time.perf_counter() - t0
