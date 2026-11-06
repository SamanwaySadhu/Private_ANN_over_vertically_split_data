"""Complete per-party breakdown (LAN) for the DELPHI-style protocol: HE only in preprocessing."""
import json
import math
import sys
from collections import defaultdict

import numpy as np

from costmodel import load_cal
from report import fmt_b, fmt_t

TAG = sys.argv[1] if len(sys.argv) > 1 else "sift_N1000000_m4_E64_mask"
import os
S_CORES = 448
C_CORES = int(os.environ.get("CLIENT_CORES", 448))      # clients also use all cores
RTT, BW = 0.1e-3, 10e9 / 8            # LAN: 0.1 ms, 10 Gbps per link

res = json.load(open(f"results/{TAG}.json"))
import os.path
det = json.load(open(f"results/detail_{TAG}.json")) if os.path.exists(f"results/detail_{TAG}.json") else None
ker = json.load(open(f"results/kernel_{TAG}.json")) if os.path.exists(f"results/kernel_{TAG}.json") else None
a_ = res["args"]; m = a_["m"]
he, gc = load_cal()
H = he(m)
slots = H["slots"]
mts = res["secure"]["meters"]
P = ["S"] + [f"C{i + 1}" for i in range(m)]            # C1 = GC evaluator ("P1")


def avg(fld):
    out = defaultdict(float)
    for mt in mts:
        for k, v in mt[fld].items():
            out[k] = out[k] + (np.array(v) if isinstance(v, list) else v)
    return {k: v / len(mts) for k, v in out.items()}


cs, cr, ss, sr, fl, tcli, cnt = (avg(f) for f in ("cs", "cr", "ss", "sr", "fl", "tcli", "cnt"))
gcs = mts[0]["gc"]
ands = sum(g["and_core"] + g["and_io"] for g in gcs.values())
ot_per_client = sum(g["in_bits"] + g["mask_bits"] for g in gcs.values()) / m
triples = sum(v for k, v in cnt.items() if k.startswith("triples|"))
reads = {}
for k, v in mts[0]["cnt"].items():
    if k.startswith("rs:"):
        _, a, n, K = k.split(":")
        reads[(int(a), int(n), int(K))] = v

# ============================== OFFLINE (per query, modelled) ==============================
off_t = defaultdict(lambda: defaultdict(float))       # component -> party -> seconds
off_b = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))   # component -> party -> [sent, recv]


def tcomp(c, p, s):
    off_t[c][p] += s


def bytes_(c, src, dst, n):
    off_b[c][src][0] += n
    off_b[c][dst][1] += n


# garbled circuits: input-independent, server garbles, tables to C1
tcomp("GC garbling", "S", ands / gc["garble_rate"](S_CORES))
bytes_("GC tables", "S", "C1", 32 * ands)
# OT extension (random OTs for the input-label transfers of every circuit)
tcomp("OT extension", "S", ot_per_client * m / gc["rot_per_s"] / S_CORES)
for i in range(1, m + 1):
    tcomp("OT extension", f"C{i}", ot_per_client / gc["rot_per_s"] / C_CORES)
    bytes_("OT extension", f"C{i}", "S", ot_per_client * gc["ot_bytes_per_ot"])
# Beaver triples through threshold HE: client i encrypts a_i,b_i (+rho_i if i>=2); server does ct*ct; Enc2Share to C1
nb = math.ceil(triples / slots)
ct, ct2, pdm, pdl = H["ct_bytes"], H["ct_mult_bytes"], H["pdec_bytes"], H["pdec_bytes"]
for i in range(1, m + 1):
    nenc = 2 + (i >= 2)
    tcomp("Beaver triples (HE)", f"C{i}", nb * (nenc * H["t_enc"] + (H["t_pdec_lead"] + H["t_fusion"] if i == 1 else H["t_pdec_main"])) / C_CORES)
    bytes_("Beaver triples (HE)", f"C{i}", "S", nb * nenc * ct)
    bytes_("Beaver triples (HE)", "S", f"C{i}", nb * ct2)
    if i >= 2:
        bytes_("Beaver triples (HE)", f"C{i}", "C1", nb * pdm)
tcomp("Beaver triples (HE)", "S", nb * (H["t_ct_ct"] + (2 * (m - 1)) * H["t_add"] + (m - 1) * H["t_sub"]) / S_CORES)
# read correlations (r, s, h = A r + s) for every masked 1-D read
for (a, n, K), calls in reads.items():
    cnum = calls * K
    ncts, rch = math.ceil(n / slots), math.ceil(a / slots)
    for i in range(1, m + 1):
        tcomp("Read correlations (HE)", f"C{i}", cnum * (ncts * H["t_enc"] + (i >= 2) * rch * H["t_enc"] +
              (rch * (H["t_pdec_lead"] + H["t_fusion"]) if i == 1 else rch * H["t_pdec_main"])) / C_CORES)
        bytes_("Read correlations (HE)", f"C{i}", "S", cnum * (ncts + (i >= 2) * rch) * ct)
        bytes_("Read correlations (HE)", "S", f"C{i}", cnum * rch * ct2)
        if i >= 2:
            bytes_("Read correlations (HE)", f"C{i}", "C1", cnum * rch * pdm)
    srv = ((m - 1) * ncts * H["t_add"] + a * ncts * (H["t_ct_pt"] + H["t_add"])
           + a * math.log2(slots) * H["t_ct_ct"] + (m - 1) * rch * H["t_sub"] + rch * H["t_add"])
    tcomp("Read correlations (HE)", "S", cnum * srv / S_CORES)

# Lagrange key one-hot (public-LSH variant): alpha^1..alpha^(R-1) via HE, Enc2Share per power, one conversion per radius per query
lag = {int(k.split(":")[1]): v for k, v in mts[0]["cnt"].items() if k.startswith("lag_conv:")}
for R, nconv in lag.items():
    cn = nconv
    for i in range(1, m + 1):
        tcomp("Key-onehot alpha powers (HE)", f"C{i}", cn * (H["t_enc"] + (i >= 2) * R * H["t_enc"] + R * (H["t_pdec_lead"] + H["t_fusion"] if i == 1 else H["t_pdec_main"])) / C_CORES)
        bytes_("Key-onehot alpha powers (HE)", f"C{i}", "S", cn * (1 + (i >= 2) * R) * ct)
        bytes_("Key-onehot alpha powers (HE)", "S", f"C{i}", cn * R * ct2)
        if i >= 2:
            bytes_("Key-onehot alpha powers (HE)", f"C{i}", "C1", cn * R * pdm)
    tcomp("Key-onehot alpha powers (HE)", "S", cn * (R * H["t_ct_ct"] + (m - 1) * H["t_add"] + R * (m - 1) * H["t_sub"]) / S_CORES)
off_comp = list(off_t.keys() | off_b.keys())
order = ["GC garbling", "GC tables", "OT extension", "Beaver triples (HE)", "Read correlations (HE)", "Key-onehot alpha powers (HE)"]
off_comp = [c for c in order if c in off_comp]

# ============================== ONLINE (per query) ==============================
on_b = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))     # cat -> party -> [sent, recv]
for k in set(cs) | set(cr) | set(ss) | set(sr):
    cat = k.split("|")[1]
    if cat == "gc_tables":
        continue
    for i in range(m):
        on_b[cat][f"C{i + 1}"][0] += float(cs[k][i]) if k in cs else 0
        on_b[cat][f"C{i + 1}"][1] += float(cr[k][i]) if k in cr else 0
    on_b[cat]["S"][0] += ss.get(k, 0)
    on_b[cat]["S"][1] += sr.get(k, 0)
flights = sum(fl.values())
on_t = defaultdict(lambda: defaultdict(float))
TS_, TC_ = str(S_CORES), str(C_CORES)
if det is not None:
    srv_t = cli_mask = cli_post = cli_bv = cli_lag = 0.0
    for key, d in det["reads"].items():
        t = d[TS_] if TS_ in d else d[sorted(d.keys() - {"calls"})[-1]]
        tc = d[TC_] if TC_ in d else t
        srv_t += d["calls"] * (t["prep"] + t["tiled"] + t["reduce"])
        cli_mask += d["calls"] * tc["mask"]
        cli_post += d["calls"] * tc["post"]
    cli_sel = cli_nq = 0.0
    for key, d in det["bv"].items():
        if key.startswith("beaver_sel:") and det.get("sel"):
            continue                                   # per-node public-LSH selection is timed with its own kernels below
        tc = d[TC_] if TC_ in d else d[sorted(d.keys() - {"calls"})[-1]]
        cli_bv += d["calls"] * (tc["open"] + tc["finish"] + tc["dsum"])
    for key, d in (det.get("sel") or {}).items():
        tc = d[TC_] if TC_ in d else d[sorted(d.keys() - {"calls"})[-1]]
        cli_sel += d["calls"] * (tc["open"] + tc["part"])
    if det.get("node_q"):
        cli_nq = det["node_q"][TC_] if TC_ in det["node_q"] else list(det["node_q"].values())[-1]
    for key, d in det["lag"].items():
        tc = d[TC_] if TC_ in d else d[sorted(d.keys() - {"calls"})[-1]]
        cli_lag += d["calls"] * tc["lag"]
    on_t["Masked 1-D reads A.(e-r) (matrix products)"]["S"] = srv_t
else:
    ker_T = str(min((int(t) for t in ker), key=lambda t: abs(math.log(t) - math.log(S_CORES))))
    on_t["Masked 1-D reads A.(e-r) (matrix products)"]["S"] = ker[ker_T]
on_t["OT sender (label transfer)"]["S"] = ot_per_client * m / gc["ot_per_s"] / S_CORES
on_t["GC evaluation"]["C1"] = ands / gc["eval_rate"](C_CORES)
lagt = sum(float(v) for k, v in tcli.items() if "lag_onehot" in k)
for i in range(1, m + 1):
    on_t["OT receiver"][f"C{i}"] = ot_per_client / gc["ot_per_s"] / C_CORES
    if det is not None:
        on_t["Client: masked selector e_i - r_i (all cores)"][f"C{i}"] = cli_mask
        on_t["Client: Beaver products incl. distance sums (all cores)"][f"C{i}"] = cli_bv
        on_t["Client: reply combination [y]+[h]"][f"C{i}"] = cli_post
        if cli_lag:
            on_t["Key one-hot, local Lagrange evaluation (real, all cores)"][f"C{i}"] = cli_lag
        if cli_nq:
            on_t["Client: quantise own block for ALL rows and radii, once per query (all cores)"][f"C{i}"] = cli_nq
        if cli_sel:
            on_t["Client: Beaver dot-product selection of the visited row's hash (all cores)"][f"C{i}"] = cli_sel
    else:
        on_t["Local share arithmetic (Beaver, e-r, ...)"][f"C{i}"] = sum(float(v) for v in tcli.values()) - lagt
        if lagt:
            on_t["Key one-hot, local Lagrange evaluation (real)"][f"C{i}"] = lagt
busy = {p: sum(d.get(p, 0.0) for d in on_t.values()) for p in P}
tot_by = {p: [sum(d[p][0] for d in on_b.values()), sum(d[p][1] for d in on_b.values())] for p in P}
t_bw = max(max(v) for v in tot_by.values()) / BW
t_lat = flights * RTT / 2
comm_t = t_bw + t_lat
latency = busy["S"] + busy["C1"] + comm_t

# ============================== OUTPUT ==============================
L = []
w = L.append
tm = res["server_build"]["times"]
w(f"# {TAG}: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server {S_CORES} cores, each client {C_CORES} cores; m={m}, C1 = GC evaluator)\n")
w("HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. "
  "Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).\n")
w("## 1. One-time preprocessing\n")
w("| party | component | time | bytes sent | bytes received |\n|---|---|---|---|---|")
w(f"| Server | HNSW build (hnswlib, 448 cores) | {fmt_t(tm['hnsw_build'])} | | |")
w(f"| Server | graph import | {fmt_t(tm['graph_import'])} | | |")
w(f"| Server | flatten + LSH + cuckoo tables | {fmt_t(tm['flatten_tables'])} | | |")
w(f"| Server | **total (measured)** | **{fmt_t(tm['server_total'])}** | | |")
kg = H["t_keygen_party"] + H["t_keygen_agg"]
kb = H["pk_bytes"] + 2 * H["evk_bytes"]
for i in range(1, m + 1):
    w(f"| Client C{i} | HE threshold keygen (modelled) | {fmt_t(kg)} | {fmt_b(kb)} | {fmt_b(H['pk_bytes'] + H['evk_bytes'])} |")
w(f"| Server | HE keygen relay/aggregation | | {fmt_b(m * (H['pk_bytes'] + H['evk_bytes']))} | {fmt_b(m * kb)} |")

w("\n## 2. Per-query preprocessing (offline phase, modelled)\n")
w("### 2a. Compute time\n")
w("| component | Server | C1 (evaluator) | each other client |\n|---|---|---|---|")
for c in off_comp:
    d = off_t.get(c, {})
    w(f"| {c} | {fmt_t(d.get('S', 0))} | {fmt_t(d.get('C1', 0))} | {fmt_t(d.get('C2', 0))} |")
tS = sum(d.get("S", 0) for d in off_t.values()); t1 = sum(d.get("C1", 0) for d in off_t.values()); t2 = sum(d.get("C2", 0) for d in off_t.values())
w(f"| **total** | **{fmt_t(tS)}** | **{fmt_t(t1)}** | **{fmt_t(t2)}** |")
w("\n### 2b. Communication (sent / received)\n")
w("| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |\n|---|---|---|---|---|---|---|")
for c in off_comp:
    d = off_b.get(c, {})
    g = lambda p, j: fmt_b(d[p][j]) if p in d else "0 B"
    w(f"| {c} | {g('S',0)} | {g('S',1)} | {g('C1',0)} | {g('C1',1)} | {g('C2',0)} | {g('C2',1)} |")
offtot = {p: [sum(off_b[c][p][j] for c in off_b if p in off_b[c]) for j in (0, 1)] for p in P}
w(f"| **total** | **{fmt_b(offtot['S'][0])}** | **{fmt_b(offtot['S'][1])}** | **{fmt_b(offtot['C1'][0])}** | **{fmt_b(offtot['C1'][1])}** | **{fmt_b(offtot['C2'][0])}** | **{fmt_b(offtot['C2'][1])}** |")
w(f"\nOffline phase: {triples:,.0f} Beaver triples ({nb} HE batches of {slots}), {ands:,.0f} GC AND gates, {sum(c*K for (a,n,K),c in reads.items()):,.0f} (r,s,h) read correlations. "
  "All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases "
  "(upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.\n")

w("## 3. Online phase (per query)\n")
w("### 3a. Compute time\n")
w("| component | Server | C1 (evaluator) | each other client |\n|---|---|---|---|")
for c, d in on_t.items():
    w(f"| {c} | {fmt_t(d.get('S', 0))} | {fmt_t(d.get('C1', 0))} | {fmt_t(d.get('C2', 0))} |")
w(f"| **total busy compute** | **{fmt_t(busy['S'])}** | **{fmt_t(busy['C1'])}** | **{fmt_t(busy['C2'])}** |")
w("\n### 3b. Communication (sent / received)\n")
w("| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |\n|---|---|---|---|---|---|---|")
for c, d in sorted(on_b.items(), key=lambda kv: -sum(x[0] for x in kv[1].values())):
    w(f"| {c} | {fmt_b(d['S'][0])} | {fmt_b(d['S'][1])} | {fmt_b(d['C1'][0])} | {fmt_b(d['C1'][1])} | {fmt_b(d['C2'][0])} | {fmt_b(d['C2'][1])} |")
w(f"| **total** | **{fmt_b(tot_by['S'][0])}** | **{fmt_b(tot_by['S'][1])}** | **{fmt_b(tot_by['C1'][0])}** | **{fmt_b(tot_by['C1'][1])}** | **{fmt_b(tot_by['C2'][0])}** | **{fmt_b(tot_by['C2'][1])}** |")
w(f"\nOnline rounds: **{flights:.0f} message flights = {flights/2:.0f} round trips**. LAN communication time: {fmt_t(t_lat)} for round latency + {fmt_t(t_bw)} for transfer = {fmt_t(comm_t)}.")
w(f"\nOnline latency (compute of server + C1, plus LAN communication, no overlap): **{fmt_t(latency)}**. "
  f"Wait: server idle {fmt_t(latency - busy['S'])}, C1 idle {fmt_t(latency - busy['C1'])}, other clients idle {fmt_t(latency - busy['C2'])}.\n")
w("## 4. Totals (offline + online, per query)\n")
w("| party | bytes sent | bytes received | total |\n|---|---|---|---|")
allb = {p: [offtot[p][j] + tot_by[p][j] for j in (0, 1)] for p in P}
for p, nm in (("S", "Server"), ("C1", "C1 (evaluator)"), ("C2", "each other client")):
    w(f"| {nm} | {fmt_b(allb[p][0])} | {fmt_b(allb[p][1])} | {fmt_b(sum(allb[p]))} |")
grand = sum(allb[p][0] for p in P)
w(f"| **all parties (each byte counted once)** | **{fmt_b(grand)}** | **{fmt_b(sum(allb[p][1] for p in P))}** | |")
w(f"\nRounds: online {flights:.0f} flights ({flights/2:.0f} RTT); offline 3 flights on the critical path (HE phases batched).")
open(f"results/BREAKDOWN_{TAG}.md", "w").write("\n".join(L))
json.dump(dict(off_t={c: dict(d) for c, d in off_t.items()}, off_b={c: {p: v for p, v in d.items()} for c, d in off_b.items()},
               on_t={c: dict(d) for c, d in on_t.items()}, on_b={c: {p: v for p, v in d.items()} for c, d in on_b.items()},
               flights=flights, latency=latency, busy=busy, tot_by=tot_by, offtot=offtot, allb=allb,
               comm_t=comm_t, t_bw=t_bw, t_lat=t_lat, triples=triples, nb=nb, ands=float(ands),
               n_corr=sum(c * K for (a, n, K), c in reads.items()), ot_per_client=ot_per_client,
               kg=kg, kb=kb, server_build=res["server_build"]["times"], accuracy=res["accuracy"],
               args=res["args"], U=res["server_build"]["sizes"]["U"], client_cores=C_CORES, server_cores=S_CORES,
               gc_total_bytes=32 * float(ands)), open(f"results/breakdown_{TAG}.json", "w"), default=float)
print("\n".join(L))
