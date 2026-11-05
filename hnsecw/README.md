# HNSecW-style baseline for private HNSW over vertically split queries

A third protocol to compare against, built from the design of *HNSecW: A Logarithmic-Time MPC Protocol for Approximate
Nearest Neighbor Search* (Zhang et al.) and adapted to this repo's setting: the query is vertically split over `m` clients, no
client learns the query (or anything about the database), and only the final top-k is delivered to the clients.
Nothing outside this folder is modified; it imports the shared code (hnswlib import, datasets, calibrations, `costmodel.Cfg`).

## Adaptation (the design decisions, please check them)

| | HNSecW paper | here |
|---|---|---|
| MPC parties | `s` servers, DO and querier secret-share into them | **n = m+1 parties: the server (holds the database/graph, is party 0) and the m clients**. Everything secret is additively shared among all n over F_p. This keeps the repo's threat model: up to n-1 colluding parties learn nothing beyond the output (the m clients together never hold the database) |
| query | one querier shares `q` | each client shares its own coordinate block (and block norm) among the n parties |
| output | top-k vectors to the querier | top-k rows of `D_-1` (vector + id) reconstructed by the **clients only**; the server only sees a uniformly random physical row address per result |
| search | fixed-step oblivious HNSW, per-layer shuffled tables, no ORAM | same (Alg. 2 + 3): 8 steps per upper layer, `ceil(log2(N d/D0)) + ef0 + 7` at the base, padded neighbour lists, fixed-size C/W/V arrays, reveal-and-read-locally table accesses |
| ef at base | k+10 | `--E` (default 64, same as the other protocols so recall is comparable) |
| non-linear parts | MP-SPDZ comparisons / sorting | garbled circuits with the repo's conventions (`gc_model.py`: 32 B/AND, n-share input reconstruction, all-party output masks) |

Per iteration: open `C[0]` -> local read of the shared graph row -> GC *visit* (visited check, dummy replacement, opens the
physical vector rows) -> local read of the vector rows -> Beaver squared distances (d mults per neighbour) -> GC *update*
(mask, stable sort + truncate of C and W). Dummy tables (replacement dummies, initial candidates, dummy graph rows) make every
iteration reveal exactly `deg` vector rows and one graph row; `hengine.py` **asserts that no physical row of any table is
revealed twice in a query**, which is what makes the revealed addresses uniform (Lemma 1 of the paper).

Choices that go beyond / differ from the paper text:
- The visited list `V` is treated as **public**: its entries are the physical addresses that were opened anyway, so equality tests
  against it are tests against circuit constants. (Alg. 2 keeps it as MPC state; charging its shares through the GC input wrapper
  would be strictly more expensive.) Only the prefix filled so far is scanned.
- Dummy graph rows point into a small dummy pool; repeat hits are removed by the same visited check, which is what keeps access
  uniqueness for dummy chains (the paper's padding counts do not cover this case explicitly).
- Sorting is the paper's full oblivious sort of `C` (T-1+deg entries) and `W` (ef+deg), stable on position (Batcher odd-even
  merge sort AND counts). Merging an already sorted list would be cheaper; not done.
- Only the **single-query** protocol is implemented. Multi-query (double-visited caches, amortised reshuffle) and batch-query are not.

## What is measured vs modelled
Same convention as the rest of the repo. **Executed**: the full protocol over additive shares for the sampled queries (Beaver
products, share reads, ideal GCs evaluated on reconstructed values), checked equal to the plaintext emulation, plus the access-uniqueness
assertion. **Counted exactly**: bytes per party/category, flights, AND counts, triples. **Modelled** from `calib/`: GC garble/evaluate,
OT, HE (triples), network.

Offline reshuffle (per query, because the single-query protocol needs fresh physical layouts) is modelled as: n sequential steps; in the
step of party j, each other party's share goes through a 2-party oblivious permutation with j's permutation (Waksman network,
one OT of a w-word row per switch). **This is a lower bound**: the relabelling of the pointer columns (`ga`, `vb`, neighbour ids) under
the new permutations is not charged, and the paper does not specify it. HE calibrations exist for n in {2,3,4,6,8}; other n use the next larger.

## Files
`hserver.py` tables + per-query layout, `hproto.py` plaintext oracle, `hgc.py` AND counts, `hengine.py` instrumented secure run,
`hcost.py` cost model, `hbench.py` driver, `breakdown.py` per-party report, `compare.py` three-way table, `run.sh`.

## Run (WSL, same venv as the main code)

    python hbench.py --dataset synth --N 20000 --d 32 --nq 200 --nperf 4   # smoke test, no data files
    python hbench.py --dataset sift --N 100000 --m 4 --E 64 --nq 1000 --nperf 8 && python breakdown.py results/hnsecw_sift_N100000_m4_E64.json
    python compare.py     # needs main (results/) and optionally baseline/results for the same N, m, E

Status: smoke-tested on synthetic data only (secure == plain on all sampled queries, no repeated address). SIFT/GIST runs and the
comparison table have not been produced yet.
