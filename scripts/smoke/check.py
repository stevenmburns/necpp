#!/usr/bin/env python3
"""Smoke test for a built nec2++: run the decks here and compare the input
impedances with the stored references (references.json) to printed digits.

  python3 check.py --exe <nec2++> [--engine baseline|avx2|auto] [--pynec]
  python3 check.py --exe <nec2++> --write-references    (regenerate)

--pynec additionally runs each deck through the installed PyNEC
(pip install pynec-accel==1.7.6) and compares to that.

"Printed digits": nec2++ prints impedances as %.4E (five significant
figures). A value passes when it prints identically; one unit in the fifth
figure is reported but tolerated (the AVX2/FMA engine copy may land on the
other side of a rounding boundary), anything larger fails.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DECKS = ["dipole.nec", "yagi3-ground.nec"]
NUM = r"[-+]?\d\.\d{4}E[-+]\d\d"


def nec2_impedances(text: str) -> list[tuple[str, str]]:
    """(R, X) as printed, one per ANTENNA INPUT PARAMETERS block."""
    out = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "ANTENNA INPUT PARAMETERS" in line:
            for m in lines[i + 1 : i + 8]:
                f = re.findall(NUM, m)
                if len(f) >= 6 and m.split()[0].isdigit():
                    out.append((f[4], f[5]))  # V re, V im, I re, I im, R, X, ...
                    break
    return out


def run_exe(exe: str, deck: Path, engine: str | None) -> tuple[list[tuple[str, str]], str]:
    env = dict(os.environ)
    env["NECPP_ENGINE_VERBOSE"] = "1"
    if engine:
        env["NECPP_ENGINE"] = engine
    with tempfile.TemporaryDirectory() as td:
        o = Path(td) / "out.txt"
        p = subprocess.run([exe, "-n", "-i", str(deck), "-o", str(o)], env=env,
                           capture_output=True, text=True)
        if p.returncode != 0:
            sys.exit(f"{exe} failed on {deck.name} (exit {p.returncode}):\n{p.stdout}\n{p.stderr}")
        return nec2_impedances(o.read_text(errors="replace")), p.stderr.strip()


def pynec_impedances(deck: Path) -> list[complex]:
    """Drive PyNEC card by card (only the cards the smoke decks use)."""
    import PyNEC

    cards = [ln.split() for ln in deck.read_text().splitlines() if ln.strip()]
    c = PyNEC.nec_context()
    g = c.get_geometry()
    for k in cards:
        if k[0] == "GW":
            v = [float(x) for x in k[3:10]]
            g.wire(int(k[1]), int(k[2]), *v[:6], v[6], 1.0, 1.0)
    ge = next(k for k in cards if k[0] == "GE")
    c.geometry_complete(int(ge[1]) if len(ge) > 1 else 0)
    nfreq = 1
    for k in cards:
        f = k[1:] + ["0"] * 10
        if k[0] == "GN":
            c.gn_card(int(f[0]), int(f[1]), float(f[4]), float(f[5]), 0, 0, 0, 0)
        elif k[0] == "EX":
            c.ex_card(int(f[0]), int(f[1]), int(f[2]), int(f[3]), float(f[4]), float(f[5]), 0, 0, 0, 0)
        elif k[0] == "FR":
            nfreq = int(f[1])
            c.fr_card(int(f[0]), nfreq, float(f[4]), float(f[5]))
        elif k[0] == "RP":
            x = f[3].rjust(4, "0")
            c.rp_card(int(f[0]), int(f[1]), int(f[2]), int(x[0]), int(x[1]), int(x[2]), int(x[3]),
                      float(f[4]), float(f[5]), float(f[6]), float(f[7]), 0, 0)
    return [c.get_input_parameters(i).get_impedance()[0] for i in range(nfreq)]


def last_digit_units(a: str, b: str) -> float:
    """|a - b| in units of a's fifth significant figure."""
    ea = int(a[-3:])
    return abs(float(a) - float(b)) / 10.0 ** (ea - 4)


def compare(label: str, got: list[tuple[str, str]], ref: list[tuple[str, str]], who: str = "ref") -> bool:
    if len(got) != len(ref):
        print(f"FAIL {label}: {len(got)} impedances, reference has {len(ref)}")
        return False
    ok = True
    for i, (g, r) in enumerate(zip(got, ref)):
        units = max(last_digit_units(r[0], g[0]), last_digit_units(r[1], g[1]))
        rel = abs(complex(float(g[0]), float(g[1])) - complex(float(r[0]), float(r[1]))) / abs(
            complex(float(r[0]), float(r[1])))
        state = "same" if g == r else ("1 unit in the last digit" if units <= 1.0001 else "FAIL")
        ok &= state != "FAIL"
        print(f"  {label}[{i}] R={g[0]} X={g[1]}  {who} R={r[0]} X={r[1]}  |dZ|/|Z|={rel:.1e}  {state}")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--engine", choices=["auto", "baseline", "avx2"], default=None)
    ap.add_argument("--pynec", action="store_true")
    ap.add_argument("--write-references", action="store_true")
    a = ap.parse_args()
    refs_path = HERE / "references.json"
    if a.write_references:
        refs = {d: run_exe(a.exe, HERE / d, "baseline")[0] for d in DECKS}
        refs_path.write_text(json.dumps(refs, indent=1) + "\n")
        print(f"wrote {refs_path}")
        return
    refs = json.loads(refs_path.read_text())
    ok = True
    for d in DECKS:
        got, said = run_exe(a.exe, HERE / d, a.engine)
        print(f"{d}: {said}")
        ok &= compare(f"{d} vs reference", got, [tuple(r) for r in refs[d]])
        if not got:
            ok = False
        if a.pynec:
            pz = [(f"{z.real:.4E}", f"{z.imag:.4E}") for z in pynec_impedances(HERE / d)]
            ok &= compare(f"{d} vs PyNEC", got, pz, "PyNEC")
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
