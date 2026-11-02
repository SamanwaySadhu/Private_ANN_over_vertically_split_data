# sift_N1000000_m8_E64_mask: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 8 cores; m=8, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 11.2 s | | |
| Server | graph import | 1.6 s | | |
| Server | flatten + LSH + cuckoo tables | 29.9 s | | |
| Server | **total (measured)** | **48.0 s** | | |
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
| OT extension | 8 ms | 58 ms | 58 ms |
| Beaver triples (HE) | 2 ms | 70 ms | 90 ms |
| Read correlations (HE) | 2.9 min | 2.7 min | 2.7 min |
| **total** | **2.9 min** | **2.7 min** | **2.7 min** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 30.42 GB | 0 B | 0 B | 30.42 GB | 0 B | 0 B |
| OT extension | 0 B | 4.49 GB | 560.63 MB | 0 B | 560.63 MB | 0 B |
| Beaver triples (HE) | 180.85 MB | 519.60 MB | 45.18 MB | 101.85 MB | 79.09 MB | 22.61 MB |
| Read correlations (HE) | 9.25 GB | 1.14 TB | 141.60 GB | 5.21 GB | 143.34 GB | 1.16 GB |
| **total** | **39.85 GB** | **1.15 TB** | **142.21 GB** | **35.73 GB** | **143.98 GB** | **1.18 GB** |

Offline phase: 351,360 Beaver triples (43 HE batches of 8192), 950,599,284 GC AND gates, 2,200 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 4.3 s | 0 ms | 0 ms |
| OT sender (label transfer) | 19 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 3.3 s | 0 ms |
| OT receiver | 0 ms | 131 ms | 131 ms |
| Local share arithmetic (Beaver, e-r, ...) | 0 ms | 25.6 s | 25.6 s |
| **total busy compute** | **4.3 s** | **29.0 s** | **25.7 s** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 1.06 MB | 65.92 GB | 8.24 GB | 1.06 MB | 8.24 GB | 0 B |
| gc_ot | 8.97 GB | 35.04 MB | 4.38 MB | 1.12 GB | 4.38 MB | 1.12 GB |
| read1d_adj | 16.38 KB | 4.10 GB | 512.00 MB | 16.38 KB | 512.00 MB | 0 B |
| gc_labels | 0 B | 0 B | 0 B | 3.92 GB | 560.63 MB | 0 B |
| beaver | 0 B | 0 B | 14.77 MB | 14.77 MB | 14.77 MB | 14.77 MB |
| read1d_theta | 116.50 KB | 102.56 MB | 12.82 MB | 116.50 KB | 12.82 MB | 0 B |
| beaver_dict | 0 B | 0 B | 4.39 MB | 4.39 MB | 4.39 MB | 4.39 MB |
| gc_out | 0 B | 0 B | 15.76 MB | 0 B | 0 B | 2.25 MB |
| beaver_hash | 0 B | 0 B | 516.10 KB | 516.10 KB | 516.10 KB | 516.10 KB |
| onehot | 0 B | 0 B | 69.66 KB | 69.66 KB | 69.66 KB | 69.66 KB |
| share_query | 0 B | 0 B | 476 B | 476 B | 476 B | 476 B |
| **total** | **8.97 GB** | **70.15 GB** | **8.80 GB** | **5.07 GB** | **9.35 GB** | **1.14 GB** |

Online rounds: **1778 message flights = 889 round trips**. LAN communication time: 89 ms for round latency + 56.1 s for transfer = 56.2 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **89.6 s**. Wait: server idle 85.3 s, C1 idle 60.5 s, other clients idle 63.9 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 48.82 GB | 1.22 TB | 1.26 TB |
| C1 (evaluator) | 151.01 GB | 40.80 GB | 191.81 GB |
| each other client | 153.32 GB | 2.32 GB | 155.65 GB |
| **all parties (each byte counted once)** | **1.27 TB** | **1.27 TB** | |

Rounds: online 1778 flights (889 RTT); offline 3 flights on the critical path (HE phases batched).