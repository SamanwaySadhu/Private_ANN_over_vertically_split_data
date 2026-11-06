# base_sift_N1000000_m8_E128: per-party breakdown of the baseline (rtt 0.1 ms, 10000 Mbps; server 64 cores, each client 8 cores; m=8, C1 = GC evaluator)

Baseline: exact greedy upper layers with secret-shared distances (no LSH), exact GC one-hot conversion, threshold HE used **online** for every 1-D read and for Beaver-triple generation. Offline = GC garbling + OT only. Counts (ANDs, reads, flights, bytes of GC/OT/Beaver) are exact for the executed protocol; HE/GC/OT times are modelled from calib/.

## 1. One-time preprocessing

| party | component | time |
|---|---|---|
| Server | HNSW build (hnswlib) | 11.2 s |
| Server | graph import | 1.7 s |
| Server | flatten tables (upper rows + layer-0 matrices) | 4.4 s |
| Server | **total (measured)** | **22.6 s** |
| each client | HE threshold keygen (modelled) | 31 ms, 4.72 MB |

Server tables: 723.26 MB (U = 142,550 upper rows, layer sizes [1000000, 124437, 15865, 1948, 270, 24, 4, 1]).

## 2. Per-query offline phase (modelled)

| component | Server | each client |
|---|---|---|
| GC garbling (3,483,663,411,172 AND gates) | 28.7 min | - |
| OT correlations | 8.5 min | 8.5 min |
| **total** | **37.2 min** | **8.5 min** |

GC tables to C1: **111.48 TB**; OT bytes per client: 2.18 TB.

| circuit | calls | ANDs | of which wrapper (I/O) | size |
|---|---|---|---|---|
| onehot:142550 | 48 | 24,386,467,608 | 23,863,024,008 | 780.37 GB |
| upper_step | 24 | 612,072 | 589,248 | 19.59 MB |
| beam_init | 1 | 6,750,126 | 6,750,126 | 216.00 MB |
| onehot:1000001 | 512 | 3,455,494,558,464 | 3,372,806,475,776 | 110.58 TB |
| beam_update | 256 | 3,774,657,536 | 3,325,882,368 | 120.79 GB |
| final | 1 | 365,366 | 365,056 | 11.69 MB |

## 3. Online phase (per query)

### 3a. Compute

| component | Server | C1 | other clients |
|---|---|---|---|
| he_read_server | 12.8 min | - | - |
| he_triples_server | 17 ms | - | - |
| ot_send | 8.5 min | - | - |
| he_encrypt | - | 5.3 min | 5.4 min |
| he_threshold_decrypt | - | 2.0 s | 1.4 s |
| he_triples | - | 143 ms | 143 ms |
| gc_evaluate | - | 3.4 h | 0 ms |
| ot_receive | - | 8.5 min | 8.5 min |
| local_share_arith | - | 6.2 s | 6.2 s |
| **busy compute** | **21.3 min** | **3.6 h** | **14.0 min** |

### 3b. Communication (sent + received)

| category | each client (max) | server |
|---|---|---|
| beaver | 61.49 MB | 0 B |
| gc_labels | 15.23 TB | 0 B |
| gc_ot | 4.37 TB | 34.95 TB |
| gc_out | 122.78 GB | 0 B |
| he_adj | 17.15 GB | 134.36 GB |
| he_triples | 160.83 MB | 1.14 GB |
| he_up_adj | 283.81 MB | 2.00 GB |
| he_up_vec | 2.27 GB | 16.04 GB |
| he_vec | 274.39 GB | 2.15 TB |
| share_query | 952 B | 0 B |
| **total online** | **20.02 TB** | **37.26 TB** |

Rounds: **5333 flights = 2666 round trips**; 560 HE 1-D reads, 548,992 HE-generated Beaver triples. Communication time 8.3 h (rounds 267 ms, transfer 8.3 h).

**Online latency (server + C1 compute + communication, no overlap): 12.2 h.** Server idle 11.9 h, C1 idle 8.6 h.

## 4. Accuracy

recall@10 vs float ground truth 0.9444 (plaintext exact-greedy HNSW 0.9444, hnswlib 0.9449); upper phase unfinished in 0.0% of queries, mean 6.1 moves; secure == plain emulation on 8/8 sampled queries.
