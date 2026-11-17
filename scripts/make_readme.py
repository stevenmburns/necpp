#!/usr/bin/env python3
"""Write the README.txt that goes into a nec2++ command-line zip."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

REPO = "https://github.com/stevenmburns/necpp"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["accel", "reuse"], required=True)
    ap.add_argument("--os", choices=["linux", "windows", "windows-mingw"], required=True)
    ap.add_argument("--necpp-commit", required=True)
    ap.add_argument("--cli-commit", required=True)
    ap.add_argument("--exe", type=Path, required=True)
    a = ap.parse_args()
    sha = hashlib.sha256(a.exe.read_bytes()).hexdigest()
    reuse = a.variant == "reuse"
    win = a.os.startswith("windows")
    if a.os == "windows-mingw":
        runtime = ("One self-contained .exe (MinGW-w64 GCC, MSYS2 MINGW64, everything static): it\n"
                   "  imports only KERNEL32.dll and msvcrt.dll, both part of Windows since Windows 7 or\n"
                   "  earlier, and nothing else needs to sit beside it (the same shape as Ward's\n"
                   "  NEC5CL build: m85, the stand-in for m90, imports only those two).")
    elif a.os == "windows":
        runtime = ("Ships with libscipy_openblas*.dll (OpenBLAS, from the scipy-openblas32 wheel, as the\n"
                   "pynec-accel Windows wheels use) and vcomp140.dll (the MSVC OpenMP runtime) beside\n"
                   "the .exe; keep them in the same folder.")
    else:
        runtime = "A fully static executable: no shared libraries needed, any x86-64 Linux."
    if a.os == "windows-mingw":
        threads = ("  OMP_NUM_THREADS sets the fill's threads and OpenBLAS's (one static libgomp);\n"
                   "  OPENBLAS_NUM_THREADS sets OpenBLAS's alone.")
    elif a.os == "windows":
        threads = ("  OMP_NUM_THREADS sets the fill's threads (vcomp140); OpenBLAS keeps its own\n"
                   "  thread pool, set by OPENBLAS_NUM_THREADS (it falls back to OMP_NUM_THREADS).")
    else:
        threads = ("  OMP_NUM_THREADS sets the fill's threads and OpenBLAS's (one shared libgomp);\n"
                   "  OPENBLAS_NUM_THREADS sets OpenBLAS's alone.")
    exe = a.exe.name
    if win:
        this_build = ("MSVC: the exe plus libscipy_openblas.dll and vcomp140.dll."
                      if a.os == "windows" else
                      "MinGW: one self-contained exe, nothing else needed.")
        guide = f"""
1. USING NEC2++ WITH 4NEC2
--------------------------
What it is
  nec2++ is a NEC-2 engine whose matrix fill runs on all your CPU cores and
  whose matrix solve uses OpenBLAS. It installs under 4nec2's own engine names
  (nec2dxs500.exe ... nec2dxs11k.exe), so 4nec2 runs it with no extra program
  in between, and 4nec2's pattern, SWR and run-time displays work as usual.

Which Windows build
  There are two zips:
    MSVC   ...-windows-x86_64.zip        exe + libscipy_openblas.dll + vcomp140.dll.
                                         Usually the faster one.
    MinGW  ...-windows-mingw-x86_64.zip  a single self-contained exe.
                                         Slower on some decks.
  Choose MSVC for speed, MinGW if you want just one file.
  This zip: {this_build}

Install
  1. Close 4nec2. Unzip this folder anywhere.
  2. Open a Command Prompt in the unzipped folder and run
       install-4nec2.cmd C:\\4nec2\\exe
     (use your own 4nec2 exe folder if it is somewhere else).
  It first copies 4nec2's existing engines (every nec2dxs*.exe in that
  folder) into a new folder beside them, C:\\4nec2\\exe\\nec2dxs-backup-<date>\\,
  then installs nec2++ under all six engine names.{" It also copies its two" + chr(10) + "  DLLs into C:\\4nec2\\exe, next to 4nec2.exe. They do no harm if you later" + chr(10) + "  switch to the other build or back to 4nec2's own engine." if a.os == "windows" else ""}
  3. Start 4nec2 and run a model as usual.

Going back
  Copy the files from C:\\4nec2\\exe\\nec2dxs-backup-<date>\\ back into
  C:\\4nec2\\exe, replacing the nec2dxs*.exe there.

Threads
  By default nec2++ uses one thread per physical CPU core. To choose another
  number, set OMP_NUM_THREADS (and, if you like, OPENBLAS_NUM_THREADS for the
  solve) in the Command Prompt you start 4nec2 from, e.g.
    set OMP_NUM_THREADS=4
    C:\\4nec2\\exe\\4nec2.exe

2. BENCHMARKING AGAINST NEC2/MP (OR 4NEC2'S OWN ENGINE)
-------------------------------------------------------
  The decks and the method are W8IO's: https://www.w8io.com/nec-benchmarks.htm
  In 4nec2: Calculate -> NEC Output Data -> Use Original File -> Generate,
  then read the total calculation time.

  - Run the same deck with each engine, at 4nec2's default settings.
    Nothing tuned.
  - Use Original File, so the deck's own frequency and pattern settings are
    used and 4nec2 does not rewrite the deck.
  - The time 4nec2 shows comes from the "RUN TIME =" line at the end of the
    output (F8).
  - Take the best of 3 runs. Expect about 10-15 % spread from run to run.
  - Set the Windows power mode to "Best performance" first. On our test it
    changed NEC2/MP's time by about 30 %.
  - No affinity or priority settings are needed. (If you want to experiment:
    the engine inherits 4nec2's CPU affinity, so starting 4nec2 with
    "start /affinity ..." limits the engine too.)

  Benchmark 1, LPDA: LogYag220-520-15dbi.nec
  1353 segments, 65 steps 200-520 MHz, azimuth plot at 2 degrees

  | NEC Engine | Operating System | CPU | Calculation Time |
  |---|---|---|---|
  | NEC2/MP v. 1.50, by Athan Papadimitriou | Windows 11 Pro 26H2 (build 26300), 64 bit | Dell XPS 9320, Intel Core i5-1240P @1.7 GHz (4.4 GHz turbo), 12 cores (4P+8E), 16 threads, 16 GB RAM | TBD seconds |
  | nec2++ accel + fill reuse, cli-v1.1.0 (MSVC build), based on NEC2++ by Tim Molteno | Windows 11 Pro 26H2 (build 26300), 64 bit | Dell XPS 9320, Intel Core i5-1240P @1.7 GHz (4.4 GHz turbo), 12 cores (4P+8E), 16 threads, 16 GB RAM | TBD seconds |

  Benchmark 2, the whip on a ground plane: whip_antenna_8ft_groundplane.nec
  4392 segments, 13 steps 400-412 MHz, elevation plot at 2 degrees

  | NEC Engine | Operating System | CPU | Calculation Time |
  |---|---|---|---|
  | NEC2/MP v. 1.50, by Athan Papadimitriou | Windows 11 Pro 26H2 (build 26300), 64 bit | Dell XPS 9320, Intel Core i5-1240P @1.7 GHz (4.4 GHz turbo), 12 cores (4P+8E), 16 threads, 16 GB RAM | TBD seconds |
  | nec2++ accel + fill reuse, cli-v1.1.0 (MSVC build), based on NEC2++ by Tim Molteno | Windows 11 Pro 26H2 (build 26300), 64 bit | Dell XPS 9320, Intel Core i5-1240P @1.7 GHz (4.4 GHz turbo), 12 cores (4P+8E), 16 threads, 16 GB RAM | TBD seconds |

  4NEC2 defaults; Windows power mode: Best performance.

"""
        fournec2 = """
4nec2 file names
  Started with no -i, nec2++ takes the input and output names from two
  arguments, else two lines on stdin, else nec2d.tmp beside the exe, and
  prints in NEC-2D's layout (also with -d). NECPP_VERBOSE=1 shows on stderr
  where the names came from. See BUILD-CLI.md in the source for details.
"""
    else:
        guide = ""
        fournec2 = f"""
4nec2 / nec2dxs file names
  Started with no -i, nec2++ takes the names as 4nec2 hands them to a
  nec2dxs engine: two arguments ({exe} in.nec out.out); else two lines on
  stdin if stdin is redirected; else the two lines of nec2d.tmp in the exe's
  own directory. The wire-intersection check is off in that mode, as with -n.
  NECPP_VERBOSE=1 reports the source and the resolved names on stderr.
"""
    print(f"""nec2++ command line, necpp fork "{a.variant}" engine ({a.os} x86-64)
=====================================================================

  {a.exe.name}
  sha256 {sha}
{guide}
What it is
  NEC2++ (GPL-2.0-or-later, Timothy C.A. Molteno and contributors) from the
  fork {REPO}, built with the same engine configuration as the pynec-accel
  Python wheel: the matrix fill parallelised with OpenMP and the LU solve
  through LAPACKE (zgetrf/zgetrs) in OpenBLAS.
  {"Fill-pair reuse is ON by default in this build (PYNEC_FILL_REUSE=0 turns it off)." if reuse else ""}

Source
  necpp commit  {REPO}/tree/{a.necpp_commit}
  build scripts {REPO}/tree/{a.cli_commit}  (branch cli-build: BUILD-CLI.md, scripts/)
  The executable is that necpp commit plus the patch(es) in scripts/patches/
  of the build-scripts commit, built with scripts/build_cli.py.

Usage
  {a.exe.name} -n -i deck.nec -o deck.out
  -n skips nec2++'s wire-intersection check, which NEC-2 does not make (the
  pynec-accel wheel's set_intersection_check(False)). -h lists the options.
{fournec2}
Threads
  By default one thread per physical core that the process may run on (its
  affinity mask: start /affinity, taskset), for the fill and the LU alike.
{threads}

CPU dispatch
  The engine is in the executable twice: compiled for the x86-64 baseline and
  for x86-64-v3 (AVX2 + FMA). It picks the second when the CPU has it.
  NECPP_ENGINE=baseline forces the baseline copy; NECPP_ENGINE_VERBOSE=1 says
  which one ran. The two agree to the printed digits; the AVX2/FMA copy can
  differ in the last bits.

Runtime
  {runtime}

Licences
  COPYING-necpp-GPL-2.0.txt   NEC2++ (GPL-2.0-or-later)
  OpenBLAS-LICENSE.txt        OpenBLAS (BSD-3-Clause) with GotoBLAS2 and LAPACK notices
{"  scipy-openblas32-LICENSE.txt  the scipy-openblas32 build of OpenBLAS (and its bundled runtimes)" + chr(10) + "  MSVC-redist-NOTICE.txt      vcomp140.dll and the other Microsoft runtime DLLs" if a.os == "windows" else ""}{"  winpthreads-LICENSE.txt     MinGW-w64 winpthreads, linked in statically" + chr(10) + "  mingw-w64-crt-LICENSE.txt   the MinGW-w64 C runtime start-up code (if present)" + chr(10) + "  libgcc, libstdc++ and libgomp are linked in under the GCC Runtime Library Exception." if a.os == "windows-mingw" else ""}""")


if __name__ == "__main__":
    main()
