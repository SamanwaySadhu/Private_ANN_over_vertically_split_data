"""Plaintext reference of the bounded, data-independent HNSecW search (Algorithms 2/3 of the paper) on the logical tables.
The secure engine evaluates the same functions (visit_fn, merge_trunc) inside its garbled circuits, so its output must
equal plain_search() exactly."""
import numpy as np

import _path  # noqa: F401


def visit_fn(nb, V, dummies):
    """Visited check + dummy replacement. nb: neighbour row ids, V: rows already accessed (public), dummies: fresh
    dummy rows. Returns (u', visited). A repeat inside the same iteration is caught too."""
    seen = set(int(x) for x in V)
    u, vis = [], []
    for x, dm in zip(nb.tolist(), dummies.tolist()):
        v = x in seen
        y = dm if v else x
        seen.add(y)
        u.append(y)
        vis.append(int(v))
    return np.array(u, np.int64), np.array(vis, np.int64)


def merge_trunc(d, payloads, keep):
    """Stable sort by distance (ties keep array order) and keep the first `keep` entries."""
    o = np.argsort(d, kind="stable")[:keep]
    return d[o], [p[o] for p in payloads]


def layer_step(L, srv, q, qn, ep, DMAX):
    """Returns (dep, initial C, W, V) for a layer entered at logical vector row ep."""
    vec, nr = srv.rows(L.l, [ep])
    dep = int(nr[0] + qn - 2 * (vec[0] @ q))
    return dep


def plain_layer(srv, l, q, qn, ep):
    prm, L = srv.prm, srv.L[l]
    DMAX, deg, T, ef = prm.DMAX, L.deg, L.T, L.ef
    dep = layer_step(L, srv, q, qn, ep, DMAX)
    Cd = np.array([dep] + [DMAX] * (T - 1), np.int64)
    Cg = np.array([L.ga[ep]] + [L.offI + j for j in range(T - 1)], np.int64)
    Wd = np.array([dep] + [DMAX] * (ef - 1), np.int64)
    Wb = np.array([L.vb[ep]] + [srv.wdummy_b(l, j) for j in range(1, ef)], np.int64)
    V = [ep]
    for t in range(T):
        c, Cd, Cg = Cg[0], Cd[1:], Cg[1:]
        nb = L.GT[c]
        dum = L.offA + t * deg + np.arange(deg)
        u, vis = visit_fn(nb, V, dum)
        V += u.tolist()
        vec, nr = srv.rows(l, u)
        dj = nr + qn - 2 * (vec @ q)
        dj = np.where((vis == 1) | (L.flag[u] == 1), DMAX, dj)
        Cd, (Cg,) = merge_trunc(np.r_[Cd, dj], [np.r_[Cg, L.ga[u]]], T)
        Wd, (Wb,) = merge_trunc(np.r_[Wd, dj], [np.r_[Wb, L.vb[u]]], ef)
    return Wb, Wd


def plain_search(srv, q):
    prm = srv.prm
    q = q.astype(np.int64)
    qn = int(q @ q)
    ep = srv.entry()
    for l in range(srv.top, 0, -1):
        Wb, Wd = plain_layer(srv, l, q, qn, ep)
        ep = int(Wb[0])
    Wb, Wd = plain_layer(srv, 0, q, qn, ep)
    ids = [int(b) + 1 if b < srv.D1_real else 0 for b in Wb[:prm.k]]
    return [x for x in ids if x != 0]
