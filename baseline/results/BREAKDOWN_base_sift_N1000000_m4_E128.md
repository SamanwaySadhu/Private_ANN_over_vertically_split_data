# base_sift_N1000000_m4_E128: per-party breakdown of the baseline (rtt 0.1 ms, 10000 Mbps; server 64 cores, each client 8 cores; m=4, C1 = GC evaluator)

Baseline: exact greedy upper layers with secret-shared distances (no LSH), exact GC one-hot conversion, threshold HE used **online** for every 1-D read and for Beaver-triple generation. Offline = GC garbling + OT only. Counts (ANDs, reads, flights, bytes of GC/OT/Beaver) are exact for the executed protocol; HE/GC/OT times are modelled from calib/.

## 1. One-time preprocessing

| party | component | time |
|---|---|---|
| Server | HNSW build (hnswlib) | 13.4 s |
| Server | graph import | 1.7 s |
| Server | flatten tables (upper rows + layer-0 matrices) | 4.8 s |
| Server | **total (measured)** | **26.6 s** |
| each client | HE threshold keygen (modelled) | 28 ms, 4.72 MB |

Server tables: 723.30 MB (U = 142,627 upper rows, layer sizes [1000000, 124520, 15856, 1955, 265, 25, 4, 1]).

## 2. Per-query offline phase (modelled)

| component | Server | each client |
|---|---|---|
| GC garbling (1,851,602,034,988 AND gates) | 15.3 min | - |
| OT correlations | 4.3 min | 8.5 min |
| **total** | **19.5 min** | **8.5 min** |

GC tables to C1: **59.25 TB**; OT bytes per client: 2.18 TB.

| circuit | calls | ANDs | of which wrapper (I/O) | size |
|---|---|---|---|---|
| onehot:142627 | 48 | 12,939,195,096 | 12,415,468,752 | 414.05 GB |
| upper_step | 24 | 308,520 | 285,696 | 9.87 MB |
| beam_init | 1 | 3,510,006 | 3,510,006 | 112.32 MB |
| onehot:1000001 | 512 | 1,836,547,320,576 | 1,753,859,237,888 | 58.77 TB |
| beam_update | 256 | 2,111,525,888 | 1,662,750,720 | 67.57 GB |
| final | 1 | 174,902 | 174,592 | 5.60 MB |

## 3. Online phase (per query)

### 3a. Compute

| component | Server | C1 | other clients |
|---|---|---|---|
| he_read_server | 12.7 min | - | - |
| he_triples_server | 16 ms | - | - |
| ot_send | 4.3 min | - | - |
| he_encrypt | - | 5.4 min | 5.4 min |
| he_threshold_decrypt | - | 1.9 s | 1.5 s |
| he_triples | - | 143 ms | 143 ms |
| gc_evaluate | - | 107.4 min | 0 ms |
| ot_receive | - | 8.5 min | 8.5 min |
| local_share_arith | - | 12 ms | 12 ms |
| **busy compute** | **17.0 min** | **2.0 h** | **13.9 min** |

### 3b. Communication (sent + received)

| category | each client (max) | server |
|---|---|---|
| beaver | 26.35 MB | 0 B |
| gc_labels | 6.53 TB | 0 B |
| gc_ot | 4.37 TB | 17.48 TB |
| gc_out | 52.62 GB | 0 B |
| he_adj | 16.88 GB | 67.11 GB |
| he_triples | 160.83 MB | 571.71 MB |
| he_up_adj | 258.54 MB | 996.15 MB |
| he_up_vec | 2.07 GB | 7.97 GB |
| he_vec | 270.08 GB | 1.07 TB |
| share_query | 792 B | 0 B |
| **total online** | **11.24 TB** | **18.63 TB** |

Rounds: **5333 flights = 2666 round trips**; 560 HE 1-D reads, 548,992 HE-generated Beaver triples. Communication time 4.1 h (rounds 267 ms, transfer 4.1 h).

**Online latency (server + C1 compute + communication, no overlap): 6.4 h.** Server idle 6.2 h, C1 idle 4.4 h.

## 4. Accuracy

recall@10 vs float ground truth 0.9422 (plaintext exact-greedy HNSW 0.9423, hnswlib 0.9425); upper phase unfinished in 0.0% of queries, mean 6.5 moves; secure == plain emulation on 8/8 sampled queries.
