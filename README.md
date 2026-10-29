# Private HNSW over vertically split queries

Implementation of `Vertically_split_ANN.pdf`. Run everything in WSL (Ubuntu-24.04, `~/venv` has numpy, hnswlib, openfhe):

    wsl -d Ubuntu-24.04 -- bash -c "cd /mnt/c/Private_ANN_over_vertically_split_data && source ~/venv/bin/activate && python run_eval.py --N 2000 --d 32 --queries 100 --Tb 64"
    # real threshold HE for every 2-D read (slow, use small instances):
    python run_eval.py --N 150 --d 16 --m 3 --queries 3 --Tg 5 --Tb 20 --E 16 --he openfhe

Files: `vsann.py` (protocol), `real_he.py` (OpenFHE threshold-BFV backend), `run_eval.py` (accuracy / LSH failure).

## Primitive status

| Primitive | Status | Library |
|---|---|---|
| Plain HNSW reference | real | hnswlib (agrees with own HNSW: recall 1.0) |
| 2-D read (Sec. 5.3) threshold HE | **real, `--he openfhe`** | OpenFHE BFV, m-of-m threshold keygen, threshold decrypt to P1 |
| Additive sharing, Beaver mult, Lagrange one-hot, masked 1-D read | own code, dealer triples | none (numpy) |
| Offline correlations (triples, alpha powers, (r,s,h)) | simulated dealer | - |
| MYao garbled circuits | simulated (ideal functionality) | - |

Field p = 2147352577 (= 1 mod 2^16) so it is also the BFV batching modulus.
No circuit privacy / noise flooding for the HE output is claimed beyond OpenFHE's multiparty mode.
