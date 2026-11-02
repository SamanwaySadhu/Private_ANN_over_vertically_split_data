# sift_N1000000_m8_E64_pub: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 448 cores; m=8, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 11.8 s | | |
| Server | graph import | 1.6 s | | |
| Server | flatten + LSH + cuckoo tables | 17.9 s | | |
| Server | **total (measured)** | **36.5 s** | | |
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
| GC garbling | 67 ms | 0 ms | 0 ms |
| GC tables | 0 ms | 0 ms | 0 ms |
| OT extension | 8 ms | 1 ms | 1 ms |
| Beaver triples (HE) | 1 ms | 1 ms | 1 ms |
| Read correlations (HE) | 2.7 min | 2.9 s | 2.9 s |
| Key-onehot alpha powers (HE) | 400 ms | 83 ms | 173 ms |
| **total** | **2.7 min** | **3.0 s** | **3.1 s** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 30.25 GB | 0 B | 0 B | 30.25 GB | 0 B | 0 B |
| OT extension | 0 B | 4.47 GB | 558.78 MB | 0 B | 558.78 MB | 0 B |
| Beaver triples (HE) | 138.79 MB | 398.76 MB | 34.68 MB | 78.16 MB | 60.70 MB | 17.35 MB |
| Read correlations (HE) | 9.25 GB | 1.14 TB | 141.60 GB | 5.21 GB | 143.34 GB | 1.16 GB |
| Key-onehot alpha powers (HE) | 44.68 GB | 39.10 GB | 3.15 MB | 25.16 GB | 8.38 GB | 5.59 GB |
| **total** | **84.32 GB** | **1.18 TB** | **142.20 GB** | **60.70 GB** | **152.34 GB** | **6.76 GB** |

Offline phase: 269,784 Beaver triples (33 HE batches of 8192), 945,223,476 GC AND gates, 2,200 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 1.6 s | 0 ms | 0 ms |
| OT sender (label transfer) | 19 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 59 ms | 0 ms |
| OT receiver | 0 ms | 2 ms | 2 ms |
| Client: masked selector e_i - r_i (all cores) | 0 ms | 55 ms | 55 ms |
| Client: Beaver products incl. distance sums (all cores) | 0 ms | 75 ms | 75 ms |
| Client: reply combination [y]+[h] | 0 ms | 2 ms | 2 ms |
| Key one-hot, local Lagrange evaluation (real, all cores) | 0 ms | 3 ms | 3 ms |
| **total busy compute** | **1.6 s** | **197 ms** | **138 ms** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 1.06 MB | 65.92 GB | 8.24 GB | 1.06 MB | 8.24 GB | 0 B |
| gc_ot | 8.94 GB | 34.92 MB | 4.37 MB | 1.12 GB | 4.37 MB | 1.12 GB |
| read1d_adj | 16.38 KB | 4.10 GB | 512.00 MB | 16.38 KB | 512.00 MB | 0 B |
| gc_labels | 0 B | 0 B | 0 B | 3.91 GB | 558.78 MB | 0 B |
| beaver_dist | 0 B | 0 B | 14.77 MB | 14.77 MB | 14.77 MB | 14.77 MB |
| read1d_theta | 12.10 KB | 102.58 MB | 12.82 MB | 12.10 KB | 12.82 MB | 0 B |
| gc_out | 0 B | 0 B | 15.74 MB | 0 B | 0 B | 2.25 MB |
| beaver_dict | 0 B | 0 B | 334.66 KB | 334.66 KB | 334.66 KB | 334.66 KB |
| onehot | 0 B | 0 B | 61.60 KB | 61.60 KB | 61.60 KB | 61.60 KB |
| share_query | 0 B | 0 B | 476 B | 476 B | 476 B | 476 B |
| lag_open | 192 B | 192 B | 24 B | 24 B | 24 B | 24 B |
| **total** | **8.94 GB** | **70.15 GB** | **8.80 GB** | **5.05 GB** | **9.34 GB** | **1.13 GB** |

Online rounds: **1660 message flights = 830 round trips**. LAN communication time: 83 ms for round latency + 56.1 s for transfer = 56.2 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **58.0 s**. Wait: server idle 56.4 s, C1 idle 57.8 s, other clients idle 57.9 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 93.26 GB | 1.26 TB | 1.35 TB |
| C1 (evaluator) | 151.00 GB | 65.74 GB | 216.74 GB |
| each other client | 161.68 GB | 7.89 GB | 169.57 GB |
| **all parties (each byte counted once)** | **1.38 TB** | **1.38 TB** | |

Rounds: online 1660 flights (830 RTT); offline 3 flights on the critical path (HE phases batched).