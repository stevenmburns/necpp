# Building the nec2++ command line (accelerated engine)

`scripts/build_cli.py` builds a portable `nec2++` executable whose engine is
configured exactly as the `pynec-accel` Python wheel's is: the matrix fill
parallelised with OpenMP, and the LU through LAPACKE (`zgetrf_work` /
`zgetrs_work`) into OpenBLAS. `.github/workflows/cli-release.yml` runs it in CI.

## Variants

| variant | necpp commit | what |
|---|---|---|
| `accel` | `a08a0d9` (python-necpp v1.7.6's `necpp_src`, = pynec-accel 1.7.6) | the plain accelerated engine |
| `reuse` | `62dacd4` (python-necpp v1.7.7's `necpp_src`, = pynec-accel 1.7.7; `accelerated` today) | the same plus fill-pair reuse, **on by default** |

Patches applied to a copy of the tree (never to the checkout):

- `scripts/patches/0001-cli-n-skips-intersection-check.patch` (both):
  `nec2++ -n` turns off the wire-intersection check, which NEC-2 does not
  make. The wheel turns it off with `set_intersection_check(False)`; the
  command line had no way to, and refuses decks such as W8IO's ELT whip.
  (Upstream's newer `-w` downgrades the check to a warning; this fork has no
  `set_intersection_fatal`.) The patch also makes `main` end in an explicit
  `return 0;`, which the dispatch build needs because it renames `main`.
- `scripts/patches/0002-fill-reuse-default-on.patch` (`reuse` only):
  `FILL_REUSE_DEFAULT = 1`. `PYNEC_FILL_REUSE=0` still turns reuse off,
  `PYNEC_FILL_REUSE=2` is the slow verify mode.
- `scripts/patches/0003-math-util-engine-namespace.patch` (both): three
  `::norm*` calls in `math_util.h` become `NECPP_NS::norm*`; `NECPP_NS` is
  empty unless the dispatch build defines it, so it is the original code.
- `scripts/patches/0004-cli-4nec2-file-names.patch` (both): the file-name
  conventions 4nec2 uses with its NEC-2 engines, so the exe can be installed
  as 4nec2's `nec2dxs*.exe` with no shim. See "4nec2" below. Adds
  `src/nec2d_names.{h,cpp}` (also listed in `src/Makefile.am`, so a plain
  autotools build gets it too) and a call from `nec_main`; nothing changes
  when `-i` is given.

## Why a script and not autotools

`configure --with-lapack` probes `clapack_zgetrf`, which OpenBLAS does not
export, and the wheel never uses that path anyway: it generates `config.h`
with `--without-lapack` and adds `-DLAPACK=1 -DLAPACKE=1` itself. There is no
CMake build, and the MSVC build has to be driven by hand regardless. The
script mirrors `PyNEC/setup.py` instead: the same sources (minus the Python
wrapper; plus `nec2cpp.cpp` and `XGetopt.cpp`; `libNEC.cpp`, the C API the
command line never calls, is left out), the same defines, and the flags the
wheel's `_PyNEC.so` records in `DW_AT_producer`:
`-O3 -fno-strict-overflow -march=x86-64 -mtune=generic -fopenmp`.
`config.h` holds only `VERSION` / `BUILD_DATE` (Eigen stays off, as in the
wheel), so the script writes it.

## The engine is in the executable twice (CPU dispatch)

Every engine source is compiled twice, through generated wrappers that
`#include` it inside a namespace: `nec_base` at the baseline
(`-march=x86-64`; MSVC default, SSE2) and `nec_avx2` at x86-64-v3
(`-march=x86-64-v3`; MSVC `/arch:AVX2`). All system headers are included
first, outside the namespace (`fat/nec_cli_prelude.h`), so only the engine
lands inside it. A small `main` (`fat/dispatch.cpp`, baseline) checks cpuid
(`__builtin_cpu_supports("x86-64-v3")` on GCC; `__cpuid`/`_xgetbv` on MSVC)
and calls one copy. No source change and no `target_clones` (MSVC has none).

- `NECPP_ENGINE=baseline` forces the baseline copy; `avx2` forces the other
  (refused on a CPU without it); unset or `auto` picks by cpuid.
- `NECPP_ENGINE_VERBOSE=1` (or `-v`) prints which copy ran, on stderr.
- OpenBLAS dispatches on its own (`DYNAMIC_ARCH`) in both copies.
- **Shared inline code.** Template and inline functions outside the engine
  namespace (`std::vector<std::complex<double>>` and the like) are emitted by
  both copies under the same name; the linker keeps one. Both GNU ld and
  link.exe keep the first one they meet, so the baseline objects are linked
  first: whatever is shared is baseline code, safe on every CPU. CI proves
  it on Linux by running the auto-dispatched executable under
  `qemu-x86_64 -cpu Westmere` (no AVX: qemu raises #UD on any VEX
  instruction).
- **Start-up code.** A copy's dynamic initialisers run before `main`, so
  before the dispatcher has chosen. The avx2 copy must have none: the build
  fails if any avx2 object carries `.init_array` (GCC) or a `.CRT$X*`
  section (MSVC). The one source that has one, `electromag.cpp`
  (`permeability = four_pi() * 1.0e-7`), is compiled at the baseline in both
  copies (`BASELINE_ONLY`); it is not hot. This was found by the qemu test:
  the first build died with SIGILL on `-v` under `-cpu Westmere`.

## Linux: fully static

Built in `ubuntu:24.04` with `gcc-14`/`g++-14` (14.2; the wheel's manylinux
build used 14.2.1). OpenBLAS is built from source:

- OpenBLAS **0.3.34** (released 2026-07-16; the version scipy-openblas32
  0.3.34.0.0 in the wheels carries), `OpenBLAS-0.3.34.tar.gz`, sha256
  `cd7e129868320cc2d033afa920e31202dfe0b8066a5b66661900ccc0f197dfed`
  (the release page's asset digest; the script refuses any other).
- `make DYNAMIC_ARCH=1 TARGET=PRESCOTT USE_OPENMP=1 NO_SHARED=1 NUM_THREADS=64
  NOFORTRAN=1 C_LAPACK=1 BUILD_TESTING=0 NO_AFFINITY=1 libs`, then the same
  with `netlib` (two runs: under one parallel make both targets append to the
  same archive at once, which fails on Windows), then
  `make ... PREFIX=<prefix> install`.
  - `USE_OPENMP=1`: OpenBLAS and the fill share one libgomp.
  - `NUM_THREADS=64`: the default is the build machine's core count.
  - `C_LAPACK=1 NOFORTRAN=1`: no Fortran runtime to link. `zgetrf` /
    `zgetrs` are OpenBLAS's own implementations either way.
  - `LAPACKE` is built (the default).
- Link: `g++ -static -fopenmp ... libopenblas.a -lm`, then `strip`.
- **A static-link trap, worked around in the dispatcher.** In a static
  executable OpenBLAS's constructor runs before libgomp's has read
  `OMP_NUM_THREADS`; OpenBLAS then records one OpenMP thread as its maximum
  and runs the LU serially (zgetrf on the whip deck: 4.7 s instead of 1.4 s
  at 4 threads, with nothing said). The dispatcher calls
  `openblas_set_num_threads()` before the engine runs, with
  `OPENBLAS_NUM_THREADS` if set, else `omp_get_max_threads()`.
- libgomp's offload-plugin loader links `dlopen`, so the link warns that a
  static `dlopen` needs the build's glibc at run time. No plugin is ever
  loaded (there are no offload targets), so it is never called.

```
docker run --rm -v "$PWD:/w" -w /w ubuntu:24.04 bash -c '
  apt-get update && apt-get install -y gcc-14 g++-14 make patch git python3
  git config --global --add safe.directory "*"
  git clone https://github.com/stevenmburns/necpp necpp-src
  git -C necpp-src checkout a08a0d980cf9d7e3c1b327675bf17713ab2ac241
  CC=gcc-14 CXX=g++-14 python3 scripts/build_cli.py --variant accel \
      --src necpp-src --out out --work work'
```

(`--variant reuse` with `62dacd44bc4d76c37e5164000d11ee1ac68c1a81`.)

## Windows: MSVC

As python-necpp's Windows wheels: MSVC with `/openmp /EHsc /bigobj
/FImsvc_compat.h` (`scripts/msvc/msvc_compat.h`), OpenBLAS from the
**scipy-openblas32 0.3.34.0.0** wheel (the one pynec-accel 1.7.6's Windows
wheels bundle; its symbols are `scipy_`-prefixed, so
`-DLAPACKE_zgetrf_work=scipy_LAPACKE_zgetrf_work` and the same for
`zgetrs`). `/MT` links the C runtime statically. From a VS x64 developer
prompt:

```
pip install scipy-openblas32==0.3.34.0.0
python scripts/build_cli.py --variant accel --src necpp-src --out out --work work
```

The zip ships `libscipy_openblas*.dll` and `vcomp140.dll` (the MSVC OpenMP
runtime has no static form) beside the `.exe`; `scripts/check_imports.py`
asserts that nothing else outside Windows itself is imported.

## 4nec2 (patch 0004)

4nec2 runs a NEC-2 engine installed as `nec2dxs500.exe`, `nec2dxs1K5.exe`,
`nec2dxs3k0.exe`, `nec2dxs5k0.exe`, `nec2dxs8k0.exe` or `nec2dxs11k.exe`
(picked from a size table), and hands it the file names without `-i`/`-o`.
When nec2++ is started **with no `-i`**, it takes the names from the first
of these that yields two:

1. exactly two positional arguments: `nec2++ in.nec out.out`;
2. the first two non-blank lines of stdin, when stdin is redirected (not a
   console / tty: `!isatty(0)` on Linux,
   `GetFileType(GetStdHandle(STD_INPUT_HANDLE)) != FILE_TYPE_CHAR` on
   Windows; `NUL` counts as a console). Redirected but empty, or no stdin
   handle at all (a GUI parent), falls through to 3;
3. the first two non-blank lines of `nec2d.tmp` in the **executable's own
   directory** (from `/proc/self/exe` / `GetModuleFileNameA`), which 4nec2
   writes before each run: CRLF lines of paths relative to that directory,
   e.g. `..\out\WHIP_ANT.inp`. A `nec2d.tmp` that is there but holds fewer
   than two names is an error.

Each name is trimmed of surrounding whitespace and CR/LF and of one pair of
surrounding double quotes. Relative names resolve against the current
directory; when they came from `nec2d.tmp` and the input is not found there,
both resolve against the executable's directory instead. The
wire-intersection check is off in this mode (as with `-n`). An explicit
`-o` still wins over the second name.

- `NECPP_VERBOSE=1` prints the source and the resolved paths on **stderr**.
  Nothing is written to stdout.
- Exit status 0 on success. A missing input prints
  `nec2++: input file not found: ...` (naming the source and the
  directories tried) on stderr and exits 2. Other errors keep their old
  status.
- With no arguments, a tty stdin and no `nec2d.tmp`, nec2++ prints its usage
  and exits non-zero, as before. Every flag behaves as before.
- `nec2d_names.cpp` is compiled **once**, at the baseline, outside both
  engine namespaces: its functions have C linkage (so `nec2cpp.cpp`'s calls
  from inside either namespace reach the one definition) and it includes
  `<windows.h>`, which must stay out of the namespace wrappers.
- Caveat: a host that redirects stdin to a pipe and never writes or closes
  it would block the read in step 2. No evidence that 4nec2 does that (the
  shim this replaces read stdin under the same rule).

`scripts/smoke/check_nec2d.py --exe <nec2++>` copies the exe, with any DLLs
beside it, into a 4nec2-like layout (`exe/nec2dxs1K5.exe`, `out/*.inp` with
CRLF) and runs it with each source: arguments, redirected stdin (quoted,
padded, CRLF names; beating a stale `nec2d.tmp`), and `nec2d.tmp` with a
console stdin (a pty on Linux, `NUL` on Windows), with an empty redirected
stdin, and from the exe's directory. Each printout must be byte-identical to
the same exe's `-n -i -o` printout apart from the timing lines (`FILL=`
/ `FACTOR:` msec and the run time), stdout must be empty, and the status 0.
`cross.nec` (two wires crossing mid-segment) is in the set because the
intersection check refuses it, so it passing shows the check is off. It also
checks the missing-input errors (all three sources), `NECPP_VERBOSE`, the
no-source usage error and `-n -i -o` under the `nec2dxs` name. CI runs it on
every build.

**The zips ship one exe and `install-4nec2.cmd`**, not six copies. A static
exe is ~25 MB (two engine copies plus a DYNAMIC_ARCH OpenBLAS), ~7 MB
compressed, and zip compresses each member separately, so six copies would
make the download ~40 MB for six identical files. `install-4nec2.cmd
[C:\4nec2\exe]` backs up any existing `nec2dxs*.exe` into
`nec2dxs-backup-<date>\` and copies the exe (and, for MSVC, its DLLs) under
the six names; the README says the same for anyone copying by hand.

## Windows: MinGW-w64, one static file

`--toolchain mingw` (the default in an MSYS2 **MINGW64** shell) builds one
self-contained `.exe` that imports only `KERNEL32.dll` and `msvcrt.dll`: the
shape of Ward's NEC5CL build (m90; measured on its stand-in `NEC5CL_m85.exe`,
whose `dumpbin /dependents` lists just those two, 14.2 MB). Not every NEC5CL build is like that: `NEC5CL_a51.exe` also imports
`libiomp5md.dll` (Intel OpenMP) and `imagehlp.dll`. MINGW64's runtime is the system `msvcrt.dll`
(not the UCRT), present on every Windows since XP.

- Toolchain: MSYS2 MINGW64 `mingw-w64-x86_64-gcc` (on GitHub's
  `windows-latest` via `msys2/setup-msys2`). Same compile flags as Linux
  (`-O3 -fno-strict-overflow -mtune=generic -fopenmp`, baseline
  `-march=x86-64`, avx2 copy `-march=x86-64-v3`), same dispatcher.
- **`-Wa,-muse-unaligned-vector-move`**: the Win64 ABI only aligns the stack
  to 16 bytes, but GCC spills 256-bit AVX values with aligned moves assuming
  32 (GCC PR 54412), which faults at random. binutils >= 2.38 assembles every
  aligned vector move as its unaligned form, which costs nothing on aligned
  data.
- OpenBLAS: the **same pinned 0.3.34 tarball and flags as Linux**
  (`DYNAMIC_ARCH=1 USE_OPENMP=1 NO_SHARED=1 NUM_THREADS=64 NOFORTRAN=1
  C_LAPACK=1 ...`), built in MSYS2 by the script, not MSYS2's
  `mingw-w64-x86_64-openblas`: that package is built with a Fortran LAPACK
  (it would drag libgfortran / libquadmath into the static link) and to its
  own threading choice and version, where this keeps one OpenBLAS
  configuration across the Linux and MinGW builds. CI caches it.
- Link: `g++ -static -static-libgcc -static-libstdc++ -fopenmp ...
  libopenblas.a -lm`, then `strip`: libgomp, winpthreads, libstdc++ and
  libgcc are all inside the exe. The dispatcher's `openblas_set_num_threads`
  work-around (see Linux) applies here too.
- **Imports gate** (hard failure in CI):
  `scripts/check_imports.py out --only kernel32.dll,msvcrt.dll --win7` reads
  the import table with `objdump -p`, fails on any other DLL, on any DLL in
  the output folder, and on any KERNEL32 function Windows 7 lacks
  (`GetSystemTimePreciseAsFileTime`, `WaitOnAddress`, ...).
- Licences: the zip adds winpthreads' licence (MIT-style; it asks for its
  notice in binary copies) and the mingw-w64 CRT's where MSYS2 ships one.
  libgcc / libstdc++ / libgomp are under the GCC Runtime Library Exception.

The CI job `compare-windows` downloads the MSVC and MinGW zips of each
variant onto one runner and runs `scripts/smoke/compare_exes.py`: the smoke
decks plus necpp's `testharness/data/*.nec` through both exes, once per
engine copy, comparing every input impedance to the printed digits (the
smoke gate's tolerance: one unit in the fifth figure) and each printout
apart from timing lines. It then times a synthetic 4,333-segment
whip-over-grid deck (`scripts/smoke/make_grid_deck.py`; W8IO's whip is not
ours to commit), indicative only.

## Smoke test

`scripts/smoke/check.py --exe <nec2++> [--engine baseline|avx2|auto] [--pynec]`
runs `dipole.nec` and `yagi3-ground.nec` (a GN 2, five-frequency Yagi) and
compares the input impedances to `references.json` to the printed digits;
`--pynec` also compares with the installed PyNEC (CI: pynec-accel 1.7.6
for `accel`, 1.7.7 with `PYNEC_FILL_REUSE=1` for `reuse`).

## Releases

`workflow_dispatch` uploads workflow artifacts only. A `cli-v*` tag push
creates a **draft** release only when the repository variable
`CLI_RELEASE_ENABLED` is `true`.
