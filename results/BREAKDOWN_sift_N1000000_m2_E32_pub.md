# sift_N1000000_m2_E32_pub: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 448 cores; m=2, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 25.8 s | | |
| Server | graph import | 2.5 s | | |
| Server | flatten + LSH + cuckoo tables | 49.5 s | | |
| Server | **total (measured)** | **83.3 s** | | |
| Client C1 | HE threshold keygen (modelled) | 26 ms | 4.72 MB | 2.62 MB |
| Client C2 | HE threshold keygen (modelled) | 26 ms | 4.72 MB | 2.62 MB |
| Server | HE keygen relay/aggregation | | 5.25 MB | 9.45 MB |

## 2. Per-query preprocessing (offline phase, modelled)

### 2a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| GC garbling | 6 ms | 0 ms | 0 ms |
| GC tables | 0 ms | 0 ms | 0 ms |
| OT extension | 1 ms | 0 ms | 0 ms |
| Beaver triples (HE) | 1 ms | 0 ms | 1 ms |
| Read correlations (HE) | 82.0 s | 1.4 s | 1.5 s |
| Key-onehot alpha powers (HE) | 90 ms | 20 ms | 43 ms |
| **total** | **82.1 s** | **1.5 s** | **1.5 s** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 2.52 GB | 0 B | 0 B | 2.52 GB | 0 B | 0 B |
| OT extension | 0 B | 282.81 MB | 141.41 MB | 0 B | 141.41 MB | 0 B |
| Beaver triples (HE) | 17.87 MB | 44.66 MB | 17.86 MB | 13.41 MB | 31.27 MB | 8.94 MB |
| Read correlations (HE) | 1.17 GB | 143.17 GB | 71.29 GB | 877.35 MB | 72.17 GB | 584.60 MB |
| Key-onehot alpha powers (HE) | 2.79 GB | 1.40 GB | 3.15 MB | 2.10 GB | 2.10 GB | 1.40 GB |
| **total** | **6.50 GB** | **144.90 GB** | **71.45 GB** | **5.51 GB** | **74.44 GB** | **1.99 GB** |

Offline phase: 138,712 Beaver triples (17 HE batches of 8192), 78,746,208 GC AND gates, 1,112 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 416 ms | 0 ms | 0 ms |
| OT sender (label transfer) | 1 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 5 ms | 0 ms |
| OT receiver | 0 ms | 1 ms | 1 ms |
| Client: masked selector e_i - r_i (all cores) | 0 ms | 27 ms | 27 ms |
| Client: Beaver products incl. distance sums (all cores) | 0 ms | 44 ms | 44 ms |
| Client: reply combination [y]+[h] | 0 ms | 1 ms | 1 ms |
| Key one-hot, local Lagrange evaluation (real, all cores) | 0 ms | 3 ms | 3 ms |
| **total busy compute** | **417 ms** | **81 ms** | **76 ms** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 534.58 KB | 8.29 GB | 4.14 GB | 534.58 KB | 4.14 GB | 0 B |
| gc_ot | 565.63 MB | 2.21 MB | 1.10 MB | 282.81 MB | 1.10 MB | 282.81 MB |
| read1d_adj | 8.19 KB | 512.00 MB | 256.00 MB | 8.19 KB | 256.00 MB | 0 B |
| gc_labels | 0 B | 0 B | 0 B | 141.41 MB | 141.41 MB | 0 B |
| read1d_theta | 12.10 KB | 25.64 MB | 12.82 MB | 12.10 KB | 12.82 MB | 0 B |
| beaver_dist | 0 B | 0 B | 1.06 MB | 1.06 MB | 1.06 MB | 1.06 MB |
| gc_out | 0 B | 0 B | 567.23 KB | 0 B | 0 B | 567.23 KB |
| beaver_dict | 0 B | 0 B | 47.81 KB | 47.81 KB | 47.81 KB | 47.81 KB |
| onehot | 0 B | 0 B | 4.45 KB | 4.45 KB | 4.45 KB | 4.45 KB |
| share_query | 0 B | 0 B | 260 B | 260 B | 260 B | 260 B |
| lag_open | 48 B | 48 B | 24 B | 24 B | 24 B | 24 B |
| **total** | **566.18 MB** | **8.83 GB** | **4.42 GB** | **425.89 MB** | **4.56 GB** | **284.49 MB** |

Online rounds: **956 message flights = 478 round trips**. LAN communication time: 48 ms for round latency + 7.1 s for transfer = 7.1 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **7.6 s**. Wait: server idle 7.2 s, C1 idle 7.5 s, other clients idle 7.5 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 7.07 GB | 153.73 GB | 160.79 GB |
| C1 (evaluator) | 75.87 GB | 5.93 GB | 81.80 GB |
| each other client | 79.00 GB | 2.27 GB | 81.27 GB |
| **all parties (each byte counted once)** | **161.93 GB** | **161.93 GB** | |

Rounds: online 956 flights (478 RTT); offline 3 flights on the critical path (HE phases batched).