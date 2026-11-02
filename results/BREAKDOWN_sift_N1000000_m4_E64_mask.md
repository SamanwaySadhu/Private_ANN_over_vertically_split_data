# sift_N1000000_m4_E64_mask: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 8 cores; m=4, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 11.0 s | | |
| Server | graph import | 1.7 s | | |
| Server | flatten + LSH + cuckoo tables | 28.5 s | | |
| Server | **total (measured)** | **46.9 s** | | |
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
| OT extension | 4 ms | 58 ms | 58 ms |
| Beaver triples (HE) | 2 ms | 69 ms | 91 ms |
| Read correlations (HE) | 2.9 min | 2.7 min | 2.7 min |
| **total** | **2.9 min** | **2.7 min** | **2.7 min** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 16.94 GB | 0 B | 0 B | 16.94 GB | 0 B | 0 B |
| OT extension | 0 B | 2.24 GB | 560.35 MB | 0 B | 560.35 MB | 0 B |
| Beaver triples (HE) | 90.42 MB | 248.50 MB | 45.18 MB | 56.57 MB | 79.09 MB | 22.61 MB |
| Read correlations (HE) | 4.63 GB | 569.87 GB | 141.60 GB | 2.89 GB | 143.34 GB | 1.16 GB |
| **total** | **21.66 GB** | **572.36 GB** | **142.21 GB** | **19.90 GB** | **143.97 GB** | **1.18 GB** |

Offline phase: 351,360 Beaver triples (43 HE batches of 8192), 529,529,820 GC AND gates, 2,200 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 3.6 s | 0 ms | 0 ms |
| OT sender (label transfer) | 9 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 1.8 s | 0 ms |
| OT receiver | 0 ms | 131 ms | 131 ms |
| Local share arithmetic (Beaver, e-r, ...) | 0 ms | 26.7 s | 26.7 s |
| **total busy compute** | **3.6 s** | **28.7 s** | **26.8 s** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 1.06 MB | 32.96 GB | 8.24 GB | 1.06 MB | 8.24 GB | 0 B |
| gc_ot | 4.48 GB | 17.51 MB | 4.38 MB | 1.12 GB | 4.38 MB | 1.12 GB |
| read1d_adj | 16.38 KB | 2.05 GB | 512.00 MB | 16.38 KB | 512.00 MB | 0 B |
| gc_labels | 0 B | 0 B | 0 B | 1.68 GB | 560.35 MB | 0 B |
| read1d_theta | 116.50 KB | 51.34 MB | 12.84 MB | 116.50 KB | 12.84 MB | 0 B |
| beaver | 0 B | 0 B | 6.33 MB | 6.33 MB | 6.33 MB | 6.33 MB |
| beaver_dict | 0 B | 0 B | 1.88 MB | 1.88 MB | 1.88 MB | 1.88 MB |
| gc_out | 0 B | 0 B | 6.75 MB | 0 B | 0 B | 2.25 MB |
| beaver_hash | 0 B | 0 B | 221.18 KB | 221.18 KB | 221.18 KB | 221.18 KB |
| onehot | 0 B | 0 B | 29.86 KB | 29.86 KB | 29.86 KB | 29.86 KB |
| share_query | 0 B | 0 B | 396 B | 396 B | 396 B | 396 B |
| **total** | **4.48 GB** | **35.08 GB** | **8.78 GB** | **2.81 GB** | **9.34 GB** | **1.13 GB** |

Online rounds: **1778 message flights = 889 round trips**. LAN communication time: 89 ms for round latency + 28.1 s for transfer = 28.2 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **60.4 s**. Wait: server idle 56.8 s, C1 idle 31.7 s, other clients idle 33.6 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 26.15 GB | 607.44 GB | 633.58 GB |
| C1 (evaluator) | 150.99 GB | 22.71 GB | 173.70 GB |
| each other client | 153.31 GB | 2.31 GB | 155.62 GB |
| **all parties (each byte counted once)** | **637.07 GB** | **637.07 GB** | |

Rounds: online 1778 flights (889 RTT); offline 3 flights on the critical path (HE phases batched).