"""Excel: HNSecW baseline, SIFT1M, m=8, E=32/64/128, LAN (0.1 ms, 10 Gbps; server 64 cores, client 8 cores)."""
import json, os, sys
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
import _path  # noqa
from hcost import Cfg, evaluate, load_cal

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "SIFT1M_m8_hnsecw_breakdown.xlsx")
MB, GB, TB = 1e6, 1e9, 1e12
he, gc = load_cal()
R = {}
for E in (32, 64, 128):
    r = json.load(open(f"{HERE}/results/hnsecw_sift_N1000000_m8_E{E}.json"))
    R[E] = (r, evaluate(r, he, gc, Cfg(0.1, 10000.0)))
HDR = PatternFill("solid", fgColor="DDE6F3")
wb = Workbook(); first = True
def sheet(name, header, rows, w0=44):
    global first
    ws = wb.active if first else wb.create_sheet(name); first = False
    ws.title = name; ws.append(header)
    for c in ws[1]: c.font = Font(bold=True); c.fill = HDR; c.alignment = Alignment(wrap_text=True)
    for r in rows: ws.append(r)
    for i in range(1, len(header) + 1): ws.column_dimensions[get_column_letter(i)].width = w0 if i == 1 else 18
    ws.freeze_panes = "A2"
Es = (32, 64, 128)
ms = lambda s: round(s * 1e3, 2)

# Summary
rows = []
for lab, f in [
 ("recall@10 (vs float GT)", lambda r, x: r["accuracy"]["recall_secure_vs_float_gt"]),
 ("Online latency (ms)", lambda r, x: ms(x["latency_s"])),
 ("  server compute (ms)", lambda r, x: ms(x["latency_compute_server_s"])),
 ("  client 1 (evaluator) compute (ms)", lambda r, x: ms(x["latency_compute_client_s"])),
 ("  communication: round-trip part (ms)", lambda r, x: ms(x["latency_rounds_s"])),
 ("  communication: transfer part (ms)", lambda r, x: ms(x["latency_transfer_s"])),
 ("Online bytes, server (MB)", lambda r, x: round(x["online_bytes_server"] / MB, 2)),
 ("Online bytes, client 1 (MB)", lambda r, x: round(x["online_bytes_client"][0] / MB, 2)),
 ("Online bytes, each client 2-8 (MB)", lambda r, x: round(x["online_bytes_client"][1] / MB, 2)),
 ("Flights", lambda r, x: x["flights"]),
 ("Round trips", lambda r, x: x["rtts"]),
 ("AND gates (GC)", lambda r, x: x["ands"]),
 ("Beaver triples", lambda r, x: x["triples"]),
 ("Offline latency per query (min)", lambda r, x: round(x["offline"]["offline_total_latency_s"] / 60, 2)),
 ("Offline reshuffle bytes per party (TB)", lambda r, x: round(x["offline"]["shuffle_bytes_per_party"] / TB, 3)),
 ("Offline reshuffle bytes total (TB)", lambda r, x: round(x["offline"]["shuffle_bytes_total"] / TB, 3))]:
    rows.append([lab] + [f(*R[E]) for E in Es])
sheet("Summary", ["metric"] + [f"E={E}" for E in Es], rows)

# Preprocessing
r = R[64][0]; sb = r["server_build"]["times"]; sz = r["server_build"]["sizes"]
rows = [["hnswlib build (s)", round(sb["hnsw_build"], 2), "-"],
        ["Table construction (s)", round(sb["tables"], 2), "-"],
        ["Server build total (s)", round(sb["server_total"], 2), "-"],
        ["Secret-shared tables per party (GB)", round(sz["tables_bytes_per_party"] / GB, 3), round(sz["tables_bytes_per_party"] / GB, 3)],
        ["Raw vectors (MB)", round(sz["raw_vectors_bytes"] / MB, 1), "-"],
        ["Layer sizes", str(sz["layer_nodes"]), ""], ["Steps per layer (base, upper...)", str(sz["T"]) if not isinstance(sz["T"], list) else str(sz["T"]), ""]]
sheet("Preprocessing", ["item (one-time)", "server", "each client"], rows)

# Offline per query
rows = []
for E in Es:
    x = R[E][1]; o = x["offline"]
    rows += [[f"E={E}: GC garbling time, server (ms)", ms(o["gc_garble_server_s"]), "-"],
             [f"E={E}: GC tables sent to client 1 (GB)", round(o["gc_table_bytes"] / GB, 3), "client 1 only"],
             [f"E={E}: OT correlations time (ms)", ms(o["rot_gen_s_server"]), ms(o["rot_gen_s_client"])],
             [f"E={E}: OT correlations bytes (MB)", "-", round(o["rot_bytes_per_client"] / MB, 2)],
             [f"E={E}: Beaver triples HE time (ms)", ms(o["triple_server_s"]), ms(o["triple_client_s"])],
             [f"E={E}: Beaver triples bytes per party (MB)", round(o["triple_bytes_party"] / MB, 2), round(o["triple_bytes_party"] / MB, 2)],
             [f"E={E}: Table reshuffle latency (min, lower bound)", round(o["shuffle_latency_s"] / 60, 2), round(o["shuffle_latency_s"] / 60, 2)],
             [f"E={E}: Table reshuffle bytes per party (TB)", round(o["shuffle_bytes_per_party"] / TB, 3), round(o["shuffle_bytes_per_party"] / TB, 3)],
             [f"E={E}: Offline latency total (min)", round(o["offline_total_latency_s"] / 60, 2), ""]]
sheet("Offline", ["component (per query)", "server", "each client"], rows, 56)

# Online compute + comm by party
rows = []
for E in Es:
    x = R[E][1]
    rows += [[f"E={E}: compute (ms)", ms(x["latency_compute_server_s"]), ms(x["latency_compute_client_s"]), ms(x["t_cl_parts"]["ot_receive"])]]
    for c, v in sorted(x["bytes_by_cat"].items()):
        rows.append([f"E={E}: comm {c} (MB)", round(v[0] / MB, 3), round(v[1] / MB, 3), round(v[2] / MB, 3)])
    rows.append([f"E={E}: comm TOTAL (MB)", round(x["online_bytes_server"] / MB, 2), round(x["online_bytes_client"][0] / MB, 2), round(x["online_bytes_client"][1] / MB, 2)])
    rows.append([f"E={E}: round trips (all 9 parties)", x["rtts"], x["rtts"], x["rtts"]])
sheet("Online", ["metric (per query)", "server", "client 1 (evaluator)", "clients 2-8 (each)"], rows, 44)

# Rounds
rows = []
for E in Es:
    x = R[E][1]
    for k, v in x["flights_by_cat"].items(): rows.append([f"E={E}: {k}", v])
    rows.append([f"E={E}: total flights / round trips", f"{x['flights']:.0f} / {x['rtts']:.0f}"])
sheet("Rounds", ["category", "flights"], rows)

# GC circuits
rows = []
for E in Es:
    for n, g in R[E][1]["gc_by_circuit"].items():
        rows.append([f"E={E}: {n}", g["calls"], g["ands"], round(g["io"] / g["ands"], 3)])
sheet("GC circuits", ["circuit", "calls", "ANDs", "wrapper share"], rows)
wb.save(OUT); print(OUT)
