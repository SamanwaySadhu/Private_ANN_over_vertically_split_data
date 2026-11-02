"""Plain (cleartext) reference of the baseline's bounded algorithm; the secure engine runs the same
transition functions inside its garbled circuits."""
import numpy as np

import _path  # noqa: F401
from vsann import INF, beam_init, beam_step


def upper_step(act, dv, v, l, down, dj, nrow, nnode):
    """One exact greedy step. dj/nrow/nnode: distances, row ids (0 = padding), node ids of the M
    neighbours. Returns (v, dv, i, l, act). Ties -> lowest neighbour slot."""
    dd = np.where(np.asarray(nrow) != 0, dj, INF)
    j = int(np.argmin(dd))
    best = int(dd[j])
    act, dv, v, l, down = int(act), int(dv), int(v), int(l), int(down)
    if act == 1:
        if best < dv:
            nv, nd, ni, nl = int(nnode[j]), best, int(nrow[j]), l
        else:
            nv, nd, ni, nl = v, dv, down, l - 1
    else:
        nv, nd, ni, nl = v, dv, 0, l
    return nv, nd, ni, nl, int(act == 1 and nl > 0)


def plain_baseline(srv, q):
    prm = srv.prm
    M, d = prm.M, prm.d
    X = srv.X
    q = q.astype(np.int64)
    i, v, l, xv, _ = srv.entry_state()
    dv = int(((q - xv) ** 2).sum())
    act = int(l > 0)
    moved = 0
    for _ in range(prm.Tg):
        nrow, down = srv.Aup_adj[:M, i], srv.Aup_adj[M, i]
        nnode = srv.Aup_vec[d + 1, nrow]
        dj = ((srv.Aup_vec[:d, nrow].T - q) ** 2).sum(1)
        pv = v
        v, dv, i, l, act = upper_step(act, dv, v, l, down, dj, nrow, nnode)
        moved += int(v != pv)
    info = dict(upper_unfinished=int(act), entry=int(v), moves=moved)
    W, V = beam_init(v, dv, prm)
    usel, live = v, 1
    for t in range(prm.Tb):
        ids = srv.Aadj[:prm.D0, usel]
        nu = srv.Aadj[prm.D0:, usel]
        cd = ((X[ids] - q) ** 2).sum(1)
        W, V, usel, live = beam_step(W, V, usel, live, ids, cd, nu, t, prm)
    valid = W[3] == 1
    out = [int(x) for x in np.where(valid, W[0], 0)[:prm.k] if x != 0]
    info["beam_live_end"] = int(live)
    return out, info
