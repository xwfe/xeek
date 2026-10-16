"""命令行：

    python3 -m kdbx_oracle summary 库.kdbx [--keyfile K] [--password-env 变量名 | --no-password]
    python3 -m kdbx_oracle diff A.kdbx B.kdbx [同上的密钥选项] [--b-keyfile K] [--b-password-env V]
                                [--ignore 模式 ...] [--reveal]

密码不从命令行参数传（会进 shell 历史和进程列表），只读环境变量或提示输入。
diff 有差异时退出码为 1，读取失败为 2。
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from .reader import KdbxError, read_kdbx
from .semantic import canonicalize, diff, summarize


def _credentials(path: str, keyfile: str | None, password_env: str | None, no_password: bool):
    password = None
    if not no_password:
        if password_env:
            if password_env not in os.environ:
                raise SystemExit(f"环境变量 {password_env} 没有设置")
            password = os.environ[password_env]
        else:
            password = getpass.getpass(f"{path} 的密码：")
    key_bytes = Path(keyfile).read_bytes() if keyfile else None
    return password, key_bytes


def _open(path: str, keyfile: str | None, password_env: str | None, no_password: bool):
    password, key_bytes = _credentials(path, keyfile, password_env, no_password)
    return read_kdbx(Path(path).read_bytes(), password=password, keyfile=key_bytes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kdbx_oracle")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_key_options(p: argparse.ArgumentParser, prefix: str = "") -> None:
        p.add_argument(f"--{prefix}keyfile")
        p.add_argument(f"--{prefix}password-env")
        p.add_argument(f"--{prefix}no-password", action="store_true")

    p_summary = sub.add_parser("summary", help="输出不含字段值的结构摘要（JSON）")
    p_summary.add_argument("database")
    add_key_options(p_summary)

    p_diff = sub.add_parser("diff", help="比较两个库的语义差异")
    p_diff.add_argument("a")
    p_diff.add_argument("b")
    add_key_options(p_diff)
    add_key_options(p_diff, "b-")
    p_diff.add_argument("--ignore", action="append", default=[], help="fnmatch 模式，可重复")
    p_diff.add_argument("--reveal", action="store_true", help="显示受保护值（只用于合成样本）")

    args = parser.parse_args(argv)
    try:
        if args.command == "summary":
            decoded = _open(args.database, args.keyfile, args.password_env, args.no_password)
            print(json.dumps(summarize(decoded), ensure_ascii=False, indent=2))
            return 0
        a = _open(args.a, args.keyfile, args.password_env, args.no_password)
        b = _open(
            args.b,
            args.b_keyfile or args.keyfile,
            args.b_password_env or args.password_env,
            args.b_no_password or args.no_password,
        )
    except KdbxError as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    differences = diff(canonicalize(a), canonicalize(b), ignore=args.ignore, reveal=args.reveal)
    for difference in differences:
        print(difference)
    return 1 if differences else 0


if __name__ == "__main__":
    sys.exit(main())
