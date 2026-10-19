"""Git pre-commit 入口；读取 Git 为这次提交准备的完整 index。"""
from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE_NAMES = ("commit_hook.py", "backend.py", "gate.py", "snapshot.py", "requirements.lock")


def check_sources(view):
    from backend import ScanFailure
    for name in SOURCE_NAMES:
        path = "tests/secret_scan/" + name
        # 复用逐级拒绝符号链接的读取；这里只比对执行链，不要求 policy 工作树一致。
        if view.read(path) != view._worktree_read(path):
            raise ScanFailure("HOOK_SOURCE_MISMATCH")


def main():
    result = {"status": "error", "scope": "index", "code": "HOOK_SCAN_FAILED"}
    code = 2
    try:
        # 导入失败也不能打印本机路径或第三方原始异常。
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            sys.path.insert(0, str(HERE))
            from backend import ScanFailure
            from gate import inspect
            from snapshot import Snapshot
            try:
                view = Snapshot(ROOT, "index")
                check_sources(view)
                result = inspect(view)
                check_sources(view)
                view.finish()
                code = 0 if result["status"] == "pass" else 1
            except ScanFailure as exc:
                result = {"status": "error", "scope": "index", "code": exc.code}
    except (Exception, KeyboardInterrupt, SystemExit):
        result = {"status": "error", "scope": "index", "code": "HOOK_SCAN_FAILED"}
        code = 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
