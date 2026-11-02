"""Instrumented execution of the private HNSW protocol (vsann.SecureANN) at real-dataset scale.

Every query is executed for real over additive shares (Beaver products, masked 1-D reads, shared
beam state, MYao wrappers). The server's heavy 1-D-read matrix products run for real on all cores
(numba). Garbled circuits and threshold HE stay ideal functionalities (as in vsann.py) but every
call is *metered*: bytes per party/direction, message flights, AND gates, HE operation counts, and
measured wall-clock of the real parts. costmodel.py turns the counters into time/communication."""
import time
from collections import Counter, defaultdict

import numpy as np

from vsann import (MPC, SecureANN, SimHE, P, signed, upper_match, upper_transition, beam_step,
                   beam_init, share_query)
from fastops import matvec_mod
from gc_model import GCModel

BPE = 4                       # bytes per field element (p < 2^31)


class Meter:
    def __init__(self, m):
        self.m = m
        self.phase = "setup"
        self.cs = defaultdict(lambda: np.zeros(m))   # (phase,cat) -> bytes sent by each client
        self.cr = defaultdict(lambda: np.zeros(m))   # received by each client
        self.ss = Counter()                          # server sent
        self.sr = Counter()                          # server received
        self.fl = Counter()                          # message flights (one-way latencies)
        self.tsrv = Counter()                        # measured server compute (s)
        self.tcli = Counter()                        # measured compute of ONE client (s)
        self.tsim = Counter()                        # simulator-only work (not protocol cost)
        self.cnt = Counter()
        self.gc = defaultdict(lambda: Counter())     # circuit -> aggregate counters
        self.gc_max = {}                             # circuit -> size of one instance

    def k(self, cat):
        return (self.phase, cat)

    def c2s(self, cat, nbytes):                      # every client -> server
        self.cs[self.k(cat)] += nbytes
        self.sr[self.k(cat)] += nbytes * self.m

    def s2c(self, cat, nbytes, to=None):             # server -> clients (list of idx)
        to = range(self.m) if to is None else to
        for i in to:
            self.cr[self.k(cat)][i] += nbytes
        self.ss[self.k(cat)] += nbytes * len(list(to))

    def a2a(self, cat, nbytes):                      # all-to-all among clients
        self.cs[self.k(cat)] += nbytes * (self.m - 1)
        self.cr[self.k(cat)] += nbytes * (self.m - 1)

    def c2c(self, cat, src, dst, nbytes):
        self.cs[self.k(cat)][src] += nbytes
        self.cr[self.k(cat)][dst] += nbytes

    def flights(self, cat, k):
        self.fl[self.k(cat)] += k


class MPCM(MPC):
    """MPC context with metering. Offline (dealer) work is excluded from protocol timers."""

    def __init__(self, m, meter, gcm, seed=1):
        super().__init__(m, seed=seed, debug=False)
        self.meter, self.gcm = meter, gcm

    def mul(self, X, Y, cat="beaver"):
        shape = X.shape[1:]
        A, B = self.rint(shape), self.rint(shape)                  # dealer triples (offline)
        SA, SB, SC = self.share(A), self.share(B), self.share(np.mod(A * B, P))
        t0 = time.perf_counter()
        e, f = self.reveal(X - SA), self.reveal(Y - SB)
        Z = np.mod(SC + np.mod(e * SB, P) + np.mod(f * SA, P), P)
        Z[0] = np.mod(Z[0] + np.mod(e * f, P), P)
        n = A.size
        self.meter.tcli[self.meter.k(cat)] += (time.perf_counter() - t0) / self.m
        self.meter.a2a(cat, 2 * n * BPE)                           # open e,f: all-to-all
        self.meter.flights(cat, 1)
        self.meter.cnt[("triples", self.meter.phase)] += n
        return Z

    def _gc(self, fn, inputs, name, open_output=False):
        t0 = time.perf_counter()
        vals = [signed(self.reveal(I)) for I in inputs]
        outs = list(fn(*vals))
        self.meter.tsim[("gc_functional", name)] += time.perf_counter() - t0
        in_el = sum(int(np.prod(I.shape[1:], dtype=np.int64)) for I in inputs)
        out_el = sum(int(np.size(y)) for y in outs) if not open_output else sum(int(np.size(y)) for y in outs)
        c = self.gcm.cost(name, in_el, out_el, open_output)
        mt = self.meter
        g = mt.gc[name]
        g["calls"] += 1
        g["and_core"] += c["core"]
        g["and_io"] += c["io"]
        g["in_bits"] += c["in_bits"]
        g["mask_bits"] += c["mask_bits"]
        mt.gc_max[name] = dict(ands=c["ands"], core=c["core"], io=c["io"], table_bytes=c["table_bytes"])
        mt.cnt[("ands", mt.phase)] += c["ands"]
        mt.s2c("gc_tables", c["table_bytes"], to=[0])              # garbler(server) -> evaluator(P1)
        bits_per_client = c["in_bits"] // self.m + c["mask_bits"] // self.m
        mt.c2s("gc_ot", bits_per_client / 8)                       # OT choice corrections
        mt.s2c("gc_ot", bits_per_client * 32)                      # two masked 128-bit labels per OT
        for j in range(1, self.m):                                 # clients forward labels to evaluator
            mt.c2c("gc_labels", j, 0, bits_per_client * 16)
        if not open_output:
            mt.s2c("gc_out", 0)
            for j in range(1, self.m):
                mt.c2c("gc_out", 0, j, c["out_elems"] * BPE)       # evaluator broadcasts masked output
        mt.flights("gc", 4)
        return outs

    def myao(self, fn, inputs, name="circ"):
        outs_raw = self._gc(fn, inputs, name)
        outs = []
        for y in outs_raw:
            y = np.mod(np.asarray(y, dtype=np.int64), P)
            eta = self.rint((self.m,) + y.shape)
            z = np.mod(y - eta.sum(0), P)
            sh = eta.copy()
            sh[0] = np.mod(z + eta[0], P)
            outs.append(sh)
        return outs

    def myao_open(self, fn, inputs, name="final"):
        outs = self._gc(fn, inputs, name, open_output=True)
        return outs


class FastSimHE(SimHE):
    """Same functionality as SimHE for a one-hot row selector: reads D_r[:, i, :] @ v."""

    def __init__(self, mpc, Dtab, meter):
        super().__init__(mpc, Dtab)
        self.meter = meter

    def begin_row(self, Ush):
        u = np.mod(Ush.sum(0), P)
        self.meter.cnt["he_row_enc_per_client"] += len(u)
        return int(np.argmax(u))

    def read2d(self, i, r, Vsh):
        cv = np.mod(Vsh.sum(0), P)
        out = matmul_mod_small(self.Dtab[r][:, i, :], cv)
        self.meter.cnt["he_col_reads"] += 1
        return self.mpc.share(out)


def matmul_mod_small(A, v):
    from vsann import matmul_mod
    return matmul_mod(A, v)


class SecureFast(SecureANN):
    def __init__(self, srv, mpc, meter, gcm, theta32, Avec32, Aadj32):
        self.srv, self.c, self.prm, self.mt, self.gcm = srv, mpc, srv.prm, meter, gcm
        self.he = FastSimHE(mpc, srv.Dtab, meter)
        self.theta32, self.Avec32, self.Aadj32 = theta32, Avec32, Aadj32
        self.checked = False

    # -- Sec. 4: shared ID -> shared one-hot (ideal functionality; cost = 1 opening) -------
    def onehot(self, Z, n, flight=True):
        c, mt = self.c, self.mt
        t0 = time.perf_counter()
        z = np.asarray(c.reveal(Z)).astype(np.int64)
        e = np.zeros(z.shape + (n,), np.int64)
        np.put_along_axis(e, z[..., None], 1, -1)
        out = c.share(e)
        mt.tsim[("sim", "onehot")] += time.perf_counter() - t0
        k = int(np.size(z))
        mt.a2a("onehot", k * BPE)                                  # open tau = z - alpha (all-to-all)
        if flight:
            mt.flights("onehot", 1)
        mt.cnt[("onehot_conv", n)] += k
        return out

    # -- Sec. 5.2: masked 1-D read, K reads against the same matrix in one round ----------
    def read1d_multi(self, A32, Esh, cat):
        """Esh (m,K,n) shared one-hots; returns shares (m,K,a) of the selected columns."""
        c, mt = self.c, self.mt
        m, K, n = Esh.shape
        a = A32.shape[0]
        t0 = time.perf_counter()
        Rsh = c.share(c.rint((K, n)))                              # offline correlation r
        mt.tsim[("sim", "read1d_offline")] += time.perf_counter() - t0
        t0 = time.perf_counter()
        qsh = np.mod(Esh - Rsh, P)                                 # each client: its share of e - r
        mt.tcli[mt.k(cat)] += (time.perf_counter() - t0) / m
        t0 = time.perf_counter()
        qA = np.mod(qsh.sum(0), P)                                 # server adds the m shares  (K,n)
        Y = matvec_mod(A32, qA.T)                                  # server: A @ (e - r)  (REAL)
        mt.tsrv[mt.k(cat)] += time.perf_counter() - t0
        mt.c2s(cat, K * n * BPE)
        mt.s2c(cat, K * a * BPE, to=[0])
        mt.flights(cat, 2)
        mt.cnt[("read1d_cols", mt.phase)] += K
        mt.cnt[f"rs:{a}:{n}:{K}"] += 1
        mt.cnt[("read1d_macs", mt.phase)] += K * a * n
        t0 = time.perf_counter()
        z = np.argmax(np.mod(Esh.sum(0), P), axis=1)               # simulator knows the selected column
        out = A32[:, z].astype(np.int64).T                         # (K,a) = A e
        if not self.checked:                                       # validate kernel vs A r + A(e-r)
            R = np.mod(Rsh.sum(0), P)
            AR = matvec_mod(A32, R.T)
            assert np.array_equal(np.mod(AR + Y, P), out.T), "read1d kernel mismatch"
            self.checked = True
        mt.tsim[("sim", "read1d_check")] += time.perf_counter() - t0
        return np.transpose(c.share(out), (0, 1, 2))

    def dist_multi(self, X, Nn):
        c, mt = self.c, self.mt
        m, K, d = X.shape
        Qb = np.broadcast_to(self.Q[:, None, :], (m, K, d)).copy()
        z = np.mod(c.mul(X, Qb).sum(-1), P)
        return np.mod(self.nq[:, None] + Nn - 2 * z, P)

    # ---------------- upper phase ----------------
    def upper(self):
        prm, srv, c, he, mt = self.prm, self.srv, self.c, self.he, self.mt
        s, d, m, U, ncol = prm.s, prm.d, prm.m, srv.U, prm.ncol
        i0, v0, l0, xv0, nv0 = srv.entry_state()
        i, v, l = c.share(i0), c.share(v0), c.share(l0)
        xs = c.share(xv0[None, :])
        dv = self.dist_multi(xs, c.share(np.array([nv0])))[:, 0]
        act = c.share(1 if l0 > 0 else 0)
        pubcol = [c.pub(np.eye(ncol, dtype=np.int64)[prm.H + j]) for j in range(prm.sigma)]
        mt.phase = "upper"
        for it in range(prm.Tg):
            ireq, = c.myao(lambda a, b: [np.where(a == 1, b, 0)], [act, i], "mux_row")
            e = self.onehot(ireq, U)
            th = self.read1d_multi(self.theta32, e[:, None, :], "read1d_theta")[:, 0, :]
            down = th[:, 2]
            blk = th[:, 3:].reshape(m, s, d + 4)
            a_sh, b_sh, w_sh = blk[:, :, :d], blk[:, :, d], blk[:, :, d + 1]
            s1_sh, s2_sh = blk[:, :, d + 2], blk[:, :, d + 3]
            Qb = np.broadcast_to(self.Q[:, None, :], (m, s, d)).copy()
            prod = c.mul(a_sh, Qb, "beaver_hash")
            Nb = np.stack([np.mod(prod[:, :, bk].sum(-1), P) for bk in prm.blocks], -1)
            Nb[:, :, 0] = np.mod(Nb[:, :, 0] + b_sh * prm.Sq, P)
            Nb = np.mod(Nb * prm.Sw, P)

            def fnA(Nn, w):
                return [(prm.Bq * Nn) // (prm.Sa * prm.Sq * w)[:, None]]
            Qrb, = c.myao(fnA, [Nb, w_sh], "div_floor")
            Qr = np.mod(Qrb.sum(-1), P)

            from vsann import phi

            def fnB(Q, s1, s2):
                hh = Q // prm.Bq
                loc = np.zeros((s, 2, 2), np.int64)
                for r in range(s):
                    for eps in range(2):
                        loc[r, eps, 0] = phi(s1[r], hh[r] + eps, prm.H)
                        loc[r, eps, 1] = phi(s2[r], hh[r] + eps, prm.H)
                return [hh, loc]
            hh_sh, loc_sh = c.myao(fnB, [Qr, s1_sh, s2_sh], "hash_probe")
            # 2-D reads: 4 hashed cells + sigma stash cells per radius. One batch of 3 flights.
            ct_u = he.begin_row(e)
            mt.flights("he", 1)
            Tsh = np.zeros((m, s, prm.Pn, 4), np.int64)
            for r in range(s):
                j = 0
                for eps in range(2):
                    for t in range(2):
                        col = self.onehot(loc_sh[:, r, eps, t], ncol, flight=(r == 0 and j == 0))
                        Tsh[:, r, j] = he.read2d(ct_u, r, col)
                        j += 1
                for q in range(prm.sigma):
                    Tsh[:, r, 4 + q] = he.read2d(ct_u, r, pubcol[q])
            mt.flights("he", 3)
            mt.cnt[("he_probes", "upper")] += s * prm.Pn

            def fnC(T, hh):
                found, cc, crow, rad = upper_match(T, hh, prm)
                return [cc, crow, found]
            cand, crow, found = c.myao(fnC, [Tsh, hh_sh], "match_priority")
            ec = self.onehot(cand, srv.prm.N + 1)
            vec = self.read1d_multi(self.Avec32, ec[:, None, :], "read1d_vec")[:, 0, :]
            dc = self.dist_multi(vec[:, None, :d], vec[:, None, d])[:, 0]

            def fnD(act_, found_, c_, dc_, dv_, crow_, v_, l_, down_):
                nv, nd, ni, nl, na, gam = upper_transition(
                    int(act_), int(found_), int(c_), int(dc_), int(dv_), int(crow_),
                    int(v_), int(l_), int(down_))
                return [nv, nd, ni, nl, na]
            v, dv, i, l, act = c.myao(fnD, [act, found, cand, dc, dv, crow, v, l, down], "transition")
        return v, dv

    # ---------------- beam phase ----------------
    def beam(self, ep0, dep0):
        prm, srv, c, mt = self.prm, self.srv, self.c, self.mt
        D0, d, N = prm.D0, prm.d, prm.N
        mt.phase = "beam"

        def fnI(ep, dd):
            W, V = beam_init(int(ep), int(dd), prm)
            return [W, V, int(ep), 1]
        W, V, usel, live = c.myao(fnI, [ep0, dep0], "beam_init")
        for t in range(prm.Tb):
            e = self.onehot(usel, N + 1)
            adj = self.read1d_multi(self.Aadj32, e[:, None, :], "read1d_adj")[:, 0, :]
            ids, nu = adj[:, :D0], adj[:, D0:]
            E16 = self.onehot(ids, N + 1)                                    # (m,D0,N+1)
            vecs = self.read1d_multi(self.Avec32, E16, "read1d_vec")        # (m,D0,d+1)
            dj = self.dist_multi(vecs[:, :, :d], vecs[:, :, d])

            def fnU(W_, V_, us_, lv_, ids_, dj_, nu_, _t=t):
                Wn, Vn, un, ln = beam_step(W_, V_, int(us_), int(lv_), ids_, dj_, nu_, _t, prm)
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


class SecureMask(SecureFast):
    """DELPHI-style variant: threshold HE is used ONLY in preprocessing (to build the (r,s,h) read
    correlations and Beaver triples). Online, the 2-D dictionary read is
        (1) one masked 1-D read of the whole dictionary row  D[:, i, :]  (plaintext, uses the correlation),
        (2) a Beaver dot product of that shared row with the shared one-hot column selector.
    The dictionary rows are appended to the theta matrix so (1) rides on the existing theta read."""

    def upper(self):
        prm, srv, c, mt = self.prm, self.srv, self.c, self.mt
        s, d, m, U, ncol, H, sg = prm.s, prm.d, prm.m, srv.U, prm.ncol, prm.H, prm.sigma
        F = 4
        A = srv.theta.shape[0]
        i0, v0, l0, xv0, nv0 = srv.entry_state()
        i, v, l = c.share(i0), c.share(v0), c.share(l0)
        xs = c.share(xv0[None, :])
        dv = self.dist_multi(xs, c.share(np.array([nv0])))[:, 0]
        act = c.share(1 if l0 > 0 else 0)
        mt.phase = "upper"
        from vsann import phi
        for it in range(prm.Tg):
            ireq, = c.myao(lambda a, b: [np.where(a == 1, b, 0)], [act, i], "mux_row")
            e = self.onehot(ireq, U)
            th_all = self.read1d_multi(self.theta32, e[:, None, :], "read1d_theta")[:, 0, :]
            th, rowv = th_all[:, :A], th_all[:, A:].reshape(m, s, F, ncol)
            down = th[:, 2]
            blk = th[:, 3:].reshape(m, s, d + 4)
            a_sh, b_sh, w_sh = blk[:, :, :d], blk[:, :, d], blk[:, :, d + 1]
            s1_sh, s2_sh = blk[:, :, d + 2], blk[:, :, d + 3]
            Qb = np.broadcast_to(self.Q[:, None, :], (m, s, d)).copy()
            prod = c.mul(a_sh, Qb, "beaver_hash")
            Nb = np.stack([np.mod(prod[:, :, bk].sum(-1), P) for bk in prm.blocks], -1)
            Nb[:, :, 0] = np.mod(Nb[:, :, 0] + b_sh * prm.Sq, P)
            Nb = np.mod(Nb * prm.Sw, P)

            def fnA(Nn, w):
                return [(prm.Bq * Nn) // (prm.Sa * prm.Sq * w)[:, None]]
            Qrb, = c.myao(fnA, [Nb, w_sh], "div_floor")
            Qr = np.mod(Qrb.sum(-1), P)

            def fnB(Q, s1, s2):
                hh = Q // prm.Bq
                loc = np.zeros((s, 2, 2), np.int64)
                for r in range(s):
                    for eps in range(2):
                        loc[r, eps, 0] = phi(s1[r], hh[r] + eps, prm.H)
                        loc[r, eps, 1] = phi(s2[r], hh[r] + eps, prm.H)
                return [hh, loc]
            hh_sh, loc_sh = c.myao(fnB, [Qr, s1_sh, s2_sh], "hash_probe")
            # column selection: shared one-hot (4 hashed probes / radius) . shared dictionary row
            ec = self.onehot(loc_sh, ncol).reshape(m, s, 4, ncol)
            X = np.broadcast_to(rowv[:, :, None, :, :], (m, s, 4, F, ncol)).copy()
            Y = np.broadcast_to(ec[:, :, :, None, :], (m, s, 4, F, ncol)).copy()
            Th = np.mod(c.mul(X, Y, "beaver_dict").sum(-1), P)            # (m,s,4,F)
            Tsh = np.zeros((m, s, prm.Pn, 4), np.int64)
            Tsh[:, :, :4, :] = Th
            for q in range(sg):                                           # stash cells: public columns, local
                Tsh[:, :, 4 + q, :] = rowv[:, :, :, H + q]

            def fnC(T, hh):
                found, cc, crow, rad = upper_match(T, hh, prm)
                return [cc, crow, found]
            cand, crow, found = c.myao(fnC, [Tsh, hh_sh], "match_priority")
            ec2 = self.onehot(cand, srv.prm.N + 1)
            vec = self.read1d_multi(self.Avec32, ec2[:, None, :], "read1d_vec")[:, 0, :]
            dc = self.dist_multi(vec[:, None, :d], vec[:, None, d])[:, 0]

            def fnD(act_, found_, c_, dc_, dv_, crow_, v_, l_, down_):
                nv, nd, ni, nl, na, gam = upper_transition(
                    int(act_), int(found_), int(c_), int(dc_), int(dv_), int(crow_),
                    int(v_), int(l_), int(down_))
                return [nv, nd, ni, nl, na]
            v, dv, i, l, act = c.myao(fnD, [act, found, cand, dc, dv, crow, v, l, down], "transition")
        return v, dv


def prepare(srv, mask=False):
    """uint32 copies of the server's tables for the numba kernels."""
    th = np.ascontiguousarray(srv.theta.astype(np.uint32))
    if mask:        # append dictionary rows: row (r,f,b) of the stacked matrix = Dtab[r][f, :, b]
        Dflat = np.stack(srv.Dtab).transpose(0, 1, 3, 2).reshape(-1, srv.U).astype(np.uint32)
        th = np.ascontiguousarray(np.vstack([th, Dflat]))
    av = np.ascontiguousarray(srv.Avec.astype(np.uint32))
    aj = np.ascontiguousarray(srv.Aadj.astype(np.uint32))
    wmax = int(srv.theta[3 + srv.prm.d + 1::srv.prm.d + 4].max()) if False else 0
    prm = srv.prm
    wcols = [3 + r * (prm.d + 4) + prm.d + 1 for r in range(prm.s)]
    wmax = int(srv.theta[wcols].max())
    return th, av, aj, wmax


def run_query(srv, prep, q, m_seed, aes_ands=6400, mode="he"):
    prm = srv.prm
    th, av, aj, wmax = prep
    meter = Meter(prm.m)
    gcm = GCModel(prm, srv.U, wmax, aes_ands)
    mpc = MPCM(prm.m, meter, gcm, seed=m_seed)
    sec = (SecureMask if mode == "mask" else SecureFast)(srv, mpc, meter, gcm, th, av, aj)
    blocks = [q[idx] for idx in prm.blocks]
    t0 = time.perf_counter()
    Q, nq = share_query(mpc, blocks, prm)
    meter.tcli[("setup", "share_query")] += (time.perf_counter() - t0) / prm.m
    meter.c2c("share_query", 0, 0, 0)
    for i in range(prm.m):                                   # each client sends one share of its block to every other
        for j in range(prm.m):
            if i != j:
                meter.c2c("share_query", i, j, (len(prm.blocks[i]) + 1) * BPE)
    meter.flights("share_query", 1)
    res = sec.search(Q, nq)
    return res, meter
