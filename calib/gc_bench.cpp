// Garbled-circuit / OT microbenchmarks with legacy emp-tool + emp-ot (half-gates, IKNP, Ferret).
// Compile with -DTHREADING (thread-local circ_exec / prot_exec).
#include "emp-tool/emp-tool.h"
#include "emp-ot/emp-ot.h"
#include <chrono>
#include <thread>
#include <vector>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <string>
using namespace emp;
using namespace std;
typedef chrono::steady_clock Clk;
static double secs(Clk::time_point a, Clk::time_point b) { return chrono::duration<double>(b - a).count(); }

// ---- semi-honest protocol executions (garbler inputs only; ALICE = garbler) ----
template <class IO> struct GenProt : ProtocolExecution {
  IO* io; HalfGateGen<IO>* gc;
  GenProt(IO* io, HalfGateGen<IO>* gc) : ProtocolExecution(ALICE), io(io), gc(gc) {}
  void feed(block* l, int party, const bool* b, int n) override {
    if (party != ALICE) { fprintf(stderr, "only ALICE inputs\n"); exit(1); }
    PRG prg; prg.random_block(l, n);
    vector<block> out(n);
    for (int i = 0; i < n; i++) out[i] = b[i] ? (l[i] ^ gc->delta) : l[i];
    io->send_block(out.data(), n);
  }
  void reveal(bool*, int, const block*, int) override {}
};
template <class IO> struct EvaProt : ProtocolExecution {
  IO* io;
  EvaProt(IO* io) : ProtocolExecution(BOB), io(io) {}
  void feed(block* l, int, const bool*, int n) override { io->recv_block(l, n); }
  void reveal(bool*, int, const block*, int) override {}
};

static const int OPS = 2000;   // x=x+y; lt=(x<y); x = lt? y : x   per op (~96 ANDs)
struct BatchRes { uint64_t ands = 0, in_bytes = 0, tab_bytes = 0; };

// plain mirror of one batch
static uint32_t plain_batch(uint32_t x, uint32_t y) {
  for (int i = 0; i < OPS; i++) { x = x + y; bool lt = (int32_t)x < (int32_t)y; if (lt) x = y;  /* emp Integer compare is signed */ }
  return x;
}

// gen side of one batch; returns zero-label of result bits in out0
template <class IO>
static void gen_batch(IO* io, HalfGateGen<IO>* gc, GenProt<IO>* gp, uint32_t xv, uint32_t yv, block* out0, BatchRes& r) {
  CircuitExecution::circ_exec = gc; ProtocolExecution::prot_exec = gp;
  uint64_t c0 = io->counter, a0 = gc->num_and();
  Integer x(32, xv, ALICE), y(32, yv, ALICE);
  uint64_t c1 = io->counter;
  for (int i = 0; i < OPS; i++) { x = x + y; Bit lt = x < y; x = x.select(lt, y); }
  for (int i = 0; i < 32; i++) out0[i] = x[i].bit;
  r.ands += gc->num_and() - a0; r.in_bytes += c1 - c0; r.tab_bytes += io->counter - c1;
}
template <class IO>
static void eva_batch(IO* io, HalfGateEva<IO>* ev, EvaProt<IO>* ep, block* out) {
  CircuitExecution::circ_exec = ev; ProtocolExecution::prot_exec = ep;
  Integer x(32, 0, ALICE), y(32, 0, ALICE);
  for (int i = 0; i < OPS; i++) { x = x + y; Bit lt = x < y; x = x.select(lt, y); }
  for (int i = 0; i < 32; i++) out[i] = x[i].bit;
}
static bool check(const block* l0, const block* le, block delta, uint32_t expect) {
  for (int i = 0; i < 32; i++) {
    block want = ((expect >> i) & 1) ? (l0[i] ^ delta) : l0[i];
    if (!cmpBlock(&want, &le[i], 1)) return false;
  }
  return true;
}

struct PairResult { double tg = 0, te = 0; uint64_t ands = 0, in_bytes = 0, tab_bytes = 0; bool ok = true; };

// Sequential per-thread: garble batch into MemIO (timed), evaluate batch from MemIO (timed).
static PairResult run_pair_seq(uint64_t target_ands, int seed) {
  PairResult pr; MemIO io(16 << 20);
  HalfGateGen<MemIO>* gc = new HalfGateGen<MemIO>(&io);
  HalfGateEva<MemIO>* ev = new HalfGateEva<MemIO>(&io);   // consumes the 3 setup blocks gen wrote
  GenProt<MemIO> gp(&io, gc); EvaProt<MemIO> ep(&io);
  uint64_t setup_bytes = io.counter; (void)setup_bytes;
  srand(seed);
  block o0[32], oe[32]; BatchRes br;
  while (br.ands < target_ands) {
    uint32_t xv = rand(), yv = rand();
    io.clear(); io.read_pos = 0;
    auto t0 = Clk::now();
    gen_batch(&io, gc, &gp, xv, yv, o0, br);
    auto t1 = Clk::now();
    eva_batch(&io, ev, &ep, oe);
    auto t2 = Clk::now();
    pr.tg += secs(t0, t1); pr.te += secs(t1, t2);
    if (io.read_pos != io.size) { pr.ok = false; if (getenv("GCDBG")) fprintf(stderr, "pos %lld size %lld\n", (long long)io.read_pos, (long long)io.size); }
    if (!check(o0, oe, gc->delta, plain_batch(xv, yv))) { pr.ok = false; if (getenv("GCDBG")) fprintf(stderr, "label mismatch\n"); }
  }
  pr.ands = br.ands; pr.in_bytes = br.in_bytes; pr.tab_bytes = br.tab_bytes;
  delete ev; delete gc;
  return pr;
}

// Real pipelined pair over localhost TCP, two threads.
static void run_pair_net(uint64_t target_ands, int port, double& wall, uint64_t& ands, uint64_t& bytes, bool& ok) {
  atomic<bool> good(true); uint64_t g_ands = 0, g_bytes = 0;
  int nb = 0; { uint64_t t = 0; while (t < target_ands) { t += 190000; nb++; } }
  auto tg = [&]() {
    NetIO io(nullptr, port, true);
    HalfGateGen<NetIO> gc(&io); GenProt<NetIO> gp(&io, &gc);
    BatchRes br; block o0[32]; srand(7);
    for (int b = 0; b < nb; b++) {
      uint32_t xv = rand(), yv = rand();
      gen_batch(&io, &gc, &gp, xv, yv, o0, br);
      // ship the expected-label check data out-of-band via the same channel is not allowed (would add bytes); skip
    }
    io.flush(); g_ands = br.ands; g_bytes = io.counter;
  };
  auto te = [&]() {
    NetIO io("127.0.0.1", port, true);
    HalfGateEva<NetIO> ev(&io); EvaProt<NetIO> ep(&io);
    block oe[32];
    for (int b = 0; b < nb; b++) eva_batch(&io, &ev, &ep, oe);
  };
  auto t0 = Clk::now();
  thread a(tg); usleep(200000); thread b(te); a.join(); b.join();
  wall = secs(t0, Clk::now()) - 0.2; ands = g_ands; bytes = g_bytes; ok = good;
}

// ---------------- OT ----------------
struct OTRes { double secs_setup = 0, secs_run = 0; uint64_t setup_bytes = 0, run_bytes_s = 0, run_bytes_r = 0; int64_t n = 0; bool ok = true; };

static OTRes ot_iknp(int64_t N, int port, bool chosen) {
  OTRes R; R.n = N;
  uint64_t sb0 = 0, rb0 = 0, sb1 = 0, rb1 = 0; double ts = 0, tr = 0, tsetup_s = 0, tsetup_r = 0;
  vector<block> d0(N), d1(N), rec(N); vector<char> bb(N); bool* b = (bool*)bb.data();
  PRG prg; prg.random_block(d0.data(), N); prg.random_block(d1.data(), N); prg.random_bool(b, N);
  atomic<int> ready(0);
  thread S([&]() {
    NetIO io(nullptr, port, true); IKNP<NetIO> ot(&io);
    auto t0 = Clk::now(); ot.setup_send(); io.flush(); tsetup_s = secs(t0, Clk::now()); sb0 = io.counter;
    ready++; while (ready < 2) {}
    t0 = Clk::now();
    if (chosen) ot.send(d0.data(), d1.data(), N); else ot.send_cot(d0.data(), N);
    io.flush(); ts = secs(t0, Clk::now()); sb1 = io.counter;
    if (!chosen) { /* d0 now holds the random OT messages; delta = ot.Delta */ }
    if (!chosen) { for (int64_t i = 0; i < N; i++) d1[i] = d0[i] ^ ot.Delta; }
  });
  thread Rv([&]() {
    usleep(200000);
    NetIO io("127.0.0.1", port, true); IKNP<NetIO> ot(&io);
    auto t0 = Clk::now(); ot.setup_recv(); io.flush(); tsetup_r = secs(t0, Clk::now()); rb0 = io.counter;
    ready++; while (ready < 2) {}
    t0 = Clk::now();
    if (chosen) ot.recv(rec.data(), b, N); else ot.recv_cot(rec.data(), b, N);
    io.flush(); tr = secs(t0, Clk::now()); rb1 = io.counter;
  });
  S.join(); Rv.join();
  for (int64_t i = 0; i < N; i++) { block want = b[i] ? d1[i] : d0[i]; if (!cmpBlock(&want, &rec[i], 1)) { R.ok = false; break; } }
  R.secs_setup = max(tsetup_s, tsetup_r); R.secs_run = max(ts, tr);
  R.setup_bytes = sb0 + rb0; R.run_bytes_s = sb1 - sb0; R.run_bytes_r = rb1 - rb0;
  return R;
}

static OTRes ot_ferret(int64_t N, int port) {
  const char* td = getenv("TMPDIR"); string base = string(td ? td : "/tmp") + "/ferret_pre_" + to_string(getpid());
  string pre_s = base + "_s", pre_r = base + "_r"; remove(pre_s.c_str()); remove(pre_r.c_str());
  OTRes R; R.n = N;
  uint64_t sb0 = 0, rb0 = 0, sb1 = 0, rb1 = 0; double ts = 0, tr = 0, tsetup_s = 0, tsetup_r = 0;
  vector<block> d0(N), rec(N); vector<char> bb(N); bool* b = (bool*)bb.data();
  PRG prg; prg.random_bool(b, N);
  atomic<int> ready(0); block delta;
  thread S([&]() {
    NetIO io(nullptr, port, true); NetIO* ios[1] = {&io};
    auto t0 = Clk::now(); FerretCOT<NetIO> ot(ALICE, 1, ios, false, true, pre_s); tsetup_s = secs(t0, Clk::now()); sb0 = io.counter;
    ready++; while (ready < 2) {}
    t0 = Clk::now(); ot.send_cot(d0.data(), N); io.flush(); ts = secs(t0, Clk::now()); sb1 = io.counter;
    delta = ot.Delta;
  });
  thread Rv([&]() {
    usleep(200000);
    NetIO io("127.0.0.1", port, true); NetIO* ios[1] = {&io};
    auto t0 = Clk::now(); FerretCOT<NetIO> ot(BOB, 1, ios, false, true, pre_r); tsetup_r = secs(t0, Clk::now()); rb0 = io.counter;
    ready++; while (ready < 2) {}
    t0 = Clk::now(); ot.recv_cot(rec.data(), b, N); io.flush(); tr = secs(t0, Clk::now()); rb1 = io.counter;
  });
  S.join(); Rv.join();
  for (int64_t i = 0; i < N; i++) { block want = b[i] ? (d0[i] ^ delta) : d0[i]; if (!cmpBlock(&want, &rec[i], 1)) { R.ok = false; break; } }
  R.secs_setup = max(tsetup_s, tsetup_r); R.secs_run = max(ts, tr);
  R.setup_bytes = sb0 + rb0; R.run_bytes_s = sb1 - sb0; R.run_bytes_r = rb1 - rb0;
  remove(pre_s.c_str()); remove(pre_r.c_str());
  return R;
}

static int count_and(const char* path) {
  FILE* f = fopen(path, "r"); if (!f) return -1;
  char line[512]; int n = 0, ngate = 0;
  if (!fgets(line, sizeof line, f)) return -1;
  while (fgets(line, sizeof line, f)) {
    if (strstr(line, "AND")) n++;
    if (strstr(line, "XOR") || strstr(line, "INV") || strstr(line, "AND")) ngate++;
  }
  fclose(f); return n;
}

int main(int argc, char** argv) {
  uint64_t ands_single = 40000000ULL;   // per pair
  uint64_t ands_par = 20000000ULL;      // per pair in the T-scaling runs
  int64_t NOT = 1 << 22;
  const char* aes1 = "/home/ec2-user/emp-legacy/include/emp-tool/circuits/files/bristol_fashion/aes_128.txt";
  const char* aes2 = "/home/ec2-user/emp-legacy/include/emp-tool/circuits/files/bristol_format/AES-non-expanded.txt";
  FILE* js = stdout;
  fprintf(js, "{\n");
  fprintf(js, "  \"library\": \"emp-tool/emp-ot legacy (header-only gates, half-gates + MITCCRH, AES-NI)\",\n");
  fprintf(js, "  \"aes128_and_gates\": {\"bristol_fashion_aes_128.txt\": %d, \"bristol_format_AES-non-expanded.txt\": %d},\n", count_and(aes1), count_and(aes2));

  // ---- GC single thread, sequential (isolated compute, MemIO) ----
  fprintf(stderr, "GC single...\n");
  PairResult p = run_pair_seq(ands_single, 1);
  fprintf(js, "  \"gc_single_thread\": {\"circuit\": \"repeated 32-bit add + compare + mux (Integer class), garbler inputs\", \"and_gates\": %llu, "
              "\"garble_s\": %.4f, \"eval_s\": %.4f, \"garble_and_per_s\": %.0f, \"eval_and_per_s\": %.0f, "
              "\"table_bytes\": %llu, \"bytes_per_and\": %.4f, \"input_label_bytes\": %llu, \"bytes_per_input_label\": 16, \"verified_correct\": %s},\n",
          (unsigned long long)p.ands, p.tg, p.te, p.ands / p.tg, p.ands / p.te, (unsigned long long)p.tab_bytes,
          (double)p.tab_bytes / p.ands, (unsigned long long)p.in_bytes, p.ok ? "true" : "false");

  // ---- GC over real localhost TCP, 2 threads pipelined ----
  fprintf(stderr, "GC net...\n");
  { double wall; uint64_t a, by; bool ok;
    run_pair_net(ands_single, 23456, wall, a, by, ok);
    fprintf(js, "  \"gc_localhost_tcp_pipelined_pair\": {\"and_gates\": %llu, \"wall_s\": %.4f, \"and_per_s_end_to_end\": %.0f, \"garbler_bytes_sent\": %llu},\n",
            (unsigned long long)a, wall, a / wall, (unsigned long long)by); }

  // ---- T independent pairs ----
  fprintf(js, "  \"gc_parallel_independent_pairs\": [\n");
  int Ts[] = {1, 8, 64};
  for (int ti = 0; ti < 3; ti++) {
    int T = Ts[ti]; fprintf(stderr, "GC T=%d...\n", T);
    vector<PairResult> res(T); vector<thread> th;
    auto t0 = Clk::now();
    for (int i = 0; i < T; i++) th.emplace_back([&, i]() { res[i] = run_pair_seq(ands_par, 100 + i); });
    for (auto& t : th) t.join();
    double wall = secs(t0, Clk::now());
    double sg = 0, se = 0; uint64_t tot = 0; bool ok = true;
    for (auto& r : res) { sg += r.ands / r.tg; se += r.ands / r.te; tot += r.ands; ok &= r.ok; }
    fprintf(js, "    {\"T\": %d, \"and_per_pair\": %llu, \"wall_s\": %.3f, \"agg_garble_and_per_s_sum_of_thread_rates\": %.0f, "
                "\"agg_eval_and_per_s_sum_of_thread_rates\": %.0f, \"agg_pair_and_per_s_wall\": %.0f, \"verified_correct\": %s}%s\n",
            T, (unsigned long long)ands_par, wall, sg, se, tot / wall, ok ? "true" : "false", ti < 2 ? "," : "");
  }
  fprintf(js, "  ],\n");

  // ---- OT ----
  fprintf(js, "  \"ot\": {\n");
  fprintf(stderr, "OT IKNP cot...\n");
  OTRes a = ot_iknp(NOT, 24001, false);
  fprintf(stderr, "OT IKNP chosen...\n");
  OTRes bres = ot_iknp(NOT, 24002, true);
  auto pr = [&](const char* name, OTRes& r, bool last) {
    fprintf(js, "    \"%s\": {\"num_ot\": %lld, \"setup_s\": %.4f, \"setup_bytes_total\": %llu, \"run_s\": %.4f, \"ot_per_s\": %.0f, "
                "\"bytes_sender_to_receiver\": %llu, \"bytes_receiver_to_sender\": %llu, \"bytes_total_per_ot\": %.4f, \"verified_correct\": %s}%s\n",
            name, (long long)r.n, r.secs_setup, (unsigned long long)r.setup_bytes, r.secs_run, r.n / r.secs_run,
            (unsigned long long)r.run_bytes_s, (unsigned long long)r.run_bytes_r,
            (double)(r.run_bytes_s + r.run_bytes_r) / r.n, r.ok ? "true" : "false", last ? "" : ",");
  };
  pr("iknp_correlated_ot_128bit", a, false);
  pr("iknp_chosen_message_ot_128bit", bres, false);
  fprintf(stderr, "OT Ferret...\n");
  OTRes f = ot_ferret(NOT * 2, 24003);
  pr("ferret_correlated_ot_128bit", f, true);
  fprintf(js, "  }\n}\n");
  return 0;
}
