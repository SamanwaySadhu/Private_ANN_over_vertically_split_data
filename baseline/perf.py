"""Performance table of all baseline runs under several networks -> results/PERF.md"""
import glob, json, os
import _path  # noqa: F401
from bcost import Cfg, evaluate, load_cal
from breakdown import fmt_b, fmt_t

HERE = os.path.dirname(os.path.abspath(__file__))
HE, GC = load_cal()
NETS = {"LAN 10 Gbps / 0.1 ms": (0.1, 10000), "WAN 1 Gbps / 10 ms": (10, 1000), "WAN 100 Mbps / 80 ms": (80, 100)}
L = ["# Baseline performance, SIFT (per query; server 64 cores, each client 8 cores)\n",
     "| run | recall@10 | network | online latency | server compute | P1 compute | online comm / client | online comm / server | rounds (RTT) | HE reads |",
     "|---|---|---|---|---|---|---|---|---|---|"]
off = ["\n## Offline (per query, network-independent) and one-time\n",
       "| run | GC ANDs | GC tables to P1 | garbling (server) | OT (server / client) | OT bytes / client | server build (one-time) | HE keygen / client |",
       "|---|---|---|---|---|---|---|---|"]
key = lambda f: (json.load(open(f))["args"]["N"], json.load(open(f))["args"]["m"], json.load(open(f))["args"]["E"])
for f in sorted(glob.glob(os.path.join(HERE, "results", "base_*.json")), key=key):
    r = json.load(open(f))
    for i, (nn, (rtt, bw)) in enumerate(NETS.items()):
        x = evaluate(r, HE, GC, Cfg(rtt, bw))
        L.append(f"| {r['tag'] if i == 0 else ''} | {r['accuracy']['recall_secure_vs_float_gt']:.3f} | {nn} | {fmt_t(x['latency_s'])} | "
                 f"{fmt_t(x['latency_compute_server_s'])} | {fmt_t(x['latency_compute_client_s'])} | {fmt_b(max(x['online_bytes_client']))} | "
                 f"{fmt_b(x['online_bytes_server'])} | {x['rtts']:.0f} | {x['he_reads']:.0f} |")
    o = x["offline"]
    off.append(f"| {r['tag']} | {x['ands']:.3g} | {fmt_b(o['gc_table_bytes'])} | {fmt_t(o['gc_garble_server_s'])} | {fmt_t(o['rot_gen_s_server'])} / {fmt_t(o['rot_gen_s_client'])} | "
               f"{fmt_b(o['rot_bytes_per_client'])} | {fmt_t(r['server_build']['times']['server_total'])} | {fmt_t(o['keygen_client_s'])} |")
open(os.path.join(HERE, "results", "PERF.md"), "w").write("\n".join(L + off))
print("\n".join(L + off))
