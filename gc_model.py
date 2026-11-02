"""AND-gate accounting for the MYao circuits used by the protocol (vsann.SecureANN).

Garbled-circuit size is determined by the number of AND gates (free-XOR + half-gates: 2 x 128-bit
ciphertexts = 32 bytes per AND, XOR/NOT free). Each circuit of the protocol is a fixed function of
public parameters, so its AND count is computed from standard building-block costs:
    add/sub/compare/equality/mux of an l-bit word : l          (ripple-carry / tree)
    modular add/sub over F_p                      : 3 l        (add, compare with p, mux)
    restoring division  ln-bit / ld-bit           : 2 ln ld
    AES-128 evaluation (hash phi)                 : aes_ands   (calibrated from the Bristol circuit)
The wrapper of Sec. 3.3 is included: every circuit reconstructs each input element from its m
additive shares and emits  y - sum_i eta_i  where every client supplies a fresh mask eta_i."""
import math
from dataclasses import dataclass

from vsann import P

KAPPA_BYTES = 16


def bits(x):
    return max(1, int(math.ceil(math.log2(max(2, x)))))


@dataclass
class GCModel:
    prm: object
    U: int
    wmax: int                    # max LSH bandwidth integer in theta (denominator width)
    aes_ands: int = 6400

    def __post_init__(self):
        p = self.prm
        self.l = 31
        self.lid = bits(p.N + 1)
        self.lrow = bits(self.U)
        self.ld = bits(p.d * 255 * 255) + 1
        self.m = p.m

    # ---- wrapper -------------------------------------------------------------------------
    def io_ands(self, in_elems, out_elems):
        l, m = self.l, self.m
        per_in = 3 * l * (m - 1) + 2 * l           # sum of m shares mod p, to signed
        per_out = 3 * l * m + l                    # y - sum_i eta_i mod p
        return in_elems * per_in + out_elems * per_out

    # ---- circuit cores --------------------------------------------------------------------
    def core_ands(self, name):
        p, l, lid, lrow, ld, m = self.prm, self.l, self.lid, self.lrow, self.ld, self.m
        s, E, D0, LV = p.s, p.E, p.D0, p.LV
        if name == "mux_row":
            return l
        if name == "div_floor":
            ln = bits(p.Sw * (p.d // m + 1) * 255 * 4 * p.Sa * p.Bq) + 2
            den = bits(p.Sa * p.Sq * self.wmax) + 1
            return s * m * 2 * ln * den
        if name == "hash_probe":
            return 4 * s * self.aes_ands + s * m * l
        if name == "match_priority":
            eq = s * (4 + 2 * p.sigma) * l
            sel = s * p.Pn * (2 * lid + 3)
            return eq + sel
        if name == "match_direct":                  # first-nonempty-radius priority over s x 2 directly addressed probes
            return s * 2 * (2 * lid + 3)
        if name == "transition":
            return ld + 2 * lid + ld + lrow + 40
        if name == "beam_init":
            return 0
        if name == "beam_update":
            kb = 1 + ld + lid
            seen = D0 * LV * (lid + 1)
            dup = D0 * (D0 - 1) // 2 * (lid + 2)
            wp = E * lid
            n = E + D0
            n2 = 1 << bits(n)
            pw = bits(n2)
            ce = ((pw * pw - pw + 4) * (1 << (pw - 2)) - 1)       # odd-even merge sort comparators
            sort = ce * (kb + kb + 2)
            fix = n * ld + E * (lid + ld + 2)
            elig = E * (ld + lid + ld)
            return seen + dup + wp + sort + fix + elig
        if name == "final":
            return p.k * l
        raise KeyError(name)

    # ---- full cost of one call ---------------------------------------------------------------
    def cost(self, name, in_elems, out_elems, open_output=False):
        core = self.core_ands(name)
        io = self.io_ands(in_elems, 0 if open_output else out_elems)
        ands = core + io
        m, l = self.m, self.l
        in_bits = m * in_elems * l
        mask_bits = 0 if open_output else m * out_elems * l
        return dict(ands=ands, core=core, io=io, in_bits=in_bits, mask_bits=mask_bits,
                    table_bytes=32 * ands, out_elems=out_elems if not open_output else 0)
