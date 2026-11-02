# LAN breakdown (10 Gbps, 0.1 ms RTT; server 64 cores, each client 8 cores)


## HE row selector: broadcast


### sift_N100000_m4_E64

**Preprocessing (one-time, server, measured, 448 cores)**: HNSW build 1.0 s, graph import 166 ms, flatten + LSH + cuckoo tables 5.5 s; total 7.0 s.

**Preprocessing (one-time, each client, modelled)**: HE threshold keygen 28 ms, 4.72 MB.

| per-query offline component (modelled) | server | each client | note |
|---|---|---|---|
| GC garbling | 255 ms | - | tables 16.50 GB to P1 |
| OT extension (input labels) | 66 ms | 131 ms | 560.35 MB/client |
| Beaver triples (273,024) | 8 ms | 72 ms | 80.41 MB/client |
| (r,s,h) read correlations | 14.5 min | 17.7 s | 16.70 GB/client |
| **total** | **14.5 min** | **17.9 s** | 17.35 GB/client |

| online component | server | P1 | other clients |
|---|---|---|---|
| read1d_matmul | 2.1 s | - | - |
| he_server | 18.8 s | - | - |
| ot_send | 66 ms | - | - |
| he_encrypt | - | 3.2 min | 3.2 min |
| he_threshold_decrypt | - | 244 ms | 183 ms |
| gc_evaluate | - | 1.8 s | 0 ms |
| ot_receive | - | 131 ms | 131 ms |
| local_share_arith | - | 3.3 s | 3.3 s |
| network (flights 1814, transfer) | 9.1 min | 9.1 min | 9.1 min |
| **busy compute** | **21.0 s** | **3.3 min** | **3.2 min** |
| **end-to-end latency** | 12.7 min | | |
| wait (network / peer compute) | 9.1 min / 3.3 min | 9.1 min / 21.0 s | 9.1 min / 22.5 s |


### gist_N100000_m4_E64

**Preprocessing (one-time, server, measured, 448 cores)**: HNSW build 1.8 s, graph import 499 ms, flatten + LSH + cuckoo tables 10.0 s; total 12.5 s.

**Preprocessing (one-time, each client, modelled)**: HE threshold keygen 28 ms, 4.72 MB.

| per-query offline component (modelled) | server | each client | note |
|---|---|---|---|
| GC garbling | 256 ms | - | tables 16.54 GB to P1 |
| OT extension (input labels) | 66 ms | 131 ms | 560.35 MB/client |
| Beaver triples (2,047,680) | 59 ms | 526 ms | 591.28 MB/client |
| (r,s,h) read correlations | 106.7 min | 17.7 s | 16.70 GB/client |
| **total** | **106.7 min** | **18.3 s** | 17.86 GB/client |

| online component | server | P1 | other clients |
|---|---|---|---|
| read1d_matmul | 4.8 s | - | - |
| he_server | 18.9 s | - | - |
| ot_send | 66 ms | - | - |
| he_encrypt | - | 3.2 min | 3.2 min |
| he_threshold_decrypt | - | 244 ms | 183 ms |
| gc_evaluate | - | 1.8 s | 0 ms |
| ot_receive | - | 131 ms | 131 ms |
| local_share_arith | - | 3.3 s | 3.3 s |
| network (flights 1814, transfer) | 9.1 min | 9.1 min | 9.1 min |
| **busy compute** | **23.7 s** | **3.3 min** | **3.2 min** |
| **end-to-end latency** | 12.8 min | | |
| wait (network / peer compute) | 9.1 min / 3.3 min | 9.1 min / 23.7 s | 9.1 min / 25.2 s |


### sift_N1000000_m4_E64

**Preprocessing (one-time, server, measured, 448 cores)**: HNSW build 7.6 s, graph import 1.6 s, flatten + LSH + cuckoo tables 29.9 s; total 44.1 s.

**Preprocessing (one-time, each client, modelled)**: HE threshold keygen 28 ms, 4.72 MB.

| per-query offline component (modelled) | server | each client | note |
|---|---|---|---|
| GC garbling | 262 ms | - | tables 16.94 GB to P1 |
| OT extension (input labels) | 66 ms | 131 ms | 560.35 MB/client |
| Beaver triples (273,024) | 8 ms | 72 ms | 80.41 MB/client |
| (r,s,h) read correlations | 19.2 min | 2.7 min | 143.34 GB/client |
| **total** | **19.2 min** | **2.7 min** | 143.98 GB/client |

| online component | server | P1 | other clients |
|---|---|---|---|
| read1d_matmul | 47.1 s | - | - |
| he_server | 3.1 min | - | - |
| ot_send | 66 ms | - | - |
| he_encrypt | - | 31.9 min | 31.9 min |
| he_threshold_decrypt | - | 244 ms | 183 ms |
| gc_evaluate | - | 1.8 s | 0 ms |
| ot_receive | - | 131 ms | 131 ms |
| local_share_arith | - | 26.7 s | 26.7 s |
| network (flights 1814, transfer) | 90.5 min | 90.5 min | 90.5 min |
| **busy compute** | **3.9 min** | **32.3 min** | **32.3 min** |
| **end-to-end latency** | 2.1 h | | |
| wait (network / peer compute) | 90.5 min / 32.3 min | 90.5 min / 3.9 min | 90.5 min / 4.0 min |


### gist_N1000000_m4_E64

**Preprocessing (one-time, server, measured, 448 cores)**: HNSW build 50.9 s, graph import 5.1 s, flatten + LSH + cuckoo tables 74.7 s; total 2.3 min.

**Preprocessing (one-time, each client, modelled)**: HE threshold keygen 28 ms, 4.72 MB.

| per-query offline component (modelled) | server | each client | note |
|---|---|---|---|
| GC garbling | 262 ms | - | tables 16.99 GB to P1 |
| OT extension (input labels) | 66 ms | 131 ms | 560.35 MB/client |
| Beaver triples (2,047,680) | 59 ms | 526 ms | 591.28 MB/client |
| (r,s,h) read correlations | 2.3 h | 2.7 min | 143.34 GB/client |
| **total** | **2.3 h** | **2.7 min** | 144.49 GB/client |

| online component | server | P1 | other clients |
|---|---|---|---|
| read1d_matmul | 116.5 s | - | - |
| he_server | 3.1 min | - | - |
| ot_send | 66 ms | - | - |
| he_encrypt | - | 31.8 min | 31.8 min |
| he_threshold_decrypt | - | 244 ms | 183 ms |
| gc_evaluate | - | 1.8 s | 0 ms |
| ot_receive | - | 131 ms | 131 ms |
| local_share_arith | - | 25.3 s | 25.3 s |
| network (flights 1814, transfer) | 90.4 min | 90.4 min | 90.4 min |
| **busy compute** | **5.1 min** | **32.3 min** | **32.2 min** |
| **end-to-end latency** | 2.1 h | | |
| wait (network / peer compute) | 90.4 min / 32.3 min | 90.4 min / 5.1 min | 90.4 min / 5.1 min |


## HE row selector: packed


### sift_N100000_m4_E64

**Preprocessing (one-time, server, measured, 448 cores)**: HNSW build 1.0 s, graph import 166 ms, flatten + LSH + cuckoo tables 5.5 s; total 7.0 s.

**Preprocessing (one-time, each client, modelled)**: HE threshold keygen 28 ms, 4.72 MB.

| per-query offline component (modelled) | server | each client | note |
|---|---|---|---|
| GC garbling | 255 ms | - | tables 16.50 GB to P1 |
| OT extension (input labels) | 66 ms | 131 ms | 560.35 MB/client |
| Beaver triples (273,024) | 8 ms | 72 ms | 80.41 MB/client |
| (r,s,h) read correlations | 14.5 min | 17.7 s | 16.70 GB/client |
| **total** | **14.5 min** | **17.9 s** | 17.35 GB/client |

| online component | server | P1 | other clients |
|---|---|---|---|
| read1d_matmul | 2.1 s | - | - |
| he_server | 23.3 s | - | - |
| ot_send | 66 ms | - | - |
| he_encrypt | - | 372 ms | 715 ms |
| he_threshold_decrypt | - | 244 ms | 183 ms |
| gc_evaluate | - | 1.8 s | 0 ms |
| ot_receive | - | 131 ms | 131 ms |
| local_share_arith | - | 3.3 s | 3.3 s |
| network (flights 1814, transfer) | 9.2 s | 9.2 s | 9.2 s |
| **busy compute** | **25.5 s** | **5.8 s** | **4.3 s** |
| **end-to-end latency** | 40.5 s | | |
| wait (network / peer compute) | 9.2 s / 5.8 s | 9.2 s / 25.5 s | 9.2 s / 27.0 s |


### gist_N100000_m4_E64

**Preprocessing (one-time, server, measured, 448 cores)**: HNSW build 1.8 s, graph import 499 ms, flatten + LSH + cuckoo tables 10.0 s; total 12.5 s.

**Preprocessing (one-time, each client, modelled)**: HE threshold keygen 28 ms, 4.72 MB.

| per-query offline component (modelled) | server | each client | note |
|---|---|---|---|
| GC garbling | 256 ms | - | tables 16.54 GB to P1 |
| OT extension (input labels) | 66 ms | 131 ms | 560.35 MB/client |
| Beaver triples (2,047,680) | 59 ms | 526 ms | 591.28 MB/client |
| (r,s,h) read correlations | 106.7 min | 17.7 s | 16.70 GB/client |
| **total** | **106.7 min** | **18.3 s** | 17.86 GB/client |

| online component | server | P1 | other clients |
|---|---|---|---|
| read1d_matmul | 4.8 s | - | - |
| he_server | 23.3 s | - | - |
| ot_send | 66 ms | - | - |
| he_encrypt | - | 372 ms | 715 ms |
| he_threshold_decrypt | - | 244 ms | 183 ms |
| gc_evaluate | - | 1.8 s | 0 ms |
| ot_receive | - | 131 ms | 131 ms |
| local_share_arith | - | 3.3 s | 3.3 s |
| network (flights 1814, transfer) | 9.2 s | 9.2 s | 9.2 s |
| **busy compute** | **28.2 s** | **5.8 s** | **4.3 s** |
| **end-to-end latency** | 43.2 s | | |
| wait (network / peer compute) | 9.2 s / 5.8 s | 9.2 s / 28.2 s | 9.2 s / 29.7 s |


### sift_N1000000_m4_E64

**Preprocessing (one-time, server, measured, 448 cores)**: HNSW build 7.6 s, graph import 1.6 s, flatten + LSH + cuckoo tables 29.9 s; total 44.1 s.

**Preprocessing (one-time, each client, modelled)**: HE threshold keygen 28 ms, 4.72 MB.

| per-query offline component (modelled) | server | each client | note |
|---|---|---|---|
| GC garbling | 262 ms | - | tables 16.94 GB to P1 |
| OT extension (input labels) | 66 ms | 131 ms | 560.35 MB/client |
| Beaver triples (273,024) | 8 ms | 72 ms | 80.41 MB/client |
| (r,s,h) read correlations | 19.2 min | 2.7 min | 143.34 GB/client |
| **total** | **19.2 min** | **2.7 min** | 143.98 GB/client |

| online component | server | P1 | other clients |
|---|---|---|---|
| read1d_matmul | 47.1 s | - | - |
| he_server | 3.3 min | - | - |
| ot_send | 66 ms | - | - |
| he_encrypt | - | 579 ms | 922 ms |
| he_threshold_decrypt | - | 244 ms | 183 ms |
| gc_evaluate | - | 1.8 s | 0 ms |
| ot_receive | - | 131 ms | 131 ms |
| local_share_arith | - | 26.7 s | 26.7 s |
| network (flights 1814, transfer) | 35.1 s | 35.1 s | 35.1 s |
| **busy compute** | **4.1 min** | **29.5 s** | **27.9 s** |
| **end-to-end latency** | 5.1 min | | |
| wait (network / peer compute) | 35.1 s / 29.5 s | 35.1 s / 4.1 min | 35.1 s / 4.1 min |


### gist_N1000000_m4_E64

**Preprocessing (one-time, server, measured, 448 cores)**: HNSW build 50.9 s, graph import 5.1 s, flatten + LSH + cuckoo tables 74.7 s; total 2.3 min.

**Preprocessing (one-time, each client, modelled)**: HE threshold keygen 28 ms, 4.72 MB.

| per-query offline component (modelled) | server | each client | note |
|---|---|---|---|
| GC garbling | 262 ms | - | tables 16.99 GB to P1 |
| OT extension (input labels) | 66 ms | 131 ms | 560.35 MB/client |
| Beaver triples (2,047,680) | 59 ms | 526 ms | 591.28 MB/client |
| (r,s,h) read correlations | 2.3 h | 2.7 min | 143.34 GB/client |
| **total** | **2.3 h** | **2.7 min** | 144.49 GB/client |

| online component | server | P1 | other clients |
|---|---|---|---|
| read1d_matmul | 116.5 s | - | - |
| he_server | 3.3 min | - | - |
| ot_send | 66 ms | - | - |
| he_encrypt | - | 579 ms | 922 ms |
| he_threshold_decrypt | - | 244 ms | 183 ms |
| gc_evaluate | - | 1.8 s | 0 ms |
| ot_receive | - | 131 ms | 131 ms |
| local_share_arith | - | 25.3 s | 25.3 s |
| network (flights 1814, transfer) | 35.1 s | 35.1 s | 35.1 s |
| **busy compute** | **5.2 min** | **28.1 s** | **26.5 s** |
| **end-to-end latency** | 6.3 min | | |
| wait (network / peer compute) | 35.1 s / 28.1 s | 35.1 s / 5.2 min | 35.1 s / 5.2 min |
