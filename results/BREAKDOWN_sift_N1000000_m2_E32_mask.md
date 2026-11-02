# sift_N1000000_m2_E32_mask: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 8 cores; m=2, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 11.7 s | | |
| Server | graph import | 1.7 s | | |
| Server | flatten + LSH + cuckoo tables | 29.0 s | | |
| Server | **total (measured)** | **47.7 s** | | |
| Client C1 | HE threshold keygen (modelled) | 26 ms | 4.72 MB | 2.62 MB |
| Client C2 | HE threshold keygen (modelled) | 26 ms | 4.72 MB | 2.62 MB |
| Server | HE keygen relay/aggregation | | 5.25 MB | 9.45 MB |

## 2. Per-query preprocessing (offline phase, modelled)

### 2a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| GC garbling | 6 ms | 0 ms | 0 ms |
| GC tables | 0 ms | 0 ms | 0 ms |
| OT extension | 1 ms | 15 ms | 15 ms |
| Beaver triples (HE) | 1 ms | 43 ms | 57 ms |
| Read correlations (HE) | 94.4 s | 81.1 s | 81.7 s |
| **total** | **94.4 s** | **81.2 s** | **81.7 s** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 2.60 GB | 0 B | 0 B | 2.60 GB | 0 B | 0 B |
| OT extension | 0 B | 285.67 MB | 142.84 MB | 0 B | 142.84 MB | 0 B |
| Beaver triples (HE) | 28.39 MB | 70.93 MB | 28.37 MB | 21.30 MB | 49.66 MB | 14.19 MB |
| Read correlations (HE) | 1.17 GB | 143.17 GB | 71.29 GB | 877.35 MB | 72.17 GB | 584.60 MB |
| **total** | **3.80 GB** | **143.52 GB** | **71.46 GB** | **3.50 GB** | **72.36 GB** | **598.80 MB** |

Offline phase: 220,288 Beaver triples (27 HE batches of 8192), 81,302,352 GC AND gates, 1,112 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 2.2 s | 0 ms | 0 ms |
| OT sender (label transfer) | 1 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 283 ms | 0 ms |
| OT receiver | 0 ms | 33 ms | 33 ms |
| Local share arithmetic (Beaver, e-r, ...) | 0 ms | 12.8 s | 12.8 s |
| **total busy compute** | **2.2 s** | **13.1 s** | **12.9 s** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 534.58 KB | 8.29 GB | 4.14 GB | 534.58 KB | 4.14 GB | 0 B |
| gc_ot | 571.34 MB | 2.23 MB | 1.12 MB | 285.67 MB | 1.12 MB | 285.67 MB |
| read1d_adj | 8.19 KB | 512.00 MB | 256.00 MB | 8.19 KB | 256.00 MB | 0 B |
| gc_labels | 0 B | 0 B | 0 B | 142.84 MB | 142.84 MB | 0 B |
| read1d_theta | 116.50 KB | 25.64 MB | 12.82 MB | 116.50 KB | 12.82 MB | 0 B |
| beaver | 0 B | 0 B | 1.06 MB | 1.06 MB | 1.06 MB | 1.06 MB |
| beaver_dict | 0 B | 0 B | 626.69 KB | 626.69 KB | 626.69 KB | 626.69 KB |
| gc_out | 0 B | 0 B | 569.25 KB | 0 B | 0 B | 569.25 KB |
| beaver_hash | 0 B | 0 B | 73.73 KB | 73.73 KB | 73.73 KB | 73.73 KB |
| onehot | 0 B | 0 B | 5.60 KB | 5.60 KB | 5.60 KB | 5.60 KB |
| share_query | 0 B | 0 B | 260 B | 260 B | 260 B | 260 B |
| **total** | **572.00 MB** | **8.83 GB** | **4.42 GB** | **430.93 MB** | **4.56 GB** | **288.01 MB** |

Online rounds: **1074 message flights = 537 round trips**. LAN communication time: 54 ms for round latency + 7.1 s for transfer = 7.1 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **22.5 s**. Wait: server idle 20.3 s, C1 idle 9.3 s, other clients idle 9.6 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 4.37 GB | 152.35 GB | 156.72 GB |
| C1 (evaluator) | 75.88 GB | 3.93 GB | 79.81 GB |
| each other client | 76.92 GB | 886.80 MB | 77.81 GB |
| **all parties (each byte counted once)** | **157.17 GB** | **157.17 GB** | |

Rounds: online 1074 flights (537 RTT); offline 3 flights on the critical path (HE phases batched).