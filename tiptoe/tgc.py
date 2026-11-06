"""AND-gate accounting of the two garbled circuits of the Tiptoe baseline (free-XOR + half-gates, 32 B per AND, constants free;
same conventions as gc_model.py / panther/pgc.py except that the shared values live in a power-of-two ring Z_{2^l}, where a modular
addition is a plain l-AND ripple adder (the repo's F_p wrapper pays 3l per add for the reduction mod p).

Parties: server = garbler (holds no shares), client 1 = evaluator, clients 2..m supply inputs by OT. Values are additively shared
among the m clients only. Every shared output is masked by all m clients (all-client output mask, as in the main protocol);
an output opened to the evaluator needs no mask.

  argmin_cluster   in : C shared distances (Z_{2^ld}, m shares each).  tournament argmin with index (ties -> lowest index),
                   one-hot decode.  out: C shared 0/1 values in Z_{2^lt}  (the cluster selector e).
  rank_topk        in : R rows x (2 + limbs) elements (ip, id limbs, nu), each the sum mod 2^64 of m+1 summands (c from the server = garbler's own
                   input, u_i from client i by OT): this is the SimplePIR decryption  round((c - sum_i H s_i) / 2^(64-lt)),
                   done on shares because no single client may hold the plaintext score (paper: the client decrypts).
                   core: round + sign; score = nu - 2*ip (nu is the secret-cluster norm, retrieved like the id limbs; one ls-bit subtract); id limbs
                   concatenated (free); top-k selection network over the R rows (same Shanbhag et al. bitonic top-k as Panther's).
                   out: k ids opened to client 1."""
import math

import _path  # noqa: F401
from gc_model import bits


def oem_comparators(n):
    if n < 2:
        return 0
    c, p = 0, 1
    while p < n:
        k = p
        while k >= 1:
            for j in range(k % p, n - k, 2 * k):
                for i in range(min(k, n - j - k)):
                    if (i + j) // (2 * p) == (i + j + k) // (2 * p):
                        c += 1
            k //= 2
        p *= 2
    return c


def bitonic_merge_comparators(n):
    if n < 2:
        return 0
    m = 1 << (n.bit_length() - 1)
    if m == n:
        m //= 2
    return (n - m) + bitonic_merge_comparators(m) + bitonic_merge_comparators(n - m)


def topk_network_comparators(n, k):
    if n <= k:
        return oem_comparators(n)
    g, r = divmod(n, k)
    sizes = [k] * g + ([r] if r else [])
    c = sum(oem_comparators(s) for s in sizes)
    for s in sizes[1:]:
        c += min(s, k) + bitonic_merge_comparators(k)
    return c


class TGC:
    def __init__(self, prm, srv):
        self.prm, self.srv, self.m = prm, srv, prm.m
        self.lt = prm.lt
        self.l1 = bits(prm.DMAX) + 1                       # ring of the centroid distances
        self.lidx = bits(prm.C)
        self.ls = prm.lt + 1                               # score bits (nu - 2 ip), signed
        self.lid = bits(prm.N + 1)
        self.R = srv.mc
        self.limbs = srv.limbs
        self.E = 2 + srv.limbs                             # decrypted elements per row: ip, id limbs, nu

    def cas(self, idbits):
        return self.ls + (self.ls + idbits)                # compare + conditional swap of (score, id)

    def core(self, name):
        p = self.prm
        if name == "argmin_cluster":
            tour = (p.C - 1) * (self.l1 + self.l1 + self.lidx)
            return tour + p.C * self.lidx                  # + one-hot decode (index equality per cluster)
        if name == "rank_topk":
            dec = self.R * self.E * self.m * 64   # m 64-bit adds per element (garbler's c is the first summand)
            score = self.R * self.ls                        # nu - 2*ip
            return dec + score + topk_network_comparators(self.R, p.k) * self.cas(self.lid)
        raise KeyError(name)

    def io(self, name):
        """wrapper cost: reconstruction of ring-shared inputs and output masks (decryption adds are counted in core)."""
        p, m = self.prm, self.m
        if name == "argmin_cluster":
            return p.C * (m - 1) * self.l1 + p.C * m * self.lt
        return 0

    def cost(self, name, n_open_out):
        core, io = self.core(name), self.io(name)
        m = self.m
        if name == "argmin_cluster":
            in_cl = self.prm.C * self.l1                    # client input bits per client (its share of every distance)
            mask_cl = self.prm.C * self.lt                  # client mask bits per client (all-client output masks)
            garb = 0
        else:
            in_cl = self.R * self.E * 64                    # u_i per element
            mask_cl = 0
            garb = self.R * self.E * 64                     # c (64 bit) per element
        ands = core + io
        return dict(ands=ands, core=core, io=io, in_bits=m * in_cl, mask_bits=m * mask_cl, garbler_bits=garb,
                    table_bytes=32 * ands, out_open=n_open_out)
