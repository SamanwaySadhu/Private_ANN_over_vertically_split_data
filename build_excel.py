"""Collect results/breakdown_*.json (SIFT1M, DELPHI-style HE-offline protocol, LAN) into one Excel file."""
import glob
import json

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

GB, MB = 1e9, 1e6
runs = sorted((json.load(open(f)) for f in glob.glob("results/breakdown_sift_N1000000_m*_E*_mask.json")),
              key=lambda r: (r["args"]["m"], r["args"]["E"]))
wb = Workbook()
HDR = PatternFill("solid", fgColor="DDE6F3")


def sheet(name, header, rows, widths=None):
    ws = wb.create_sheet(name) if wb.active.title != "Sheet" or name != "Summary" else wb.active
    if ws.title == "Sheet":
        ws.title = name
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True); c.fill = HDR; c.alignment = Alignment(wrap_text=True, vertical="top")
    for r in rows:
        ws.append(r)
    for i in range(1, len(header) + 1):
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(i, 16)
    ws.freeze_panes = "C2"
    ws.row_dimensions[1].height = 48
    return ws


def other(d, key, j=None):
    """value for 'each other client' (C2); same for C3.. by symmetry"""
    return d.get(key)


# ---------------- Summary ----------------
hdr = ["m (clients)", "E (beam width)", "Tb (beam steps)", "recall@10 (secure)", "recall@10 (plaintext HNSW)",
       "GC AND gates / query", "GC size / query (GB)", "Beaver triples / query", "read correlations / query",
       "PREPROC compute Server (s)", "PREPROC compute C1 evaluator (s)", "PREPROC compute each other client (s)",
       "PREPROC sent Server (GB)", "PREPROC recv Server (GB)", "PREPROC sent C1 (GB)", "PREPROC recv C1 (GB)",
       "PREPROC sent other client (GB)", "PREPROC recv other client (GB)",
       "ONLINE compute Server (s)", "ONLINE compute C1 (s)", "ONLINE compute other client (s)",
       "ONLINE sent Server (GB)", "ONLINE recv Server (GB)", "ONLINE sent C1 (GB)", "ONLINE recv C1 (GB)",
       "ONLINE sent other client (GB)", "ONLINE recv other client (GB)",
       "ONLINE message flights", "ONLINE round trips", "PREPROC critical-path flights",
       "ONLINE LAN comm time (s)", "ONLINE latency LAN (s)",
       "TOTAL sent Server (GB)", "TOTAL recv Server (GB)", "TOTAL sent C1 (GB)", "TOTAL recv C1 (GB)",
       "TOTAL sent other client (GB)", "TOTAL recv other client (GB)", "TOTAL communication, all parties (GB)"]
rows = []
for r in runs:
    a = r["args"]; ac = r["accuracy"]
    offc = {p: sum(d.get(p, 0) for d in r["off_t"].values()) for p in ("S", "C1", "C2")}
    ot, ob = r["offtot"], r["tot_by"]
    al = r["allb"]
    rows.append([a["m"], a["E"], a["Tb"] or 2 * a["E"], ac["recall_secure_vs_float_gt"], ac["recall_exact_greedy_hnsw_vs_float_gt"],
                 r["ands"], r["gc_total_bytes"] / GB, r["triples"], r["n_corr"],
                 offc["S"], offc["C1"], offc["C2"],
                 ot["S"][0] / GB, ot["S"][1] / GB, ot["C1"][0] / GB, ot["C1"][1] / GB, ot["C2"][0] / GB, ot["C2"][1] / GB,
                 r["busy"]["S"], r["busy"]["C1"], r["busy"]["C2"],
                 ob["S"][0] / GB, ob["S"][1] / GB, ob["C1"][0] / GB, ob["C1"][1] / GB, ob["C2"][0] / GB, ob["C2"][1] / GB,
                 r["flights"], r["flights"] / 2, 3, r["comm_t"], r["latency"],
                 al["S"][0] / GB, al["S"][1] / GB, al["C1"][0] / GB, al["C1"][1] / GB, al["C2"][0] / GB, al["C2"][1] / GB,
                 sum(al[p][0] for p in al) / GB])
ws = sheet("Summary", hdr, rows)
for row in ws.iter_rows(min_row=2):
    for c in row[3:5]:
        c.number_format = "0.000"
    for c in row[6:7] + row[9:27] + row[30:]:
        c.number_format = "0.00"

# ---------------- one-time ----------------
rows = []
for r in runs:
    a = r["args"]; t = r["server_build"]
    rows.append([a["m"], a["E"], t["hnsw_build"], t["graph_import"], t["flatten_tables"], t["server_total"], r["kg"], r["kb"] / MB])
sheet("OneTime_Preproc", ["m", "E", "Server: HNSW build (s)", "Server: graph import (s)", "Server: flatten+LSH+cuckoo (s)",
                          "Server total (s)", "Each client: HE keygen (s)", "Each client keygen sent (MB)"], rows)

# ---------------- per-component long tables ----------------
def comp_rows(key, scale=None):
    out = []
    for r in runs:
        a = r["args"]
        for comp, d in r[key].items():
            out.append([a["m"], a["E"], comp] + [d.get(p, 0) for p in ("S", "C1", "C2")])
    return out


sheet("Preproc_compute", ["m", "E", "component", "Server (s)", "C1 evaluator (s)", "each other client (s)"],
      comp_rows("off_t"), {3: 28})
sheet("Online_compute", ["m", "E", "component", "Server (s)", "C1 evaluator (s)", "each other client (s)"],
      comp_rows("on_t"), {3: 44})


def comm_rows(key):
    out = []
    for r in runs:
        a = r["args"]
        for comp, d in r[key].items():
            g = lambda p, j: d[p][j] / MB if p in d else 0
            out.append([a["m"], a["E"], comp, g("S", 0), g("S", 1), g("C1", 0), g("C1", 1), g("C2", 0), g("C2", 1)])
    return out


hc = ["m", "E", "component", "Server sent (MB)", "Server recv (MB)", "C1 sent (MB)", "C1 recv (MB)",
      "other client sent (MB)", "other client recv (MB)"]
sheet("Preproc_comm", hc, comm_rows("off_b"), {3: 26})
sheet("Online_comm", hc, comm_rows("on_b"), {3: 20})

# ---------------- notes ----------------
ws = wb.create_sheet("Notes")
notes = [
    "SIFT1M (1,000,000 x 128), LAN only: 10 Gbps per link, 0.1 ms RTT. Server uses all 448 cores, each client 8 cores. k=10, M=8, efConstruction=100, Tg=12, s=6, Tb=2E.",
    "Protocol: HE (threshold BFV) is used ONLY in preprocessing, to build the single-use (r,s,h) read correlations and Beaver triples. Online = masked plaintext reads, Beaver products, garbled circuits. HE is not used online.",
    "C1 is the garbled-circuit evaluator (receives the GC tables, evaluates, receives forwarded labels). The server garbles. 'other client' = C2..Cm (identical by symmetry).",
    "MEASURED (executed): online bytes per party, message flights, AND-gate counts, server 1-D-read matrix-product time (all 448 threads, cache-tiled numba kernel, re-measured on the full read set of each configuration), client local share arithmetic (single-thread numpy), recall, server one-time build time.",
    "MODELLED from native micro-benchmarks (calib/): all preprocessing compute and bytes for GC garbling, OT extension, HE-based Beaver triples and read correlations; HE keygen; GC evaluation and OT time online.",
    "Read-correlation server compute is an upper bound: it prices 13 rotations per matrix row at the ct*ct key-switch time. HE ops are parallelised over independent ciphertexts across the party's cores (server 448 cores: linear extrapolation of the single-core calibrations, only the matrix products are measured at 448 threads). The online matrix product stops speeding up beyond ~64 threads (memory-bandwidth bound).",
    "Preprocessing is per query (correlations are single-use). One-time costs (graph build, keygen) are in OneTime_Preproc.",
    "Ideal functionality (not charged beyond one opening): shared ID -> one-hot conversion. The Sec. 4 Lagrange construction is O(n^2) per client and is not included in any time.",
    "Online latency = server compute + C1 compute + LAN communication (no overlap). Communication time = flights x RTT/2 + max-link bytes / bandwidth.",
    "Rounds: ONLINE message flights are one-way messages (round trips = flights/2). PREPROC: all correlations are generated in one batch, 3 flights on the critical path.",
    "Recall varies with the random build (LSH tables and hnswlib are randomised; SIFT recall std ~0.1 across builds at N=100k), so differences in recall between rows are largely build noise; m does not affect accuracy.",
    "Each byte is counted once in 'TOTAL communication, all parties' (sum of bytes sent by all parties = sum received).",
]
for n in notes:
    ws.append([n])
ws.column_dimensions["A"].width = 160
for row in ws.iter_rows():
    for c in row:
        c.alignment = Alignment(wrap_text=True, vertical="top")
wb.move_sheet("Notes", offset=-(len(wb.sheetnames) - 1))
import sys
OUT = sys.argv[1] if len(sys.argv) > 1 else "SIFT1M_LAN_breakdown.xlsx"
wb.save(OUT)
print("wrote", OUT, "with", len(runs), "configurations;", wb.sheetnames)
