"""Build an HNSW index with hnswlib (multi-threaded) and import its exact graph
(levels, per-layer adjacency, entry point) into the structures used by vsann.Server."""
import os
import struct
import tempfile
import time

import numpy as np
import hnswlib


def build_hnswlib(X, M, efc, seed=0, threads=None):
    N, d = X.shape
    idx = hnswlib.Index(space="l2", dim=d)
    idx.init_index(max_elements=N, ef_construction=efc, M=M, random_seed=seed)
    idx.set_num_threads(threads or os.cpu_count())
    t0 = time.time()
    idx.add_items(X.astype(np.float32), np.arange(N))
    return idx, time.time() - t0


def parse_index(idx, d):
    """Read hnswlib's serialised index. Returns (label_of_internal, levels, nb) where
    nb[l] = dict internal_id -> np.array(neighbour internal ids)."""
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "i.bin")
        idx.save_index(p)
        buf = open(p, "rb").read()
    (off0, maxel, cnt, size_per_el, label_off, off_data) = struct.unpack_from("<6Q", buf, 0)
    maxlevel, enter = struct.unpack_from("<iI", buf, 48)
    maxM, maxM0, M = struct.unpack_from("<3Q", buf, 56)
    pos = 56 + 24 + 8 + 8                      # + mult(double) + ef_construction(size_t)
    lvl0 = np.frombuffer(buf, np.uint8, cnt * size_per_el, pos).reshape(cnt, size_per_el)
    pos += cnt * size_per_el
    labels = lvl0[:, label_off:label_off + 8].copy().view("<u8").ravel().astype(np.int64)
    cnt0 = lvl0[:, :2].copy().view("<u2").ravel()
    links0 = lvl0[:, 4:4 + 4 * maxM0].copy().view("<u4").reshape(cnt, maxM0)
    nb0 = {i: links0[i, :cnt0[i]].astype(np.int64) for i in range(cnt)}
    size_links = maxM * 4 + 4
    levels = np.zeros(cnt, np.int64)
    nbl = {}
    for i in range(cnt):
        (sz,) = struct.unpack_from("<I", buf, pos)
        pos += 4
        if sz:
            lv = sz // size_links
            levels[i] = lv
            blob = np.frombuffer(buf, np.uint8, sz, pos).reshape(lv, size_links)
            for l in range(1, lv + 1):
                c = int(blob[l - 1, :2].view("<u2")[0])
                nbl.setdefault(l, {})[i] = blob[l - 1, 4:4 + 4 * maxM].view("<u4")[:c].astype(np.int64)
            pos += sz
    nb = {0: nb0, **nbl}
    return labels, levels, nb, enter, maxlevel
