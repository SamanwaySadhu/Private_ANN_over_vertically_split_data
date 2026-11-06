# tiptoe_synth_N1000000_m4_b4: Tiptoe baseline, vertically split query (rtt 0.1 ms, 10000 Mbps; server 64 cores, clients 8; server + 4 clients)

C=1000 clusters (sizes 31..1800, mean 1166, padded to mc=1800 rows; 1,165,682 stored vectors incl. 20% duplicated at cluster boundaries), 4-bit embeddings, plaintext ring 2^17. Ranking matrix 1800 x 128,000 (int8, 230.40 MB), id/norm matrix 5400 x 1000.

## One-time

- clients download the 1000 public centroids: 128.00 KB
- server hint H = M*A: 4.83e+11 64-bit MACs = 11.1 s on 64 cores, hint size 117.96 MB (server-side only)

## Offline, per query (query independent; the paper's 'query token' phase included)

| component | time | bytes |
|---|---|---|
| RLWE tokens: server (4 clients x 64 ct x 2048 cols) | 96 ms | |
| RLWE tokens: client (encrypt 2048 z-cts, decrypt) | 49 ms | 40.47 MB / client (transfer 130 ms) |
| client LWE mask A*s_i (query independent) | 49 ms | |
| Beaver outer-product triple (128,000 elements) | server 4 ms, client 34 ms | 37.84 MB / client |
| GC garbling (2,656,702 ANDs), server | 1 ms | tables to client 1: 85.01 MB |
| OT correlations for GC inputs | server 1 ms, client 2 ms | 8.03 MB / client |
| **offline latency** | **431 ms** | **86.34 MB / client** |

| circuit | calls | ANDs | wrapper share |
|---|---|---|---|
| argmin_cluster | 1 | 207,942 | 67% |
| rank_topk | 1 | 2,448,760 | 0% |

## Online, per query (after the query is entered)

| category | server | each client (max) |
|---|---|---|
| beaver_open | 0 B | 20.30 KB |
| gc_labels | 7.37 MB | 31.46 MB |
| gc_ot | 64.48 MB | 16.12 MB |
| gc_out | 40 B | 40 B |
| output | 0 B | 120 B |
| query_upload | 4.13 MB | 1.03 MB |
| **total** | **75.98 MB** | **48.63 MB** |

Compute (online): server scan_rank 1 ms, scan_id 0 ms, ot_send 1 ms; client 1 gc_evaluate 9 ms, ot_receive 2 ms, local_ring_ops 0 ms.

11 flights = 6 round trips. Communication 61 ms (rounds 1 ms, transfer 61 ms); compute server 2 ms, client 1 11 ms.

**Online latency: 75 ms.**

## Accuracy

recall@10 vs float ground truth 0.1030; 0.0% of queries >= 0.9; secure == plain emulation on 4/4 sampled queries.
