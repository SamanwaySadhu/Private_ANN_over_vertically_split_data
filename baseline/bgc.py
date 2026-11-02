"""AND-gate accounting for the baseline's garbled circuits. Extends gc_model.GCModel (beam_update,
beam_init, final are reused unchanged) with

  upper_step     exact greedy step of the upper layers: validity mux, argmin tournament over the M
                 neighbour distances, compare with the current distance, move-or-descend mux
  onehot:<n>     exact ID -> additively shared one-hot over a domain of n elements:
                 n equality tests of the (reconstructed) ID against the constants 0..n-1 (bits(n)-1
                 ANDs each, constants are free), each result bit is output as an F_p additive share
                 through the all-client output-mask wrapper of Sec. 3.3 (3 l m + l ANDs per element,
                 gc_model.io_ands)."""
import _path  # noqa: F401
from gc_model import GCModel, bits


class BaselineGC(GCModel):
    def __post_init__(self):
        super().__post_init__()
        self.lu = bits(self.U)

    def _pack(self, core, in_elems, out_elems, open_output):
        io = self.io_ands(in_elems, 0 if open_output else out_elems)
        ands = core + io
        m, l = self.m, self.l
        return dict(ands=ands, core=core, io=io, in_bits=m * in_elems * l,
                    mask_bits=0 if open_output else m * out_elems * l, table_bytes=32 * ands,
                    out_elems=out_elems if not open_output else 0)

    def core_ands(self, name):
        if name == "upper_step":
            M, l, lid, lu, ld = self.prm.M, self.l, self.lid, self.lu, self.ld
            pay = ld + lu + lid                                   # (distance, row id, node id)
            mux_valid = M * ld
            tour = (M - 1) * (ld + pay)                           # compare + select of the winner
            fin = ld + pay + l                                    # beat current? move/descend mux (+ level - 1)
            return mux_valid + tour + fin + 40
        return super().core_ands(name)

    def cost(self, name, in_elems, out_elems, open_output=False):
        if name.startswith("onehot:"):
            n = int(name.split(":")[1])
            return self._pack(in_elems * n * (bits(n) - 1), in_elems, out_elems, open_output)
        return super().cost(name, in_elems, out_elems, open_output)
