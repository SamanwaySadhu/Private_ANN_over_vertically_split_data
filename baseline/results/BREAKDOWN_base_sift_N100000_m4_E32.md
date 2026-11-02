# base_sift_N100000_m4_E32: per-party breakdown of the baseline (rtt 0.1 ms, 10000 Mbps; server 64 cores, each client 8 cores; m=4, C1 = GC evaluator)

Baseline: exact greedy upper layers with secret-shared distances (no LSH), exact GC one-hot conversion, threshold HE used **online** for every 1-D read and for Beaver-triple generation. Offline = GC garbling + OT only. Counts (ANDs, reads, flights, bytes of GC/OT/Beaver) are exact for the executed protocol; HE/GC/OT times are modelled from calib/.

## 1. One-time preprocessing

| party | component | time |
|---|---|---|
| Server | HNSW build (hnswlib) | 990 ms |
| Server | graph import | 160 ms |
| Server | flatten tables (upper rows + layer-0 matrices) | 280 ms |
| Server | **total (measured)** | **1.7 s** |
| each client | HE threshold keygen (modelled) | 28 ms, 4.72 MB |

Server tables: 72.31 MB (U = 14,219 upper rows, layer sizes [100000, 12412, 1578, 194, 32, 2]).

## 2. Per-query offline phase (modelled)

| component | Server | each client |
|---|---|---|
| GC garbling (46,674,690,084 AND gates) | 23.1 s | - |
| OT correlations | 6.5 s | 12.9 s |
| **total** | **29.5 s** | **12.9 s** |

GC tables to C1: **1.49 TB**; OT bytes per client: 55.25 GB.

| circuit | calls | ANDs | of which wrapper (I/O) | size |
|---|---|---|---|---|
| onehot:14219 | 36 | 958,302,090 | 928,356,876 | 30.67 GB |
| upper_step | 18 | 230,382 | 214,272 | 7.37 MB |
| beam_init | 1 | 879,222 | 879,222 | 28.14 MB |
| onehot:100001 | 128 | 45,588,026,880 | 43,847,209,472 | 1.46 TB |
| beam_update | 64 | 127,207,552 | 104,850,432 | 4.07 GB |
| final | 1 | 43,958 | 43,648 | 1.41 MB |

## 3. Online phase (per query)

### 3a. Compute

| component | Server | C1 | other clients |
|---|---|---|---|
| he_read_server | 56.2 s | - | - |
| he_triples_server | 4 ms | - | - |
| ot_send | 6.5 s | - | - |
| he_encrypt | - | 8.6 s | 9.4 s |
| he_threshold_decrypt | - | 529 ms | 398 ms |
| he_triples | - | 40 ms | 40 ms |
| gc_evaluate | - | 2.7 min | 0 ms |
| ot_receive | - | 12.9 s | 12.9 s |
| local_share_arith | - | 3 ms | 3 ms |
| **busy compute** | **62.7 s** | **3.1 min** | **22.8 s** |

### 3b. Communication (sent + received)

| category | each client (max) | server |
|---|---|---|
| beaver | 7.18 MB | 0 B |
| gc_labels | 165.75 GB | 0 B |
| gc_ot | 110.93 GB | 443.73 GB |
| gc_out | 1.33 GB | 0 B |
| he_adj | 521.31 MB | 1.98 GB |
| he_triples | 44.94 MB | 159.74 MB |
| he_up_adj | 42.59 MB | 141.88 MB |
| he_up_vec | 340.74 MB | 1.14 GB |
| he_vec | 8.34 GB | 31.74 GB |
| share_query | 792 B | 0 B |
| **total online** | **287.31 GB** | **478.89 GB** |

Rounds: **1571 flights = 786 round trips**; 164 HE 1-D reads, 149,632 HE-generated Beaver triples. Communication time 6.4 min (rounds 79 ms, transfer 6.4 min).

**Online latency (server + C1 compute + communication, no overlap): 10.5 min.** Server idle 9.5 min, C1 idle 7.4 min.

## 4. Accuracy

recall@10 vs float ground truth 0.8841 (plaintext exact-greedy HNSW 0.8841, hnswlib 0.8841); upper phase unfinished in 0.0% of queries, mean 5.3 moves; secure == plain emulation on 8/8 sampled queries.
