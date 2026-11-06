# Panther baseline for private ANN over vertically split queries

A fourth protocol to compare against, built from *Panther: Private Approximate Nearest Neighbor Search in the Single Server
Setting* (Li et al., CCS'25; reference implementation <https://github.com/AntCPLab/OpenPanther>) and adapted to this repo's
setting: the query is vertically split over `m` clients, **no client learns the query (or any intermediate value) and nobody
learns the database; the only thing the clients learn is the final top-k ids.** Nothing outside this folder is modified; it
imports the shared code (`vsann.MPC`/`P`, `gc_model.bits`, `datasets`, `costmodel.Cfg/load_cal`, `../calib`).

Same convention as `hnsecw/` and `baseline/`: an instrumented simulation (additive shares executed, HE/GC as metered ideal
functionalities) plus a cost model calibrated from `../calib`. This is **not** a port of the OpenPanther C++ code (SecretFlow +
EMP, 2-party); the paper's protocol is re-implemented at the level of its data flow, message sizes and operation counts.

## Panther in one paragraph
k-means into `t` clusters padded to `mc` points. Per query the server shuffles the cluster index map (free: every cluster is
coefficient-encoded in its own BFV plaintexts). Distances to the `t` centroids by HE (client encrypts `q`, server does ct*pt, H2A
re-sharing, no noise flooding). Approximate top-`u` (bin minima + selection network) gives shared *shuffled* positions, which are
revealed to the client (pseudorandom: the server alone knows the shuffle). A 3-way-cuckoo batch PIR (`B = 1.5u` buckets, SealPIR
2-D with `p'=q1` so the 2-D response can be re-shared) fetches the `u` clusters **as secret shares**. Distances to the retrieved
`B*mc` points by HE + local product + OT wrap-bit correction. Exact top-k by a selection network in GC. Top-k ids revealed.

## Adaptation to `m` clients (the design decisions, please check them)

| | Panther paper | here |
|---|---|---|
| parties | server S, one client C | **n = m+1: server (party 0) + m clients**; client 1 additionally queries the PIR, fuses partial decryptions, evaluates the GCs |
| HE keys | C's key | joint public key per parameter set, **secret key m-of-m threshold-shared among the clients** (S never decrypts, no single client can). Calibration = OpenFHE threshold-BFV (`calib/he_calib.json`) |
| query | C encrypts `q` | client `i` encrypts its coordinate block `q_i` (constant polynomials, as in Sec. 7.3.1) and shares `\|\|q_i\|\|^2` among the n parties. Same ciphertexts serve centroid and point distances |
| shared values | 2-party additive shares | additive among all n parties (GC wrapper reconstructs n shares, all-party output masks: `gc_model` conventions) |
| retrieved points | C holds one share, S the other | **block-aligned**: coordinate `j` of block `i` is shared between S and client `i` only. Client 1 receives the masked PIR output, keeps block 1, forwards block `i` to client `i`. Then `<q,v> = sum_i <q_i, v_S[i]>` (HE, server share) `+ sum_i <q_i, v_C[i]>` (local at client `i`): Sec. 7.3.2 verbatim per block, **no client-to-client multiplication**. Norms and ids are re-shared by client 1 among all clients |
| wrap-bit correction | OT between S and C | one OT per (point, coordinate) between S and the block owner |
| revealed cluster positions | to C | **to client 1 only** (uniform distinct values for anyone not knowing the server's permutation: simulatable) |
| output | k ids to C | k ids opened to the evaluator (client 1), forwarded to the other clients; server learns nothing |
| non-linear parts | SS comparisons (silent OT) for bin minima, GC for exact top-k | **GC for both** (with the n-party wrapper): the SS comparison protocol is 2-party and has no n-party counterpart in this repo; reconstructing to 2 shares would let server+one client open every intermediate |

Security statement of this adaptation: semi-honest, as in Panther. Corrupt server alone, or any set of clients not containing
client 1 together with the server, learns nothing beyond the output. **Caveat inherited from Panther's design**: client 1 sees
the (pseudorandom) shuffled cluster positions and the PIR output shares; colluding with the server it would learn which clusters
were selected. Panther does not defend against this either (its single client sees the same). Removing it requires computing the
encrypted PIR selectors from shared indices, which is the open problem Panther's shuffle-and-reveal was designed to avoid.

## What is measured vs modelled
**Executed**: the full protocol over additive F_p shares for the sampled queries (shuffle, share arithmetic, block-aligned shares,
distances from shares, cuckoo batch code with real buckets, GCs and HE evaluated as ideal functionalities on reconstructed values),
checked equal to the plaintext emulation `pproto.plain_search`. Recall is measured on all queries with the plain emulation.
**Counted exactly**: bytes per party/category, flights, AND counts (exact comparator counts of the selection networks for
arbitrary `n, k`), wrap OTs, PIR geometry. **Modelled** from `calib/`: GC garble/evaluate, OT, HE (times scaled from the
N=8192/4x60-bit OpenFHE calibration to Panther's own parameters of Table 6 by N*log q, key-switch by N*L^2; sizes analytic),
network.

## Cost-model choices to know about
- **Not charged (all favour Panther)**: HE key generation, threshold-decryption smudging noise, the paper's 1-bit H2A error fix
  (Sec. 7.2 truncation), one-time database encoding, the SealPIR Galois keys. The Z_{2^k} plaintext ring of the paper is replaced by F_p
  (the repo's field) for execution; only the HE sizes/counts follow the paper's parameters.
- The multi-client overhead is concentrated in PIR: every PIR response polynomial must be threshold-decrypted twice (outer layer
  `sk'`, then recovered inner layer `sk`) with partial decryptions of all clients going to client 1 (`pir_dec1`, `pir_dec2`
  rows of the breakdown), and the server's response polys go to all clients (`pir_resp`).
- GC wrapper: 3l(n-1)+2l ANDs per input element (l = 31), as in the other protocols. For this protocol it is 65-75% of all ANDs.
  Panther's 2-party numbers (paper Table 9) are therefore not comparable with these without that convention.
- Online latency = server compute + client-1 compute + RTT/2 per flight + max-party bytes/BW, no overlap (same as the other models).
- Wrap OTs use silent (Ferret) COT as in the paper (0.19 B/OT offline, calibrated rate) + 3 B/OT online.
- `--cap 1.5` (default) limits cluster size to 1.5 N/t by moving overflow points to the next closest centroid, so padding to `mc`
  does not blow up the PIR database; `--cap 0` pads to the largest k-means cluster as the paper does. Hyperparameters `t = sqrt(N)`,
  `k' = u/0.01 bins` (capped at t), `u` is the recall knob (`--sweep_u`). Extra random clusters returned by the batch code
  (`B = 1.5u` clusters for `u` wanted) do enter the top-k, as in the real protocol, so measured recall includes them.
- Cuckoo insertion failures are counted (`cuckoo_failed`) and the cluster that failed is dropped (recall impact is in the measurement).

## Files
`pserver.py` k-means, capacity-constrained clusters, batch-code buckets; `pproto.py` plaintext oracle (shuffle, ApproxTopK,
cuckoo plan, top-k); `phe.py` HE parameter sets and PIR geometry; `pgc.py` AND counts (selection networks); `pengine.py`
instrumented secure run; `pcost.py` cost model; `pbench.py` driver; `breakdown.py` per-party report; `compare.py` table against
main / exact-greedy / HNSecW-style when their results exist; `run.sh`.

## Run (any Python with numpy; hnswlib is **not** needed)

    python pbench.py --dataset synth --N 20000 --d 32 --nq 200 --nperf 4          # smoke test, no data files
    python pbench.py --dataset sift --N 1000000 --sweep_u 4,8,12,16,24            # recall vs u (needs ANN_DATA / ~/ann_data)
    python pbench.py --dataset sift --N 1000000 --m 4 --u 12 --nq 1000 --nperf 8 && python breakdown.py results/panther_sift_N1000000_m4_u12.json
    python compare.py

Status: smoke-tested on synthetic data only (secure == plain emulation on all sampled queries). The SIFT runs, the choice of `u`
that matches the other protocols' recall, and the comparison table have not been produced (no dataset files where this was written).
