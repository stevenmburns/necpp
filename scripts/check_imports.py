#!/usr/bin/env python3
"""Windows: check that every .exe/.dll in DIR imports only system DLLs or a
DLL that ships in DIR. With --redist, a missing Microsoft redistributable DLL
(e.g. vcruntime140.dll needed by vcomp140.dll) is copied in from the Visual
Studio redist tree first. Needs dumpbin (a VS developer prompt).

  python check_imports.py DIR [--redist "%VCToolsRedistDir%"]

--only LIST (the static MinGW build) is stricter: every .exe in DIR may
import nothing but the comma-separated DLLs in LIST, no .dll may ship beside
it, and with --win7 none of the KERNEL32 functions that Windows 7 lacks may
be imported. Reads the import table with objdump -p (binutils) when dumpbin
is not on PATH.

  python check_imports.py DIR --only kernel32.dll,msvcrt.dll --win7
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

SYSTEM = {
    "kernel32.dll", "user32.dll", "advapi32.dll", "ntdll.dll", "msvcrt.dll", "ws2_32.dll",
    "shell32.dll", "ole32.dll", "oleaut32.dll", "bcrypt.dll", "gdi32.dll", "ucrtbase.dll",
    "kernelbase.dll", "psapi.dll", "dbghelp.dll", "version.dll", "winmm.dll",
}


# KERNEL32 exports that Windows 7 does not have (added in 8 / 8.1 / 10), as
# a MinGW runtime or OpenBLAS might reach for them. Importing one makes the
# exe refuse to start on Windows 7 ("entry point not found").
NOT_ON_WIN7 = {
    "GetSystemTimePreciseAsFileTime", "CreateFile2", "GetCurrentThreadStackLimits",
    "SetThreadDescription", "GetThreadDescription", "SetThreadInformation", "GetThreadInformation",
    "PrefetchVirtualMemory", "WaitOnAddress", "WakeByAddressSingle", "WakeByAddressAll",
    "InitializeSynchronizationBarrier", "EnterSynchronizationBarrier", "DeleteSynchronizationBarrier",
    "GetSystemCpuSetInformation", "GetProcessDefaultCpuSets", "SetThreadSelectedCpuSets",
    "CreateFileMappingFromApp", "MapViewOfFileFromApp", "VirtualAllocFromApp", "GetPackageFamilyName",
    "GetOverlappedResultEx", "GetFileInformationByName", "SetProcessDefaultCpuSets",
}


def objdump_imports(path: Path) -> dict[str, list[str]]:
    """{dll: [function, ...]} from objdump -p's import tables."""
    p = subprocess.run(["objdump", "-p", str(path)], capture_output=True, text=True, check=True)
    out: dict[str, list[str]] = {}
    cur = None
    for ln in p.stdout.splitlines():
        m = re.match(r"\s*DLL Name:\s*(\S+)", ln)
        if m:
            cur = m.group(1)
            out[cur] = []
            continue
        if cur is None:
            continue
        m = re.match(r"\s*[0-9a-fA-F]+\s+(?:<none>\s+)?[0-9a-fA-F]+\s+(\w+)\s*$", ln)
        if m:
            out[cur].append(m.group(1))
        elif not ln.strip():
            cur = None if out.get(cur) else cur
    return out


def deps(path: Path) -> list[str]:
    if not shutil.which("dumpbin"):
        return list(objdump_imports(path))
    p = subprocess.run(["dumpbin", "/nologo", "/dependents", str(path)], capture_output=True, text=True, check=True)
    m = re.search(r"Image has the following dependencies:\s*\n(.*?)\n\s*\n", p.stdout, re.S)
    return [ln.strip() for ln in m.group(1).splitlines() if ln.strip()] if m else []


def strict(d: Path, allowed: set[str], win7: bool) -> None:
    exes = sorted(p for p in d.iterdir() if p.suffix.lower() == ".exe")
    dlls = sorted(p.name for p in d.iterdir() if p.suffix.lower() == ".dll")
    if not exes:
        sys.exit(f"FAIL: no .exe in {d}")
    bad = []
    if dlls:
        bad.append(f"DLLs ship beside the exe: {dlls}")
    for e in exes:
        imps = objdump_imports(e)
        print(f"{e.name}: {e.stat().st_size} bytes; imports {', '.join(imps)}")
        for dll, funcs in imps.items():
            print(f"  {dll}: {len(funcs)} functions")
            if dll.lower() not in allowed:
                bad.append(f"{e.name} imports {dll}")
            if win7 and dll.lower() == "kernel32.dll":
                late = sorted(set(funcs) & NOT_ON_WIN7)
                if late:
                    bad.append(f"{e.name} imports KERNEL32 functions Windows 7 lacks: {late}")
        if not imps:
            bad.append(f"{e.name}: no import table read (objdump output not understood)")
    if bad:
        sys.exit("FAIL:\n  " + "\n  ".join(bad))
    print(f"OK: only {sorted(allowed)}" + (", nothing Windows 7 lacks" if win7 else ""))


def is_system(name: str) -> bool:
    n = name.lower()
    return n in SYSTEM or n.startswith("api-ms-win-") or n.startswith("ext-ms-")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", type=Path)
    ap.add_argument("--redist", type=Path, default=None)
    ap.add_argument("--only", default=None, help="comma-separated: the only DLLs an .exe may import")
    ap.add_argument("--win7", action="store_true", help="with --only: refuse KERNEL32 functions Windows 7 lacks")
    a = ap.parse_args()
    if a.only:
        strict(a.dir, {x.strip().lower() for x in a.only.split(",") if x.strip()}, a.win7)
        return
    for _ in range(3):
        files = sorted(p for p in a.dir.iterdir() if p.suffix.lower() in (".exe", ".dll"))
        shipped = {p.name.lower() for p in files}
        missing: set[str] = set()
        for f in files:
            d = deps(f)
            print(f"{f.name}: {', '.join(d)}")
            missing |= {x for x in d if not is_system(x) and x.lower() not in shipped}
        if not missing:
            print("OK: only system DLLs and DLLs shipped beside the exe")
            return
        if not a.redist:
            sys.exit(f"FAIL: non-system DLLs not shipped: {sorted(missing)}")
        for m in sorted(missing):
            cands = [p for p in a.redist.rglob(m) if "x64" in str(p).lower() and "onecore" not in str(p).lower()
                     and "debug" not in str(p).lower()]
            if not cands:
                sys.exit(f"FAIL: {m} is neither system nor found in {a.redist}")
            shutil.copy2(cands[0], a.dir / cands[0].name)
            print(f"copied {cands[0]}")
    sys.exit("FAIL: dependency closure did not settle")


if __name__ == "__main__":
    main()
