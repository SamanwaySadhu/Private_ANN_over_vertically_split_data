"""Toy-size REAL execution of the cryptographic core of the adaptation (no ideal functionality):
  * m clients each hold an additive share of q~ in Z_{2^lt} and an additive share s_i of the LWE secret (ternary),
    b_i = A s_i + e_i + D q~^(i)  (mod 2^64, D = 2^(64-lt), e_i discrete Gaussian sigma = 81920 as in paper App. C);
  * the server adds the b_i and computes c = M b with the preprocessed hint H = M A;
  * the decryption  round((c - sum_i H s_i) / D)  is evaluated on the shares (c at the server, -H s_i at client i), exactly the
    arithmetic done inside the rank_topk garbled circuit, and must equal M q~ mod 2^lt;
  * also checks the paper's two token tricks: base-16 digit decomposition of H (App. C) and dropping the low-order bits of H (A.3).
Run:  python tlwe_check.py"""
import numpy as np

rng = np.random.default_rng(1)
U = np.uint64


def run(m=3, n=256, d=8, C=6, R=20, lt=17, drop=16, trials=20):
    D = U(1) << U(64 - lt)
    bad = 0
    for _ in range(trials):
        M = rng.integers(-8, 8, size=(R, C * d))
        Mu = M.astype(np.int64).astype(U)                                    # two's complement entries
        A = rng.integers(0, 1 << 63, size=(C * d, n), dtype=np.uint64) * U(2) + rng.integers(0, 2, size=(C * d, n), dtype=np.uint64)
        H = Mu @ A                                                           # SimplePIR hint (uint64 wraps)
        q = rng.integers(-8, 8, size=d)
        cs = int(rng.integers(C))
        qt = np.zeros((C, d), np.int64)
        qt[cs] = q
        qt = qt.reshape(-1)
        sh = rng.integers(0, 1 << lt, size=(m, C * d), dtype=np.int64)
        sh[0] = (qt - sh[1:].sum(0)) & ((1 << lt) - 1)
        s = rng.integers(-1, 2, size=(m, n)).astype(np.int64).astype(U)
        e = np.rint(rng.normal(0, 81920, size=(m, C * d))).astype(np.int64).astype(U)
        b = sum((A @ s[i] + e[i] + sh[i].astype(U) * D) for i in range(m))   # sum of the clients' ciphertext shares
        c = Mu @ b
        Hd = (H >> U(drop)) << U(drop)                                       # server drops the low-order bits (A.3)
        u = [(U(0) - (Hd @ s[i])) for i in range(m)]
        v = c + sum(u)
        val = ((v + (D >> U(1))) >> U(64 - lt)).astype(np.int64) & ((1 << lt) - 1)
        ref = (M @ qt) & ((1 << lt) - 1)
        bad += int(not np.array_equal(val, ref))
        # base-16 digits of H: sum_k 16^k (H_k s) == H s mod 2^64 with every digit-product sum < p_rlwe = 65537
        tot = U(0) * np.zeros(R, U)
        for k in range(16):
            Hk = ((H >> U(4 * k)) & U(15)).astype(np.int64)
            part = Hk @ (np.where(s[0] > U(1 << 62), -1, s[0].astype(np.int64)))
            assert np.abs(part).max() < 65537 // 2          # fits the RLWE plaintext space (n * 15 < 2^15)
            tot = tot + (part.astype(np.int64).astype(U) << U(4 * k))
        assert np.array_equal(tot, H @ s[0]), "base-16 digit decomposition mismatch"
    return bad


if __name__ == "__main__":
    for kw in (dict(), dict(m=5, n=512, d=16, C=10, R=40), dict(m=2, lt=18, d=16)):
        bad = run(**kw)
        print(f"{kw or 'default'}: share-decryption failures {bad}/20")
        assert bad == 0
    print("OK: multi-key additive-share LWE decryption (with dropped hint bits and base-16 digits) matches M q~ exactly")
