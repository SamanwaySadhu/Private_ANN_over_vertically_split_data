# sift_N1000000_m4_E128_pub: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 448 cores; m=4, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 24.4 s | | |
| Server | graph import | 2.6 s | | |
| Server | flatten + LSH + cuckoo tables | 44.3 s | | |
| Server | **total (measured)** | **76.8 s** | | |
| Client C1 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Client C2 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Client C3 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Client C4 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Server | HE keygen relay/aggregation | | 10.50 MB | 18.89 MB |

## 2. Per-query preprocessing (offline phase, modelled)

### 2a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| GC garbling | 149 ms | 0 ms | 0 ms |
| GC tables | 0 ms | 0 ms | 0 ms |
| OT extension | 16 ms | 4 ms | 4 ms |
| Beaver triples (HE) | 2 ms | 2 ms | 2 ms |
| Read correlations (HE) | 5.3 min | 5.7 s | 5.8 s |
| Key-onehot alpha powers (HE) | 170 ms | 37 ms | 79 ms |
| **total** | **5.3 min** | **5.8 s** | **5.9 s** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 67.69 GB | 0 B | 0 B | 67.69 GB | 0 B | 0 B |
| OT extension | 0 B | 8.89 GB | 2.22 GB | 0 B | 2.22 GB | 0 B |
| Beaver triples (HE) | 136.69 MB | 375.65 MB | 68.30 MB | 85.51 MB | 119.56 MB | 34.17 MB |
| Read correlations (HE) | 9.20 GB | 1.14 TB | 282.22 GB | 5.76 GB | 285.67 GB | 2.30 GB |
| Key-onehot alpha powers (HE) | 10.23 GB | 7.68 GB | 3.15 MB | 6.40 GB | 3.84 GB | 2.56 GB |
| **total** | **87.26 GB** | **1.15 TB** | **284.51 GB** | **79.94 GB** | **291.85 GB** | **4.89 GB** |

Offline phase: 531,424 Beaver triples (65 HE batches of 8192), 2,115,454,972 GC AND gates, 4,376 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 1.6 s | 0 ms | 0 ms |
| OT sender (label transfer) | 37 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 132 ms | 0 ms |
| OT receiver | 0 ms | 9 ms | 9 ms |
| Client: masked selector e_i - r_i (all cores) | 0 ms | 100 ms | 100 ms |
| Client: Beaver products incl. distance sums (all cores) | 0 ms | 133 ms | 133 ms |
| Client: reply combination [y]+[h] | 0 ms | 3 ms | 3 ms |
| Key one-hot, local Lagrange evaluation (real, all cores) | 0 ms | 3 ms | 3 ms |
| **total busy compute** | **1.7 s** | **380 ms** | **249 ms** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 2.12 MB | 65.73 GB | 16.43 GB | 2.12 MB | 16.43 GB | 0 B |
| gc_ot | 17.78 GB | 69.45 MB | 17.36 MB | 4.44 GB | 17.36 MB | 4.44 GB |
| gc_labels | 0 B | 0 B | 0 B | 6.67 GB | 2.22 GB | 0 B |
| read1d_adj | 32.77 KB | 4.10 GB | 1.02 GB | 32.77 KB | 1.02 GB | 0 B |
| read1d_theta | 11.09 KB | 51.25 MB | 12.81 MB | 11.09 KB | 12.81 MB | 0 B |
| beaver_dist | 0 B | 0 B | 12.62 MB | 12.62 MB | 12.62 MB | 12.62 MB |
| gc_out | 0 B | 0 B | 26.86 MB | 0 B | 0 B | 8.95 MB |
| beaver_dict | 0 B | 0 B | 131.33 KB | 131.33 KB | 131.33 KB | 131.33 KB |
| onehot | 0 B | 0 B | 52.51 KB | 52.51 KB | 52.51 KB | 52.51 KB |
| share_query | 0 B | 0 B | 396 B | 396 B | 396 B | 396 B |
| lag_open | 96 B | 96 B | 24 B | 24 B | 24 B | 24 B |
| **total** | **17.78 GB** | **69.94 GB** | **17.53 GB** | **11.13 GB** | **19.72 GB** | **4.47 GB** |

Online rounds: **3068 message flights = 1534 round trips**. LAN communication time: 153 ms for round latency + 56.0 s for transfer = 56.1 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **58.1 s**. Wait: server idle 56.5 s, C1 idle 57.8 s, other clients idle 57.9 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 105.04 GB | 1.22 TB | 1.33 TB |
| C1 (evaluator) | 302.04 GB | 91.06 GB | 393.10 GB |
| each other client | 311.57 GB | 9.36 GB | 320.93 GB |
| **all parties (each byte counted once)** | **1.34 TB** | **1.34 TB** | |

Rounds: online 3068 flights (1534 RTT); offline 3 flights on the critical path (HE phases batched).