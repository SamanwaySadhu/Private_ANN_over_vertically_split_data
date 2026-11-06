# Panther baseline vs the other protocols (per query)

Panther: clustering ANNS, shuffled coefficient-encoded database, cuckoo batch PIR, PIR-to-shares, GC top-k selection networks, adapted to a vertically split query (see README). Offline column of Panther = GC garbling + OT + GC table transfer; there is no per-query reshuffle and no Beaver triple. Other protocols' offline column is as defined in their own cost models.

| config | net | protocol | recall@10 | online latency | online comm / client | online comm / server | rounds (RTT) | offline latency | offline comm / client |
|---|---|---|---|---|---|---|---|---|---|
| synth N=300,000 m=4 | LAN | **Panther (u=10, t=548)** | 0.798 | 521 ms | 182.92 MB | 192.19 MB | 11 | 416 ms | 12.58 MB |
| synth N=300,000 m=4 | WAN | **Panther (u=10, t=548)** | 0.798 | 16.6 s | 182.92 MB | 192.19 MB | 11 | 40.5 s | 12.58 MB |