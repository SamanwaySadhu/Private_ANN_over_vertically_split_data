# sift_N1000000_m2_E128_pub: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 448 cores; m=2, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 23.6 s | | |
| Server | graph import | 3.6 s | | |
| Server | flatten + LSH + cuckoo tables | 44.3 s | | |
| Server | **total (measured)** | **77.0 s** | | |
| Client C1 | HE threshold keygen (modelled) | 26 ms | 4.72 MB | 2.62 MB |
| Client C2 | HE threshold keygen (modelled) | 26 ms | 4.72 MB | 2.62 MB |
| Server | HE keygen relay/aggregation | | 5.25 MB | 9.45 MB |

## 2. Per-query preprocessing (offline phase, modelled)

### 2a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| GC garbling | 91 ms | 0 ms | 0 ms |
| GC tables | 0 ms | 0 ms | 0 ms |
| OT extension | 8 ms | 4 ms | 4 ms |
| Beaver triples (HE) | 2 ms | 2 ms | 2 ms |
| Read correlations (HE) | 5.3 min | 5.7 s | 5.8 s |
| Key-onehot alpha powers (HE) | 90 ms | 20 ms | 43 ms |
| **total** | **5.4 min** | **5.8 s** | **5.8 s** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 41.03 GB | 0 B | 0 B | 41.03 GB | 0 B | 0 B |
| OT extension | 0 B | 4.44 GB | 2.22 GB | 0 B | 2.22 GB | 0 B |
| Beaver triples (HE) | 68.34 MB | 170.75 MB | 68.30 MB | 51.28 MB | 119.56 MB | 34.17 MB |
| Read correlations (HE) | 4.60 GB | 566.73 GB | 282.22 GB | 3.45 GB | 285.67 GB | 2.30 GB |
| Key-onehot alpha powers (HE) | 2.79 GB | 1.40 GB | 3.15 MB | 2.10 GB | 2.10 GB | 1.40 GB |
| **total** | **48.49 GB** | **572.75 GB** | **284.51 GB** | **46.62 GB** | **290.11 GB** | **3.73 GB** |

Offline phase: 531,928 Beaver triples (65 HE batches of 8192), 1,282,048,864 GC AND gates, 4,376 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 1.5 s | 0 ms | 0 ms |
| OT sender (label transfer) | 19 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 80 ms | 0 ms |
| OT receiver | 0 ms | 9 ms | 9 ms |
| Client: masked selector e_i - r_i (all cores) | 0 ms | 117 ms | 117 ms |
| Client: Beaver products incl. distance sums (all cores) | 0 ms | 162 ms | 162 ms |
| Client: reply combination [y]+[h] | 0 ms | 3 ms | 3 ms |
| Key one-hot, local Lagrange evaluation (real, all cores) | 0 ms | 4 ms | 4 ms |
| **total busy compute** | **1.6 s** | **375 ms** | **295 ms** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 2.12 MB | 32.86 GB | 16.43 GB | 2.12 MB | 16.43 GB | 0 B |
| gc_ot | 8.89 GB | 34.73 MB | 17.36 MB | 4.44 GB | 17.36 MB | 4.44 GB |
| gc_labels | 0 B | 0 B | 0 B | 2.22 GB | 2.22 GB | 0 B |
| read1d_adj | 32.77 KB | 2.05 GB | 1.02 GB | 32.77 KB | 1.02 GB | 0 B |
| read1d_theta | 12.10 KB | 25.62 MB | 12.81 MB | 12.10 KB | 12.81 MB | 0 B |
| gc_out | 0 B | 0 B | 8.95 MB | 0 B | 0 B | 8.95 MB |
| beaver_dist | 0 B | 0 B | 4.21 MB | 4.21 MB | 4.21 MB | 4.21 MB |
| beaver_dict | 0 B | 0 B | 47.81 KB | 47.81 KB | 47.81 KB | 47.81 KB |
| onehot | 0 B | 0 B | 17.50 KB | 17.50 KB | 17.50 KB | 17.50 KB |
| share_query | 0 B | 0 B | 260 B | 260 B | 260 B | 260 B |
| lag_open | 48 B | 48 B | 24 B | 24 B | 24 B | 24 B |
| **total** | **8.89 GB** | **34.97 GB** | **17.50 GB** | **6.67 GB** | **19.71 GB** | **4.46 GB** |

Online rounds: **3068 message flights = 1534 round trips**. LAN communication time: 153 ms for round latency + 28.0 s for transfer = 28.1 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **30.1 s**. Wait: server idle 28.5 s, C1 idle 29.7 s, other clients idle 29.8 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 57.38 GB | 607.72 GB | 665.10 GB |
| C1 (evaluator) | 302.01 GB | 53.30 GB | 355.31 GB |
| each other client | 309.82 GB | 8.19 GB | 318.01 GB |
| **all parties (each byte counted once)** | **669.21 GB** | **669.21 GB** | |

Rounds: online 3068 flights (1534 RTT); offline 3 flights on the critical path (HE phases batched).