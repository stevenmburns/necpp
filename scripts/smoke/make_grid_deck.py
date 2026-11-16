#!/usr/bin/env python3
"""Write a large timing deck: a UHF whip over a square wire-grid ground plane.

  python3 make_grid_deck.py [--cells 46] > grid-whip.nec

It stands in for W8IO's ELT whip benchmark (4,392 segments, 13 frequencies,
an elevation cut), which is not ours to commit: by default 4,324 grid
segments + 9 whip segments, free space, FR 13 x 400-412 MHz, and a 2-degree
elevation cut. The grid's wires cross at segment ends, so most segments
repeat geometrically (fill-pair reuse applies, as on the whip). Indicative
timing only; not a correctness reference.
"""

from __future__ import annotations

import argparse


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", type=int, default=46, help="grid cells per side (even)")
    ap.add_argument("--size", type=float, default=0.60, help="grid side, m")
    a = ap.parse_args()
    n, half = a.cells, a.size / 2
    if n % 2:
        raise SystemExit("--cells must be even (the whip stands on the centre node)")
    lines = [f"CM Synthetic timing deck: whip over a {n}x{n}-cell wire grid "
             f"({2 * n * (n + 1) + 9} segments)", "CE"]
    tag = 1
    r = 0.0005
    for i in range(n + 1):
        c = -half + a.size * i / n
        lines.append(f"GW {tag} {n} {-half:.6f} {c:.6f} 0 {half:.6f} {c:.6f} 0 {r}")
        tag += 1
        lines.append(f"GW {tag} {n} {c:.6f} {-half:.6f} 0 {c:.6f} {half:.6f} 0 {r}")
        tag += 1
    whip = tag
    lines.append(f"GW {whip} 9 0 0 0 0 0 0.18 {r}")
    lines += ["GE 0", f"EX 0 {whip} 1 0 1 0", "FR 0 13 0 0 400 1",
              "RP 0 91 1 1000 0 0 2 0", "EN"]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
