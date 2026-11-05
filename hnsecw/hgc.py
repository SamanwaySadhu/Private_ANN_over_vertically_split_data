"""AND-gate accounting for the garbled circuits of the HNSecW-style baseline (same conventions as gc_model.py:
free-XOR + half-gates, 32 B per AND, constants free, every input element reconstructed from its n additive shares).

Parties: n = m+1 (server + m clients). Server garbles, client 1 evaluates, clients supply inputs by OT, the server's own
share and its output mask are garbler inputs (no OT).

  visit   per iteration: deg neighbour rows + deg fresh dummy rows in (shared); the already-visited rows V are PUBLIC
          (every accessed row address was opened), so each equality is a test against a constant (lu-1 ANDs).
          Out: deg replaced rows u' (opened to all, they are the physical addresses to read), deg visited bits (shared).
  update  per iteration: C remainder, W, and the deg new entries in (shared); mask select, stable sort of C (T-1+deg) and
          of W (ef+deg) by (distance, position), keep T / ef. Out: new C, W (shared).
"""
import math

import _path  # noqa: F401
from gc_model import bits

L_BITS = 31


def comparators(n):
    n2 = 1 << bits(n)
    pw = bits(n2)
    if pw < 2:
        return 1
    return (pw * pw - pw + 4) * (1 << (pw - 2)) - 1      # Batcher odd-even merge sort on n2 inputs


class HGC:
    def __init__(self, prm, srv):
        self.prm, self.srv, self.n, self.m = prm, srv, prm.n, prm.m
        self.l = L_BITS
        self.ld = bits(prm.d * 255 * 255) + 1

    def lu(self, l):
        return bits(self.srv.L[l].Rv + 1)

    def lg(self, l):
        return bits(self.srv.L[l].Rg + 1)

    def io(self, in_el, out_shared):
        l, n = self.l, self.n
        return in_el * (3 * l * (n - 1) + 2 * l) + out_shared * (3 * l * n + l)

    def core(self, name, l):
        L = self.srv.L[l]
        deg, T, ef, ld = L.deg, L.T, L.ef, self.ld
        if name == "visit":
            raise KeyError("use visit_core(l, t)")
        if name == "update":
            tb = bits(T + deg)
            lg = self.lg(l)
            lb = bits(L.Rv + self.prm.N + 1)
            mask = deg * ld + 2 * deg                              # (visited or dummy) -> d_max
            cC = comparators(T - 1 + deg) * ((ld + tb) + (ld + tb + lg))
            cW = comparators(ef + deg) * ((ld + tb) + (ld + tb + lb))
            return mask + cC + cW
        raise KeyError(name)

    def visit_core(self, l, t):
        L = self.srv.L[l]
        deg, lu = L.deg, self.lu(l)
        Vlen = t * deg + 1
        eq = deg * Vlen * (lu - 1) + deg * (deg - 1) // 2 * (lu - 1)
        orr = deg * (Vlen + deg)
        sel = deg * lu
        return eq + orr + sel

    def cost(self, core, in_el, out_shared, out_open):
        io = self.io(in_el, out_shared)
        ands = core + io
        m, l = self.m, self.l
        return dict(ands=ands, core=core, io=io, in_bits=m * in_el * l, mask_bits=m * out_shared * l,
                    table_bytes=32 * ands, out_shared=out_shared, out_open=out_open, in_el=in_el)
