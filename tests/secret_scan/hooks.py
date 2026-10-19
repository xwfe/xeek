"""显式安装、检查或撤销本仓库的 pre-commit；不修改 Git 配置。"""
from __future__ import annotations

import argparse
import ast
import contextlib
import json
import os
import shlex
import stat
import subprocess
import sys
import uuid
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
HOOK = "pre-commit"
MAX_HOOK = 16 * 1024


class HookFailure(Exception):
    def __init__(self, code):
        self.code = code


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise HookFailure("USAGE")


def launcher(python):
    if not os.path.isabs(python) or any(ord(char) < 32 or ord(char) == 127 for char in python):
        raise HookFailure("PYTHON_PATH")
    # Git 在非 bare 仓库根目录执行 pre-commit；相对入口允许移动整个仓库。
    return (
        "#!/bin/sh\n# keex-secret-scan-hook-v1\n"
        + shlex.quote(python) + " -I -S -B tests/secret_scan/commit_hook.py 2>/dev/null\n"
        + "result=$?\n"
        + 'if [ "$result" -ne 0 ]; then\n'
        + """    printf '%s\\n' '{"status":"error","scope":"index","code":"HOOK_ABORTED"}' >&2\n"""
        + "fi\n"
        + 'exit "$result"\n'
    ).encode("utf-8")


def git(root, *args, allowed=(0,)):
    # 安装必须看到真实生效的全局/系统/仓库配置，尤其是 hooksPath。
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_TRACE")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="",
               GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1")
    result = subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", *args],
        cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=20, check=False,
    )
    if result.returncode not in allowed:
        raise HookFailure("GIT_INSPECTION")
    return result


def repository(root):
    if os.name != "posix":
        raise HookFailure("UNSUPPORTED_PLATFORM")
    if not stat.S_ISDIR((root / ".git").lstat().st_mode):
        raise HookFailure("GIT_LAYOUT")
    top = git(root, "rev-parse", "--show-toplevel").stdout.decode("utf-8").rstrip("\n")
    actual = git(root, "rev-parse", "--absolute-git-dir").stdout.decode("utf-8").rstrip("\n")
    common = git(root, "rev-parse", "--git-common-dir").stdout.decode("utf-8").rstrip("\n")
    if (Path(top).resolve() != root or Path(actual).resolve() != root / ".git"
            or (root / common).resolve() != root / ".git"):
        raise HookFailure("GIT_LAYOUT")
    if git(root, "config", "--null", "--get-all", "core.hooksPath", allowed=(0, 1)).returncode == 0:
        raise HookFailure("HOOKS_PATH_CONFIGURED")


@contextlib.contextmanager
def hook_directory(root, create=False):
    git_fd = os.open(root / ".git", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    hook_fd = None
    try:
        if create:
            try:
                os.mkdir("hooks", 0o755, dir_fd=git_fd)
            except FileExistsError:
                pass
        try:
            hook_fd = os.open("hooks", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=git_fd)
        except FileNotFoundError:
            yield None
        else:
            yield hook_fd
    finally:
        if hook_fd is not None:
            os.close(hook_fd)
        os.close(git_fd)


def identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns, value.st_nlink)


def read_hook(directory):
    if directory is None:
        return None
    try:
        fd = os.open(HOOK, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        return None
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_HOOK:
            raise HookFailure("HOOK_CONFLICT")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(MAX_HOOK + 1)
        current = os.stat(HOOK, dir_fd=directory, follow_symlinks=False)
        if (identity(before) != identity(os.fstat(fd)) or identity(before) != identity(current)
                or len(data) != before.st_size):
            raise HookFailure("HOOK_CHANGED")
        return data, before
    finally:
        os.close(fd)


def ready(root):
    here = root / "tests/secret_scan"
    for directory in (root / "tests", here):
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise HookFailure("HOOK_ENTRY")
    for name in ("commit_hook.py", "backend.py", "gate.py", "snapshot.py", "requirements.lock"):
        path = here / name
        if not stat.S_ISREG(path.lstat().st_mode):
            raise HookFailure("HOOK_ENTRY")
        if name.endswith(".py"):
            ast.parse(path.read_bytes())
    # 检查固定依赖能初始化，不自动下载；撤销不依赖扫描器或其依赖可用。
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c",
         "import sys\nsys.path.insert(0, sys.argv[1])\nfrom backend import Backend\nwith Backend(): pass",
         str(here)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=20, check=False,
    )
    if result.returncode:
        raise HookFailure("HOOK_RUNTIME")


def publish(directory, data):
    # 完整写好后以不覆盖的硬链接发布；Git 不会看见一个空的可执行 hook。
    temporary = ".keex-pre-commit-" + uuid.uuid4().hex
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700, dir_fd=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), 0o700)
            os.fsync(stream.fileno())
        os.link(temporary, HOOK, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
    finally:
        os.unlink(temporary, dir_fd=directory)


def manage(action, root=ROOT, python=None):
    root = root.resolve(strict=True)
    repository(root)
    expected = launcher(python or sys.executable)
    with hook_directory(root) as directory:
        existing = read_hook(directory)
        if existing and existing[0] != expected:
            raise HookFailure("HOOK_CONFLICT")
        if action == "uninstall":
            if existing:
                if identity(os.stat(HOOK, dir_fd=directory, follow_symlinks=False)) != identity(existing[1]):
                    raise HookFailure("HOOK_CHANGED")
                os.unlink(HOOK, dir_fd=directory)
            return {"status": "absent"}
        if existing and not existing[1].st_mode & stat.S_IXUSR:
            raise HookFailure("HOOK_NOT_EXECUTABLE")
        if action == "status":
            return {"status": "installed" if existing else "absent"}
    ready(root)
    # 初始化依赖期间可能改变配置、删除或替换 hook；重复安装也必须重新核对。
    repository(root)
    with hook_directory(root, create=True) as directory:
        current = read_hook(directory)
        if current:
            if current[0] != expected:
                raise HookFailure("HOOK_CONFLICT")
            if not current[1].st_mode & stat.S_IXUSR:
                raise HookFailure("HOOK_NOT_EXECUTABLE")
        else:
            publish(directory, expected)
        final = read_hook(directory)
        if not final or final[0] != expected or not final[1].st_mode & stat.S_IXUSR:
            raise HookFailure("HOOK_CHANGED")
    return {"status": "installed"}


def main(argv=None):
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument("action", choices=("install", "status", "uninstall"))
        parser.add_argument("--installed-python", help="仅用于检查/撤销：原安装解释器的绝对路径，不执行该路径")
        args = parser.parse_args(argv)
        if args.action == "install" and args.installed_python is not None:
            raise HookFailure("USAGE")
        result, code = manage(args.action, python=args.installed_python), 0
    except HookFailure as exc:
        result, code = {"status": "error", "code": exc.code}, 2
    except (Exception, KeyboardInterrupt):
        result, code = {"status": "error", "code": "HOOK_OPERATION_FAILED"}, 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
