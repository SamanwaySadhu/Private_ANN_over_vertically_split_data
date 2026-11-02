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


# ------------------------------------------------------------------------------------------
# Fully parallel server read: share summation, 16-bit split, cache-tiled matrix product and
# chunk reduction all run inside numba prange loops (no single-threaded numpy on the hot path).
# ------------------------------------------------------------------------------------------
JB, RB = 2048, 16


@njit(parallel=True, cache=True)
def _prep(qsh, K, n, Qlo, Qhi):
    """qsh (m, K, n) uint64 shares of (e - r); Qlo/Qhi (n, K) uint32 = low/high 16 bits of the sum mod P."""
    m = qsh.shape[0]
    for j in prange(n):
        for k in range(K):
            s = np.uint64(0)
            for t in range(m):
                s += qsh[t, k, j]
            s %= np.uint64(P)
            Qlo[j, k] = np.uint32(s & np.uint64(0xFFFF))
            Qhi[j, k] = np.uint32(s >> np.uint64(16))


@njit(parallel=True, cache=True)
def _tiled(A, Qlo, Qhi, nch, out):
    a, n = A.shape
    K = Qlo.shape[1]
    nrb = (a + RB - 1) // RB
    for t in prange(nch * nrb):
        c = t // nrb
        rb = t % nrb
        j0 = c * JB
        j1 = min(n, j0 + JB)
        r0 = rb * RB
        r1 = min(a, r0 + RB)
        for i in range(r0, r1):
            lo = np.zeros(K, np.uint64)
            hi = np.zeros(K, np.uint64)
            for j in range(j0, j1):
                av = np.uint64(A[i, j])
                for k in range(K):
                    lo[k] += av * np.uint64(Qlo[j, k])
                    hi[k] += av * np.uint64(Qhi[j, k])
            for k in range(K):
                out[i, c, k] = ((lo[k] % np.uint64(P)) + ((hi[k] % np.uint64(P)) << np.uint64(16))) % np.uint64(P)


@njit(parallel=True, cache=True)
def _reduce(out, res):
    a, nch, K = out.shape
    for i in prange(a):
        for k in range(K):
            s = np.uint64(0)
            for c in range(nch):
                s += out[i, c, k]
            res[i, k] = s % np.uint64(P)


def server_read(A32, qsh):
    """A32 (a,n) uint32; qsh (m,K,n) uint64 additive shares of e - r. Returns (a,K) int64 = A @ (sum qsh) mod P."""
    a, n = A32.shape
    m, K, _ = qsh.shape
    Qlo = np.empty((n, K), np.uint32)
    Qhi = np.empty((n, K), np.uint32)
    _prep(qsh, K, n, Qlo, Qhi)
    nch = (n + JB - 1) // JB
    out = np.zeros((a, nch, K), np.uint64)
    _tiled(A32, Qlo, Qhi, nch, out)
    res = np.empty((a, K), np.uint64)
    _reduce(out, res)
    return res.astype(np.int64)


# ------------------------------------------------------------------------------------------
# CLIENT-side kernels (all cores). Each function exists in a parallel and a serial build; worker
# processes created with fork() use the serial build (numba's parallel runtime is not fork-safe).
# ------------------------------------------------------------------------------------------
def _client_kernels(parallel):
    deco = njit(parallel=parallel)

    @deco
    def sub_mod(E, R, out):
        """out = (E - R) mod P, elementwise over flat int64 arrays: a client forms its share of q_A = e - r."""
        for i in prange(E.shape[0]):
            x = E[i] - R[i]
            if x < 0:
                x += P
            out[i] = x

    @deco
    def beaver_open(X, A, Y, B, e, f):
        """X,A,Y,B (m,L): opened values e = sum_c (X-A), f = sum_c (Y-B) (mod P); client c contributes X_c-A_c."""
        m, L = X.shape
        for j in prange(L):
            se = np.int64(0)
            sf = np.int64(0)
            for c in range(m):
                x = X[c, j] - A[c, j]
                if x < 0:
                    x += P
                se += x
                y = Y[c, j] - B[c, j]
                if y < 0:
                    y += P
                sf += y
            e[j] = se % P
            f[j] = sf % P

    @deco
    def beaver_finish(C, e, f, A, B, out):
        """[xy]_c = C_c + e B_c + f A_c  (+ e f for client 0), all mod P."""
        m, L = C.shape
        for idx in prange(m * L):
            c = idx // L
            j = idx % L
            z = (C[c, j] + (e[j] * B[c, j]) % P + (f[j] * A[c, j]) % P) % P
            if c == 0:
                z = (z + (e[j] * f[j]) % P) % P
            out[c, j] = z

    @deco
    def sum_last(Z, out):
        """Z (m,K,d) -> out (m,K) = sum over d mod P (inner-product accumulation of a distance)."""
        m, K, d = Z.shape
        for idx in prange(m * K):
            s = np.int64(0)
            c = idx // K
            k = idx % K
            for t in range(d):
                s += Z[c, k, t]
            out[c, k] = s % P

    @deco
    def lag_tm(Bn, Dm, tp, out):
        R = Bn.shape[0]
        for h in prange(R):
            for t in range(R):
                out[h, t] = (Bn[h, t] * tp[Dm[h, t]]) % P

    @deco
    def matmul_mod_k(A, B, out):
        a, b = A.shape
        c = B.shape[1]
        for i in prange(a):
            for k in range(c):
                s = np.int64(0)
                for j in range(b):
                    s += (A[i, j] * B[j, k]) % P
                out[i, k] = s % P

    return sub_mod, beaver_open, beaver_finish, sum_last, lag_tm, matmul_mod_k


_KP = _client_kernels(True)
_KS = _client_kernels(False)


def ck():
    """client kernels for the current mode"""
    return _KP if PARALLEL else _KS
