#!/usr/bin/env python3
"""Test nec2++'s 4nec2 / nec2dxs file-name conventions (patch 0004).

  python3 check_nec2d.py --exe <nec2++>

The executable is copied, with any DLLs beside it, into a scratch layout like
a 4nec2 install,

    <tmp>/exe/nec2dxs1K5[.exe]   (+ nec2d.tmp, as 4nec2 writes it)
    <tmp>/out/<deck>.inp

and run with the names from each source: two positional arguments, stdin
(redirected), and nec2d.tmp beside the executable (stdin a console / tty:
a pty on Linux, NUL on Windows; and stdin redirected but empty, which falls
through to nec2d.tmp). Each printout must be byte-identical to the one the
same executable writes with `-n -i <deck> -o <out>`, apart from the timing
lines; nothing may reach stdout; exit status 0. Error cases: a missing input
exits non-zero with a message on stderr, and NECPP_VERBOSE=1 names the source.

The decks are the smoke decks plus cross.nec, whose two wires cross at their
middles: nec2++'s intersection check refuses it, so it passing in every mode
shows the check is off there, as with -n.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DECKS = ["dipole.nec", "yagi3-ground.nec", "cross.nec"]
WIN = os.name == "nt"
EXT = ".exe" if WIN else ""
SEP = "\\" if WIN else "/"
# Lines that carry a measured time (nec2++ prints elapsed / CPU times).
TIMING = re.compile(r"TIME|SECONDS|\bSEC\b|ELAPSED", re.I)

failures: list[str] = []


def check(cond: bool, what: str) -> None:
    print(("  ok    " if cond else "  FAIL  ") + what)
    if not cond:
        failures.append(what)


def strip_timing(text: bytes) -> list[bytes]:
    return [ln for ln in text.splitlines() if not TIMING.search(ln.decode("latin-1"))]


def run(exe: Path, args: list[str], cwd: Path, stdin=subprocess.DEVNULL, data: bytes | None = None,
        env_extra: dict | None = None, use_pty: bool = False) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("NECPP_VERBOSE", None)
    env.update(env_extra or {})
    if use_pty:
        import pty

        master, slave = pty.openpty()
        try:
            return subprocess.run([str(exe), *args], cwd=cwd, stdin=slave, capture_output=True,
                                  env=env, timeout=600)
        finally:
            os.close(slave)
            os.close(master)
    if data is not None:
        return subprocess.run([str(exe), *args], cwd=cwd, input=data, capture_output=True, env=env, timeout=600)
    return subprocess.run([str(exe), *args], cwd=cwd, stdin=stdin, capture_output=True, env=env, timeout=600)


def same_printout(got: Path, ref: Path, label: str) -> None:
    if not got.exists():
        check(False, f"{label}: {got.name} was written")
        return
    g, r = strip_timing(got.read_bytes()), strip_timing(ref.read_bytes())
    n_time = len(ref.read_bytes().splitlines()) - len(r)
    check(g == r and len(r) > 20,
          f"{label}: printout byte-identical to the -n -i -o run ({len(r)} lines, {n_time} timing lines skipped)")


def quiet_ok(p: subprocess.CompletedProcess, label: str) -> None:
    check(p.returncode == 0, f"{label}: exit 0 (got {p.returncode}; stderr {p.stderr.decode(errors='replace')!r})")
    check(p.stdout == b"", f"{label}: nothing on stdout (got {p.stdout[:200]!r})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True, type=Path)
    ap.add_argument("--name", default="nec2dxs1K5", help="the nec2dxs name to install the copy as")
    a = ap.parse_args()
    src_exe = a.exe.resolve()

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        exedir, outdir, other = root / "exe", root / "out", root / "elsewhere"
        for d in (exedir, outdir, other):
            d.mkdir()
        exe = exedir / f"{a.name}{EXT}"
        shutil.copy2(src_exe, exe)
        for dll in src_exe.parent.glob("*.dll"):
            shutil.copy2(dll, exedir / dll.name)
        tmpfile = exedir / "nec2d.tmp"

        for deck in DECKS:
            stem = Path(deck).stem.upper()
            # 4nec2 writes .inp decks with CRLF line ends.
            inp = outdir / f"{stem}.inp"
            inp.write_bytes(b"\r\n".join((HERE / deck).read_bytes().splitlines()) + b"\r\n")
            print(f"{deck} -> {inp.name}")

            ref = outdir / f"{stem}-ref.out"
            p = run(src_exe, ["-n", "-i", str(inp), "-o", str(ref)], cwd=root)
            check(p.returncode == 0 and ref.exists(), f"reference -n -i -o run (exit {p.returncode})")
            if deck == "cross.nec":
                q = run(src_exe, ["-i", str(inp), "-o", str(outdir / "check-on.out")], cwd=root)
                check(q.returncode != 0, f"cross.nec is refused WITH the intersection check (exit {q.returncode})")

            # 1. two positional arguments (relative to the cwd); a stale
            #    nec2d.tmp and redirected stdin must not win over them.
            tmpfile.write_bytes(b"..\\out\\NOPE.inp\r\n..\\out\\NOPE.out\r\n")
            o = outdir / f"{stem}-args.out"
            p = run(exe, [inp.name, o.name], cwd=outdir, data=b"WRONG.inp\nWRONG.out\n")
            quiet_ok(p, "args")
            same_printout(o, ref, "args")

            # 2. stdin, redirected: quotes, surrounding blanks, CRLF, a blank
            #    first line; beats the stale nec2d.tmp.
            o = outdir / f"{stem}-stdin.out"
            data = f'\r\n  "{inp.name}"  \r\n\t{o.name} \r\n'.encode()
            p = run(exe, [], cwd=outdir, data=data)
            quiet_ok(p, "stdin")
            same_printout(o, ref, "stdin")

            # 3. nec2d.tmp beside the exe, names relative to the exe's
            #    directory, run from a different cwd.
            o = outdir / f"{stem}-tmp.out"
            tmpfile.write_bytes(f'..{SEP}out{SEP}{inp.name}\r\n"..{SEP}out{SEP}{o.name}"\r\n'.encode())
            if WIN:
                # NUL is a character device, as a console is: not "redirected".
                p = run(exe, [], cwd=other, stdin=subprocess.DEVNULL)
                quiet_ok(p, "nec2d.tmp (stdin NUL = console)")
            else:
                p = run(exe, [], cwd=other, use_pty=True)
                quiet_ok(p, "nec2d.tmp (stdin a tty)")
            same_printout(o, ref, "nec2d.tmp")

            # 3b. stdin redirected but empty: falls through to nec2d.tmp.
            o.unlink(missing_ok=True)
            p = run(exe, [], cwd=other, data=b"")
            quiet_ok(p, "nec2d.tmp (stdin redirected, empty)")
            same_printout(o, ref, "nec2d.tmp, empty stdin")

            # 3c. cwd = the exe's directory: the names resolve directly.
            o.unlink(missing_ok=True)
            p = run(exe, [], cwd=exedir, stdin=subprocess.DEVNULL)
            quiet_ok(p, "nec2d.tmp (cwd = exe dir)")
            same_printout(o, ref, "nec2d.tmp, cwd = exe dir")
            tmpfile.unlink()

        # Error and reporting cases.
        print("errors and reporting")
        tmpfile.write_bytes(b"..\\out\\MISSING.inp\r\n..\\out\\MISSING.out\r\n" if WIN
                            else b"../out/MISSING.inp\r\n../out/MISSING.out\r\n")
        p = run(exe, [], cwd=other, stdin=subprocess.DEVNULL)
        err = p.stderr.decode(errors="replace")
        check(p.returncode != 0, f"missing input (nec2d.tmp): non-zero exit (got {p.returncode})")
        check("not found" in err and "MISSING.inp" in err, f"missing input: stderr names it ({err.strip()!r})")
        check(p.stdout == b"", "missing input: nothing on stdout")
        tmpfile.unlink()

        p = run(exe, ["NOSUCH.inp", "NOSUCH.out"], cwd=outdir)
        check(p.returncode != 0 and b"NOSUCH.inp" in p.stderr, f"missing input (args): non-zero exit ({p.returncode})")

        p = run(exe, [], cwd=outdir, data=b"NOSUCH.inp\r\nNOSUCH.out\r\n")
        check(p.returncode != 0 and b"NOSUCH.inp" in p.stderr, f"missing input (stdin): non-zero exit ({p.returncode})")

        inp = outdir / "DIPOLE.inp"
        p = run(exe, [inp.name, "v.out"], cwd=outdir, env_extra={"NECPP_VERBOSE": "1"})
        err = p.stderr.decode(errors="replace")
        check(p.returncode == 0 and "the command line" in err and "DIPOLE.inp" in err,
              f"NECPP_VERBOSE=1 reports source and names on stderr ({err.strip()!r})")
        check(p.stdout == b"", "NECPP_VERBOSE=1: still nothing on stdout")

        # Existing behaviour: no arguments and no source -> usage, non-zero.
        if not WIN:
            p = run(exe, [], cwd=other, use_pty=True)
            check(p.returncode != 0 and b"usage" in p.stderr,
                  f"no arguments, tty stdin, no nec2d.tmp: usage and non-zero exit ({p.returncode})")
        # -i/-o still work under the nec2dxs name.
        o = outdir / "DIPOLE-i.out"
        p = run(exe, ["-n", "-i", inp.name, "-o", o.name], cwd=outdir, data=b"WRONG\nWRONG\n")
        quiet_ok(p, "-n -i -o under the nec2dxs name")
        same_printout(o, outdir / "DIPOLE-ref.out", "-n -i -o under the nec2dxs name")

    print(f"{'FAIL' if failures else 'PASS'}: {len(failures)} failure(s)")
    for f in failures:
        print("  " + f)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
