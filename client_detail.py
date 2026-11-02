"""Client online-compute detail for m=8: local share arithmetic by phase/operation, GC AND decomposition."""
import json
import numpy as np
from openpyxl import load_workbook
from openpyxl.styles import Font
from gc_model import GCModel, bits
from vsann import Params
from costmodel import load_cal

he, gc = load_cal()
out = {}
rows_local, rows_gc = [], []
for E in (32, 64, 128):
    tag = f"sift_N1000000_m8_E{E}_mask"
    r = json.load(open(f"results/{tag}.json")); b = json.load(open(f"results/breakdown_{tag}.json"))
    ms = r["secure"]["meters"]; Tb = 2 * E
    tc = {k: float(np.mean([m["tcli"].get(k, 0) for m in ms])) for k in set().union(*[m["tcli"].keys() for m in ms])}
    cnt = ms[0]["cnt"]
    ops = [
        ("Beam: vector reads (16 per step) - subtract Rsh from Esh mod p", "beam|read1d_vec", Tb, 16 * 1000001),
        ("Beam: adjacency read (1 per step) - subtract mask mod p", "beam|read1d_adj", Tb, 1000001),
        ("Beam: Beaver products for distances (16x128 per step)", "beam|beaver", Tb, 16 * 129),
        ("Upper: 12 x vector read of candidate", "upper|read1d_vec", 12, 1000001),
        ("Upper: 12 x dictionary/theta row read", "upper|read1d_theta", 12, r["server_build"]["sizes"]["U"]),
        ("Upper: Beaver products (hash a.q + dictionary column pick + distance)", None, 12, None),
    ]
    up_b = sum(tc.get(k, 0) for k in ("upper|beaver", "upper|beaver_hash", "upper|beaver_dict", "setup|beaver", "setup|share_query"))
    for name, key, calls, elems in ops:
        t = up_b if key is None else tc.get(key, 0)
        rows_local.append([8, E, Tb, name, calls, elems, t, t / calls if calls else 0])
    tot = sum(tc.values())
    beam = sum(v for k, v in tc.items() if k.startswith("beam"))
    rows_local.append([8, E, Tb, "TOTAL local share arithmetic", "", "", tot, ""])
    rows_local.append([8, E, Tb, "  of which beam phase", "", "", beam, ""])
    rows_local.append([8, E, Tb, "  of which upper phase + setup", "", "", tot - beam, ""])
    # GC decomposition of one beam_update call
    prm = Params(N=1000000, d=128, m=8, M=8, E=E, Tb=Tb, s=6)
    g = GCModel(prm, r["server_build"]["sizes"]["U"], r["server_build"]["wmax"] if "wmax" in r["server_build"] else 3000)
    l, lid, ld, D0, LV = g.l, g.lid, g.ld, prm.D0, prm.LV
    kb = 1 + ld + lid
    seen = D0 * LV * (lid + 1)
    n2 = 1 << bits(E + D0); pw = bits(n2)
    ce = (pw * pw - pw + 4) * (1 << (pw - 2)) - 1
    sort = ce * (2 * kb + 2)
    other = D0 * (D0 - 1) // 2 * (lid + 2) + E * lid + (E + D0) * ld + E * (lid + ld + 2) + E * (ld + lid + ld)
    in_el = 4 * E + 2 * LV + 2 + 3 * D0
    out_el = 4 * E + 2 * LV + 2
    io_in = in_el * (3 * l * 7 + 2 * l); io_out = out_el * (3 * l * 8 + l)
    tot_call = seen + sort + other + io_in + io_out
    tot_gc = sum(x["and_core"] + x["and_io"] for x in ms[0]["gc"].values())
    ev = tot_gc / gc["eval_rate"](8)
    rows_gc.append([8, E, Tb, LV, seen, sort, other, io_in, io_out, tot_call, Tb, tot_call * Tb, tot_gc, ev, io_in + io_out])
wb = load_workbook("SIFT1M_LAN_breakdown_full.xlsx")
for nm in ("m8_ClientLocal_detail", "m8_GC_eval_detail"):
    if nm in wb.sheetnames: del wb[nm]
ws = wb.create_sheet("m8_ClientLocal_detail")
ws.append(["m", "E", "Tb", "operation (per client, measured)", "calls / query", "elements per call", "time / query (s)", "time per call (s)"])
for r in rows_local: ws.append(r)
ws2 = wb.create_sheet("m8_GC_eval_detail")
ws2.append(["m", "E", "Tb", "V length LV=1+16*Tb", "ANDs/call: V-membership check (D0 x LV x 21 bits)", "ANDs/call: sorting network",
            "ANDs/call: dup/eviction/argmin", "ANDs/call: reconstruct inputs (wrapper)", "ANDs/call: re-share outputs (wrapper)",
            "ANDs per beam_update call", "calls / query", "ANDs beam_update / query", "ANDs all circuits / query", "C1 GC evaluation time (s, 8 cores)", "ANDs/call in wrapper (in+out)"])
for r in rows_gc: ws2.append(r)
for w in (ws, ws2):
    for c in w[1]: c.font = Font(bold=True)
    for i, wd in enumerate([6, 6, 6, 60, 12, 16, 16, 16]):
        w.column_dimensions[chr(65 + i)].width = wd
wb.save("SIFT1M_LAN_breakdown_full.xlsx")
for r in rows_local: print(r)
print()
for r in rows_gc: print([round(x, 2) if isinstance(x, float) else x for x in r])
