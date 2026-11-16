#!/usr/bin/env python3
"""Run the same decks through two nec2++ executables and compare them.

  python3 compare_exes.py --a <exe> --a-label MSVC --b <exe> --b-label MinGW \\
      --decks DIR_OR_FILE [...] [--engine baseline|avx2|auto] [--timeout S]

Each deck runs as `exe -n -i deck -o out`. Compared, per deck: every input
impedance (R, X as printed, %.4E: five significant figures), and the whole
printout apart from timing lines. An impedance pair is "same" when it prints
identically, "1 unit" when it differs by one unit in the fifth figure (the
tolerance of the existing Windows / dispatch smoke gate, check.py), and a
FAILURE otherwise. A deck that fails in both executables the same way (the
deck itself is refused) is counted as skipped; failing in only one is a
FAILURE.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from check import last_digit_units, nec2_impedances  # noqa: E402

TIMING = re.compile(r"TIME|SECONDS|\bSEC\b|ELAPSED", re.I)


def run(exe: str, deck: Path, out: Path, engine: str | None, timeout: float) -> tuple[int | str, str]:
    env = dict(os.environ)
    if engine:
        env["NECPP_ENGINE"] = engine
    try:
        p = subprocess.run([exe, "-n", "-i", str(deck), "-o", str(out)], env=env, capture_output=True,
                           timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return "timeout", ""
    return p.returncode, (p.stderr + p.stdout).decode(errors="replace").strip()[-300:]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--a-label", default="A")
    ap.add_argument("--b", required=True)
    ap.add_argument("--b-label", default="B")
    ap.add_argument("--decks", nargs="+", type=Path, required=True)
    ap.add_argument("--engine", default=None)
    ap.add_argument("--timeout", type=float, default=300)
    a = ap.parse_args()

    decks: list[Path] = []
    for d in a.decks:
        decks += sorted(d.glob("*.nec")) if d.is_dir() else [d]

    n = {"decks": 0, "skipped": 0, "z": 0, "same": 0, "unit": 0, "fail": 0, "identical": 0}
    fails: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        for deck in decks:
            oa, ob = Path(td) / "a.out", Path(td) / "b.out"
            for o in (oa, ob):
                o.unlink(missing_ok=True)
            ra, ea = run(a.a, deck, oa, a.engine, a.timeout)
            rb, eb = run(a.b, deck, ob, a.engine, a.timeout)
            if ra != 0 or rb != 0:
                if ra == rb:
                    n["skipped"] += 1
                    print(f"skip {deck.name}: both exit {ra} ({ea.splitlines()[-1] if ea else ''})")
                else:
                    fails.append(f"{deck.name}: {a.a_label} exit {ra}, {a.b_label} exit {rb}")
                    print(f"FAIL {deck.name}: {a.a_label} exit {ra} {ea!r}; {a.b_label} exit {rb} {eb!r}")
                continue
            n["decks"] += 1
            ta = oa.read_text(errors="replace")
            tb = ob.read_text(errors="replace")
            za, zb = nec2_impedances(ta), nec2_impedances(tb)
            if len(za) != len(zb):
                fails.append(f"{deck.name}: {len(za)} vs {len(zb)} impedances")
                continue
            worst = 0.0
            for x, y in zip(za, zb):
                n["z"] += 1
                u = max(last_digit_units(x[0], y[0]), last_digit_units(x[1], y[1]))
                worst = max(worst, u)
                if x == y:
                    n["same"] += 1
                elif u <= 1.0001:
                    n["unit"] += 1
                else:
                    n["fail"] += 1
                    fails.append(f"{deck.name}: Z {x} vs {y} ({u:.1f} units)")
            la = [ln for ln in ta.splitlines() if not TIMING.search(ln)]
            lb = [ln for ln in tb.splitlines() if not TIMING.search(ln)]
            ident = la == lb
            n["identical"] += ident
            ndiff = sum(1 for x, y in zip(la, lb) if x != y) + abs(len(la) - len(lb))
            print(f"{deck.name}: {len(za)} impedances, worst {worst:.1f} units; printout "
                  + ("identical" if ident else f"{ndiff} of {len(la)} lines differ"))

    print(f"\n{a.a_label} vs {a.b_label}" + (f" (NECPP_ENGINE={a.engine})" if a.engine else "") + ":")
    print(f"  decks compared {n['decks']}, skipped (refused by both) {n['skipped']}")
    print(f"  impedances {n['z']}: same {n['same']}, 1 unit in the 5th figure {n['unit']}, worse {n['fail']}")
    print(f"  printouts identical apart from timing lines: {n['identical']} of {n['decks']}")
    if fails:
        print("FAIL:\n  " + "\n  ".join(fails))
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
