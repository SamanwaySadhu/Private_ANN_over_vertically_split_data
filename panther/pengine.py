"""Instrumented secure execution of the Panther baseline for a vertically split query: n = m+1 parties (party 0 = server,
parties 1..m = clients, client 1 = PIR querier / partial-decryption fuser / GC evaluator).

What differs from the 2-party paper (every difference is forced by 'no client may learn the query or any intermediate'):
  * the single client C is replaced by m clients. Client i owns coordinate block i of the query. Joint public keys, secret keys
    threshold-shared among the clients: the server never decrypts, a single client alone cannot decrypt.
  * every value the paper shares between C and S is additively shared among all n parties (GC wrapper reconstructs n shares),
    except where a protocol step is inherently 2-party between S and ONE client, which is then block-aligned:
      - retrieved points: for coordinate j of block i the shares are held by S and client i only (client 1 gets the masked PIR
        output, keeps its block, forwards block i to client i). Then <q, v> = sum_i <q_i, v_S[i]> (HE, server share)
        + sum_i <q_i, v_C[i]> (local at client i), exactly Sec. 7.3.2 of the paper, with no client-to-client multiplication.
      - norms and ids are re-shared by client 1 among all clients.
  * the shuffled cluster positions chosen by ApproxTopK are opened to client 1 only (uniform distinct values for everybody who
    does not know the server's permutation; they are simulatable). The final top-k ids are opened to client 1 and forwarded to
    the other clients. The server learns nothing.
Garbled circuits and HE are ideal functionalities evaluated on reconstructed values inside one call (outputs re-shared with
fresh masks) but metered exactly; the share arithmetic outside them is executed on real additive shares over F_p."""
import time
from collections import defaultdict

import numpy as np

import _path  # noqa: F401
from vsann import MPC, P
from pgc import PGC
from phe import DIST, PIR1, PIR2, ct_bytes, poly_bytes, pir_shape
import pproto as pp

BPE = 4


class PMeter:
    def __init__(self, n):
        self.n = n
        self.phase = "online"
        self.sent = defaultdict(lambda: np.zeros(n))
        self.recv = defaultdict(lambda: np.zeros(n))
        self.fl = defaultdict(int)
        self.cnt = defaultdict(float)
        self.gc = defaultdict(lambda: defaultdict(float))
        self.shape = {}

    def key(self, cat):
        return f"{self.phase}|{cat}"

    def send(self, cat, src, dst, nbytes):
        self.sent[self.key(cat)][src] += nbytes
        self.recv[self.key(cat)][dst] += nbytes

    def flights(self, cat, k=1):
        self.fl[self.key(cat)] += k


class PSecure:
    def __init__(self, srv, seed):
        self.srv, self.prm = srv, srv.prm
        self.n, self.m = self.prm.n, self.prm.m
        self.mt = PMeter(self.n)
        self.c = MPC(self.n, seed=seed + 17)
        self.gc = PGC(self.prm, srv)
        self.seed = seed
        self.pir = pir_shape(srv)
        self.learned = defaultdict(list)          # what each party sees in the clear (audit)

    # ---- sharing helpers ---------------------------------------------------------------------------------------
    def share_sp(self, x):
        """Additive share between the server (party 0) and client 1 only (output of an HE evaluation + threshold decryption)."""
        x = np.mod(np.asarray(x, np.int64), P)
        r = self.c.rint(x.shape)
        S = np.zeros((self.n,) + x.shape, np.int64)
        S[0] = np.mod(-r, P)
        S[1] = np.mod(x + r, P)
        return S

    def split_clients(self, masked, server_share):
        """client 1 re-shares a value it holds among all clients; the server keeps its own share."""
        out = np.zeros((self.n,) + masked.shape, np.int64)
        out[1:self.m] = self.c.rint((self.m - 1,) + masked.shape)       # m random shares summing to `masked`
        out[self.m] = np.mod(masked - out[1:self.m].sum(0), P)
        out[0] = server_share
        return out

    # ---- ideal garbled circuit (n-party wrapper), evaluator = client 1 ------------------------------------------
    def run_gc(self, name, in_shared, fn, n_shared_out=0, n_open_out=0):
        mt, n = self.mt, self.n
        vals = [np.mod(self.c.reveal(I), P) for I in in_shared]
        opens, shareds = fn(*vals)
        in_el = sum(int(np.prod(I.shape[1:], dtype=np.int64)) for I in in_shared)
        c = self.gc.cost(self.gc.core(name), in_el, n_shared_out, n_open_out)
        g = mt.gc[name]
        g["calls"] += 1
        g["and_core"] += c["core"]
        g["and_io"] += c["io"]
        g["in_bits"] += c["in_bits"]
        g["mask_bits"] += c["mask_bits"]
        g["ands"] += c["ands"]
        l = self.gc.l
        mt.send("gc_tables", 0, 1, c["table_bytes"])
        mt.send("gc_labels", 0, 1, 16 * l * in_el)                       # garbler's own input labels
        bits_cl = (in_el + n_shared_out) * l
        for j in range(1, n):
            mt.send("gc_ot", j, 0, bits_cl / 8)
            mt.send("gc_ot", 0, j, bits_cl * 32)
            if j != 1:
                mt.send("gc_labels", j, 1, bits_cl * 16)
        mt.send("gc_out", 0, 1, n_open_out * BPE)                        # output decoding info for the opened outputs
        mt.flights("gc", 4)
        return list(opens), [self.c.share(np.mod(np.asarray(y, np.int64), P)) for y in shareds]

    # ---- the protocol ------------------------------------------------------------------------------------------
    def search(self, q):
        srv, prm, c, mt, n, m = self.srv, self.prm, self.c, self.mt, self.n, self.m
        d, t, B, mc, W = prm.d, prm.t, prm.B, srv.mc, srv.W
        blocks = prm.blocks
        rng = np.random.default_rng(self.seed)                  # same per-query randomness as pproto.plain_search
        q = q.astype(np.int64)
        shp = dict(self.pir, d=d, t=t, mc=mc, W=W, m=m, dist_cts_t=-(-t // DIST["N"]),
                   dist_cts_pts=-(-(B * mc) // DIST["N"]))
        mt.shape = shp
        ctd = ct_bytes(DIST)
        # 0. server shuffles the cluster index map (free: every cluster has its own plaintext polynomials)
        perm = pp.shuffle(srv, rng)
        # 1. query: client i encrypts its d_i coordinates (constant polynomials) under the joint DIST key, shares ||q_i||^2
        qn = np.zeros((n,), np.int64)
        for i, idx in enumerate(blocks):
            qi = q[idx]
            qn = np.mod(qn + c.share(int((qi ** 2).sum())), P)
            mt.send("query_ct", i + 1, 0, len(idx) * ctd)
            for j in range(n):
                if j != i + 1:
                    mt.send("share_norm", i + 1, j, BPE)
        mt.flights("query_ct", 1)
        mt.flights("share_norm", 1)

        # 2. centroid distances. HE: server: sum_i Enc(q_i) * pt(centroid block i); H2A mask; threshold-decrypt to client 1
        def he_dist_cts(n_out, cat):
            for i in range(m):                                  # server -> every client: the 'a' polys (b+r stays at the server)
                mt.send(cat, 0, i + 1, n_out * poly_bytes(DIST["N"], DIST["logq"]))
            for i in range(1, m):                               # partial decryptions to client 1
                mt.send(cat, i + 1, 1, n_out * poly_bytes(DIST["N"], DIST["logq"]))
            mt.flights(cat, 2)
        z = np.zeros(t, np.int64)
        for i, idx in enumerate(blocks):
            z += srv.C[perm][:, idx] @ q[idx]
        zsh = self.share_sp(z)
        he_dist_cts(shp["dist_cts_t"], "he_centroid")
        Dc = np.mod(qn[:, None] - 2 * zsh, P)
        Dc[0] = np.mod(Dc[0] + srv.Cn[perm], P)                  # the server adds ||c_j||^2 to its own share

        # 3. approximate top-u over the t centroid distances (GC), positions opened to client 1 only
        def f_approx(D):
            sel = pp.bin_min_topk(D, prm)
            return [sel], []
        (sel,), _ = self.run_gc("approx_topk", [Dc], f_approx, 0, prm.u)
        self.learned[1].append(("shuffled positions of the u closest clusters", len(sel)))

        # 4. client 1 plans the batch-PIR queries (cuckoo), sends B encrypted selectors (one per PIR dimension) to the server
        pos, failed = pp.cuckoo_plan(srv, sel, rng)
        assert len(set(pos.tolist())) == B
        mt.cnt["cuckoo_failed"] += failed
        mt.send("pir_query", 1, 0, B * (ct_bytes(PIR1) + ct_bytes(PIR2)))
        mt.flights("pir_query", 1)

        # 5. PIR to secret shares (PI_PIR2A): the PIR output (data + server mask) is threshold-decrypted to client 1 (two layers)
        ids = srv.cluster[perm[pos]]                              # (B, mc), ids of the retrieved clusters (0 = padding)
        V = srv.X[ids]
        nrm = srv.nrm[ids]
        rS, rN, rI = c.rint(V.shape), c.rint(nrm.shape), c.rint(ids.shape)
        shV = np.zeros((n,) + V.shape, np.int64)                  # block-aligned: coordinate j of block i -> server + client i
        shV[0] = np.mod(-rS, P)
        mV = np.mod(V + rS, P)
        for i, idx in enumerate(blocks):
            shV[i + 1][..., idx] = mV[..., idx]
        shN = self.split_clients(np.mod(nrm + rN, P), np.mod(-rN, P))
        shI = self.split_clients(np.mod(ids + rI, P), np.mod(-rI, P))
        pairs = B * shp["P"]
        p2, p1 = poly_bytes(PIR2["N"], PIR2["q_sw"]), poly_bytes(PIR1["N"], PIR1["q1"])
        for i in range(m):
            mt.send("pir_resp", 0, i + 1, pairs * 2 * p2)         # w0'.a and w1.a to everybody (for the partial decryptions)
        mt.send("pir_resp", 0, 1, pairs * (p2 + 16))              # w1.b and the PRG seed of the mask r to client 1
        for i in range(1, m):
            mt.send("pir_dec2", i + 1, 1, pairs * 2 * p2)         # layer-2 partial decryptions
            mt.send("pir_dec1", 1, i + 1, pairs * p1)             # client 1 forwards the recovered first-layer 'a'
            mt.send("pir_dec1", i + 1, 1, pairs * p1)             # layer-1 partial decryptions
        mt.flights("pir_resp", 1)
        mt.flights("pir_dec2", 1)
        mt.flights("pir_dec1", 2)
        for i, idx in enumerate(blocks):                          # client 1 distributes the block shares / re-shares norm and id
            if i != 0:
                mt.send("pir_distribute", 1, i + 1, B * mc * (len(idx) + 2) * BPE)
        mt.flights("pir_distribute", 1)

        # 6. distances to the B*mc retrieved points. server share: HE (<Enc(q_i), v_S[block i]>); client share: local;
        #    wrap-bit correction (Z_{2^l1} shares embedded in Z_{2^l2}): one OT per (point, coordinate), block owner -> server
        dotC = np.zeros((n, B, mc), np.int64)
        dotS = np.zeros((B, mc), np.int64)
        for i, idx in enumerate(blocks):
            dotC[i + 1] = np.mod(shV[i + 1][..., idx] @ q[idx], P)
            dotS += np.mod(shV[0][..., idx] @ q[idx], P)
            dotS %= P
            mt.send("wrap_ot", i + 1, 0, B * mc * len(idx) * 3)   # l2-bit correlation correction per OT (3 B)
            mt.send("wrap_ot", 0, i + 1, B * mc * len(idx) / 8)   # choice bit derandomisation
            mt.cnt["wrap_ots"] += B * mc * len(idx)
        mt.flights("wrap_ot", 1)
        dsh = np.mod(dotC + self.share_sp(dotS), P)
        he_dist_cts(shp["dist_cts_pts"], "he_points")
        Dp = np.mod(qn[:, None, None] + shN - 2 * dsh, P).reshape(n, B * mc)

        # 7. exact top-k over the B*mc candidates (GC); ids opened to client 1, then forwarded to the other clients
        def f_exact(D, I):
            return [pp.exact_topk(D, I, prm.k)], []
        (top,), _ = self.run_gc("exact_topk", [Dp, shI.reshape(n, B * mc)], f_exact, 0, prm.k)
        for i in range(2, m + 1):
            mt.send("output", 1, i, prm.k * BPE)
        mt.flights("output", 1)
        self.learned[1].append(("top-k ids", prm.k))
        return [int(x) for x in top if x != 0]


def run_query(srv, q, seed):
    sec = PSecure(srv, seed)
    t0 = time.perf_counter()
    res = sec.search(q)
    return res, sec.mt, time.perf_counter() - t0
