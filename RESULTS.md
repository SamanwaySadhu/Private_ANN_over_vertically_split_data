# Private HNSW over vertically split queries: evaluation on SIFT1M and GIST1M

Full tables: `results/TABLES.md`. Figure: `results/fig_wan.png`. Raw data: `results/*.json`.
Reproduce: `run_all.sh`, `run_more.sh`, `kernel_scaling.py`, `seed_variance.py`, `recall_vs_E.py`, `lagrange_bench.py`, `report.py`
(interpreter: `~/miniconda3/envs/ann/bin/python`; calibrations: `calib/`).

## 0. What is measured, what is modelled

| Quantity | Status |
|---|---|
| Recall, LSH failure rate, graph and table sizes, server preprocessing time | **measured** (real data, real code) |
| Secure protocol over additive shares (Beaver products, masked 1-D reads, shared beam state) | **executed** for every sampled query. Output equals the plain emulation on 100% of sampled queries (all runs, 64 to 128 queries each; 32 for GIST1M) |
| Server 1-D-read matrix products (the dominant server work) | **measured**, multi-core numba kernels (`kernel_scaling.py`) |
| Message count, bytes per party and direction, AND-gate counts, HE-op counts | **exact counters** of the executed protocol |
| HE times and sizes (OpenFHE BFV, ring 8192, log q = 240, ciphertext 525 KB) | **modelled**: counts x native micro-benchmarks (`calib/he_calib.json`) |
| GC garble/evaluate/OT times | **modelled**: AND counts x emp-tool micro-benchmarks (`calib/gc_calib.json`: ~34M/36M AND/s per core, 32 B per AND) |
| Network time | **modelled**: `flights x RTT/2 + bytes/bandwidth`, no overlap of compute and communication |
| Offline phase (GC tables, Beaver triples, (r,s,h) read correlations) | **modelled** from the same calibrations. The repo's dealer is ideal, so none of this was run |

Garbled circuits and threshold HE remain ideal functionalities, as in `vsann.py`. Their sizes and costs come from counted gates and operations, not from executed garbling.
GIST is quantised globally to 8 bits. Recall is reported against exact kNN on the original floats.

Setup: HNSW M=8, efConstruction=100, E=64 (beam capacity and efSearch), Tb=2E, Tg=12, s=6 LSH radii, m=4 clients, k=10. Modelled party sizes: server 64 cores, each client 8 cores.

## 1. Headline results

| | SIFT 100k | SIFT 1M | GIST 100k | GIST 1M |
|---|---|---|---|---|
| recall@10, secure (one build) | 0.942 (mean over 6 builds 0.81, std 0.12, range 0.64 to 0.94) | 0.816 | 0.755 (6 builds: 0.756 +/- 0.004) | 0.572 |
| recall@10, plaintext HNSW, same graph | 0.954 | 0.876 | 0.755 | 0.569 |
| graph (ids only) / flattened server tables | 5.0 MB / 322 MB | ~50 MB / 3.2 GB | 3.2 MB / 1.19 GB | 30 MB / 11.9 GB |
| server preprocessing (448 cores) | 7.0 s | 44 s | 12.5 s | 135 s |
| garbled circuits per query | 515M ANDs = **16.5 GB** | 16.9 GB | 16.5 GB | 17.0 GB |
| online latency, LAN, packed HE | 40 s | 5.1 min | 43 s | 6.3 min |
| online latency, WAN 100 Mbps / 80 ms, packed HE | 17 min | 64 min | 17 min | 65 min |
| online latency, LAN, HE as implemented (broadcast) | 12.7 min | 2.1 h | 12.8 min | 2.1 h |
| online comm per client, packed / broadcast | 4.8 GB / 172 GB | 12.9 GB / 1.7 TB | 4.9 GB / 173 GB | 13 GB / 1.7 TB |
| offline comm per client (GC tables to P1 plus correlations) | 17 GB | 144 GB | 18 GB | 144 GB |

Four things follow from the table:

1. **The MPC does not cost accuracy.** The secure result equals the plain emulation of the same bounded algorithm, so recall is exactly that of the algorithm. GIST recall matches plain HNSW at the same E. GIST recall is low only because M=8, E=64 is a weak HNSW setting. GIST-100k recall vs beam width E (mean of 3 builds): 0.63, 0.76, 0.85, 0.92 for E = 32, 64, 128, 256.
2. **SIFT recall is unstable because of the LSH upper phase.** The same SIFT-100k, E=64 setup gives 0.64 to 0.94 across six builds. The 0.629 (m=2) vs 0.942 (m=4) gap in the tables is build noise, not an effect of m. In failing queries the LSH descent ends at an entry point about 2.2 to 2.5x farther than the exact greedy entry (checked on two seeds). The fixed-budget beam cannot always recover from that.
3. **Cost does not depend on d, apart from server compute.** Rounds, GC, and HE traffic depend on N (via U and N+1), m, and E. SIFT and GIST overlap in the WAN figure for that reason. Server compute depends on d.
4. **The HE row-selector encoding dominates the as-implemented protocol at scale.** `real_he.py` sends U broadcast ciphertexts per client per upper iteration. With U = 26.5k that is 14 GB per client per iteration, about 170 GB per query. This number is computed from the executed protocol's counts and the calibrated ciphertext size. It has not been transferred over a network. The packed variant is a model I added (see section 4), not code in the repo.

## 2. What each metric means and where it comes from

**Recall@k.** The fraction of the true k nearest neighbours returned. It is lost in three places:
- HNSW itself (M, E).
- The LSH upper phase. The server cannot show the clients the graph, so each upper-layer greedy step is replaced by a secret-keyed LSH lookup.
  - With 60% of steps missing an existing improving neighbour (the measured LSH failure rate), only 29% of (point, radius) entries survive the one-representative-per-bucket rule.
  - A premature descent gives a worse beam entry point.
- Fixed budgets (Tg upper steps, Tb beam steps). They are needed for obliviousness, because the number of steps cannot depend on the data.

**Graph size.** The plain HNSW adjacency is about N x 2M x 4 B. The server stores a *flattened* form instead:
- `theta`: A x U field elements, with A = 3 + s(d+4). It holds the per-node LSH coefficients (a, b, w, hash seeds).
- LSH dictionaries: 4 fields x s x U x ncol. Each is a cuckoo table with a stash, built per upper-layer node and radius.
- `Avec`: (d+1) x (N+1), vectors plus norms.
- `Aadj`: 2 x 2M x (N+1).

Every read touches the whole matrix, so these sizes are also the per-read server work.

**Preprocessing, server.** Measured:
- hnswlib build, 448 threads.
- Graph import.
- Flattening: LSH keys, cuckoo tables, and theta, built in parallel over all cores.

**Preprocessing, clients.** Threshold-HE key generation takes about 28 ms and ~4.7 MB per client (modelled, calibrated). Clients hold no data-dependent state.

**Offline phase per query (modelled).**
- *GC tables.* Input-independent, so garbling takes only ~0.26 s on 64 cores. The tables are 16.5 GB and go to the evaluator.
- *Beaver triples.* One per secret-shared product (273k per query for SIFT, 2.05M for GIST).
- *(r, s, h) correlations for the masked 1-D reads.* Computing h = A r + s under HE is the most expensive offline item: 15 min of server time at SIFT-100k, 107 min at GIST-100k, and 2.3 h at GIST-1M. Treat it as an upper bound. The model charges `rows x log2(slots)` rotations per read, each priced as a ct x ct key-switch.

**Latency.** This is a sum, with no overlap of compute and communication:
- Server compute: the 1-D-read matrix products plus HE server work.
- Client compute: the critical (P1) client.
- Rounds: ~907 round trips for E=64, from the message flights counted per primitive. The GC, one-hot, 1-D-read, Beaver, and HE rounds all come from the executed code path.
- Transfer: the maximum bytes over any link divided by bandwidth.

**Wait time.** A party's wait is `latency - its own busy time`, split into network time and time waiting for the peer's compute. Example from `results/TABLES.md` (SIFT-100k, WAN 100 Mbps/80 ms, packed): the server idles ~16.6 min of 17.0 min, of which 16.5 min is network.

**Per-client communication.** Bytes sent plus received by one client. Its parts:
- Masked-read uploads: n field elements per read, so N+1 per Avec read. These are the main online term.
- Beaver openings.
- GC input-label OT.
- Label forwarding from clients to the evaluator.
- HE ciphertexts.

P1 is the heaviest client because it also receives the GC tables and returns the reads' results.

**Server computation.** The 1-D read A·(e−r) is O(a x n) per read.
- Per query: ~780 vector reads over matrices of (d+1) x N, batched 16 at a time in the beam phase.
- Thread scaling (clean, idle machine): SIFT-100k takes 18.9 s on 1 thread, 3.7 s on 8, 2.1 s on 64, and 2.0 s on 128. It then stops improving, because the work is memory-bound (a 129 x 100k matrix is streamed ~800 times per query).
- GIST-1M: 3118 s on 1 thread, 431 s on 8, 117 s on 64, 68 s on 448.

**Throughput.** This is a model, `min(server CPU, client CPU, network)`, over concurrent pipelined queries. Network is the bottleneck almost everywhere. At 1 Gbps (RTT 40 ms), packed HE, N=100k, it gives 0.011 q/s, about 90 s per query of link time. Server CPU becomes the limit only above ~5 Gbps, at 0.03 to 0.04 q/s. I did not measure throughput end to end over a real network.

**Garbled-circuit size.** Exact AND counts of the executed circuits (`gc_model.py`), at 32 B per AND (half-gates). Per query for SIFT-100k, E=64:
- 515M ANDs, 16.5 GB.
- 99% of it is `beam_update`, called 128 times at 4.0M ANDs (128 MB) each.
- **82% of beam_update is the I/O wrapper, not the algorithm.** It reconstructs and re-shares the visited-history vector V (2·LV = 4098 field elements, 31 bits each) on every step. The distance-sort itself is small.
- GC size grows about linearly in E x Tb (E=32: 4.2 GB, E=128: 66 GB) and in m (m=8: 30 GB).
- Shrinking the V-history I/O is the biggest GC lever.

These AND counts rest on the standard per-primitive costs listed in `gc_model.py`, not on a synthesised netlist.

## 3. Effect of WAN bandwidth and latency (SIFT/GIST 100k, packed HE)

| | latency @ RTT 40 ms | |
|---|---|---|
| bandwidth 20 Mbps | 77 min | |
| bandwidth 100 Mbps | 16.4 min | |
| bandwidth 1 Gbps | 2.7 min | |

| | latency @ 1 Gbps | |
|---|---|---|
| RTT 10 ms | 2.2 min | |
| RTT 80 ms | 3.3 min | |
| RTT 300 ms | 6.6 min | |

- Latency is inversely proportional to bandwidth until compute takes over at roughly 5 Gbps, so the protocol is **bandwidth-bound** in a WAN. The data moved is the 1-D-read uploads (8.25 GB per client at GIST-1M, 0.83 GB at 100k), the HE ciphertexts, and GC OT/labels.
- RTT matters less. The ~907 round trips cost ~0.1 s at 0.1 ms RTT and ~73 s at 80 ms. They become visible only when RTT >= 40 ms.
- With the as-implemented HE encoding, latency is 95 min at 1 Gbps and 15 h at 100 Mbps.
- All of these exclude the offline phase.

## 4. Modelling assumptions and open issues

- **Packed HE variant.** The repo does not implement it. I assumed the row selector is sent as ceil(U/slots) ciphertexts and the server evaluates the selector contraction with 2·sqrt(U) rotations per radius, each priced as a ct x ct key-switch. That is an optimisation I assumed, not a repo feature.
- **Which party garbles.** I assumed the server garbles and client P1 evaluates. Other clients get input labels by OT and forward them to P1. Your paper's MYao may distribute this differently, and a BMR-style construction would scale GC size with m.
- **Ideal one-hot conversion.** Execution uses the ideal functionality (reveal and re-share), as in the repo's default. I charge only the opening. The real Sec. 4 Lagrange conversion is O(n^2) work and memory per client (measured at 2.8 s and 400 MB for n=4096, empirical exponent ~2.6). At n = N+1 = 100k, and also at n = U (~26k), it is not feasible with this implementation. That means one-hot conversion client compute is **not** included in any reported time. If the paper uses another construction for large domains, its cost needs adding.
- **HE parallelism.** OpenFHE's own multithreading scales poorly (ct x ct ~3x on 8 threads). I assumed task parallelism across independent ciphertexts, dividing op counts by the party's cores. Memory bandwidth may break this at full scale.
- **Non-HE server work.** Client-local share arithmetic in the simulator is single-threaded numpy (25 s per query at GIST-1M). Counted as client time, so client compute is somewhat overstated for large N.
- **Sampled queries.** The secure engine ran 128 queries at 100k, 64 at SIFT-1M, and 32 at GIST-1M. Accuracy used 1000 queries per run. Communication and AND counts are deterministic (identical per query), so only compute time varies across the sample.
- **Recall variance.** SIFT recall depends strongly on the random LSH tables (std 0.12 over 6 builds at 100k). Differences between rows of the m/E sweeps in `results/TABLES.md` for SIFT are within that noise unless stated otherwise.
- **Memory-bandwidth scaling.** At 1M, SIFT stops speeding up past ~128 threads and GIST past ~448. I did not break that limit down further.
