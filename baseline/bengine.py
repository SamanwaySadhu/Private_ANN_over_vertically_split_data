"""Instrumented execution of the baseline private-ANN protocol (same metering conventions as engine.py).

Protocol
  upper layers  exact greedy HNSW descent over secret-shared state: per step
                  GC one-hot(row)  ->  HE read of the adjacency row  ->  GC one-hot of the M neighbour rows
                  ->  HE read of their vectors  ->  Beaver squared distances  ->  GC upper_step (argmin/move/descend)
  layer 0       the beam search of the main protocol, with the same fused GC beam update
  one-hot       exact, by garbled circuit (no Lagrange / alpha powers)
  1-D read      threshold HE *online*: clients encrypt their additive shares of the one-hot, the server computes
                A . Enc(e) with plaintext-ciphertext products, adds the clients' encrypted output masks, the clients
                threshold-decrypt to P1 -> additive shares of A e.  No offline correlations, no mask (r,s,h).
  Beaver triples generated with threshold HE during the online phase (one batch at the start of the query).

As in engine.py garbled circuits and HE are ideal functionalities in the simulation (the values are
computed in the clear inside one call) but every call is metered; bcost.py converts the counters into
time and bytes. The one-hot is kept as the selected index inside the simulator instead of an (m,K,n)
array of shares (n up to 10^6); the metered cost is that of the full one-hot circuit."""
import time

import numpy as np

import _path  # noqa: F401
from engine import BPE, Meter, MPCM
from vsann import P, beam_init, beam_step, share_query
from bgc import BaselineGC
from bproto import upper_step


class OneHot:
    """Simulator handle for K shared one-hot vectors over a domain of n elements."""

    def __init__(self, z, n):
        self.z, self.n = np.asarray(z, np.int64).reshape(-1), n


class BMPC(MPCM):
    def gc_meter(self, name, in_el, out_el, open_output=False):
        """Metering block of MPCM._gc for a circuit whose output is not materialised."""
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
        mt.s2c("gc_tables", c["table_bytes"], to=[0])
        bits_per_client = c["in_bits"] // self.m + c["mask_bits"] // self.m
        mt.c2s("gc_ot", bits_per_client / 8)
        mt.s2c("gc_ot", bits_per_client * 32)
        for j in range(1, self.m):
            mt.c2c("gc_labels", j, 0, bits_per_client * 16)
        mt.s2c("gc_out", 0)
        for j in range(1, self.m):
            mt.c2c("gc_out", 0, j, c["out_elems"] * BPE)
        mt.flights("gc", 4)


class SecureBaseline:
    def __init__(self, srv, mpc, meter, gcm):
        self.srv, self.c, self.prm, self.mt, self.gcm = srv, mpc, srv.prm, meter, gcm

    # ---- exact one-hot by garbled circuit ----------------------------------------------------
    def onehot(self, Z, n):
        c, mt = self.c, self.mt
        t0 = time.perf_counter()
        z = np.asarray(c.reveal(Z)).astype(np.int64)
        assert z.min() >= 0 and z.max() < n
        mt.tsim[("sim", "onehot")] += time.perf_counter() - t0
        K = int(z.size)
        c.gc_meter(f"onehot:{n}", K, K * n)
        mt.cnt[("onehot_conv", n)] += K
        return OneHot(z, n)

    # ---- 1-D read with threshold HE, online ---------------------------------------------------
    def read(self, A, E, cat):
        """A (a,n) plaintext server matrix; E: OneHot of K selectors. Returns shares (m,K,a) of A e_k."""
        c, mt = self.c, self.mt
        a, n = A.shape
        assert n == E.n
        K = len(E.z)
        t0 = time.perf_counter()
        out = np.mod(A[:, E.z].T, P)
        mt.tsim[("sim", "he_read")] += time.perf_counter() - t0
        mt.flights(cat, 3)                       # clients->server (Enc shares), server->clients (ct), partial dec -> P1
        mt.cnt[f"he1d|{cat}|{a}|{n}|{K}"] += 1
        return c.share(out)

    def dist_multi(self, X, Nn):
        c = self.c
        m, K, d = X.shape
        Qb = np.broadcast_to(self.Q[:, None, :], (m, K, d)).copy()
        z = np.mod(c.mul(X, Qb).sum(-1), P)
        return np.mod(self.nq[:, None] + Nn - 2 * z, P)

    # ---- upper layers: exact greedy descent ----------------------------------------------------
    def upper(self):
        prm, srv, c, mt = self.prm, self.srv, self.c, self.mt
        d, m, M, U = prm.d, prm.m, prm.M, srv.U
        i0, v0, l0, xv0, nv0 = srv.entry_state()
        i, v, l = c.share(i0), c.share(v0), c.share(l0)
        xs = c.share(xv0[None, :])
        dv = self.dist_multi(xs, c.share(np.array([nv0])))[:, 0]
        act = c.share(1 if l0 > 0 else 0)
        mt.phase = "upper"

        def fnU(act_, dv_, v_, l_, down_, dj_, nrow_, nnode_):
            return list(upper_step(act_, dv_, v_, l_, down_, dj_, nrow_, nnode_))
        for _ in range(prm.Tg):
            e = self.onehot(i, U)
            adj = self.read(srv.Aup_adj, e, "he_up_adj")[:, 0, :]
            nrow, down = adj[:, :M], adj[:, M]
            e2 = self.onehot(nrow, U)
            vec = self.read(srv.Aup_vec, e2, "he_up_vec")                 # (m,M,d+2)
            dj = self.dist_multi(vec[:, :, :d], vec[:, :, d])
            v, dv, i, l, act = c.myao(fnU, [act, dv, v, l, down, dj, nrow, vec[:, :, d + 1]], "upper_step")
        return v, dv

    # ---- layer 0: beam search ---------------------------------------------------------------------
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
            adj = self.read(srv.Aadj, e, "he_adj")[:, 0, :]
            ids, nu = adj[:, :D0], adj[:, D0:]
            vecs = self.read(srv.Avec, self.onehot(ids, N + 1), "he_vec")
            dj = self.dist_multi(vecs[:, :, :d], vecs[:, :, d])

            def fnB(W_, V_, us_, lv_, ids_, dj_, nu_, _t=t):
                Wn, Vn, un, ln = beam_step(W_, V_, int(us_), int(lv_), ids_, dj_, nu_, _t, prm)
                return [Wn, Vn, un, ln]
            W, V, usel, live = c.myao(fnB, [W, V, usel, live, ids, dj, nu], "beam_update")

        def fnF(W_):
            valid = W_[3] == 1
            return [np.where(valid, W_[0], 0)[:prm.k], int(valid[:prm.k].sum())]
        return c.myao_open(fnF, [W], "final")

    def search(self, Q, nq):
        self.Q, self.nq = Q, nq
        ep0, dep0 = self.upper()
        ids, _ = self.beam(ep0, dep0)
        return [int(x) for x in ids if x != 0]


def run_query(srv, q, m_seed, aes_ands=6400):
    prm = srv.prm
    meter = Meter(prm.m)
    gcm = BaselineGC(prm, srv.U, 1, aes_ands)
    mpc = BMPC(prm.m, meter, gcm, seed=m_seed)
    sec = SecureBaseline(srv, mpc, meter, gcm)
    blocks = [q[idx] for idx in prm.blocks]
    t0 = time.perf_counter()
    Q, nq = share_query(mpc, blocks, prm)
    meter.tcli[("setup", "share_query")] += (time.perf_counter() - t0) / prm.m
    for i in range(prm.m):
        for j in range(prm.m):
            if i != j:
                meter.c2c("share_query", i, j, (len(prm.blocks[i]) + 1) * BPE)
    meter.flights("share_query", 1)
    return sec.search(Q, nq), meter
