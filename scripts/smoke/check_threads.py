#!/usr/bin/env python3
"""Windows: run nec2++ under a restricted affinity mask with no thread
variables and count the threads its pools actually start.

  python check_threads.py --exe <nec2++.exe> [--mask 0x1] [--mask 0x5] ...

The exe is started suspended, given the mask (as `start /affinity` would),
and resumed. While it solves a medium deck, a toolhelp snapshot is taken
every 20 ms; each thread is attributed to the module its start address lies
in (NtQueryInformationThread ThreadQuerySetWin32StartAddress), and the
threads that start in ntdll.dll (the loader's and the OS thread pool's
workers, not ours) are left out. With n = physical cores the mask reaches
(counted here independently, from GetLogicalProcessorInformation):

  - NECPP_ENGINE_VERBOSE's reported counts equal n;
  - at every snapshot, our threads <= 1 (main) + (n - 1) OpenMP workers
    + (n - 1) for OpenBLAS's own pool in the MSVC build (its DLL keeps
    one; the MinGW build's OpenBLAS runs on the OpenMP pool) + 1 spare;
  - the MSVC build's OpenBLAS pool (threads starting in its DLL) <= n - 1.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll")
psapi = ctypes.WinDLL("psapi")

TH32CS_SNAPTHREAD = 0x4
CREATE_SUSPENDED = 0x4
THREAD_QUERY_INFORMATION = 0x40
PROCESS_QUERY_INFORMATION, PROCESS_VM_READ = 0x400, 0x10


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD), ("tpBasePri", wintypes.LONG),
                ("tpDeltaPri", wintypes.LONG), ("dwFlags", wintypes.DWORD)]


class MODULEINFO(ctypes.Structure):
    _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", wintypes.DWORD), ("EntryPoint", ctypes.c_void_p)]


k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.OpenThread.restype = wintypes.HANDLE
k32.OpenProcess.restype = wintypes.HANDLE


def physical_cores(mask: int) -> int:
    """Cores (RelationProcessorCore entries) whose processor mask meets `mask`."""
    class SLPI(ctypes.Structure):  # SYSTEM_LOGICAL_PROCESSOR_INFORMATION, 32 bytes on x64
        _fields_ = [("ProcessorMask", ctypes.c_size_t), ("Relationship", wintypes.DWORD),
                    ("_pad", wintypes.DWORD), ("u", ctypes.c_ulonglong * 2)]
    n = wintypes.DWORD(0)
    k32.GetLogicalProcessorInformation(None, ctypes.byref(n))
    buf = (SLPI * (n.value // ctypes.sizeof(SLPI)))()
    if not k32.GetLogicalProcessorInformation(buf, ctypes.byref(n)):
        raise OSError(ctypes.get_last_error())
    return sum(1 for e in buf if e.Relationship == 0 and (e.ProcessorMask & mask))


def modules(hproc) -> list[tuple[str, int, int]]:
    arr = (ctypes.c_void_p * 1024)()
    need = wintypes.DWORD()
    if not psapi.EnumProcessModulesEx(hproc, arr, ctypes.sizeof(arr), ctypes.byref(need), 3):
        return []
    out = []
    for h in arr[: need.value // ctypes.sizeof(ctypes.c_void_p)]:
        name = ctypes.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(hproc, ctypes.c_void_p(h), name, 260)
        mi = MODULEINFO()
        psapi.GetModuleInformation(hproc, ctypes.c_void_p(h), ctypes.byref(mi), ctypes.sizeof(mi))
        out.append((name.value.lower(), mi.lpBaseOfDll or 0, mi.SizeOfImage))
    return out


def thread_starts(pid: int) -> dict[int, int]:
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = THREADENTRY32()
    te.dwSize = ctypes.sizeof(te)
    out = {}
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            h = k32.OpenThread(THREAD_QUERY_INFORMATION, False, te.th32ThreadID)
            addr = ctypes.c_void_p()
            if h:
                ntdll.NtQueryInformationThread(wintypes.HANDLE(h), 9, ctypes.byref(addr), ctypes.sizeof(addr), None)
                k32.CloseHandle(wintypes.HANDLE(h))
            out[te.th32ThreadID] = addr.value or 0
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(wintypes.HANDLE(snap))
    return out


def run_masked(exe: Path, mask: int, deck: Path) -> tuple[dict[str, int], int, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")}
    env["NECPP_ENGINE_VERBOSE"] = "1"
    with tempfile.TemporaryDirectory() as td:
        p = subprocess.Popen([str(exe), "-n", "-i", str(deck), "-o", str(Path(td) / "o.out")], env=env,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             creationflags=CREATE_SUSPENDED)
        h = wintypes.HANDLE(int(p._handle))
        if not k32.SetProcessAffinityMask(h, ctypes.c_size_t(mask)):
            raise OSError(ctypes.get_last_error())
        ntdll.NtResumeProcess(h)
        hq = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, p.pid)
        peak: dict[str, int] = {}
        peak_total = 0
        peak_ours = 0
        while p.poll() is None:
            starts = thread_starts(p.pid)
            mods = modules(hq)
            count: dict[str, int] = {}
            for a in starts.values():
                m = next((n for n, b, sz in mods if b <= a < b + sz), "?")
                count[m] = count.get(m, 0) + 1
            for m, c in count.items():
                peak[m] = max(peak.get(m, 0), c)
            peak_total = max(peak_total, len(starts))
            peak_ours = max(peak_ours, len(starts) - count.get("ntdll.dll", 0))
            time.sleep(0.02)
        err = p.stderr.read().decode(errors="replace")
        if p.returncode != 0:
            raise SystemExit(f"{exe.name} exited {p.returncode}: {err}")
        k32.CloseHandle(wintypes.HANDLE(hq))
        return peak, peak_total, peak_ours, err


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", type=Path, required=True)
    ap.add_argument("--mask", action="append", default=None)
    a = ap.parse_args()
    exe = a.exe.resolve()
    with tempfile.TemporaryDirectory() as td:
        deck = Path(td) / "grid.nec"
        deck.write_text(subprocess.run([sys.executable, str(HERE / "make_grid_deck.py"), "--cells", "24"],
                                       capture_output=True, text=True, check=True).stdout)
        n_cpu = os.cpu_count() or 1
        masks = [int(m, 0) for m in (a.mask or ["0x1", "0x5", hex((1 << n_cpu) - 1)])]
        fails = []
        for mask in masks:
            mask &= (1 << n_cpu) - 1
            if not mask:
                continue
            n = physical_cores(mask)
            peak, total, ours, err = run_masked(exe, mask, deck)
            line = next((ln for ln in err.splitlines() if "threads:" in ln), "")
            msvc_build = (exe.parent / "vcomp140.dll").exists()
            blas = sum(c for m, c in peak.items() if m.startswith("libscipy_openblas"))
            budget = 1 + (n - 1) + ((n - 1) if msvc_build else 0) + 1
            print(f"mask {mask:#x}: {n} physical core(s); peak threads {total}, ours {ours} "
                  f"(budget {budget}); peak by start module {peak}")
            print(f"  {line.strip()}")
            if f"fill {n} (physical cores in the mask), LU {n} (physical cores in the mask)" not in line:
                fails.append(f"mask {mask:#x}: reported counts are not {n}/{n}: {line!r}")
            if ours > budget:
                fails.append(f"mask {mask:#x}: {ours} threads > budget {budget}")
            if blas > max(0, n - 1):
                fails.append(f"mask {mask:#x}: {blas} OpenBLAS pool threads > {n - 1}")
        print("PASS" if not fails else "FAIL:\n  " + "\n  ".join(fails))
        sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
