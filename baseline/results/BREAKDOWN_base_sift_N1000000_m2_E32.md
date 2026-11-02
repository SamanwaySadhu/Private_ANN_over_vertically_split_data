# base_sift_N1000000_m2_E32: per-party breakdown of the baseline (rtt 0.1 ms, 10000 Mbps; server 64 cores, each client 8 cores; m=2, C1 = GC evaluator)

Baseline: exact greedy upper layers with secret-shared distances (no LSH), exact GC one-hot conversion, threshold HE used **online** for every 1-D read and for Beaver-triple generation. Offline = GC garbling + OT only. Counts (ANDs, reads, flights, bytes of GC/OT/Beaver) are exact for the executed protocol; HE/GC/OT times are modelled from calib/.

## 1. One-time preprocessing

| party | component | time |
|---|---|---|
| Server | HNSW build (hnswlib) | 10.2 s |
| Server | graph import | 1.7 s |
| Server | flatten tables (upper rows + layer-0 matrices) | 4.4 s |
| Server | **total (measured)** | **21.7 s** |
| each client | HE threshold keygen (modelled) | 26 ms, 4.72 MB |

Server tables: 723.29 MB (U = 142,606 upper rows, layer sizes [1000000, 124512, 15837, 1957, 269, 25, 4, 1]).

## 2. Per-query offline phase (modelled)

| component | Server | each client |
|---|---|---|
| GC garbling (264,055,120,320 AND gates) | 2.2 min | - |
| OT correlations | 32.5 s | 2.2 min |
| **total** | **2.7 min** | **2.2 min** |

GC tables to C1: **8.45 TB**; OT bytes per client: 555.07 GB.

| circuit | calls | ANDs | of which wrapper (I/O) | size |
|---|---|---|---|---|
| onehot:142606 | 48 | 7,207,911,144 | 6,684,261,912 | 230.65 GB |
| upper_step | 24 | 156,744 | 133,920 | 5.02 MB |
| beam_init | 1 | 473,370 | 473,370 | 15.15 MB |
| onehot:1000001 | 128 | 256,768,425,408 | 236,096,404,736 | 8.22 TB |
| beam_update | 64 | 78,133,504 | 52,377,600 | 2.50 GB |
| final | 1 | 20,150 | 19,840 | 644.80 KB |

## 3. Online phase (per query)

### 3a. Compute

| component | Server | C1 | other clients |
|---|---|---|---|
| he_read_server | 3.3 min | - | - |
| he_triples_server | 5 ms | - | - |
| ot_send | 32.5 s | - | - |
| he_encrypt | - | 81.9 s | 82.6 s |
| he_threshold_decrypt | - | 546 ms | 412 ms |
| he_triples | - | 42 ms | 42 ms |
| gc_evaluate | - | 15.3 min | 0 ms |
| ot_receive | - | 2.2 min | 2.2 min |
| local_share_arith | - | 4 ms | 4 ms |
| **busy compute** | **3.9 min** | **18.9 min** | **3.6 min** |

### 3b. Communication (sent + received)

| category | each client (max) | server |
|---|---|---|
| beaver | 2.49 MB | 0 B |
| gc_labels | 555.07 GB | 0 B |
| gc_ot | 1.11 TB | 2.23 TB |
| gc_out | 4.48 GB | 0 B |
| he_adj | 4.22 GB | 8.37 GB |
| he_triples | 47.30 MB | 84.07 MB |
| he_up_adj | 258.51 MB | 491.77 MB |
| he_up_vec | 2.07 GB | 3.93 GB |
| he_vec | 67.52 GB | 133.96 GB |
| share_query | 520 B | 0 B |
| **total online** | **1.75 TB** | **2.38 TB** |

Rounds: **1685 flights = 842 round trips**; 176 HE 1-D reads, 155,776 HE-generated Beaver triples. Communication time 31.7 min (rounds 84 ms, transfer 31.7 min).

**Online latency (server + C1 compute + communication, no overlap): 54.4 min.** Server idle 50.5 min, C1 idle 35.5 min.

## 4. Accuracy

recall@10 vs float ground truth 0.7680 (plaintext exact-greedy HNSW 0.7680, hnswlib 0.7680); upper phase unfinished in 0.0% of queries, mean 6.3 moves; secure == plain emulation on 8/8 sampled queries.
