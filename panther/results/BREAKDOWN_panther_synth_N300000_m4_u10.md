# panther_synth_N300000_m4_u10: Panther baseline, vertically split query (rtt 100.0 ms, 80 Mbps; server 64 cores, clients 8; n = 5 parties)

t=548 clusters (sizes 381..822, padded to mc=822), u=10 retrieved, B=15 PIR buckets (125 items/bucket, 27 plaintext polys/item, dims 12x11), k'=548 bins. 12,330 candidate points enter the exact top-k. Cuckoo failures per query: 0.00.

## Offline, per query (modelled)

| component | time | bytes |
|---|---|---|
| GC garbling (15,826,934 ANDs), server | 8 ms | tables to client 1: 506.46 MB |
| OT correlations for GC inputs | server 1 ms, client 3 ms | 12.50 MB / client |
| silent COTs for wrap-bit OTs (1,578,240) | server 2 ms, client 3 ms | 75.64 KB / client |
| per-query table reshuffle | free (index map) | 0 |
| **offline latency (garble + OT + table transfer)** | **50.7 s** | **12.58 MB / client** |

| circuit | calls | ANDs | wrapper share |
|---|---|---|---|
| approx_topk | 1 | 417,342 | 57% |
| exact_topk | 1 | 15,409,592 | 69% |

## Online, per query

| category | server | each client (max) |
|---|---|---|
| gc_labels | 12.50 MB | 50.01 MB |
| gc_ot | 100.42 MB | 25.10 MB |
| gc_out | 80 B | 80 B |
| he_centroid | 55.30 KB | 55.30 KB |
| he_points | 387.07 KB | 387.07 KB |
| output | 0 B | 120 B |
| pir_dec1 | 0 B | 29.86 MB |
| pir_dec2 | 0 B | 44.79 MB |
| pir_distribute | 0 B | 5.03 MB |
| pir_query | 3.16 MB | 3.16 MB |
| pir_resp | 67.19 MB | 22.40 MB |
| query_ct | 3.54 MB | 884.74 KB |
| share_norm | 16 B | 28 B |
| wrap_ot | 4.93 MB | 1.23 MB |
| **total** | **192.19 MB** | **182.92 MB** |

Compute (online): server he_distance 1 ms, pir_expand 7 ms, pir_dim1 162 ms, pir_dim2 19 ms, ot_send 1 ms; client 1 encrypt_query 1 ms, pir_query_encrypt 4 ms, threshold_decrypt_dist 0 ms, threshold_decrypt_pir 113 ms, gc_evaluate 55 ms, ot_receive 3 ms.

22 flights = 11 round trips. Communication 20.3 s (rounds 1.1 s, transfer 19.2 s); compute server 190 ms, client 1 176 ms.

**Online latency: 20.7 s.**

## Accuracy

recall@10 vs float ground truth 0.7980; 41.0% of queries >= 0.9; secure == plain emulation on 2/2 sampled queries.
