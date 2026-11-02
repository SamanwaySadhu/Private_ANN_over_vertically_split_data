# sift_N1000000_m8_E128_mask: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 8 cores; m=8, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 10.6 s | | |
| Server | graph import | 1.7 s | | |
| Server | flatten + LSH + cuckoo tables | 30.1 s | | |
| Server | **total (measured)** | **47.6 s** | | |
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
| GC garbling | 267 ms | 0 ms | 0 ms |
| GC tables | 0 ms | 0 ms | 0 ms |
| OT extension | 33 ms | 228 ms | 228 ms |
| Beaver triples (HE) | 3 ms | 122 ms | 157 ms |
| Read correlations (HE) | 5.6 min | 5.3 min | 5.4 min |
| **total** | **5.6 min** | **5.4 min** | **5.4 min** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 121.20 GB | 0 B | 0 B | 121.20 GB | 0 B | 0 B |
| OT extension | 0 B | 17.79 GB | 2.22 GB | 0 B | 2.22 GB | 0 B |
| Beaver triples (HE) | 315.43 MB | 906.28 MB | 78.81 MB | 177.64 MB | 137.96 MB | 39.43 MB |
| Read correlations (HE) | 18.40 GB | 2.27 TB | 282.22 GB | 10.36 GB | 285.67 GB | 2.30 GB |
| **total** | **139.92 GB** | **2.29 TB** | **284.52 GB** | **131.75 GB** | **288.03 GB** | **2.34 GB** |

Offline phase: 613,504 Beaver triples (75 HE batches of 8192), 3,787,642,996 GC AND gates, 4,376 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 8.2 s | 0 ms | 0 ms |
| OT sender (label transfer) | 74 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 13.2 s | 0 ms |
| OT receiver | 0 ms | 521 ms | 521 ms |
| Local share arithmetic (Beaver, e-r, ...) | 0 ms | 51.1 s | 51.1 s |
| **total busy compute** | **8.3 s** | **64.8 s** | **51.6 s** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 2.12 MB | 131.46 GB | 16.43 GB | 2.12 MB | 16.43 GB | 0 B |
| gc_ot | 35.59 GB | 139.02 MB | 17.38 MB | 4.45 GB | 17.38 MB | 4.45 GB |
| gc_labels | 0 B | 0 B | 0 B | 15.57 GB | 2.22 GB | 0 B |
| read1d_adj | 32.77 KB | 8.19 GB | 1.02 GB | 32.77 KB | 1.02 GB | 0 B |
| beaver | 0 B | 0 B | 29.45 MB | 29.45 MB | 29.45 MB | 29.45 MB |
| read1d_theta | 116.50 KB | 102.50 MB | 12.81 MB | 116.50 KB | 12.81 MB | 0 B |
| gc_out | 0 B | 0 B | 62.69 MB | 0 B | 0 B | 8.96 MB |
| beaver_dict | 0 B | 0 B | 4.39 MB | 4.39 MB | 4.39 MB | 4.39 MB |
| beaver_hash | 0 B | 0 B | 516.10 KB | 516.10 KB | 516.10 KB | 516.10 KB |
| onehot | 0 B | 0 B | 130.59 KB | 130.59 KB | 130.59 KB | 130.59 KB |
| share_query | 0 B | 0 B | 476 B | 476 B | 476 B | 476 B |
| **total** | **35.59 GB** | **139.89 GB** | **17.58 GB** | **20.06 GB** | **19.74 GB** | **4.49 GB** |

Online rounds: **3186 message flights = 1593 round trips**. LAN communication time: 159 ms for round latency + 111.9 s for transfer = 112.1 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **3.1 min**. Wait: server idle 2.9 min, C1 idle 2.0 min, other clients idle 2.2 min.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 175.52 GB | 2.43 TB | 2.61 TB |
| C1 (evaluator) | 302.10 GB | 151.80 GB | 453.91 GB |
| each other client | 307.78 GB | 6.83 GB | 314.61 GB |
| **all parties (each byte counted once)** | **2.63 TB** | **2.63 TB** | |

Rounds: online 3186 flights (1593 RTT); offline 3 flights on the critical path (HE phases batched).