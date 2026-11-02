"""Turns metered counters (bench.py) + native micro-benchmark calibrations (calib/*.json) into the
performance quantities reported in the private-ANN literature.

MEASURED here (real execution on this machine):  server 1-D-read matrix products, client-local
  share arithmetic, accuracy, server preprocessing, all message counts / byte counts / AND counts
  (which are exact functions of the executed protocol).
MODELLED from calibrations:  HE operation times (OpenFHE C++ micro-benchmarks), GC garble / evaluate
  and OT times (emp-tool micro-benchmarks), the network (latency + size/bandwidth).
Nothing below is invented: every constant comes from calib/*.json or from a stated protocol formula."""
import json
import math
import os
from collections import defaultdict

import numpy as np

BPE = 4
CAL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calib")


def load_cal(batch="8192"):
    """Calibrations from calib/*.json. HE ops are timed single-threaded (OMP=1); independent
    ciphertexts are processed on independent cores (task parallelism), so a party with c cores
    divides the op counts by c. GC/OT rates are the T=64 aggregate of independent pairs."""
    hj = json.load(open(os.path.join(CAL_DIR, "he_calib.json")))["full_run"]["configs"][batch]
    gj = json.load(open(os.path.join(CAL_DIR, "gc_calib.json")))

    def he(m):
        e = hj["by_m"][str(m)]
        ms, by = e["ms"], e["bytes"]
        return dict(slots=hj["num_slots"], ring_dim=hj["ring_dim"], log2q=hj["log2_q_bits"],
                    ct_bytes=by["ciphertext_fresh"], ct_mult_bytes=by["ciphertext_after_mult_relin"],
                    pdec_bytes=by["partial_decrypt_share_main"], pk_bytes=by["public_key"], evk_bytes=by["eval_mult_key"],
                    t_enc=ms["encrypt_pk"] / 1e3, t_add=ms["eval_add"] / 1e3, t_sub=ms["eval_sub"] / 1e3,
                    t_ct_pt=ms["eval_mult_ct_pt"] / 1e3, t_ct_ct=ms["eval_mult_ct_ct_relin"] / 1e3,
                    t_pdec_lead=ms["decrypt_lead"] / 1e3, t_pdec_main=ms["decrypt_main"] / 1e3,
                    t_fusion=ms["decrypt_fusion"] / 1e3, t_keygen_party=ms["keygen_per_party_max"] / 1e3,
                    t_keygen_agg=ms["keygen_aggregation"] / 1e3)
    par = {d["T"]: d for d in gj["gc_parallel_independent_pairs"]}
    g_core = par[64]["agg_garble_and_per_s_sum_of_thread_rates"] / 64
    e_core = par[64]["agg_eval_and_per_s_sum_of_thread_rates"] / 64
    gc = dict(garble_rate=lambda c: g_core * max(1, min(c, 64)) if c <= 64 else g_core * 64 * (c / 64),
              eval_rate=lambda c: e_core * max(1, c),
              ot_per_s=gj["ot"]["iknp_chosen_message_ot_128bit"]["ot_per_s"],
              rot_per_s=gj["ot"]["iknp_correlated_ot_128bit"]["ot_per_s"],
              ot_bytes_per_ot=gj["ot"]["iknp_correlated_ot_128bit"]["bytes_total_per_ot"],
              aes_ands=gj["aes128_and_gates"]["bristol_fashion_aes_128.txt"])
    return he, gc


def mean_meter(res):
    """Average the per-query meters (comm / AND counts are deterministic; times vary)."""
    ms = res["secure"]["meters"]
    out = {}
    for fld in ("cs", "cr", "ss", "sr", "fl", "tsrv", "tcli", "tsim", "cnt"):
        acc = defaultdict(float)
        for mt in ms:
            for k, v in mt[fld].items():
                acc[k] = acc[k] + (np.array(v) if isinstance(v, list) else v)
        out[fld] = {k: v / len(ms) for k, v in acc.items()}
    out["gc"] = ms[0]["gc"]
    out["gc_max"] = ms[0]["gc_max"]
    return out


class Cfg:
    def __init__(self, rtt_ms=0.1, bw_mbps=10000, server_bw_mbps=None, server_cores=64, client_cores=8,
                 he_enc="broadcast"):
        self.rtt = rtt_ms / 1e3
        self.bw = bw_mbps * 1e6 / 8                       # bytes/s per client link
        self.sbw = (server_bw_mbps or bw_mbps) * 1e6 / 8  # server link
        self.S, self.C = server_cores, client_cores
        self.he_enc = he_enc


def evaluate(res, he, gc, cfg):
    """Return a flat dict of performance numbers for one configuration."""
    a = res["args"]
    m, N, E, s = a["m"], a["N"], a["E"], a["s"]
    sz = res["server_build"]["sizes"]
    U = sz["U"]
    Tg, ncol = a["Tg"], sz["ncol"]
    mt = mean_meter(res)
    H = he(m)
    G = gc
    row_cts = U if cfg.he_enc == "broadcast" else math.ceil(U / H["slots"])
    probes = s * (4 + (ncol - sz["H"]))           # 2-D reads per upper iteration (4 hashed + sigma stash)
    R = {}

    # ------------------- bytes -------------------------------------------------------------
    cl_on = np.zeros(m); cl_off = np.zeros(m); sv_on = 0.0; sv_off = 0.0
    bycat = defaultdict(lambda: np.zeros(m))
    for k in set(mt["cs"]) | set(mt["cr"]):
        cat = k.split("|")[1]
        tot = np.array(mt["cs"].get(k, np.zeros(m))) + np.array(mt["cr"].get(k, np.zeros(m)))
        bycat[cat] += tot
        if cat == "gc_tables":
            cl_off += tot
        else:
            cl_on += tot
    svcat = defaultdict(float)
    for k in set(mt["ss"]) | set(mt["sr"]):
        cat = k.split("|")[1]
        v = mt["ss"].get(k, 0) + mt["sr"].get(k, 0)
        svcat[cat] += v
        if cat == "gc_tables":
            sv_off += v
        else:
            sv_on += v
    # HE traffic (broadcast row-selector encoding as in real_he.py)
    ct, ct2, pd = H["ct_bytes"], H["ct_mult_bytes"], H["pdec_bytes"]
    he_cl = np.zeros(m)
    he_cl += Tg * (row_cts * ct + probes * ct)                      # row selector + Enc(v)
    he_cl[1:] += Tg * probes * ct                             # Enc(rho_i), i>=2
    he_cl += Tg * probes * ct2                                # server -> client for partial decrypt
    he_cl[1:] += Tg * probes * pd                             # partial decryption shares ->P1
    he_cl[0] += (m - 1) * Tg * probes * pd
    he_sv = Tg * (m * (row_cts * ct + probes * ct) + (m - 1) * probes * ct + m * probes * ct2)
    cl_on += he_cl
    sv_on += he_sv
    bycat["he"] += he_cl
    svcat["he"] += he_sv

    # ------------------- compute (single party, all cores of that party) -------------------
    ands = sum(g["and_core"] + g["and_io"] for g in mt["gc"].values())
    ot_bits_per_client = sum(g["in_bits"] + g["mask_bits"] for g in mt["gc"].values()) / m
    garble_rate = G["garble_rate"](cfg.S)         # AND/s aggregate over S cores
    eval_rate = G["eval_rate"](cfg.C)
    t_srv = {}
    ks = res.get("server_kernel_s") or res["server_compute_by_threads"]
    t_srv["read1d_matmul"] = ks[_nearest(ks, cfg.S)]
    rot = 0.0 if cfg.he_enc == "broadcast" else s * 2 * math.sqrt(U) * H["t_ct_ct"]   # BSGS rotations (key-switch ~ ct*ct)
    t_srv["he_server"] = Tg * (rot + row_cts * (m - 1) * H["t_add"] + s * U * (H["t_ct_pt"] + H["t_add"])
                               + probes * (H["t_ct_ct"] + (2 * m - 2) * H["t_add"])) / cfg.S
    t_srv["ot_send"] = ot_bits_per_client * m / G["ot_per_s"] / cfg.S
    t_cli = defaultdict(lambda: np.zeros(m))
    t_cli["he_encrypt"] += Tg * (row_cts + probes) * H["t_enc"] / cfg.C
    t_cli["he_encrypt"][1:] += Tg * probes * H["t_enc"] / cfg.C
    t_cli["he_threshold_decrypt"][1:] += Tg * probes * H["t_pdec_main"] / cfg.C
    t_cli["he_threshold_decrypt"][0] += Tg * probes * (H["t_pdec_lead"] + H["t_fusion"]) / cfg.C
    t_cli["gc_evaluate"][0] += ands / eval_rate
    t_cli["ot_receive"] += ot_bits_per_client / G["ot_per_s"] / cfg.C
    loc = sum(v for k, v in mt["tcli"].items())
    t_cli["local_share_arith"] += loc
    t_on_srv = sum(t_srv.values())
    t_on_cli = np.zeros(m)
    for v in t_cli.values():
        t_on_cli += v
    # ------------------- network -----------------------------------------------------------
    flights = sum(mt["fl"].values())
    t_lat = flights * cfg.rtt / 2
    t_bw = max(sv_on / cfg.sbw, float(np.max(cl_on)) / cfg.bw)
    t_comm = t_lat + t_bw
    L = t_on_srv + float(np.max(t_on_cli)) + t_comm
    R.update(
        latency_s=L, latency_compute_server_s=t_on_srv, latency_compute_client_s=float(np.max(t_on_cli)),
        latency_comm_s=t_comm, latency_rounds_s=t_lat, latency_transfer_s=t_bw, flights=flights, rtts=flights / 2,
        server_busy_s=t_on_srv, client_busy_s=[float(x) for x in t_on_cli],
        server_wait_s=L - t_on_srv, client_wait_s=[float(L - x) for x in t_on_cli],
        wait_comm_s=t_comm, client_wait_peer_s=[float(L - t_comm - x) for x in t_on_cli],
        server_wait_peer_s=float(L - t_comm - t_on_srv),
        online_bytes_client=[float(x) for x in cl_on], online_bytes_server=float(sv_on),
        offline_gc_bytes_server=float(sv_off), offline_gc_bytes_client=[float(x) for x in cl_off],
        bytes_by_cat_client={k: [float(x) for x in v] for k, v in bycat.items()},
        bytes_by_cat_server={k: float(v) for k, v in svcat.items()},
        t_server_parts=t_srv, t_client_parts={k: [float(x) for x in v] for k, v in t_cli.items()},
        ands=float(ands), gc_bytes=32 * float(ands),
    )
    # ------------------- throughput (pipelined concurrent queries) ---------------------------
    cpu_srv = res["server_compute_by_threads"][_nearest(res["server_compute_by_threads"], 1)]
    loaded = [sum(v for v in mm["tsrv"].values()) for mm in res["secure"]["meters"]]
    cpu_srv_loaded = float(np.mean(loaded))                # 1-thread, machine fully busy
    he_srv_cpu = t_srv["he_server"] * cfg.S
    ot_srv_cpu = t_srv["ot_send"] * cfg.S
    srv_cpu = cpu_srv_loaded + he_srv_cpu + ot_srv_cpu
    cli_cpu = float(np.max(t_on_cli)) * cfg.C
    qps_srv = cfg.S / srv_cpu
    qps_cli = cfg.C / cli_cpu
    qps_net = min(cfg.sbw / max(sv_on, 1), cfg.bw / max(float(np.max(cl_on)), 1))
    R.update(qps_server_cpu=qps_srv, qps_client_cpu=qps_cli, qps_network=qps_net,
             qps=min(qps_srv, qps_cli, qps_net),
             bottleneck=min([("server CPU", qps_srv), ("client CPU", qps_cli), ("network", qps_net)],
                            key=lambda t: t[1])[0],
             server_cpu_s_per_query=srv_cpu, client_cpu_s_per_query=cli_cpu)
    # ------------------- offline (per query) ------------------------------------------------
    R["offline"] = offline_model(res, mt, H, G, cfg, U)
    return R


def _nearest(dct, T):
    ks = sorted(int(k) for k in dct)
    best = min(ks, key=lambda k: abs(math.log(k) - math.log(max(T, 1))))
    return str(best) if str(best) in dct else best


def offline_model(res, mt, H, G, cfg, U):
    a = res["args"]
    m, N, s = a["m"], a["N"], a["s"]
    d = res["server_build"]["sizes"]["A"]
    slots = H["slots"]
    prm_d = (d - 3) // s - 4
    out = {}
    # (1) garbled circuits
    ands = sum(g["and_core"] + g["and_io"] for g in mt["gc"].values())
    out["gc_garble_server_s"] = ands / G["garble_rate"](cfg.S)
    out["keygen_client_s"] = H["t_keygen_party"] + H["t_keygen_agg"]
    out["keygen_bytes_client"] = H["pk_bytes"] + H["evk_bytes"] * 2
    out["gc_table_bytes"] = 32 * ands
    ot_bits = sum(g["in_bits"] + g["mask_bits"] for g in mt["gc"].values())
    out["rot_gen_s_server"] = ot_bits / G["ot_per_s"] / cfg.S
    out["rot_gen_s_client"] = ot_bits / m / G["ot_per_s"] / cfg.C
    out["rot_bytes_per_client"] = ot_bits / m * G["ot_bytes_per_ot"]
    # (2) Beaver triples (threshold-HE batched generation: Enc(a_i), Enc(b_i), Enc(rho_i); ct*ct; threshold dec.)
    tri = sum(v for k, v in mt["cnt"].items() if k.startswith("triples|"))
    batches = math.ceil(tri / slots)
    out["triples"] = tri
    out["triple_client_s"] = batches * (3 * H["t_enc"] + H["t_pdec_main"]) / cfg.C
    out["triple_server_s"] = batches * (H["t_ct_ct"] + 2 * (m - 1) * H["t_add"]) / cfg.S
    out["triple_bytes_client"] = batches * (3 * H["ct_bytes"] + H["ct_mult_bytes"] + H["pdec_bytes"])
    # (3) read1d correlations (r, s, h = A r + s): server evaluates A.Enc(r) with packed ct-pt products
    Tb = a["Tb"] or 2 * a["E"]
    D0 = 2 * a["M"]
    spec = [(d, U, a["Tg"]), (prm_d + 1, N + 1, a["Tg"]), (2 * D0, N + 1, Tb), (prm_d + 1, N + 1, Tb * D0)]
    srv_s = 0.0; cli_s = 0.0; byt = 0.0
    for rows, n, cnt in spec:
        ncts = math.ceil(n / slots)
        srv_s += cnt * (rows * ncts * (H["t_ct_pt"] + H["t_add"]) + rows * math.log2(slots) * H["t_ct_ct"])
        cli_s += cnt * (ncts * H["t_enc"] + math.ceil(rows / slots) * H["t_pdec_main"])
        byt += cnt * (ncts * H["ct_bytes"] + math.ceil(rows / slots) * (H["ct_mult_bytes"] + H["pdec_bytes"]))
    out["read_corr_server_s"] = srv_s / cfg.S
    out["read_corr_client_s"] = cli_s / cfg.C
    out["read_corr_bytes_client"] = byt
    out["offline_server_s"] = out["gc_garble_server_s"] + out["rot_gen_s_server"] + out["triple_server_s"] + out["read_corr_server_s"]
    out["offline_client_s"] = out["rot_gen_s_client"] + out["triple_client_s"] + out["read_corr_client_s"]
    out["offline_bytes_client"] = out["rot_bytes_per_client"] + out["triple_bytes_client"] + out["read_corr_bytes_client"]
    return out
