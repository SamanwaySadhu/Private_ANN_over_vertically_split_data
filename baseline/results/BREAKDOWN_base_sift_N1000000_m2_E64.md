# base_sift_N1000000_m2_E64: per-party breakdown of the baseline (rtt 0.1 ms, 10000 Mbps; server 64 cores, each client 8 cores; m=2, C1 = GC evaluator)

Baseline: exact greedy upper layers with secret-shared distances (no LSH), exact GC one-hot conversion, threshold HE used **online** for every 1-D read and for Beaver-triple generation. Offline = GC garbling + OT only. Counts (ANDs, reads, flights, bytes of GC/OT/Beaver) are exact for the executed protocol; HE/GC/OT times are modelled from calib/.

## 1. One-time preprocessing

| party | component | time |
|---|---|---|
| Server | HNSW build (hnswlib) | 11.9 s |
| Server | graph import | 1.7 s |
| Server | flatten tables (upper rows + layer-0 matrices) | 5.0 s |
| Server | **total (measured)** | **25.1 s** |
| each client | HE threshold keygen (modelled) | 26 ms, 4.72 MB |

Server tables: 723.24 MB (U = 142,520 upper rows, layer sizes [1000000, 124455, 15829, 1941, 263, 26, 4, 1]).

## 2. Per-query offline phase (modelled)

| component | Server | each client |
|---|---|---|
| GC garbling (521,057,052,384 AND gates) | 4.3 min | - |
| OT correlations | 64.2 s | 4.3 min |
| **total** | **5.4 min** | **4.3 min** |

GC tables to C1: **16.67 TB**; OT bytes per client: 1.10 TB.

| circuit | calls | ANDs | of which wrapper (I/O) | size |
|---|---|---|---|---|
| onehot:142520 | 48 | 7,203,564,360 | 6,680,230,920 | 230.51 GB |
| upper_step | 24 | 156,744 | 133,920 | 5.02 MB |
| beam_init | 1 | 945,562 | 945,562 | 30.26 MB |
| onehot:1000001 | 256 | 513,536,850,816 | 472,192,809,472 | 16.43 TB |
| beam_update | 128 | 315,494,912 | 208,367,616 | 10.10 GB |
| final | 1 | 39,990 | 39,680 | 1.28 MB |

## 3. Online phase (per query)

### 3a. Compute

| component | Server | C1 | other clients |
|---|---|---|---|
| he_read_server | 6.5 min | - | - |
| he_triples_server | 8 ms | - | - |
| ot_send | 64.2 s | - | - |
| he_encrypt | - | 2.7 min | 2.7 min |
| he_threshold_decrypt | - | 1.0 s | 755 ms |
| he_triples | - | 76 ms | 76 ms |
| gc_evaluate | - | 30.2 min | 0 ms |
| ot_receive | - | 4.3 min | 4.3 min |
| local_share_arith | - | 7 ms | 7 ms |
| **busy compute** | **7.5 min** | **37.2 min** | **7.0 min** |

### 3b. Communication (sent + received)

| category | each client (max) | server |
|---|---|---|
| beaver | 4.59 MB | 0 B |
| gc_labels | 1.10 TB | 0 B |
| gc_ot | 2.20 TB | 4.40 TB |
| gc_out | 8.83 GB | 0 B |
| he_adj | 8.44 GB | 16.74 GB |
| he_triples | 85.14 MB | 151.33 MB |
| he_up_adj | 258.51 MB | 491.77 MB |
| he_up_vec | 2.07 GB | 3.93 GB |
| he_vec | 135.04 GB | 267.92 GB |
| share_query | 520 B | 0 B |
| **total online** | **3.45 TB** | **4.69 TB** |

Rounds: **2901 flights = 1450 round trips**; 304 HE 1-D reads, 286,848 HE-generated Beaver triples. Communication time 62.5 min (rounds 145 ms, transfer 62.5 min).

**Online latency (server + C1 compute + communication, no overlap): 107.2 min.** Server idle 99.7 min, C1 idle 70.0 min.

## 4. Accuracy

recall@10 vs float ground truth 0.8739 (plaintext exact-greedy HNSW 0.8739, hnswlib 0.8740); upper phase unfinished in 0.0% of queries, mean 6.6 moves; secure == plain emulation on 8/8 sampled queries.
