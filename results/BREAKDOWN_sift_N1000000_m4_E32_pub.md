# sift_N1000000_m4_E32_pub: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 448 cores; m=4, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 22.2 s | | |
| Server | graph import | 5.4 s | | |
| Server | flatten + LSH + cuckoo tables | 46.5 s | | |
| Server | **total (measured)** | **79.2 s** | | |
| Client C1 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Client C2 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Client C3 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Client C4 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Server | HE keygen relay/aggregation | | 10.50 MB | 18.89 MB |

## 2. Per-query preprocessing (offline phase, modelled)

### 2a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| GC garbling | 9 ms | 0 ms | 0 ms |
| GC tables | 0 ms | 0 ms | 0 ms |
| OT extension | 1 ms | 0 ms | 0 ms |
| Beaver triples (HE) | 1 ms | 0 ms | 1 ms |
| Read correlations (HE) | 81.8 s | 1.5 s | 1.5 s |
| Key-onehot alpha powers (HE) | 185 ms | 40 ms | 87 ms |
| **total** | **82.0 s** | **1.5 s** | **1.5 s** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 4.22 GB | 0 B | 0 B | 4.22 GB | 0 B | 0 B |
| OT extension | 0 B | 565.63 MB | 141.41 MB | 0 B | 141.41 MB | 0 B |
| Beaver triples (HE) | 35.75 MB | 98.25 MB | 17.86 MB | 22.36 MB | 31.27 MB | 8.94 MB |
| Read correlations (HE) | 2.34 GB | 286.92 GB | 71.29 GB | 1.46 GB | 72.17 GB | 584.60 MB |
| Key-onehot alpha powers (HE) | 11.17 GB | 8.39 GB | 3.15 MB | 6.99 GB | 4.19 GB | 2.79 GB |
| **total** | **17.76 GB** | **295.97 GB** | **71.45 GB** | **12.69 GB** | **76.53 GB** | **3.39 GB** |

Offline phase: 138,712 Beaver triples (17 HE batches of 8192), 131,773,692 GC AND gates, 1,112 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 435 ms | 0 ms | 0 ms |
| OT sender (label transfer) | 2 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 8 ms | 0 ms |
| OT receiver | 0 ms | 1 ms | 1 ms |
| Client: masked selector e_i - r_i (all cores) | 0 ms | 29 ms | 29 ms |
| Client: Beaver products incl. distance sums (all cores) | 0 ms | 43 ms | 43 ms |
| Client: reply combination [y]+[h] | 0 ms | 1 ms | 1 ms |
| Key one-hot, local Lagrange evaluation (real, all cores) | 0 ms | 3 ms | 3 ms |
| **total busy compute** | **438 ms** | **85 ms** | **77 ms** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 534.58 KB | 16.58 GB | 4.14 GB | 534.58 KB | 4.14 GB | 0 B |
| gc_ot | 1.13 GB | 4.42 MB | 1.10 MB | 282.81 MB | 1.10 MB | 282.81 MB |
| read1d_adj | 8.19 KB | 1.02 GB | 256.00 MB | 8.19 KB | 256.00 MB | 0 B |
| gc_labels | 0 B | 0 B | 0 B | 424.22 MB | 141.41 MB | 0 B |
| read1d_theta | 12.10 KB | 51.28 MB | 12.82 MB | 12.10 KB | 12.82 MB | 0 B |
| beaver_dist | 0 B | 0 B | 3.19 MB | 3.19 MB | 3.19 MB | 3.19 MB |
| gc_out | 0 B | 0 B | 1.70 MB | 0 B | 0 B | 567.23 KB |
| beaver_dict | 0 B | 0 B | 143.42 KB | 143.42 KB | 143.42 KB | 143.42 KB |
| onehot | 0 B | 0 B | 13.34 KB | 13.34 KB | 13.34 KB | 13.34 KB |
| share_query | 0 B | 0 B | 396 B | 396 B | 396 B | 396 B |
| lag_open | 96 B | 96 B | 24 B | 24 B | 24 B | 24 B |
| **total** | **1.13 GB** | **17.66 GB** | **4.42 GB** | **710.93 MB** | **4.56 GB** | **286.72 MB** |

Online rounds: **956 message flights = 478 round trips**. LAN communication time: 48 ms for round latency + 14.1 s for transfer = 14.2 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **14.7 s**. Wait: server idle 14.3 s, C1 idle 14.6 s, other clients idle 14.6 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 18.89 GB | 313.63 GB | 332.52 GB |
| C1 (evaluator) | 75.87 GB | 13.40 GB | 89.27 GB |
| each other client | 81.09 GB | 3.67 GB | 84.77 GB |
| **all parties (each byte counted once)** | **338.04 GB** | **338.04 GB** | |

Rounds: online 956 flights (478 RTT); offline 3 flights on the critical path (HE phases batched).