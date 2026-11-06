// Microbenchmarks for the Tiptoe baseline cost model (calib/scan_calib.json):
//  (1) server scan  out[r] = sum_j M[r][j] * b[j]  (mod 2^64),  M int8 (rows x cols), b uint64  == SimplePIR/Tiptoe "Apply"
//      (same for int16 M, used by the id matrix)
//  (2) client LWE mask  A*s  (mod 2^64), A (rows x n) expanded on the fly from a PRG (splitmix64), s ternary
// Usage: ./scan_bench rows cols n_lwe a_rows  -> JSON on stdout. Threads via OMP_NUM_THREADS / set below.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <chrono>
#include <omp.h>
using namespace std;
static inline uint64_t sm64(uint64_t x) { x += 0x9e3779b97f4a7c15ULL; x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL; x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL; return x ^ (x >> 31); }
static double now() { return chrono::duration<double>(chrono::steady_clock::now().time_since_epoch()).count(); }
template <class T>
double scan(const vector<T>& M, const vector<uint64_t>& b, vector<uint64_t>& out, size_t rows, size_t cols, int th) {
  double best = 1e30;
  for (int rep = 0; rep < 4; rep++) {
    double t0 = now();
#pragma omp parallel for num_threads(th) schedule(static)
    for (long r = 0; r < (long)rows; r++) {
      const T* row = &M[(size_t)r * cols];
      uint64_t acc = 0;
      for (size_t j = 0; j < cols; j++) acc += (uint64_t)(int64_t)row[j] * b[j];
      out[r] = acc;
    }
    best = min(best, now() - t0);
  }
  return best;
}
int main(int argc, char** argv) {
  size_t rows = argc > 1 ? atol(argv[1]) : 1500, cols = argc > 2 ? atol(argv[2]) : 128000;
  size_t n = argc > 3 ? atol(argv[3]) : 2048, arows = argc > 4 ? atol(argv[4]) : 16000;
  int maxT = omp_get_max_threads();
  vector<int8_t> M8(rows * cols);
  vector<int16_t> M16(rows * cols);
  for (size_t i = 0; i < M8.size(); i++) { uint64_t x = sm64(i); M8[i] = (int8_t)((x & 15) - 8); M16[i] = (int16_t)(x & 4095); }
  vector<uint64_t> b(cols), out(rows);
  for (size_t j = 0; j < cols; j++) b[j] = sm64(j + 777);
  printf("{\"rows\": %zu, \"cols\": %zu, \"n_lwe\": %zu, \"a_rows\": %zu, \"max_threads\": %d,\n \"scan_int8\": {", rows, cols, n, arows, maxT);
  bool first = true;
  for (int th = 1; th <= maxT; th *= 2) {
    double t = scan(M8, b, out, rows, cols, th);
    printf("%s\"%d\": {\"s\": %.6f, \"bytes\": %zu, \"GBps\": %.3f}", first ? "" : ", ", th, t, rows * cols, rows * cols / t / 1e9);
    first = false;
    if (th * 2 > maxT && th != maxT) { th = maxT / 2; }
  }
  printf("},\n \"scan_int16\": {");
  first = true;
  for (int th = 1; th <= maxT; th *= 2) {
    double t = scan(M16, b, out, rows, cols, th);
    printf("%s\"%d\": {\"s\": %.6f, \"bytes\": %zu, \"GBps\": %.3f}", first ? "" : ", ", th, t, rows * cols * 2, rows * cols * 2 / t / 1e9);
    first = false;
    if (th * 2 > maxT && th != maxT) { th = maxT / 2; }
  }
  printf("},\n \"lwe_mask\": {");
  vector<int8_t> s(n);
  for (size_t j = 0; j < n; j++) s[j] = (int8_t)(sm64(j + 5) % 3) - 1;
  vector<uint64_t> o2(arows);
  first = true;
  for (int th = 1; th <= maxT; th *= 2) {
    double best = 1e30;
    for (int rep = 0; rep < 3; rep++) {
      double t0 = now();
#pragma omp parallel for num_threads(th) schedule(static)
      for (long r = 0; r < (long)arows; r++) {
        uint64_t acc = 0; uint64_t base = (uint64_t)r * n;
        for (size_t j = 0; j < n; j++) acc += sm64(base + j) * (uint64_t)(int64_t)s[j];
        o2[r] = acc;
      }
      best = min(best, now() - t0);
    }
    printf("%s\"%d\": {\"s\": %.6f, \"macs\": %zu, \"Gmac_per_s\": %.3f}", first ? "" : ", ", th, best, arows * n, arows * n / best / 1e9);
    first = false;
    if (th * 2 > maxT && th != maxT) { th = maxT / 2; }
  }
  volatile uint64_t sink = out[0] + o2[0]; (void)sink;
  printf("}}\n");
}
