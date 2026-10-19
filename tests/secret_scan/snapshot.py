"""读取 Git index 或明确选择的工作树；不执行 filter/textconv，不解密容器。"""
from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
from pathlib import Path

from backend import ScanFailure

MAX_FILE = 64 * 1024 * 1024
MAX_TEXT = 8 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
MAX_FILES = 5000
MAX_LINE = 256 * 1024


def file_id(path: str) -> str:
    return "f-" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]


def safe_path(path):
    if not isinstance(path, str) or not path or "\\" in path:
        raise ScanFailure("UNSAFE_PATH")
    if any(part in ("", ".", "..") for part in path.split("/")):
        raise ScanFailure("UNSAFE_PATH")
    if any(ord(char) < 32 or ord(char) == 127 for char in path):
        raise ScanFailure("UNSAFE_PATH")
    return path


class Snapshot:
    def __init__(self, root: Path, scope: str):
        self.root = root.resolve(strict=True)
        if scope not in ("index", "worktree"):
            raise ScanFailure("SCOPE")
        self.scope = scope
        self._observed = {}
        index_file = os.environ.get("GIT_INDEX_FILE")
        self._index_file = index_file
        if index_file and not os.path.isabs(index_file):
            # 保留链接与 .. 的原始路径语义，结束检查才能发现链接换向。
            self._index_file = os.path.join(os.getcwd(), index_file)
        actual = self._git("rev-parse", "--show-toplevel").decode("utf-8").strip()
        if Path(actual).resolve() != self.root:
            raise ScanFailure("REPOSITORY_ROOT")
        self._initial = self._listing()
        self.entries = self._parse(self._initial)
        self.names = tuple(sorted(self.entries))
        if len(self.names) > MAX_FILES:
            raise ScanFailure("FILE_COUNT_LIMIT")
        self.fingerprint = hashlib.sha256(self._initial).hexdigest()

    def _git(self, *args):
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_TRACE")}
        if self._index_file:
            env["GIT_INDEX_FILE"] = self._index_file
        env.update({
            "GIT_NO_REPLACE_OBJECTS": "1", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "", "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_OPTIONAL_LOCKS": "0",
        })
        # 保留 GIT_INDEX_FILE：Git 部分提交会使用临时 index，门禁须检查同一份。
        try:
            result = subprocess.run(
                ["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
                 "-c", "core.quotePath=false", *args],
                cwd=self.root, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=20, check=False,
            )
            if result.returncode:
                raise ScanFailure("GIT_COMMAND")
            return result.stdout
        except (OSError, subprocess.SubprocessError):
            raise ScanFailure("GIT_COMMAND") from None

    def _listing(self):
        args = ("ls-files", "--stage", "-z") if self.scope == "index" else (
            "ls-files", "--cached", "--others", "--exclude-standard", "-z",
        )
        value = self._git(*args)
        if len(value) > 2 * 1024 * 1024:
            raise ScanFailure("INDEX_SIZE_LIMIT")
        return value

    def _parse(self, raw):
        entries = {}
        try:
            if raw and not raw.endswith(b"\0"):
                raise ScanFailure("INDEX_FORMAT")
            for record in raw.split(b"\0")[:-1]:
                if self.scope == "index":
                    metadata, raw_path = record.split(b"\t", 1)
                    mode, oid, stage = metadata.decode("ascii").split()
                    if stage != "0":
                        raise ScanFailure("INDEX_CONFLICT")
                    if mode not in ("100644", "100755"):
                        raise ScanFailure("UNSUPPORTED_MODE")
                    if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", oid):
                        raise ScanFailure("INDEX_FORMAT")
                else:
                    raw_path, oid = record, None
                path = safe_path(raw_path.decode("utf-8"))
                if path in entries and self.scope == "index":
                    raise ScanFailure("INDEX_DUPLICATE")
                entries[path] = oid
        except (UnicodeError, ValueError):
            raise ScanFailure("INDEX_FORMAT") from None
        return entries

    def _worktree_read(self, path):
        # 按目录 fd 逐级打开，避免父目录或末级符号链接把扫描带到仓库外。
        opened = []
        try:
            flags = os.O_RDONLY | os.O_NOFOLLOW
            parent = os.open(self.root, flags | os.O_DIRECTORY)
            opened.append(parent)
            parts = path.split("/")
            for part in parts[:-1]:
                parent = os.open(part, flags | os.O_DIRECTORY, dir_fd=parent)
                opened.append(parent)
            fd = os.open(parts[-1], flags | os.O_NONBLOCK, dir_fd=parent)
            opened.append(fd)
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise ScanFailure("UNSUPPORTED_MODE")
            if before.st_size > MAX_FILE:
                raise ScanFailure("FILE_SIZE_LIMIT")
            with os.fdopen(fd, "rb", closefd=False) as source:
                data = source.read(MAX_FILE + 1)
            after = os.fstat(fd)
            if len(data) > MAX_FILE:
                raise ScanFailure("FILE_SIZE_LIMIT")
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
            ) or len(data) != before.st_size:
                raise ScanFailure("WORKTREE_CHANGED")
            return data
        except (OSError, AttributeError, NotImplementedError):
            raise ScanFailure("FILE_READ") from None
        finally:
            for fd in reversed(opened):
                os.close(fd)

    def read(self, path):
        if path not in self.entries:
            raise ScanFailure("FILE_MISSING")
        if self.scope == "index":
            oid = self.entries[path]
            try:
                size = int(self._git("cat-file", "-s", oid))
            except ValueError:
                raise ScanFailure("BLOB_SIZE") from None
            if size < 0 or size > MAX_FILE:
                raise ScanFailure("FILE_SIZE_LIMIT")
            data = self._git("cat-file", "blob", oid)
            if len(data) != size:
                raise ScanFailure("BLOB_SIZE")
        else:
            data = self._worktree_read(path)
            digest = hashlib.sha256(data).hexdigest()
            if path in self._observed and self._observed[path] != digest:
                raise ScanFailure("WORKTREE_CHANGED")
            self._observed[path] = digest
        return data

    def finish(self):
        if self._listing() != self._initial:
            raise ScanFailure("SNAPSHOT_CHANGED")
        if self.scope == "worktree":
            for path, digest in self._observed.items():
                if hashlib.sha256(self._worktree_read(path)).hexdigest() != digest:
                    raise ScanFailure("WORKTREE_CHANGED")
            if self._listing() != self._initial:
                raise ScanFailure("SNAPSHOT_CHANGED")
            self.fingerprint = hashlib.sha256(
                "".join(path + "\0" + digest + "\n" for path, digest in sorted(self._observed.items())).encode()
            ).hexdigest()
