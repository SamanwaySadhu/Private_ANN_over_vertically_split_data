"""Per-party breakdown of the baseline:  python breakdown.py results/base_sift_N1000000_m4_E64.json [rtt_ms bw_mbps]
Writes results/BREAKDOWN_<tag>.md (default LAN 10 Gbps / 0.1 ms, server 64 cores, clients 8 cores)."""
import json
import os
import sys

import _path  # noqa: F401
from bcost import Cfg, evaluate, load_cal

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
    m, a = r["args"]["m"], r["args"]
    tm, sz = r["server_build"]["times"], r["server_build"]["sizes"]
    o = x["offline"]
    L = [f"# {r['tag']}: per-party breakdown of the baseline (rtt {rtt} ms, {bw:g} Mbps; server 64 cores, each client 8 cores; m={m}, C1 = GC evaluator)\n",
         "Baseline: exact greedy upper layers with secret-shared distances (no LSH), exact GC one-hot conversion, threshold HE used "
         "**online** for every 1-D read and for Beaver-triple generation. Offline = GC garbling + OT only. Counts (ANDs, reads, flights, "
         "bytes of GC/OT/Beaver) are exact for the executed protocol; HE/GC/OT times are modelled from calib/.\n",
         "## 1. One-time preprocessing\n", "| party | component | time |", "|---|---|---|",
         f"| Server | HNSW build (hnswlib) | {fmt_t(tm['hnsw_build'])} |", f"| Server | graph import | {fmt_t(tm['graph_import'])} |",
         f"| Server | flatten tables (upper rows + layer-0 matrices) | {fmt_t(tm['flatten_tables'])} |",
         f"| Server | **total (measured)** | **{fmt_t(tm['server_total'])}** |",
         f"| each client | HE threshold keygen (modelled) | {fmt_t(o['keygen_client_s'])}, {fmt_b(o['keygen_bytes_client'])} |\n",
         f"Server tables: {fmt_b(sz['flattened_total_bytes'])} (U = {sz['U']:,} upper rows, layer sizes {sz['layer_nodes']}).\n",
         "## 2. Per-query offline phase (modelled)\n", "| component | Server | each client |", "|---|---|---|",
         f"| GC garbling ({x['ands']:,.0f} AND gates) | {fmt_t(o['gc_garble_server_s'])} | - |",
         f"| OT correlations | {fmt_t(o['rot_gen_s_server'])} | {fmt_t(o['rot_gen_s_client'])} |",
         f"| **total** | **{fmt_t(o['offline_server_s'])}** | **{fmt_t(o['offline_client_s'])}** |\n",
         f"GC tables to C1: **{fmt_b(o['gc_table_bytes'])}**; OT bytes per client: {fmt_b(o['rot_bytes_per_client'])}.\n",
         "| circuit | calls | ANDs | of which wrapper (I/O) | size |", "|---|---|---|---|---|"]
    for n, g in x["gc_by_circuit"].items():
        L.append(f"| {n} | {g['calls']:.0f} | {g['ands']:,.0f} | {g['io']:,.0f} | {fmt_b(32 * g['ands'])} |")
    L += ["\n## 3. Online phase (per query)\n", "### 3a. Compute\n", "| component | Server | C1 | other clients |", "|---|---|---|---|"]
    keys = list(x["t_server_parts"]) + [k for k in x["t_client_parts"] if k not in x["t_server_parts"]]
    for k in keys:
        s = x["t_server_parts"].get(k)
        c = x["t_client_parts"].get(k)
        L.append(f"| {k} | {fmt_t(s) if s is not None else '-'} | {fmt_t(c[0]) if c else '-'} | {fmt_t(c[1]) if c else '-'} |")
    L.append(f"| **busy compute** | **{fmt_t(x['server_busy_s'])}** | **{fmt_t(x['client_busy_s'][0])}** | **{fmt_t(x['client_busy_s'][1])}** |\n")
    L += ["### 3b. Communication (sent + received)\n", "| category | each client (max) | server |", "|---|---|---|"]
    for k in sorted(set(x["bytes_by_cat_client"]) | set(x["bytes_by_cat_server"])):
        if k == "gc_tables":
            continue
        L.append(f"| {k} | {fmt_b(max(x['bytes_by_cat_client'].get(k, [0])))} | {fmt_b(x['bytes_by_cat_server'].get(k, 0))} |")
    L.append(f"| **total online** | **{fmt_b(max(x['online_bytes_client']))}** | **{fmt_b(x['online_bytes_server'])}** |\n")
    L.append(f"Rounds: **{x['flights']:.0f} flights = {x['rtts']:.0f} round trips**; {x['he_reads']:.0f} HE 1-D reads, {x['triples']:,.0f} HE-generated Beaver triples. "
             f"Communication time {fmt_t(x['latency_comm_s'])} (rounds {fmt_t(x['latency_rounds_s'])}, transfer {fmt_t(x['latency_transfer_s'])}).\n")
    L.append(f"**Online latency (server + C1 compute + communication, no overlap): {fmt_t(x['latency_s'])}.** "
             f"Server idle {fmt_t(x['latency_s'] - x['server_busy_s'])}, C1 idle {fmt_t(x['latency_s'] - x['client_busy_s'][0])}.\n")
    ac = r["accuracy"]
    L.append(f"## 4. Accuracy\n\nrecall@10 vs float ground truth {ac['recall_secure_vs_float_gt']:.4f} (plaintext exact-greedy HNSW {ac['recall_exact_greedy_hnsw_vs_float_gt']:.4f}, "
             f"hnswlib {ac['recall_hnswlib_vs_quantized_gt']:.4f}); upper phase unfinished in {ac['upper_unfinished_rate']:.1%} of queries, "
             f"mean {ac['mean_upper_moves']:.1f} moves; secure == plain emulation on {r['secure']['identical']}/{r['secure']['nperf']} sampled queries.\n")
    out = os.path.join(HERE, "results", f"BREAKDOWN_{r['tag']}.md")
    open(out, "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
