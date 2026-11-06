# base_sift_N1000000_m8_E64: per-party breakdown of the baseline (rtt 0.1 ms, 10000 Mbps; server 64 cores, each client 8 cores; m=8, C1 = GC evaluator)

Baseline: exact greedy upper layers with secret-shared distances (no LSH), exact GC one-hot conversion, threshold HE used **online** for every 1-D read and for Beaver-triple generation. Offline = GC garbling + OT only. Counts (ANDs, reads, flights, bytes of GC/OT/Beaver) are exact for the executed protocol; HE/GC/OT times are modelled from calib/.

## 1. One-time preprocessing

| party | component | time |
|---|---|---|
| Server | HNSW build (hnswlib) | 10.6 s |
| Server | graph import | 1.7 s |
| Server | flatten tables (upper rows + layer-0 matrices) | 4.2 s |
| Server | **total (measured)** | **21.7 s** |
| each client | HE threshold keygen (modelled) | 31 ms, 4.72 MB |

Server tables: 723.31 MB (U = 142,635 upper rows, layer sizes [1000000, 124471, 15883, 1970, 276, 29, 4, 1]).

## 2. Per-query offline phase (modelled)

| component | Server | each client |
|---|---|---|
| GC garbling (1,753,093,629,348 AND gates) | 14.4 min | - |
| OT correlations | 4.3 min | 4.3 min |
| **total** | **18.7 min** | **4.3 min** |

GC tables to C1: **56.10 TB**; OT bytes per client: 1.10 TB.

| circuit | calls | ANDs | of which wrapper (I/O) | size |
|---|---|---|---|---|
| onehot:142635 | 48 | 24,401,008,728 | 23,877,253,008 | 780.83 GB |
| upper_step | 24 | 612,072 | 589,248 | 19.59 MB |
| beam_init | 1 | 3,377,326 | 3,377,326 | 108.07 MB |
| onehot:1000001 | 256 | 1,727,747,279,232 | 1,686,403,237,888 | 55.29 TB |
| beam_update | 128 | 941,169,152 | 834,041,856 | 30.12 GB |
| final | 1 | 182,838 | 182,528 | 5.85 MB |

## 3. Online phase (per query)

### 3a. Compute

| component | Server | C1 | other clients |
|---|---|---|---|
| he_read_server | 6.5 min | - | - |
| he_triples_server | 9 ms | - | - |
| ot_send | 4.3 min | - | - |
| he_encrypt | - | 2.7 min | 2.7 min |
| he_threshold_decrypt | - | 1.0 s | 757 ms |
| he_triples | - | 75 ms | 75 ms |
| gc_evaluate | - | 101.7 min | 0 ms |
| ot_receive | - | 4.3 min | 4.3 min |
| local_share_arith | - | 3.4 s | 3.4 s |
| **busy compute** | **10.8 min** | **108.8 min** | **7.1 min** |

### 3b. Communication (sent + received)

| category | each client (max) | server |
|---|---|---|
| beaver | 32.13 MB | 0 B |
| gc_labels | 7.67 TB | 0 B |
| gc_ot | 2.20 TB | 17.59 TB |
| gc_out | 61.81 GB | 0 B |
| he_adj | 8.57 GB | 67.18 GB |
| he_triples | 85.14 MB | 605.34 MB |
| he_up_adj | 283.81 MB | 2.00 GB |
| he_up_vec | 2.27 GB | 16.04 GB |
| he_vec | 137.20 GB | 1.07 TB |
| share_query | 952 B | 0 B |
| **total online** | **10.08 TB** | **18.75 TB** |

Rounds: **2901 flights = 1450 round trips**; 304 HE 1-D reads, 286,848 HE-generated Beaver triples. Communication time 4.2 h (rounds 145 ms, transfer 4.2 h).

**Online latency (server + C1 compute + communication, no overlap): 6.2 h.** Server idle 6.0 h, C1 idle 4.3 h.

## 4. Accuracy

recall@10 vs float ground truth 0.8735 (plaintext exact-greedy HNSW 0.8735, hnswlib 0.8734); upper phase unfinished in 0.0% of queries, mean 6.1 moves; secure == plain emulation on 8/8 sampled queries.
