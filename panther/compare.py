"""Comparison table: Panther baseline (this folder) next to whatever else exists for the same dataset, N and m:
main protocol (results/<dataset>_N*_m*_E64_mask.json), exact-greedy baseline (baseline/results), HNSecW-style (hnsecw/results).
    python compare.py  -> results/COMPARE.md   (LAN 10 Gbps/0.1 ms and WAN 100 Mbps/80 ms; server 64 cores, clients 8)
Panther rows are emitted for every panther/results/panther_*.json; the other protocols' rows only if their result file exists."""
import glob
import json
import os
import sys

import _path  # noqa: F401
from pcost import Cfg, evaluate as ev_p, load_cal
from breakdown import fmt_b, fmt_t

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HE, GC = load_cal()


def other_rows(a, net, rtt, bw, name):
    rows = []
    E = 64
    mf = os.path.join(ROOT, "results", f"{a['dataset']}_N{a['N']}_m{a['m']}_E{E}_mask.json")
    bf = os.path.join(ROOT, "baseline", "results", f"base_{a['dataset']}_N{a['N']}_m{a['m']}_E{E}.json")
    hf = os.path.join(ROOT, "hnsecw", "results", f"hnsecw_{a['dataset']}_N{a['N']}_m{a['m']}_E{E}.json")
    if os.path.exists(mf):
        from costmodel import evaluate as ev_main
        mr = json.load(open(mf))
        kf = mf.replace("/sift_", "/kernel_sift_")
        if os.path.exists(kf):
            mr["server_kernel_s"] = json.load(open(kf))
            mr["server_compute_by_threads"] = mr["server_compute_by_threads"] or mr["server_kernel_s"]
        x = ev_main(mr, HE, GC, Cfg(rtt, bw, None, 64, 8, "packed"))
        rows.append((f"main (E={E})", mr["accuracy"]["recall_secure_vs_float_gt"], x, x["offline"]["offline_server_s"]))
    for f, label, modname, pre in ((bf, "exact-greedy baseline", "bcost", "baseline"), (hf, "HNSecW-style", "hcost", "hnsecw")):
        if os.path.exists(f):
            sys.path.insert(0, os.path.join(ROOT, pre))
            for mod in ("_path", "bcost", "hcost"):
                sys.modules.pop(mod, None)
            mod = __import__(modname)
            r = json.load(open(f))
            x = mod.evaluate(r, HE, GC, mod.Cfg(rtt, bw))
            off = x["offline"].get("offline_total_latency_s", x["offline"]["offline_server_s"])
            rows.append((f"{label} (E={E})", r["accuracy"]["recall_secure_vs_float_gt"], x, off))
            sys.path.pop(0)
    return rows


def main():
    L = ["# Panther baseline vs the other protocols (per query)\n",
         "Panther: clustering ANNS, shuffled coefficient-encoded database, cuckoo batch PIR, PIR-to-shares, GC top-k selection networks, "
         "adapted to a vertically split query (see README). Offline column of Panther = GC garbling + OT + GC table transfer; there is no "
         "per-query reshuffle and no Beaver triple. Other protocols' offline column is as defined in their own cost models.\n",
         "| config | net | protocol | recall@10 | online latency | online comm / client | online comm / server | rounds (RTT) | offline latency | offline comm / client |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for f in sorted(glob.glob(os.path.join(HERE, "results", "panther_*.json"))):
        r = json.load(open(f))
        a = r["args"]
        cfgname = f"{a['dataset']} N={a['N']:,} m={a['m']}"
        for net, (rtt, bw) in (("LAN", (0.1, 10000)), ("WAN", (80, 100))):
            for name, rec, x, off in other_rows(a, net, rtt, bw, "") if True else []:
                L.append(f"| {cfgname} | {net} | {name} | {rec:.3f} | {fmt_t(x['latency_s'])} | {fmt_b(max(x['online_bytes_client']))} | "
                         f"{fmt_b(x['online_bytes_server'])} | {x['rtts']:.0f} | {fmt_t(off)} | {fmt_b(x['offline']['offline_bytes_client'])} |")
            x = ev_p(r, HE, GC, Cfg(rtt, bw))
            o = x["offline"]
            L.append(f"| {cfgname} | {net} | **Panther (u={a['u']}, t={a['t']})** | {r['accuracy']['recall_secure_vs_float_gt']:.3f} | {fmt_t(x['latency_s'])} | "
                     f"{fmt_b(max(x['online_bytes_client']))} | {fmt_b(x['online_bytes_server'])} | {x['rtts']:.0f} | "
                     f"{fmt_t(o['offline_total_latency_s'])} | {fmt_b(o['offline_bytes_client'])} |")
    open(os.path.join(HERE, "results", "COMPARE.md"), "w").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
