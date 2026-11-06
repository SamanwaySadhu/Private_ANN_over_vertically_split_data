"""Cost model of the Panther baseline: metered counters (pengine.py) + native calibrations (../calib).

Parties: n = m+1 (server with S cores, m clients with C cores; client 1 queries the PIR, fuses threshold decryptions and
evaluates the garbled circuits; partial decryptions of the other clients run in parallel with client 1).

Online latency = server compute + client-1 compute + flights*RTT/2 + max-party bytes/BW   (no overlap, as in the other
protocols' models). GC tables and all OT correlations are offline.

HE times: the OpenFHE calibration (he_calib.json, BFV m-of-m threshold, N=8192, 4 x 60-bit towers) is scaled to Panther's own
parameter sets (phe.py) by the work ratio: linear ops (ct*pt, add, encrypt, partial decrypt, fusion) x N*log q, key-switch
(automorphism of the PIR query expansion) x N*L^2 (L = log q / 60). Ciphertext sizes are analytic (phe.py).
Wrap-bit correction OTs (paper Sec. 7.3.2) use silent (Ferret) correlated OT as in the paper: calibrated rate and 0.19 B/OT,
plus a 3-byte (l2 = 24 bit) message per OT online.

NOT charged (lower bound for Panther): HE key generation (one time), the paper's 1-bit H2A error fix (truncation, Sec. 7.2),
threshold-decryption smudging noise, one-time server database encoding."""
import json
import os
from collections import defaultdict

import numpy as np

import _path  # noqa: F401
from costmodel import Cfg, load_cal, CAL_DIR   # noqa: F401
from phe import DIST, PIR1, PIR2, ct_bytes, poly_bytes

CAL_N, CAL_LOGQ = 8192, 240


def he_for(he, n):
    for k in (2, 3, 4, 6, 8):
        if k >= n:
            return he(k)
    return he(8)


def ferret():
    g = json.load(open(os.path.join(CAL_DIR, "gc_calib.json")))["ot"]["ferret_correlated_ot_128bit"]
    return g["ot_per_s"], g["bytes_total_per_ot"]


def scaled(H, par, logq=None):
    """Per-operation times (s) of calibration set H scaled to parameter set par (optionally at modulus logq)."""
    lq = logq or par["logq"]
    lin = par["N"] * lq / (CAL_N * CAL_LOGQ)
    L, Lc = lq / 60.0, CAL_LOGQ / 60.0
    ks = par["N"] * L * L / (CAL_N * Lc * Lc)
    return dict(ct_pt=H["t_ct_pt"] * lin, add=H["t_add"] * lin, enc=H["t_enc"] * lin, pdec=H["t_pdec_main"] * lin,
                fusion=H["t_fusion"] * lin, ks=H["t_ct_ct"] * ks)


def mean_meters(res):
    ms = res["secure"]["meters"]
    out = {"sent": defaultdict(float), "recv": defaultdict(float), "fl": defaultdict(float), "cnt": defaultdict(float)}
    for mt in ms:
        for f in ("sent", "recv"):
            for k, v in mt[f].items():
                out[f][k] = out[f][k] + np.array(v) / len(ms)
        for f in ("fl", "cnt"):
            for k, v in mt[f].items():
                out[f][k] += v / len(ms)
    out["gc"] = {n_: {k: v / len(ms) for k, v in g.items()} for n_, g in ms[0]["gc"].items()}
    for mt in ms[1:]:
        for n_, g in mt["gc"].items():
            for k, v in g.items():
                out["gc"][n_][k] += v / len(ms)
    out["shape"] = ms[0]["shape"]
    return out


def evaluate(res, he, gc, cfg):
    a = res["args"]
    m, n = a["m"], a["m"] + 1
    mt = mean_meters(res)
    sh = mt["shape"]
    H = he_for(he, n)
    G, S, C = gc, cfg.S, cfg.C
    sD, s1, s2 = scaled(H, DIST), scaled(H, PIR1), scaled(H, PIR2)
    ands = sum(g["ands"] for g in mt["gc"].values())
    ot_bits = sum(g["in_bits"] + g["mask_bits"] for g in mt["gc"].values())
    wrap_ots = mt["cnt"]["wrap_ots"]
    # ---- bytes -----------------------------------------------------------------------------------------------
    on, off = np.zeros(n), np.zeros(n)
    bycat = defaultdict(lambda: np.zeros(n))
    for k in set(mt["sent"]) | set(mt["recv"]):
        _, cat = k.split("|")
        tot = np.array(mt["sent"].get(k, np.zeros(n))) + np.array(mt["recv"].get(k, np.zeros(n)))
        bycat[cat] += tot
        (off if cat == "gc_tables" else on).__iadd__(tot)
    # ---- server compute (online), all independent ciphertext ops spread over S cores -------------------------------
    d, B, P, Rb, n1, n2 = sh["d"], sh["B"], sh["P"], sh["Rb"], sh["n1"], sh["n2"]
    ct_t, ct_p = sh["dist_cts_t"], sh["dist_cts_pts"]
    t_dist = d * (ct_t + ct_p) * (sD["ct_pt"] + sD["add"]) + (ct_t + ct_p) * sD["enc"]
    t_expand = B * (n1 * (s1["ks"] + 2 * s1["add"]) + n2 * (s2["ks"] + 2 * s2["add"]))
    t_dim1 = B * P * (Rb * (s1["ct_pt"] + s1["add"]) + n2 * s1["enc"])
    t_dim2 = B * P * 2 * n2 * (s2["ct_pt"] + s2["add"])
    t_srv = {"he_distance": t_dist / S, "pir_expand": t_expand / S, "pir_dim1": t_dim1 / S, "pir_dim2": t_dim2 / S,
             "ot_send": ot_bits / G["ot_per_s"] / S}
    # ---- client compute -------------------------------------------------------------------------------------
    pairs = B * P
    di = -(-d // m)
    t_c1 = {"encrypt_query": di * sD["enc"] / C,
            "pir_query_encrypt": B * (s1["enc"] + s2["enc"]) / C,
            "threshold_decrypt_dist": (ct_t + ct_p) * (sD["pdec"] + sD["fusion"]) / C,
            "threshold_decrypt_pir": pairs * (2 * (s2["pdec"] + s2["fusion"]) + (s1["pdec"] + s1["fusion"])) / C,
            "gc_evaluate": ands / G["eval_rate"](C), "ot_receive": ot_bits / m / G["ot_per_s"] / C}
    fus_d = (ct_t + ct_p) * sD["fusion"] / C                  # fusion work happens at client 1 only
    fus_p = pairs * (2 * s2["fusion"] + s1["fusion"]) / C
    t_cl = dict(t_c1, pir_query_encrypt=0.0, gc_evaluate=0.0,
                threshold_decrypt_dist=t_c1["threshold_decrypt_dist"] - fus_d,
                threshold_decrypt_pir=t_c1["threshold_decrypt_pir"] - fus_p)
    on_srv, on_c1 = sum(t_srv.values()), sum(t_c1.values())
    flights = sum(mt["fl"].values())
    t_lat = flights * cfg.rtt / 2
    t_bw = max(on[0] / cfg.sbw, float(np.max(on[1:])) / cfg.bw)
    R = dict(latency_s=on_srv + on_c1 + t_lat + t_bw, latency_compute_server_s=on_srv, latency_compute_client_s=on_c1,
             latency_rounds_s=t_lat, latency_transfer_s=t_bw, latency_comm_s=t_lat + t_bw, flights=flights, rtts=flights / 2,
             online_bytes_server=float(on[0]), online_bytes_client=[float(x) for x in on[1:]],
             bytes_by_cat={k: [float(x) for x in v] for k, v in bycat.items() if k != "gc_tables"},
             ands=float(ands), gc_bytes=32 * float(ands), t_server_parts=t_srv, t_c1_parts=t_c1, t_cl_parts=t_cl,
             gc_by_circuit={k: dict(calls=g["calls"], ands=g["ands"], core=g["and_core"], io=g["and_io"]) for k, g in mt["gc"].items()},
             flights_by_cat={k.split("|")[1]: v for k, v in mt["fl"].items()}, wrap_ots=wrap_ots, shape=sh,
             cuckoo_failed=mt["cnt"]["cuckoo_failed"])
    # ---- offline (per query) -------------------------------------------------------------------------------
    f_rate, f_bytes = ferret()
    o = {}
    o["gc_garble_server_s"] = ands / G["garble_rate"](S)
    o["gc_table_bytes"] = 32 * ands
    o["rot_gen_s_server"] = ot_bits / G["ot_per_s"] / S
    o["rot_gen_s_client"] = ot_bits / m / G["ot_per_s"] / C
    o["rot_bytes_per_client"] = ot_bits / m * G["ot_bytes_per_ot"]
    o["wrap_cot_s_server"] = wrap_ots / f_rate / S
    o["wrap_cot_s_client"] = wrap_ots / m / f_rate / C
    o["wrap_cot_bytes_per_client"] = wrap_ots / m * f_bytes
    o["table_transfer_s"] = o["gc_table_bytes"] / min(cfg.bw, cfg.sbw)
    o["offline_server_s"] = o["gc_garble_server_s"] + o["rot_gen_s_server"] + o["wrap_cot_s_server"]
    o["offline_client_s"] = o["rot_gen_s_client"] + o["wrap_cot_s_client"]
    o["offline_total_latency_s"] = o["offline_server_s"] + o["table_transfer_s"]
    o["offline_bytes_client"] = o["rot_bytes_per_client"] + o["wrap_cot_bytes_per_client"]
    o["shuffle_s"] = 0.0                                     # index-map shuffle of coefficient-encoded plaintexts: free
    R["offline"] = o
    return R
