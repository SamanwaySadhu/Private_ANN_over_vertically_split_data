"""Per-party report:  python breakdown.py results/<tag>.json [rtt_ms bw_mbps]   (default LAN 10 Gbps / 0.1 ms; server 64 cores, clients 8)
Writes results/BREAKDOWN_<tag>.md"""
import json
import os
import sys

import _path  # noqa: F401
from pcost import Cfg, evaluate, load_cal

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
    L = [f"# {r['tag']}: Panther baseline, vertically split query (rtt {rtt} ms, {bw:g} Mbps; server 64 cores, clients 8; n = {a['m'] + 1} parties)\n",
         f"t={sz['t']} clusters (sizes {sz['cluster_min']}..{sz['cluster_max']}, padded to mc={sz['mc']}), u={sz['u']} retrieved, B={sz['B']} PIR buckets "
         f"({sh['Rb']} items/bucket, {sh['P']} plaintext polys/item, dims {sh['n1']}x{sh['n2']}), k'={sz['kprime']} bins. "
         f"{sh['B'] * sz['mc']:,} candidate points enter the exact top-k. Cuckoo failures per query: {x['cuckoo_failed']:.2f}.\n",
         "## Offline, per query (modelled)\n", "| component | time | bytes |", "|---|---|---|",
         f"| GC garbling ({x['ands']:,.0f} ANDs), server | {fmt_t(o['gc_garble_server_s'])} | tables to client 1: {fmt_b(o['gc_table_bytes'])} |",
         f"| OT correlations for GC inputs | server {fmt_t(o['rot_gen_s_server'])}, client {fmt_t(o['rot_gen_s_client'])} | {fmt_b(o['rot_bytes_per_client'])} / client |",
         f"| silent COTs for wrap-bit OTs ({x['wrap_ots']:,.0f}) | server {fmt_t(o['wrap_cot_s_server'])}, client {fmt_t(o['wrap_cot_s_client'])} | {fmt_b(o['wrap_cot_bytes_per_client'])} / client |",
         "| per-query table reshuffle | free (index map) | 0 |",
         f"| **offline latency (garble + OT + table transfer)** | **{fmt_t(o['offline_total_latency_s'])}** | **{fmt_b(o['offline_bytes_client'])} / client** |\n",
         "| circuit | calls | ANDs | wrapper share |", "|---|---|---|---|"]
    for n, g in x["gc_by_circuit"].items():
        L.append(f"| {n} | {g['calls']:.0f} | {g['ands']:,.0f} | {g['io'] / g['ands']:.0%} |")
    L += ["\n## Online, per query\n", "| category | server | each client (max) |", "|---|---|---|"]
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
