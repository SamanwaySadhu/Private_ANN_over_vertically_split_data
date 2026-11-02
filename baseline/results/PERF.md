# Baseline performance, SIFT (per query; server 64 cores, each client 8 cores)

| run | recall@10 | network | online latency | server compute | P1 compute | online comm / client | online comm / server | rounds (RTT) | HE reads |
|---|---|---|---|---|---|---|---|---|---|
| base_sift_N100000_m2_E64 | 0.956 | LAN 10 Gbps / 0.1 ms | 11.9 min | 113.9 s | 3.7 min | 348.83 GB | 474.14 GB | 1394 | 292 |
|  | 0.956 | WAN 1 Gbps / 10 ms | 69.1 min | 113.9 s | 3.7 min | 348.83 GB | 474.14 GB | 1394 | 292 |
|  | 0.956 | WAN 100 Mbps / 80 ms | 10.7 h | 113.9 s | 3.7 min | 348.83 GB | 474.14 GB | 1394 | 292 |
| base_sift_N100000_m4_E32 | 0.884 | LAN 10 Gbps / 0.1 ms | 10.5 min | 62.7 s | 3.1 min | 287.31 GB | 478.89 GB | 786 | 164 |
|  | 0.884 | WAN 1 Gbps / 10 ms | 68.1 min | 62.7 s | 3.1 min | 287.31 GB | 478.89 GB | 786 | 164 |
|  | 0.884 | WAN 100 Mbps / 80 ms | 10.7 h | 62.7 s | 3.1 min | 287.31 GB | 478.89 GB | 786 | 164 |
| base_sift_N100000_m4_E64 | 0.959 | LAN 10 Gbps / 0.1 ms | 20.8 min | 2.0 min | 6.1 min | 569.87 GB | 949.51 GB | 1394 | 292 |
|  | 0.959 | WAN 1 Gbps / 10 ms | 2.2 h | 2.0 min | 6.1 min | 569.87 GB | 949.51 GB | 1394 | 292 |
|  | 0.959 | WAN 100 Mbps / 80 ms | 21.3 h | 2.0 min | 6.1 min | 569.87 GB | 949.51 GB | 1394 | 292 |
| base_sift_N100000_m4_E128 | 0.986 | LAN 10 Gbps / 0.1 ms | 41.4 min | 3.9 min | 12.2 min | 1.14 TB | 1.90 TB | 2610 | 548 |
|  | 0.986 | WAN 1 Gbps / 10 ms | 4.5 h | 3.9 min | 12.2 min | 1.14 TB | 1.90 TB | 2610 | 548 |
|  | 0.986 | WAN 100 Mbps / 80 ms | 42.5 h | 3.9 min | 12.2 min | 1.14 TB | 1.90 TB | 2610 | 548 |
| base_sift_N100000_m8_E64 | 0.958 | LAN 10 Gbps / 0.1 ms | 38.4 min | 2.2 min | 10.9 min | 1.01 TB | 1.90 TB | 1394 | 292 |
|  | 0.958 | WAN 1 Gbps / 10 ms | 4.4 h | 2.2 min | 10.9 min | 1.01 TB | 1.90 TB | 1394 | 292 |
|  | 0.958 | WAN 100 Mbps / 80 ms | 42.5 h | 2.2 min | 10.9 min | 1.01 TB | 1.90 TB | 1394 | 292 |
| base_sift_N1000000_m2_E32 | 0.768 | LAN 10 Gbps / 0.1 ms | 54.4 min | 3.9 min | 18.9 min | 1.75 TB | 2.38 TB | 842 | 176 |
|  | 0.768 | WAN 1 Gbps / 10 ms | 5.7 h | 3.9 min | 18.9 min | 1.75 TB | 2.38 TB | 842 | 176 |
|  | 0.768 | WAN 100 Mbps / 80 ms | 53.2 h | 3.9 min | 18.9 min | 1.75 TB | 2.38 TB | 842 | 176 |
| base_sift_N1000000_m2_E64 | 0.874 | LAN 10 Gbps / 0.1 ms | 107.2 min | 7.5 min | 37.2 min | 3.45 TB | 4.69 TB | 1450 | 304 |
|  | 0.874 | WAN 1 Gbps / 10 ms | 11.2 h | 7.5 min | 37.2 min | 3.45 TB | 4.69 TB | 1450 | 304 |
|  | 0.874 | WAN 100 Mbps / 80 ms | 104.9 h | 7.5 min | 37.2 min | 3.45 TB | 4.69 TB | 1450 | 304 |
| base_sift_N1000000_m2_E128 | 0.945 | LAN 10 Gbps / 0.1 ms | 3.5 h | 14.9 min | 74.0 min | 6.85 TB | 9.31 TB | 2666 | 560 |
|  | 0.945 | WAN 1 Gbps / 10 ms | 22.2 h | 14.9 min | 74.0 min | 6.85 TB | 9.31 TB | 2666 | 560 |
|  | 0.945 | WAN 100 Mbps / 80 ms | 208.5 h | 14.9 min | 74.0 min | 6.85 TB | 9.31 TB | 2666 | 560 |
| base_sift_N1000000_m4_E32 | 0.767 | LAN 10 Gbps / 0.1 ms | 98.7 min | 4.4 min | 30.9 min | 2.87 TB | 4.75 TB | 842 | 176 |
|  | 0.767 | WAN 1 Gbps / 10 ms | 11.2 h | 4.4 min | 30.9 min | 2.87 TB | 4.75 TB | 842 | 176 |
|  | 0.767 | WAN 100 Mbps / 80 ms | 106.2 h | 4.4 min | 30.9 min | 2.87 TB | 4.75 TB | 842 | 176 |
| base_sift_N1000000_m4_E64 | 0.873 | LAN 10 Gbps / 0.1 ms | 3.2 h | 8.6 min | 61.1 min | 5.66 TB | 9.38 TB | 1450 | 304 |
|  | 0.873 | WAN 1 Gbps / 10 ms | 22.0 h | 8.6 min | 61.1 min | 5.66 TB | 9.38 TB | 1450 | 304 |
|  | 0.873 | WAN 100 Mbps / 80 ms | 209.5 h | 8.6 min | 61.1 min | 5.66 TB | 9.38 TB | 1450 | 304 |
| base_sift_N1000000_m4_E128 | 0.942 | LAN 10 Gbps / 0.1 ms | 6.4 h | 17.0 min | 2.0 h | 11.24 TB | 18.63 TB | 2666 | 560 |
|  | 0.942 | WAN 1 Gbps / 10 ms | 43.7 h | 17.0 min | 2.0 h | 11.24 TB | 18.63 TB | 2666 | 560 |
|  | 0.942 | WAN 100 Mbps / 80 ms | 416.3 h | 17.0 min | 2.0 h | 11.24 TB | 18.63 TB | 2666 | 560 |

## Offline (per query, network-independent) and one-time

| run | GC ANDs | GC tables to P1 | garbling (server) | OT (server / client) | OT bytes / client | server build (one-time) | HE keygen / client |
|---|---|---|---|---|---|---|---|
| base_sift_N100000_m2_E64 | 5.15e+10 | 1.65 TB | 25.5 s | 6.4 s / 25.7 s | 109.63 GB | 1.9 s | 26 ms |
| base_sift_N100000_m4_E32 | 4.67e+10 | 1.49 TB | 23.1 s | 6.5 s / 12.9 s | 55.25 GB | 1.7 s | 28 ms |
| base_sift_N100000_m4_E64 | 9.26e+10 | 2.96 TB | 45.8 s | 12.8 s / 25.7 s | 109.63 GB | 2.0 s | 28 ms |
| base_sift_N100000_m4_E128 | 1.85e+11 | 5.93 TB | 91.6 s | 25.7 s / 51.4 s | 219.22 GB | 1.8 s | 28 ms |
| base_sift_N100000_m8_E64 | 1.75e+11 | 5.60 TB | 86.4 s | 25.7 s / 25.7 s | 109.63 GB | 1.6 s | 31 ms |
| base_sift_N1000000_m2_E32 | 2.64e+11 | 8.45 TB | 2.2 min | 32.5 s / 2.2 min | 555.07 GB | 21.7 s | 26 ms |
| base_sift_N1000000_m2_E64 | 5.21e+11 | 16.67 TB | 4.3 min | 64.2 s / 4.3 min | 1.10 TB | 25.1 s | 26 ms |
| base_sift_N1000000_m2_E128 | 1.04e+12 | 33.14 TB | 8.5 min | 2.1 min / 8.5 min | 2.18 TB | 18.5 s | 26 ms |
| base_sift_N1000000_m4_E32 | 4.72e+11 | 15.11 TB | 3.9 min | 65.0 s / 2.2 min | 555.06 GB | 25.1 s | 28 ms |
| base_sift_N1000000_m4_E64 | 9.32e+11 | 29.82 TB | 7.7 min | 2.1 min / 4.3 min | 1.10 TB | 24.0 s | 28 ms |
| base_sift_N1000000_m4_E128 | 1.85e+12 | 59.25 TB | 15.3 min | 4.3 min / 8.5 min | 2.18 TB | 26.6 s | 28 ms |