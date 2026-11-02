# base_sift_N1000000_m2_E128: per-party breakdown of the baseline (rtt 0.1 ms, 10000 Mbps; server 64 cores, each client 8 cores; m=2, C1 = GC evaluator)

Baseline: exact greedy upper layers with secret-shared distances (no LSH), exact GC one-hot conversion, threshold HE used **online** for every 1-D read and for Beaver-triple generation. Offline = GC garbling + OT only. Counts (ANDs, reads, flights, bytes of GC/OT/Beaver) are exact for the executed protocol; HE/GC/OT times are modelled from calib/.

## 1. One-time preprocessing

| party | component | time |
|---|---|---|
| Server | HNSW build (hnswlib) | 7.3 s |
| Server | graph import | 1.6 s |
| Server | flatten tables (upper rows + layer-0 matrices) | 4.3 s |
| Server | **total (measured)** | **18.5 s** |
| each client | HE threshold keygen (modelled) | 26 ms, 4.72 MB |

Server tables: 723.29 MB (U = 142,614 upper rows, layer sizes [1000000, 124523, 15842, 1952, 266, 25, 4, 1]).

## 2. Per-query offline phase (modelled)

| component | Server | each client |
|---|---|---|
| GC garbling (1,035,564,103,552 AND gates) | 8.5 min | - |
| OT correlations | 2.1 min | 8.5 min |
| **total** | **10.7 min** | **8.5 min** |

GC tables to C1: **33.14 TB**; OT bytes per client: 2.18 TB.

| circuit | calls | ANDs | of which wrapper (I/O) | size |
|---|---|---|---|---|
| onehot:142614 | 48 | 7,208,315,496 | 6,684,636,888 | 230.67 GB |
| upper_step | 24 | 156,744 | 133,920 | 5.02 MB |
| beam_init | 1 | 1,889,946 | 1,889,946 | 60.48 MB |
| onehot:1000001 | 512 | 1,027,073,701,632 | 944,385,618,944 | 32.87 TB |
| beam_update | 256 | 1,279,960,064 | 831,184,896 | 40.96 GB |
| final | 1 | 79,670 | 79,360 | 2.55 MB |

## 3. Online phase (per query)

### 3a. Compute

| component | Server | C1 | other clients |
|---|---|---|---|
| he_read_server | 12.7 min | - | - |
| he_triples_server | 16 ms | - | - |
| ot_send | 2.1 min | - | - |
| he_encrypt | - | 5.3 min | 5.4 min |
| he_threshold_decrypt | - | 1.9 s | 1.4 s |
| he_triples | - | 143 ms | 143 ms |
| gc_evaluate | - | 60.1 min | 0 ms |
| ot_receive | - | 8.5 min | 8.5 min |
| local_share_arith | - | 14 ms | 14 ms |
| **busy compute** | **14.9 min** | **74.0 min** | **13.9 min** |

### 3b. Communication (sent + received)

| category | each client (max) | server |
|---|---|---|
| beaver | 8.78 MB | 0 B |
| gc_labels | 2.18 TB | 0 B |
| gc_ot | 4.37 TB | 8.74 TB |
| gc_out | 17.54 GB | 0 B |
| he_adj | 16.88 GB | 33.49 GB |
| he_triples | 160.83 MB | 285.85 MB |
| he_up_adj | 258.51 MB | 491.77 MB |
| he_up_vec | 2.07 GB | 3.93 GB |
| he_vec | 270.07 GB | 535.84 GB |
| share_query | 520 B | 0 B |
| **total online** | **6.85 TB** | **9.31 TB** |

Rounds: **5333 flights = 2666 round trips**; 560 HE 1-D reads, 548,992 HE-generated Beaver triples. Communication time 2.1 h (rounds 267 ms, transfer 2.1 h).

**Online latency (server + C1 compute + communication, no overlap): 3.5 h.** Server idle 3.3 h, C1 idle 2.3 h.

## 4. Accuracy

recall@10 vs float ground truth 0.9452 (plaintext exact-greedy HNSW 0.9452, hnswlib 0.9455); upper phase unfinished in 0.0% of queries, mean 6.2 moves; secure == plain emulation on 8/8 sampled queries.
