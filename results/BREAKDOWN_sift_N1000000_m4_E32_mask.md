# sift_N1000000_m4_E32_mask: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 8 cores; m=4, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 7.5 s | | |
| Server | graph import | 1.6 s | | |
| Server | flatten + LSH + cuckoo tables | 28.9 s | | |
| Server | **total (measured)** | **43.4 s** | | |
| Client C1 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Client C2 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Client C3 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Client C4 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Server | HE keygen relay/aggregation | | 10.50 MB | 18.89 MB |

## 2. Per-query preprocessing (offline phase, modelled)

### 2a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| GC garbling | 10 ms | 0 ms | 0 ms |
| GC tables | 0 ms | 0 ms | 0 ms |
| OT extension | 1 ms | 15 ms | 15 ms |
| Beaver triples (HE) | 1 ms | 44 ms | 57 ms |
| Read correlations (HE) | 94.1 s | 81.3 s | 81.8 s |
| **total** | **94.1 s** | **81.3 s** | **81.9 s** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 4.33 GB | 0 B | 0 B | 4.33 GB | 0 B | 0 B |
| OT extension | 0 B | 571.91 MB | 142.98 MB | 0 B | 142.98 MB | 0 B |
| Beaver triples (HE) | 56.78 MB | 156.04 MB | 28.37 MB | 35.52 MB | 49.66 MB | 14.19 MB |
| Read correlations (HE) | 2.34 GB | 286.92 GB | 71.29 GB | 1.46 GB | 72.17 GB | 584.60 MB |
| **total** | **6.72 GB** | **287.65 GB** | **71.46 GB** | **5.82 GB** | **72.36 GB** | **598.80 MB** |

Offline phase: 220,288 Beaver triples (27 HE batches of 8192), 135,162,588 GC AND gates, 1,112 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 2.3 s | 0 ms | 0 ms |
| OT sender (label transfer) | 2 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 471 ms | 0 ms |
| OT receiver | 0 ms | 34 ms | 34 ms |
| Local share arithmetic (Beaver, e-r, ...) | 0 ms | 12.8 s | 12.8 s |
| **total busy compute** | **2.3 s** | **13.3 s** | **12.9 s** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 534.58 KB | 16.58 GB | 4.14 GB | 534.58 KB | 4.14 GB | 0 B |
| gc_ot | 1.14 GB | 4.47 MB | 1.12 MB | 285.96 MB | 1.12 MB | 285.96 MB |
| read1d_adj | 8.19 KB | 1.02 GB | 256.00 MB | 8.19 KB | 256.00 MB | 0 B |
| gc_labels | 0 B | 0 B | 0 B | 428.93 MB | 142.98 MB | 0 B |
| read1d_theta | 116.50 KB | 51.27 MB | 12.82 MB | 116.50 KB | 12.82 MB | 0 B |
| beaver | 0 B | 0 B | 3.19 MB | 3.19 MB | 3.19 MB | 3.19 MB |
| beaver_dict | 0 B | 0 B | 1.88 MB | 1.88 MB | 1.88 MB | 1.88 MB |
| gc_out | 0 B | 0 B | 1.71 MB | 0 B | 0 B | 569.82 KB |
| beaver_hash | 0 B | 0 B | 221.18 KB | 221.18 KB | 221.18 KB | 221.18 KB |
| onehot | 0 B | 0 B | 16.80 KB | 16.80 KB | 16.80 KB | 16.80 KB |
| share_query | 0 B | 0 B | 396 B | 396 B | 396 B | 396 B |
| **total** | **1.14 GB** | **17.66 GB** | **4.42 GB** | **720.85 MB** | **4.56 GB** | **291.83 MB** |

Online rounds: **1074 message flights = 537 round trips**. LAN communication time: 54 ms for round latency + 14.1 s for transfer = 14.2 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **29.8 s**. Wait: server idle 27.5 s, C1 idle 16.5 s, other clients idle 16.9 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 7.86 GB | 305.30 GB | 313.17 GB |
| C1 (evaluator) | 75.88 GB | 6.54 GB | 82.43 GB |
| each other client | 76.92 GB | 890.63 MB | 77.81 GB |
| **all parties (each byte counted once)** | **314.52 GB** | **314.52 GB** | |

Rounds: online 1074 flights (537 RTT); offline 3 flights on the critical path (HE phases batched).