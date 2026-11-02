# base_sift_N100000_m8_E64: per-party breakdown of the baseline (rtt 0.1 ms, 10000 Mbps; server 64 cores, each client 8 cores; m=8, C1 = GC evaluator)

Baseline: exact greedy upper layers with secret-shared distances (no LSH), exact GC one-hot conversion, threshold HE used **online** for every 1-D read and for Beaver-triple generation. Offline = GC garbling + OT only. Counts (ANDs, reads, flights, bytes of GC/OT/Beaver) are exact for the executed protocol; HE/GC/OT times are modelled from calib/.

## 1. One-time preprocessing

| party | component | time |
|---|---|---|
| Server | HNSW build (hnswlib) | 840 ms |
| Server | graph import | 162 ms |
| Server | flatten tables (upper rows + layer-0 matrices) | 290 ms |
| Server | **total (measured)** | **1.6 s** |
| each client | HE threshold keygen (modelled) | 31 ms, 4.72 MB |

Server tables: 72.28 MB (U = 14,173 upper rows, layer sizes [100000, 12359, 1584, 196, 31, 2]).

## 2. Per-query offline phase (modelled)

| component | Server | each client |
|---|---|---|
| GC garbling (174,865,605,468 AND gates) | 86.4 s | - |
| OT correlations | 25.7 s | 25.7 s |
| **total** | **112.1 s** | **25.7 s** |

GC tables to C1: **5.60 TB**; OT bytes per client: 109.63 GB.

| circuit | calls | ANDs | of which wrapper (I/O) | size |
|---|---|---|---|---|
| onehot:14173 | 36 | 1,809,383,994 | 1,779,535,656 | 57.90 GB |
| upper_step | 18 | 458,046 | 441,936 | 14.66 MB |
| beam_init | 1 | 3,377,326 | 3,377,326 | 108.07 MB |
| onehot:100001 | 256 | 172,124,872,704 | 168,643,237,888 | 5.51 TB |
| beam_update | 128 | 927,330,560 | 834,041,856 | 29.67 GB |
| final | 1 | 182,838 | 182,528 | 5.85 MB |

## 3. Online phase (per query)

### 3a. Compute

| component | Server | C1 | other clients |
|---|---|---|---|
| he_read_server | 107.7 s | - | - |
| he_triples_server | 9 ms | - | - |
| ot_send | 25.7 s | - | - |
| he_encrypt | - | 17.0 s | 18.4 s |
| he_threshold_decrypt | - | 1.0 s | 740 ms |
| he_triples | - | 73 ms | 73 ms |
| gc_evaluate | - | 10.1 min | 0 ms |
| ot_receive | - | 25.7 s | 25.7 s |
| local_share_arith | - | 4 ms | 4 ms |
| **busy compute** | **2.2 min** | **10.9 min** | **44.9 s** |

### 3b. Communication (sent + received)

| category | each client (max) | server |
|---|---|---|
| beaver | 31.44 MB | 0 B |
| gc_labels | 767.41 GB | 0 B |
| gc_ot | 220.12 GB | 1.76 TB |
| gc_out | 6.17 GB | 0 B |
| he_adj | 1.18 GB | 8.00 GB |
| he_triples | 82.78 MB | 588.52 MB |
| he_up_adj | 61.55 MB | 293.21 MB |
| he_up_vec | 492.38 MB | 2.35 GB |
| he_vec | 18.84 GB | 128.05 GB |
| share_query | 952 B | 0 B |
| **total online** | **1.01 TB** | **1.90 TB** |

Rounds: **2787 flights = 1394 round trips**; 292 HE 1-D reads, 280,704 HE-generated Beaver triples. Communication time 25.3 min (rounds 139 ms, transfer 25.3 min).

**Online latency (server + C1 compute + communication, no overlap): 38.4 min.** Server idle 36.2 min, C1 idle 27.6 min.

## 4. Accuracy

recall@10 vs float ground truth 0.9582 (plaintext exact-greedy HNSW 0.9582, hnswlib 0.9582); upper phase unfinished in 0.2% of queries, mean 5.5 moves; secure == plain emulation on 8/8 sampled queries.
