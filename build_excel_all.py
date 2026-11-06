"""One workbook for everything: SIFT1M recall (all modes, m, E, k, seeds), the study of why recall varies with
the number of clients, the gap to plain HNSW and optimisations, and the full performance breakdowns
(mask = per-node secret LSH with GC hash, pub = public LSH without GC hash). LAN only."""
import glob
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from costmodel import load_cal

GB, MB = 1e9, 1e6
BW, RTT = 10e9 / 8, 0.1e-3
OUT = sys.argv[1] if len(sys.argv) > 1 else "SIFT1M_recall_and_performance_ALL.xlsx"
MODES = {"mask": "secret per-node LSH (hash in GC)", "pub": "public LSH (no-GC hash)"}
MS, ES = (2, 4, 8), (32, 64, 128)
KS = (1, 5, 10, 20, 50, 100)
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
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(i, 14)
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = height
    return ws


def stat(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return (None,) * 4
    a = np.array(xs, float)
    return float(a.mean()), float(a.std(ddof=1)) if len(a) > 1 else 0.0, float(a.min()), float(a.max())


# ------------------------------------------------------------------ study data
recs = []
for f in sorted(glob.glob("results/recall_study_s*_both.json")):
    recs += json.load(open(f))
seeds = sorted({r["seed"] for r in recs})
S = defaultdict(list)                         # (part, mode, name, m, E) -> records over seeds
for r in recs:
    S[(r["part"], r["mode"], r["name"], r["m"], r["E"])].append(r)
rec_at = lambda rs, k: [r["recall"].get(str(k)) for r in rs]
print("seeds", seeds, "records", len(recs))

# plain hnswlib reference: per build where known, else the mask build of the same seed
ref_build = defaultdict(dict)                 # (seed, build) -> E -> recall dict
for r in recs:
    if r["mode"] == "hnswlib":
        ref_build[(r["seed"], "mask_m8")][r["E"]] = r["recall"]
    elif r["mode"] == "hnswlib_build":
        ref_build[(r["seed"], r["build"])][r["E"]] = r["recall"]


def plain(mode, m, E, k, per_build=True):
    vals = []
    for s in seeds:
        d = ref_build.get((s, f"{mode}_m{m}" if mode == "pub" else "mask_m8"), {}).get(E)
        if d is None and not per_build:
            d = ref_build.get((s, "mask_m8"), {}).get(E)
        if d and str(k) in d:
            vals.append(d[str(k)])
    return stat(vals)


# ------------------------------------------------------------------ 1. recall vs k
rows = []
for mode in ("mask", "pub"):
    for m in ((1, 2, 4, 8, 16) if mode == "mask" else MS):
        for E in (32, 64, 128, 256):
            rs = S.get(("sweep", mode, f"base m{m}", m, E), [])
            for k in KS:
                if k > E or not rs:
                    continue
                mu, sd, lo, hi = stat(rec_at(rs, k))
                pm, _, _, _ = plain(mode, m, E, k)
                pa, _, _, _ = plain("mask", 8, E, k)
                rows.append([MODES[mode], m, E, k, len(rs), mu, sd, lo, hi, pm, (pm - mu) if pm is not None else None, pa, pa - mu])
sheet("Recall_vs_k", ["variant", "m (clients)", "E (beam width)", "k", "#builds (seeds)", "secure recall@k (mean over builds)", "std over builds",
                      "min over builds", "max over builds", "plain hnswlib, same build (mean)", "gap: plain(same build) - secure",
                      "plain hnswlib, mean over all builds", "gap: plain(mean) - secure"], rows, {1: 32})

# ------------------------------------------------------------------ 2. why does recall change with m
rows = []
for s in seeds:
    for E in (32, 64, 128, 256):
        base = S.get(("sweep", "mask", "base m1", 1, E))
        base = [r for r in base if r["seed"] == s] if base else []
        if not base or not base[0]["per10"]:
            continue
        p1 = np.array(base[0]["per10"])
        line = [s, E, p1.mean()]
        mx = 0
        for m in (2, 4, 8, 16):
            r = [x for x in S.get(("sweep", "mask", f"base m{m}", m, E), []) if x["seed"] == s]
            if not r:
                line += [None, None, None]; continue
            p = np.array(r[0]["per10"]); dlt = p - p1
            mx = max(mx, abs(p.mean() - p1.mean()))
            line += [p.mean(), float((dlt != 0).mean()), float(dlt.mean() / (dlt.std(ddof=1) / math.sqrt(len(dlt)) + 1e-12))]
        line.append(mx)
        rows.append(line)
hdr = ["build seed", "E", "m=1 (exact hash, no quantisation) recall@10"]
for m in (2, 4, 8, 16):
    hdr += [f"m={m} recall@10", f"m={m}: fraction of queries whose recall@10 differs from m=1", f"m={m}: paired t-statistic of the mean difference"]
hdr += ["max |recall@10(m) - recall@10(m=1)|"]
sheet("Why_m_controlled", hdr, rows, {1: 10, 3: 18}, 90)
why_m_rows = list(rows)

rows = []
for mode in ("pub", "mask"):
    for m in MS:
        for E in ES:
            rs = S.get(("sweep", mode, f"base m{m}", m, E), [])
            for r in rs:
                pr = ref_build.get((r["seed"], f"{mode}_m{m}" if mode == "pub" else "mask_m8"), {}).get(E, {}).get("10")
                rows.append([MODES[mode], r["seed"], m, E, r["recall"].get("10"), pr, (pr - r["recall"]["10"]) if pr is not None else None])
sheet("Why_m_build_variance", ["variant", "build seed", "m", "E", "secure recall@10", "plain hnswlib recall@10 on THE SAME build", "gap (points/100)"],
      rows, {1: 32}, 62)

# measured per-config runs of the earlier performance pipeline (each (m,E) rebuilt the graph and tables)
rows = []
for f in sorted(glob.glob("results/sift_N1000000_m*_E*_*.json")):
    r = json.load(open(f))
    if "accuracy" not in r or "_k" in f:
        continue
    a = r["accuracy"]; ar = r["args"]
    rows.append([MODES[ar["mode"]], ar["m"], ar["E"], a["nq"], a["recall_secure_vs_float_gt"], a["recall_hnswlib_vs_quantized_gt"],
                 a["recall_hnswlib_vs_quantized_gt"] - a["recall_secure_vs_float_gt"], r["server_build"]["sizes"]["U"]])
sheet("Why_m_perf_runs", ["variant", "m", "E", "queries", "secure recall@10 (first 1000 queries)", "plain hnswlib recall@10 (same build)", "gap",
                          "rows U of upper table (differs per build)"], rows, {1: 32}, 62)

# ------------------------------------------------------------------ 3. optimisations / gap decomposition
VAR = ["base", "Tg=24", "Tg=48", "Tb=4E", "oracle entry", "trail seeding", "all-radii", "trail+all-radii", "trail+all-radii+Tg24"]
rows, rows_d = [], []
for mode in ("mask", "pub"):
    for E in ES:
        pl = plain(mode, 8, E, 10)[0] if mode == "pub" else plain("mask", 8, E, 10)[0]
        base10 = None
        for name in VAR:
            rs = S.get(("ablate", mode, name, 8, E), [])
            if not rs:
                continue
            row = [MODES[mode], E, name, len(rs)]
            for k in (1, 10, 50, 100):
                row += [stat(rec_at(rs, k))[0] if k <= E else None]
            mu, sd, lo, hi = stat(rec_at(rs, 10))
            if name == "base":
                base10 = mu
            plain_s = plain("mask", 8, E, 10)[0]
            row += [sd, lo, hi, mu - base10 if base10 is not None else None, plain_s,
                    ((mu - base10) / (plain_s - base10)) if base10 is not None and plain_s - base10 > 1e-9 else None]
            rows.append(row)
            st = defaultdict(list)
            for r in rs:
                for k_, v_ in r["stats"].items():
                    st[k_].append(v_)
            rows_d.append([MODES[mode], E, name] + [float(np.mean(st[k_])) if st[k_] else None for k_ in
                                                    ("acc", "steps", "empty", "ep_is_oracle", "ep_d_ratio", "unfinished", "live_end")])
sheet("Optimizations", ["variant", "E", "optimisation", "#builds", "recall@1", "recall@10", "recall@50", "recall@100", "std of recall@10 over builds",
                        "worst build recall@10", "best build recall@10", "gain vs base (recall@10)", "plain hnswlib recall@10 (same-seed mask build)", "share of the gap to plain HNSW closed"], rows, {1: 32, 3: 26}, 76)
sheet("Upper_phase_diagnostics", ["variant", "E", "optimisation", "accepted upper moves / query", "active upper steps / query", "empty-lookup steps / query",
                                  "fraction of queries whose layer-0 entry == plain-HNSW entry", "mean d(entry)/d(plain entry)", "fraction with upper budget unfinished",
                                  "fraction of queries whose beam hit Tb"], rows_d, {1: 32, 3: 26}, 76)


# ---- build-to-build variance diagnosis
rows = []
for mode in ("mask", "pub"):
    fn = f"results/diag_bad_build_{mode}.json"
    if os.path.exists(fn):
        for d in json.load(open(fn)):
            lay = d["layers"]
            rows.append([MODES[mode], d["build"], d["hnswlib"], d["protocol"], d["oracle_entry"], d["frac_queries_recall_lt_half"], d["frac_oracle_lt_half"],
                         d["ep_ratio_hard"], d["ep_ratio_easy"], d["distinct_entries"], str(d["layer_nodes"])] +
                        [lay.get(str(l), {}).get("move_rate") for l in range(1, 7)])
sheet("Diag_rebuild_same_config", ["variant", "rebuild #", "plain hnswlib recall@10", "protocol recall@10", "protocol with oracle entry point recall@10",
                                   "fraction of queries with recall@10 < 0.5 (protocol)", "same with oracle entry", "mean d(entry)/d(plain entry), queries with recall < 0.5",
                                   "same, queries with recall >= 0.5", "distinct layer-0 entry points used", "nodes per layer (layer 0 ... top)"] +
      [f"layer {l}: fraction of upper steps that moved" for l in range(1, 7)], rows, {1: 32, 11: 40}, 90)
rows = []
for mode in ("mask", "pub"):
    fn = f"results/lsh_seed_variance_{mode}.json"
    if os.path.exists(fn):
        for d in json.load(open(fn)):
            rows.append([MODES[mode], d["graph"], d["lsh_seed"], d["hnswlib"], d["base"], d["oracle"], d["all-radii+Tg24"]])
sheet("Diag_LSH_draw_variance", ["variant", "graph # (fixed hnswlib graph)", "LSH draw #", "plain hnswlib recall@10 (E=64)", "protocol recall@10 (baseline)",
                                 "protocol, oracle entry point", "protocol, all-radii + Tg=24"], rows, {1: 32}, 76)

# ------------------------------------------------------------------ 4. performance
he, gc = load_cal()
runs = {}
for mode in ("mask", "pub"):
    for m in MS:
        for E in ES:
            tag = f"sift_N1000000_m{m}_E{E}_{mode}"
            try:
                runs[(mode, m, E)] = dict(tag=tag, br=json.load(open(f"results/breakdown_{tag}.json")), res=json.load(open(f"results/{tag}.json")),
                                          det=json.load(open(f"results/detail_{tag}.json")) if os.path.exists(f"results/detail_{tag}.json") else None)
            except FileNotFoundError:
                print("missing perf run", tag)
rows = []
for (mode, m, E), R in runs.items():
    b, a = R["br"], R["res"]["accuracy"]
    L = a["lsh"]
    rs = S.get(("sweep", mode, f"base m{m}", m, E), [])
    offc = {p: sum(d.get(p, 0) for d in b["off_t"].values()) for p in ("S", "C1", "C2")}
    ot, ob, al = b["offtot"], b["tot_by"], b["allb"]
    herr = L.get("hash_err", 0) / max(1, L.get("hash_total", 1)) if mode == "pub" else None
    rows.append([MODES[mode], m, E, 2 * E, stat(rec_at(rs, 10))[0], stat(rec_at(rs, 1))[0], plain("mask", 8, E, 10)[0], a["recall_secure_vs_float_gt"], herr,
                 b["ands"], b["gc_total_bytes"] / GB, b["triples"], b["n_corr"],
                 offc["S"], offc["C1"], offc["C2"],
                 ot["S"][0] / GB, ot["S"][1] / GB, ot["C1"][0] / GB, ot["C1"][1] / GB, ot["C2"][0] / GB, ot["C2"][1] / GB,
                 b["busy"]["S"], b["busy"]["C1"], b["busy"]["C2"],
                 ob["S"][0] / GB, ob["S"][1] / GB, ob["C1"][0] / GB, ob["C1"][1] / GB, ob["C2"][0] / GB, ob["C2"][1] / GB,
                 b["flights"], b["flights"] / 2, b["comm_t"], b["latency"],
                 al["S"][0] / GB, al["S"][1] / GB, al["C1"][0] / GB, al["C1"][1] / GB, al["C2"][0] / GB, al["C2"][1] / GB,
                 sum(al[p][0] for p in al) / GB])
sheet("Perf_Summary", ["variant", "m", "E", "Tb", "recall@10 (mean over builds, 10k queries)", "recall@1 (mean over builds)", "plain hnswlib recall@10 (mean over builds)",
                       "recall@10 of THIS run (first 1000 queries, its own build)", "hash error rate P(h_hat != h_true)",
                       "GC AND gates / query", "GC size / query (GB)", "Beaver triples / query", "read correlations / query",
                       "PREPROC compute Server (s)", "PREPROC compute C1 (s)", "PREPROC compute other client (s)",
                       "PREPROC sent Server (GB)", "PREPROC recv Server (GB)", "PREPROC sent C1 (GB)", "PREPROC recv C1 (GB)", "PREPROC sent other (GB)", "PREPROC recv other (GB)",
                       "ONLINE compute Server (s)", "ONLINE compute C1 (s)", "ONLINE compute other client (s)",
                       "ONLINE sent Server (GB)", "ONLINE recv Server (GB)", "ONLINE sent C1 (GB)", "ONLINE recv C1 (GB)", "ONLINE sent other (GB)", "ONLINE recv other (GB)",
                       "ONLINE message flights", "ONLINE round trips", "ONLINE LAN comm time (s)", "ONLINE latency LAN (s)",
                       "TOTAL sent Server (GB)", "TOTAL recv Server (GB)", "TOTAL sent C1 (GB)", "TOTAL recv C1 (GB)", "TOTAL sent other (GB)", "TOTAL recv other (GB)",
                       "TOTAL communication, all parties (GB)"], rows, {1: 32}, 90)
sheet("OneTime_Preproc", ["variant", "m", "E", "Server HNSW build (s)", "Server graph import (s)", "Server flatten+tables (s)", "Server total (s)",
                          "Each client HE keygen (s)", "Each client keygen sent (MB)"],
      [[MODES[k[0]], k[1], k[2], R["br"]["server_build"]["hnsw_build"], R["br"]["server_build"]["graph_import"], R["br"]["server_build"]["flatten_tables"],
        R["br"]["server_build"]["server_total"], R["br"]["kg"], R["br"]["kb"] / MB] for k, R in runs.items()], {1: 32})


def comp_rows(key):
    return [[MODES[k[0]], k[1], k[2], c] + [d.get(p, 0) for p in ("S", "C1", "C2")] for k, R in runs.items() for c, d in R["br"][key].items()]


def comm_rows(key):
    out = []
    for k, R in runs.items():
        for c, d in R["br"][key].items():
            g = lambda p, j: d[p][j] / MB if p in d else 0
            out.append([MODES[k[0]], k[1], k[2], c, g("S", 0), g("S", 1), g("C1", 0), g("C1", 1), g("C2", 0), g("C2", 1)])
    return out


ch = ["variant", "m", "E", "component", "Server (s)", "C1 evaluator (s)", "each other client (s)"]
sheet("Preproc_compute", ch, comp_rows("off_t"), {1: 32, 4: 44})
sheet("Online_compute", ch, comp_rows("on_t"), {1: 32, 4: 56})
hc = ["variant", "m", "E", "component", "Server sent (MB)", "Server recv (MB)", "C1 sent (MB)", "C1 recv (MB)", "other client sent (MB)", "other client recv (MB)"]
sheet("Preproc_comm", hc, comm_rows("off_b"), {1: 32, 4: 34})
sheet("Online_comm", hc, comm_rows("on_b"), {1: 32, 4: 24})


# ---- cost estimate of the all-radii optimisation (candidate vector read K: 1 -> s=6 columns, per upper iteration)
rows = []
for (mode, m, E), R in runs.items():
    cnt = R["res"]["secure"]["meters"][0]["cnt"]
    reads = {tuple(int(x) for x in k.split(":")[1:]): v for k, v in cnt.items() if isinstance(k, str) and k.startswith("rs:")}
    macs = sum(a * n * K * c for (a, n, K), c in reads.items())
    up = sum(c for (a, n, K), c in reads.items() if a == 129 and K == 1)           # candidate-vector reads of the upper phase
    Tg = R["res"]["args"]["Tg"]
    n = 1000001
    add_macs = Tg * 5 * 129 * n
    upl = sum(n_ * K * c * 4 for (a, n_, K), c in reads.items())                    # per-client upload bytes of all masked reads
    add_upl = Tg * 5 * n * 4
    bv_tot = None
    ands = R["br"]["ands"]
    rows.append([MODES[mode], m, E, macs / 1e9, add_macs / 1e9, add_macs / macs, upl / MB, add_upl / MB, add_upl / upl,
                 Tg * 5 * 128, Tg * 5 * 129 * 4 / 1e3, 12 * 6 * 110, 12 * 6 * 110 / ands, 5 * Tg / sum(K * c for (a, n_, K), c in reads.items())])
sheet("AllRadii_cost_estimate", ["variant", "m", "E", "server multiply-adds / query now (G)", "extra with all-radii (G)", "extra (relative)",
                                 "client upload / query now (MB per client)", "extra (MB per client)", "extra (relative)", "extra Beaver products / query",
                                 "extra server reply (KB)", "extra GC AND gates (rough: 12 iterations x 6 candidates x ~110)", "extra AND gates (relative)",
                                 "extra read correlations (relative)"], rows, {1: 32}, 90)

# ---- hash error / upper-phase LSH statistics of the perf runs
hr = []
for (mode, m, E), R in runs.items():
    a = R["res"]["accuracy"]; L = a["lsh"]
    if mode == "pub":
        hr.append([MODES[mode], m, E, a["nq"], L.get("hash_total", 0), L.get("hash_err", 0), L.get("hash_err", 0) / max(1, L.get("hash_total", 1)),
                   L.get("hash_bound_viol", 0), L.get("oor", 0), L.get("steps", 0), L.get("differs", 0), L.get("improve", 0), L.get("missed", 0),
                   L.get("missed", 0) / max(1, L.get("improve", 1)), L.get("empty", 0)])
    else:
        hr.append([MODES[mode], m, E, a["nq"], None, None, None, None, None, L.get("active", 0), None, L.get("improve_exists", 0), L.get("missed", 0),
                   L.get("missed", 0) / max(1, L.get("improve_exists", 1)), L.get("empty_all_radii", 0)])
sheet("LSH_hash_error", ["variant", "m", "E", "queries", "hash evaluations", "evaluations with h_hat != h_true", "hash error rate",
                         "violations of the one-bucket bound", "keys outside interpolation domain", "active upper steps",
                         "steps where quantised lookup picks a different candidate", "steps with an improving neighbour", "of which missed (premature descent)",
                         "LSH miss rate", "steps with empty lookup"], hr, {1: 32}, 76)

# ---- beam detail sheets
cache_H = {}


def Hm(m):
    if m not in cache_H:
        H = he(m)
        cache_H[m] = (H, H["slots"], H["ct_bytes"], H["ct_mult_bytes"], H["pdec_bytes"])
    return cache_H[m]


def rows_builder(R, mode, m, E):
    return None


def make_add(rows, mode, m, E, Tb):
    def add(op, srv=0.0, c1=0.0, oth=0.0, c8=0.0, ssent=0, srecv=0, c1s=0, c1r=0, os_=0, or_=0, fl=0, note=""):
        lan = max(ssent, srecv, c1s, c1r, os_, or_) / BW
        rows.append([MODES[mode], m, E, Tb, op, srv, c1, oth, c8, ssent, srecv, c1s, c1r, os_, or_, lan, fl, srv * Tb, c1 * Tb, oth * Tb, c8 * Tb,
                     ssent * Tb, srecv * Tb, c1s * Tb, c1r * Tb, os_ * Tb, or_ * Tb, lan * Tb, fl * Tb, note])
    return add


def read_rows(k, R, a_rows, K):
    mode, m, E = k
    det, res = R["det"], R["res"]
    Tb = res["args"]["Tb"] or 2 * E
    n = 1000001
    d = det["reads"][f"{a_rows}:{n}:{K}"]
    T8, T448 = d["8"], d["448"]
    H, slots, ct, ct2, pdm = Hm(m)
    ncts, rch = math.ceil(n / slots), math.ceil(a_rows / slots)
    rows = []
    add = make_add(rows, mode, m, E, Tb)
    add("1. Shared one-hot creation, %d conversion(s) of size N+1 (IDEAL functionality, cost not charged beyond the opening)" % K,
        c1s=K * 4 * (m - 1), c1r=K * 4 * (m - 1), os_=K * 4 * (m - 1), or_=K * 4 * (m - 1), fl=1,
        note="the real Lagrange conversion is O(n^2) per client at n=1M and infeasible; only the masked opening tau is charged")
    add("2. Client: masked selector e_i - r_i mod p over K*n entries", c1=T448["mask"], oth=T448["mask"], c8=T8["mask"],
        note="elementwise subtract+reduce on all client cores (448 threads); 8-core column uses 8 threads")
    add("3. Upload q_i = e_i - r_i to the server (n x K field elements per client)", srecv=m * K * n * 4, c1s=K * n * 4, os_=K * n * 4, fl=1)
    add("4. Server: add the m shares, split into 16-bit halves (_prep)", srv=T448["prep"], note="448 threads")
    add("5. Server: cache-tiled integer matrix product A . q (_tiled)", srv=T448["tiled"], note=f"{a_rows} x {n} x {K} multiply-adds, x2 for the 16-bit split")
    add("6. Server: reduce partial sums mod p (_reduce)", srv=T448["reduce"])
    add("7. Server -> C1: reply y = A q - s (a x K values)", ssent=a_rows * K * 4, c1r=a_rows * K * 4, fl=1)
    add("8. C1: out = [y] + [h] (a x K values)", c1=T448["post"], c8=T8["post"])
    cl_off = K * (ncts * H["t_enc"] + rch * (H["t_pdec_lead"] + H["t_fusion"])) / 448
    cl_off_o = K * (ncts * H["t_enc"] + rch * H["t_enc"] + rch * H["t_pdec_main"]) / 448
    srv_off = K * ((m - 1) * ncts * H["t_add"] + a_rows * ncts * (H["t_ct_pt"] + H["t_add"]) + a_rows * math.log2(slots) * H["t_ct_ct"] + (m - 1) * rch * H["t_sub"]) / 448
    add("OFFLINE (modelled, per step): (r,s,h) correlations via threshold HE for these %d read(s)" % K, srv=srv_off, c1=cl_off, oth=cl_off_o, c8=cl_off * 448 / 8,
        ssent=K * m * rch * ct2, srecv=K * (m * ncts + (m - 1) * rch) * ct, c1s=K * ncts * ct, c1r=K * rch * ct2 + K * (m - 1) * rch * pdm,
        os_=K * (ncts + rch) * ct + K * rch * pdm, or_=K * rch * ct2, fl=3,
        note="server time includes 13 rotations per matrix row priced at the ct x ct key-switch time (upper bound); modelled from OpenFHE micro-benchmarks")
    return rows


def bv_rows(k, R, bvdet):
    mode, m, E = k
    res = R["res"]
    Tb = res["args"]["Tb"] or 2 * E
    H, slots, ct, ct2, pdm = Hm(m)
    L = 16 * 128
    d = bvdet["bv"][f"beaver_dist:{L}"]
    T8, T448 = d["8"], d["448"]
    rows = []
    add = make_add(rows, mode, m, E, Tb)
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
    add("OFFLINE (modelled, per step): 2,048 Beaver triples via threshold HE (fraction of one 8,192-slot batch)", srv=srv_off, c1=cl_off, oth=cl_off_o, c8=cl_off * 448 / 8,
        ssent=m * nbatch * ct2, srecv=(m * 2 + (m - 1)) * nbatch * ct, c1s=2 * nbatch * ct, c1r=nbatch * ct2 + (m - 1) * nbatch * pdm,
        os_=3 * nbatch * ct + nbatch * pdm, or_=nbatch * ct2, fl=3, note="triples are packed 8,192 per ciphertext; a whole step uses 25% of one batch")
    return rows


hdr_d = ["variant", "m", "E", "Tb (steps)", "sub-operation", "Server time / step, 448 cores (s)", "C1 time / step, 448 cores (s)",
         "each other client time / step, 448 cores (s)", "client time / step, 8 cores (s)",
         "Server sent / step (B)", "Server recv / step (B)", "C1 sent / step (B)", "C1 recv / step (B)", "other client sent / step (B)",
         "other client recv / step (B)", "LAN transfer time / step (s)", "message flights / step",
         "Server time / query (s)", "C1 time / query (s)", "other client time / query (s)", "client 8 cores time / query (s)",
         "Server sent / query (B)", "Server recv / query (B)", "C1 sent / query (B)", "C1 recv / query (B)",
         "other sent / query (B)", "other recv / query (B)", "LAN transfer time / query (s)", "flights / query", "note"]
vec, adj, bvs = [], [], []
for k, R in runs.items():
    if R["det"] is None:
        continue
    vec += read_rows(k, R, 129, 16)
    adj += read_rows(k, R, 32, 1)
    bvd = R["det"] if "beaver_dist:2048" in R["det"]["bv"] else (runs.get(("pub", k[1], k[2])) or {}).get("det")
    if bvd and "beaver_dist:2048" in bvd["bv"]:
        bvs += bv_rows(k, R, bvd)
sheet("Beam_vector_reads", hdr_d, vec, {1: 32, 5: 80, 30: 80})
sheet("Beam_adjacency_read", hdr_d, adj, {1: 32, 5: 80, 30: 80})
sheet("Beam_Beaver_distances", hdr_d, bvs, {1: 32, 5: 80, 30: 80})

# ------------------------------------------------------------------ 5. dependence on k (performance)
rows = []
for k_, tag in ((1, "sift_N1000000_m8_E128_pub_k1"), (10, "sift_N1000000_m8_E128_pub"), (100, "sift_N1000000_m8_E128_pub_k100")):
    try:
        r = json.load(open(f"results/{tag}.json"))
        b = json.load(open(f"results/breakdown_{tag}.json")) if os.path.exists(f"results/breakdown_{tag}.json") else None
    except FileNotFoundError:
        continue
    a, sec = r["accuracy"], r["secure"]
    ands = sum(v for kk, v in sec["meters"][0]["cnt"].items() if str(kk).startswith("ands|"))
    rows.append([k_, a["recall_secure_vs_float_gt"], a["recall_hnswlib_vs_quantized_gt"], sec["identical"], sec["nperf"], ands,
                 b["gc_total_bytes"] / GB if b else None, b["flights"] if b else None, b["allb"]["S"][0] / GB if b else None, b["allb"]["C1"][0] / GB if b else None,
                 b["allb"]["C2"][0] / GB if b else None, b["busy"]["S"] if b else None, b["busy"]["C1"] if b else None, b["latency"] if b else None])
if rows:
    sheet("Perf_vs_k", ["k", "secure recall@k (1000 queries)", "plain hnswlib recall@k", "secure output identical to plain emulation (queries)", "queries run",
                        "AND gates / query (measured)", "GC size (GB)", "online message flights", "TOTAL sent Server (GB)", "TOTAL sent C1 (GB)", "TOTAL sent other client (GB)",
                        "online compute Server (s)", "online compute C1 (s)", "online latency LAN (s)"], rows, {}, 90)

# ---- hash precision study
rows = []
if os.path.exists("results/hash_precision_study.json"):
    hp = json.load(open("results/hash_precision_study.json"))
    for r in hp:
        rows.append([r["graph"], r["m"], r["E"], r["variant"], r["recall10"], r["hnswlib"], r["hnswlib"] - r["recall10"]])
    sheet("Hash_precision_vs_m", ["fixed graph #", "m", "E", "variant (mask mode)", "protocol recall@10", "plain hnswlib recall@10", "gap"], rows, {4: 24}, 62)

# ---- findings (numbers computed from the data above)
F = []
def line(t): F.append([t])
bmask = {E: stat(rec_at(S.get(("ablate", "mask", "base", 8, E), []), 10)) for E in ES}
bpub = {E: stat(rec_at(S.get(("ablate", "pub", "base", 8, E), []), 10)) for E in ES}
orc = {md: {E: stat(rec_at(S.get(("ablate", md, "oracle entry", 8, E), []), 10))[0] for E in ES} for md in ("mask", "pub")}
alr = {md: {E: stat(rec_at(S.get(("ablate", md, "all-radii", 8, E), []), 10)) for E in ES} for md in ("mask", "pub")}
pl = {E: plain("mask", 8, E, 10)[0] for E in ES}
line(f"BUILDS USED: {len(seeds)} independent builds (seeds {seeds}); each build = new multithreaded hnswlib graph + new LSH draws; 10,000 SIFT queries; recall@10 unless stated.")
line("")
mx_all = max(r[-1] for r in why_m_rows) if why_m_rows else float("nan")
mx_med = float(np.median([r[-1] for r in why_m_rows])) if why_m_rows else float("nan")
line("1. DOES RECALL IMPROVE WITH THE NUMBER OF CLIENTS?  No. Sheet Why_m_controlled: on ONE fixed graph and ONE set of tables, with identical queries, only m changed (m=1 is the exact, unquantised hash): "
     f"the largest recall@10 change over m in 1..16 is {mx_all:.3f} (median over builds and E: {mx_med:.4f}), in either direction.")
line("   m enters the protocol only through the precision of the LSH quantisation, B = 2^ceil(log2 m) (baseline) or 2^ceil(log2(m/0.1)) (public LSH): each client floors its own partial projection, so the hash is h or h-1 and the lookup probes h_hat and h_hat+1. That slightly changes WHICH bucket-mate is returned (a random +-perturbation, Hash_precision_vs_m), it does not make the walk better. With a finer B recall is the same for every m.")
line("   The apparent improvement with m in the earlier per-configuration runs came from the fact that every (m, E) run rebuilt the graph and the LSH tables (hnswlib's multithreaded build is not deterministic). Build-to-build variance is far larger than any m effect (see 2.).")
line("")
line("2. BUILD-TO-BUILD VARIANCE (baseline, E=64, m=8): " + f"secret per-node LSH mean {bmask[64][0]:.3f}, std {bmask[64][1]:.3f}, worst {bmask[64][2]:.3f}, best {bmask[64][3]:.3f};  "
     + f"public LSH mean {bpub[64][0]:.3f}, std {bpub[64][1]:.3f}, worst {bpub[64][2]:.3f}, best {bpub[64][3]:.3f};  plain hnswlib {pl[64]:.3f} on every build (std ~0.001).")
line("   Diag_rebuild_same_config (same configuration rebuilt 5 times) and Diag_LSH_draw_variance (ONE fixed graph, 5 different LSH draws): some graphs are robust (recall within ~0.5 point of plain for any LSH draw), others are fragile (same plain recall, but protocol recall 0.71-0.86 depending on the draw).")
line("")
line("3. WHERE THE GAP TO PLAIN HNSW COMES FROM: the upper-layer descent. Replacing the protocol's LSH-based entry point by the plain-HNSW greedy entry point ('oracle entry') restores plain recall on EVERY build: "
     + "; ".join(f"E={E}: secret {orc['mask'][E]:.3f} / public {orc['pub'][E]:.3f} (plain {pl[E]:.3f})" for E in ES) + ".")
line("   The layer-0 beam, the visited history, Tb = 2E and Tg = 12 are NOT the problem: Tg = 24/48, Tb = 4E and trail seeding give no gain (Optimizations sheet). The LSH lookup returns only a bucket-mate of the query (63-72% of upper steps miss an existing improving neighbour); the walk then enters layer 0 at a node ~1.6-2.3x farther than the plain-HNSW entry. On fragile graphs a beam of width E cannot escape the wrong basin (recall ceiling stays low even at E=256).")
line("")
def closed(md, E):
    b0 = (bmask if md == "mask" else bpub)[E][0]
    return (alr[md][E][0] - b0) / (pl[E] - b0) if pl[E] - b0 > 1e-9 else float("nan")
line("4. OPTIMIZATION: evaluate the candidates of ALL matching radii (up to s=6 per upper iteration) and move to the closest, instead of only the first non-empty radius. Recall@10 (mean over builds; worst build): "
     + "; ".join(f"E={E}: secret {alr['mask'][E][0]:.3f} ({alr['mask'][E][2]:.3f}), public {alr['pub'][E][0]:.3f} ({alr['pub'][E][2]:.3f}), plain {pl[E]:.3f}" for E in ES) + ".")
line("   Share of the gap to plain HNSW closed (mean over builds): " + "; ".join(f"E={E}: secret {closed('mask', E):.0%}, public {closed('pub', E):.0%}" for E in ES)
     + ". With secret per-node LSH it is essentially complete on every build (worst build within ~0.5 point of plain at E=64). With public LSH it is partial on the worst builds: one global projection draw is a single point of failure for all queries (not fixed by all-radii; untested mitigations: several independent global hash families, or the server keeps the best of several draws judged on held-out queries).")
line("   On ONE fixed graph with 5 different LSH draws each (Diag_LSH_draw_variance, 2 graphs per mode) all-radii + Tg=24 gives 0.870-0.874 vs plain 0.872-0.874 in all 20 cases.")
line("   Cost (AllRadii_cost_estimate): about +3% server multiply-adds, +3% client upload, +3% read correlations, a few thousand extra AND gates (<0.001%); the candidate-vector read goes from 1 to 6 columns per upper iteration (the beam's 16-column reads are unchanged). It is NOT implemented in the secure engine; recall is measured with the plain emulation of the protocol and the cost is derived from the engine's own per-read formulas.")
line("   Other tested knobs: finer hash precision B (removes the m-dependence; does not raise the mean), larger E (costly: beam update cost ~E^2, Perf_Summary). Not tested: narrower/more radii, several entries per bucket, graph rebuilt with larger M/efConstruction.")
line("")
line("5. RECALL FOR ALL k: Recall_vs_k (k in 1,5,10,20,50,100; k <= E; E up to 256). Performance for all (variant, m, E): Perf_Summary and the breakdown sheets; performance vs k: Perf_vs_k (the output size k only changes the final reveal circuit, so cost is k-independent to within the final circuit).")
ws = wb.create_sheet("Findings", 0)
for r in F:
    ws.append(r)
ws.column_dimensions["A"].width = 200
for row in ws.iter_rows():
    for c in row:
        c.alignment = Alignment(wrap_text=True, vertical="top")

# ------------------------------------------------------------------ notes
notes = [
    "SIFT1M (1,000,000 x 128, 10,000 queries), LAN only (10 Gbps per link, 0.1 ms RTT); server and every client use ALL 448 cores (8-core client shown in the beam detail sheets).",
    "Two protocol variants: 'secret per-node LSH (hash in GC)' = baseline, HE only in preprocessing; 'public LSH (no-GC hash)' = public global projections, hash from additive shares + local Lagrange key one-hot, hash error measured.",
    "RECALL sheets: every number comes from the plain emulation of the protocol, which was verified identical to the secure run on every sampled query. Builds are independent (build seed = column); each build re-creates the hnswlib graph (multithreaded, not deterministic) and the LSH tables.",
    "Why_m_controlled: ONE graph + tables per seed, the same 10,000 queries, only m changed (m=1 = exact hash without quantisation). Recall@10 is identical to within noise, so the number of clients does not improve recall. Why_m_build_variance / Why_m_perf_runs: when every configuration rebuilds the graph and tables, recall varies from build to build by much more than any effect of m (e.g. a poorly connected hnswlib graph or unlucky LSH constants), and this was mistaken for an m effect.",
    "Optimizations sheet: ablations on a fixed build (m=8). oracle entry = start layer 0 from the plain-HNSW greedy entry point (upper bound of what fixing the upper phase can give); all-radii = evaluate the candidate of EVERY matching radius instead of only the first non-empty radius; trail seeding = seed the beam with every candidate whose distance the upper phase computed; Tg / Tb = larger budgets. The cost of all-radii is estimated in the Notes below (not implemented in the secure engine).",
    "PERFORMANCE sheets: measured = online bytes, flights, AND-gate counts, all client/server arithmetic (micro-benchmarks on the run's shapes); modelled from native OpenFHE / emp-tool benchmarks = all preprocessing and GC evaluation / OT online time. 'Online latency' = server + C1 compute + LAN transfer, no overlap.",
    "The 9 mask-mode runs predate the per-call Beaver counters, so their Beam_Beaver_distances rows reuse the kernel timings measured in the pub-mode run with the same m (the Beaver kernel depends only on m and call size, not on the variant).",
    "The shared-ID -> one-hot conversion over N+1 columns is an IDEAL functionality (only the masked opening is charged); the real Lagrange conversion is O(n^2) and infeasible at n = 1M.",
]
ws = wb.create_sheet("Notes", 0)
for n_ in notes:
    ws.append([n_])
ws.column_dimensions["A"].width = 170
for row in ws.iter_rows():
    for c in row:
        c.alignment = Alignment(wrap_text=True, vertical="top")
wb.move_sheet("Findings", offset=-wb.index(wb["Findings"]))
wb.save(OUT)
print("wrote", OUT, wb.sheetnames)
