# base_sift_N1000000_m8_E32: per-party breakdown of the baseline (rtt 0.1 ms, 10000 Mbps; server 64 cores, each client 8 cores; m=8, C1 = GC evaluator)

Baseline: exact greedy upper layers with secret-shared distances (no LSH), exact GC one-hot conversion, threshold HE used **online** for every 1-D read and for Beaver-triple generation. Offline = GC garbling + OT only. Counts (ANDs, reads, flights, bytes of GC/OT/Beaver) are exact for the executed protocol; HE/GC/OT times are modelled from calib/.

## 1. One-time preprocessing

| party | component | time |
|---|---|---|
| Server | HNSW build (hnswlib) | 11.6 s |
| Server | graph import | 1.7 s |
| Server | flatten tables (upper rows + layer-0 matrices) | 4.1 s |
| Server | **total (measured)** | **22.6 s** |
| each client | HE threshold keygen (modelled) | 31 ms, 4.72 MB |

Server tables: 723.29 MB (U = 142,614 upper rows, layer sizes [1000000, 124526, 15838, 1955, 264, 25, 4, 1]).

## 2. Per-query offline phase (modelled)

| component | Server | each client |
|---|---|---|
| GC garbling (888,509,002,404 AND gates) | 7.3 min | - |
| OT correlations | 2.2 min | 2.2 min |
| **total** | **9.5 min** | **2.2 min** |

GC tables to C1: **28.43 TB**; OT bytes per client: 555.07 GB.

| circuit | calls | ANDs | of which wrapper (I/O) | size |
|---|---|---|---|---|
| onehot:142614 | 48 | 24,397,416,216 | 23,873,737,608 | 780.72 GB |
| upper_step | 24 | 612,072 | 589,248 | 19.59 MB |
| beam_init | 1 | 1,690,926 | 1,690,926 | 54.11 MB |
| onehot:1000001 | 128 | 863,873,639,616 | 843,201,618,944 | 27.64 TB |
| beam_update | 64 | 235,552,000 | 209,796,096 | 7.54 GB |
| final | 1 | 91,574 | 91,264 | 2.93 MB |

## 3. Online phase (per query)

### 3a. Compute

| component | Server | C1 | other clients |
|---|---|---|---|
| he_read_server | 3.3 min | - | - |
| he_triples_server | 5 ms | - | - |
| ot_send | 2.2 min | - | - |
| he_encrypt | - | 81.7 s | 82.5 s |
| he_threshold_decrypt | - | 568 ms | 413 ms |
| he_triples | - | 42 ms | 42 ms |
| gc_evaluate | - | 51.6 min | 0 ms |
| ot_receive | - | 2.2 min | 2.2 min |
| local_share_arith | - | 2.0 s | 2.0 s |
| **busy compute** | **5.5 min** | **55.1 min** | **3.6 min** |

### 3b. Communication (sent + received)

| category | each client (max) | server |
|---|---|---|
| beaver | 17.45 MB | 0 B |
| gc_labels | 3.89 TB | 0 B |
| gc_ot | 1.11 TB | 8.92 TB |
| gc_out | 31.33 GB | 0 B |
| he_adj | 4.29 GB | 33.59 GB |
| he_triples | 47.30 MB | 336.30 MB |
| he_up_adj | 283.81 MB | 2.00 GB |
| he_up_vec | 2.27 GB | 16.04 GB |
| he_vec | 68.60 GB | 537.45 GB |
| share_query | 952 B | 0 B |
| **total online** | **5.11 TB** | **9.51 TB** |

Rounds: **1685 flights = 842 round trips**; 176 HE 1-D reads, 155,776 HE-generated Beaver triples. Communication time 2.1 h (rounds 84 ms, transfer 2.1 h).

**Online latency (server + C1 compute + communication, no overlap): 3.1 h.** Server idle 3.0 h, C1 idle 2.2 h.

## 4. Accuracy

recall@10 vs float ground truth 0.7717 (plaintext exact-greedy HNSW 0.7717, hnswlib 0.7717); upper phase unfinished in 0.0% of queries, mean 5.8 moves; secure == plain emulation on 8/8 sampled queries.
