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
        fournec2 = f"""
4nec2
  This exe can stand in for 4nec2's NEC-2 engine directly, with no shim. 4nec2
  runs one of nec2dxs500.exe, nec2dxs1K5.exe, nec2dxs3k0.exe, nec2dxs5k0.exe,
  nec2dxs8k0.exe and nec2dxs11k.exe (by deck size) from its exe folder, so
  install a copy under each name:

    install-4nec2.cmd C:\\4nec2\\exe

  backs up any existing nec2dxs*.exe to <folder>\\nec2dxs-backup-<date>\\ and
  copies {exe}{" and the DLLs beside it" if a.os == "windows" else ""} there under the six names.
  Copies rather than one file: the zip stays one exe instead of six identical
  ones. The names are what matter; the exe does not care which it runs as.

  Started with no -i, nec2++ takes the input and output names from, in order:
  two arguments ({exe} in.nec out.out); else two lines on stdin if stdin
  is redirected; else the two lines of nec2d.tmp in the exe's own folder,
  which 4nec2 writes before each run (paths relative to that folder). Names
  are trimmed of blanks, CR/LF and surrounding double quotes. The
  wire-intersection check is off in that mode, as with -n, and the printout
  is in NEC-2D's layout (the card echo, section titles, input-parameter and
  radiation-pattern tables, and the closing RUN TIME line 4nec2 needs);
  -d gives the same layout from the command line. NECPP_VERBOSE=1 prints, on
  stderr only, which source was used and the resolved names. Exit status 0
  on success; a missing input prints a message on stderr and exits non-zero.
"""
    else:
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
