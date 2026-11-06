"""Excel for the PER-NODE PUBLIC-LSH variant (no GC for the query hash): SIFT1M, m = 8, E = 32/64/128. LAN only."""
import json
import math
import os
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

GB, MB = 1e9, 1e6
BW, RTT = 10e9 / 8, 0.1e-3
OUT = sys.argv[1] if len(sys.argv) > 1 else "SIFT1M_m8_node_public_LSH_breakdown.xlsx"
Es, m, s, Tg = (32, 64, 128), 8, 6, 12
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


def load(tag):
    try:
        return dict(tag=tag, br=json.load(open(f"results/breakdown_{tag}.json")), res=json.load(open(f"results/{tag}.json")),
                    det=json.load(open(f"results/detail_{tag}.json")) if os.path.exists(f"results/detail_{tag}.json") else None)
    except FileNotFoundError:
        return None


runs = {E: load(f"sift_N1000000_m8_E{E}_node") for E in Es}
runs = {E: R for E, R in runs.items() if R}
other = {E: {"pub": load(f"sift_N1000000_m8_E{E}_pub"), "mask": load(f"sift_N1000000_m8_E{E}_mask")} for E in Es}

# ------------------------------------------------------------------ Summary
hdr = ["m", "E", "Tb", "recall@10 (secure, this build, 10,000 queries)", "recall@10 plain hnswlib (same build)", "hash error rate P(h_hat != h_true)",
       "keys outside the interpolation domain (rate)", "GC AND gates / query", "GC size / query (GB)", "Beaver triples / query", "read correlations / query",
       "PREPROC compute Server (s)", "PREPROC compute C1 (s)", "PREPROC compute other client (s)",
       "PREPROC sent Server (GB)", "PREPROC recv Server (GB)", "PREPROC sent C1 (GB)", "PREPROC recv C1 (GB)", "PREPROC sent other (GB)", "PREPROC recv other (GB)",
       "ONLINE compute Server (s)", "ONLINE compute C1 (s)", "ONLINE compute other client (s)",
       "ONLINE sent Server (GB)", "ONLINE recv Server (GB)", "ONLINE sent C1 (GB)", "ONLINE recv C1 (GB)", "ONLINE sent other (GB)", "ONLINE recv other (GB)",
       "ONLINE message flights", "ONLINE round trips", "ONLINE LAN comm time (s)", "ONLINE latency LAN (s)",
       "TOTAL sent Server (GB)", "TOTAL recv Server (GB)", "TOTAL sent C1 (GB)", "TOTAL recv C1 (GB)", "TOTAL sent other (GB)", "TOTAL recv other (GB)",
       "TOTAL communication, all parties (GB)"]
rows = []
for E, R in runs.items():
    b, a = R["br"], R["res"]["accuracy"]
    L = a["lsh"]
    offc = {p: sum(d.get(p, 0) for d in b["off_t"].values()) for p in ("S", "C1", "C2")}
    ot, ob, al = b["offtot"], b["tot_by"], b["allb"]
    rows.append([m, E, 2 * E, a["recall_secure_vs_float_gt"], a["recall_hnswlib_vs_quantized_gt"], L.get("hash_err", 0) / max(1, L.get("hash_total", 1)),
                 L.get("oor", 0) / max(1, L.get("hash_total", 1)), b["ands"], b["gc_total_bytes"] / GB, b["triples"], b["n_corr"],
                 offc["S"], offc["C1"], offc["C2"],
                 ot["S"][0] / GB, ot["S"][1] / GB, ot["C1"][0] / GB, ot["C1"][1] / GB, ot["C2"][0] / GB, ot["C2"][1] / GB,
                 b["busy"]["S"], b["busy"]["C1"], b["busy"]["C2"],
                 ob["S"][0] / GB, ob["S"][1] / GB, ob["C1"][0] / GB, ob["C1"][1] / GB, ob["C2"][0] / GB, ob["C2"][1] / GB,
                 b["flights"], b["flights"] / 2, b["comm_t"], b["latency"],
                 al["S"][0] / GB, al["S"][1] / GB, al["C1"][0] / GB, al["C1"][1] / GB, al["C2"][0] / GB, al["C2"][1] / GB,
                 sum(al[p][0] for p in al) / GB])
sheet("Summary", hdr, rows, {}, 90)

# ------------------------------------------------------------------ comparison with the other two variants
rows = []
for E in Es:
    for name, R in (("per-node PUBLIC LSH (this variant, no GC hash)", runs.get(E)), ("global public LSH (no GC hash)", other[E]["pub"]),
                    ("per-node SECRET LSH (hash in GC)", other[E]["mask"])):
        if not R:
            continue
        b, a = R["br"], R["res"]["accuracy"]
        al = b["allb"]
        rows.append([E, name, a["recall_secure_vs_float_gt"], b["ands"], b["gc_total_bytes"] / GB, b["triples"], b["n_corr"], b["busy"]["S"], b["busy"]["C1"], b["busy"]["C2"],
                     b["flights"], b["comm_t"], b["latency"], al["S"][0] / GB, al["C1"][0] / GB, al["C2"][0] / GB, sum(al[p][0] for p in al) / GB])
sheet("Compare_variants", ["E", "variant", "recall@10 (first 1000 queries of that run's build)", "GC AND gates / query", "GC size (GB)", "Beaver triples / query", "read correlations / query",
                           "ONLINE compute Server (s)", "ONLINE compute C1 (s)", "ONLINE compute other client (s)", "ONLINE flights", "ONLINE LAN comm time (s)", "ONLINE latency LAN (s)",
                           "TOTAL sent Server (GB)", "TOTAL sent C1 (GB)", "TOTAL sent other client (GB)", "TOTAL communication all parties (GB)"], rows, {2: 46}, 76)

# ------------------------------------------------------------------ one-time preprocessing
rows = []
for E, R in runs.items():
    sb, sz = R["br"]["server_build"], R["res"]["server_build"]["sizes"]
    rows.append([m, E, sb["hnsw_build"], sb["graph_import"], R["res"]["server_build"]["times"].get("node_params"), R["res"]["server_build"]["times"].get("node_dicts"), sb["server_total"],
                 R["br"]["kg"], R["br"]["kb"] / MB, sz.get("node_table_bytes", 0) / MB, sz["U"], str(sz.get("node_K")), sz.get("node_B"), sz["theta_bytes"] / MB])
sheet("OneTime_Preproc", ["m", "E", "Server HNSW build (s)", "Server graph import (s)", "Server per-node LSH parameters + key windows (s)", "Server directly addressed dictionaries (s)",
                          "Server total (s)", "Each client HE keygen (s)", "Each client keygen sent (MB)",
                          "PUBLIC LSH parameter table every client downloads once (MB per client: a int16, b, w, key offset)", "rows U of the upper table",
                          "key window K_r per radius (columns)", "quantisation precision B", "server table theta (MB)"], rows, {12: 28}, 120)


def comp_rows(key):
    return [[m, E, c] + [d.get(p, 0) for p in ("S", "C1", "C2")] for E, R in runs.items() for c, d in R["br"][key].items()]


def comm_rows(key):
    out = []
    for E, R in runs.items():
        for c, d in R["br"][key].items():
            g = lambda p, j: d[p][j] / MB if p in d else 0
            out.append([m, E, c, g("S", 0), g("S", 1), g("C1", 0), g("C1", 1), g("C2", 0), g("C2", 1)])
    return out


sheet("Preproc_compute", ["m", "E", "component", "Server (s)", "C1 evaluator (s)", "each other client (s)"], comp_rows("off_t"), {3: 44})
sheet("Online_compute", ["m", "E", "component", "Server (s)", "C1 evaluator (s)", "each other client (s)"], comp_rows("on_t"), {3: 70})
hc = ["m", "E", "component", "Server sent (MB)", "Server recv (MB)", "C1 sent (MB)", "C1 recv (MB)", "other client sent (MB)", "other client recv (MB)"]
sheet("Preproc_comm", hc, comm_rows("off_b"), {3: 34})
sheet("Online_comm", hc, comm_rows("on_b"), {3: 24})

# ------------------------------------------------------------------ the new part: the query hash, step by step
hh = ["E", "step", "what is computed", "calls / query", "client time / call, 448 cores (s)", "client time / call, 8 cores (s)", "client time / query, 448 cores (s)",
      "client time / query, 8 cores (s)", "sent per client / call (B)", "recv per client / call (B)", "sent per client / query (B)", "recv per client / query (B)",
      "flights / call", "flights / query", "offline per query (preprocessing)", "note"]
rows = []
for E, R in runs.items():
    det, br, res = R["det"], R["br"], R["res"]
    if det is None:
        continue
    cnt = res["secure"]["meters"][0]["cnt"]
    sz = res["server_build"]["sizes"]
    U, K, Bq = sz["U"], sz["node_K"], sz["node_B"]
    d = 128
    ob = br["on_b"]
    tot = dict(c448=0.0, c8=0.0, sent=0.0, recv=0.0, fl=0)

    def add(step, what, calls, t448, t8, sent_q, recv_q, fl_call, offline, note):
        rows.append([E, step, what, calls, t448, t8, t448 * calls, t8 * calls, sent_q / max(1, calls), recv_q / max(1, calls), sent_q, recv_q, fl_call, fl_call * calls, offline, note])
        tot["c448"] += t448 * calls; tot["c8"] += t8 * calls; tot["sent"] += sent_q; tot["recv"] += recv_q; tot["fl"] += fl_call * calls

    nq = det["node_q"]
    add("A. once per query", f"each client quantises its own {d // m} coordinates for ALL {U:,} rows x {s} radii: q_i[row,r] = floor(B * t_i), t_i = (<a_row,r^(i), x^(i)> + b)/w (public a,b,w)",
        1, nq["448"], nq["8"], 0, 0, 0, "none",
        f"{U * s * d // m / 1e6:.0f} M multiply-adds + {U * s / 1e6:.1f} M divisions per client; reads the public parameter table; purely local, no communication")
    sel = list(det["sel"].values())[0]
    calls = sel["calls"]
    sk = ob["beaver_sel"]["C2"]
    add("B. every upper iteration", f"private selection of the visited row's Q'_r: {s} Beaver dot products of length {U:,} (shared one-hot of the row x the clients' shares of Q'[row,r]; the mask of the one-hot is reused for all {s} radii)",
        calls, sel["448"]["open"] + sel["448"]["part"], sel["8"]["open"] + sel["8"]["part"], sk[0], sk[1], 1,
        f"{s * U:,} multiplication triples (HE) + {(1 + s) * U * 4 / MB:.1f} MB of mask shares per client",
        "open e-A (U values) and Q-B (s*U values) to all other clients; each client then does 2 multiply-adds per entry")
    add("C. every upper iteration", f"open tau_r = Q'_r - alpha_r for the {s} radii (upload; the server broadcasts tau)", calls, 0.0, 0.0,
        ob["lag_open"]["C2"][0], ob["lag_open"]["C2"][1], 2, "alpha shares", "masked opening hides Q'; one value per radius")
    for r in range(s):
        R_ = K[r] * Bq
        lg = det["lag"].get(str(R_))
        if lg:
            add(f"D{r}. every upper iteration", f"radius {r}: fused truncation + one-hot by Lagrange interpolation over R = K*B = {K[r]}*{Bq} = {R_:,} points: T(tau) table, T x [alpha powers], coefficient matrix", lg["calls"],
                lg["448"]["lag"], lg["8"]["lag"], 0, 0, 0, f"{R_ - 1:,} shared powers of alpha (HE, depth log2 R)", f"O(R^2) = {R_ * R_ / 1e6:.1f} M local field operations per client per call")
    bd = [v for k, v in det["bv"].items() if k.startswith("beaver_dict:")][0]
    dk = ob["beaver_dict"]["C2"]
    add("E. every upper iteration", "pick the dictionary entry: Beaver dot products of the key one-hot (2 probes) with the read dictionary row (valid, id, next)",
        bd["calls"], bd["448"]["open"] + bd["448"]["finish"], bd["8"]["open"] + bd["8"]["finish"], dk[0], dk[1], 1, "triples", f"{2 * 3 * sum(K):,} products per call")
    mg = res["secure"]["meters"][0]["gc"]
    for name in ("match_direct",):
        g = mg[name]
        ands = (g["and_core"] + g["and_io"]) / g["calls"]
        rows.append([E, "F. every upper iteration", f"GC {name}: first valid (radius, probe) -> candidate id and next row (replaces hash_probe / div_floor / match_priority-with-key-check)", g["calls"], None, None, None, None,
                     None, None, None, None, 4, 4 * g["calls"], f"{ands:,.0f} AND gates = {ands * 32 / MB:.2f} MB of tables per call", "evaluated by C1 (garbled by the server); no division circuit"])
    rows.append([E, "TOTAL (A-E, per client, per query)", "", None, None, None, tot["c448"], tot["c8"], None, None, tot["sent"], tot["recv"], None, tot["fl"], "", "excludes the GC part F"])
sheet("Upper_hash_breakdown", hh, rows, {2: 24, 3: 90, 15: 44, 16: 70}, 76)

# ------------------------------------------------------------------ error / accuracy
rows = []
for E, R in runs.items():
    a = R["res"]["accuracy"]; L = a["lsh"]
    sz = R["res"]["server_build"]["sizes"]; bs = R["res"]["server_build"]["stats"]
    rows.append([m, E, a["nq"], L.get("hash_total", 0), L.get("hash_err", 0), L.get("hash_err", 0) / max(1, L.get("hash_total", 1)), L.get("hash_bound_viol", 0),
                 L.get("oor", 0), L.get("steps", 0), L.get("differs", 0), L.get("differs", 0) / max(1, L.get("steps", 1)), L.get("improve", 0), L.get("missed", 0),
                 L.get("missed", 0) / max(1, L.get("improve", 1)), L.get("empty", 0), bs.get("oor_items", 0), 1 - bs["kept"] / max(1, bs["points"]),
                 a["recall_secure_vs_float_gt"], a["recall_exact_greedy_hnsw_vs_float_gt"], a["recall_hnswlib_vs_quantized_gt"], a["frac_queries_recall1"],
                 str(sz.get("node_K")), sz.get("node_B")])
sheet("LSH_hash_error", ["m", "E", "queries", "hash evaluations (queries x radii x upper steps)", "evaluations with h_hat != h_true", "hash error rate",
                         "violations of the one-bucket bound", "keys outside the interpolation domain", "active upper steps",
                         "steps where the quantised lookup returns a different candidate than the exact-hash lookup", "candidate-disagreement rate",
                         "steps with an improving neighbour", "of which missed (premature descent)", "LSH miss rate", "steps with empty lookup",
                         "dictionary items outside their key window (build)", "bucket-collision loss (items not kept / items)",
                         "recall@10 secure", "recall@10 plain HNSW on the same graph", "recall@10 hnswlib", "fraction of queries with recall 1",
                         "key window K_r per radius", "B"], rows, {}, 120)

notes = [
    "SIFT1M (1,000,000 x 128), m = 8 clients, LAN only (10 Gbps per link, 0.1 ms RTT). Server and every client use ALL 448 cores (8-core client times in Upper_hash_breakdown).",
    "VARIANT: per-node PUBLIC LSH, no garbled circuit for the query hash. Every upper node row keeps its OWN random projection (a, b, w) per radius (w scaled to the node's neighbour distances, as in the baseline) but the whole parameter table is public: the server sends it to every client once (OneTime_Preproc). No secret sharing of (a, b, w), no Beaver products for <a, q>, no secret division circuit (div_floor), no cuckoo dictionary / key check (hash_probe).",
    "WHAT THE CLIENTS CANNOT KNOW IS WHICH ROW IS VISITED (the row index is secret-shared; learning the row's parameters would reveal the node). So: (A) once per query every client quantises its own block for ALL rows and radii locally (doc Sec. 2: q_i = floor(B t_i); the sum over clients is an additive sharing of Q'[row, r]); (B) in every upper iteration the visited row's Q'_r is selected privately with one Beaver dot product of length U = 267k per radius (shared one-hot of the row x shares of Q'[., r]); (C) one masked opening tau = Q' - alpha per radius; (D) fused truncation + one-hot by local Lagrange evaluation over the key window (doc Sec. 4, 6; REAL arithmetic); (E) the directly addressed dictionary row (masked read) is combined with the key one-hot by Beaver dot products; (F) GC only for the first-match priority and the transition.",
    "ERROR: B = 2^ceil(log2(m/0.1)) = 128 (doc Sec. 3.3). The quantised bucket is h or h-1 (never violated, see LSH_hash_error); the lookup probes h_hat and h_hat+1. Hash error rate and recall effect are in LSH_hash_error.",
    "KEY WINDOW: with per-node parameters every row needs its own key window (K_r columns, set from a 3,000-point data sample plus 25% margin on each side, then padded to the largest window over all rows). If a query's key falls outside the interpolation domain the real protocol is undefined (the Lagrange interpolant returns garbage); the simulator counts these cases ('keys outside the interpolation domain') and treats them as a lookup miss. A deployment needs a range guarantee (rigorous bound on Q') or a range proof.",
    "MEASURED: online bytes, flights, AND gates, hash error / recall (all 10,000 queries, plain emulation; the secure engine reproduced it on every one of the 32 secure queries per run), all client / server arithmetic (micro-benchmarks with 8 and 448 threads on the exact shapes: detail_bench.py). MODELLED from native OpenFHE / emp-tool benchmarks: all preprocessing (HE triples, read correlations, alpha powers, garbling, OT) and GC evaluation / OT time online.",
    "COSTS THAT GROW vs the other variants: the Beaver-dot selection needs s*U = 1.6 M triples per upper iteration (19 M per query), a 7.5 MB mask-share store per client per iteration, and (1+s)*U field elements opened all-to-all per iteration (as in all Beaver steps of this engine the opening is all-to-all among clients; routing it through the server would divide client traffic by ~(m-1)). Lagrange evaluation now runs in every upper iteration (not once per query) over larger domains.",
    "RECALL depends on the random build (hnswlib's multithreaded graph + LSH draws): each run here is ONE build; see SIFT1M_recall_and_performance_ALL.xlsx for the build-to-build variance of the other variants. The shared-ID -> one-hot conversion over N+1 columns remains an ideal functionality (only its opening is charged).",
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
