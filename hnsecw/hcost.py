"""Cost model of the HNSecW-style baseline: metered counters (hengine.py) + native calibrations (../calib).

Parties: n = m+1 (server with S cores, m clients with C cores; client 1 evaluates the garbled circuits).

Online (everything after the query exists): GC evaluation + OT derandomisation, Beaver openings, address openings,
  the GC table transfer is offline. Latency = server compute + client-1 compute + flights*RTT/2 + max-party bytes/BW
  (no overlap, same as the other protocols' models).
Offline per query:
  * GC garbling + table transfer + OT correlations (as in baseline/bcost.py, n-party wrapper)
  * Beaver triples by threshold HE among n parties (calibration by_m, next available m >= n)
  * joint reshuffle of every table (the paper's single-query protocol reshuffles per query):
      every party j applies its own permutation to the full sharing; for each other party i this is a 2-party oblivious
      permutation of i's share (Waksman network, one 1-of-2 OT of a w-word row per switch, switches = R*ceil(log2 R) -
      2^ceil(log2 R) + 1). n(n-1) such runs per table. LOWER BOUND: the relabelling of pointer columns under the new
      permutations and the one-time dealing of the shared database are not charged (dealing is PRG-seeded, ~free)."""
import math
from collections import defaultdict

import numpy as np

import _path  # noqa: F401
from costmodel import Cfg, load_cal   # noqa: F401


def he_for(he, n):
    for k in (2, 3, 4, 6, 8):
        if k >= n:
            return he(k)
    return he(8)


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
    return out


def waksman_switches(R):
    p = max(1, math.ceil(math.log2(R)))
    return R * p - (1 << p) + 1


def evaluate(res, he, gc, cfg):
    a = res["args"]
    m, n = a["m"], a["m"] + 1
    mt = mean_meters(res)
    H, G = he_for(he, n), gc
    S, C = cfg.S, cfg.C
    slots = H["slots"]
    R = {}
    ands = sum(g["ands"] for g in mt["gc"].values())
    ot_bits = sum(g["in_bits"] + g["mask_bits"] for g in mt["gc"].values())
    tri = mt["cnt"]["triples"]
    # ---- bytes per party (sent + received), online vs offline ----------------------------------------
    on, off = np.zeros(n), np.zeros(n)
    bycat = defaultdict(lambda: np.zeros(n))
    for k in set(mt["sent"]) | set(mt["recv"]):
        _, cat = k.split("|")
        tot = np.array(mt["sent"].get(k, np.zeros(n))) + np.array(mt["recv"].get(k, np.zeros(n)))
        bycat[cat] += tot
        (off if cat == "gc_tables" else on).__iadd__(tot)
    # ---- compute ----------------------------------------------------------------------------------------
    t_srv = {"ot_send": ot_bits / G["ot_per_s"] / S}
    t_c1 = {"gc_evaluate": ands / G["eval_rate"](C), "ot_receive": ot_bits / m / G["ot_per_s"] / C}
    t_cl = {"ot_receive": ot_bits / m / G["ot_per_s"] / C}
    on_srv = sum(t_srv.values())
    on_c1 = sum(t_c1.values())
    flights = sum(mt["fl"].values())
    t_lat = flights * cfg.rtt / 2
    t_bw = max(on[0] / cfg.sbw, float(np.max(on[1:])) / cfg.bw)
    L = on_srv + on_c1 + t_lat + t_bw
    R.update(latency_s=L, latency_compute_server_s=on_srv, latency_compute_client_s=on_c1, latency_rounds_s=t_lat,
             latency_transfer_s=t_bw, latency_comm_s=t_lat + t_bw, flights=flights, rtts=flights / 2,
             online_bytes_server=float(on[0]), online_bytes_client=[float(x) for x in on[1:]],
             bytes_by_cat={k: [float(x) for x in v] for k, v in bycat.items() if k != "gc_tables"},
             ands=float(ands), gc_bytes=32 * float(ands), triples=tri, t_server_parts=t_srv, t_c1_parts=t_c1, t_cl_parts=t_cl,
             gc_by_circuit={k: dict(calls=g["calls"], ands=g["ands"], core=g["and_core"], io=g["and_io"]) for k, g in mt["gc"].items()},
             flights_by_cat={k.split("|")[1]: v for k, v in mt["fl"].items()})
    # ---- offline ------------------------------------------------------------------------------------------
    o = {}
    o["gc_garble_server_s"] = ands / G["garble_rate"](S)
    o["gc_table_bytes"] = 32 * ands
    o["rot_gen_s_server"] = ot_bits / G["ot_per_s"] / S
    o["rot_gen_s_client"] = ot_bits / m / G["ot_per_s"] / C
    o["rot_bytes_per_client"] = ot_bits / m * G["ot_bytes_per_ot"]
    nb = math.ceil(tri / slots)
    o["triple_server_s"] = nb * (H["t_ct_ct"] + 2 * (n - 1) * H["t_add"]) / S
    o["triple_client_s"] = nb * (3 * H["t_enc"] + H["t_pdec_main"]) / C
    o["triple_bytes_party"] = nb * (3 * H["ct_bytes"] + H["ct_mult_bytes"] + H["pdec_bytes"])
    # joint reshuffle of the tables (per query)
    shapes = res["server_build"]["sizes"]["tables"]
    ot_ps = G["ot_per_s"]
    run_ots = sum(waksman_switches(Rr) * math.ceil(32 * w / 128) for _, Rr, w in shapes)   # OTs of one 2-party permutation run
    run_bytes = run_ots * 48.0
    run_core_s = run_ots / ot_ps
    # n sequential steps (one per permuting party j); in step j party j runs (n-1) runs in parallel on its cores
    step_server = (n - 1) * run_core_s / S
    step_client = (n - 1) * run_core_s / C
    o["shuffle_compute_s"] = step_server + m * step_client
    o["shuffle_bytes_per_party"] = 2 * (n - 1) * run_bytes
    o["shuffle_bytes_total"] = n * (n - 1) * run_bytes
    o["shuffle_transfer_s"] = o["shuffle_bytes_per_party"] / min(cfg.bw, cfg.sbw) * 0.5   # sequential steps share the link
    o["shuffle_latency_s"] = o["shuffle_compute_s"] + o["shuffle_transfer_s"] + n * 2 * cfg.rtt
    o["offline_server_s"] = o["gc_garble_server_s"] + o["rot_gen_s_server"] + o["triple_server_s"] + step_server * 1
    o["offline_client_s"] = o["rot_gen_s_client"] + o["triple_client_s"] + (m * step_client + 0) / max(m, 1) * 1
    o["offline_total_latency_s"] = o["gc_garble_server_s"] + o["rot_gen_s_server"] + o["shuffle_latency_s"] + o["triple_server_s"] + o["triple_client_s"]
    o["offline_bytes_client"] = o["rot_bytes_per_client"] + o["triple_bytes_party"] + o["shuffle_bytes_per_party"]
    o["keygen_client_s"] = H["t_keygen_party"] + H["t_keygen_agg"]
    o["keygen_bytes_client"] = H["pk_bytes"] + H["evk_bytes"] * 2
    o["shuffle_tables"] = [(nm, Rr, w) for nm, Rr, w in shapes]
    o["table_bytes_per_party"] = sum(Rr * w * 4 for _, Rr, w in shapes)
    R["offline"] = o
    return R
