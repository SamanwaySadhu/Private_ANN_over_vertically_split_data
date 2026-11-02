"""Stand-alone simulation of the server's masked 1-D read  y = A @ (sum_i q_i) mod p,  q_i = e_i - r_i,
for SIFT/GIST-sized databases, on CPU (numba, all cores) and/or GPU (PyTorch/CUDA, all GPUs).

Nothing else of the protocol runs: no clients, GC, HE or network. Inputs are random but have the exact
shapes the full protocol uses, so the numbers are the server's matrix-product cost for one query:

    per query = Tg x [upper table read] + Tg x [layer-0 dictionary/vector read]       (K = 1)
              + Tb x [adjacency read, a = 2*D0]      + Tb x [neighbour-vector read, a = d+1, K = D0]

GPU method (exact mod p = 2147352577 < 2^31): split A and Q into 16-bit limbs, float64 GEMM on
[A_lo; A_hi] @ [Q_lo | Q_hi] over chunks of 2^19 columns (every dot product < 2^32 * 2^19 = 2^51 < 2^53,
so fp64 is exact), then recombine the four partial products in int64 mod p. A is uploaded once and stays
resident (the server database is static); only the m shares of (e - r) are per-read inputs.
With several GPUs the rows of A are sharded across devices.

Examples (see --help):  python server_read_sim.py --backend gpu --N 1000000 --m 2,4,8 --E 32,64,128
"""
import argparse
import csv
import json
import os
import time

import numpy as np

P = 2147352577
NC = 1 << 19                      # GEMM column chunk: keeps fp64 dot products exact (< 2^53)
M32 = (1 << 32) % P


# ----------------------------------------------------------------------------- workloads
def workload(a):
    """List of (name, a_rows, n_cols, K, count) for one query."""
    N, d, E = a.N, a.d, a.E
    D0 = 2 * a.M
    Tb = a.Tb or 2 * E
    return [
        ("upper table read", a.arow, a.U, 1, a.Tg),
        ("dictionary/col read", d + 1, N + 1, 1, a.Tg),
        ("adjacency read", 2 * D0, N + 1, 1, Tb),
        ("neighbour-vector read", d + 1, N + 1, D0, Tb),
    ]


# ----------------------------------------------------------------------------- CPU backend (numba)
class CPUBackend:
    name = "cpu"

    def __init__(self, a):
        import numba as nb
        import fastops
        nb.set_num_threads(a.cpu_threads or nb.config.NUMBA_NUM_THREADS)
        fastops.PARALLEL = True
        self.fastops, self.threads = fastops, nb.get_num_threads()
        self.desc = f"CPU numba, {self.threads} threads"

    def make_table(self, rows, n, rng, maxv):
        return rng.integers(0, maxv, (rows, n), dtype=np.uint32)

    def make_shares(self, m, K, n, rng):
        return rng.integers(0, P, (m, K, n), dtype=np.uint64)

    def read(self, A, q):
        return self.fastops.server_read(A, q)

    def sync(self):
        pass

    def mem_info(self):
        return ""


# ----------------------------------------------------------------------------- GPU backend (torch)
class GPUBackend:
    name = "gpu"

    def __init__(self, a):
        import torch
        self.t = torch
        if a.device == "cpu":                              # algorithm check on machines without a GPU
            self.devs = [torch.device("cpu")]
        else:
            if not torch.cuda.is_available():
                raise SystemExit("torch.cuda is not available: install a CUDA build of PyTorch "
                                 "(pip install torch --index-url https://download.pytorch.org/whl/cu121) "
                                 "or use --backend cpu / --device cpu")
            ng = torch.cuda.device_count()
            ids = [int(x) for x in a.gpus.split(",")] if a.gpus else list(range(ng))
            self.devs = [torch.device(f"cuda:{i}") for i in ids]
        names = sorted({torch.cuda.get_device_name(d) for d in self.devs}) if self.devs[0].type == "cuda" else ["cpu"]
        self.desc = f"torch {torch.__version__}, {len(self.devs)} x {'/'.join(names)}, fp64 limb GEMM"
        self.h2d = a.h2d

    # A is sharded by rows over the devices and kept as fp64 16-bit limbs (single limb if all entries < 2^16)
    def make_table(self, rows, n, rng, maxv):
        t = self.t
        parts = np.array_split(np.arange(rows), len(self.devs))
        shards = []
        for dev, idx in zip(self.devs, parts):
            if len(idx) == 0:
                continue
            g = t.Generator(device=dev); g.manual_seed(int(rng.integers(1 << 30)))
            A = t.randint(0, maxv, (len(idx), n), dtype=t.int64, device=dev, generator=g)
            shards.append(self._limbs(A, maxv))
        return shards

    def from_numpy(self, A32):
        t = self.t
        parts = np.array_split(np.arange(A32.shape[0]), len(self.devs))
        out = []
        for dev, idx in zip(self.devs, parts):
            if len(idx):
                A = t.from_numpy(A32[idx].astype(np.int64)).to(dev)
                out.append(self._limbs(A, int(A32.max()) + 1))
        return out

    def _limbs(self, A, maxv):
        t = self.t
        lo = (A & 0xFFFF).to(t.float64)
        if maxv <= (1 << 16):
            return (A.shape[0], 1, lo.contiguous())
        hi = (A >> 16).to(t.float64)
        return (A.shape[0], 2, t.cat([lo, hi], 0).contiguous())     # (2a, n) rows [lo; hi]

    def make_shares(self, m, K, n, rng):
        t = self.t
        out = []
        for dev in self.devs:
            g = t.Generator(device=dev); g.manual_seed(int(rng.integers(1 << 30)))
            out.append(t.randint(0, P, (m, K, n), dtype=t.int64, device=dev, generator=g))
        if self.h2d and self.devs[0].type == "cuda":
            # shares live in pinned host memory (they arrive over the network); every read pays the PCIe copy
            return [o.cpu().pin_memory() for o in out[:1]]
        return out

    def _read_shard(self, shard, q, dev):
        t = self.t
        a, nl, Ab = shard
        if q.device != dev:
            q = q.to(dev, non_blocking=True)
        m, K, n = q.shape
        qs = q.sum(0) % P                                   # (K, n)  server adds the m client shares
        Qb = t.cat([qs & 0xFFFF, qs >> 16], 0).to(t.float64)  # (2K, n)  [lo ; hi]
        acc = t.zeros((a, K), dtype=t.int64, device=dev)
        for c0 in range(0, n, NC):
            c1 = min(n, c0 + NC)
            R = Ab[:, c0:c1] @ Qb[:, c0:c1].T               # (nl*a, 2K) exact fp64
            R = R.to(t.int64) % P
            if nl == 2:
                alo, ahi = R[:a], R[a:]
                ll, lh, hl, hh = alo[:, :K], alo[:, K:], ahi[:, :K], ahi[:, K:]
                v = ll + (((lh + hl) % P) << 16) + (hh * M32) % P
            else:
                v = R[:, :K] + ((R[:, K:] % P) << 16)
            acc = (acc + v) % P
        return acc

    def read(self, A, q):
        qs = q if isinstance(q, list) else [q]
        outs = [self._read_shard(sh, qs[min(i, len(qs) - 1)], self.devs[i]) for i, sh in enumerate(A)]
        return self.t.cat([o.to(self.devs[0]) for o in outs], 0) if len(outs) > 1 else outs[0]

    def sync(self):
        if self.devs[0].type == "cuda":
            for d in self.devs:
                self.t.cuda.synchronize(d)

    def mem_info(self):
        if self.devs[0].type != "cuda":
            return ""
        return " | " + ", ".join(f"{d}: peak {self.t.cuda.max_memory_allocated(d)/2**30:.1f} GB" for d in self.devs)


# ----------------------------------------------------------------------------- helpers
def best_time(fn, sync, reps, warm=1):
    for _ in range(warm):
        fn()
    sync()
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter(); fn(); sync(); ts.append(time.perf_counter() - t0)
    return min(ts), float(np.median(ts))


def verify(a):
    """GPU(or torch-cpu) result == numba CPU result == exact Python-int dot product, on a reduced shape."""
    be = GPUBackend(a)
    import numba as nb, fastops
    fastops.PARALLEL = True
    rng = np.random.default_rng(1)
    n, rows, K, m = 150_000, 40, 3, 4
    for maxv in (256, P):
        A = rng.integers(0, maxv, (rows, n), dtype=np.uint32)
        q = rng.integers(0, P, (m, K, n), dtype=np.uint64)
        ref = fastops.server_read(A, q)
        qa = q.astype(object).sum(0) % P
        exact = np.array([[int(sum(int(A[r, j]) * int(qa[k, j]) for j in range(0, n, 97))) for k in range(K)] for r in range(2)])
        got = be.read(be.from_numpy(A), be.t.from_numpy(q.astype(np.int64)).to(be.devs[0])).cpu().numpy()
        ok_cpu = np.array_equal(got, ref)
        # independent exact check on a strided subset of columns for 2 rows (full n is too slow in Python ints)
        sub = np.arange(0, n, 97)
        qs = q[:, :, sub].astype(object).sum(0) % P
        ex = np.array([[int((A[r, sub].astype(object) * qs[k]).sum() % P) for k in range(K)] for r in range(2)])
        qsub = q.copy(); mask = np.zeros(n, bool); mask[sub] = True; qsub[:, :, ~mask] = 0
        got2 = be.read(be.from_numpy(A), be.t.from_numpy(qsub.astype(np.int64)).to(be.devs[0])).cpu().numpy()[:2]
        print(f"verify  A<{maxv:>10}: matches numba kernel: {ok_cpu} | matches exact python ints: {np.array_equal(got2, ex)}")
        assert ok_cpu and np.array_equal(got2, ex)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", default="gpu", choices=["cpu", "gpu", "both"])
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"], help="'cpu' runs the GPU algorithm via torch on CPU (testing only)")
    ap.add_argument("--gpus", default="", help="comma list of CUDA device ids (default: all visible)")
    ap.add_argument("--N", default="1000000", help="comma list of database sizes")
    ap.add_argument("--m", default="8", help="comma list of client counts (number of shares summed per read)")
    ap.add_argument("--E", default="32,64,128", help="comma list of beam widths (Tb = 2E beam steps)")
    ap.add_argument("--d", type=int, default=128, help="dimension: SIFT 128, GIST 960")
    ap.add_argument("--M", type=int, default=8, help="HNSW M (layer-0 degree D0 = 2M, adjacency rows 2*D0)")
    ap.add_argument("--Tg", type=int, default=12, help="flattened upper-layer iterations")
    ap.add_argument("--Tb", type=int, default=0, help="beam steps (default 2E)")
    ap.add_argument("--U", type=int, default=267131, help="rows of the flattened upper-layer table (SIFT1M: 267131)")
    ap.add_argument("--arow", type=int, default=252, help="height of the upper table (SIFT1M m=8: 252)")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--cpu-threads", type=int, default=0)
    ap.add_argument("--h2d", action="store_true", help="GPU: also charge the PCIe copy of the m shares to every read")
    ap.add_argument("--verify", action="store_true", help="check the GPU algorithm against the numba kernel and exact ints, then exit")
    ap.add_argument("--out", default="results/server_read_sim")
    a = ap.parse_args()

    if a.verify:
        verify(a); return

    backends = [CPUBackend(a)] if a.backend == "cpu" else [GPUBackend(a)] if a.backend == "gpu" else [CPUBackend(a), GPUBackend(a)]
    rng = np.random.default_rng(0)
    rows_out, summary = [], []
    for N in map(int, a.N.split(",")):
        for E in map(int, a.E.split(",")):
            for m in map(int, a.m.split(",")):
                a.N, a.E = N, E
                wl = workload(a)
                for be in backends:
                    tables, tot, parts = {}, 0.0, []
                    for name, rows, n, K, cnt in wl:
                        key = (rows, n)
                        if key not in tables:
                            tables[key] = be.make_table(rows, n, rng, 256 if "vector" in name or "dict" in name else (n if "adj" in name else P))
                        q = be.make_shares(m, K, n, rng)
                        tmin, tmed = best_time(lambda: be.read(tables[key], q), be.sync, a.reps)
                        bytes_a = rows * n * 4                       # logical uint32 database bytes streamed per read
                        rows_out.append(dict(backend=be.name, N=N, m=m, E=E, read=name, a=rows, n=n, K=K, count=cnt,
                                             t_read_ms=tmin * 1e3, t_median_ms=tmed * 1e3, t_total_s=tmin * cnt,
                                             GBps_logical=bytes_a / tmin / 1e9, Gmac_s=rows * n * K / tmin / 1e9))
                        tot += tmin * cnt; parts.append((name, cnt, tmin))
                    del tables
                    summary.append(dict(backend=be.name, N=N, m=m, E=E, server_matmul_s_per_query=tot))
                    print(f"[{be.desc}] N={N} m={m} E={E}  Tb={a.Tb or 2*E}: " + "  ".join(f"{n} {c}x{t*1e3:.2f}ms" for n, c, t in parts)
                          + f"  => {tot:.3f} s/query{be.mem_info()}", flush=True)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(dict(summary=summary, reads=rows_out), open(a.out + ".json", "w"), indent=1)
    with open(a.out + ".csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0])); w.writeheader(); w.writerows(rows_out)
    print("\nbackend    N        m   E    server matmul s/query")
    for s in summary:
        print(f"{s['backend']:<8} {s['N']:>8} {s['m']:>3} {s['E']:>4}   {s['server_matmul_s_per_query']:.3f}")
    print(f"\nwrote {a.out}.json and {a.out}.csv")


if __name__ == "__main__":
    main()
