"""Accuracy / LSH-failure evaluation of the vertically split private HNSW pipeline."""
import argparse
import time
from collections import Counter

import numpy as np

try:
    import hnswlib
except ImportError:
    hnswlib = None

from vsann import (Params, Server, MPC, SecureANN, share_query, plain_protocol,
                   lag_tables, P)


def make_data(N, d, nq, seed, clusters=20, latent=6):
    """Clustered data with low intrinsic dimension (like embeddings): per-cluster
    latent_dim-dimensional structure embedded in d dims, plus small isotropic noise."""
    rng = np.random.default_rng(seed)
    cent = rng.uniform(40, 215, size=(clusters, d))
    proj = rng.normal(0, 1, size=(clusters, latent, d))
    proj *= 15 / np.sqrt(latent)

    def draw(n):
        c = rng.integers(0, clusters, n)
        z = rng.normal(0, 1, (n, latent))
        x = cent[c] + np.einsum("nl,nld->nd", z, proj[c]) + rng.normal(0, 2, (n, d))
        return np.clip(np.rint(x), 0, 255).astype(np.int64)
    return draw(N), draw(nq)


def exact_knn(X, q, k):
    dd = ((X - q) ** 2).sum(1)
    return set((np.argsort(dd, kind="stable")[:k] + 1).tolist())


def secure_query(sec, prm, q, mpc):
    """Each client passes ONLY its own coordinate block; the engine sees shares."""
    blocks = [q[idx] for idx in prm.blocks]
    Q, nq = share_query(mpc, blocks, prm)
    mpc.trace.clear()
    return sec.search(Q, nq)


def unit_checks():
    mpc = MPC(4, seed=5)
    # Beaver
    x, y = mpc.rint(50), mpc.rint(50)
    assert np.array_equal(mpc.reveal(mpc.mul(mpc.share(x), mpc.share(y))), np.mod(x * y, P))
    # one-hot via interpolation
    prm = Params(N=10, d=4, m=4, onehot="lagrange")
    sec = SecureANN.__new__(SecureANN)
    sec.c, sec.prm = mpc, prm
    for n in (2, 17, 68, 301):
        for z in (0, 1, n // 2, n - 1):
            e = mpc.reveal(sec.onehot(mpc.share(z), n))
            ref = np.zeros(n, np.int64)
            ref[z] = 1
            assert np.array_equal(e, ref), (n, z)
    print("unit checks passed: Beaver product, Lagrange one-hot (n=2,17,68,301)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--N", type=int, default=2000)
    ap.add_argument("--d", type=int, default=32)
    ap.add_argument("--m", type=int, default=4)
    ap.add_argument("--queries", type=int, default=100)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--E", type=int, default=32)
    ap.add_argument("--Tg", type=int, default=12)
    ap.add_argument("--Tb", type=int, default=48)
    ap.add_argument("--s", type=int, default=6)
    ap.add_argument("--M", type=int, default=8)
    ap.add_argument("--onehot", default="ideal", choices=["ideal", "lagrange"])
    ap.add_argument("--he", default="sim", choices=["sim", "openfhe"],
                    help="2-D read backend: ideal-functionality sim or real threshold BFV (OpenFHE)")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    unit_checks()
    rho = tuple(0.5 * 2 ** r for r in range(a.s))
    prm = Params(N=a.N, d=a.d, m=a.m, M=a.M, k=a.k, E=a.E, Tg=a.Tg, Tb=a.Tb, s=a.s,
                 rho=rho, seed=a.seed, onehot=a.onehot)
    X, Qs = make_data(a.N, a.d, a.queries, a.seed)
    t0 = time.time()
    srv = Server(X, prm)
    bs = srv.build_stats
    print(f"\n[offline] N={a.N} d={a.d} m={a.m} layers={srv.top + 1} upper-rows U={srv.U} "
          f"H={prm.H} sigma={prm.sigma} s={prm.s}  built in {time.time() - t0:.1f}s")
    print(f"[offline] bucket-cap loss: {1 - bs['kept'] / bs['points']:.3%} of (point,radius) entries "
          f"dropped by one-representative-per-key; cuckoo retries={bs['cuckoo_retries']} "
          f"stash cells used={bs['stash_used']}")

    ref = None
    if hnswlib is not None:       # literature-standard plaintext HNSW (same M, efConstruction)
        ref = hnswlib.Index(space="l2", dim=a.d)
        ref.init_index(max_elements=a.N, ef_construction=prm.efc, M=prm.M, random_seed=a.seed)
        ref.add_items(X.astype(np.float32), np.arange(1, a.N + 1))
        ref.set_ef(a.E)
    rec_lib = []

    mpc = MPC(a.m, seed=a.seed + 7, debug=True)
    he = None
    if a.he == "openfhe":
        from real_he import OpenFHEThreshold
        he = OpenFHEThreshold(mpc, srv.Dtab)
        print(f"[HE] OpenFHE threshold BFV, {a.m}-of-{a.m}, ring dim {he.ring_dim}, plaintext modulus p={P}")
    sec = SecureANN(srv, mpc, he)

    rec_sec, rec_hnsw, rec_plain = [], [], []
    mismatch = 0
    steps = Counter()
    rad_hist = Counter()
    q_prem_desc = 0
    q_budget_beam = 0
    q_budget_up = 0
    rounding_fail = 0
    entry_ratio = []
    t0 = time.time()
    for qi, q in enumerate(Qs):
        truth = exact_knn(srv.X[1:], q, a.k)
        res = secure_query(sec, prm, q, mpc)
        strace = list(mpc.trace)
        pres, ptrace, info = plain_protocol(srv, q)
        keys = ("act", "l", "v", "gam", "found", "c", "rad")
        same = (res == pres and len(strace) == len(ptrace) and
                all(all(s_[k] == p_[k] for k in keys) for s_, p_ in zip(strace, ptrace)))
        mismatch += (not same)
        rec_sec.append(len(truth & set(res)) / a.k)
        rec_plain.append(len(truth & set(pres)) / a.k)
        rec_hnsw.append(len(truth & set(srv.hnsw_search(q, a.E, a.k))) / a.k)
        if ref is not None:
            lab, _ = ref.knn_query(q.astype(np.float32)[None, :], k=a.k)
            rec_lib.append(len(truth & set(lab[0].tolist())) / a.k)
        prem = False
        for st in ptrace:
            rounding_fail += (not st["rounding_ok"])
            if not st["act"]:
                continue
            steps["active"] += 1
            steps["empty_all_radii"] += (st["found"] == 0)
            steps["found_not_improving"] += (st["found"] == 1 and not st["gam"])
            steps["accepted_move"] += st["gam"]
            if st["improve"]:
                steps["improve_exists"] += 1
                if not st["gam"]:
                    steps["missed_improvement"] += 1
                    steps["missed_empty"] += (st["found"] == 0)
                    steps["missed_nonimp"] += (st["found"] == 1)
                    prem = True
            else:
                steps["local_min"] += 1
                steps["local_min_descend"] += (not st["gam"])
            if st["gam"]:
                rad_hist[st["rad"]] += 1
        q_prem_desc += prem
        q_budget_up += info["upper_unfinished"]
        q_budget_beam += info["beam_live_end"]
        # entry quality vs exact greedy descent
        cur = [srv.ep]
        for lc in range(srv.top, 0, -1):
            cur = [srv.search_layer(q, cur, 1, lc)[0][1]]
        d_ex = ((srv.X[cur[0]] - q) ** 2).sum()
        d_ls = ((srv.X[info["ep0"]] - q) ** 2).sum()
        entry_ratio.append(np.sqrt(d_ls / max(d_ex, 1)))
        if (qi + 1) % 10 == 0:
            print(f"  ... {qi + 1}/{a.queries} queries, {(time.time() - t0) / (qi + 1):.2f}s/query")

    nQ = a.queries
    print("\n==================== RESULTS ====================")
    print(f"secure pipeline == plain emulation (ids and LSH trace) on {nQ - mismatch}/{nQ} queries")
    print(f"recall@{a.k}  secure private HNSW : {np.mean(rec_sec):.4f}")
    print(f"recall@{a.k}  plain emulation     : {np.mean(rec_plain):.4f}")
    print(f"recall@{a.k}  plain exact-upper HNSW (ef={a.E}) baseline: {np.mean(rec_hnsw):.4f}")
    if ref is not None:
        print(f"recall@{a.k}  hnswlib (library HNSW, M={prm.M}, ef={a.E}) : {np.mean(rec_lib):.4f}")
    print(f"queries with recall 1.0: {np.mean(np.array(rec_sec) == 1):.2%}; min recall {min(rec_sec):.2f}")
    A = steps["active"]
    print(f"\nLSH upper-layer statistics over {A} active steps ({A / nQ:.1f}/query)")
    print(f"  all radii empty (no bucket hit)      : {steps['empty_all_radii'] / A:.2%}")
    print(f"  hit but candidate not improving      : {steps['found_not_improving'] / A:.2%}")
    print(f"  accepted improving move              : {steps['accepted_move'] / A:.2%}")
    I = max(steps["improve_exists"], 1)
    print(f"  steps where an improving neighbour exists: {steps['improve_exists']}")
    print(f"  -> LSH FAILURE RATE (descend although exact greedy would move): "
          f"{steps['missed_improvement'] / I:.2%}")
    print(f"       of which empty buckets {steps['missed_empty'] / I:.2%}, "
          f"non-improving representative {steps['missed_nonimp'] / I:.2%}")
    print(f"  steps at a local minimum (correct descents): {steps['local_min']} "
          f"({steps['local_min_descend']} descended)")
    print(f"  queries with >=1 premature descent    : {q_prem_desc / nQ:.2%}")
    print(f"  mean dist(entry)/dist(exact greedy entry): {np.mean(entry_ratio):.3f}")
    print(f"  accepted-move radius histogram: {dict(sorted(rad_hist.items()))}")
    print(f"  rounding bound h in {{h_hat, h_hat+1}} violated: {rounding_fail} times")
    print(f"budget: upper phase unfinished (Tg={a.Tg}): {q_budget_up / nQ:.2%}; "
          f"beam frontier non-empty after Tb={a.Tb}: {q_budget_beam / nQ:.2%}")
    print("\nper-query protocol cost (simulated counters):")
    for k_, v_ in sorted(mpc.stats.items()):
        print(f"  {k_:28s} {v_ / nQ:12.1f}")


if __name__ == "__main__":
    main()
