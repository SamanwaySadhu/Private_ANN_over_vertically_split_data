"""Real ANN benchmark datasets (TEXMEX SIFT1M / GIST1M) as integer-valued vectors for the
fixed-point MPC protocol, with exact ground truth for recall@k."""
import os
import numpy as np

DATA_ROOT = os.environ.get("ANN_DATA", os.path.expanduser("~/ann_data"))
FILES = {
    "sift": ("sift/sift/sift_base.fvecs", "sift/sift/sift_query.fvecs"),
    "gist": ("gist/gist/gist_base.fvecs", "gist/gist/gist_query.fvecs"),
}


def read_fvecs(path, n=None):
    raw = np.memmap(path, dtype=np.int32, mode="r")
    d = int(raw[0])
    mat = raw.reshape(-1, d + 1)
    if n is not None:
        mat = mat[:n]
    return np.ascontiguousarray(mat[:, 1:]).view(np.float32)


def exact_knn(X, Q, k, chunk=200):
    """Exact k-NN ids (0-based, ascending distance) by BLAS in float64 chunks."""
    X = X.astype(np.float64)
    xn = (X ** 2).sum(1)
    out = np.empty((len(Q), k), np.int64)
    for s in range(0, len(Q), chunk):
        q = Q[s:s + chunk].astype(np.float64)
        dd = xn[None, :] - 2 * q @ X.T
        idx = np.argpartition(dd, k, axis=1)[:, :k]
        part = np.take_along_axis(dd, idx, 1)
        out[s:s + chunk] = np.take_along_axis(idx, np.argsort(part, 1, kind="stable"), 1)
    return out


def load(name, N, nq, k=10, seed=0, subsample="first"):
    """Returns dict with
         Xf, Qf : original float32 vectors (what the literature measures recall against)
         X, Q   : int64 vectors in [0,255] used by the protocol (SIFT: as is; GIST: global 8-bit quantisation)
         gt_f, gt_q : exact top-k ids (0-based) w.r.t. float / quantised data."""
    bpath, qpath = (os.path.join(DATA_ROOT, f) for f in FILES[name])
    Xf = read_fvecs(bpath, None if subsample != "first" else N)
    if subsample == "random":
        rng = np.random.default_rng(seed)
        Xf = Xf[np.sort(rng.choice(len(Xf), N, replace=False))]
    Qf = read_fvecs(qpath, nq)
    if name == "sift":
        X, Q, scale = Xf.astype(np.int64), Qf.astype(np.int64), 1.0
    else:
        scale = 255.0 / float(Xf.max())
        X = np.clip(np.rint(Xf * scale), 0, 255).astype(np.int64)
        Q = np.clip(np.rint(Qf * scale), 0, 255).astype(np.int64)
    return dict(name=name, N=len(X), d=X.shape[1], Xf=Xf, Qf=Qf, X=X, Q=Q, scale=scale,
                gt_f=exact_knn(Xf, Qf, k), gt_q=exact_knn(X, Q, k))
