"""Instrumented secure execution of the Tiptoe baseline for a vertically split query: the server (party 0) holds the corpus; m
clients (parties 1..m) hold coordinate blocks of the query. NOBODY learns the query, the chosen cluster, the cluster's scores or
any intermediate value; the clients learn only the k ids at the end (opened to client 1, forwarded to the others).

How Tiptoe's single-client protocol (Sec. 3, 4, 5, 6) is split among the clients
  paper                                        here
  client picks cluster i* from the centroids   clients add their local partial distances (centroids are public, so each
  it downloaded                                client computes ||q_i - c_i||^2 alone), GC argmin -> one-hot e, SHARED among clients
  q~ = (0..0, q, 0..0) with q in block i*      q~ = e (x) q by a Beaver OUTER-product (ring Z_{2^lt}); only C+d values are opened,
                                               the C*d-element triple is offline; result: additive shares q~^(i)
  client encrypts q~ (LWE, secret s)           client i encrypts its share under its own additive key share s_i:
                                                 b_i = A s_i + e_i + D q~^(i)  (D = 2^(64-lt)); the server adds the b_i, which is a valid
                                               ciphertext of q~ under s = sum_i s_i; A s_i is query independent (precomputed)
  server: c = M b                              identical, ONE scan of M (hint H = M A precomputed once)
  query tokens: server returns H s under       every client i obtains its own token  H s_i  (one RLWE token per client, per query)
  RLWE(s); client decrypts c locally           c stays at the server; the decryption  round((c - sum_i H s_i)/D)  is a GC over the
                                               shares (c, -H s_1, ..., -H s_m), no party sees the score
  client sorts the scores, picks top           GC top-k selection network over the shared scores
  URL service (PIR on the doc id)              linear id lookup M_id e with the same machinery (ids never leave shares), then GC output
Garbled circuits, LWE/RLWE are ideal functionalities executed on reconstructed values (outputs re-shared with fresh masks) and
metered exactly; the ring arithmetic outside them (Beaver outer product, share conversions) is executed on real additive shares.
tlwe_check.py runs the real LWE share-decryption (multi-key, mod 2^64, rounding) at toy size to validate the construction."""
import time
from collections import defaultdict

import numpy as np

import _path  # noqa: F401
from tgc import TGC
import tproto as tp

OFFLINE_CATS = {"gc_tables", "token_up", "token_down"}


class TMeter:
    def __init__(self, n):
        self.n = n
        self.sent = defaultdict(lambda: np.zeros(n))
        self.recv = defaultdict(lambda: np.zeros(n))
        self.fl = defaultdict(int)
        self.cnt = defaultdict(float)
        self.gc = defaultdict(lambda: defaultdict(float))
        self.shape = {}

    def send(self, cat, src, dst, nbytes):
        k = ("offline|" if cat in OFFLINE_CATS else "online|") + cat
        self.sent[k][src] += nbytes
        self.recv[k][dst] += nbytes

    def flights(self, cat, k=1):
        self.fl[("offline|" if cat in OFFLINE_CATS else "online|") + cat] += k


def ct_bytes(prm):
    return 2 * (prm.rlwe_n * prm.rlwe_logq + 7) // 8


class TSecure:
    def __init__(self, srv, seed):
        self.srv, self.prm = srv, srv.prm
        self.m = self.prm.m
        self.mt = TMeter(self.m + 1)
        self.rng = np.random.default_rng(seed + 17)
        self.gc = TGC(self.prm, srv)
        self.learned = defaultdict(list)

    # ---- ring sharing among the m clients ------------------------------------------------------------------
    def rint(self, shape, l):
        return self.rng.integers(0, 1 << l, size=shape, dtype=np.int64)

    def share(self, x, l):
        x = np.asarray(x, np.int64) & ((1 << l) - 1)
        S = self.rint((self.m,) + x.shape, l)
        S[0] = (x - S[1:].sum(0)) & ((1 << l) - 1)
        return S

    def open_all(self, cat, nelem, l):
        """every client broadcasts its share of nelem ring elements to every other client"""
        b = nelem * ((l + 7) // 8)
        for i in range(1, self.m + 1):
            for j in range(1, self.m + 1):
                if i != j:
                    self.mt.send(cat, i, j, b)
        self.mt.flights(cat, 1)

    # ---- ideal garbled circuit -----------------------------------------------------------------------------
    def meter_gc(self, name, n_open_out):
        mt, m = self.mt, self.m
        c = self.gc.cost(name, n_open_out)
        g = mt.gc[name]
        g["calls"] += 1
        g["and_core"] += c["core"]
        g["and_io"] += c["io"]
        g["in_bits"] += c["in_bits"]
        g["mask_bits"] += c["mask_bits"]
        g["garbler_bits"] += c["garbler_bits"]
        g["ands"] += c["ands"]
        mt.send("gc_tables", 0, 1, c["table_bytes"])
        mt.send("gc_labels", 0, 1, 16 * c["garbler_bits"])
        per_client = (c["in_bits"] + c["mask_bits"]) / m
        for j in range(1, m + 1):
            mt.send("gc_ot", j, 0, per_client / 8)
            mt.send("gc_ot", 0, j, per_client * 32)
            if j != 1:
                mt.send("gc_labels", j, 1, per_client * 16)
        mt.send("gc_out", 0, 1, n_open_out * 4)
        mt.flights("gc", 4)

    # ---- the protocol --------------------------------------------------------------------------------------
    def search(self, q):
        srv, prm, mt, m = self.srv, self.prm, self.mt, self.m
        d, C, lt = prm.d, prm.C, prm.lt
        mod = 1 << lt
        R, limbs = srv.mc, srv.limbs
        blocks = prm.blocks
        q = q.astype(np.int64)
        gc = self.gc
        zb = ct_bytes(prm)
        ell_r, ell_i = R, (limbs + 1) * R
        digits = 16
        keep = 0.5 if prm.drop_low else 1.0
        mt.shape = dict(C=C, d=d, m=m, mc=R, limbs=limbs, lt=lt, ell_rank=ell_r, ell_id=ell_i, lwe_n=prm.lwe_n,
                        rlwe_n=prm.rlwe_n, rlwe_logq=prm.rlwe_logq, ct_bytes=zb, drop_low=prm.drop_low,
                        tok_cts_rank=int(np.ceil(ell_r / prm.rlwe_n)) * digits, tok_cts_id=int(np.ceil(ell_i / prm.rlwe_n)) * digits,
                        dup=prm.dup, upload_dim=C * d, id_upload_dim=C)

        # -- 0. query tokens (per client, per query; independent of the query string -> offline) --------------------------
        # client i sends n RLWE ciphertexts z_j = Enc2(s_i[j] copies), shared by the ranking and the id service (App. A.3);
        # the server returns H s_i and H_id s_i under Enc2 (base-16 digits of the 64-bit entries, half the digits' work if the
        # low-order bits are dropped)
        for i in range(1, m + 1):
            mt.send("token_up", i, 0, prm.lwe_n * zb)
            mt.send("token_down", 0, i, int((mt.shape["tok_cts_rank"] + mt.shape["tok_cts_id"]) * zb * keep))
        mt.flights("token_up", 1)
        mt.flights("token_down", 1)

        # -- 1. clients: local partial distances to the PUBLIC centroids (additive shares of the true distances) -------------
        D_sh = np.zeros((m, C), np.int64)
        for i, idx in enumerate(blocks):
            D_sh[i] = ((srv.cent[:, idx] - q[idx][None]) ** 2).sum(1) & ((1 << gc.l1) - 1)

        # -- 2. GC argmin_cluster: shared distances -> shared one-hot selector e (never revealed) --------------------------
        D = D_sh.sum(0) & ((1 << gc.l1) - 1)
        cstar, Dtrue = tp.nearest_cluster(srv.cent, q)
        assert np.array_equal(D, Dtrue)
        e = np.zeros(C, np.int64)
        e[int(np.argmin(D))] = 1
        e_sh = self.share(e, lt)
        self.meter_gc("argmin_cluster", 0)

        # -- 3. q~ = e (x) q~'  by a Beaver outer product in Z_{2^lt}; q' = quantised query (client i quantises its block) ----
        qq = np.zeros(d, np.int64)
        for i, idx in enumerate(blocks):
            half = 2 ** (prm.bits - 1)
            qq[idx] = np.clip(np.rint((q[idx].astype(np.float32) - srv.mu[idx]) / srv.scale), -half, half - 1).astype(np.int64)
        assert np.array_equal(qq, srv.quant(q[None])[0])
        q_sh = np.zeros((m, d), np.int64)
        for i, idx in enumerate(blocks):
            q_sh[i, idx] = qq[idx] & (mod - 1)                  # block i is held by client i alone (others hold 0)
        a, b = self.rint(C, lt), self.rint(d, lt)               # offline: outer-product triple (a, b, c = a (x) b), shared
        a_sh, b_sh = self.share(a, lt), self.share(b, lt)
        c_sh = self.share((a[:, None] * b[None, :]) & (mod - 1), lt)
        delta = (e_sh - a_sh).sum(0) & (mod - 1)                # opened: C values
        eps = (q_sh - b_sh).sum(0) & (mod - 1)                  # opened: d values
        self.open_all("beaver_open", C + d, lt)
        mt.cnt["triples"] += C * d
        qt_sh = (delta[None, :, None] * b_sh[:, None, :] + a_sh[:, :, None] * eps[None, None, :] + c_sh) & (mod - 1)
        qt_sh[0] = (qt_sh[0] + delta[:, None] * eps[None, :]) & (mod - 1)      # public term added once
        # sanity (simulator only): shares reconstruct to e (x) q'
        assert np.array_equal(qt_sh.sum(0) & (mod - 1), (e[:, None] * (qq & (mod - 1))[None, :]) & (mod - 1))

        # -- 4. clients upload LWE ciphertext shares of q~ and e; server adds them and scans its matrices -------------------
        for i in range(1, m + 1):
            mt.send("query_upload", i, 0, (C * d + C) * 8)       # b_i (dC words) and b'_i (C words), 64-bit
        mt.flights("query_upload", 1)
        qt = qt_sh.sum(0) & (mod - 1)                           # ideal LWE: the ciphertext sum encrypts the sum of the shares
        ip = np.zeros(R, np.int64)
        for s0 in range(0, C, 64):
            ip += np.einsum("crj,cj->r", srv.X8[s0:s0 + 64].astype(np.int64), qt[s0:s0 + 64])
        ip &= (mod - 1)                                          # M . q~  mod 2^lt (server's scan, ideal-encrypted)
        ev = e_sh.sum(0) & (mod - 1)
        idl = np.zeros((limbs + 1, R), np.int64)                  # id limbs and the norm row, all linear in e
        for l in range(limbs):
            limb = (srv.ids >> (12 * l)) & 4095                   # (C, R)
            idl[l] = np.einsum("cr,c->r", limb, ev) & (mod - 1)  # M_id . e
        idl[limbs] = np.einsum("cr,c->r", srv.nu, ev) & (mod - 1)

        # -- 5. decrypt-on-shares inside GC rank_topk: inputs c (server) and -H s_i (clients) in Z_{2^64} ---------------------
        delta64 = np.uint64(1) << np.uint64(64 - lt)
        T = np.concatenate([ip[None], idl]).astype(np.uint64) * delta64        # Delta * (M q~, M_id e)   (uint64 wraps)
        cs = self.rng.integers(0, 1 << 63, size=T.shape, dtype=np.uint64) * np.uint64(2) + self.rng.integers(0, 2, size=T.shape, dtype=np.uint64)
        us = self.rng.integers(0, 1 << 63, size=(m,) + T.shape, dtype=np.uint64) * np.uint64(2)
        us[0] = T - cs - us[1:].sum(0, dtype=np.uint64)
        v = cs + us.sum(0, dtype=np.uint64)
        val = ((v + (delta64 >> np.uint64(1))) >> np.uint64(64 - lt)).astype(np.int64) & (mod - 1)
        ipr = np.where(val[0] >= mod // 2, val[0] - mod, val[0])
        ids = np.zeros(R, np.int64)
        for l in range(limbs):
            ids |= val[1 + l] << (12 * l)
        nu = val[1 + limbs]
        score = nu - 2 * ipr
        top = tp.topk_rows(score, prm.k)
        res_ids = ids[top]
        self.meter_gc("rank_topk", prm.k)
        for i in range(2, m + 1):
            mt.send("output", 1, i, prm.k * 4)
        mt.flights("output", 1)
        self.learned[1].append(("top-k ids", prm.k))
        mt.cnt["cluster_fill"] += int((srv.ids[cstar] > 0).sum())
        return [int(x) for x in res_ids if x != 0]


def run_query(srv, q, seed):
    sec = TSecure(srv, seed)
    t0 = time.perf_counter()
    res = sec.search(q)
    return res, sec.mt, time.perf_counter() - t0
