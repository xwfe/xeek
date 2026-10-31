"""K070 核对：浏览器里写出的库不由浏览器自己判断，交给独立 oracle、原生补丁库和 KeePassXC。

    python3 -B tests/wasm_core/check_outputs.py inputs <目录>    准备输入和配置，打印配置路径
    python3 -B tests/wasm_core/check_outputs.py check <报告.json> <输出目录> <配置.json>
"""
from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reference = load_module("core_reference", "tests/reference_writer/generate.py")
build = load_module("core_build", "tests/rust_preservation/build.py")
checks = reference.checks
from kdbx_oracle import read_kdbx
from kdbx_oracle.semantic import canonicalize

FIXTURES = build.FIXTURES
USERNAME = "synthetic-browser-edit"
KEEPASSXC = shutil.which("keepassxc-cli")
HISTORY_EDIT = build.TARGET / "release" / build.HISTORY_EDIT
# 真实参数，不为了跑得快而调低：KeePassXC 默认的 64 MiB 量级，再往上探到浏览器的极限。
LADDER = [
    ("aes-kdf", 0, 1_000_000, 0), ("aes-kdf", 0, 6_000_000, 0),
    ("argon2d", 64, 3, 1), ("argon2id", 16, 2, 1), ("argon2id", 64, 2, 1),
    ("argon2id", 64, 3, 2), ("argon2id", 64, 3, 4),
    ("argon2id", 256, 2, 1), ("argon2id", 1024, 2, 1), ("argon2id", 1536, 1, 1), ("argon2id", 1920, 1, 1),
    ("argon2id", 2048, 1, 1), ("argon2id", 3072, 1, 1),
]


def sample_stage(manifest, sample_id, stage_name):
    sample = next(s for s in json.loads((FIXTURES / manifest).read_text())["samples"] if s["id"] == sample_id)
    stage = next(s for s in sample["stages"] if s["name"] == stage_name)
    return stage["file"], sample["credentials"]["password"]


def prepare_inputs(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    build.unknown_content_inputs(directory)
    golden = next(s for s in json.loads((FIXTURES / "manifest.json").read_text())["samples"] if s["id"] == "G41-RICH")
    round_trips = [
        ("vault", *sample_stage("vault_manifest.json", "V41-VAULT", "edit2")),
        ("passkey", *sample_stage("matrix_manifest.json", "M41-PASSKEY", "edit2")),
        ("golden", golden["file"], golden["credentials"]["password"]),
        ("scale-1k", *sample_stage("matrix_manifest.json", "M41-SCALE-1000-LARGE", "edit1")),
        ("scale-10k", *sample_stage("matrix_manifest.json", "M41-SCALE-10000-LARGE", "edit1")),
    ]
    rows = [line.split("\t") for line in build.registered_fixtures().splitlines()]
    config = {
        "roundTrips": [{"name": n, "file": f, "password": p} for n, f, p in round_trips],
        "allSamples": [{"file": str(Path(path).relative_to(FIXTURES)), "password": password,
                        "keyfile": str(Path(keyfile).relative_to(FIXTURES)) if keyfile else None}
                       for path, password, keyfile in rows],
        "guarded": {"unknown": "@unknown.kdbx", "protected": "@unknown-protected.kdbx",
                    "password": (directory / "unknown.password").read_text()},
        "ladder": [{"name": n, "memoryMiB": m, "iterations": i, "parallelism": p} for n, m, i, p in LADDER],
    }
    path = directory / "core-config.json"
    path.write_text(json.dumps(config, ensure_ascii=False))
    print(path)


def expected_after_edit(before, target):
    expected = replace(before, root=copy.deepcopy(before.root))
    entry = checks.current_entries(expected)[target]
    snapshot = copy.deepcopy(entry)
    for nested in snapshot.findall("History"):
        snapshot.remove(nested)
    history = entry.find("History")
    if history is None:
        history = ET.SubElement(entry, "History")
    history.append(snapshot)
    return expected


def outer_fields(data):
    position, fields = 12, {}
    while True:
        identifier = data[position]
        size = struct.unpack("<i", data[position + 1:position + 5])[0]
        fields[identifier] = data[position + 5:position + 5 + size]
        position += 5 + size
        if identifier == 0:
            return fields


def check_round_trip(sample, target, output_bytes, work, failures):
    source = FIXTURES / sample["file"]
    password = sample["password"]
    before = read_kdbx(source.read_bytes(), password)
    after = read_kdbx(output_bytes, password)
    name = sample["name"]
    if (after.version, after.cipher, after.kdf, after.compressed) != (before.version, before.cipher, before.kdf, before.compressed):
        failures.append(f"{name}: 算法设置变了")
    identifier = target.replace("-", "")
    path = checks.paths(before)[identifier]
    field = path + "/String=UserName"
    allowed = {field, field + "/Value", path + "/Times/LastModificationTime"}
    expected = expected_after_edit(before, identifier)
    other = [c.label for c in checks.diff(canonicalize(expected), canonicalize(after), ignore=()) if c.path not in allowed]
    if other:
        failures.append(f"{name}: 除目标条目外有差异 {other[:5]}")

    # 同一输入、同样的改动：WASM 和原生补丁库必须写出同样的语义。这是“共享一个 writer”的依据。
    native = work / f"native-{name}.kdbx"
    run = subprocess.run([str(HISTORY_EDIT), str(source), str(native), target, USERNAME],
                         input=password + "\n", capture_output=True, text=True, timeout=300)
    if run.returncode:
        failures.append(f"{name}: 原生对照失败 {run.stderr[:120]}")
    else:
        from_native = read_kdbx(native.read_bytes(), password)
        difference = [c.label for c in checks.diff(canonicalize(from_native), canonicalize(after), ignore=())
                      if c.path != path + "/Times/LastModificationTime"]
        if difference:
            failures.append(f"{name}: 和原生输出不同 {difference[:5]}")

    output = work / f"output-{name}.kdbx"
    output.write_bytes(output_bytes)
    export = subprocess.run([KEEPASSXC, "export", "-q", "-f", "xml", str(output)], input=password + "\n",
                            capture_output=True, text=True, timeout=300)
    if export.returncode:
        failures.append(f"{name}: KeePassXC 打不开 {export.stderr[:120]}")


def check(report_path, outputs, config_path):
    report = json.loads(Path(report_path).read_text())
    config = json.loads(Path(config_path).read_text())
    outputs = Path(outputs)
    label = report["label"]
    failures = []
    facts = {}
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        results = report["results"]["roundTrips"].get("results", {})
        for sample in config["roundTrips"]:
            record = results.get(sample["name"], {})
            output = outputs / f"{label}--{sample['name']}.kdbx"
            if not record.get("ok") or not output.exists():
                failures.append(f"{sample['name']}: 浏览器里没有写出来")
                continue
            check_round_trip(sample, record["target"], output.read_bytes(), work, failures)

        first, second = (outputs / f"{label}--random-{n}.kdbx" for n in (1, 2))
        if first.exists() and second.exists():
            a, b = outer_fields(first.read_bytes()), outer_fields(second.read_bytes())
            for field, name in ((4, "主种子"), (7, "IV"), (11, "KDF 盐")):
                if a[field] == b[field]:
                    failures.append(f"两次保存的{name}相同")
            facts["randomValuesChanged"] = True
        else:
            failures.append("随机值用例没有输出")

        verified = []
        for step in report["results"]["kdfLadder"].get("results", []):
            output = outputs / f"{label}--kdf-{step['name']}-{step['memoryMiB']}-{step['iterations']}-{step['parallelism']}.kdbx"
            if not output.exists():
                continue
            # 再大的只记录浏览器里成功与否：oracle 重算一遍太慢，也不增加证据。
            if step["memoryMiB"] > 256 or step["iterations"] > 1_000_000:
                continue
            password = config["roundTrips"][0]["password"]
            decoded = read_kdbx(output.read_bytes(), password)
            if decoded.kdf["name"] != step["name"]:
                failures.append(f"KDF 输出不对 {output.name}: {decoded.kdf}")
            export = subprocess.run([KEEPASSXC, "export", "-q", "-f", "xml", str(output)], input=password + "\n",
                                    capture_output=True, text=True, timeout=300)
            if export.returncode:
                failures.append(f"KeePassXC 打不开 {output.name}")
            verified.append(output.name.split("--")[1])
        facts["ladderFilesVerified"] = verified

        counted = 0
        for row in report["results"]["readsEveryRegisteredSample"].get("results", []):
            if not row["ok"]:
                continue
            sample = next(s for s in config["allSamples"] if s["file"] == row["file"])
            keyfile = (FIXTURES / sample["keyfile"]).read_bytes() if sample["keyfile"] else None
            decoded = read_kdbx((FIXTURES / row["file"]).read_bytes(), sample["password"] or None, keyfile)
            if len(checks.current_entries(decoded)) != row["entries"]:
                failures.append(f"{row['file']}: 条目数和 oracle 不同（{row['entries']}）")
            if row["unknown"]:
                failures.append(f"{row['file']}: 被判成有未知内容")
            counted += 1
        facts["samplesComparedWithOracle"] = counted
    print(json.dumps({"label": label, "facts": facts, "failures": failures}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    if sys.argv[1] == "inputs":
        prepare_inputs(sys.argv[2])
    else:
        sys.exit(check(*sys.argv[2:5]))
