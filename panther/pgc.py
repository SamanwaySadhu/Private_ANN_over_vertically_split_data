"""AND-gate accounting of the garbled circuits of the Panther baseline (same conventions as gc_model.py / hnsecw/hgc.py:
free-XOR + half-gates, 32 B per AND, constants free, every input element reconstructed from its n additive shares, every
shared output masked by all parties; an output opened to the evaluator needs no mask).

Parties: n = m+1 (server garbles, client 1 evaluates, the other clients supply inputs by OT).

  approx_topk  inputs: t shared centroid distances (positions are constants). k' bins -> minimum per bin (compare + mux),
               then top-u selection network over the k' minima (Sec. 6.1 of the paper; here evaluated entirely in GC because
               the paper's SS-based bin minimum is a 2-party OT protocol and has no n-party counterpart in this repo).
               Out: u positions opened to client 1.
  exact_topk   inputs: B*mc shared distances + B*mc shared ids. Top-k selection network (Sec. 6.2). Out: k ids opened to client 1.

The selection network is Shanbhag et al.'s bitonic top-k as in the paper: ceil(n/k) groups sorted with Batcher's odd-even merge
sort, then ceil(n/k)-1 'top-k merges' (k compare-swaps keep the k smallest of two sorted k-lists, a bitonic merge sorts the kept
half). Comparator counts are exact for arbitrary n, k (no power-of-two padding)."""
import math

import _path  # noqa: F401
from gc_model import bits

L_BITS = 31


def oem_comparators(n):
    """Batcher odd-even merge sort on n wires (comparators touching missing wires removed)."""
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
    """Compare-swaps of the top-k selection network on n inputs (n >= k)."""
    if n <= k:
        return oem_comparators(n)
    g, r = divmod(n, k)
    sizes = [k] * g + ([r] if r else [])
    c = sum(oem_comparators(s) for s in sizes)
    for s in sizes[1:]:
        c += min(s, k) + bitonic_merge_comparators(k)
    return c


class PGC:
    def __init__(self, prm, srv):
        self.prm, self.srv, self.n, self.m = prm, srv, prm.n, prm.m
        self.l = L_BITS
        self.ld = bits(prm.d * 255 * 255 + 1) + 1          # distance bits
        self.lid = bits(prm.N + 1)
        self.lpos = bits(prm.t)

    def io(self, in_el, out_shared):
        l, n = self.l, self.n
        return in_el * (3 * l * (n - 1) + 2 * l) + out_shared * (3 * l * n + l)

    def cas(self, idbits):
        return self.ld + (self.ld + idbits)                 # compare + swap (one AND per swapped bit)

    def core(self, name):
        p = self.prm
        if name == "approx_topk":
            b = math.ceil(p.t / p.kprime)
            mins = (p.t - p.kprime) * self.cas(self.lpos)    # every non-winning element costs one compare-min
            net = topk_network_comparators(p.kprime, p.u) * self.cas(self.lpos)
            return mins + net
        if name == "exact_topk":
            n_in = p.B * self.srv.mc
            return topk_network_comparators(n_in, p.k) * self.cas(self.lid)
        raise KeyError(name)

    def cost(self, core, in_el, out_shared, out_open):
        io = self.io(in_el, out_shared)
        ands = core + io
        m, l = self.m, self.l
        return dict(ands=ands, core=core, io=io, in_bits=m * in_el * l, mask_bits=m * out_shared * l,
                    table_bytes=32 * ands, out_shared=out_shared, out_open=out_open, in_el=in_el)
