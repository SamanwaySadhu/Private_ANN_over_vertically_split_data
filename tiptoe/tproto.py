"""Plaintext reference of the (bounded, deterministic) Tiptoe search. The secure engine evaluates the same helpers inside its
ideal functionalities, so its output must equal plain_search() exactly.

  1. choose the cluster whose (public, integer) centroid is closest to the query (client side in the paper)
  2. ranking:  row r of the chosen cluster scores  nu[r] - 2 <x_r, q'>  on the quantised vectors
  3. the k best rows are returned (ties: lowest row index) and mapped to vector ids"""
import numpy as np

import _path  # noqa: F401


def nearest_cluster(cent, q):
    """argmin over centroids of the integer squared distance; ties -> lowest index (the GC tournament uses the same rule)."""
    D = ((cent - q[None]) ** 2).sum(1)
    return int(np.argmin(D)), D


def topk_rows(score, k):
    return np.argsort(score, kind="stable")[:k]


def plain_search(srv, q):
    q = q.astype(np.int64)
    c, _ = nearest_cluster(srv.cent, q)
    qq = srv.quant(q[None])[0]
    ip = srv.X8[c].astype(np.int64) @ qq
    score = srv.nu[c] - 2 * ip
    rows = topk_rows(score, srv.prm.k)
    return [int(x) for x in srv.ids[c][rows] if x != 0]
