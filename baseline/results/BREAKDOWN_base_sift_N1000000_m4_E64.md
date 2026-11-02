# base_sift_N1000000_m4_E64: per-party breakdown of the baseline (rtt 0.1 ms, 10000 Mbps; server 64 cores, each client 8 cores; m=4, C1 = GC evaluator)

Baseline: exact greedy upper layers with secret-shared distances (no LSH), exact GC one-hot conversion, threshold HE used **online** for every 1-D read and for Beaver-triple generation. Offline = GC garbling + OT only. Counts (ANDs, reads, flights, bytes of GC/OT/Beaver) are exact for the executed protocol; HE/GC/OT times are modelled from calib/.

## 1. One-time preprocessing

| party | component | time |
|---|---|---|
| Server | HNSW build (hnswlib) | 10.9 s |
| Server | graph import | 1.7 s |
| Server | flatten tables (upper rows + layer-0 matrices) | 4.9 s |
| Server | **total (measured)** | **24.0 s** |
| each client | HE threshold keygen (modelled) | 28 ms, 4.72 MB |

Server tables: 723.30 MB (U = 142,618 upper rows, layer sizes [1000000, 124500, 15852, 1962, 271, 26, 5, 1]).

## 2. Per-query offline phase (modelled)

| component | Server | each client |
|---|---|---|
| GC garbling (931,738,244,172 AND gates) | 7.7 min | - |
| OT correlations | 2.1 min | 4.3 min |
| **total** | **9.8 min** | **4.3 min** |

GC tables to C1: **29.82 TB**; OT bytes per client: 1.10 TB.

| circuit | calls | ANDs | of which wrapper (I/O) | size |
|---|---|---|---|---|
| onehot:142618 | 48 | 12,938,378,616 | 12,414,685,320 | 414.03 GB |
| upper_step | 24 | 308,520 | 285,696 | 9.87 MB |
| beam_init | 1 | 1,756,150 | 1,756,150 | 56.20 MB |
| onehot:1000001 | 256 | 918,273,660,288 | 876,929,618,944 | 29.38 TB |
| beam_update | 128 | 524,052,992 | 416,925,696 | 16.77 GB |
| final | 1 | 87,606 | 87,296 | 2.80 MB |

## 3. Online phase (per query)

### 3a. Compute

| component | Server | C1 | other clients |
|---|---|---|---|
| he_read_server | 6.5 min | - | - |
| he_triples_server | 9 ms | - | - |
| ot_send | 2.1 min | - | - |
| he_encrypt | - | 2.7 min | 2.7 min |
| he_threshold_decrypt | - | 1.0 s | 762 ms |
| he_triples | - | 76 ms | 76 ms |
| gc_evaluate | - | 54.1 min | 0 ms |
| ot_receive | - | 4.3 min | 4.3 min |
| local_share_arith | - | 5 ms | 5 ms |
| **busy compute** | **8.6 min** | **61.1 min** | **7.0 min** |

### 3b. Communication (sent + received)

| category | each client (max) | server |
|---|---|---|
| beaver | 13.77 MB | 0 B |
| gc_labels | 3.29 TB | 0 B |
| gc_ot | 2.20 TB | 8.80 TB |
| gc_out | 26.49 GB | 0 B |
| he_adj | 8.44 GB | 33.56 GB |
| he_triples | 85.14 MB | 302.67 MB |
| he_up_adj | 258.54 MB | 996.15 MB |
| he_up_vec | 2.07 GB | 7.97 GB |
| he_vec | 135.04 GB | 536.92 GB |
| share_query | 792 B | 0 B |
| **total online** | **5.66 TB** | **9.38 TB** |

Rounds: **2901 flights = 1450 round trips**; 304 HE 1-D reads, 286,848 HE-generated Beaver triples. Communication time 2.1 h (rounds 145 ms, transfer 2.1 h).

**Online latency (server + C1 compute + communication, no overlap): 3.2 h.** Server idle 3.1 h, C1 idle 2.2 h.

## 4. Accuracy

recall@10 vs float ground truth 0.8729 (plaintext exact-greedy HNSW 0.8731, hnswlib 0.8730); upper phase unfinished in 0.0% of queries, mean 6.0 moves; secure == plain emulation on 8/8 sampled queries.
