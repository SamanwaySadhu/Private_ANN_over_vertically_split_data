# sift_N1000000_m8_E32_pub: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 448 cores; m=8, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 11.5 s | | |
| Server | graph import | 1.6 s | | |
| Server | flatten + LSH + cuckoo tables | 19.1 s | | |
| Server | **total (measured)** | **37.4 s** | | |
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
| OT extension | 2 ms | 0 ms | 0 ms |
| Beaver triples (HE) | 1 ms | 0 ms | 1 ms |
| Read correlations (HE) | 82.2 s | 1.4 s | 1.5 s |
| Key-onehot alpha powers (HE) | 390 ms | 81 ms | 169 ms |
| **total** | **82.6 s** | **1.5 s** | **1.6 s** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 7.61 GB | 0 B | 0 B | 7.61 GB | 0 B | 0 B |
| OT extension | 0 B | 1.13 GB | 141.41 MB | 0 B | 141.41 MB | 0 B |
| Beaver triples (HE) | 71.50 MB | 205.42 MB | 17.86 MB | 40.27 MB | 31.27 MB | 8.94 MB |
| Read correlations (HE) | 4.68 GB | 574.43 GB | 71.29 GB | 2.63 GB | 72.17 GB | 584.60 MB |
| Key-onehot alpha powers (HE) | 43.61 GB | 38.16 GB | 3.15 MB | 24.56 GB | 8.18 GB | 5.45 GB |
| **total** | **55.96 GB** | **613.92 GB** | **71.45 GB** | **34.84 GB** | **80.52 GB** | **6.04 GB** |

Offline phase: 138,568 Beaver triples (17 HE batches of 8192), 237,828,660 GC AND gates, 1,112 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 820 ms | 0 ms | 0 ms |
| OT sender (label transfer) | 5 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 15 ms | 0 ms |
| OT receiver | 0 ms | 1 ms | 1 ms |
| Client: masked selector e_i - r_i (all cores) | 0 ms | 29 ms | 29 ms |
| Client: Beaver products incl. distance sums (all cores) | 0 ms | 43 ms | 43 ms |
| Client: reply combination [y]+[h] | 0 ms | 1 ms | 1 ms |
| Key one-hot, local Lagrange evaluation (real, all cores) | 0 ms | 4 ms | 4 ms |
| **total busy compute** | **825 ms** | **92 ms** | **77 ms** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 534.58 KB | 33.15 GB | 4.14 GB | 534.58 KB | 4.14 GB | 0 B |
| gc_ot | 2.26 GB | 8.84 MB | 1.10 MB | 282.81 MB | 1.10 MB | 282.81 MB |
| read1d_adj | 8.19 KB | 2.05 GB | 256.00 MB | 8.19 KB | 256.00 MB | 0 B |
| gc_labels | 0 B | 0 B | 0 B | 989.85 MB | 141.41 MB | 0 B |
| read1d_theta | 11.81 KB | 102.55 MB | 12.82 MB | 11.81 KB | 12.82 MB | 0 B |
| beaver_dist | 0 B | 0 B | 7.43 MB | 7.43 MB | 7.43 MB | 7.43 MB |
| gc_out | 0 B | 0 B | 3.97 MB | 0 B | 0 B | 567.23 KB |
| beaver_dict | 0 B | 0 B | 326.59 KB | 326.59 KB | 326.59 KB | 326.59 KB |
| onehot | 0 B | 0 B | 31.14 KB | 31.14 KB | 31.14 KB | 31.14 KB |
| share_query | 0 B | 0 B | 476 B | 476 B | 476 B | 476 B |
| lag_open | 192 B | 192 B | 24 B | 24 B | 24 B | 24 B |
| **total** | **2.26 GB** | **35.31 GB** | **4.43 GB** | **1.28 GB** | **4.56 GB** | **291.17 MB** |

Online rounds: **956 message flights = 478 round trips**. LAN communication time: 48 ms for round latency + 28.2 s for transfer = 28.3 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **29.2 s**. Wait: server idle 28.4 s, C1 idle 29.1 s, other clients idle 29.1 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 58.23 GB | 649.23 GB | 707.46 GB |
| C1 (evaluator) | 75.88 GB | 36.12 GB | 112.00 GB |
| each other client | 85.08 GB | 6.34 GB | 91.42 GB |
| **all parties (each byte counted once)** | **729.70 GB** | **729.70 GB** | |

Rounds: online 956 flights (478 RTT); offline 3 flights on the critical path (HE phases batched).