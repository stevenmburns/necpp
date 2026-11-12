#!/usr/bin/env python3
"""Windows: check that every .exe/.dll in DIR imports only system DLLs or a
DLL that ships in DIR. With --redist, a missing Microsoft redistributable DLL
(e.g. vcruntime140.dll needed by vcomp140.dll) is copied in from the Visual
Studio redist tree first. Needs dumpbin (a VS developer prompt).

  python check_imports.py DIR [--redist "%VCToolsRedistDir%"]
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


def deps(path: Path) -> list[str]:
    p = subprocess.run(["dumpbin", "/nologo", "/dependents", str(path)], capture_output=True, text=True, check=True)
    m = re.search(r"Image has the following dependencies:\s*\n(.*?)\n\s*\n", p.stdout, re.S)
    return [ln.strip() for ln in m.group(1).splitlines() if ln.strip()] if m else []


def is_system(name: str) -> bool:
    n = name.lower()
    return n in SYSTEM or n.startswith("api-ms-win-") or n.startswith("ext-ms-")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", type=Path)
    ap.add_argument("--redist", type=Path, default=None)
    a = ap.parse_args()
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
