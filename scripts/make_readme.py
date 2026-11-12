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
    ap.add_argument("--os", choices=["linux", "windows"], required=True)
    ap.add_argument("--necpp-commit", required=True)
    ap.add_argument("--cli-commit", required=True)
    ap.add_argument("--exe", type=Path, required=True)
    a = ap.parse_args()
    sha = hashlib.sha256(a.exe.read_bytes()).hexdigest()
    reuse = a.variant == "reuse"
    if a.os == "windows":
        runtime = ("Ships with libscipy_openblas*.dll (OpenBLAS, from the scipy-openblas32 wheel, as the\n"
                   "pynec-accel Windows wheels use) and vcomp140.dll (the MSVC OpenMP runtime) beside\n"
                   "the .exe; keep them in the same folder.")
    else:
        runtime = "A fully static executable: no shared libraries needed, any x86-64 Linux."
    if a.os == "windows":
        threads = ("  OMP_NUM_THREADS sets the fill's threads (vcomp140); OpenBLAS keeps its own\n"
                   "  thread pool, set by OPENBLAS_NUM_THREADS (it falls back to OMP_NUM_THREADS).")
    else:
        threads = ("  OMP_NUM_THREADS sets the fill's threads and OpenBLAS's (one shared libgomp);\n"
                   "  OPENBLAS_NUM_THREADS sets OpenBLAS's alone.")
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

Threads
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
{"  scipy-openblas32-LICENSE.txt  the scipy-openblas32 build of OpenBLAS (and its bundled runtimes)" + chr(10) + "  MSVC-redist-NOTICE.txt      vcomp140.dll and the other Microsoft runtime DLLs" if a.os == "windows" else ""}""")


if __name__ == "__main__":
    main()
