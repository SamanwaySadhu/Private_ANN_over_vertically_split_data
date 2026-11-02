# base_sift_N100000_m2_E64: per-party breakdown of the baseline (rtt 0.1 ms, 10000 Mbps; server 64 cores, each client 8 cores; m=2, C1 = GC evaluator)

Baseline: exact greedy upper layers with secret-shared distances (no LSH), exact GC one-hot conversion, threshold HE used **online** for every 1-D read and for Beaver-triple generation. Offline = GC garbling + OT only. Counts (ANDs, reads, flights, bytes of GC/OT/Beaver) are exact for the executed protocol; HE/GC/OT times are modelled from calib/.

## 1. One-time preprocessing

| party | component | time |
|---|---|---|
| Server | HNSW build (hnswlib) | 1.1 s |
| Server | graph import | 166 ms |
| Server | flatten tables (upper rows + layer-0 matrices) | 281 ms |
| Server | **total (measured)** | **1.9 s** |
| each client | HE threshold keygen (modelled) | 26 ms, 4.72 MB |

Server tables: 72.30 MB (U = 14,215 upper rows, layer sizes [100000, 12402, 1583, 195, 32, 2]).

## 2. Per-query offline phase (modelled)

| component | Server | each client |
|---|---|---|
| GC garbling (51,534,078,720 AND gates) | 25.5 s | - |
| OT correlations | 6.4 s | 25.7 s |
| **total** | **31.9 s** | **25.7 s** |

GC tables to C1: **1.65 TB**; OT bytes per client: 109.63 GB.

| circuit | calls | ANDs | of which wrapper (I/O) | size |
|---|---|---|---|---|
| onehot:14215 | 36 | 529,676,010 | 499,739,220 | 16.95 GB |
| upper_step | 18 | 116,550 | 100,440 | 3.73 MB |
| beam_init | 1 | 945,562 | 945,562 | 30.26 MB |
| onehot:100001 | 256 | 50,701,644,288 | 47,220,009,472 | 1.62 TB |
| beam_update | 128 | 301,656,320 | 208,367,616 | 9.65 GB |
| final | 1 | 39,990 | 39,680 | 1.28 MB |

## 3. Online phase (per query)

### 3a. Compute

| component | Server | C1 | other clients |
|---|---|---|---|
| he_read_server | 107.5 s | - | - |
| he_triples_server | 8 ms | - | - |
| ot_send | 6.4 s | - | - |
| he_encrypt | - | 17.0 s | 18.4 s |
| he_threshold_decrypt | - | 978 ms | 738 ms |
| he_triples | - | 73 ms | 73 ms |
| gc_evaluate | - | 3.0 min | 0 ms |
| ot_receive | - | 25.7 s | 25.7 s |
| local_share_arith | - | 7 ms | 7 ms |
| **busy compute** | **113.9 s** | **3.7 min** | **44.9 s** |

### 3b. Communication (sent + received)

| category | each client (max) | server |
|---|---|---|
| beaver | 4.49 MB | 0 B |
| gc_labels | 109.63 GB | 0 B |
| gc_ot | 220.12 GB | 440.24 GB |
| gc_out | 881.87 MB | 0 B |
| he_adj | 1.04 GB | 1.95 GB |
| he_triples | 82.78 MB | 147.13 MB |
| he_up_adj | 42.57 MB | 66.21 MB |
| he_up_vec | 340.58 MB | 529.68 MB |
| he_vec | 16.68 GB | 31.20 GB |
| share_query | 520 B | 0 B |
| **total online** | **348.83 GB** | **474.14 GB** |

Rounds: **2787 flights = 1394 round trips**; 292 HE 1-D reads, 280,704 HE-generated Beaver triples. Communication time 6.3 min (rounds 139 ms, transfer 6.3 min).

**Online latency (server + C1 compute + communication, no overlap): 11.9 min.** Server idle 10.0 min, C1 idle 8.2 min.

## 4. Accuracy

recall@10 vs float ground truth 0.9562 (plaintext exact-greedy HNSW 0.9562, hnswlib 0.9562); upper phase unfinished in 0.0% of queries, mean 5.2 moves; secure == plain emulation on 8/8 sampled queries.
