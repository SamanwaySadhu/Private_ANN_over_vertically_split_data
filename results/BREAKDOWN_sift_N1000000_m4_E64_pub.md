# sift_N1000000_m4_E64_pub: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 448 cores; m=4, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 24.2 s | | |
| Server | graph import | 3.8 s | | |
| Server | flatten + LSH + cuckoo tables | 52.1 s | | |
| Server | **total (measured)** | **85.5 s** | | |
| Client C1 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Client C2 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Client C3 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Client C4 | HE threshold keygen (modelled) | 28 ms | 4.72 MB | 2.62 MB |
| Server | HE keygen relay/aggregation | | 10.50 MB | 18.89 MB |

## 2. Per-query preprocessing (offline phase, modelled)

### 2a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| GC garbling | 37 ms | 0 ms | 0 ms |
| GC tables | 0 ms | 0 ms | 0 ms |
| OT extension | 4 ms | 1 ms | 1 ms |
| Beaver triples (HE) | 1 ms | 1 ms | 1 ms |
| Read correlations (HE) | 2.7 min | 2.9 s | 2.9 s |
| Key-onehot alpha powers (HE) | 188 ms | 41 ms | 88 ms |
| **total** | **2.7 min** | **2.9 s** | **3.0 s** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 16.84 GB | 0 B | 0 B | 16.84 GB | 0 B | 0 B |
| OT extension | 0 B | 2.24 GB | 558.78 MB | 0 B | 558.78 MB | 0 B |
| Beaver triples (HE) | 69.40 MB | 190.71 MB | 34.68 MB | 43.41 MB | 60.70 MB | 17.35 MB |
| Read correlations (HE) | 4.63 GB | 569.87 GB | 141.60 GB | 2.89 GB | 143.34 GB | 1.16 GB |
| Key-onehot alpha powers (HE) | 11.31 GB | 8.49 GB | 3.15 MB | 7.07 GB | 4.24 GB | 2.83 GB |
| **total** | **32.84 GB** | **580.78 GB** | **142.20 GB** | **26.85 GB** | **148.20 GB** | **4.00 GB** |

Offline phase: 269,856 Beaver triples (33 HE batches of 8192), 526,140,924 GC AND gates, 2,200 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 847 ms | 0 ms | 0 ms |
| OT sender (label transfer) | 9 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 33 ms | 0 ms |
| OT receiver | 0 ms | 2 ms | 2 ms |
| Client: masked selector e_i - r_i (all cores) | 0 ms | 55 ms | 55 ms |
| Client: Beaver products incl. distance sums (all cores) | 0 ms | 85 ms | 85 ms |
| Client: reply combination [y]+[h] | 0 ms | 2 ms | 2 ms |
| Key one-hot, local Lagrange evaluation (real, all cores) | 0 ms | 3 ms | 3 ms |
| **total busy compute** | **856 ms** | **181 ms** | **148 ms** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 1.06 MB | 32.96 GB | 8.24 GB | 1.06 MB | 8.24 GB | 0 B |
| gc_ot | 4.47 GB | 17.46 MB | 4.37 MB | 1.12 GB | 4.37 MB | 1.12 GB |
| read1d_adj | 16.38 KB | 2.05 GB | 512.00 MB | 16.38 KB | 512.00 MB | 0 B |
| gc_labels | 0 B | 0 B | 0 B | 1.68 GB | 558.78 MB | 0 B |
| read1d_theta | 12.24 KB | 51.27 MB | 12.82 MB | 12.24 KB | 12.82 MB | 0 B |
| beaver_dist | 0 B | 0 B | 6.33 MB | 6.33 MB | 6.33 MB | 6.33 MB |
| gc_out | 0 B | 0 B | 6.74 MB | 0 B | 0 B | 2.25 MB |
| beaver_dict | 0 B | 0 B | 145.15 KB | 145.15 KB | 145.15 KB | 145.15 KB |
| onehot | 0 B | 0 B | 26.40 KB | 26.40 KB | 26.40 KB | 26.40 KB |
| share_query | 0 B | 0 B | 396 B | 396 B | 396 B | 396 B |
| lag_open | 96 B | 96 B | 24 B | 24 B | 24 B | 24 B |
| **total** | **4.47 GB** | **35.08 GB** | **8.78 GB** | **2.80 GB** | **9.33 GB** | **1.13 GB** |

Online rounds: **1660 message flights = 830 round trips**. LAN communication time: 83 ms for round latency + 28.1 s for transfer = 28.1 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **29.2 s**. Wait: server idle 28.3 s, C1 idle 29.0 s, other clients idle 29.0 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 37.31 GB | 615.86 GB | 653.17 GB |
| C1 (evaluator) | 150.98 GB | 29.65 GB | 180.63 GB |
| each other client | 157.53 GB | 5.13 GB | 162.66 GB |
| **all parties (each byte counted once)** | **660.88 GB** | **660.88 GB** | |

Rounds: online 1660 flights (830 RTT); offline 3 flights on the critical path (HE phases batched).