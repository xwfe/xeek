#!/usr/bin/env python3
"""只用标准库运行可移植基线；不安装工具或验证生产能力。"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CHECKS = (
    ("设计与主任务", ("adr/design/verify.py",)),
    ("移动专项文档", ("adr/design/verify_ios.py",)),
    ("个人保险柜计划", ("adr/verify_personal_vault.py",)),
    ("合成领域契约", ("-m", "unittest", "discover",
                    "-s", "tests/vault_domain", "-p", "test_contract.py")),
)


def main() -> int:
    if sys.version_info < (3, 12):
        print("需要 Python 3.12+。", file=sys.stderr)
        return 2
    for label, arguments in CHECKS:
        print(f"检查：{label}", flush=True)
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-B", *arguments], cwd=ROOT,
        )
        if result.returncode:
            return result.returncode
    print("4 组基线检查通过；不代表生产或平台能力验收。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
