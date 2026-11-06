"""Plain emulation of the PER-NODE PUBLIC-LSH protocol (same arithmetic as the secure engine) + error statistics."""
import numpy as np

from vsann import upper_transition, beam_step, beam_init, lsh_key


def client_quantize_rows(prm, srv, rows, q):
    """(m, len(rows), s): client i's local q_i[row, r] = floor(B * t_i) from its OWN block (+ public offset -B*kmin at client 0)."""
    nd, B = srv.node, srv.pub["B"]
    rows = np.atleast_1d(rows)
    out = np.zeros((prm.m, len(rows), prm.s), np.int64)
    for i, blk in enumerate(prm.blocks):
        lo, hi = blk[0], blk[-1] + 1
        dot = nd["a"][rows][:, :, lo:hi].astype(np.int64) @ q[lo:hi]
        if i == 0:
            dot = dot + nd["b"][rows] * prm.Sq
        num = prm.Sw * dot
        out[i] = (B * num) // (prm.Sa * prm.Sq * nd["w"][rows])
        if i == 0:
            out[i] -= B * nd["kmin"][rows]
    return out


def lookup(srv, row, col):
    """first-nonempty-radius priority over probes (r, eps), eps in {0,1}; col[r] = column of probe eps=0. Out-of-window probes miss."""
    prm, pub = srv.prm, srv.pub
    found, c, crow = 0, 0, 0
    for r in range(prm.s):
        K, off = pub["K"][r], pub["off"][r]
        for eps in (0, 1):
            cc = int(col[r]) + eps
            if 0 <= cc < K and srv.theta[off + cc, row] == 1:
                if not found:
                    c, crow = int(srv.theta[off + K + cc, row]), int(srv.theta[off + 2 * K + cc, row])
                found = 1
    return found, c, crow


def plain_protocol_node(srv, q):
    prm, pub, nd = srv.prm, srv.pub, srv.node
    s, d, B = prm.s, prm.d, pub["B"]
    X = srv.X
    q = q.astype(np.int64)
    i, v, l, xv = srv.entry_state()[0], srv.ep, srv.top, X[srv.ep]
    dv = int(((q - xv) ** 2).sum())
    act = int(l > 0)
    st = dict(hash_total=0, hash_err=0, hash_bound_viol=0, oor=0, steps=0, differs=0, improve=0, missed=0, accepted=0, empty=0, local_min=0)
    for it in range(prm.Tg):
        ireq = i if act else 0
        qi = client_quantize_rows(prm, srv, ireq, q)[:, 0, :]           # (m, s): only the visited row is needed for the emulation
        Qp = qi.sum(0)                                                  # Q' = Q + B*J0 (J0 = -kmin)
        inr = (Qp >= 0) & (Qp < pub["K"][0] * B * 0 + np.array(pub["K"]) * B)
        col = np.where(inr, Qp // B, -(10 ** 6))                        # out of the interpolation domain -> miss (real protocol: undefined)
        found, c, crow = lookup(srv, ireq, col)
        if act:
            h_true = np.array([int(lsh_key(prm, nd["a"][ireq, r].astype(np.int64), int(nd["b"][ireq, r]), int(nd["w"][ireq, r]), q)) - int(nd["kmin"][ireq, r])
                               for r in range(s)])
            st["hash_total"] += s
            st["hash_err"] += int((col != h_true).sum())
            st["hash_bound_viol"] += int((~((h_true - col >= 0) & (h_true - col <= 1) | ~inr)).sum())
            st["oor"] += int((~inr).sum())
            fi, ci, _ = lookup(srv, ireq, h_true)
            st["differs"] += int(ci != c)
        dc = int(((q - X[c]) ** 2).sum())
        down = int(srv.theta[2, ireq])
        improve = False
        if act:
            nbl = srv.nb[l][v]
            improve = bool(len(nbl) and ((X[nbl] - q) ** 2).sum(1).min() < dv)
        nv, nd_, ni, nl, na, gam = upper_transition(act, found, c, dc, dv, crow, v, l, down)
        if act:
            st["steps"] += 1
            st["empty"] += int(found == 0)
            st["accepted"] += gam
            if improve:
                st["improve"] += 1
                st["missed"] += int(not gam)
            else:
                st["local_min"] += 1
        v, dv, i, l, act = nv, nd_, ni, nl, na
    W, Vh = beam_init(v, dv, prm)
    usel, live = v, 1
    for t in range(prm.Tb):
        ids = srv.Aadj[:prm.D0, usel]
        nu = srv.Aadj[prm.D0:, usel]
        cd = ((X[ids] - q) ** 2).sum(1)
        W, Vh, usel, live = beam_step(W, Vh, usel, live, ids, cd, nu, t, prm)
    valid = W[3] == 1
    out = [int(x) for x in np.where(valid, W[0], 0)[:prm.k] if x != 0]
    st["upper_unfinished"] = int(act)
    st["beam_live_end"] = int(live)
    return out, st
