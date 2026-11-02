# sift_N1000000_m2_E64_mask: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 8 cores; m=2, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 10.3 s | | |
| Server | graph import | 1.7 s | | |
| Server | flatten + LSH + cuckoo tables | 30.7 s | | |
| Server | **total (measured)** | **47.8 s** | | |
| Client C1 | HE threshold keygen (modelled) | 26 ms | 4.72 MB | 2.62 MB |
| Client C2 | HE threshold keygen (modelled) | 26 ms | 4.72 MB | 2.62 MB |
| Server | HE keygen relay/aggregation | | 5.25 MB | 9.45 MB |

## 2. Per-query preprocessing (offline phase, modelled)

### 2a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| GC garbling | 23 ms | 0 ms | 0 ms |
| GC tables | 0 ms | 0 ms | 0 ms |
| OT extension | 2 ms | 58 ms | 58 ms |
| Beaver triples (HE) | 1 ms | 69 ms | 90 ms |
| Read correlations (HE) | 2.9 min | 2.7 min | 2.7 min |
| **total** | **2.9 min** | **2.7 min** | **2.7 min** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 10.21 GB | 0 B | 0 B | 10.21 GB | 0 B | 0 B |
| OT extension | 0 B | 1.12 GB | 560.21 MB | 0 B | 560.21 MB | 0 B |
| Beaver triples (HE) | 45.21 MB | 112.96 MB | 45.18 MB | 33.93 MB | 79.09 MB | 22.61 MB |
| Read correlations (HE) | 2.31 GB | 284.36 GB | 141.60 GB | 1.74 GB | 143.34 GB | 1.16 GB |
| **total** | **12.57 GB** | **285.59 GB** | **142.21 GB** | **11.98 GB** | **143.97 GB** | **1.18 GB** |

Offline phase: 351,360 Beaver triples (43 HE batches of 8192), 319,155,792 GC AND gates, 2,200 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 3.9 s | 0 ms | 0 ms |
| OT sender (label transfer) | 5 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 1.1 s | 0 ms |
| OT receiver | 0 ms | 131 ms | 131 ms |
| Local share arithmetic (Beaver, e-r, ...) | 0 ms | 25.4 s | 25.4 s |
| **total busy compute** | **4.0 s** | **26.6 s** | **25.5 s** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 1.06 MB | 16.48 GB | 8.24 GB | 1.06 MB | 8.24 GB | 0 B |
| gc_ot | 2.24 GB | 8.75 MB | 4.38 MB | 1.12 GB | 4.38 MB | 1.12 GB |
| read1d_adj | 16.38 KB | 1.02 GB | 512.00 MB | 16.38 KB | 512.00 MB | 0 B |
| gc_labels | 0 B | 0 B | 0 B | 560.21 MB | 560.21 MB | 0 B |
| read1d_theta | 116.50 KB | 25.65 MB | 12.83 MB | 116.50 KB | 12.83 MB | 0 B |
| beaver | 0 B | 0 B | 2.11 MB | 2.11 MB | 2.11 MB | 2.11 MB |
| gc_out | 0 B | 0 B | 2.25 MB | 0 B | 0 B | 2.25 MB |
| beaver_dict | 0 B | 0 B | 626.69 KB | 626.69 KB | 626.69 KB | 626.69 KB |
| beaver_hash | 0 B | 0 B | 73.73 KB | 73.73 KB | 73.73 KB | 73.73 KB |
| onehot | 0 B | 0 B | 9.95 KB | 9.95 KB | 9.95 KB | 9.95 KB |
| share_query | 0 B | 0 B | 260 B | 260 B | 260 B | 260 B |
| **total** | **2.24 GB** | **17.54 GB** | **8.77 GB** | **1.68 GB** | **9.33 GB** | **1.13 GB** |

Online rounds: **1778 message flights = 889 round trips**. LAN communication time: 89 ms for round latency + 14.0 s for transfer = 14.1 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **44.7 s**. Wait: server idle 40.7 s, C1 idle 18.1 s, other clients idle 19.2 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 14.81 GB | 303.13 GB | 317.94 GB |
| C1 (evaluator) | 150.98 GB | 13.67 GB | 164.65 GB |
| each other client | 153.31 GB | 2.30 GB | 155.61 GB |
| **all parties (each byte counted once)** | **319.10 GB** | **319.10 GB** | |

Rounds: online 1778 flights (889 RTT); offline 3 flights on the critical path (HE phases batched).