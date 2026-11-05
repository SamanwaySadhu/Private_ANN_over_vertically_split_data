"""Three-way comparison on matching configurations (same dataset, N, m, E):
   main protocol (LSH + Lagrange + HE offline)  |  exact-greedy + GC one-hot baseline (baseline/)  |  HNSecW-style baseline (here)
python compare.py -> results/COMPARE.md  (LAN 10 Gbps/0.1 ms and WAN 100 Mbps/80 ms; server 64 cores, clients 8)
Rows are emitted for every hnsecw/results/hnsecw_*.json that has a main-protocol result; the exact-greedy baseline
column is added when baseline/results/base_<...>.json exists."""
import glob
import json
import os

import _path  # noqa: F401
from hcost import Cfg, evaluate as ev_h, load_cal
from breakdown import fmt_b, fmt_t
from costmodel import evaluate as ev_main

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HE, GC = load_cal()


def main():
    import sys
    sys.path.insert(0, os.path.join(ROOT, "baseline"))
    from bcost import evaluate as ev_base, Cfg as BCfg
    L = ["# Main vs exact-greedy baseline vs HNSecW-style baseline (per query)\n",
         "HNSecW-style: per-layer shuffled secret-shared tables among server + m clients, oblivious fixed-step search, no LSH. "
         "Offline column includes the per-query joint reshuffle (a lower bound, see README). Single-query protocol: one reshuffle per query.\n",
         "| config | net | protocol | recall@10 | online latency | online comm / client | online comm / server | rounds (RTT) | offline latency | offline comm / client |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for f in sorted(glob.glob(os.path.join(HERE, "results", "hnsecw_*.json"))):
        h = json.load(open(f))
        a = h["args"]
        mf = os.path.join(ROOT, "results", f"{a['dataset']}_N{a['N']}_m{a['m']}_E{a['E']}_mask.json")
        bf = os.path.join(ROOT, "baseline", "results", f"base_{a['dataset']}_N{a['N']}_m{a['m']}_E{a['E']}.json")
        mr = json.load(open(mf)) if os.path.exists(mf) else None
        if mr is not None:
            kf = mf.replace("/sift_", "/kernel_sift_")
            if os.path.exists(kf):
                mr["server_kernel_s"] = json.load(open(kf))
                mr["server_compute_by_threads"] = mr["server_compute_by_threads"] or mr["server_kernel_s"]
        br = json.load(open(bf)) if os.path.exists(bf) else None
        cfgname = f"{a['dataset']} N={a['N']:,} m={a['m']} E={a['E']}"
        for net, (rtt, bw) in (("LAN", (0.1, 10000)), ("WAN", (80, 100))):
            if mr is not None:
                xm = ev_main(mr, HE, GC, Cfg(rtt, bw, None, 64, 8, "packed"))
                om = xm["offline"]
                L.append(f"| {cfgname} | {net} | main | {mr['accuracy']['recall_secure_vs_float_gt']:.3f} | {fmt_t(xm['latency_s'])} | {fmt_b(max(xm['online_bytes_client']))} | "
                         f"{fmt_b(xm['online_bytes_server'])} | {xm['rtts']:.0f} | {fmt_t(om['offline_server_s'])} | {fmt_b(om['offline_bytes_client'])} |")
            if br is not None:
                xb = ev_base(br, HE, GC, BCfg(rtt, bw))
                ob = xb["offline"]
                L.append(f"| {cfgname} | {net} | exact-greedy baseline | {br['accuracy']['recall_secure_vs_float_gt']:.3f} | {fmt_t(xb['latency_s'])} | {fmt_b(max(xb['online_bytes_client']))} | "
                         f"{fmt_b(xb['online_bytes_server'])} | {xb['rtts']:.0f} | {fmt_t(ob['offline_server_s'])} | {fmt_b(ob['offline_bytes_client'])} |")
            xh = ev_h(h, HE, GC, Cfg(rtt, bw))
            oh = xh["offline"]
            L.append(f"| {cfgname} | {net} | **HNSecW-style** | {h['accuracy']['recall_secure_vs_float_gt']:.3f} | {fmt_t(xh['latency_s'])} | {fmt_b(max(xh['online_bytes_client']))} | "
                     f"{fmt_b(xh['online_bytes_server'])} | {xh['rtts']:.0f} | {fmt_t(oh['offline_total_latency_s'])} | {fmt_b(oh['offline_bytes_client'])} |")
    open(os.path.join(HERE, "results", "COMPARE.md"), "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
