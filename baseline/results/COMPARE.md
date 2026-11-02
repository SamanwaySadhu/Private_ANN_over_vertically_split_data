# Baseline vs main protocol (per query)

Main = LSH upper layers + Lagrange one-hot + HE-generated correlations in preprocessing (`--mode mask` results of the parent directory). Baseline = exact greedy upper layers + GC one-hot + HE online. Same graph parameters (M=8, d=128, same k, E).

| config | net | protocol | recall@10 | online latency | online comm / client | online comm / server | rounds (RTT) | offline server | offline GC tables | offline comm / client |
|---|---|---|---|---|---|---|---|---|---|---|
| N=1,000,000 m=2 E=64 | LAN | main | 0.859 | 4.8 min | 11.73 GB | 21.71 GB | 889 | 19.2 min | 10.21 GB | 144.00 GB |
| N=1,000,000 m=2 E=64 | LAN | **baseline** | 0.874 | 107.2 min | 3.45 TB | 4.69 TB | 1450 | 5.4 min | 16.67 TB | 1.10 TB |
| N=1,000,000 m=2 E=64 | WAN | main | 0.859 | 34.7 min | 11.73 GB | 21.71 GB | 889 | 19.2 min | 10.21 GB | 144.00 GB |
| N=1,000,000 m=2 E=64 | WAN | **baseline** | 0.874 | 104.9 h | 3.45 TB | 4.69 TB | 1450 | 5.4 min | 16.67 TB | 1.10 TB |
| N=1,000,000 m=4 E=128 | LAN | main | 0.899 | 7.1 min | 29.93 GB | 91.90 GB | 1593 | 37.7 min | 67.80 GB | 288.07 GB |
| N=1,000,000 m=4 E=128 | LAN | **baseline** | 0.942 | 6.4 h | 11.24 TB | 18.63 TB | 2666 | 19.5 min | 59.25 TB | 2.18 TB |
| N=1,000,000 m=4 E=128 | WAN | main | 0.899 | 2.2 h | 29.93 GB | 91.90 GB | 1593 | 37.7 min | 67.80 GB | 288.07 GB |
| N=1,000,000 m=4 E=128 | WAN | **baseline** | 0.942 | 416.3 h | 11.24 TB | 18.63 TB | 2666 | 19.5 min | 59.25 TB | 2.18 TB |
| N=1,000,000 m=4 E=32 | LAN | main | 0.716 | 4.2 min | 6.41 GB | 22.96 GB | 537 | 9.9 min | 4.33 GB | 72.38 GB |
| N=1,000,000 m=4 E=32 | LAN | **baseline** | 0.767 | 98.7 min | 2.87 TB | 4.75 TB | 842 | 5.0 min | 15.11 TB | 555.06 GB |
| N=1,000,000 m=4 E=32 | WAN | main | 0.716 | 35.2 min | 6.41 GB | 22.96 GB | 537 | 9.9 min | 4.33 GB | 72.38 GB |
| N=1,000,000 m=4 E=32 | WAN | **baseline** | 0.767 | 106.2 h | 2.87 TB | 4.75 TB | 842 | 5.0 min | 15.11 TB | 555.06 GB |
| N=1,000,000 m=4 E=64 | LAN | main | 0.781 | 5.1 min | 12.86 GB | 43.72 GB | 889 | 19.2 min | 16.94 GB | 144.00 GB |
| N=1,000,000 m=4 E=64 | LAN | **baseline** | 0.873 | 3.2 h | 5.66 TB | 9.38 TB | 1450 | 9.8 min | 29.82 TB | 1.10 TB |
| N=1,000,000 m=4 E=64 | WAN | main | 0.781 | 64.0 min | 12.86 GB | 43.72 GB | 889 | 19.2 min | 16.94 GB | 144.00 GB |
| N=1,000,000 m=4 E=64 | WAN | **baseline** | 0.873 | 209.5 h | 5.66 TB | 9.38 TB | 1450 | 9.8 min | 29.82 TB | 1.10 TB |