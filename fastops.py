"""Multi-core numba kernels for the server's 1-D reads: out = A @ Q (mod P) for a database matrix
A (a x n, uint32 entries < P) and K masked selector vectors Q (n x K, entries < P).
Q is split in 16-bit halves so a chunk of up to 2^16 terms accumulates in uint64 without overflow."""
import numpy as np
import numba as nb
from numba import njit, prange

P = 2147352577
CH = 1 << 15                       # j-chunk (<= 2^16 terms per uint64 accumulator)


@njit(parallel=True, cache=True)
def _mv_chunks(A, Qlo, Qhi, nch, out):
    a, n = A.shape
    K = Qlo.shape[1]
    for t in prange(a * nch):
        i = t // nch
        c = t % nch
        j0 = c * CH
        j1 = min(n, j0 + CH)
        lo = np.zeros(K, np.uint64)
        hi = np.zeros(K, np.uint64)
        for j in range(j0, j1):
            av = np.uint64(A[i, j])
            if av != 0:
                for k in range(K):
                    lo[k] += av * Qlo[j, k]
                    hi[k] += av * Qhi[j, k]
        for k in range(K):
            out[i, c, k] = ((lo[k] % np.uint64(P)) + ((hi[k] % np.uint64(P)) << np.uint64(16))) % np.uint64(P)


def set_threads(t):
    nb.set_num_threads(t)


@njit(cache=True)
def _mv_chunks_serial(A, Qlo, Qhi, nch, out):
    a, n = A.shape
    K = Qlo.shape[1]
    for t in range(a * nch):
        i = t // nch
        c = t % nch
        j0 = c * CH
        j1 = min(n, j0 + CH)
        lo = np.zeros(K, np.uint64)
        hi = np.zeros(K, np.uint64)
        for j in range(j0, j1):
            av = np.uint64(A[i, j])
            if av != 0:
                for k in range(K):
                    lo[k] += av * Qlo[j, k]
                    hi[k] += av * Qhi[j, k]
        for k in range(K):
            out[i, c, k] = ((lo[k] % np.uint64(P)) + ((hi[k] % np.uint64(P)) << np.uint64(16))) % np.uint64(P)


PARALLEL = True            # worker processes (fork) switch this off and use the serial kernel


def matvec_mod(A32, Q):
    """A32 (a,n) uint32 C-contiguous; Q (n,K) int64 in [0,P). Returns (a,K) int64 = A@Q mod P."""
    a, n = A32.shape
    Q = np.ascontiguousarray(Q, dtype=np.uint64)
    Qlo = Q & np.uint64(0xFFFF)
    Qhi = Q >> np.uint64(16)
    nch = (n + CH - 1) // CH
    out = np.zeros((a, nch, Q.shape[1]), np.uint64)
    (_mv_chunks if PARALLEL else _mv_chunks_serial)(A32, Qlo, Qhi, nch, out)
    return (out.sum(1) % np.uint64(P)).astype(np.int64)
