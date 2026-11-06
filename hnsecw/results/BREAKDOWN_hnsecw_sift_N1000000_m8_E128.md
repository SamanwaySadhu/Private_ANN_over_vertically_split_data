# hnsecw_sift_N1000000_m8_E128: HNSecW-style baseline (rtt 0.1 ms, 10000 Mbps; server 64 cores, clients 8; n = 9 parties)

Layers [1000000, 124597, 15844, 1949, 267, 26, 4, 1], steps per layer [158, 8, 8, 8, 8, 8, 8, 8]. Secret-shared tables: 1.19 GB per party (raw vectors 512.00 MB).

## Offline, per query (modelled)

| component | time | bytes |
|---|---|---|
| GC garbling (339,256,002 ANDs), server | 168 ms | tables to C1: 10.86 GB |
| OT correlations | server 24 ms, client 24 ms | 102.25 MB / client |
| Beaver triples (HE, 381,952) | server 12 ms, client 99 ms | 111.16 MB / party |
| **joint table reshuffle (lower bound)** | 12.9 min | 1.08 TB / party, 4.87 TB total |
| **offline latency total** | **12.9 min** | **1.08 TB / client** |

| circuit | calls | ANDs | wrapper share |
|---|---|---|---|
| visit:Lup | 56 | 1,267,424 | 88% |
| update:Lup | 56 | 3,916,696 | 87% |
| visit:L0 | 158 | 70,274,608 | 9% |
| update:L0 | 158 | 263,797,274 | 61% |

## Online, per query

| category | server | each client (max) |
|---|---|---|
| beaver | 48.89 MB | 48.89 MB |
| gc_labels | 55.45 MB | 771.19 MB |
| gc_ot | 1.64 GB | 205.30 MB |
| gc_out | 389.34 KB | 3.11 MB |
| open_cand | 13.70 KB | 13.70 KB |
| open_ep | 448 B | 448 B |
| open_out | 640 B | 640 B |
| output | 41.28 KB | 77.40 KB |
| share_query | 544 B | 1.02 KB |
| **total** | **1.75 GB** | **1.03 GB** |

2158 flights = 1079 round trips. Compute: server 24 ms, client 1 (evaluator) 1.2 s. Communication 1.5 s (rounds 108 ms, transfer 1.4 s).

**Online latency: 2.7 s.**

## Accuracy

recall@10 vs float ground truth 0.9530 (hnswlib 0.9408); 88.5% of queries >= 0.9; secure == plain emulation on 8/8 sampled queries.
