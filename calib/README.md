# Calibration microbenchmarks

Build: `./build.sh` (g++ 11.5, -O3 -march=native). Run: `./run_he.sh` (writes he_calib.json; REPS=20 default) and `./gc_bench > gc_calib.json`.

Exact compile commands are inside build.sh.
- gc_bench: `g++ -std=c++17 -O3 -march=native -maes -mrdseed -mpclmul -DTHREADING -I~/emp-legacy/include gc_bench.cpp ~/emp-legacy/include/emp-tool/emp-tool.cpp -lcrypto`
- he_bench: `g++ -std=c++17 -O3 -march=native -fopenmp -I/usr/local/include/openfhe{,/core,/pke,/binfhe,/cereal} he_bench.cpp -L/usr/local/lib -lOPENFHEpke -lOPENFHEcore -lOPENFHEbinfhe --start-group libsnark.a libff.a --end-group -lgmp -lgmpxx -lpbc -lcrypto`

## Versions
- OpenFHE 1.0.4 headers/libs in /usr/local (this install is the zkOpenFHE-modified build: libs need libff/libsnark/gmp/pbc to link). Plain `find_package(OpenFHE)` was not used; direct g++ line instead.
- emp: the *legacy* emp-tool/emp-ot in ~/emp-legacy (header-only half-gates, IKNP, Ferret). The new C++20 emp in ~/emp (and its SoftSpoken OT) was not used, so SoftSpoken is NOT measured.
- OpenSSL libcrypto (system), AES-NI enabled.

## Caveats
- HE: BatchSize 1024/4096/8192 all give ring_dim 8192 (4 RNG towers, log2 q = 240) with these params, so sizes/times are identical across batch sizes (differences are noise). Pack time is for MakePackedPlaintext of batch-size values.
- HE: the main table runs under OMP_NUM_THREADS=1 (omp_max_threads recorded in the JSON). Thread scaling (m=8 only) is separate processes with OMP_NUM_THREADS=1/8/64; keygen/decrypt/etc. are also recorded there.
- HE keygen times: "total_sequential" = all parties' work executed serially in one process + aggregation; "per_party" = that party's own KeyGen/MultipartyKeyGen + (Multi)KeySwitchGen + MultiMultEvalKey. Medians over 20 independent keygens. ct*ct time is the EvalMult with automatic relinearisation (key from InsertEvalMultKey). Decrypt benchmarks are on the ct*ct product; every config's threshold-decryption result was checked correct (decrypt_correct).
- Sizes are cereal binary via Serial::Serialize (includes cereal headers, so slightly above raw polynomial bytes).
- GC: circuit is repeated 32-bit add + signed compare + mux built with emp's Integer class (inputs from the garbler only, so no input OT in this measurement), processed in ~190k-AND batches. Garbler and evaluator run alternately in the same thread over an in-memory MemIO buffer, timed separately (compute only, no network). Output labels verified against a plaintext mirror. A real 2-thread localhost-TCP pipelined run is also reported. T-pair scaling runs T independent garble/eval pairs in T threads (20M AND each); numbers are sum of per-thread rates and aggregate wall rate. Machine has only 6 GB RAM, hence batching rather than a recorded 20M-gate transcript.
- Wire label 16 B; garbler sends 32 B/AND (2 ciphertexts); free-XOR so XOR is 0 bytes; input label 16 B per garbler input bit.
- OT: 4.19M (IKNP) and 8.39M (Ferret) 128-bit OTs, single thread, two threads in one process over localhost TCP, semi-honest. Bytes counted as sender+receiver bytes written by NetIO (excluding TCP headers). IKNP COT = 16 B/OT (receiver->sender only); chosen-message = 48 B/OT; Ferret ~0.19 B/OT (amortised, plus setup ~1.17 MB). ot_per_s is from the slower of the two sides. Results verified. Ferret/IKNP "setup" = base OTs.
- AES-128 AND count: counted from Bristol files in the emp sources: aes_128.txt (bristol fashion) = 6400, AES-non-expanded.txt = 6800 (literature 6400).
