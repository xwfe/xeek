"""K003 隔离补丁构建；只读取固定缓存，不修改原候选、锁文件或包缓存。"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REFERENCE = ROOT / "tests/reference_writer"
TARGET = REFERENCE / "target"
NAME = "keex-preservation-writer"
BINARY = TARGET / "release" / NAME
VERSION = "0.15.3"
PATCHES = (HERE / "patches/01-icons.patch", HERE / "patches/02-history.patch")
sys.path[:0] = [str(ROOT / path) for path in (
    "tests/kdbx_oracle/.deps-argon2", "tests/kdbx_oracle", "tests/fixtures/kdbx")]
from candidate_minimal import make_case


def run(argv, *, timeout=180):
    result = subprocess.run(argv, cwd=ROOT, capture_output=True,
                            text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{argv[0]} failed ({result.returncode}):\n{result.stdout}{result.stderr}")
    return result.stdout


def source_archive(lock):
    package = next(p for p in lock["package"] if p["name"] == "keepass")
    if package["version"] != VERSION:
        raise ValueError("preservation patches require keepass 0.15.3")
    host = next(line.removeprefix("host: ") for line in run(["rustc", "-vV"]).splitlines()
                if line.startswith("host: "))
    metadata = json.loads(run([
        "cargo", "metadata", "--locked", "--offline", "--filter-platform", host,
        "--format-version", "1", "--manifest-path", str(REFERENCE / "Cargo.toml"),
    ]))
    cached = Path(next(p["manifest_path"] for p in metadata["packages"]
                       if p["name"] == "keepass" and p["version"] == VERSION)).parent
    archive = cached.parents[2] / "cache" / cached.parent.name / (cached.name + ".crate")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != package["checksum"]:
        raise ValueError("cached keepass archive differs from the existing Cargo.lock")
    return archive


def isolated_lock(text):
    # 只替换实验根包名和 keepass 的来源；所有传递版本/校验和沿用原锁。
    blocks = text.split("\n[[package]]\n")
    for index, block in enumerate(blocks):
        if block.startswith('name = "keex-reference-writer"\n'):
            blocks[index] = block.replace('"keex-reference-writer"', f'"{NAME}"', 1)
        elif block.startswith('name = "keepass"\n'):
            blocks[index] = "\n".join(line for line in block.split("\n")
                                      if not line.startswith(("source = ", "checksum = ")))
    return "\n[[package]]\n".join(blocks)


def build_helper():
    lock_text = (REFERENCE / "Cargo.lock").read_text()
    archive = source_archive(tomllib.loads(lock_text))
    work_parent = HERE / "target"
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="source-", dir=work_parent) as directory:
        work = Path(directory)
        with tarfile.open(archive) as source:
            source.extractall(work, filter="data")
        upstream = work / ("keepass-" + VERSION)
        for patch in PATCHES:
            run(["git", "apply", "--directory=" + str(upstream.relative_to(ROOT)), str(patch)])

        manifest = (REFERENCE / "Cargo.toml").read_text().replace(
            'name = "keex-reference-writer"', f'name = "{NAME}"', 1
        ).replace('keepass = { ', f'keepass = {{ path = "keepass-{VERSION}", ', 1)
        manifest += (
            f'\n[[bin]]\nname = "{NAME}"\n'
            f'path = {json.dumps(str(REFERENCE / "src/main.rs"))}\n'
            '\n[[test]]\nname = "preservation"\n'
            f'path = {json.dumps(str(HERE / "tests/preservation.rs"))}\n'
        )
        (work / "Cargo.toml").write_text(manifest)
        (work / "Cargo.lock").write_text(isolated_lock(lock_text))
        data, password = make_case("dual-icons")
        (work / "dual-icons.kdbx").write_bytes(data)
        (work / "dual-icons.password").write_text(password)
        run(["cargo", "fmt", "--manifest-path", str(work / "Cargo.toml"), "--", "--check"])
        arguments = ["--locked", "--offline", "--release", "--manifest-path",
                     str(work / "Cargo.toml"), "--target-dir", str(TARGET)]
        test_output = run(["cargo", "test", *arguments, "--test", "preservation"])
        run(["cargo", "build", *arguments, "--bin", NAME])
        # Cargo 的 --locked 拒绝重新解析；再核对实验锁未被构建步骤改写。
        if (work / "Cargo.lock").read_text() != isolated_lock(lock_text):
            raise ValueError("isolated dependency lock changed")
    return BINARY, test_output


if __name__ == "__main__":
    _, output = build_helper()
    print(output, end="")
    print("built isolated preservation helper; original sources and lock unchanged")
