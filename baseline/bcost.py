"""Cost model of the baseline: metered counters (bengine.py) + native calibrations (../calib).

Phase assignment (the point of this baseline)
  offline  GC garbling and table transfer, OT correlation generation. NO homomorphic encryption.
  online   everything that touches the query, including ALL threshold-HE work:
             * every 1-D read A.Enc(e): clients encrypt shares of the one-hot, server ct-pt products, threshold decrypt
             * Beaver-triple generation (one batch, three flights, at the start of the query)
           plus GC evaluation, OT, Beaver openings.

1-D read via HE (matrix a x n, K selectors, slots S, ncts = ceil(n/S) ciphertexts per selector):
  client (each)   encrypt its share of each selector: K*ncts;  clients 2..m also encrypt a mask rho_i: K*ceil(a/S)
  server          K*(ncts*(m-1)) adds, K*a*ncts (ct-pt + add) row dot-product pieces, slot sums by folding
                  (pair rows: 4 ct-pt + 1 rotation, halving; a-1 + log2(S/a) rotations in total; a rotation is
                  charged at the ct-ct+relin time of the calibration = a key-switch), + mask adds
  clients         partial decryption of ceil(a/S) cts per selector; P1 fuses; result: P1 holds dec, client i>=2 holds -rho_i
Time of a party with c cores = work / c (independent ciphertexts)."""
import math
from collections import defaultdict

import numpy as np

import _path  # noqa: F401
from costmodel import Cfg, load_cal, mean_meter, BPE   # noqa: F401


def pow2ceil(x):
    return 1 << max(0, (int(x) - 1).bit_length())


def he_reads(mt):
    out = []
    for k, v in mt["cnt"].items():
        if k.startswith("he1d|"):
            _, cat, a, n, K = k.split("|")
            out.append((cat, int(a), int(n), int(K), v))
    return out


def evaluate(res, he, gc, cfg):
    a_ = res["args"]
    m = a_["m"]
    mt = mean_meter(res)
    H, G = he(m), gc
    S, C = cfg.S, cfg.C
    slots = H["slots"]
    ct, ct2, pd = H["ct_bytes"], H["ct_mult_bytes"], H["pdec_bytes"]
    R = {}

    # ------------------------------ HE reads (online) -----------------------------------------------
    t_srv = defaultdict(float)
    t_cli = defaultdict(lambda: np.zeros(m))
    heb_cl = defaultdict(lambda: np.zeros(m))      # bytes per client (sent+received) by category
    heb_sv = defaultdict(float)
    n_reads = 0
    for cat, a, n, K, cnt in he_reads(mt):
        assert a <= slots
        ncts = math.ceil(n / slots)
        oc = 1                                      # a <= slots: one output ciphertext per selector
        rots = (a - 1) + math.ceil(math.log2(slots / a)) if a > 1 else math.log2(slots)
        srv_s = K * ((ncts * (m - 1)) * H["t_add"] + a * ncts * (H["t_ct_pt"] + H["t_add"])
                     + 2 * a * (H["t_ct_pt"] + H["t_add"]) + rots * H["t_ct_ct"] + (m - 1) * H["t_add"])
        t_srv["he_read_server"] += cnt * srv_s / S
        t_cli["he_encrypt"] += cnt * K * ncts * H["t_enc"] / C
        t_cli["he_encrypt"][1:] += cnt * K * oc * H["t_enc"] / C
        t_cli["he_threshold_decrypt"][1:] += cnt * K * oc * H["t_pdec_main"] / C
        t_cli["he_threshold_decrypt"][0] += cnt * K * oc * (H["t_pdec_lead"] + H["t_fusion"]) / C
        b = np.zeros(m)
        b += cnt * K * ncts * ct                                   # share ciphertexts -> server
        b[1:] += cnt * K * oc * ct                                 # Enc(rho_i) -> server
        b += cnt * K * oc * ct2                                    # product ciphertext <- server
        b[1:] += cnt * K * oc * pd                                 # partial decryptions -> P1
        b[0] += (m - 1) * cnt * K * oc * pd
        heb_cl[cat] += b
        heb_sv[cat] += cnt * K * (m * ncts * ct + (m - 1) * oc * ct + m * oc * ct2)
        n_reads += cnt
    # ------------------------------ Beaver triples via HE (online, one batch) -----------------------------
    tri = sum(v for k, v in mt["cnt"].items() if k.startswith("triples|"))
    nb = math.ceil(tri / slots)
    t_srv["he_triples_server"] = nb * (H["t_ct_ct"] + 2 * (m - 1) * H["t_add"]) / S
    t_cli["he_triples"] += nb * (3 * H["t_enc"] + H["t_pdec_main"]) / C
    heb_cl["he_triples"] += nb * (3 * ct + ct2 + pd)
    heb_sv["he_triples"] += nb * m * (3 * ct + ct2)
    he_flights = 3
    # ------------------------------ GC / OT --------------------------------------------------------------
    ands = sum(g["and_core"] + g["and_io"] for g in mt["gc"].values())
    ot_bits = sum(g["in_bits"] + g["mask_bits"] for g in mt["gc"].values())
    ot_bits_cl = ot_bits / m
    t_srv["ot_send"] = ot_bits / G["ot_per_s"] / S
    t_cli["gc_evaluate"][0] += ands / G["eval_rate"](C)
    t_cli["ot_receive"] += ot_bits_cl / G["ot_per_s"] / C
    t_cli["local_share_arith"] += sum(mt["tcli"].values())
    # ------------------------------ bytes (non-HE, from the meter) ---------------------------------------
    cl_on, cl_off = np.zeros(m), np.zeros(m)
    bycat = defaultdict(lambda: np.zeros(m))
    for k in set(mt["cs"]) | set(mt["cr"]):
        cat = k.split("|")[1]
        tot = np.array(mt["cs"].get(k, np.zeros(m))) + np.array(mt["cr"].get(k, np.zeros(m)))
        bycat[cat] += tot
        (cl_off if cat == "gc_tables" else cl_on).__iadd__(tot)
    sv_on = sv_off = 0.0
    svcat = defaultdict(float)
    for k in set(mt["ss"]) | set(mt["sr"]):
        cat = k.split("|")[1]
        v = mt["ss"].get(k, 0) + mt["sr"].get(k, 0)
        svcat[cat] += v
        if cat == "gc_tables":
            sv_off += v
        else:
            sv_on += v
    for cat, v in heb_cl.items():
        bycat[cat] += v
        cl_on += v
    for cat, v in heb_sv.items():
        svcat[cat] += v
        sv_on += v
    # ------------------------------ latency ---------------------------------------------------------------
    on_srv = sum(t_srv.values())
    on_cli = np.zeros(m)
    for v in t_cli.values():
        on_cli += v
    flights = sum(mt["fl"].values()) + he_flights
    t_lat = flights * cfg.rtt / 2
    t_bw = max(sv_on / cfg.sbw, float(np.max(cl_on)) / cfg.bw)
    t_comm = t_lat + t_bw
    L = on_srv + float(np.max(on_cli)) + t_comm
    R.update(
        latency_s=L, latency_compute_server_s=on_srv, latency_compute_client_s=float(np.max(on_cli)),
        latency_comm_s=t_comm, latency_rounds_s=t_lat, latency_transfer_s=t_bw, flights=flights, rtts=flights / 2,
        server_busy_s=on_srv, client_busy_s=[float(x) for x in on_cli],
        server_wait_peer_s=float(L - t_comm - on_srv), client_wait_peer_s=[float(L - t_comm - x) for x in on_cli],
        online_bytes_client=[float(x) for x in cl_on], online_bytes_server=float(sv_on),
        offline_gc_bytes_server=float(sv_off), offline_gc_bytes_client=[float(x) for x in cl_off],
        bytes_by_cat_client={k: [float(x) for x in v] for k, v in bycat.items()},
        bytes_by_cat_server={k: float(v) for k, v in svcat.items()},
        t_server_parts=dict(t_srv), t_client_parts={k: [float(x) for x in v] for k, v in t_cli.items()},
        ands=float(ands), gc_bytes=32 * float(ands), he_reads=n_reads, triples=tri,
        flights_by_cat={k.split("|")[1]: v for k, v in mt["fl"].items()},
        onehot_elems={str(k): v for k, v in mt["cnt"].items() if isinstance(k, str) and k.startswith("onehot_conv")},
        gc_by_circuit={n: dict(calls=g["calls"], ands=g["and_core"] + g["and_io"], core=g["and_core"], io=g["and_io"])
                       for n, g in mt["gc"].items()},
    )
    # ------------------------------ throughput ---------------------------------------------------------------
    srv_cpu = on_srv * S
    cli_cpu = float(np.max(on_cli)) * C
    qps_srv, qps_cli = S / max(srv_cpu, 1e-9), C / max(cli_cpu, 1e-9)
    qps_net = min(cfg.sbw / max(sv_on, 1), cfg.bw / max(float(np.max(cl_on)), 1))
    R.update(qps=min(qps_srv, qps_cli, qps_net), qps_server_cpu=qps_srv, qps_client_cpu=qps_cli, qps_network=qps_net,
             bottleneck=min([("server CPU", qps_srv), ("client CPU", qps_cli), ("network", qps_net)], key=lambda t: t[1])[0])
    # ------------------------------ offline (per query; GC + OT only) --------------------------------------------
    o = {}
    o["gc_garble_server_s"] = ands / G["garble_rate"](S)
    o["gc_table_bytes"] = 32 * ands
    o["rot_gen_s_server"] = ot_bits / G["ot_per_s"] / S
    o["rot_gen_s_client"] = ot_bits_cl / G["ot_per_s"] / C
    o["rot_bytes_per_client"] = ot_bits_cl * G["ot_bytes_per_ot"]
    o["offline_server_s"] = o["gc_garble_server_s"] + o["rot_gen_s_server"]
    o["offline_client_s"] = o["rot_gen_s_client"]
    o["offline_bytes_client"] = o["rot_bytes_per_client"]
    o["keygen_client_s"] = H["t_keygen_party"] + H["t_keygen_agg"]          # one-time, HE keygen is still needed
    o["keygen_bytes_client"] = H["pk_bytes"] + H["evk_bytes"] * 2
    R["offline"] = o
    return R
