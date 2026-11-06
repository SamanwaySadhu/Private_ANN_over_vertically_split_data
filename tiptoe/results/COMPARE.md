# Tiptoe baseline vs the other protocols (per query)

Tiptoe: clustering ANNS, SimplePIR-style LWE linear scan over the whole matrix, query shares encrypted under additive key shares, GC decrypt + top-k, adapted to a vertically split query (see README). Offline column of Tiptoe = RLWE query tokens (one per client) + Beaver outer-product triple + GC garbling/OT/table transfer. Other protocols' offline column is as defined in their own cost models.

| config | net | protocol | recall@10 | online latency | online comm / client | online comm / server | rounds (RTT) | offline latency | offline comm / client |
|---|---|---|---|---|---|---|---|---|---|
| synth N=1,000,000 m=4 | LAN | **Tiptoe (b=4, C=1000)** | 0.103 | 75 ms | 48.63 MB | 75.98 MB | 6 | 431 ms | 86.34 MB |
| synth N=1,000,000 m=4 | WAN | **Tiptoe (b=4, C=1000)** | 0.103 | 6.5 s | 48.63 MB | 75.98 MB | 6 | 20.0 s | 86.34 MB |
| synth N=300,000 m=4 | LAN | Panther (u=10) | 0.798 | 521 ms | 182.92 MB | 192.19 MB | 11 | 416 ms | 12.58 MB |
| synth N=300,000 m=4 | LAN | **Tiptoe (b=4, C=548)** | 0.134 | 41 ms | 26.64 MB | 41.62 MB | 6 | 336 ms | 66.00 MB |
| synth N=300,000 m=4 | WAN | Panther (u=10) | 0.798 | 16.6 s | 182.92 MB | 192.19 MB | 11 | 40.5 s | 12.58 MB |
| synth N=300,000 m=4 | WAN | **Tiptoe (b=4, C=548)** | 0.134 | 3.8 s | 26.64 MB | 41.62 MB | 6 | 16.8 s | 66.00 MB |
| synth N=300,000 m=4 | LAN | Panther (u=10) | 0.798 | 521 ms | 182.92 MB | 192.19 MB | 11 | 416 ms | 12.58 MB |
| synth N=300,000 m=4 | LAN | **Tiptoe (b=5, C=300)** | 0.254 | 68 ms | 45.60 MB | 69.40 MB | 6 | 367 ms | 59.87 MB |
| synth N=300,000 m=4 | WAN | Panther (u=10) | 0.798 | 16.6 s | 182.92 MB | 192.19 MB | 11 | 40.5 s | 12.58 MB |
| synth N=300,000 m=4 | WAN | **Tiptoe (b=5, C=300)** | 0.254 | 6.0 s | 45.60 MB | 69.40 MB | 6 | 19.5 s | 59.87 MB |