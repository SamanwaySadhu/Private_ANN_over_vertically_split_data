"""Per-party report:  python breakdown.py results/<tag>.json [rtt_ms bw_mbps]   (default LAN 10 Gbps / 0.1 ms; server 64 cores, clients 8)
Writes results/BREAKDOWN_<tag>.md"""
import json
import os
import sys

import _path  # noqa: F401
from tcost import Cfg, evaluate, load_cal

HERE = os.path.dirname(os.path.abspath(__file__))


def fmt_b(x):
    for u, d in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if x >= d:
            return f"{x / d:.2f} {u}"
    return f"{x:.0f} B"


def fmt_t(x):
    if x < 1:
        return f"{x * 1e3:.0f} ms"
    if x < 120:
        return f"{x:.1f} s"
    if x < 7200:
        return f"{x / 60:.1f} min"
    return f"{x / 3600:.1f} h"


def main():
    path = sys.argv[1]
    rtt, bw = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) > 3 else (0.1, 10000.0)
    r = json.load(open(path))
    he, gc = load_cal()
    x = evaluate(r, he, gc, Cfg(rtt, bw))
    a, o, sh = r["args"], x["offline"], x["shape"]
    sz = r["server_build"]["sizes"]
    L = [f"# {r['tag']}: Tiptoe baseline, vertically split query (rtt {rtt} ms, {bw:g} Mbps; server 64 cores, clients 8; server + {a['m']} clients)\n",
         f"C={sz['C']} clusters (sizes {sz['cluster_min']}..{sz['cluster_max']}, mean {sz['cluster_mean']:.0f}, padded to mc={sz['mc']} rows; {sz['stored']:,} stored "
         f"vectors incl. {a['dup']:.0%} duplicated at cluster boundaries), {sz['bits']}-bit embeddings, plaintext ring 2^{sz['lt']}. "
         f"Ranking matrix {sz['rows']} x {sz['upload_dim']:,} (int8, {fmt_b(sz['M_bytes'])}), id/norm matrix {sz['id_rows']} x {sz['C']}.\n",
         "## One-time\n",
         f"- clients download the {sz['C']} public centroids: {fmt_b(o['setup_centroid_download_bytes'])}",
         f"- server hint H = M*A: {o['setup_hint_macs']:.2e} 64-bit MACs = {fmt_t(o['setup_hint_server_s'])} on 64 cores, hint size {fmt_b(o['setup_hint_bytes'])} (server-side only)\n",
         "## Offline, per query (query independent; the paper's 'query token' phase included)\n", "| component | time | bytes |", "|---|---|---|",
         f"| RLWE tokens: server ({a['m']} clients x {sh['tok_cts_rank'] + sh['tok_cts_id']} ct x {sh['lwe_n']} cols) | {fmt_t(o['token_server_s'])} | |",
         f"| RLWE tokens: client (encrypt {sh['lwe_n']} z-cts, decrypt) | {fmt_t(o['token_client_s'])} | {fmt_b(o['token_bytes_client'])} / client (transfer {fmt_t(o['token_transfer_s'])}) |",
         f"| client LWE mask A*s_i (query independent) | {fmt_t(o['lwe_mask_client_s'])} | |",
         f"| Beaver outer-product triple ({o['triples']:,.0f} elements) | server {fmt_t(o['triple_server_s'])}, client {fmt_t(o['triple_client_s'])} | {fmt_b(o['triple_bytes_client'])} / client |",
         f"| GC garbling ({x['ands']:,.0f} ANDs), server | {fmt_t(o['gc_garble_server_s'])} | tables to client 1: {fmt_b(o['gc_table_bytes'])} |",
         f"| OT correlations for GC inputs | server {fmt_t(o['rot_gen_s_server'])}, client {fmt_t(o['rot_gen_s_client'])} | {fmt_b(o['rot_bytes_per_client'])} / client |",
         f"| **offline latency** | **{fmt_t(o['offline_total_latency_s'])}** | **{fmt_b(o['offline_bytes_client'])} / client** |\n",
         "| circuit | calls | ANDs | wrapper share |", "|---|---|---|---|"]
    for n, g in x["gc_by_circuit"].items():
        L.append(f"| {n} | {g['calls']:.0f} | {g['ands']:,.0f} | {g['io'] / g['ands']:.0%} |")
    L += ["\n## Online, per query (after the query is entered)\n", "| category | server | each client (max) |", "|---|---|---|"]
    for k, v in sorted(x["bytes_by_cat"].items()):
        L.append(f"| {k} | {fmt_b(v[0])} | {fmt_b(max(v[1:]))} |")
    L.append(f"| **total** | **{fmt_b(x['online_bytes_server'])}** | **{fmt_b(max(x['online_bytes_client']))}** |\n")
    L.append("Compute (online): server " + ", ".join(f"{k} {fmt_t(v)}" for k, v in x["t_server_parts"].items()) + "; client 1 " +
             ", ".join(f"{k} {fmt_t(v)}" for k, v in x["t_c1_parts"].items()) + ".\n")
    L.append(f"{x['flights']:.0f} flights = {x['rtts']:.0f} round trips. Communication {fmt_t(x['latency_comm_s'])} "
             f"(rounds {fmt_t(x['latency_rounds_s'])}, transfer {fmt_t(x['latency_transfer_s'])}); compute server "
             f"{fmt_t(x['latency_compute_server_s'])}, client 1 {fmt_t(x['latency_compute_client_s'])}.\n")
    L.append(f"**Online latency: {fmt_t(x['latency_s'])}.**\n")
    ac = r["accuracy"]
    L.append(f"## Accuracy\n\nrecall@{ac['k']} vs float ground truth {ac['recall_secure_vs_float_gt']:.4f}; "
             f"{ac['frac_ge_0_9']:.1%} of queries >= 0.9; secure == plain emulation on {r['secure']['identical']}/{r['secure']['nperf']} sampled queries.\n")
    open(os.path.join(HERE, "results", f"BREAKDOWN_{r['tag']}.md"), "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
