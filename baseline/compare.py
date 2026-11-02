"""Baseline vs the main (LSH + Lagrange + HE-in-preprocessing 'mask') protocol on matching configurations.
python compare.py   ->  results/COMPARE.md   (LAN 10 Gbps / 0.1 ms and WAN 100 Mbps / 80 ms; server 64 cores, clients 8 cores)"""
import glob
import json
import os

import _path  # noqa: F401
from bcost import Cfg, evaluate, load_cal
from breakdown import fmt_b, fmt_t
from costmodel import evaluate as evaluate_main

HERE = os.path.dirname(os.path.abspath(__file__))
HE, GC = load_cal()


def main():
    L = ["# Baseline vs main protocol (per query)\n",
         "Main = LSH upper layers + Lagrange one-hot + HE-generated correlations in preprocessing (`--mode mask` results of the parent directory). "
         "Baseline = exact greedy upper layers + GC one-hot + HE online. Same graph parameters (M=8, d=128, same k, E).\n"]
    rows = []
    for f in sorted(glob.glob(os.path.join(HERE, "results", "base_*.json"))):
        b = json.load(open(f))
        a = b["args"]
        mf = os.path.join(HERE, "..", "results", f"{a['dataset']}_N{a['N']}_m{a['m']}_E{a['E']}_mask.json")
        if not os.path.exists(mf):
            continue
        mr = json.load(open(mf))
        kf = mf.replace("/sift_", "/kernel_sift_")
        if os.path.exists(kf):
            mr["server_kernel_s"] = json.load(open(kf))
            mr["server_compute_by_threads"] = mr["server_compute_by_threads"] or mr["server_kernel_s"]   # only used for throughput
        for net, (rtt, bw) in (("LAN", (0.1, 10000)), ("WAN", (80, 100))):
            xb = evaluate(b, HE, GC, Cfg(rtt, bw))
            xm = evaluate_main(mr, HE, GC, Cfg(rtt, bw, None, 64, 8, "packed"))
            rows.append((a, net, b, mr, xb, xm))
    L.append("| config | net | protocol | recall@10 | online latency | online comm / client | online comm / server | rounds (RTT) | offline server | offline GC tables | offline comm / client |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for a, net, b, mr, xb, xm in rows:
        cfg = f"N={a['N']:,} m={a['m']} E={a['E']}"
        om, ob = xm["offline"], xb["offline"]
        L.append(f"| {cfg} | {net} | main | {mr['accuracy']['recall_secure_vs_float_gt']:.3f} | {fmt_t(xm['latency_s'])} | {fmt_b(max(xm['online_bytes_client']))} | "
                 f"{fmt_b(xm['online_bytes_server'])} | {xm['rtts']:.0f} | {fmt_t(om['offline_server_s'])} | {fmt_b(om['gc_table_bytes'])} | {fmt_b(om['offline_bytes_client'])} |")
        L.append(f"| {cfg} | {net} | **baseline** | {b['accuracy']['recall_secure_vs_float_gt']:.3f} | {fmt_t(xb['latency_s'])} | {fmt_b(max(xb['online_bytes_client']))} | "
                 f"{fmt_b(xb['online_bytes_server'])} | {xb['rtts']:.0f} | {fmt_t(ob['offline_server_s'])} | {fmt_b(ob['gc_table_bytes'])} | {fmt_b(ob['offline_bytes_client'])} |")
    open(os.path.join(HERE, "results", "COMPARE.md"), "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
