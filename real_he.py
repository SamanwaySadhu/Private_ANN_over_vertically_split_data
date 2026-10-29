"""
Real m-of-m threshold BFV (OpenFHE) backend for the 2-D read of Sec. 5.3.

Same interface as vsann.SimHE:
    begin_row(Ush)        -> row-selector state  (clients encrypt their shares of e_i)
    read2d(state, r, Vsh) -> fresh additive shares (m, F) of D_r[:, i, j]

Packing (avoids rotations and the O(U) ciphertext*ciphertext products of the
paper's literal formula):
  * per row t and radius r, a plaintext slot vector  D_r[t] = (D_r[f,t,b])_{f,b}
    (F fields x ncol columns, slot f*ncol+b);
  * the clients' selector shares of e_i are encrypted as U broadcast ciphertexts
    and summed by the server:      W_r = sum_t Enc(u_t) * ptxt(D_r[t])
    (ciphertext x plaintext only; one W_r per radius, reused by all probes);
  * a column probe is ONE ciphertext Enc(v) (replicated over fields) and one
    ciphertext x ciphertext product  W_r * Enc(v);
  * Enc2Share: server subtracts Enc(rho_i) of clients i>1, the key-share holders
    run threshold decryption to P1 only; the slot-vector shares are folded over
    b locally, which is linear, so the result is [D_ij] per field.
No plaintext of any ciphertext is ever visible to the server code.
"""
import numpy as np
import openfhe as ofhe

from vsann import P, matmul_mod


class OpenFHEThreshold:
    def __init__(self, mpc, Dtab, ring_dim=None, depth=1):
        self.mpc, self.m = mpc, mpc.m
        self.Dtab = Dtab                                   # list over r of (F,U,ncol)
        self.F, self.U, self.ncol = Dtab[0].shape
        self.live = self.F * self.ncol
        self.slots = 1
        while self.slots < self.live:
            self.slots *= 2           # OpenFHE batch size must be a power of two
        prm = ofhe.CCParamsBFVRNS()
        prm.SetPlaintextModulus(P)
        prm.SetMultiplicativeDepth(depth)
        prm.SetSecurityLevel(ofhe.SecurityLevel.HEStd_128_classic)
        prm.SetMultipartyMode(ofhe.MultipartyMode.NOISE_FLOODING_MULTIPARTY)
        if ring_dim:
            prm.SetRingDim(ring_dim)
        prm.SetBatchSize(self.slots)
        cc = ofhe.GenCryptoContext(prm)
        for f in (ofhe.PKESchemeFeature.PKE, ofhe.PKESchemeFeature.KEYSWITCH,
                  ofhe.PKESchemeFeature.LEVELEDSHE, ofhe.PKESchemeFeature.ADVANCEDSHE,
                  ofhe.PKESchemeFeature.MULTIPARTY):
            cc.Enable(f)
        self.cc = cc
        self.ring_dim = cc.GetRingDimension()
        self._keygen()
        self._pt_cache = {}
        self._W = {}

    # -- distributed key generation: no party ever holds the joint secret key --
    def _keygen(self):
        cc, m = self.cc, self.m
        kps = [cc.KeyGen()]
        for i in range(1, m):
            kps.append(cc.MultipartyKeyGen(kps[-1].publicKey))
        self.kps = kps
        self.pk = kps[-1].publicKey
        tag = self.pk.GetKeyTag()
        # joint relinearisation key
        ek = [cc.KeySwitchGen(kps[0].secretKey, kps[0].secretKey)]
        for i in range(1, m):
            ek.append(cc.MultiKeySwitchGen(kps[i].secretKey, kps[i].secretKey, ek[0]))
        acc = ek[0]
        for i in range(1, m):
            acc = cc.MultiAddEvalKeys(acc, ek[i], tag)
        parts = [cc.MultiMultEvalKey(kp.secretKey, acc, tag) for kp in kps]
        fin = parts[0]
        for p_ in parts[1:]:
            fin = cc.MultiAddEvalMultKeys(fin, p_, tag)
        cc.InsertEvalMultKey([fin])

    # -- helpers --
    def _enc(self, vec):
        pt = self.cc.MakePackedPlaintext([int(x) for x in vec])
        return self.cc.Encrypt(self.pk, pt)

    def _pt_row(self, r, t):
        key = (r, t)
        if key not in self._pt_cache:
            v = np.zeros(self.slots, np.int64)
            v[:self.live] = self.Dtab[r][:, t, :].reshape(-1)
            self._pt_cache[key] = self.cc.MakePackedPlaintext([int(x) for x in v])
        return self._pt_cache[key]

    def begin_row(self, Ush):
        """Ush (m,U): client i encrypts U broadcast ciphertexts of its shares."""
        cc, U, S = self.cc, self.U, self.slots
        cts = []
        for t in range(U):
            acc = None
            for i in range(self.m):
                c = self._enc(np.full(S, Ush[i, t]))
                acc = c if acc is None else cc.EvalAdd(acc, c)
            cts.append(acc)
        self._W = {}
        self.mpc.stats["he_enc_row"] += U * self.m
        return cts

    def _W_r(self, cts, r):
        if r not in self._W:
            cc, acc = self.cc, None
            for t in range(self.U):
                term = cc.EvalMult(cts[t], self._pt_row(r, t))
                acc = term if acc is None else cc.EvalAdd(acc, term)
            self._W[r] = acc
            self.mpc.stats["he_ct_pt_mults"] += self.U
        return self._W[r]

    def read2d(self, cts, r, Vsh):
        cc, m, F, ncol, S = self.cc, self.m, self.F, self.ncol, self.slots
        W = self._W_r(cts, r)
        ctv = None
        for i in range(m):
            c = self._enc(np.pad(np.tile(Vsh[i], F), (0, S - self.live)))
            ctv = c if ctv is None else cc.EvalAdd(ctv, c)
        prod = cc.EvalMult(W, ctv)                         # ciphertext x ciphertext
        self.mpc.stats["he_ct_mults"] += 1
        rho = [self.mpc.rint(S) for _ in range(m - 1)]     # clients 2..m
        out = prod
        for rr in rho:
            out = cc.EvalSub(out, self._enc(rr))
        lead = cc.MultipartyDecryptLead([out], self.kps[0].secretKey)
        mains = [cc.MultipartyDecryptMain([out], kp.secretKey) for kp in self.kps[1:]]
        pt = cc.MultipartyDecryptFusion(lead + [c for mn in mains for c in mn])
        pt.SetLength(S)
        v1 = np.mod(np.array(pt.GetPackedValue(), dtype=np.int64), P)
        slot_sh = np.stack([v1] + rho)                     # (m, F*ncol) additive shares
        self.mpc.stats["he_threshold_decrypt"] += 1
        return np.mod(slot_sh[:, :self.live].reshape(m, F, ncol).sum(-1), P)


if __name__ == "__main__":
    import time
    from vsann import MPC
    import sys
    m, F, U, ncol = 3, 4, int(sys.argv[1]) if len(sys.argv) > 1 else 20, 68
    mpc = MPC(m, seed=1)
    rng = np.random.default_rng(0)
    Dtab = [rng.integers(0, P, size=(F, U, ncol)).astype(np.int64) for _ in range(2)]
    t0 = time.time()
    he = OpenFHEThreshold(mpc, Dtab)
    print(f"keygen+setup {time.time() - t0:.1f}s ring_dim={he.ring_dim}")
    i, j = U - 3, 33
    ei, ej = np.zeros(U, np.int64), np.zeros(ncol, np.int64)
    ei[i] = 1
    ej[j] = 1
    t0 = time.time()
    st = he.begin_row(mpc.share(ei))
    print(f"begin_row {time.time() - t0:.1f}s")
    for r in (0, 1):
        t0 = time.time()
        out = he.read2d(st, r, mpc.share(ej))
        got = mpc.reveal(out)
        ok = np.array_equal(got, Dtab[r][:, i, j] % P)
        print(f"radius {r}: read2d {time.time() - t0:.2f}s correct={ok}")
