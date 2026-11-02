"""Excel for the m=8 runs (public-LSH, no-GC hash, HE only in preprocessing). LAN only."""
import json
import math
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from costmodel import load_cal

GB, MB = 1e9, 1e6
BW = 10e9 / 8                      # LAN 10 Gbps per link
RTT = 0.1e-3
OUT = sys.argv[1] if len(sys.argv) > 1 else "SIFT1M_m8_breakdown.xlsx"
Es = [32, 64, 128]
runs = {}
for E in Es:
    tag = f"sift_N1000000_m8_E{E}_pub"
    try:
        runs[E] = dict(tag=tag, br=json.load(open(f"results/breakdown_{tag}.json")), det=json.load(open(f"results/detail_{tag}.json")),
                       res=json.load(open(f"results/{tag}.json")))
    except FileNotFoundError:
        print("missing", tag)
he, gc = load_cal()
H = he(8)
slots, ct, ct2, pdm = H["slots"], H["ct_bytes"], H["ct_mult_bytes"], H["pdec_bytes"]
wb = Workbook()
HDR = PatternFill("solid", fgColor="DDE6F3")


def sheet(name, header, rows, widths=None, first=False):
    ws = wb.active if first else wb.create_sheet(name)
    ws.title = name
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True); c.fill = HDR; c.alignment = Alignment(wrap_text=True, vertical="top")
    for r in rows:
        ws.append(r)
    for i in range(1, len(header) + 1):
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(i, 15)
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 62
    return ws


# ---------------- Summary ----------------
hdr = ["m", "E", "Tb", "recall@10 (secure)", "recall@10 (plaintext HNSW)", "hash error rate P(h_hat != h_true)",
       "GC AND gates / query", "GC size / query (GB)", "Beaver triples / query", "read correlations / query",
       "PREPROC compute Server (s)", "PREPROC compute C1 (s)", "PREPROC compute other client (s)",
       "PREPROC sent Server (GB)", "PREPROC recv Server (GB)", "PREPROC sent C1 (GB)", "PREPROC recv C1 (GB)",
       "PREPROC sent other (GB)", "PREPROC recv other (GB)",
       "ONLINE compute Server (s)", "ONLINE compute C1 (s)", "ONLINE compute other client (s)",
       "ONLINE sent Server (GB)", "ONLINE recv Server (GB)", "ONLINE sent C1 (GB)", "ONLINE recv C1 (GB)",
       "ONLINE sent other (GB)", "ONLINE recv other (GB)", "ONLINE message flights", "ONLINE round trips",
       "ONLINE LAN comm time (s)", "ONLINE latency LAN (s)",
       "TOTAL sent Server (GB)", "TOTAL recv Server (GB)", "TOTAL sent C1 (GB)", "TOTAL recv C1 (GB)",
       "TOTAL sent other (GB)", "TOTAL recv other (GB)", "TOTAL communication, all parties (GB)"]
rows = []
for E, R in runs.items():
    b, a = R["br"], R["res"]["accuracy"]
    L = a["lsh"]
    offc = {p: sum(d.get(p, 0) for d in b["off_t"].values()) for p in ("S", "C1", "C2")}
    ot, ob, al = b["offtot"], b["tot_by"], b["allb"]
    rows.append([8, E, 2 * E, a["recall_secure_vs_float_gt"], a["recall_exact_greedy_hnsw_vs_float_gt"], L.get("hash_err", 0) / max(1, L.get("hash_total", 1)),
                 b["ands"], b["gc_total_bytes"] / GB, b["triples"], b["n_corr"],
                 offc["S"], offc["C1"], offc["C2"],
                 ot["S"][0] / GB, ot["S"][1] / GB, ot["C1"][0] / GB, ot["C1"][1] / GB, ot["C2"][0] / GB, ot["C2"][1] / GB,
                 b["busy"]["S"], b["busy"]["C1"], b["busy"]["C2"],
                 ob["S"][0] / GB, ob["S"][1] / GB, ob["C1"][0] / GB, ob["C1"][1] / GB, ob["C2"][0] / GB, ob["C2"][1] / GB,
                 b["flights"], b["flights"] / 2, b["comm_t"], b["latency"],
                 al["S"][0] / GB, al["S"][1] / GB, al["C1"][0] / GB, al["C1"][1] / GB, al["C2"][0] / GB, al["C2"][1] / GB,
                 sum(al[p][0] for p in al) / GB])
sheet("Summary", hdr, rows, first=True)
sheet("OneTime_Preproc", ["m", "E", "Server HNSW build (s)", "Server graph import (s)", "Server flatten+tables (s)", "Server total (s)", "Each client HE keygen (s)", "Each client keygen sent (MB)"],
      [[8, E, R["br"]["server_build"]["hnsw_build"], R["br"]["server_build"]["graph_import"], R["br"]["server_build"]["flatten_tables"],
        R["br"]["server_build"]["server_total"], R["br"]["kg"], R["br"]["kb"] / MB] for E, R in runs.items()])


def comp_rows(key):
    return [[8, E, c] + [d.get(p, 0) for p in ("S", "C1", "C2")] for E, R in runs.items() for c, d in R["br"][key].items()]


def comm_rows(key):
    out = []
    for E, R in runs.items():
        for c, d in R["br"][key].items():
            g = lambda p, j: d[p][j] / MB if p in d else 0
            out.append([8, E, c, g("S", 0), g("S", 1), g("C1", 0), g("C1", 1), g("C2", 0), g("C2", 1)])
    return out


sheet("Preproc_compute", ["m", "E", "component", "Server (s)", "C1 evaluator (s)", "each other client (s)"], comp_rows("off_t"), {3: 40})
sheet("Online_compute", ["m", "E", "component", "Server (s)", "C1 evaluator (s)", "each other client (s)"], comp_rows("on_t"), {3: 56})
hc = ["m", "E", "component", "Server sent (MB)", "Server recv (MB)", "C1 sent (MB)", "C1 recv (MB)", "other client sent (MB)", "other client recv (MB)"]
sheet("Preproc_comm", hc, comm_rows("off_b"), {3: 34})
sheet("Online_comm", hc, comm_rows("on_b"), {3: 20})

# ---------------- hash error ----------------
hr = []
for E, R in runs.items():
    a = R["res"]["accuracy"]; L = a["lsh"]
    hr.append([8, E, a["nq"], L.get("hash_total", 0), L.get("hash_err", 0), L.get("hash_err", 0) / max(1, L.get("hash_total", 1)),
               L.get("hash_bound_viol", 0), L.get("oor", 0), L.get("steps", 0), L.get("differs", 0), L.get("differs", 0) / max(1, L.get("steps", 1)),
               L.get("improve", 0), L.get("missed", 0), L.get("missed", 0) / max(1, L.get("improve", 1)),
               a["recall_secure_vs_float_gt"], a["recall_exact_greedy_hnsw_vs_float_gt"], a["recall_hnswlib_vs_quantized_gt"], a["frac_queries_recall1"]])
sheet("LSH_hash_error", ["m", "E", "queries", "hash evaluations (queries x radii)", "evaluations with h_hat != h_true", "hash error rate",
                         "violations of the one-bucket bound", "keys outside the interpolation domain",
                         "active upper steps", "steps where quantised lookup picks a different candidate than ideal exact-bucket lookup",
                         "candidate-disagreement rate", "steps with an improving neighbour", "of which missed (premature descent)",
                         "LSH failure rate", "recall@10 secure", "recall@10 plaintext HNSW (same graph)", "recall@10 hnswlib", "fraction of queries with recall 1"], hr)


# ---------------- detailed beam breakdowns ----------------
def read_rows(R, a_rows, K):
    b, det, res = R["br"], R["det"], R["res"]
    E = res["args"]["E"]; Tb = res["args"]["Tb"] or 2 * E
    m, n = 8, 1000001
    d = det["reads"][f"{a_rows}:{n}:{K}"]
    T8, T448 = d["8"], d["448"]
    ncts, rch = math.ceil(n / slots), math.ceil(a_rows / slots)
    rows = []

    def add(op, srv=0.0, c1=0.0, oth=0.0, c8=0.0, ssent=0, srecv=0, c1s=0, c1r=0, os_=0, or_=0, fl=0, note=""):
        lan = max(ssent, srecv, c1s, c1r, os_, or_) / BW
        rows.append([E, Tb, op, srv, c1, oth, c8, ssent, srecv, c1s, c1r, os_, or_, lan, fl, srv * Tb, c1 * Tb, oth * Tb, c8 * Tb,
                     ssent * Tb, srecv * Tb, c1s * Tb, c1r * Tb, os_ * Tb, or_ * Tb, lan * Tb, fl * Tb, note])

    add("1. Shared one-hot creation, %d conversion(s) of size N+1 (IDEAL functionality, cost not charged beyond the opening)" % K,
        c1s=K * 4 * (m - 1), c1r=K * 4 * (m - 1), os_=K * 4 * (m - 1), or_=K * 4 * (m - 1), fl=1,
        note="the real Lagrange conversion is O(n^2) per client at n=1M and infeasible; only the masked opening tau is charged")
    add("2. Client: masked selector e_i - r_i mod p over K*n entries", c1=T448["mask"], oth=T448["mask"], c8=T8["mask"],
        note="elementwise subtract+reduce on all cores of the client (448 threads); 'client 8 cores' column uses 8 threads")
    add("3. Upload q_i = e_i - r_i to the server (n x K field elements per client)", srecv=m * K * n * 4, c1s=K * n * 4, os_=K * n * 4, fl=1)
    add("4. Server: add the m shares, split into 16-bit halves (_prep)", srv=T448["prep"], note="448 threads")
    add("5. Server: cache-tiled integer matrix product A . q (_tiled)", srv=T448["tiled"], note=f"{a_rows} x {n} x {K} multiply-adds, x2 for the 16-bit split")
    add("6. Server: reduce partial sums mod p (_reduce)", srv=T448["reduce"])
    add("7. Server -> C1: reply y = A q - s (a x K values)", ssent=a_rows * K * 4, c1r=a_rows * K * 4, fl=1)
    add("8. C1: out = [y] + [h] (a x K values)", c1=T448["post"], c8=T8["post"])
    cl_off = K * (ncts * H["t_enc"] + rch * (H["t_pdec_lead"] + H["t_fusion"])) / 448
    cl_off_o = K * (ncts * H["t_enc"] + rch * H["t_enc"] + rch * H["t_pdec_main"]) / 448
    srv_off = K * ((m - 1) * ncts * H["t_add"] + a_rows * ncts * (H["t_ct_pt"] + H["t_add"]) + a_rows * math.log2(slots) * H["t_ct_ct"] + (m - 1) * rch * H["t_sub"]) / 448
    add("OFFLINE (modelled, per step): (r,s,h) correlations via threshold HE for these %d read(s)" % K,
        srv=srv_off, c1=cl_off, oth=cl_off_o, c8=cl_off * 448 / 8,
        ssent=K * m * rch * ct2, srecv=K * (m * ncts + (m - 1) * rch) * ct, c1s=K * ncts * ct, c1r=K * rch * ct2 + K * (m - 1) * rch * pdm,
        os_=K * (ncts + rch) * ct + K * rch * pdm, or_=K * rch * ct2, fl=3,
        note="server time includes 13 rotations per matrix row priced at the ct x ct key-switch time (upper bound); modelled from OpenFHE micro-benchmarks")
    return rows


def bv_rows(R):
    b, det, res = R["br"], R["det"], R["res"]
    E = res["args"]["E"]; Tb = res["args"]["Tb"] or 2 * E
    m = 8
    L = 16 * 128
    d = det["bv"][f"beaver_dist:{L}"]
    T8, T448 = d["8"], d["448"]
    rows = []

    def add(op, srv=0.0, c1=0.0, oth=0.0, c8=0.0, ssent=0, srecv=0, c1s=0, c1r=0, os_=0, or_=0, fl=0, note=""):
        lan = max(ssent, srecv, c1s, c1r, os_, or_) / BW
        rows.append([E, Tb, op, srv, c1, oth, c8, ssent, srecv, c1s, c1r, os_, or_, lan, fl, srv * Tb, c1 * Tb, oth * Tb, c8 * Tb,
                     ssent * Tb, srecv * Tb, c1s * Tb, c1r * Tb, os_ * Tb, or_ * Tb, lan * Tb, fl * Tb, note])

    both = lambda k: (T448[k], T8[k])
    add("1. Client: x - A and y - B for the 16x128 = 2,048 products (opened values e, f)", c1=T448["open"], oth=T448["open"], c8=T8["open"],
        note="x = shared query coordinates, y = shared retrieved neighbour coordinates")
    add("2. Open e, f: each client sends its shares to all other clients (2 x 2,048 field elements to each of the m-1 others)",
        c1s=2 * L * 4 * (m - 1), c1r=2 * L * 4 * (m - 1), os_=2 * L * 4 * (m - 1), or_=2 * L * 4 * (m - 1), fl=1)
    add("3. Client: [xy] = [C] + e[B] + f[A] (+ e f for client 1) mod p", c1=T448["finish"], oth=T448["finish"], c8=T8["finish"])
    add("4. Client: sum the 128 products per neighbour -> [z_u]; d_u = n_q + n_u - 2 z_u", c1=T448["dsum"], oth=T448["dsum"], c8=T8["dsum"])
    nbatch = L / slots
    cl_off = nbatch * (2 * H["t_enc"] + H["t_pdec_lead"] + H["t_fusion"]) / 448
    cl_off_o = nbatch * (3 * H["t_enc"] + H["t_pdec_main"]) / 448
    srv_off = nbatch * (H["t_ct_ct"] + 2 * (m - 1) * H["t_add"] + (m - 1) * H["t_sub"]) / 448
    add("OFFLINE (modelled, per step): 2,048 Beaver triples via threshold HE (fraction of one 8,192-slot batch)", srv=srv_off, c1=cl_off, oth=cl_off_o,
        c8=cl_off * 448 / 8, ssent=m * nbatch * ct2, srecv=(m * 2 + (m - 1)) * nbatch * ct, c1s=2 * nbatch * ct, c1r=nbatch * ct2 + (m - 1) * nbatch * pdm,
        os_=3 * nbatch * ct + nbatch * pdm, or_=nbatch * ct2, fl=3, note="triples are packed 8,192 per ciphertext; a whole step uses 25% of one batch")
    return rows


hdr_d = ["E", "Tb (steps)", "sub-operation", "Server time / step, 448 cores (s)", "C1 time / step, 448 cores (s)",
         "each other client time / step, 448 cores (s)", "client time / step, 8 cores (s)",
         "Server sent / step (B)", "Server recv / step (B)", "C1 sent / step (B)", "C1 recv / step (B)", "other client sent / step (B)",
         "other client recv / step (B)", "LAN transfer time / step (s)", "message flights / step",
         "Server time / query (s)", "C1 time / query (s)", "other client time / query (s)", "client 8 cores time / query (s)",
         "Server sent / query (B)", "Server recv / query (B)", "C1 sent / query (B)", "C1 recv / query (B)",
         "other sent / query (B)", "other recv / query (B)", "LAN transfer time / query (s)", "flights / query", "note"]
sheet("Beam_vector_reads", hdr_d, [r for R in runs.values() for r in read_rows(R, 129, 16)], {3: 80, 28: 80})
sheet("Beam_adjacency_read", hdr_d, [r for R in runs.values() for r in read_rows(R, 32, 1)], {3: 80, 28: 80})
sheet("Beam_Beaver_distances", hdr_d, [r for R in runs.values() for r in bv_rows(R)], {3: 80, 28: 80})

notes = [
    "SIFT1M (1,000,000 x 128), m = 8 clients, LAN only (10 Gbps per link, 0.1 ms RTT). Server and every client use ALL 448 cores (also shown for an 8-core client in the detail sheets).",
    "Protocol variant: PUBLIC global LSH projections (doc private_selection_preprocessing_lsh): clients quantise their own block locally, q_i = floor(B t_i); the hash is computed ONCE per query from additive shares (no GC, no Beaver products for the hash); one masked opening per radius; fused truncation + one-hot by Lagrange interpolation (real arithmetic) over a small key domain; directly addressed dictionary (no cuckoo, no AES, no key check).",
    "HE (threshold BFV) is used ONLY in preprocessing (Beaver triples, (r,s,h) read correlations, alpha powers for the key one-hot). Online: masked plaintext reads, Beaver products, garbled circuits (row mux, match priority, transition, beam update).",
    "Hash error: B = 2^ceil(log2(m/eps)) with eps = 0.1 (m=8 -> B=128). 'hash error rate' = fraction of hash evaluations where the quantised bucket h_hat differs from the exact bucket h (always h or h-1, never violated). The lookup probes h_hat and h_hat+1.",
    "MEASURED: online bytes, message flights, AND gates, recall and error rates (1000 queries); all client-side and server-side arithmetic times (per-operation micro-benchmarks with 8 and 448 threads on the exact shapes of the run: detail_bench.py); server one-time build.",
    "MODELLED from native OpenFHE / emp-tool micro-benchmarks: all preprocessing compute and bytes (HE correlations, triples, alpha powers, GC garbling, OT), GC evaluation and OT time online. Client HE/GC items assume linear scaling to 448 cores.",
    "The shared-ID -> one-hot conversion over N+1 = 1M columns is an IDEAL functionality (value revealed in the simulator and re-shared); only its masked opening is charged. The real Lagrange conversion is O(n^2) per client and infeasible at n = 1M. The key one-hot over the tiny key domain is real.",
    "(r,s,h) read-correlation server time is an upper bound: 13 rotations per matrix row priced at the ct x ct key-switch time. alpha-power HE assumes depth-1 calibration (deeper circuits need larger parameters).",
    "Online latency = server compute + C1 compute + LAN communication (no overlap). Beam-step detail sheets: per-step and per-query (x Tb) values for every sub-operation; per-party bytes are per step.",
    "SIFT recall depends on the random build (LSH constants/hnswlib); with public global projections recall is lower than with per-node secret projections (see LSH_hash_error sheet).",
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
