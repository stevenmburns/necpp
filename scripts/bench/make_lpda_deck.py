#!/usr/bin/env python3
"""Write a LogYag-like timing deck: a log-periodic dipole array with a
transmission-line feeder, many frequencies, a few hundred to ~1,400 segments.

  python3 make_lpda_deck.py [--elements 30] [--segs 45] [--freqs 65] > lpda.nec

It stands in for W8IO's LogYag220-520-15dbi (1,353 segments, 52 TL cards,
EK, 65 frequencies), which is not ours to commit: by default 30 dipoles of
45 segments (1,350), 29 TL cards joining the centres with phase reversal,
EK, FR 65 x 220-540 MHz, and one 37-point elevation cut per frequency.
Fill-pair reuse finds few repeats here (no two elements alike). Indicative
timing only; not a correctness reference.
"""

from __future__ import annotations

import argparse


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--elements", type=int, default=30)
    ap.add_argument("--segs", type=int, default=45, help="segments per element (odd)")
    ap.add_argument("--freqs", type=int, default=65)
    a = ap.parse_args()
    tau, l0, x = 0.95, 0.70, 0.0  # longest half-length 0.35 m (~210 MHz)
    lines = ["CM Synthetic LogYag-like timing deck: LPDA with a TL feeder", "CE"]
    seg = a.segs
    for k in range(a.elements):
        half = l0 / 2 * tau**k
        lines.append(f"GW {k + 1} {seg} {x:.6f} {-half:.6f} 0 {x:.6f} {half:.6f} 0 0.002")
        x += 2 * 0.16 * (2 * half)  # spacing 2 sigma L, sigma = 0.16
    lines.append("GE 0")
    lines.append("EK")
    mid = seg // 2 + 1
    for k in range(a.elements - 1):
        lines.append(f"TL {k + 1} {mid} {k + 2} {mid} -100 0 0 0 0 0")
    lines.append(f"EX 0 {a.elements} {mid} 0 1 0")
    step = (540.0 - 220.0) / max(1, a.freqs - 1)
    lines += [f"FR 0 {a.freqs} 0 0 220 {step:.4f}", "RP 0 37 1 1000 -90 0 5 0", "EN"]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
