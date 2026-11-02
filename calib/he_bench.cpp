// OpenFHE BFVRNS threshold (m-of-m) microbenchmarks. Mirrors real_he.py API usage.
// usage: he_bench full  <reps>          -> per (batch, m) full table, JSON to stdout
//        he_bench scale <reps> <batch..> -> Encrypt / EvalMult timings for largest m (run under different OMP_NUM_THREADS)
#include "openfhe.h"
#include "ciphertext-ser.h"
#include "cryptocontext-ser.h"
#include "key/key-ser.h"
#include "scheme/bfvrns/bfvrns-ser.h"
#include <omp.h>
#include <chrono>
#include <algorithm>
#include <sstream>
#include <random>
#include <cstdio>
using namespace lbcrypto;
using namespace std;
typedef chrono::steady_clock Clk;
static const int64_t P = 2147352577;

template <class F> static double time_ms(F&& f) { auto t0 = Clk::now(); f(); return chrono::duration<double, milli>(Clk::now() - t0).count(); }
static double median(vector<double> v) { sort(v.begin(), v.end()); size_t n = v.size(); return n % 2 ? v[n / 2] : 0.5 * (v[n / 2 - 1] + v[n / 2]); }
template <class F> static double med(int reps, F&& f) { vector<double> v; for (int i = 0; i < reps; i++) v.push_back(time_ms(f)); return median(v); }
template <class T> static size_t ser_size(const T& o) { stringstream ss; Serial::Serialize(o, ss, SerType::BINARY); return ss.str().size(); }

static CryptoContext<DCRTPoly> make_cc(uint32_t batch) {
  CCParams<CryptoContextBFVRNS> prm;
  prm.SetPlaintextModulus(P);
  prm.SetMultiplicativeDepth(1);
  prm.SetSecurityLevel(HEStd_128_classic);
  prm.SetMultipartyMode(NOISE_FLOODING_MULTIPARTY);
  prm.SetBatchSize(batch);
  auto cc = GenCryptoContext(prm);
  cc->Enable(PKE); cc->Enable(KEYSWITCH); cc->Enable(LEVELEDSHE); cc->Enable(ADVANCEDSHE); cc->Enable(MULTIPARTY);
  return cc;
}

struct KG { vector<KeyPair<DCRTPoly>> kps; KeyPair<DCRTPoly> joint; EvalKey<DCRTPoly> relin; double total_ms, agg_ms; vector<double> party_ms; };

// distributed keygen exactly as real_he.py; timed per party
static KG keygen(CryptoContext<DCRTPoly> cc, int m) {
  KG g; g.party_ms.assign(m, 0); g.agg_ms = 0;
  auto T0 = Clk::now();
  g.kps.resize(m);
  g.party_ms[0] += time_ms([&] { g.kps[0] = cc->KeyGen(); });
  for (int i = 1; i < m; i++) g.party_ms[i] += time_ms([&] { g.kps[i] = cc->MultipartyKeyGen(g.kps[i - 1].publicKey); });
  auto pk = g.kps[m - 1].publicKey; auto tag = pk->GetKeyTag();
  vector<EvalKey<DCRTPoly>> ek(m);
  g.party_ms[0] += time_ms([&] { ek[0] = cc->KeySwitchGen(g.kps[0].secretKey, g.kps[0].secretKey); });
  for (int i = 1; i < m; i++) g.party_ms[i] += time_ms([&] { ek[i] = cc->MultiKeySwitchGen(g.kps[i].secretKey, g.kps[i].secretKey, ek[0]); });
  EvalKey<DCRTPoly> acc = ek[0];
  for (int i = 1; i < m; i++) g.agg_ms += time_ms([&] { acc = cc->MultiAddEvalKeys(acc, ek[i], tag); });
  vector<EvalKey<DCRTPoly>> parts(m);
  for (int i = 0; i < m; i++) g.party_ms[i] += time_ms([&] { parts[i] = cc->MultiMultEvalKey(g.kps[i].secretKey, acc, tag); });
  EvalKey<DCRTPoly> fin = parts[0];
  for (int i = 1; i < m; i++) g.agg_ms += time_ms([&] { fin = cc->MultiAddEvalMultKeys(fin, parts[i], tag); });
  g.agg_ms += time_ms([&] { cc->InsertEvalMultKey({fin}); });
  g.total_ms = chrono::duration<double, milli>(Clk::now() - T0).count();
  g.joint = {pk, g.kps[m - 1].secretKey}; g.relin = fin;
  return g;
}

static string jarr(const vector<double>& v) { string s = "["; char b[64]; for (size_t i = 0; i < v.size(); i++) { snprintf(b, sizeof b, "%s%.4f", i ? ", " : "", v[i]); s += b; } return s + "]"; }

int main(int argc, char** argv) {
  string mode = argc > 1 ? argv[1] : "full";
  int reps = argc > 2 ? atoi(argv[2]) : 20;
  vector<uint32_t> batches = {1024, 4096, 8192};
  if (mode == "scale" && argc > 3) { batches.clear(); for (int i = 3; i < argc; i++) batches.push_back(atoi(argv[i])); }
  vector<int> ms = {2, 3, 4, 6, 8};
  if (mode == "scale") ms = {8};
  mt19937_64 rng(1);
  printf("{\n  \"omp_max_threads\": %d, \"reps\": %d, \"mode\": \"%s\", \"plaintext_modulus\": %lld,\n  \"configs\": {\n", omp_get_max_threads(), reps, mode.c_str(), (long long)P);
  for (size_t bi = 0; bi < batches.size(); bi++) {
    uint32_t batch = batches[bi];
    auto cc = make_cc(batch);
    uint32_t N = cc->GetRingDimension();
    auto ep = cc->GetCryptoParameters()->GetElementParams();
    size_t ntowers = ep->GetParams().size();
    uint32_t logq = ep->GetModulus().GetMSB();
    fprintf(stderr, "batch %u ring_dim %u logq %u towers %zu\n", batch, N, logq, ntowers);
    printf("    \"%u\": {\"batch_size\": %u, \"ring_dim\": %u, \"log2_q_bits\": %u, \"num_rns_towers\": %zu, \"num_slots\": %u, \"by_m\": {\n", batch, batch, N, logq, ntowers, N);
    for (size_t mi = 0; mi < ms.size(); mi++) {
      int m = ms[mi];
      fprintf(stderr, "  m=%d\n", m);
      // ---- keygen timing (median over reps independent runs); last run's keys are used below ----
      vector<double> tot, aggv, pavg, pmax; KG g;
      for (int r = 0; r < reps; r++) {
        g = keygen(cc, m);
        tot.push_back(g.total_ms); aggv.push_back(g.agg_ms);
        double s = 0, mx = 0; for (double x : g.party_ms) { s += x; mx = max(mx, x); }
        pavg.push_back(s / m); pmax.push_back(mx);
      }
      double kg_total = median(tot), kg_agg = median(aggv), kg_pavg = median(pavg), kg_pmax = median(pmax);
      auto pk = g.joint.publicKey;
      vector<int64_t> va(batch), vb(batch);
      for (auto& x : va) x = rng() % P;
      for (auto& x : vb) x = rng() % P;
      Plaintext pta, ptb;
      double t_pack = med(reps, [&] { pta = cc->MakePackedPlaintext(va); });
      ptb = cc->MakePackedPlaintext(vb);
      Ciphertext<DCRTPoly> ca, cb, cadd, csub, cmp, cmc;
      double t_enc = med(reps, [&] { ca = cc->Encrypt(pk, pta); });
      cb = cc->Encrypt(pk, ptb);
      double t_add = med(reps, [&] { cadd = cc->EvalAdd(ca, cb); });
      double t_sub = med(reps, [&] { csub = cc->EvalSub(ca, cb); });
      double t_mpt = med(reps, [&] { cmp = cc->EvalMult(ca, ptb); });
      double t_mcc = med(reps, [&] { cmc = cc->EvalMult(ca, cb); });
      size_t sz_ct = ser_size(ca), sz_ctmul = ser_size(cmc), sz_pk = ser_size(pk), sz_rk = ser_size(g.relin);
      size_t n_elems_ct = ca->GetElements().size(), n_elems_mul = cmc->GetElements().size();
      // ---- threshold decryption of the ct*ct product ----
      vector<Ciphertext<DCRTPoly>> lead, mainv; Plaintext res;
      double t_lead = med(reps, [&] { lead = cc->MultipartyDecryptLead({cmc}, g.kps[0].secretKey); });
      vector<double> mainv_t;
      double t_main = med(reps, [&] { mainv = cc->MultipartyDecryptMain({cmc}, g.kps[1].secretKey); });
      vector<Ciphertext<DCRTPoly>> shares = lead;
      for (int i = 1; i < m; i++) { auto s = cc->MultipartyDecryptMain({cmc}, g.kps[i].secretKey); shares.push_back(s[0]); }
      double t_fus = med(reps, [&] { cc->MultipartyDecryptFusion(shares, &res); });
      res->SetLength(batch);
      auto out = res->GetPackedValue();
      bool ok = true;
      for (uint32_t i = 0; i < batch && ok; i++) { __int128 e = ((__int128)va[i] * vb[i]) % P; if ((((int64_t)out[i] % P) + P) % P != (int64_t)e) ok = false; }
      size_t sz_lead = ser_size(lead[0]), sz_main = ser_size(mainv[0]);
      // threshold-decrypt a fresh (non-multiplied) ciphertext too, to report share size there
      printf("      \"%d\": {\"m\": %d, \"decrypt_correct\": %s,\n", m, m, ok ? "true" : "false");
      printf("        \"bytes\": {\"ciphertext_fresh\": %zu, \"ciphertext_after_mult_relin\": %zu, \"public_key\": %zu, \"eval_mult_key\": %zu, \"partial_decrypt_share_lead\": %zu, \"partial_decrypt_share_main\": %zu, \"ct_polys_fresh\": %zu, \"ct_polys_after_mult\": %zu},\n",
             sz_ct, sz_ctmul, sz_pk, sz_rk, sz_lead, sz_main, n_elems_ct, n_elems_mul);
      printf("        \"ms\": {\"keygen_total_sequential\": %.4f, \"keygen_per_party_avg\": %.4f, \"keygen_per_party_max\": %.4f, \"keygen_aggregation\": %.4f, "
             "\"pack_plaintext\": %.5f, \"encrypt_pk\": %.4f, \"eval_add\": %.5f, \"eval_sub\": %.5f, \"eval_mult_ct_pt\": %.4f, \"eval_mult_ct_ct_relin\": %.4f, "
             "\"decrypt_lead\": %.4f, \"decrypt_main\": %.4f, \"decrypt_fusion\": %.4f, \"keygen_all_reps_total\": %s}}%s\n",
             kg_total, kg_pavg, kg_pmax, kg_agg, t_pack, t_enc, t_add, t_sub, t_mpt, t_mcc, t_lead, t_main, t_fus, jarr(tot).c_str(), mi + 1 < ms.size() ? "," : "");
      fflush(stdout);
    }
    printf("    }}%s\n", bi + 1 < batches.size() ? "," : "");
  }
  printf("  }\n}\n");
  return 0;
}
