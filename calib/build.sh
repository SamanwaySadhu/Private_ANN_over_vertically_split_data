#!/bin/bash
# Build calibration microbenchmarks. Usage: ./build.sh  (from anywhere)
set -e
D="$(cd "$(dirname "$0")" && pwd)"
cd "$D"
EMP=$HOME/emp-legacy/include
g++ -std=c++17 -O3 -march=native -maes -mrdseed -mpclmul -DTHREADING -funroll-loops -pthread \
    -Wno-ignored-attributes -Wno-unused-result -Wno-deprecated-declarations \
    -I"$EMP" gc_bench.cpp "$EMP/emp-tool/emp-tool.cpp" -o gc_bench -lcrypto
if [ -f he_bench.cpp ]; then
g++ -std=c++17 -O3 -march=native -fopenmp -DOPENFHE_VERSION=1.0.4 -DMATHBACKEND=4 \
    -Wno-unused-parameter -Wno-ignored-attributes \
    -I/usr/local/include/openfhe -I/usr/local/include/openfhe/core -I/usr/local/include/openfhe/pke \
    -I/usr/local/include/openfhe/binfhe -I/usr/local/include/openfhe/cereal \
    he_bench.cpp -o he_bench -L/usr/local/lib -lOPENFHEpke -lOPENFHEcore -lOPENFHEbinfhe \
    -Wl,--start-group /usr/local/lib/libsnark.a /usr/local/lib/libff.a -Wl,--end-group -lgmp -lgmpxx -lpbc -lcrypto -Wl,-rpath,/usr/local/lib
fi
