"""本地提交前门禁。默认扫描完整 Git index；--worktree 检查当前工作树。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from backend import ScanFailure, silence
from gate import inspect
from snapshot import Snapshot


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ScanFailure("USAGE")


def main(argv=None):
    scope = "index"
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument("--worktree", action="store_true")
        parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
        args = parser.parse_args(argv)
        scope = "worktree" if args.worktree else "index"
        with silence():
            result = inspect(Snapshot(args.root, scope))
        code = 0 if result["status"] == "pass" else 1
    except ScanFailure as exc:
        result, code = {"status": "error", "scope": scope, "code": exc.code}, 2
    except (Exception, KeyboardInterrupt):
        result, code = {"status": "error", "scope": scope, "code": "SCAN_FAILED"}, 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
