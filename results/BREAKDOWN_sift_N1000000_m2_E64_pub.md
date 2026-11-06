# sift_N1000000_m2_E64_pub: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 448 cores; m=2, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 22.8 s | | |
| Server | graph import | 1.6 s | | |
| Server | flatten + LSH + cuckoo tables | 40.2 s | | |
| Server | **total (measured)** | **70.1 s** | | |
| Client C1 | HE threshold keygen (modelled) | 26 ms | 4.72 MB | 2.62 MB |
| Client C2 | HE threshold keygen (modelled) | 26 ms | 4.72 MB | 2.62 MB |
| Server | HE keygen relay/aggregation | | 5.25 MB | 9.45 MB |

## 2. Per-query preprocessing (offline phase, modelled)

### 2a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| GC garbling | 22 ms | 0 ms | 0 ms |
| GC tables | 0 ms | 0 ms | 0 ms |
| OT extension | 2 ms | 1 ms | 1 ms |
| Beaver triples (HE) | 1 ms | 1 ms | 1 ms |
| Read correlations (HE) | 2.7 min | 2.9 s | 2.9 s |
| Key-onehot alpha powers (HE) | 90 ms | 20 ms | 43 ms |
| **total** | **2.7 min** | **2.9 s** | **2.9 s** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 10.13 GB | 0 B | 0 B | 10.13 GB | 0 B | 0 B |
| OT extension | 0 B | 1.12 GB | 558.78 MB | 0 B | 558.78 MB | 0 B |
| Beaver triples (HE) | 34.70 MB | 86.69 MB | 34.68 MB | 26.04 MB | 60.70 MB | 17.35 MB |
| Read correlations (HE) | 2.31 GB | 284.36 GB | 141.60 GB | 1.74 GB | 143.34 GB | 1.16 GB |
| Key-onehot alpha powers (HE) | 2.79 GB | 1.40 GB | 3.15 MB | 2.10 GB | 2.10 GB | 1.40 GB |
| **total** | **15.27 GB** | **286.96 GB** | **142.20 GB** | **13.99 GB** | **146.05 GB** | **2.57 GB** |

Offline phase: 269,784 Beaver triples (33 HE batches of 8192), 316,599,648 GC AND gates, 2,200 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 777 ms | 0 ms | 0 ms |
| OT sender (label transfer) | 5 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 20 ms | 0 ms |
| OT receiver | 0 ms | 2 ms | 2 ms |
| Client: masked selector e_i - r_i (all cores) | 0 ms | 52 ms | 52 ms |
| Client: Beaver products incl. distance sums (all cores) | 0 ms | 75 ms | 75 ms |
| Client: reply combination [y]+[h] | 0 ms | 2 ms | 2 ms |
| Key one-hot, local Lagrange evaluation (real, all cores) | 0 ms | 3 ms | 3 ms |
| **total busy compute** | **782 ms** | **155 ms** | **135 ms** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 1.06 MB | 16.48 GB | 8.24 GB | 1.06 MB | 8.24 GB | 0 B |
| gc_ot | 2.24 GB | 8.73 MB | 4.37 MB | 1.12 GB | 4.37 MB | 1.12 GB |
| read1d_adj | 16.38 KB | 1.02 GB | 512.00 MB | 16.38 KB | 512.00 MB | 0 B |
| gc_labels | 0 B | 0 B | 0 B | 558.78 MB | 558.78 MB | 0 B |
| read1d_theta | 12.10 KB | 25.64 MB | 12.82 MB | 12.10 KB | 12.82 MB | 0 B |
| beaver_dist | 0 B | 0 B | 2.11 MB | 2.11 MB | 2.11 MB | 2.11 MB |
| gc_out | 0 B | 0 B | 2.25 MB | 0 B | 0 B | 2.25 MB |
| beaver_dict | 0 B | 0 B | 47.81 KB | 47.81 KB | 47.81 KB | 47.81 KB |
| onehot | 0 B | 0 B | 8.80 KB | 8.80 KB | 8.80 KB | 8.80 KB |
| share_query | 0 B | 0 B | 260 B | 260 B | 260 B | 260 B |
| lag_open | 48 B | 48 B | 24 B | 24 B | 24 B | 24 B |
| **total** | **2.24 GB** | **17.54 GB** | **8.77 GB** | **1.68 GB** | **9.33 GB** | **1.12 GB** |

Online rounds: **1660 message flights = 830 round trips**. LAN communication time: 83 ms for round latency + 14.0 s for transfer = 14.1 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **15.1 s**. Wait: server idle 14.3 s, C1 idle 14.9 s, other clients idle 14.9 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 17.51 GB | 304.50 GB | 322.01 GB |
| C1 (evaluator) | 150.97 GB | 15.67 GB | 166.64 GB |
| each other client | 155.38 GB | 3.69 GB | 159.08 GB |
| **all parties (each byte counted once)** | **323.86 GB** | **323.86 GB** | |

Rounds: online 1660 flights (830 RTT); offline 3 flights on the critical path (HE phases batched).