"""Plaintext reference of the (bounded, randomised) Panther search. The secure engine evaluates the same helper functions inside
its ideal functionalities with the same per-query randomness, so its output must equal plain_search() exactly."""
import numpy as np

import _path  # noqa: F401


def shuffle(srv, rng):
    """Server's per-query shuffle: shuffled position i holds cluster perm[i]."""
    return rng.permutation(srv.prm.t)


def bin_min_topk(dist, prm):
    """ApproxTopK (Alg. 1): consecutive (= random, the order is shuffled) bins, minimum per bin, exact top-u of the minima.
    Returns the selected shuffled positions (ascending distance, ties by position)."""
    t, kp, u = prm.t, prm.kprime, prm.u
    edges = np.linspace(0, t, kp + 1).astype(np.int64)
    mins = np.array([edges[b] + int(np.argmin(dist[edges[b]:edges[b + 1]])) for b in range(kp)])
    o = np.argsort(dist[mins], kind="stable")[:u]
    return mins[o]


def cuckoo_plan(srv, sel, rng):
    """Client side of the batch PIR: place the u wanted shuffled positions into B buckets (one per bucket), fill empty
    buckets with distinct random dummy positions of that bucket. Returns (pos[B] = shuffled position queried in bucket b,
    n_failed). A failed cuckoo insertion drops that cluster."""
    h, content = srv.buckets()
    B = srv.prm.B
    slot = [-1] * B
    failed = 0
    for x in sel.tolist():
        cur, ok = x, False
        for _ in range(500):
            free = [b for b in h[cur] if slot[b] < 0]
            if free:
                slot[free[0]] = cur
                ok = True
                break
            b = int(h[cur][rng.integers(3)])
            slot[b], cur = cur, slot[b]
        if not ok:
            failed += 1
    used = set(s for s in slot if s >= 0)
    for b in range(B):
        if slot[b] < 0:
            opts = [i for i in content[b] if i not in used]
            slot[b] = int(rng.choice(opts))
            used.add(slot[b])
    return np.array(slot, np.int64), failed


def exact_topk(dist, ids, k):
    """Ideal functionality of the top-k selection network: k smallest distances, ties by input position."""
    o = np.argsort(dist, kind="stable")[:k]
    return ids[o]


def plain_search(srv, q, seed):
    prm = srv.prm
    rng = np.random.default_rng(seed)
    q = q.astype(np.int64)
    perm = shuffle(srv, rng)
    dist = srv.Cn[perm] + int(q @ q) - 2 * (srv.C[perm] @ q)
    sel = bin_min_topk(dist, prm)
    pos, failed = cuckoo_plan(srv, sel, rng)
    ids = srv.cluster[perm[pos]].reshape(-1)
    dp = srv.nrm[ids] + int(q @ q) - 2 * (srv.X[ids] @ q)
    return [int(x) for x in exact_topk(dp, ids, prm.k) if x != 0]
