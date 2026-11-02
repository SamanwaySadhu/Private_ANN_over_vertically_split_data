# base_sift_N100000_m4_E128: per-party breakdown of the baseline (rtt 0.1 ms, 10000 Mbps; server 64 cores, each client 8 cores; m=4, C1 = GC evaluator)

Baseline: exact greedy upper layers with secret-shared distances (no LSH), exact GC one-hot conversion, threshold HE used **online** for every 1-D read and for Beaver-triple generation. Offline = GC garbling + OT only. Counts (ANDs, reads, flights, bytes of GC/OT/Beaver) are exact for the executed protocol; HE/GC/OT times are modelled from calib/.

## 1. One-time preprocessing

| party | component | time |
|---|---|---|
| Server | HNSW build (hnswlib) | 986 ms |
| Server | graph import | 173 ms |
| Server | flatten tables (upper rows + layer-0 matrices) | 306 ms |
| Server | **total (measured)** | **1.8 s** |
| each client | HE threshold keygen (modelled) | 28 ms, 4.72 MB |

Server tables: 72.28 MB (U = 14,169 upper rows, layer sizes [100000, 12372, 1569, 193, 32, 2]).

## 2. Per-query offline phase (modelled)

| component | Server | each client |
|---|---|---|
| GC garbling (185,365,853,476 AND gates) | 91.6 s | - |
| OT correlations | 25.7 s | 51.4 s |
| **total** | **117.3 s** | **51.4 s** |

GC tables to C1: **5.93 TB**; OT bytes per client: 219.22 GB.

| circuit | calls | ANDs | of which wrapper (I/O) | size |
|---|---|---|---|---|
| onehot:14169 | 36 | 954,932,490 | 925,092,576 | 30.56 GB |
| upper_step | 18 | 230,382 | 214,272 | 7.37 MB |
| beam_init | 1 | 3,510,006 | 3,510,006 | 112.32 MB |
| onehot:100001 | 512 | 182,352,107,520 | 175,388,837,888 | 5.84 TB |
| beam_update | 256 | 2,054,898,176 | 1,662,750,720 | 65.76 GB |
| final | 1 | 174,902 | 174,592 | 5.60 MB |

## 3. Online phase (per query)

### 3a. Compute

| component | Server | C1 | other clients |
|---|---|---|---|
| he_read_server | 3.5 min | - | - |
| he_triples_server | 16 ms | - | - |
| ot_send | 25.7 s | - | - |
| he_encrypt | - | 33.9 s | 36.6 s |
| he_threshold_decrypt | - | 1.9 s | 1.4 s |
| he_triples | - | 141 ms | 141 ms |
| gc_evaluate | - | 10.8 min | 0 ms |
| ot_receive | - | 51.4 s | 51.4 s |
| local_share_arith | - | 10 ms | 10 ms |
| **busy compute** | **3.9 min** | **12.2 min** | **89.5 s** |

### 3b. Communication (sent + received)

| category | each client (max) | server |
|---|---|---|
| beaver | 26.06 MB | 0 B |
| gc_labels | 657.67 GB | 0 B |
| gc_ot | 440.16 GB | 1.76 TB |
| gc_out | 5.28 GB | 0 B |
| he_adj | 2.09 GB | 7.94 GB |
| he_triples | 158.46 MB | 563.30 MB |
| he_up_adj | 42.59 MB | 141.88 MB |
| he_up_vec | 340.74 MB | 1.14 GB |
| he_vec | 33.36 GB | 126.97 GB |
| share_query | 792 B | 0 B |
| **total online** | **1.14 TB** | **1.90 TB** |

Rounds: **5219 flights = 2610 round trips**; 548 HE 1-D reads, 542,848 HE-generated Beaver triples. Communication time 25.3 min (rounds 261 ms, transfer 25.3 min).

**Online latency (server + C1 compute + communication, no overlap): 41.4 min.** Server idle 37.5 min, C1 idle 29.2 min.

## 4. Accuracy

recall@10 vs float ground truth 0.9864 (plaintext exact-greedy HNSW 0.9864, hnswlib 0.9864); upper phase unfinished in 0.0% of queries, mean 4.8 moves; secure == plain emulation on 8/8 sampled queries.
