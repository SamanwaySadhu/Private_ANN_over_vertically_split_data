"""HE parameter sets of Panther (Table 6 of the paper) and the structural quantities derived from them.
Sizes are analytic (polys * N * log2 q / 8). Operation times are scaled from the OpenFHE calibration in ../calib
(see pcost.py). The m clients hold the secret keys as an m-of-m threshold sharing (one joint public key per parameter
set); the server never sees a secret key. Client 1 queries the PIR, fuses partial decryptions and evaluates the GCs.

  DIST  distance computation (Sec. 7.3):  N = 2048, q = 54 bit,                       p = 2^24
  PIR1  first PIR dimension:               N = 4096, q = 24+36+37 = 97 bit,             p = 2^13
  PIR2  second PIR dimension:              N = 4096, q' = 36+36+37 = 109 bit, p' = q1 = 2^24 (the first-dimension ciphertext,
        modulus-switched to q1 = 24 bit, is the plaintext of the second dimension, Sec. 5.2)
  responses are modulus-switched to the last 36-bit tower before they are sent."""
import math

DIST = dict(N=2048, logq=54, logp=24)
PIR1 = dict(N=4096, logq=97, logp=13, q1=24)
PIR2 = dict(N=4096, logq=109, logp=24, q_sw=36)


def poly_bytes(N, logq):
    return math.ceil(N * logq / 8)


def ct_bytes(par, logq=None):
    return 2 * poly_bytes(par["N"], logq or par["logq"])


def pir_shape(srv):
    """Per-bucket PIR geometry of the shuffled, cuckoo-encoded database."""
    prm = srv.prm
    _, content = srv.buckets()
    Rb = max(len(c) for c in content)                       # items (clusters) per bucket
    P = math.ceil(srv.mc * srv.W / PIR1["N"])               # plaintext polynomials per cluster (one word per coefficient)
    n1 = math.ceil(math.sqrt(Rb))
    n2 = math.ceil(Rb / n1)
    return dict(B=prm.B, Rb=Rb, P=P, n1=n1, n2=n2)
