# sift_N1000000_m8_E32_mask: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 8 cores; m=8, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 10.1 s | | |
| Server | graph import | 1.8 s | | |
| Server | flatten + LSH + cuckoo tables | 31.7 s | | |
| Server | **total (measured)** | **49.1 s** | | |
| Client C1 | HE threshold keygen (modelled) | 31 ms | 4.72 MB | 2.62 MB |
| Client C2 | HE threshold keygen (modelled) | 31 ms | 4.72 MB | 2.62 MB |
| Client C3 | HE threshold keygen (modelled) | 31 ms | 4.72 MB | 2.62 MB |
| Client C4 | HE threshold keygen (modelled) | 31 ms | 4.72 MB | 2.62 MB |
| Client C5 | HE threshold keygen (modelled) | 31 ms | 4.72 MB | 2.62 MB |
| Client C6 | HE threshold keygen (modelled) | 31 ms | 4.72 MB | 2.62 MB |
| Client C7 | HE threshold keygen (modelled) | 31 ms | 4.72 MB | 2.62 MB |
| Client C8 | HE threshold keygen (modelled) | 31 ms | 4.72 MB | 2.62 MB |
| Server | HE keygen relay/aggregation | | 21.00 MB | 37.79 MB |

## 2. Per-query preprocessing (offline phase, modelled)

### 2a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| GC garbling | 17 ms | 0 ms | 0 ms |
| GC tables | 0 ms | 0 ms | 0 ms |
| OT extension | 2 ms | 15 ms | 15 ms |
| Beaver triples (HE) | 1 ms | 44 ms | 57 ms |
| Read correlations (HE) | 94.6 s | 81.0 s | 81.6 s |
| **total** | **94.6 s** | **81.1 s** | **81.6 s** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 7.78 GB | 0 B | 0 B | 7.78 GB | 0 B | 0 B |
| OT extension | 0 B | 1.15 GB | 143.26 MB | 0 B | 143.26 MB | 0 B |
| Beaver triples (HE) | 113.56 MB | 326.26 MB | 28.37 MB | 63.95 MB | 49.66 MB | 14.19 MB |
| Read correlations (HE) | 4.68 GB | 574.43 GB | 71.29 GB | 2.63 GB | 72.17 GB | 584.60 MB |
| **total** | **12.57 GB** | **575.90 GB** | **71.46 GB** | **10.48 GB** | **72.36 GB** | **598.80 MB** |

Offline phase: 220,288 Beaver triples (27 HE batches of 8192), 243,204,468 GC AND gates, 1,112 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 2.5 s | 0 ms | 0 ms |
| OT sender (label transfer) | 5 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 847 ms | 0 ms |
| OT receiver | 0 ms | 34 ms | 34 ms |
| Local share arithmetic (Beaver, e-r, ...) | 0 ms | 13.9 s | 13.9 s |
| **total busy compute** | **2.5 s** | **14.8 s** | **14.0 s** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 534.58 KB | 33.15 GB | 4.14 GB | 534.58 KB | 4.14 GB | 0 B |
| gc_ot | 2.29 GB | 8.95 MB | 1.12 MB | 286.53 MB | 1.12 MB | 286.53 MB |
| read1d_adj | 8.19 KB | 2.05 GB | 256.00 MB | 8.19 KB | 256.00 MB | 0 B |
| gc_labels | 0 B | 0 B | 0 B | 1.00 GB | 143.26 MB | 0 B |
| read1d_theta | 116.50 KB | 102.48 MB | 12.81 MB | 116.50 KB | 12.81 MB | 0 B |
| beaver | 0 B | 0 B | 7.43 MB | 7.43 MB | 7.43 MB | 7.43 MB |
| beaver_dict | 0 B | 0 B | 4.39 MB | 4.39 MB | 4.39 MB | 4.39 MB |
| beaver_hash | 0 B | 0 B | 516.10 KB | 516.10 KB | 516.10 KB | 516.10 KB |
| gc_out | 0 B | 0 B | 4.00 MB | 0 B | 0 B | 570.98 KB |
| onehot | 0 B | 0 B | 39.20 KB | 39.20 KB | 39.20 KB | 39.20 KB |
| share_query | 0 B | 0 B | 476 B | 476 B | 476 B | 476 B |
| **total** | **2.29 GB** | **35.31 GB** | **4.43 GB** | **1.30 GB** | **4.57 GB** | **299.47 MB** |

Online rounds: **1074 message flights = 537 round trips**. LAN communication time: 54 ms for round latency + 28.2 s for transfer = 28.3 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **45.6 s**. Wait: server idle 43.1 s, C1 idle 30.8 s, other clients idle 31.6 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 14.87 GB | 611.21 GB | 626.07 GB |
| C1 (evaluator) | 75.89 GB | 11.78 GB | 87.68 GB |
| each other client | 76.93 GB | 898.27 MB | 77.83 GB |
| **all parties (each byte counted once)** | **629.28 GB** | **629.28 GB** | |

Rounds: online 1074 flights (537 RTT); offline 3 flights on the critical path (HE phases batched).