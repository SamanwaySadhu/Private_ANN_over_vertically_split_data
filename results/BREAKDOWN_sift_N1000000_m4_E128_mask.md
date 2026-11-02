# sift_N1000000_m4_E128_mask: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 8 cores; m=4, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 7.3 s | | |
| Server | graph import | 1.7 s | | |
| Server | flatten + LSH + cuckoo tables | 30.9 s | | |
| Server | **total (measured)** | **45.2 s** | | |
| Client C1 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Client C2 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Client C3 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Client C4 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Server | HE keygen relay/aggregation | | 10.50 MB | 18.89 MB |

## 2. Per-query preprocessing (offline phase, modelled)

### 2a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| GC garbling | 150 ms | 0 ms | 0 ms |
| GC tables | 0 ms | 0 ms | 0 ms |
| OT extension | 16 ms | 228 ms | 228 ms |
| Beaver triples (HE) | 3 ms | 121 ms | 158 ms |
| Read correlations (HE) | 5.5 min | 5.4 min | 5.4 min |
| **total** | **5.5 min** | **5.4 min** | **5.4 min** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 67.80 GB | 0 B | 0 B | 67.80 GB | 0 B | 0 B |
| OT extension | 0 B | 8.90 GB | 2.22 GB | 0 B | 2.22 GB | 0 B |
| Beaver triples (HE) | 157.72 MB | 433.44 MB | 78.81 MB | 98.66 MB | 137.96 MB | 39.43 MB |
| Read correlations (HE) | 9.20 GB | 1.14 TB | 282.22 GB | 5.76 GB | 285.67 GB | 2.30 GB |
| **total** | **77.16 GB** | **1.15 TB** | **284.52 GB** | **73.66 GB** | **288.03 GB** | **2.34 GB** |

Offline phase: 613,504 Beaver triples (75 HE batches of 8192), 2,118,843,868 GC AND gates, 4,376 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 7.0 s | 0 ms | 0 ms |
| OT sender (label transfer) | 37 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 7.4 s | 0 ms |
| OT receiver | 0 ms | 521 ms | 521 ms |
| Local share arithmetic (Beaver, e-r, ...) | 0 ms | 50.6 s | 50.6 s |
| **total busy compute** | **7.0 s** | **58.5 s** | **51.2 s** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 2.12 MB | 65.73 GB | 16.43 GB | 2.12 MB | 16.43 GB | 0 B |
| gc_ot | 17.79 GB | 69.50 MB | 17.37 MB | 4.45 GB | 17.37 MB | 4.45 GB |
| gc_labels | 0 B | 0 B | 0 B | 6.67 GB | 2.22 GB | 0 B |
| read1d_adj | 32.77 KB | 4.10 GB | 1.02 GB | 32.77 KB | 1.02 GB | 0 B |
| read1d_theta | 116.50 KB | 51.28 MB | 12.82 MB | 116.50 KB | 12.82 MB | 0 B |
| beaver | 0 B | 0 B | 12.62 MB | 12.62 MB | 12.62 MB | 12.62 MB |
| gc_out | 0 B | 0 B | 26.86 MB | 0 B | 0 B | 8.95 MB |
| beaver_dict | 0 B | 0 B | 1.88 MB | 1.88 MB | 1.88 MB | 1.88 MB |
| beaver_hash | 0 B | 0 B | 221.18 KB | 221.18 KB | 221.18 KB | 221.18 KB |
| onehot | 0 B | 0 B | 55.97 KB | 55.97 KB | 55.97 KB | 55.97 KB |
| share_query | 0 B | 0 B | 396 B | 396 B | 396 B | 396 B |
| **total** | **17.79 GB** | **69.94 GB** | **17.53 GB** | **11.14 GB** | **19.72 GB** | **4.47 GB** |

Online rounds: **3186 message flights = 1593 round trips**. LAN communication time: 159 ms for round latency + 56.0 s for transfer = 56.1 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **2.0 min**. Wait: server idle 114.6 s, C1 idle 63.1 s, other clients idle 70.5 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 94.96 GB | 1.22 TB | 1.31 TB |
| C1 (evaluator) | 302.05 GB | 84.80 GB | 386.84 GB |
| each other client | 307.76 GB | 6.81 GB | 314.57 GB |
| **all parties (each byte counted once)** | **1.32 TB** | **1.32 TB** | |

Rounds: online 3186 flights (1593 RTT); offline 3 flights on the critical path (HE phases batched).