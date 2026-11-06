"""Cost model of the Tiptoe baseline: metered counters (tengine.py) + native calibrations (../calib, calib/scan_calib.json).

Parties: server with S cores, m clients with C cores each; client 1 evaluates the garbled circuits.
ONLINE (after the clients entered their query):  GC argmin -> Beaver outer-product opening -> upload of the LWE ciphertext shares ->
  server scan -> GC decrypt+top-k -> output.   Latency = server compute + client-1 compute + flights*RTT/2 + max-party bytes/BW
  (no overlap, as in the other protocols' models).
OFFLINE (per query, query independent, the paper's 'query token' phase + the usual GC/triple preprocessing): RLWE tokens (one per
  client per query), A*s_i precomputation, GC garbling + OT correlations + table transfer, Beaver outer-product triples.
ONE-TIME: hint H = M*A at the server (batch job), centroid download at the clients.

Measured natively (calib/scan_bench.cpp): the server scan (int8 / int16 matrix x uint64 vector mod 2^64), the client's A*s_i.
The single-thread rate is scaled linearly to S server cores: this assumes memory bandwidth scales with cores (the measuring VM
saturates at ~2 cores, a real many-channel server does not).  Modelled: RLWE operation times (OpenFHE calibration scaled to the
paper's N=2048 / 38-bit parameters by N*log q), GC/OT (calib), network.  Sizes are analytic.
NOT charged (lower bound for Tiptoe): RLWE key generation, noise flooding, the paper's Enc2 plaintext-encoding of H (done once per
corpus, kept pre-NTT'ed)."""
import json
import math
import os
from collections import defaultdict

import numpy as np

import _path  # noqa: F401
from costmodel import Cfg, load_cal, CAL_DIR   # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))
CAL_N, CAL_LOGQ = 8192, 240


def he_for(he, n):
    for k in (2, 3, 4, 6, 8):
        if k >= n:
            return he(k)
    return he(8)


def scan_cal():
    j = json.load(open(os.path.join(HERE, "calib", "scan_calib.json")))
    return dict(int8_Bps=j["scan_int8"]["1"]["GBps"] * 1e9, int16_Bps=j["scan_int16"]["1"]["GBps"] * 1e9,
                mac_ps=j["lwe_mask"]["1"]["Gmac_per_s"] * 1e9)


def ferret():
    g = json.load(open(os.path.join(CAL_DIR, "gc_calib.json")))["ot"]["ferret_correlated_ot_128bit"]
    return g["ot_per_s"], g["bytes_total_per_ot"]


def scaled(H, N, logq):
    lin = N * logq / (CAL_N * CAL_LOGQ)
    return dict(ct_pt=H["t_ct_pt"] * lin, add=H["t_add"] * lin, enc=H["t_enc"] * lin, dec=H["t_pdec_main"] * lin)


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
    m = a["m"]
    n = m + 1
    mt = mean_meters(res)
    sh = mt["shape"]
    G, S, C = gc, cfg.S, cfg.C
    K = scan_cal()
    Hr = he_for(he, 2)                                   # token RLWE: client <-> server, single key
    Hm = he_for(he, n)                                   # triples: threshold HE among the clients
    sR = scaled(Hr, sh["rlwe_n"], sh["rlwe_logq"])
    slots = Hm["slots"]
    ands = sum(g["ands"] for g in mt["gc"].values())
    ot_bits = sum(g["in_bits"] + g["mask_bits"] for g in mt["gc"].values())
    # ---- bytes -------------------------------------------------------------------------------------------------
    on, off = np.zeros(n), np.zeros(n)
    bycat = defaultdict(lambda: np.zeros(n))
    for k in set(mt["sent"]) | set(mt["recv"]):
        ph, cat = k.split("|")
        tot = np.array(mt["sent"].get(k, np.zeros(n))) + np.array(mt["recv"].get(k, np.zeros(n)))
        if ph == "online":
            bycat[cat] += tot
            on += tot
        else:
            off += tot
    # ---- online compute ------------------------------------------------------------------------------------------
    Cc, d, Rr, limbs = sh["C"], sh["d"], sh["mc"], sh["limbs"]
    scan_rank_B = Cc * Rr * d + m * (Cc * d + Cc) * 8                # int8 matrix + summing the m uploaded ciphertext vectors
    scan_id_B = (limbs + 1) * Rr * Cc * 2
    t_srv = {"scan_rank": scan_rank_B / K["int8_Bps"] / S, "scan_id": scan_id_B / K["int16_Bps"] / S,
             "ot_send": ot_bits / G["ot_per_s"] / S}
    t_loc = (3 * Cc * d + Cc * d) / 1e9 / C                           # outer-product combine + adding D*q~_i (assumed 1 Gop/s/core)
    t_c1 = {"gc_evaluate": ands / G["eval_rate"](C), "ot_receive": ot_bits / m / G["ot_per_s"] / C, "local_ring_ops": t_loc}
    t_cl = dict(t_c1, gc_evaluate=0.0)
    on_srv, on_c1 = sum(t_srv.values()), sum(t_c1.values())
    flights = sum(v for k, v in mt["fl"].items() if k.startswith("online|"))
    t_lat = flights * cfg.rtt / 2
    t_bw = max(on[0] / cfg.sbw, float(np.max(on[1:])) / cfg.bw)
    R = dict(latency_s=on_srv + on_c1 + t_lat + t_bw, latency_compute_server_s=on_srv, latency_compute_client_s=on_c1,
             latency_rounds_s=t_lat, latency_transfer_s=t_bw, latency_comm_s=t_lat + t_bw, flights=flights, rtts=flights / 2,
             online_bytes_server=float(on[0]), online_bytes_client=[float(x) for x in on[1:]],
             bytes_by_cat={k: [float(x) for x in v] for k, v in bycat.items()},
             ands=float(ands), gc_bytes=32 * float(ands), t_server_parts=t_srv, t_c1_parts=t_c1, t_cl_parts=t_cl,
             gc_by_circuit={k: dict(calls=g["calls"], ands=g["ands"], core=g["and_core"], io=g["and_io"]) for k, g in mt["gc"].items()},
             flights_by_cat={k.split("|")[1]: v for k, v in mt["fl"].items() if k.startswith("online|")}, shape=sh,
             cluster_fill=mt["cnt"]["cluster_fill"])
    # ---- offline, per query -------------------------------------------------------------------------------------------
    o = {}
    keep = 0.5 if sh["drop_low"] else 1.0
    tok_cts = sh["tok_cts_rank"] + sh["tok_cts_id"]
    ops = tok_cts * sh["lwe_n"] * keep                                # ct*pt mult-adds per client token (digits x chunks x n columns)
    o["token_server_s"] = m * ops * (sR["ct_pt"] + sR["add"]) / S
    o["token_client_s"] = (sh["lwe_n"] * sR["enc"] + tok_cts * keep * sR["dec"]) / C
    o["lwe_mask_client_s"] = (Cc * d + Cc) * sh["lwe_n"] / K["mac_ps"] / C              # A s_i  (query independent)
    tok_up = sh["lwe_n"] * sh["ct_bytes"]
    tok_dn = tok_cts * sh["ct_bytes"] * keep
    o["token_bytes_client"] = tok_up + tok_dn
    o["token_transfer_s"] = max(m * (tok_up + tok_dn) / cfg.sbw, (tok_up + tok_dn) / cfg.bw)
    o["gc_garble_server_s"] = ands / G["garble_rate"](S)
    o["gc_table_bytes"] = 32 * ands
    o["rot_gen_s_server"] = ot_bits / G["ot_per_s"] / S
    o["rot_gen_s_client"] = ot_bits / m / G["ot_per_s"] / C
    o["rot_bytes_per_client"] = ot_bits / m * G["ot_bytes_per_ot"]
    o["table_transfer_s"] = o["gc_table_bytes"] / min(cfg.bw, cfg.sbw)
    tri = mt["cnt"]["triples"]
    nb = math.ceil(tri / slots)
    o["triples"] = tri
    o["triple_server_s"] = nb * (Hm["t_ct_ct"] + 2 * (n - 1) * Hm["t_add"]) / S
    o["triple_client_s"] = nb * (3 * Hm["t_enc"] + Hm["t_pdec_main"]) / C
    o["triple_bytes_client"] = nb * (3 * Hm["ct_bytes"] + Hm["ct_mult_bytes"] + Hm["pdec_bytes"])
    o["offline_server_s"] = o["token_server_s"] + o["gc_garble_server_s"] + o["rot_gen_s_server"] + o["triple_server_s"]
    o["offline_client_s"] = o["token_client_s"] + o["lwe_mask_client_s"] + o["rot_gen_s_client"] + o["triple_client_s"]
    o["offline_bytes_client"] = o["token_bytes_client"] + o["rot_bytes_per_client"] + o["triple_bytes_client"]
    o["offline_total_latency_s"] = (o["token_server_s"] + o["token_client_s"] + o["lwe_mask_client_s"] + o["token_transfer_s"] +
                                    o["gc_garble_server_s"] + o["rot_gen_s_server"] + o["table_transfer_s"] +
                                    o["triple_server_s"] + o["triple_client_s"])
    # ---- one-time ---------------------------------------------------------------------------------------------------
    o["setup_hint_macs"] = (Rr * Cc * d + (limbs + 1) * Rr * Cc) * sh["lwe_n"]
    o["setup_hint_server_s"] = o["setup_hint_macs"] / K["mac_ps"] / S
    o["setup_hint_bytes"] = (Rr + (limbs + 1) * Rr) * sh["lwe_n"] * 8
    o["setup_centroid_download_bytes"] = Cc * d
    R["offline"] = o
    return R
