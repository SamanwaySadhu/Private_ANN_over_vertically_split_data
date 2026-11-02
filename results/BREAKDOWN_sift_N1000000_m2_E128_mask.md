# sift_N1000000_m2_E128_mask: complete per-party breakdown (LAN 10 Gbps / 0.1 ms; server 448 cores, each client 8 cores; m=2, C1 = GC evaluator)

HE is used ONLY in preprocessing (threshold BFV: Beaver triples and (r,s,h) read correlations). Online uses masked plaintext values, Beaver products, and garbled circuits. Online server read time and all online byte/round counts are measured from the executed protocol; HE/GC/OT preprocessing times and bytes are modelled from native micro-benchmarks (calib/).

## 1. One-time preprocessing

| party | component | time | bytes sent | bytes received |
|---|---|---|---|---|
| Server | HNSW build (hnswlib, 448 cores) | 12.2 s | | |
| Server | graph import | 1.6 s | | |
| Server | flatten + LSH + cuckoo tables | 29.8 s | | |
| Server | **total (measured)** | **48.8 s** | | |
| Client C1 | HE threshold keygen (modelled) | 26 ms | 4.72 MB | 2.62 MB |
| Client C2 | HE threshold keygen (modelled) | 26 ms | 4.72 MB | 2.62 MB |
| Server | HE keygen relay/aggregation | | 5.25 MB | 9.45 MB |

## 2. Per-query preprocessing (offline phase, modelled)

### 2a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| GC garbling | 91 ms | 0 ms | 0 ms |
| GC tables | 0 ms | 0 ms | 0 ms |
| OT extension | 8 ms | 228 ms | 228 ms |
| Beaver triples (HE) | 3 ms | 121 ms | 157 ms |
| Read correlations (HE) | 5.6 min | 5.4 min | 5.4 min |
| **total** | **5.6 min** | **5.4 min** | **5.4 min** |

### 2b. Communication (sent / received)

| component | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| GC garbling | 0 B | 0 B | 0 B | 0 B | 0 B | 0 B |
| GC tables | 41.11 GB | 0 B | 0 B | 41.11 GB | 0 B | 0 B |
| OT extension | 0 B | 4.45 GB | 2.22 GB | 0 B | 2.22 GB | 0 B |
| Beaver triples (HE) | 78.86 MB | 197.02 MB | 78.81 MB | 59.17 MB | 137.96 MB | 39.43 MB |
| Read correlations (HE) | 4.60 GB | 566.73 GB | 282.22 GB | 3.45 GB | 285.67 GB | 2.30 GB |
| **total** | **45.79 GB** | **571.38 GB** | **284.52 GB** | **44.62 GB** | **288.03 GB** | **2.34 GB** |

Offline phase: 613,504 Beaver triples (75 HE batches of 8192), 1,284,605,008 GC AND gates, 4,376 (r,s,h) read correlations. All correlations are generated in one batch, so the offline critical path is 3 message flights for the HE phases (upload ciphertexts, server returns ciphertexts, partial-decryption shares to C1), in parallel with 1 flight for the GC tables and 2 for OT extension.

## 3. Online phase (per query)

### 3a. Compute time

| component | Server | C1 (evaluator) | each other client |
|---|---|---|---|
| Masked 1-D reads A.(e-r) (matrix products) | 7.4 s | 0 ms | 0 ms |
| OT sender (label transfer) | 19 ms | 0 ms | 0 ms |
| GC evaluation | 0 ms | 4.5 s | 0 ms |
| OT receiver | 0 ms | 521 ms | 521 ms |
| Local share arithmetic (Beaver, e-r, ...) | 0 ms | 50.6 s | 50.6 s |
| **total busy compute** | **7.4 s** | **55.6 s** | **51.1 s** |

### 3b. Communication (sent / received)

| category | Server sent | Server recv | C1 sent | C1 recv | other client sent | other client recv |
|---|---|---|---|---|---|---|
| read1d_vec | 2.12 MB | 32.86 GB | 16.43 GB | 2.12 MB | 16.43 GB | 0 B |
| gc_ot | 8.90 GB | 34.75 MB | 17.37 MB | 4.45 GB | 17.37 MB | 4.45 GB |
| gc_labels | 0 B | 0 B | 0 B | 2.22 GB | 2.22 GB | 0 B |
| read1d_adj | 32.77 KB | 2.05 GB | 1.02 GB | 32.77 KB | 1.02 GB | 0 B |
| read1d_theta | 116.50 KB | 25.65 MB | 12.83 MB | 116.50 KB | 12.83 MB | 0 B |
| gc_out | 0 B | 0 B | 8.95 MB | 0 B | 0 B | 8.95 MB |
| beaver | 0 B | 0 B | 4.21 MB | 4.21 MB | 4.21 MB | 4.21 MB |
| beaver_dict | 0 B | 0 B | 626.69 KB | 626.69 KB | 626.69 KB | 626.69 KB |
| beaver_hash | 0 B | 0 B | 73.73 KB | 73.73 KB | 73.73 KB | 73.73 KB |
| onehot | 0 B | 0 B | 18.66 KB | 18.66 KB | 18.66 KB | 18.66 KB |
| share_query | 0 B | 0 B | 260 B | 260 B | 260 B | 260 B |
| **total** | **8.90 GB** | **34.97 GB** | **17.50 GB** | **6.68 GB** | **19.71 GB** | **4.46 GB** |

Online rounds: **3186 message flights = 1593 round trips**. LAN communication time: 159 ms for round latency + 28.0 s for transfer = 28.1 s.

Online latency (compute of server + C1, plus LAN communication, no overlap): **91.2 s**. Wait: server idle 83.7 s, C1 idle 35.5 s, other clients idle 40.0 s.

## 4. Totals (offline + online, per query)

| party | bytes sent | bytes received | total |
|---|---|---|---|
| Server | 54.68 GB | 606.35 GB | 661.04 GB |
| C1 (evaluator) | 302.02 GB | 51.30 GB | 353.32 GB |
| each other client | 307.75 GB | 6.80 GB | 314.55 GB |
| **all parties (each byte counted once)** | **664.45 GB** | **664.45 GB** | |

Rounds: online 3186 flights (1593 RTT); offline 3 flights on the critical path (HE phases batched).