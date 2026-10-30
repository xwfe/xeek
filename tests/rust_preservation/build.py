"""K003 隔离补丁构建；只读取固定缓存，不修改原候选、锁文件或包缓存。"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REFERENCE = ROOT / "tests/reference_writer"
TARGET = REFERENCE / "target"
FIXTURES = ROOT / "tests/fixtures/kdbx"
NAME = "keex-preservation-writer"
BINARY = TARGET / "release" / NAME
HISTORY_EDIT = "keex-history-edit"
VERSION = "0.15.3"
PATCHES = tuple(HERE / "patches" / name for name in (
    "01-icons.patch", "02-history.patch", "03-attachments.patch", "04-child-order.patch",
    "05-unknown-content.patch", "06-history-limits.patch", "07-absent-defaults.patch"))
sys.path[:0] = [str(ROOT / path) for path in (
    "tests/kdbx_oracle/.deps-argon2", "tests/kdbx_oracle", "tests/fixtures/kdbx")]
from candidate_minimal import encode_v4, make_case, plain_case


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


def vault_fixture():
    # 共享附件与历史独占附件的真实客户端样本；先按登记哈希核对，避免拿错文件当输入。
    sample = next(s for s in json.loads((FIXTURES / "vault_manifest.json").read_text())["samples"]
                  if s["id"] == "V41-VAULT")
    stage = next(s for s in sample["stages"] if s["name"] == "edit1")
    data = (FIXTURES / stage["file"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != stage["sha256"]:
        raise ValueError("registered vault fixture differs from vault_manifest.json")
    return data, sample["credentials"]["password"]


def registered_fixtures():
    """所有登记过的完好样本，一行一个“路径、密码、密钥文件”；扫描器不能把真实客户端写的文件判成未知。"""
    def manifest(name):
        return json.loads((FIXTURES / name).read_text())

    rows = []
    for sample in manifest("manifest.json")["samples"]:
        if sample["id"].startswith("G"):
            key = sample["credentials"]
            rows.append((sample["file"], key["password"], key["keyfile"]))
    for name in ("vault_manifest.json", "matrix_manifest.json"):
        for sample in manifest(name)["samples"]:
            key = sample["credentials"]
            rows += [(stage["file"], key["password"], key["keyfile"]) for stage in sample["stages"]]
    for name in ("rust_writer_manifest.json", "dart_writer_manifest.json"):
        rows += [(s["file"], s["password"], s.get("keyfile")) for s in manifest(name)["samples"]]
    upstream = manifest("upstream_kdbxweb/manifest.json")
    rows += [("upstream_kdbxweb/" + item["file"], upstream["credentials"]["password"],
              "upstream_kdbxweb/" + upstream["credentials"]["keyfile"])
             for item in upstream["files"] if item["file"].endswith(".kdbx")]
    return "".join(f"{FIXTURES / path}\t{password or ''}\t{FIXTURES / keyfile if keyfile else ''}\n"
                   for path, password, keyfile in rows)


def unknown_content_inputs(work):
    # 同一口令的三份合成输入：未知元素（可读不可存）；未知受保护值和历史在字段之前（都拒绝打开）。
    unknown = plain_case("control", "4.1")
    ET.SubElement(unknown.find("Root/Group/Entry"), "KeexFuture").text = "synthetic-unknown"
    protected = plain_case("control", "4.1")
    holder = ET.Element("KeexSecret")
    ET.SubElement(holder, "Value", {"ProtectInMemory": "True"}).text = "synthetic-hidden"
    protected.find("Root/Group/Entry").insert(0, holder)
    history_first = plain_case("history", "4.1")
    entry = history_first.find("Root/Group/Entry")
    history = entry.find("History")
    entry.remove(history)
    entry.insert(0, history)
    for name, root in (("unknown", unknown), ("unknown-protected", protected),
                       ("history-first", history_first)):
        data, password = encode_v4(root)
        (work / (name + ".kdbx")).write_bytes(data)
    (work / "unknown.password").write_text(password)


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
            f'\n[[bin]]\nname = "{HISTORY_EDIT}"\n'
            f'path = {json.dumps(str(HERE / "src/history_edit.rs"))}\n'
            '\n[[test]]\nname = "preservation"\n'
            f'path = {json.dumps(str(HERE / "tests/preservation.rs"))}\n'
        )
        (work / "Cargo.toml").write_text(manifest)
        (work / "Cargo.lock").write_text(isolated_lock(lock_text))
        data, password = make_case("dual-icons")
        (work / "dual-icons.kdbx").write_bytes(data)
        (work / "dual-icons.password").write_text(password)
        data, password = vault_fixture()
        (work / "vault.kdbx").write_bytes(data)
        (work / "vault.password").write_text(password)
        unknown_content_inputs(work)
        (work / "fixtures.tsv").write_text(registered_fixtures())
        run(["cargo", "fmt", "--manifest-path", str(work / "Cargo.toml"), "--", "--check"])
        arguments = ["--locked", "--offline", "--release", "--manifest-path",
                     str(work / "Cargo.toml"), "--target-dir", str(TARGET)]
        test_output = run(["cargo", "test", *arguments, "--test", "preservation"])
        run(["cargo", "build", *arguments, "--bin", NAME, "--bin", HISTORY_EDIT])
        # Cargo 的 --locked 拒绝重新解析；再核对实验锁未被构建步骤改写。
        if (work / "Cargo.lock").read_text() != isolated_lock(lock_text):
            raise ValueError("isolated dependency lock changed")
    return BINARY, test_output


if __name__ == "__main__":
    _, output = build_helper()
    print(output, end="")
    print("built isolated preservation helper; original sources and lock unchanged")
