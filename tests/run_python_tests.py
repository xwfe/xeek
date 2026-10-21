"""用项目内固定测试依赖运行 oracle / 领域回归，不改变全局 Python 包。"""
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE / "kdbx_oracle" / ".deps-argon2"))
sys.path.insert(0, str(HERE / "kdbx_oracle"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("oracle", "domain", "all"), default="all")
    parser.add_argument("--pattern", default="test_*.py")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    try:
        import argon2.low_level  # noqa: F401
    except ImportError:
        parser.error("缺少 argon2-cffi 测试依赖；安装步骤见 tests/kdbx_oracle/README.md")
    roots = {"oracle": HERE / "kdbx_oracle" / "tests", "domain": HERE / "vault_domain"}
    suites = [
        unittest.TestLoader().discover(str(path), pattern=args.pattern)
        for name, path in roots.items() if args.suite in (name, "all")
    ]
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(unittest.TestSuite(suites))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
