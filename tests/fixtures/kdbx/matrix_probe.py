#!/usr/bin/env python3
"""单独新进程测量合成命令/只读解锁；输出计数和资源，不输出明文。"""
from __future__ import annotations

import json
import resource
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent.parent / "kdbx_oracle")]
from kdbx_oracle import read_kdbx
import matrix_checks


def rss_bytes(who):
    value = resource.getrusage(who).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def main():
    request = json.load(sys.stdin)
    if request["mode"] == "cli":
        started = time.perf_counter()
        run = subprocess.run(request["argv"], input=request["stdin"], capture_output=True,
                             text=True, timeout=120)
        if run.returncode:
            raise RuntimeError("synthetic CLI failed; exit " + str(run.returncode))
        result = {"elapsed_seconds": time.perf_counter() - started,
                  "peak_rss_bytes": rss_bytes(resource.RUSAGE_CHILDREN)}
    else:
        raw = Path(request["file"]).read_bytes()
        started = time.perf_counter()
        decoded = read_kdbx(raw, password=request["password"])
        opened = time.perf_counter() - started
        open_rss = rss_bytes(resource.RUSAGE_SELF)
        started = time.perf_counter()
        results = matrix_checks.domain_results(decoded)
        checked = time.perf_counter() - started
        result = {"open_seconds": opened, "open_peak_rss_bytes": open_rss,
                  "contract_seconds": checked, "combined_peak_rss_bytes": rss_bytes(resource.RUSAGE_SELF),
                  "entries": len(results), "statuses": dict(Counter(r.status for r in results))}
    print(json.dumps(result))


if __name__ == "__main__":
    main()

