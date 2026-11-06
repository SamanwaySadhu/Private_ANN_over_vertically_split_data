# tiptoe_synth_N300000_m4_b4: Tiptoe baseline, vertically split query (rtt 0.1 ms, 10000 Mbps; server 64 cores, clients 8; server + 4 clients)

C=548 clusters (sizes 39..986, mean 650, padded to mc=986 rows; 356,046 stored vectors incl. 20% duplicated at cluster boundaries), 4-bit embeddings, plaintext ring 2^17. Ranking matrix 986 x 70,144 (int8, 69.16 MB), id/norm matrix 2958 x 548.

## One-time

- clients download the 548 public centroids: 70.14 KB
- server hint H = M*A: 1.45e+11 64-bit MACs = 3.3 s on 64 cores, hint size 64.62 MB (server-side only)

## Offline, per query (query independent; the paper's 'query token' phase included)

| component | time | bytes |
|---|---|---|
| RLWE tokens: server (4 clients x 48 ct x 2048 cols) | 72 ms | |
| RLWE tokens: client (encrypt 2048 z-cts, decrypt) | 48 ms | 40.31 MB / client (transfer 129 ms) |
| client LWE mask A*s_i (query independent) | 27 ms | |
| Beaver outer-product triple (70,144 elements) | server 2 ms, client 19 ms | 21.29 MB / client |
| GC garbling (1,449,008 ANDs), server | 1 ms | tables to client 1: 46.37 MB |
| OT correlations for GC inputs | server 1 ms, client 1 ms | 4.40 MB / client |
| **offline latency** | **336 ms** | **66.00 MB / client** |

| circuit | calls | ANDs | wrapper share |
|---|---|---|---|
| argmin_cluster | 1 | 113,926 | 67% |
| rank_topk | 1 | 1,335,082 | 0% |

## Online, per query (after the query is entered)

| category | server | each client (max) |
|---|---|---|
| beaver_open | 0 B | 12.17 KB |
| gc_labels | 4.04 MB | 17.23 MB |
| gc_ot | 35.32 MB | 8.83 MB |
| gc_out | 40 B | 40 B |
| output | 0 B | 120 B |
| query_upload | 2.26 MB | 565.54 KB |
| **total** | **41.62 MB** | **26.64 MB** |

Compute (online): server scan_rank 0 ms, scan_id 0 ms, ot_send 1 ms; client 1 gc_evaluate 5 ms, ot_receive 1 ms, local_ring_ops 0 ms.

11 flights = 6 round trips. Communication 34 ms (rounds 1 ms, transfer 33 ms); compute server 1 ms, client 1 6 ms.

**Online latency: 41 ms.**

## Accuracy

recall@10 vs float ground truth 0.1340; 0.0% of queries >= 0.9; secure == plain emulation on 4/4 sampled queries.
