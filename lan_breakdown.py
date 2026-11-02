"""LAN-only (10 Gbps, 0.1 ms) per-component breakdown: preprocessing and online, per party."""
from report import load_all, ev, fmt_t, fmt_b

RUNS = ["sift_N100000_m4_E64", "gist_N100000_m4_E64", "sift_N1000000_m4_E64", "gist_N1000000_m4_E64"]
R = load_all()
out = ["# LAN breakdown (10 Gbps, 0.1 ms RTT; server 64 cores, each client 8 cores)\n"]
for enc in ("broadcast", "packed"):
    out.append(f"\n## HE row selector: {enc}\n")
    for t in RUNS:
        r = R[t]; x = ev(r, 0.1, 10000, enc); o = x["offline"]; tm = r["server_build"]["times"]
        tp, tc = x["t_server_parts"], x["t_client_parts"]
        bc = x["bytes_by_cat_client"]; bs = x["bytes_by_cat_server"]
        out.append(f"\n### {t}\n")
        out.append("**Preprocessing (one-time, server, measured, 448 cores)**: " +
                   f"HNSW build {fmt_t(tm['hnsw_build'])}, graph import {fmt_t(tm['graph_import'])}, "
                   f"flatten + LSH + cuckoo tables {fmt_t(tm['flatten_tables'])}; total {fmt_t(tm['server_total'])}.\n")
        out.append("**Preprocessing (one-time, each client, modelled)**: HE threshold keygen " +
                   f"{fmt_t(o['keygen_client_s'])}, {fmt_b(o['keygen_bytes_client'])}.\n")
        out.append("| per-query offline component (modelled) | server | each client | note |\n|---|---|---|---|")
        out.append(f"| GC garbling | {fmt_t(o['gc_garble_server_s'])} | - | tables {fmt_b(o['gc_table_bytes'])} to P1 |")
        out.append(f"| OT extension (input labels) | {fmt_t(o['rot_gen_s_server'])} | {fmt_t(o['rot_gen_s_client'])} | {fmt_b(o['rot_bytes_per_client'])}/client |")
        out.append(f"| Beaver triples ({o['triples']:,.0f}) | {fmt_t(o['triple_server_s'])} | {fmt_t(o['triple_client_s'])} | {fmt_b(o['triple_bytes_client'])}/client |")
        out.append(f"| (r,s,h) read correlations | {fmt_t(o['read_corr_server_s'])} | {fmt_t(o['read_corr_client_s'])} | {fmt_b(o['read_corr_bytes_client'])}/client |")
        out.append(f"| **total** | **{fmt_t(o['offline_server_s'])}** | **{fmt_t(o['offline_client_s'])}** | {fmt_b(o['offline_bytes_client'])}/client |\n")
        out.append("| online component | server | P1 | other clients |\n|---|---|---|---|")
        for k, v in tp.items():
            out.append(f"| {k} | {fmt_t(v)} | - | - |")
        for k, v in tc.items():
            out.append(f"| {k} | - | {fmt_t(v[0])} | {fmt_t(v[1])} |")
        out.append(f"| network (flights {x['flights']:.0f}, transfer) | {fmt_t(x['latency_comm_s'])} | {fmt_t(x['latency_comm_s'])} | {fmt_t(x['latency_comm_s'])} |")
        out.append(f"| **busy compute** | **{fmt_t(x['server_busy_s'])}** | **{fmt_t(x['client_busy_s'][0])}** | **{fmt_t(x['client_busy_s'][1])}** |")
        out.append(f"| **end-to-end latency** | {fmt_t(x['latency_s'])} | | |")
        out.append(f"| wait (network / peer compute) | {fmt_t(x['wait_comm_s'])} / {fmt_t(x['server_wait_peer_s'])} | {fmt_t(x['wait_comm_s'])} / {fmt_t(x['client_wait_peer_s'][0])} | {fmt_t(x['wait_comm_s'])} / {fmt_t(x['client_wait_peer_s'][1])} |\n")
open("results/LAN_BREAKDOWN.md", "w").write("\n".join(out))
print("\n".join(out))
