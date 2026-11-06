# hnsecw_sift_N1000000_m8_E32: HNSecW-style baseline (rtt 0.1 ms, 10000 Mbps; server 64 cores, clients 8; n = 9 parties)

Layers [1000000, 124481, 15825, 1951, 266, 25, 4, 1], steps per layer [62, 8, 8, 8, 8, 8, 8, 8]. Secret-shared tables: 1.19 GB per party (raw vectors 512.00 MB).

## Offline, per query (modelled)

| component | time | bytes |
|---|---|---|
| GC garbling (51,231,706 ANDs), server | 25 ms | tables to C1: 1.64 GB |
| OT correlations | server 4 ms, client 4 ms | 18.16 MB / client |
| Beaver triples (HE, 185,344) | server 6 ms, client 48 ms | 54.40 MB / party |
| **joint table reshuffle (lower bound)** | 12.9 min | 1.08 TB / party, 4.86 TB total |
| **offline latency total** | **12.9 min** | **1.08 TB / client** |

| circuit | calls | ANDs | wrapper share |
|---|---|---|---|
| visit:Lup | 56 | 1,267,424 | 88% |
| update:Lup | 56 | 3,916,696 | 87% |
| visit:L0 | 62 | 12,338,992 | 20% |
| update:L0 | 62 | 33,708,594 | 69% |

## Online, per query

| category | server | each client (max) |
|---|---|---|
| beaver | 23.72 MB | 23.72 MB |
| gc_labels | 11.16 MB | 138.28 MB |
| gc_ot | 291.69 MB | 36.46 MB |
| gc_out | 62.18 KB | 497.41 KB |
| open_cand | 7.55 KB | 7.55 KB |
| open_ep | 448 B | 448 B |
| open_out | 640 B | 640 B |
| output | 41.28 KB | 77.40 KB |
| share_query | 544 B | 1.02 KB |
| **total** | **326.69 MB** | **199.05 MB** |

1198 flights = 599 round trips. Compute: server 4 ms, client 1 (evaluator) 183 ms. Communication 321 ms (rounds 60 ms, transfer 261 ms).

**Online latency: 508 ms.**

## Accuracy

recall@10 vs float ground truth 0.8641 (hnswlib 0.7704); 65.0% of queries >= 0.9; secure == plain emulation on 8/8 sampled queries.
