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
  as 4nec2's `nec2dxs*.exe` with no shim, and the NEC-2D printout layout
  4nec2 reads. See "4nec2" below. Adds `src/nec2d_names.{h,cpp}` (also
  listed in `src/Makefile.am`, so a plain autotools build gets it too) and
  `src/nec2d_layout.h`, a call from `nec_main`, a new `-d` flag, and
  `if (nec2d_layout)` branches at the printout sites. Without `-d`, and
  with `-i` given, the printout is byte-identical to before.

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
  at 4 threads, with nothing said). The dispatcher therefore always calls
  `openblas_set_num_threads()` before the engine runs (see "Thread counts").
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

## Thread counts (every build, every mode)

The dispatcher sets both pools before the engine runs. Default: **one
thread per physical core in the process's affinity mask**
(`GetProcessAffinityMask` + `GetLogicalProcessorInformationEx` on Windows,
`sched_getaffinity` + `thread_siblings_list` on Linux), for the OpenMP fill
and the OpenBLAS LU alike, as momwire's standalone launchers count them
(momwire#1952). `OMP_NUM_THREADS` still sets the fill, and
`OPENBLAS_NUM_THREADS` the LU (else `OMP_NUM_THREADS`).
`NECPP_ENGINE_VERBOSE=1` reports the counts and where they came from.

**The MSVC build's OpenBLAS DLL** (`libscipy_openblas.dll`) starts its own
thread pool when it is loaded, sized from `OPENBLAS_NUM_THREADS` or else
every CPU in the machine; it ignores the affinity mask, and
`openblas_set_num_threads()` afterwards only lowers the count it uses (the
pool stays). Observed: 22 threads under `start /affinity 55` on the 16-thread
box, against 5 for the MinGW build. So the MSVC link delay-loads the DLL
(`/DELAYLOAD`, `delayimp.lib`) and the dispatcher, before its first call
into it, puts `OPENBLAS_NUM_THREADS=<count>` into the OS environment, its
own CRT's, and the already-loaded shared CRTs' (`ucrtbase.dll`,
`msvcrt.dll`), each of which keeps its own copy. An `OPENBLAS_NUM_THREADS`
the user set is left alone. `scripts/smoke/check_threads.py` (CI, both
Windows builds) starts the exe suspended, applies masks 0x1, 0x5 and all
CPUs, and counts its threads by start module in toolhelp snapshots while it
solves: the reported counts must equal the physical cores in the mask, the
threads that are ours (not ntdll's loader / thread-pool workers) must stay
within main + (n-1) OpenMP + (n-1) OpenBLAS (MSVC) + 1, and the MSVC
OpenBLAS pool within n-1.

Why: 4nec2 under a 4-CPU mask (0x55) with no thread variables started 36
threads and ran past 204 s on the whip deck; with the variables at 4 it took
23-27 s. The OpenMP and OpenBLAS defaults count every CPU in the machine,
not the mask. The default also drops SMT siblings, so on an SMT machine with
no variables set the count halves from before (Haswell: 8 -> 4); a few
decks' last printed digits move with the thread count (the fill's parallel
sums), exactly as they do when `OMP_NUM_THREADS` is changed by hand.

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
  it would block the read in step 2. 4nec2 does not: observed, it redirects
  stdin from a FILE (`FILE_TYPE_DISK`) holding the same two CRLF lines as
  `nec2d.tmp`, runs the bare exe name with no arguments, from cwd
  `C:\4nec2\exe`, and needs no side files. Whether it checks the exit
  status is not known (every observed run exited 0).

### The NEC-2D printout layout (4nec2 mode, or `-d`)

4nec2 reads the engine's printout by NEC-2D's exact text, and refuses or
misreads nec2++'s own layout. Observed with 4nec2 itself (Windows-builder,
with Steve at the GUI), bisected where noted:

- **The closing RUN TIME line is required**: without it every run is
  rejected ("NEC error ? Check output (F8)"). `"\n\n RUN TIME = %9.3f\n"`,
  wall seconds, at the very end of the file; nec2++'s own
  `TOTAL RUN TIME: ... msec` (kept, just before it) is not recognised.
- **The data-card echo is required** for both the pattern and the SWR plot:
  `" ***** DATA CARD NO.%3d   %-2.2s%4d%6d%6d%6d"` + 6 x `"%13.5E"`.
- **The ANTENNA INPUT PARAMETERS body** is read in fixed columns (else
  "terrible SWR everywhere"): a blank line after the title, NEC-2D's two
  header lines, rows `" %5d %5d"` + 9 x `"%12.5E"` (the columns run
  together).
- **RADIATION PATTERNS**: NEC-2D's title (after a blank line), a blank
  line, its three header lines (`VERT.`/`HOR.` or `MAJOR`/`MINOR` by the RP
  card's X digit), rows
  `FORMAT(1X,F7.2,F9.2,3X,3F8.2,F11.5,F9.2,2X,A6,2(E15.5,F9.2))`, the sense
  blank where nec2++ has none.
- Not bisected, emitted as the shim did: NEC-2D's section titles for
  FREQUENCY, STRUCTURE IMPEDANCE LOADING, ANTENNA ENVIRONMENT, MATRIX
  TIMING, CURRENTS AND LOCATION, POWER BUDGET and NORMALIZED GAIN;
  `"FREQUENCY= %10.4E MHZ"` (36 leading blanks); `"NORMALIZATION FACTOR
  =%9.2f DB"`.
- **Short-segment warnings**: one summary line per run
  (`WARNING- n SEGMENTS SHORTER THAN 0.02 WAVELENGTHS AT f MHZ ...`) in
  place of one per segment per frequency (51 x 36 = 1,836 lines on a sane
  inverted V). They were shown not to cause the rejection; it is noise.

Everything is printed **from the values**, not re-parsed from nec2++'s
text (as the shim had to), so the NEC-2D fields carry their full precision.
Still in nec2++'s layout, and not exercised by any 4nec2 view so far: the
currents, segmentation and structure tables, the normalized-gain table body
(nec2++ prints one point per row, NEC-2D three), the near-ground field
table, and the RANGE lines of a pattern at a finite range.

Exponents: every build prints two exponent digits (`E+02`), as NEC-2D
does. MSVC's UCRT and glibc do by default; MinGW's msvcrt `printf` would
print three (`E+002`), so the MinGW build compiles with
`-D__USE_MINGW_ANSI_STDIO=1` (MinGW-w64's own C99 printf).

The mode is a global flag (`nec2d_layout`, `src/nec2d_layout.h`, defined
in `nec_output.cpp`) set by the 4nec2 file-name mode or by `-d`; each
printout site that differs has an `if (nec2d_layout)` branch, and
`nec2d_title()` maps nec2++'s section names to NEC-2D's title lines. In the
dispatch build each engine copy has its own flag, set by its own `nec_main`.

`scripts/smoke/check_nec2d.py --exe <nec2++>` copies the exe, with any DLLs
beside it, into a 4nec2-like layout (`exe/nec2dxs1K5.exe`, `out/*.inp` with
CRLF) and runs it with each source: arguments, redirected stdin (quoted,
padded, CRLF names; beating a stale `nec2d.tmp`), and `nec2d.tmp` with a
console stdin (a pty on Linux, `NUL` on Windows), with an empty redirected
stdin, and from the exe's directory. Each printout must be byte-identical to
the same exe's `-n -d -i -o` printout apart from the timing lines (`FILL=`
/ `FACTOR:` msec and the run times), stdout must be empty, and the status 0.
The 4nec2-mode printout is held line by line to NEC-2D's text by
`scripts/smoke/nec2d_format.py`: each card echo, FREQUENCY, NORMALIZATION,
impedance and pattern line is cut at NEC-2D's column widths and re-printed
with NEC-2D's format from the values read back, and must come out
identical; the headers and titles must match exactly, nec2++'s own titles
must be gone, the file must end in the RUN TIME line, and the impedances
must round to the plain printout's. The plain `-n -i -o` printout must keep
nec2++'s layout. A fourth deck, the dipole with a normalized pattern
(`RP ... 1500`), covers NORMALIZED GAIN. The thread defaults are checked
too: counts from the mask with no variables, the variables overriding, and
(Linux) one thread each under a one-CPU mask.
`cross.nec` (two wires crossing mid-segment) is in the set because the
intersection check refuses it, so it passing shows the check is off. It also
checks the missing-input errors (all three sources), `NECPP_VERBOSE`, the
no-source usage error and `-n -i -o` under the `nec2dxs` name. CI runs it on
every build.

**The zips ship one exe and `install-4nec2.cmd`**, not six copies. The
static exes are ~22 MB each (MinGW 22.3 MB, Linux 24.8 MB: two engine
copies plus a DYNAMIC_ARCH OpenBLAS), ~6-7 MB compressed, and zip
compresses each member separately, so six copies would make a ~35-40 MB
download of identical files. (The MSVC exe alone is ~1 MB, because its
OpenBLAS is the 20 MB `libscipy_openblas.dll` beside it.)
`install-4nec2.cmd [C:\4nec2\exe]` backs up any existing `nec2dxs*.exe`
into `nec2dxs-backup-<date>\` and copies the exe (and, for MSVC, its DLLs)
under the six names; the README says the same for anyone copying by hand.

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

First results (run 43951234587, `windows-latest`, 4 vCPUs = 2 cores):
impedances agree on every deck in both engine copies (63/63 accel, 64/64
reuse, one of them a zero), but **the MinGW exe is slower where the fill
dominates**: plain fill 1.5-1.75x MSVC's wall time (accel 124 vs 70 s at the
default 2 threads, 85-94 vs 56 s at 4), while with fill-pair reuse on, which
removes most of the fill, they are within 10 % (24 vs 22.5 s; 20.7 vs 19.6 s).
The LU is the same OpenBLAS 0.3.34 in both, so the gap is in the fill,
most likely MinGW-w64's libm (`sin`/`cos`/`exp`, the fill's inner work),
which is slower than MSVC's CRT. Not yet measured apart.

`testharness/sommerfield1.nec` crashes both Windows builds (access
violation, 0xC0000005) but runs on Linux. Its `LD 5 1 1 41` loads segments
1-41 of a 17-segment wire; an out-of-range write that Linux happens to
survive is the likely cause (not confirmed). The compare job counts it as
refused by both.

## The README in each zip

`scripts/make_readme.py` writes each zip's `README.txt`. The Windows ones
open with two sections written for 4nec2 users, not developers: **using
nec2++ with 4nec2** (what it is, MSVC vs MinGW, `install-4nec2.cmd`, what it
backs up and how to go back, threads) and **benchmarking against NEC2/MP**
(default settings, the deck's own sweep, the `RUN TIME =` line, best of 3,
"Best performance" power mode, and W8IO-format results tables for his two decks). A note to
users can say "follow the README".

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
