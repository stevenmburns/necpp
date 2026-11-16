/* libm_bench.cpp: time the scalar math the nec2++ fill leans on (gf():
   sqrt, sin, cos; eksc()/efld(): complex arithmetic, exp), so the MSVC,
   MinGW-w64 and glibc runtimes can be compared on one runner.

     g++ -O3 -fno-strict-overflow -march=x86-64 libm_bench.cpp -o libm_bench
     cl /O2 /EHsc libm_bench.cpp

   Prints ns per call for each function over arguments in the fill's range
   (kr from ~0 to a few hundred radians). Indicative: one thread, best of 5.
   A checksum is printed so nothing is optimised away. */
#include <chrono>
#include <cmath>
#include <complex>
#include <cstdio>
#include <vector>

#if defined(_MSC_VER)
#define NOINLINE __declspec(noinline)
#else
#define NOINLINE __attribute__((noinline))
#endif

static const int N = 1 << 20;

template <class F>
static double best_ns(F f) {
  double best = 1e30;
  for (int rep = 0; rep < 5; rep++) {
    auto t0 = std::chrono::steady_clock::now();
    f();
    auto t1 = std::chrono::steady_clock::now();
    double ns = std::chrono::duration<double, std::nano>(t1 - t0).count() / N;
    if (ns < best) best = ns;
  }
  return best;
}

int main() {
  std::vector<double> x(N), y(N), out(N);
  std::vector<std::complex<double>> a(N), b(N), c(N);
  unsigned s = 12345;
  auto rnd = [&]() { s = s * 1664525u + 1013904223u; return (s >> 8) / double(1 << 24); };
  for (int i = 0; i < N; i++) {
    x[i] = 0.01 + 300.0 * rnd();       /* kr, radians */
    y[i] = -20.0 * rnd();              /* exp arguments */
    a[i] = {rnd() - 0.5, rnd() - 0.5};
    b[i] = {rnd() + 0.1, rnd() - 0.5};
  }
  double sum = 0;
  struct R { const char* name; double ns; };
  std::vector<R> r;
  r.push_back({"sqrt", best_ns([&] { for (int i = 0; i < N; i++) out[i] = std::sqrt(x[i]); })});
  sum += out[N / 2];
  r.push_back({"sin", best_ns([&] { for (int i = 0; i < N; i++) out[i] = std::sin(x[i]); })});
  sum += out[N / 2];
  r.push_back({"cos", best_ns([&] { for (int i = 0; i < N; i++) out[i] = std::cos(x[i]); })});
  sum += out[N / 2];
  r.push_back({"sin+cos (gf)", best_ns([&] { for (int i = 0; i < N; i++) out[i] = std::sin(x[i]) / x[i] + std::cos(x[i]) / x[i]; })});
  sum += out[N / 2];
  r.push_back({"exp", best_ns([&] { for (int i = 0; i < N; i++) out[i] = std::exp(y[i]); })});
  sum += out[N / 2];
  r.push_back({"complex exp", best_ns([&] { for (int i = 0; i < N; i++) c[i] = std::exp(std::complex<double>(y[i] * 0.01, x[i])); })});
  sum += c[N / 2].real();
  r.push_back({"complex mul", best_ns([&] { for (int i = 0; i < N; i++) c[i] = a[i] * b[i]; })});
  sum += c[N / 2].real();
  r.push_back({"complex div", best_ns([&] { for (int i = 0; i < N; i++) c[i] = a[i] / b[i]; })});
  sum += c[N / 2].real();
  for (const R& e : r) std::printf("LIBM %-14s %7.2f ns/call\n", e.name, e.ns);
  std::printf("checksum %.6e\n", sum);
  return 0;
}
