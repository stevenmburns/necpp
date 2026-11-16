#!/usr/bin/env python3
"""Sum nec2++'s per-frequency MATRIX TIMING (FILL= / FACTOR: msec) over a printout.

  python3 fill_factor.py <printout> [label]

Prints one line: frequencies, fill s, factor s, and the run's TOTAL RUN TIME.
The msec values are nec2++'s secnds(): process CPU time (user+system, all
threads) on Linux, clock() on Windows (wall time for both MSVC's UCRT and
MinGW's msvcrt), so compare Windows builds with Windows builds.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(errors="replace")
label = sys.argv[2] if len(sys.argv) > 2 else Path(sys.argv[1]).name
ff = re.findall(r"FILL=\s*(-?\d+) msec\s+FACTOR:\s*(-?\d+) msec", text)
fill = sum(int(a) for a, _ in ff) / 1000.0
factor = sum(int(b) for _, b in ff) / 1000.0
m = re.search(r"TOTAL RUN TIME:\s*(\d+) msec", text)
total = int(m.group(1)) / 1000.0 if m else float("nan")
print(f"FILLFACTOR {label}: frequencies {len(ff)}  fill {fill:8.2f} s  factor {factor:8.2f} s  "
      f"total {total:8.2f} s  other {total - fill - factor:8.2f} s")
