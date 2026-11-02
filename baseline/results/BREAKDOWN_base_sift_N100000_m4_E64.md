# base_sift_N100000_m4_E64: per-party breakdown of the baseline (rtt 0.1 ms, 10000 Mbps; server 64 cores, each client 8 cores; m=4, C1 = GC evaluator)

Baseline: exact greedy upper layers with secret-shared distances (no LSH), exact GC one-hot conversion, threshold HE used **online** for every 1-D read and for Beaver-triple generation. Offline = GC garbling + OT only. Counts (ANDs, reads, flights, bytes of GC/OT/Beaver) are exact for the executed protocol; HE/GC/OT times are modelled from calib/.

## 1. One-time preprocessing

| party | component | time |
|---|---|---|
| Server | HNSW build (hnswlib) | 1.1 s |
| Server | graph import | 188 ms |
| Server | flatten tables (upper rows + layer-0 matrices) | 348 ms |
| Server | **total (measured)** | **2.0 s** |
| each client | HE threshold keygen (modelled) | 28 ms, 4.72 MB |

Server tables: 72.30 MB (U = 14,209 upper rows, layer sizes [100000, 12404, 1575, 195, 32, 2]).

## 2. Per-query offline phase (modelled)

| component | Server | each client |
|---|---|---|
| GC garbling (92,645,970,468 AND gates) | 45.8 s | - |
| OT correlations | 12.8 s | 25.7 s |
| **total** | **58.6 s** | **25.7 s** |

GC tables to C1: **2.96 TB**; OT bytes per client: 109.63 GB.

| circuit | calls | ANDs | of which wrapper (I/O) | size |
|---|---|---|---|---|
| onehot:14209 | 36 | 957,628,170 | 927,704,016 | 30.64 GB |
| upper_step | 18 | 230,382 | 214,272 | 7.37 MB |
| beam_init | 1 | 1,756,150 | 1,756,150 | 56.20 MB |
| onehot:100001 | 256 | 91,176,053,760 | 87,694,418,944 | 2.92 TB |
| beam_update | 128 | 510,214,400 | 416,925,696 | 16.33 GB |
| final | 1 | 87,606 | 87,296 | 2.80 MB |

## 3. Online phase (per query)

### 3a. Compute

| component | Server | C1 | other clients |
|---|---|---|---|
| he_read_server | 107.2 s | - | - |
| he_triples_server | 8 ms | - | - |
| ot_send | 12.8 s | - | - |
| he_encrypt | - | 17.0 s | 18.4 s |
| he_threshold_decrypt | - | 989 ms | 745 ms |
| he_triples | - | 74 ms | 74 ms |
| gc_evaluate | - | 5.4 min | 0 ms |
| ot_receive | - | 25.7 s | 25.7 s |
| local_share_arith | - | 5 ms | 5 ms |
| **busy compute** | **2.0 min** | **6.1 min** | **45.0 s** |

### 3b. Communication (sent + received)

| category | each client (max) | server |
|---|---|---|
| beaver | 13.47 MB | 0 B |
| gc_labels | 328.90 GB | 0 B |
| gc_ot | 220.12 GB | 880.48 GB |
| gc_out | 2.65 GB | 0 B |
| he_adj | 1.04 GB | 3.97 GB |
| he_triples | 82.78 MB | 294.26 MB |
| he_up_adj | 42.59 MB | 141.88 MB |
| he_up_vec | 340.74 MB | 1.14 GB |
| he_vec | 16.68 GB | 63.49 GB |
| share_query | 792 B | 0 B |
| **total online** | **569.87 GB** | **949.51 GB** |

Rounds: **2787 flights = 1394 round trips**; 292 HE 1-D reads, 280,704 HE-generated Beaver triples. Communication time 12.7 min (rounds 139 ms, transfer 12.7 min).

**Online latency (server + C1 compute + communication, no overlap): 20.8 min.** Server idle 18.8 min, C1 idle 14.7 min.

## 4. Accuracy

recall@10 vs float ground truth 0.9586 (plaintext exact-greedy HNSW 0.9586, hnswlib 0.9586); upper phase unfinished in 0.1% of queries, mean 5.4 moves; secure == plain emulation on 8/8 sampled queries.
