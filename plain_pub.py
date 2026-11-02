"""Plain emulation of the PUBLIC-LSH protocol (same arithmetic as the secure engine) + error statistics."""
import numpy as np

from vsann import upper_transition, beam_step, beam_init, lsh_key


def client_quantize(prm, pub, q):
    """Each client i computes q_{r,i} = floor(B * t_{r,i}) from its OWN block; Q_r = sum_i q_{r,i}."""
    s, m = prm.s, prm.m
    qi = np.zeros((m, s), np.int64)
    for r in range(s):
        for i, blk in enumerate(prm.blocks):
            num = prm.Sw * (int(pub["a"][r][blk] @ q[blk]) + (int(pub["b"][r]) * prm.Sq if i == 0 else 0))
            qi[i, r] = (pub["B"] * num) // (prm.Sa * prm.Sq * int(pub["w"][r]))
    return qi


def lookup(srv, row, hh, ret_all=False):
    """first-nonempty-radius priority over probes (r, eps) with eps in {0,1}; hh[r] = key of probe eps=0."""
    prm, pub = srv.prm, srv.pub
    found, c, crow, rad = 0, 0, 0, -1
    for r in range(prm.s):
        K, off = pub["K"][r], pub["off"][r]
        for eps in (0, 1):
            col = int(hh[r]) + eps - pub["kmin"][r]
            if 0 <= col < K and srv.theta[off + col, row] == 1:
                if not found:
                    c, crow, rad = int(srv.theta[off + K + col, row]), int(srv.theta[off + 2 * K + col, row]), r
                found = 1
    return found, c, crow, rad


def plain_protocol_pub(srv, q):
    prm, pub = srv.prm, srv.pub
    s, d = prm.s, prm.d
    X = srv.X
    q = q.astype(np.int64)
    qi = client_quantize(prm, pub, q)
    Q = qi.sum(0)
    hh = Q // pub["B"]                                              # quantised key  h_hat
    h_true = np.array([int(lsh_key(prm, pub["a"][r], int(pub["b"][r]), int(pub["w"][r]), q)) for r in range(s)])
    stats = dict(hash_total=s, hash_err=int((hh != h_true).sum()),
                 hash_bound_viol=int((~((h_true - hh >= 0) & (h_true - hh <= 1))).sum()),
                 oor=int(sum(not (0 <= hh[r] - pub["kmin"][r] < pub["K"][r] - 1) for r in range(s))))
    i, v, l, xv = srv.entry_state()[0], srv.ep, srv.top, X[srv.ep]
    dv = int(((q - xv) ** 2).sum())
    act = int(l > 0)
    st = dict(steps=0, differs=0, improve=0, missed=0, accepted=0, empty=0, local_min=0)
    for it in range(prm.Tg):
        ireq = i if act else 0
        found, c, crow, rad = lookup(srv, ireq, hh)
        fi, ci, _, _ = lookup(srv, ireq, h_true)                 # ideal: exact bucket only, probe eps=0 (and 1 harmlessly)
        dc = int(((q - X[c]) ** 2).sum())
        down = int(srv.theta[2, ireq])
        improve = False
        if act:
            nbl = srv.nb[l][v]
            improve = bool(len(nbl) and ((X[nbl] - q) ** 2).sum(1).min() < dv)
        nv, nd, ni, nl, na, gam = upper_transition(act, found, c, dc, dv, crow, v, l, down)
        if act:
            st["steps"] += 1
            st["differs"] += int(ci != c)
            st["empty"] += int(found == 0)
            st["accepted"] += gam
            if improve:
                st["improve"] += 1
                st["missed"] += int(not gam)
            else:
                st["local_min"] += 1
        v, dv, i, l, act = nv, nd, ni, nl, na
    W, V = beam_init(v, dv, prm)
    usel, live = v, 1
    for t in range(prm.Tb):
        ids = srv.Aadj[:prm.D0, usel]
        nu = srv.Aadj[prm.D0:, usel]
        cd = ((X[ids] - q) ** 2).sum(1)
        W, V, usel, live = beam_step(W, V, usel, live, ids, cd, nu, t, prm)
    valid = W[3] == 1
    out = [int(x) for x in np.where(valid, W[0], 0)[:prm.k] if x != 0]
    stats.update(st)
    stats["upper_unfinished"] = int(act)
    stats["beam_live_end"] = int(live)
    return out, stats
