"""Excel: performance breakdown of the BASELINE (no LSH / Lagrange / offline HE) for SIFT1M, m = 8, E = 32/64/128, LAN only.
Two core configurations: 448 cores for the server and for every client (same as the other workbooks) and the baseline's own
default (server 64 cores, each client 8 cores)."""
import json
import os
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import _path  # noqa: F401
from bcost import Cfg, evaluate, load_cal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "SIFT1M_m8_baseline_breakdown.xlsx")
GB, MB, TB = 1e9, 1e6, 1e12
Es, m = (32, 64, 128), 8
CFGS = {"448 cores server + each client": Cfg(0.1, 10000, server_cores=448, client_cores=448),
        "baseline default: server 64 cores, client 8 cores": Cfg(0.1, 10000)}
he, gc = load_cal()
HDR = PatternFill("solid", fgColor="DDE6F3")
wb = Workbook()
first = [True]


def sheet(name, header, rows, widths=None, height=62):
    ws = wb.active if first[0] else wb.create_sheet(name)
    first[0] = False
    ws.title = name
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True); c.fill = HDR; c.alignment = Alignment(wrap_text=True, vertical="top")
    for r in rows:
        ws.append(r)
    for i in range(1, len(header) + 1):
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(i, 15)
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = height
    return ws


runs = {}
for E in Es:
    f = os.path.join(HERE, "results", f"base_sift_N1000000_m{m}_E{E}.json")
    if os.path.exists(f):
        r = json.load(open(f))
        runs[E] = dict(res=r, ev={k: evaluate(r, he, gc, c) for k, c in CFGS.items()})

# ---------------- Summary
hdr = ["cores", "m", "E", "Tb", "recall@10 (secure, 1000 queries)", "recall@10 plain hnswlib (same graph)", "upper-phase moves / query (mean)", "GC AND gates / query", "GC tables (TB)",
       "OT bytes / client (TB)", "HE 1-D reads / query", "HE-generated Beaver triples / query",
       "OFFLINE compute Server (s)", "OFFLINE compute each client (s)",
       "ONLINE compute Server (s)", "ONLINE compute C1 (s)", "ONLINE compute other client (s)",
       "ONLINE sent+recv per client, C1 (GB)", "ONLINE sent+recv per client, other (GB)", "ONLINE sent+recv Server (GB)",
       "ONLINE message flights", "ONLINE round trips", "ONLINE LAN comm time (s)", "ONLINE latency LAN (s)", "ONLINE latency (h)"]
rows = []
for cname in CFGS:
    for E, R in runs.items():
        x, a, o = R["ev"][cname], R["res"]["accuracy"], R["ev"][cname]["offline"]
        rows.append([cname, m, E, 2 * E, a["recall_secure_vs_float_gt"], a["recall_hnswlib_vs_quantized_gt"], a["mean_upper_moves"], x["ands"], o["gc_table_bytes"] / TB,
                     o["rot_bytes_per_client"] / TB, x["he_reads"], x["triples"], o["offline_server_s"], o["offline_client_s"],
                     x["server_busy_s"], x["client_busy_s"][0], x["client_busy_s"][1], x["online_bytes_client"][0] / GB, x["online_bytes_client"][1] / GB,
                     x["online_bytes_server"] / GB, x["flights"], x["rtts"], x["latency_comm_s"], x["latency_s"], x["latency_s"] / 3600])
sheet("Summary", hdr, rows, {1: 40}, 90)

# ---------------- one-time + offline
rows = []
for E, R in runs.items():
    sb, sz = R["res"]["server_build"]["times"], R["res"]["server_build"]["sizes"]
    o = R["ev"][list(CFGS)[0]]["offline"]
    rows.append([m, E, sb["hnsw_build"], sb["graph_import"], sb["flatten_tables"], sb["server_total"], o["keygen_client_s"], o["keygen_bytes_client"] / MB, sz["U"], str(sz["layer_nodes"]),
                 sz["flattened_total_bytes"] / MB])
sheet("OneTime_Preproc", ["m", "E", "Server HNSW build (s)", "Server graph import (s)", "Server flatten tables (s)", "Server total (s)", "Each client HE keygen (s)",
                          "Each client keygen sent (MB)", "rows U of the upper tables", "nodes per layer", "server tables (MB)"], rows, {10: 50}, 62)
rows = []
for cname in CFGS:
    for E, R in runs.items():
        o = R["ev"][cname]["offline"]
        rows.append([cname, m, E, "GC garbling", o["gc_garble_server_s"], 0.0, o["gc_table_bytes"] / GB, 0.0])
        rows.append([cname, m, E, "OT correlations", o["rot_gen_s_server"], o["rot_gen_s_client"], 0.0, o["rot_bytes_per_client"] / GB])
        rows.append([cname, m, E, "TOTAL", o["offline_server_s"], o["offline_client_s"], o["gc_table_bytes"] / GB, o["rot_bytes_per_client"] / GB])
sheet("Offline_per_query", ["cores", "m", "E", "component", "Server compute (s)", "each client compute (s)", "GC tables Server -> C1 (GB)", "OT bytes per client (GB)"], rows, {1: 40, 4: 22}, 62)
rows = []
for E, R in runs.items():
    for n, g in R["ev"][list(CFGS)[0]]["gc_by_circuit"].items():
        rows.append([m, E, n, g["calls"], g["ands"], g["io"], g["io"] / max(1, g["ands"]), 32 * g["ands"] / GB])
sheet("GC_by_circuit", ["m", "E", "circuit", "calls / query", "AND gates", "of which I/O wrapper", "wrapper share", "table size (GB)"], rows, {3: 22}, 48)

# ---------------- online compute / comm
rows = []
for cname in CFGS:
    for E, R in runs.items():
        x = R["ev"][cname]
        for k in list(x["t_server_parts"]) + [k for k in x["t_client_parts"] if k not in x["t_server_parts"]]:
            c = x["t_client_parts"].get(k)
            rows.append([cname, m, E, k, x["t_server_parts"].get(k, 0.0), c[0] if c else 0.0, c[1] if c else 0.0])
        rows.append([cname, m, E, "BUSY COMPUTE", x["server_busy_s"], x["client_busy_s"][0], x["client_busy_s"][1]])
sheet("Online_compute", ["cores", "m", "E", "component", "Server (s)", "C1 evaluator (s)", "each other client (s)"], rows, {1: 40, 4: 28}, 48)
rows = []
for E, R in runs.items():
    x = R["ev"][list(CFGS)[0]]
    for k in sorted(set(x["bytes_by_cat_client"]) | set(x["bytes_by_cat_server"])):
        if k == "gc_tables":
            continue
        v = x["bytes_by_cat_client"].get(k, [0, 0])
        rows.append([m, E, k, v[0] / MB, v[1] / MB, x["bytes_by_cat_server"].get(k, 0) / MB, x["flights_by_cat"].get(k, 0)])
    rows.append([m, E, "TOTAL ONLINE", x["online_bytes_client"][0] / MB, x["online_bytes_client"][1] / MB, x["online_bytes_server"] / MB, x["flights"]])
sheet("Online_comm", ["m", "E", "category", "C1 sent+recv (MB)", "each other client sent+recv (MB)", "Server sent+recv (MB)", "message flights"], rows, {3: 22}, 62)

# ---------------- comparison with the main-protocol variants (m = 8, 448 cores)
rows = []
tags = {"baseline (exact greedy upper layers, GC one-hot, HE online)": None, "per-node SECRET LSH (hash in GC)": "mask", "global public LSH (no GC hash)": "pub", "per-node PUBLIC LSH (no GC hash)": "node"}
for E in Es:
    for name, suf in tags.items():
        if suf is None:
            if E not in runs:
                continue
            R = runs[E]; x = R["ev"][list(CFGS)[0]]; a = R["res"]["accuracy"]
            rows.append([E, name, a["recall_secure_vs_float_gt"], x["ands"], x["ands"] * 32 / GB, x["server_busy_s"], x["client_busy_s"][0], x["client_busy_s"][1], x["flights"],
                         x["latency_comm_s"], x["latency_s"], max(x["online_bytes_client"]) / GB, x["online_bytes_server"] / GB, "online"])
        else:
            f = os.path.join(ROOT, "results", f"breakdown_sift_N1000000_m8_E{E}_{suf}.json")
            g = os.path.join(ROOT, "results", f"sift_N1000000_m8_E{E}_{suf}.json")
            if not (os.path.exists(f) and os.path.exists(g)):
                continue
            b, r = json.load(open(f)), json.load(open(g))
            on = b["tot_by"]
            rows.append([E, name, r["accuracy"]["recall_secure_vs_float_gt"], b["ands"], b["gc_total_bytes"] / GB, b["busy"]["S"], b["busy"]["C1"], b["busy"]["C2"], b["flights"],
                         b["comm_t"], b["latency"], max(on["C1"][0] + on["C1"][1], on["C2"][0] + on["C2"][1]) / GB, (on["S"][0] + on["S"][1]) / GB, "offline"])
sheet("Compare_all_variants", ["E", "variant", "recall@10 (that run's build, 1000 queries)", "GC AND gates / query", "GC tables (GB)", "ONLINE compute Server (s)", "ONLINE compute C1 (s)",
                               "ONLINE compute other client (s)", "ONLINE flights", "ONLINE LAN comm time (s)", "ONLINE latency LAN (s)", "ONLINE sent+recv per client, max (GB)",
                               "ONLINE sent+recv Server (GB)", "where HE work is done"], rows, {2: 52}, 76)

notes = [
    "BASELINE (folder baseline/): private HNSW without LSH, Lagrange one-hot or offline HE. Upper layers: exact greedy HNSW descent on secret-shared state (read neighbour row, read neighbour vectors, Beaver squared distances, GC argmin/move/descend). Shared ID -> shared one-hot: exact garbled circuit (n equality tests, every output bit shared through the all-client mask wrapper). 1-D read A e: threshold HE ONLINE (clients encrypt shares of e, server ct-pt products, threshold decryption to P1). Beaver triples: HE online. Offline = GC garbling + OT only.",
    "RUN: SIFT1M (1,000,000 x 128), m = 8, E = 32/64/128 (Tb = 2E, upper budget Tg = 3*top+3), driver bbench.py with nq = 1000 accuracy queries and nperf = 8 metered secure queries (identical to the plain emulation on all of them). LAN only: 10 Gbps per link, 0.1 ms RTT; latency = server + C1 compute + communication, no overlap.",
    "CORES: the Summary / compute sheets give two configurations: 448 cores for the server and for every client (consistent with the other workbooks) and the baseline's own default (server 64 cores, each client 8 cores). Communication and AND counts do not depend on the cores.",
    "MEASURED / EXACT: recall, graph and table sizes, server preprocessing time, every byte / flight count of GC, OT and Beaver, AND counts, HE read counts and shapes. MODELLED from calib/ (native OpenFHE and emp-tool micro-benchmarks): HE op times, GC garble / evaluate, OT, network. GC and HE are ideal functionalities inside the simulation.",
    "WHY IT IS SO EXPENSIVE: the exact GC one-hot (n equality tests with the all-client output wrapper) is ~97% of all GC cost; a 1M-element one-hot is ~4e8 AND gates. Its OT traffic (hundreds of GB to TB per client) dominates the online latency. A cheaper bit-output + B2A conversion would change the numbers by orders of magnitude but is not what the baseline specification asks for. HE rotations are charged at the ct x ct + relinearisation time (upper bound).",
    "In Compare_all_variants the main-protocol rows come from results/breakdown_*.json (448 cores for server and clients; HE only in preprocessing, so their online latency excludes HE and GC garbling). Recall of every run depends on its own random hnswlib build (see SIFT1M_recall_and_performance_ALL.xlsx).",
]
ws = wb.create_sheet("Notes", 0)
for n_ in notes:
    ws.append([n_])
ws.column_dimensions["A"].width = 170
for row in ws.iter_rows():
    for c in row:
        c.alignment = Alignment(wrap_text=True, vertical="top")
wb.save(OUT)
print("wrote", OUT, wb.sheetnames)
