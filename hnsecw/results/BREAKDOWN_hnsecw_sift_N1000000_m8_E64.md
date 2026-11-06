# hnsecw_sift_N1000000_m8_E64: HNSecW-style baseline (rtt 0.1 ms, 10000 Mbps; server 64 cores, clients 8; n = 9 parties)

Layers [1000000, 124477, 15844, 1950, 265, 26, 5, 1], steps per layer [94, 8, 8, 8, 8, 8, 8, 8]. Secret-shared tables: 1.19 GB per party (raw vectors 512.00 MB).

## Offline, per query (modelled)

| component | time | bytes |
|---|---|---|
| GC garbling (110,080,506 ANDs), server | 54 ms | tables to C1: 3.52 GB |
| OT correlations | server 9 ms, client 9 ms | 38.06 MB / client |
| Beaver triples (HE, 250,880) | server 8 ms, client 65 ms | 73.32 MB / party |
| **joint table reshuffle (lower bound)** | 12.9 min | 1.08 TB / party, 4.86 TB total |
| **offline latency total** | **12.9 min** | **1.08 TB / client** |

| circuit | calls | ANDs | wrapper share |
|---|---|---|---|
| visit:Lup | 56 | 1,267,424 | 88% |
| update:Lup | 56 | 3,916,696 | 87% |
| visit:L0 | 94 | 26,407,984 | 14% |
| update:L0 | 94 | 78,488,402 | 71% |

## Online, per query

| category | server | each client (max) |
|---|---|---|
| beaver | 32.11 MB | 32.11 MB |
| gc_labels | 21.86 MB | 288.30 MB |
| gc_ot | 611.39 MB | 76.42 MB |
| gc_out | 138.46 KB | 1.11 MB |
| open_cand | 9.60 KB | 9.60 KB |
| open_ep | 448 B | 448 B |
| open_out | 640 B | 640 B |
| output | 41.28 KB | 77.40 KB |
| share_query | 544 B | 1.02 KB |
| **total** | **665.55 MB** | **398.04 MB** |

1518 flights = 759 round trips. Compute: server 9 ms, client 1 (evaluator) 392 ms. Communication 608 ms (rounds 76 ms, transfer 532 ms).

**Online latency: 1.0 s.**

## Accuracy

recall@10 vs float ground truth 0.9170 (hnswlib 0.8728); 79.4% of queries >= 0.9; secure == plain emulation on 8/8 sampled queries.
