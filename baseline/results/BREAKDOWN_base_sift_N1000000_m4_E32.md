# base_sift_N1000000_m4_E32: per-party breakdown of the baseline (rtt 0.1 ms, 10000 Mbps; server 64 cores, each client 8 cores; m=4, C1 = GC evaluator)

Baseline: exact greedy upper layers with secret-shared distances (no LSH), exact GC one-hot conversion, threshold HE used **online** for every 1-D read and for Beaver-triple generation. Offline = GC garbling + OT only. Counts (ANDs, reads, flights, bytes of GC/OT/Beaver) are exact for the executed protocol; HE/GC/OT times are modelled from calib/.

## 1. One-time preprocessing

| party | component | time |
|---|---|---|
| Server | HNSW build (hnswlib) | 11.9 s |
| Server | graph import | 1.8 s |
| Server | flatten tables (upper rows + layer-0 matrices) | 4.8 s |
| Server | **total (measured)** | **25.1 s** |
| each client | HE threshold keygen (modelled) | 28 ms, 4.72 MB |

Server tables: 723.25 MB (U = 142,536 upper rows, layer sizes [1000000, 124481, 15815, 1945, 264, 25, 4, 1]).

## 2. Per-query offline phase (modelled)

| component | Server | each client |
|---|---|---|
| GC garbling (472,199,607,756 AND gates) | 3.9 min | - |
| OT correlations | 65.0 s | 2.2 min |
| **total** | **5.0 min** | **2.2 min** |

GC tables to C1: **15.11 TB**; OT bytes per client: 555.06 GB.

| circuit | calls | ANDs | of which wrapper (I/O) | size |
|---|---|---|---|---|
| onehot:142536 | 48 | 12,930,939,576 | 12,407,547,384 | 413.79 GB |
| upper_step | 24 | 308,520 | 285,696 | 9.87 MB |
| beam_init | 1 | 879,222 | 879,222 | 28.14 MB |
| onehot:1000001 | 128 | 459,136,830,144 | 438,464,809,472 | 14.69 TB |
| beam_update | 64 | 130,606,336 | 104,850,432 | 4.18 GB |
| final | 1 | 43,958 | 43,648 | 1.41 MB |

## 3. Online phase (per query)

### 3a. Compute

| component | Server | C1 | other clients |
|---|---|---|---|
| he_read_server | 3.3 min | - | - |
| he_triples_server | 5 ms | - | - |
| ot_send | 65.0 s | - | - |
| he_encrypt | - | 82.0 s | 82.8 s |
| he_threshold_decrypt | - | 552 ms | 415 ms |
| he_triples | - | 42 ms | 42 ms |
| gc_evaluate | - | 27.4 min | 0 ms |
| ot_receive | - | 2.2 min | 2.2 min |
| local_share_arith | - | 3 ms | 3 ms |
| **busy compute** | **4.4 min** | **30.9 min** | **3.6 min** |

### 3b. Communication (sent + received)

| category | each client (max) | server |
|---|---|---|
| beaver | 7.48 MB | 0 B |
| gc_labels | 1.67 TB | 0 B |
| gc_ot | 1.11 TB | 4.46 TB |
| gc_out | 13.43 GB | 0 B |
| he_adj | 4.22 GB | 16.78 GB |
| he_triples | 47.30 MB | 168.15 MB |
| he_up_adj | 258.54 MB | 996.15 MB |
| he_up_vec | 2.07 GB | 7.97 GB |
| he_vec | 67.52 GB | 268.46 GB |
| share_query | 792 B | 0 B |
| **total online** | **2.87 TB** | **4.75 TB** |

Rounds: **1685 flights = 842 round trips**; 176 HE 1-D reads, 155,776 HE-generated Beaver triples. Communication time 63.4 min (rounds 84 ms, transfer 63.4 min).

**Online latency (server + C1 compute + communication, no overlap): 98.7 min.** Server idle 94.3 min, C1 idle 67.8 min.

## 4. Accuracy

recall@10 vs float ground truth 0.7668 (plaintext exact-greedy HNSW 0.7668, hnswlib 0.7669); upper phase unfinished in 0.0% of queries, mean 5.9 moves; secure == plain emulation on 8/8 sampled queries.
