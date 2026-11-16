#!/usr/bin/env python3
"""Hold a NEC-2D-layout nec2++ printout (4nec2 mode, or -d) to NEC-2D's text.

  python3 nec2d_format.py <nec2d printout> <normal printout>

The formats are those 4nec2 was observed to need (byte-checked against
NEC2/MP v1.50's printout by the Windows-builder session): the data-card echo,
the section titles, the FREQUENCY and NORMALIZATION FACTOR lines, the ANTENNA
INPUT PARAMETERS and RADIATION PATTERNS headers and rows, and the closing
RUN TIME line. Each numeric line is cut at NEC-2D's fixed column widths and
re-printed with NEC-2D's own format from the values read back; the line must
come out identical (so every field has the right width, precision and a
two-digit exponent). The impedances must round to the normal printout's.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from check import last_digit_units, nec2_impedances  # noqa: E402

TITLES = {
    "FREQUENCY": "                                 - - - - - - FREQUENCY - - - - - -",
    "STRUCTURE IMPEDANCE LOADING": "                               - - - STRUCTURE IMPEDANCE LOADING - - -",
    "ANTENNA ENVIRONMENT": "                                  - - - ANTENNA ENVIRONMENT - - -",
    "MATRIX TIMING": "                                - - - MATRIX TIMING - - -",
    "ANTENNA INPUT PARAMETERS": "                                          - - - ANTENNA INPUT PARAMETERS - - -",
    "CURRENTS AND LOCATION": "                             - - - CURRENTS AND LOCATION - - -",
    "POWER BUDGET": "                                        - - - POWER BUDGET - - -",
    "NORMALIZED GAIN": "                                     - - - - NORMALIZED GAIN - - - -",
    "RADIATION PATTERNS": "                                                - - - RADIATION PATTERNS - - -",
}
Z_HEAD = [
    "   TAG   SEG.    VOLTAGE (VOLTS)         CURRENT (AMPS)         IMPEDANCE (OHMS)        ADMITTANCE (MHOS)      POWER",
    "   NO.   NO.    REAL        IMAG.       REAL        IMAG.       REAL        IMAG.       REAL        IMAG.     (WATTS)",
]
P_HEAD = [
    "  - - ANGLES - -           - POWER GAINS -       - - - POLARIZATION - - -    - - - E(THETA) - - -    - - - E(PHI) - - -",
    "  THETA     PHI        VERT.   HOR.    TOTAL      AXIAL     TILT   SENSE     MAGNITUDE    PHASE      MAGNITUDE    PHASE ",
    " DEGREES  DEGREES       DB      DB      DB        RATIO     DEG.              VOLTS/M    DEGREES      VOLTS/M    DEGREES",
]
CARD_FMT = " ***** DATA CARD NO.%3d   %-2.2s%4d%6d%6d%6d" + "%13.5E" * 6
FREQ_FMT = "                                    FREQUENCY= %10.4E MHZ"
NORM_FMT = "                                      NORMALIZATION FACTOR =%9.2f DB"
Z_FMT = " %5d %5d" + "%12.5E" * 9
P_FMT = " %7.2f%9.2f   %8.2f%8.2f%8.2f%11.5f%9.2f  %-6.6s%15.5E%9.2f%15.5E%9.2f"
RUN_FMT = " RUN TIME = %9.3f"


def cut(line: str, widths: list[int]) -> list[str]:
    out, k = [], 0
    for w in widths:
        out.append(line[k : k + w])
        k += w
    return out


def check_file(nec2d: Path, normal: Path) -> list[str]:
    errs: list[str] = []
    text = nec2d.read_text(errors="replace")
    lines = text.splitlines()
    seen = {k: 0 for k in TITLES}
    n_card = n_freq = n_norm = n_z = n_p = 0
    z_vals: list[tuple[float, float]] = []

    def bad(i: int, why: str) -> None:
        if len(errs) < 20:
            errs.append(f"line {i + 1}: {why}: {lines[i]!r}")

    # nec2++'s own titles must be gone for every section NEC-2D names.
    for i, ln in enumerate(lines):
        for name in TITLES:
            if name in ln and "---" in ln and ln != TITLES[name]:
                bad(i, f"nec2++-style {name} title")
        if "DATA CARD N0." in ln:
            bad(i, "nec2++-style card echo")

    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln in TITLES.values():
            name = next(k for k, v in TITLES.items() if v == ln)
            seen[name] += 1
        if "DATA CARD NO." in ln:
            f = cut(ln, [20, 3, 3, 2, 4, 6, 6, 6] + [13] * 6)
            try:
                vals = (int(f[1]), f[3], int(f[4]), int(f[5]), int(f[6]), int(f[7]), *map(float, f[8:]))
                if CARD_FMT % vals != ln:
                    bad(i, "card echo not in NEC-2D format")
            except ValueError:
                bad(i, "card echo fields")
            n_card += 1
        elif "FREQUENCY=" in ln:
            try:
                if FREQ_FMT % float(ln.split("=")[1].split()[0]) != ln:
                    bad(i, "FREQUENCY line")
            except (ValueError, IndexError):
                bad(i, "FREQUENCY line")
            n_freq += 1
        elif ln.startswith("                                      NORMALIZATION FACTOR ="):
            if True:
                if NORM_FMT % float(ln.split("=")[1].split()[0]) != ln:
                    bad(i, "NORMALIZATION FACTOR line")
                n_norm += 1
        if ln == TITLES["ANTENNA INPUT PARAMETERS"]:
            if lines[i + 1 : i + 4] != ["", *Z_HEAD]:
                bad(i, "ANTENNA INPUT PARAMETERS header (blank line + 2 NEC-2D lines)")
            j = i + 4
            while j < len(lines) and re.match(r"^ [ \d]{5} [ \d]{5}[ -]\d", lines[j]):
                f = cut(lines[j], [6, 6] + [12] * 9)
                try:
                    v = (int(f[0]), int(f[1]), *map(float, f[2:]))
                    if Z_FMT % v != lines[j]:
                        bad(j, "impedance row not 2(1X,I5),9E12.5")
                    z_vals.append((v[6], v[7]))
                except ValueError:
                    bad(j, "impedance row fields")
                n_z += 1
                j += 1
            i = j
            continue
        if ln == TITLES["RADIATION PATTERNS"]:
            if lines[i - 1] != "":
                bad(i, "no blank line before the RADIATION PATTERNS title")
            j = i + 1
            while j < len(lines) and lines[j].lstrip().startswith(("RANGE", "EXP(-JKR)")):
                j += 1
            heads = (P_HEAD, [P_HEAD[0], P_HEAD[1].replace("VERT.", "MAJOR").replace("HOR. ", "MINOR"), P_HEAD[2]])
            if lines[j : j + 4] not in (["", *heads[0]], ["", *heads[1]]):
                bad(j, "RADIATION PATTERNS header (blank line + 3 NEC-2D lines)")
            j += 4
            while j < len(lines) and re.match(r"^ [ \d.-]{7}[ \d.-]{9}   ", lines[j]):
                f = cut(lines[j], [8, 9, 3, 8, 8, 8, 11, 9, 2, 6, 15, 9, 15, 9])
                try:
                    v = (float(f[0]), float(f[1]), float(f[3]), float(f[4]), float(f[5]), float(f[6]),
                         float(f[7]), f[9].strip(), float(f[10]), float(f[11]), float(f[12]), float(f[13]))
                    if P_FMT % v != lines[j]:
                        bad(j, "pattern row not NEC-2D's FORMAT")
                except ValueError:
                    bad(j, "pattern row fields")
                n_p += 1
                j += 1
            i = j
            continue
        i += 1

    # The closing line, exactly: "\n\n RUN TIME = %9.3f\n" at the very end.
    if not re.search(r"\n\n RUN TIME = [ \d]{4}\d\.\d{3}\n$", text):
        errs.append("the printout does not end in '\\n\\n RUN TIME = %9.3f\\n'")
    else:
        try:
            if RUN_FMT % float(lines[-1].split("=")[1]) != lines[-1]:
                errs.append("RUN TIME line format")
        except ValueError:
            errs.append("RUN TIME value")

    # The values: the impedances round to the normal printout's.
    ref = nec2_impedances(normal.read_text(errors="replace"))
    if len(ref) != len(z_vals):
        errs.append(f"{len(z_vals)} NEC-2D impedance rows, the normal printout has {len(ref)}")
    else:
        for (r, x), (rr, rx) in zip(z_vals, ref):
            u = max(last_digit_units(rr, f"{r:.4E}"), last_digit_units(rx, f"{x:.4E}"))
            if u > 1.0001:
                errs.append(f"impedance {r:.5E} {x:.5E} vs normal printout {rr} {rx}")

    if n_card == 0:
        errs.append("no data-card echo")
    if n_freq == 0 or seen["FREQUENCY"] == 0:
        errs.append("no NEC-2D FREQUENCY title / line")
    if n_z == 0:
        errs.append("no ANTENNA INPUT PARAMETERS rows")
    summary = (f"cards {n_card}, titles {sum(seen.values())} "
               f"({', '.join(f'{k} {v}' for k, v in seen.items() if v)}), FREQUENCY lines {n_freq}, "
               f"NORMALIZATION lines {n_norm}, impedance rows {n_z}, pattern rows {n_p}")
    print(f"    NEC-2D format of {nec2d.name}: {summary}")
    return errs


if __name__ == "__main__":
    e = check_file(Path(sys.argv[1]), Path(sys.argv[2]))
    print("\n".join(e) if e else "PASS")
    sys.exit(1 if e else 0)
