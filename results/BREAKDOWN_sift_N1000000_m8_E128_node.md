# sift_N1000000_m8_E128_node: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 448 cores; m=8, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 12.5 s | | |
| Server | graph import | 1.6 s | | |
| Server | flatten + LSH + cuckoo tables | 51.0 s | | |
| Server | **total (measured)** | **70.7 s** | | |
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
| OT extension | 33 ms | 4 ms | 4 ms |
| Beaver triples (HE) | 95 ms | 70 ms | 90 ms |
| Read correlations (HE) | 5.4 min | 5.7 s | 5.8 s |
| Key-onehot alpha powers (HE) | 11.8 s | 2.4 s | 5.1 s |
| **total** | **5.6 min** | **8.2 s** | **11.0 s** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 121.03 GB | 0 B | 0 B | 121.03 GB | 0 B | 0 B |
| OT extension | 0 B | 17.78 GB | 2.22 GB | 0 B | 2.22 GB | 0 B |
| Beaver triples (HE) | 10.16 GB | 29.18 GB | 2.54 GB | 5.72 GB | 4.44 GB | 1.27 GB |
| Read correlations (HE) | 18.40 GB | 2.27 TB | 282.22 GB | 10.36 GB | 285.67 GB | 2.30 GB |
| Key-onehot alpha powers (HE) | 1.32 TB | 1.15 TB | 37.83 MB | 742.17 GB | 247.15 GB | 164.73 GB |
| **total** | **1.47 TB** | **3.47 TB** | **287.02 GB** | **879.29 GB** | **539.49 GB** | **168.30 GB** |

Offline phase: 19,778,464 Beaver triples (2415 HE batches of 8192), 3,782,267,188 GC AND gates, 4,376 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 3.1 s | 0 ms | 0 ms |
| OT sender (label transfer) | 74 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 235 ms | 0 ms |
| OT receiver | 0 ms | 9 ms | 9 ms |
| Client: masked selector e_i - r_i (all cores) | 0 ms | 110 ms | 110 ms |
| Client: Beaver products incl. distance sums (all cores) | 0 ms | 153 ms | 153 ms |
| Client: reply combination [y]+[h] | 0 ms | 3 ms | 3 ms |
| Key one-hot, local Lagrange evaluation (real, all cores) | 0 ms | 393 ms | 393 ms |
| Client: quantise own block for ALL rows and radii, once per query (all cores) | 0 ms | 0 ms | 0 ms |
| Client: Beaver dot-product selection of the visited row's hash (all cores) | 0 ms | 5 ms | 5 ms |
| **total busy compute** | **3.2 s** | **910 ms** | **674 ms** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 2.12 MB | 131.46 GB | 16.43 GB | 2.12 MB | 16.43 GB | 0 B |
| gc_ot | 35.56 GB | 138.90 MB | 17.36 MB | 4.44 GB | 17.36 MB | 4.44 GB |
| gc_labels | 0 B | 0 B | 0 B | 15.56 GB | 2.22 GB | 0 B |
| read1d_adj | 32.77 KB | 8.19 GB | 1.02 GB | 32.77 KB | 1.02 GB | 0 B |
| beaver_sel | 0 B | 0 B | 628.44 MB | 628.44 MB | 628.44 MB | 628.44 MB |
| beaver_dist | 0 B | 0 B | 29.45 MB | 29.45 MB | 29.45 MB | 29.45 MB |
| read1d_theta | 29.52 KB | 102.60 MB | 12.83 MB | 29.52 KB | 12.83 MB | 0 B |
| gc_out | 0 B | 0 B | 62.67 MB | 0 B | 0 B | 8.95 MB |
| beaver_dict | 0 B | 0 B | 822.53 KB | 822.53 KB | 822.53 KB | 822.53 KB |
| onehot | 0 B | 0 B | 122.53 KB | 122.53 KB | 122.53 KB | 122.53 KB |
| lag_open | 2.30 KB | 2.30 KB | 288 B | 288 B | 288 B | 288 B |
| share_query | 0 B | 0 B | 476 B | 476 B | 476 B | 476 B |
| **total** | **35.56 GB** | **139.89 GB** | **18.21 GB** | **20.66 GB** | **20.37 GB** | **5.11 GB** |

Online rounds: **3102 message flights = 1551 round trips**. LAN communication time: 155 ms for round latency + 111.9 s for transfer = 112.1 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **116.2 s**. Wait: server idle 113.0 s, C1 idle 115.3 s, other clients idle 115.5 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 1.50 TB | 3.61 TB | 5.12 TB |
| C1 (evaluator) | 305.22 GB | 899.95 GB | 1.21 TB |
| each other client | 559.85 GB | 173.41 GB | 733.27 GB |
| **all parties (each byte counted once)** | **5.73 TB** | **5.73 TB** | |

Rounds: online 3102 flights (1551 RTT); offline 3 flights on the critical path (HE phases batched).