# Tiptoe baseline for private ANN over vertically split queries

A fifth protocol to compare against, built from *Private Web Search with Tiptoe* (Henzinger, Dauterman, Corrigan-Gibbs, Zeldovich,
SOSP'23; reference implementation <https://github.com/ahenzinger/tiptoe>, crypto in <https://github.com/ahenzinger/underhood>) and
adapted to this repo's setting: the query is vertically split over `m` clients, **no client learns the query, the chosen cluster, the
cluster's scores or any other intermediate value; the only thing the clients learn is the final top-k ids.** The server holds the
corpus. Nothing outside this folder is modified; it imports the shared code (`datasets`, `gc_model.bits`, `costmodel.Cfg/load_cal`,
`../calib`).

Same convention as `baseline/`, `hnsecw/`, `panther/`: an instrumented simulation (additive shares executed, GC and LWE/RLWE as
metered ideal functionalities) plus a cost model calibrated from native micro-benchmarks. It is **not** a port of the Go code of the
paper (that code serves one client, in the clear, with the scores returned to it); the protocol is re-implemented at the level of
its data flow, message sizes and operation counts, and the multi-client split is new (the paper has no such protocol).

## Tiptoe in one paragraph
Embeddings -> k-means into `C ~ sqrt(N)` clusters whose centroids are **public** (clients download them), 20% of the vectors stored
in two clusters, clusters padded to `mc` rows. The ranking matrix `M` (`mc` rows x `d*C` columns, column block `c` = cluster `c`) is
scanned in full for every query, which is what hides the cluster. The client encrypts `q~ = (0,..,q,..,0)` (q in block `i*`, the
cluster nearest to q by its centroid) under SimplePIR-style LWE (q = 2^64, p = 2^17, n = 2048); the server returns `M*Enc(q~)`
(2 N d 64-bit operations, hint `H = M*A` preprocessed once). The client would decrypt, which needs `H*s`; to avoid downloading the
GB-sized `H`, it sends a second-layer RLWE encryption of `s` ("query token", prepared before the query) and the server hands back
`H*s` under it. The client sorts the `~sqrt(N)` scores it now holds and fetches URLs by PIR.

## Adaptation to `m` clients (the design decisions, please check them)

| step | Tiptoe paper (1 client) | here (server + `m` clients) |
|---|---|---|
| cluster choice | client compares q with the downloaded centroids | centroids stay public (as in the paper), so client `i` computes its **partial** distance `\|\|q_i - c_i\|\|^2` to all `C` centroids locally; these are additive shares of the true distances. **GC `argmin_cluster`** -> shared one-hot `e` (not revealed) |
| `q~ = (0,..,q,..,0)` | client builds it | `q~ = e (x) q` by a **Beaver outer product** in the ring `Z_{2^17}`: only `C + d` values are opened online, the `C*d` triple is offline. Result: additive shares `q~^(i)` |
| encryption | `b = A s + e + D q~` | client `i` encrypts its share under its own **additive key share** `s_i`: `b_i = A s_i + e_i + D q~^(i)` (`D = 2^(64-17)`). `sum_i b_i` is a valid LWE ciphertext of `q~` under `s = sum_i s_i`, so the server does **one** scan of `M`. `A s_i` is query independent (offline) |
| decryption | client: `round((c - H s)/D)` | `c` never leaves the server. Query token per client: server returns `H s_i` under client `i`'s RLWE key. **GC `rank_topk`** takes `c` (garbler) and `-H s_i` (client `i`, by OT), adds them mod 2^64 and rounds: nobody sees a score. This is the only place where the plaintext inner products exist |
| ranking | client sorts the scores | the same GC runs the top-k selection network (Shanbhag et al. bitonic top-k, comparator counts exact for arbitrary `n,k`) |
| L2 instead of inner product | cosine / inner product | `score = \|\|x\|\|^2 - 2<x,q>` on the quantised vectors; the row norms are one more row of the id matrix (linear in `e`), padding rows get `2^16-1` so they never win |
| result | client gets doc ids, then URLs by a PIR step | The "URL service" is replaced by a **linear lookup** `M_id e` with the same LWE machinery (ids split in 12-bit limbs, `e` encrypted shares): the id of every row of the secret cluster is retrieved as shares and enters the GC. Revealing `(cluster, row)` to the clients (as the paper does before its PIR) would leak the chosen cluster; this does not. The k ids are opened to client 1 and forwarded |
| server memory access | independent of the query | identical: full scan of `M` and `M_id`, no query-dependent access |

Security statement of the adaptation (semi-honest, as in the paper and the other baselines): the server sees only ciphertexts
(`b_i`, RLWE tokens) and garbles; it learns nothing. A coalition of `m-1` clients plus the server learns nothing about the remaining
client's block beyond the output (additive shares of `q~`, `e`, key shares). **Caveat**: if *all* clients collude without the server
they hold `s = sum s_i` and the tokens, hence `H s` (database-dependent) and, with the server's `c`, could decrypt the cluster's
scores. The paper's single client trivially gets those scores, so this is not weaker than Tiptoe itself. Another inherited property:
centroids are public by design (the paper's setting is a public corpus); clients therefore learn the `C` centroids, which the
`panther/` and main protocols do not reveal.

## What is measured vs modelled
**Executed**: the whole protocol over real additive shares for the sampled queries: local partial distances, ring sharing among the
clients, the Beaver outer product (checked to reconstruct `e (x) q`), the share-to-ciphertext conversion `T = D * (M q~, M_id e)` into
`Z_{2^64}` shares `(c, u_1..u_m)`, the decryption `round(sum / D)` + sign lift, the id-limb recombination and the top-k. GC and the
LWE scan are ideal functionalities on reconstructed values. Checked equal to the plain emulation `tproto.plain_search`; recall on all
queries uses the plain emulation. `tlwe_check.py` runs the **real LWE arithmetic at toy size** (multi-key additive-share
encryption, `c = M b`, hint `H = M A`, share decryption in `Z_{2^64}` with the paper's discrete-Gaussian noise `sigma = 81920`,
dropped low-order hint bits, base-16 digit decomposition used by the token step) and confirms exact agreement with `M q~`.
**Counted exactly**: bytes per party and category, flights, AND counts, triple count, matrix shapes.
**Measured natively** (`calib/scan_bench.cpp` -> `calib/scan_calib.json`, 12-thread WSL VM): the server scan `M b mod 2^64`
(int8 and int16 matrices) and the client's `A s_i`.
**Modelled**: GC garble/evaluate and OT (`../calib`), RLWE op times (OpenFHE calibration scaled to the paper's `N=2048`, 38-bit
parameters by `N log q`), Beaver triples (threshold-HE batched generation, as in `hnsecw/`), network.

## Cost-model choices to know about
- **Scan time scales linearly in the server's cores** from the measured single-thread rate (2.7 GB/s of `M`). The measuring VM
  saturates memory bandwidth at ~2 threads (5 GB/s), so 64 cores at 170 GB/s is optimistic unless the server has many memory channels.
  Scan time is tiny either way compared with communication and GC at these sizes.
- **Tokens are per client per query**: each client has its own LWE key share, so the server runs the token computation `m` times
  (one RLWE token each) and each client uploads `2048` RLWE ciphertexts (~40 MB) and downloads `16*ceil(l/n)` ciphertexts per matrix.
  Sanity check against the paper's Table 7 (360M docs, ranking+URL): our formulas give ~38 MiB up (paper 32.4 MiB: the paper
  seed-compresses some ciphertexts) and `16*25*19.5 KB = 7.8 MB` down for ranking only (paper 9.8 MiB incl. URL tokens).
- Ring wrapper: values live in `Z_{2^l}` where a modular addition is `l` ANDs (the repo's `F_p` wrapper pays `3l`), shared inputs use the
  natural ring width (`l = 24` for distances, `17` for the selector, `64` for the LWE decryption). Hence Tiptoe's GC counts are not
  directly comparable with the other protocols' `l = 31` field convention; in practice the 64-bit decryption adds dominate.
- Not charged (all favour Tiptoe): RLWE key generation, noise flooding on the token, the per-corpus pre-NTT of `H`'s digits, LWE noise
  in the engine (validated separately in `tlwe_check.py`), the query's PCA step (SIFT d = 128 is not reduced).
- Latency = server compute + client-1 compute + RTT/2 per flight + max-party bytes/BW, no overlap. Tokens, triples and GC tables are
  offline (reported separately, as in the paper's 74%-before-the-query accounting).
- Offline column here also counts the `m` tokens' server work, the biggest term at scale; one-time costs (hint `H = M A`, centroid
  download) are reported separately in the breakdown.

## Recall
Tiptoe searches **one cluster, with no probe knob**: recall is bounded by the fraction of queries whose nearest *centroid* contains the
true neighbours (35% of MS MARCO queries in the paper) and by the 4-bit quantisation. `--bits` (the paper uses 4; the `Z_{2^p}`
parameter table limits it, `tserver.p_max_table12`), `--C`, `--dup`, `--cap` are the only knobs. On the synthetic Gaussian-blob data
(no SIFT files on this machine, see below) recall@10 with 300 clusters at d=128: 0.18 (4 bit), 0.26 (5 bit); the upper bound
(unquantised, same cluster) is 0.27. Do not read these as SIFT numbers.

## Files
- `tserver.py` server build (quantisation, k-means, boundary duplication, `M`, `M_id`, parameter checks against the paper's tables)
- `tproto.py` plaintext reference (`plain_search`), the oracle for the secure run
- `tgc.py` AND counts of `argmin_cluster` and `rank_topk`
- `tengine.py` instrumented secure execution (ring shares, Beaver outer product, LWE share conversion, GCs, metering)
- `tcost.py` cost model; `calib/scan_bench.cpp`, `calib/scan_calib.json` native scan / `A s` calibration
- `tbench.py` driver, `breakdown.py` per-party report, `compare.py` Tiptoe next to main / baseline / HNSecW / Panther rows if
  their result files exist, `tlwe_check.py` real toy-size LWE check, `run.sh` reproduces everything
- `results/` raw JSON, logs, `BREAKDOWN_*.md`, `COMPARE.md`

## Running
    wsl -d Ubuntu-24.04 -- bash -c "cd /mnt/c/Private_ANN_over_vertically_split_data/tiptoe && source ~/venv/bin/activate && python tlwe_check.py && python tbench.py --dataset synth --N 300000 --d 128 --m 4 --nq 200 --nperf 4 && python breakdown.py results/tiptoe_synth_N300000_m4_b4.json && python compare.py"
`run.sh` does the SIFT100K / SIFT1M configurations of the other baselines; it needs `sift_base.fvecs` under `$ANN_DATA`
(default `~/ann_data`), which is not present on this machine, so only `--dataset synth` results are checked in.
