# sift_N1000000_m8_E32_node: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 448 cores; m=8, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 13.2 s | | |
| Server | graph import | 5.3 s | | |
| Server | flatten + LSH + cuckoo tables | 54.0 s | | |
| Server | **total (measured)** | **84.3 s** | | |
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
| Beaver triples (HE) | 94 ms | 69 ms | 89 ms |
| Read correlations (HE) | 84.0 s | 1.4 s | 1.5 s |
| Key-onehot alpha powers (HE) | 11.0 s | 2.3 s | 4.7 s |
| **total** | **95.1 s** | **3.8 s** | **6.3 s** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 7.61 GB | 0 B | 0 B | 7.61 GB | 0 B | 0 B |
| OT extension | 0 B | 1.13 GB | 141.41 MB | 0 B | 141.41 MB | 0 B |
| Beaver triples (HE) | 9.95 GB | 28.59 GB | 2.49 GB | 5.60 GB | 4.35 GB | 1.24 GB |
| Read correlations (HE) | 4.68 GB | 574.43 GB | 71.29 GB | 2.63 GB | 72.17 GB | 584.60 MB |
| Key-onehot alpha powers (HE) | 1.23 TB | 1.07 TB | 37.83 MB | 691.24 GB | 230.19 GB | 153.43 GB |
| **total** | **1.25 TB** | **1.68 TB** | **73.96 GB** | **707.09 GB** | **306.86 GB** | **155.25 GB** |

Offline phase: 19,379,488 Beaver triples (2366 HE batches of 8192), 237,828,660 GC AND gates, 1,112 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 815 ms | 0 ms | 0 ms |
| OT sender (label transfer) | 5 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 15 ms | 0 ms |
| OT receiver | 0 ms | 1 ms | 1 ms |
| Client: masked selector e_i - r_i (all cores) | 0 ms | 28 ms | 28 ms |
| Client: Beaver products incl. distance sums (all cores) | 0 ms | 42 ms | 42 ms |
| Client: reply combination [y]+[h] | 0 ms | 1 ms | 1 ms |
| Key one-hot, local Lagrange evaluation (real, all cores) | 0 ms | 333 ms | 333 ms |
| Client: quantise own block for ALL rows and radii, once per query (all cores) | 0 ms | 0 ms | 0 ms |
| Client: Beaver dot-product selection of the visited row's hash (all cores) | 0 ms | 5 ms | 5 ms |
| **total busy compute** | **820 ms** | **425 ms** | **410 ms** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 534.58 KB | 33.15 GB | 4.14 GB | 534.58 KB | 4.14 GB | 0 B |
| beaver_sel | 0 B | 0 B | 628.28 MB | 628.28 MB | 628.28 MB | 628.28 MB |
| gc_ot | 2.26 GB | 8.84 MB | 1.10 MB | 282.81 MB | 1.10 MB | 282.81 MB |
| read1d_adj | 8.19 KB | 2.05 GB | 256.00 MB | 8.19 KB | 256.00 MB | 0 B |
| gc_labels | 0 B | 0 B | 0 B | 989.85 MB | 141.41 MB | 0 B |
| read1d_theta | 27.50 KB | 102.58 MB | 12.82 MB | 27.50 KB | 12.82 MB | 0 B |
| beaver_dist | 0 B | 0 B | 7.43 MB | 7.43 MB | 7.43 MB | 7.43 MB |
| beaver_dict | 0 B | 0 B | 766.08 KB | 766.08 KB | 766.08 KB | 766.08 KB |
| gc_out | 0 B | 0 B | 3.97 MB | 0 B | 0 B | 567.23 KB |
| onehot | 0 B | 0 B | 31.14 KB | 31.14 KB | 31.14 KB | 31.14 KB |
| lag_open | 2.30 KB | 2.30 KB | 288 B | 288 B | 288 B | 288 B |
| share_query | 0 B | 0 B | 476 B | 476 B | 476 B | 476 B |
| **total** | **2.26 GB** | **35.31 GB** | **5.05 GB** | **1.91 GB** | **5.19 GB** | **919.89 MB** |

Online rounds: **990 message flights = 495 round trips**. LAN communication time: 50 ms for round latency + 28.2 s for transfer = 28.3 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **29.5 s**. Wait: server idle 28.7 s, C1 idle 29.1 s, other clients idle 29.1 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 1.25 TB | 1.71 TB | 2.96 TB |
| C1 (evaluator) | 79.01 GB | 709.00 GB | 788.01 GB |
| each other client | 312.05 GB | 156.17 GB | 468.22 GB |
| **all parties (each byte counted once)** | **3.52 TB** | **3.52 TB** | |

Rounds: online 990 flights (495 RTT); offline 3 flights on the critical path (HE phases batched).