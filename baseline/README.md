# Baseline: private HNSW without LSH, Lagrange one-hot, or offline HE

Same setting as the main protocol (server holds the database and the HNSW graph, `m` clients hold additive shares of the
query, vertically split). Three changes, everything else (graph, beam search + fused GC update, Beaver distances, GC
conventions, calibrations, metering) is reused from the parent directory unchanged.

| | main protocol | baseline |
|---|---|---|
| upper layers | per-node secret LSH + cuckoo dictionaries, 2-D reads | exact greedy HNSW descent on secret-shared state: read neighbour row, read neighbour vectors, Beaver squared distances, GC argmin / move / descend (`upper_step`) |
| shared ID -> shared one-hot | Lagrange / alpha-powers (Sec. 4), 1 opening | exact garbled circuit: `n` equality tests against constants, every bit output as an F_p additive share through the all-client mask wrapper (`onehot:<n>`) |
| 1-D read `A e` | masked read with (r, s, h = A r + s) correlations made with HE **in preprocessing** | HE **online**: clients encrypt their shares of `e`, server computes `A . Enc(e)` (ct-pt products, folded slot sums), adds clients' encrypted masks, threshold decryption to P1 |
| Beaver triples | HE, preprocessing | HE, online (one batch of 3 flights at query start) |
| preprocessing left | GC garbling, OT, HE correlations | GC garbling + OT only (HE keygen is one-time) |

Upper-layer tables: one row per (node, level >= 1) with `M` neighbour row ids and a down pointer (`Aup_adj`), and a
vector/norm/node-id table (`Aup_vec`), both over domain `U` (~N/7). Layer 0 is the original `Aadj` / `Avec` over `N+1`.
Upper step budget `Tg = 3*top + 3` (descents + moves; 0% of queries unfinished at N=1M).

## Files
- `bserver.py` server tables (hnswlib import, no LSH) and a plaintext HNSW reference
- `bproto.py` the bounded plaintext algorithm (`upper_step`, `plain_baseline`): oracle for the secure run
- `bgc.py` AND counts of the new circuits (`upper_step`, `onehot:<n>`), extends `gc_model.GCModel`
- `bengine.py` instrumented secure execution (additive shares, Beaver, GC/HE as metered ideal functionalities)
- `bcost.py` cost model: HE online, GC/OT offline, from `../calib`
- `bbench.py` driver, `breakdown.py` per-party report, `compare.py` baseline vs main, `run.sh` reproduces everything
- `results/` raw JSON, logs, `BREAKDOWN_*.md`, `COMPARE.md`

## What is measured vs modelled
Same as the main code. Measured/exact: recall (secure run == plaintext emulation on the sampled queries, checked), graph and
table sizes, server preprocessing time, every message/byte/flight count of GC/OT/Beaver, AND counts, HE read counts and shapes.
Modelled from `calib/`: HE op times, GC garble/evaluate, OT, network. Garbled circuits and HE are ideal functionalities inside
the simulation; the one-hot is held as its index inside the simulator (the metered cost is that of the full n-element circuit).

## Cost-model choices to know about
- One-hot output wrapper: 3·l·m + l ANDs and `m·l` OT input bits per output element (the same wrapper the main protocol
  charges every circuit). It is ~97% of all GC cost: a 1M-element one-hot is ~4e8 ANDs (~13 GB of tables). A cheaper bit-output +
  B2A design would change the baseline's numbers by orders of magnitude; it is not what was asked for ("use GC") so it is not modelled.
- HE slot sums use folding (a-1 + log2(slots/a) rotations); a rotation is charged at the calibrated ct*ct+relin time
  (no rotation microbenchmark exists), so HE server time is an upper bound.
- No overlap of server/client compute and communication in the latency (as in the main model); GC tables are offline.
- Recall differs slightly between runs at equal parameters because hnswlib's multi-threaded build is not deterministic.

## Headline (SIFT1M, m=4, E=64, LAN 10 Gbps/0.1 ms; see `results/COMPARE.md`)
recall@10 0.873 (main: 0.781, no LSH misses) at ~3.2 h online latency, 5.7 TB online comm per client, 29.8 TB of GC tables offline
(main: 5.1 min, 12.9 GB, 16.9 GB).
