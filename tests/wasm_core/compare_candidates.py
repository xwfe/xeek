"""K070：社区候选和补丁版用同一把尺子量。每个候选改同一个条目，由独立 oracle 全文比较。

    python3 -B tests/wasm_core/compare_candidates.py [候选名…]

候选的 helper 参数一样：输入 输出 条目UUID 新用户名，口令从 stdin 读。kpasslib 用项目内 pub 缓存；
manykee-fork 会克隆并运行外部仓库的代码（固定提交），不想这样就点名别的候选。
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
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


reference = load_module("compare_reference", "tests/reference_writer/generate.py")
build = load_module("compare_build", "tests/rust_preservation/build.py")
checks = reference.checks
import candidate_minimal as minimal
from kdbx_oracle import read_kdbx
from kdbx_oracle.semantic import canonicalize

FIXTURES = build.FIXTURES
KEEPASSXC = shutil.which("keepassxc-cli")
MANYKEE_URL = "https://github.com/ManyMath/ManyKee.git"
MANYKEE_COMMIT = "8b8a2ca"
USERNAME = "synthetic-candidate-edit"


def build_manykee():
    # 只编译它的 keepass-rs 分支和 keepassxc 核心，不编 FFI、WASM 和 YubiKey。
    target = ROOT / "tests/wasm_core/target/candidates"
    source = target / "ManyKee"
    if not source.exists():
        target.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", MANYKEE_URL, str(source)], check=True, timeout=300)
    subprocess.run(["git", "-C", str(source), "checkout", "-q", MANYKEE_COMMIT], check=True)
    crate = target / "manykee-helper"
    (crate / "src").mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "tests/wasm_core/manykee_helper.rs", crate / "src/main.rs")
    (crate / "Cargo.toml").write_text(f'''[package]
name = "manykee-helper"
version = "0.0.0"
edition = "2021"
publish = false

[workspace]

[dependencies]
keepass = {{ path = "{source}/rust/keepass-rs", features = ["save_kdbx4", "save_kdbx3"] }}
keepassxc = {{ path = "{source}/rust/keepassxc", default-features = false }}
''')
    built = subprocess.run(["cargo", "build", "--release", "--manifest-path", str(crate / "Cargo.toml")],
                           capture_output=True, text=True, timeout=900)
    if built.returncode:
        raise RuntimeError(built.stderr[-1500:])
    return crate / "target/release/manykee-helper"


def build_swift():
    # Swift → C ABI → 同一份 Rust。动态库和 helper 由 tests/mobile/README.md 里的命令编好。
    return ROOT / "tests/mobile/build/swift-helper"


def build_kpasslib():
    package = ROOT / "tests/kpasslib_candidate"
    environment = {**os.environ, "PUB_CACHE": str(package / ".pub-cache"), "PUB_HOSTED_URL": "https://pub.dev"}
    output = package / "build" / "helper"
    output.parent.mkdir(exist_ok=True)
    subprocess.run(["dart", "pub", "get", "--enforce-lockfile"], cwd=package, env=environment, check=True, capture_output=True)
    subprocess.run(["dart", "compile", "exe", "bin/helper.dart", "-o", str(output)], cwd=package, env=environment,
                   check=True, capture_output=True, timeout=300)
    return output


def build_dart_ffi():
    # 完整路径：Dart 接口 → FFI → 和 WASM 同一份 Rust 核心。动态库由 build.py 编好。
    package = ROOT / "tests/flutter_bridge/keex_core"
    environment = {**os.environ, "PUB_CACHE": str(package.parent / ".pub-cache"), "PUB_HOSTED_URL": "https://pub.dev"}
    output = package.parent / "build" / "helper"
    output.parent.mkdir(exist_ok=True)
    subprocess.run(["dart", "compile", "exe", "bin/helper.dart", "-o", str(output)], cwd=package, env=environment,
                   check=True, capture_output=True, timeout=300)
    os.environ["KEEX_CORE_LIB"] = str(ROOT / "tests/wasm_core/target/release/libkeex_wasm_core.dylib")
    return output


CANDIDATES = {
    "keex-patched": lambda: build.TARGET / "release" / build.HISTORY_EDIT,
    "kpasslib": build_kpasslib,
    "swift-c-rust": build_swift,
    "manykee-fork": build_manykee,
    "dart-ffi-rust": build_dart_ffi,
}


def registered():
    def stage(manifest, sample_id, name):
        sample = next(s for s in json.loads((FIXTURES / manifest).read_text())["samples"] if s["id"] == sample_id)
        record = next(s for s in sample["stages"] if s["name"] == name)
        return (FIXTURES / record["file"]).read_bytes(), sample["credentials"]["password"]

    yield "vault 4.1", *stage("vault_manifest.json", "V41-VAULT", "edit2")
    yield "passkey 4.1", *stage("matrix_manifest.json", "M41-PASSKEY", "edit2")
    yield "vault 4.0", *stage("vault_manifest.json", "V40-VAULT", "edit2")
    yield "vault 3.1", *stage("vault_manifest.json", "V31-VAULT", "edit2")
    golden = next(s for s in json.loads((FIXTURES / "manifest.json").read_text())["samples"] if s["id"] == "G41-RICH")
    yield "golden 4.1", (FIXTURES / golden["file"]).read_bytes(), golden["credentials"]["password"]


def adversarial():
    """K003 §7 的反例。受保护值全部设成短值，错位时一眼能看出来。"""
    def entry(root):
        return root.find("Root/Group/Entry")

    def add(parent, tag="KeexFuture"):
        ET.SubElement(parent, tag).text = "synthetic-unknown"

    def unknown_protected(root, length):
        holder = ET.Element("KeexSecret")
        ET.SubElement(holder, "Value", {"ProtectInMemory": "True"}).text = "x" * length
        entry(root).insert(0, holder)

    def history_first(root):
        history = entry(root).find("History")
        entry(root).remove(history)
        entry(root).insert(0, history)

    def root_first(root):
        meta = root.find("Meta")
        root.remove(meta)
        root.append(meta)

    def attribute(root):
        entry(root).set("KeexAttr", "synthetic")
        entry(root).find("String").set("KeexAttr", "synthetic")

    cases = {
        "未知元素：条目": lambda r: add(entry(r)),
        "未知元素：Meta": lambda r: add(r.find("Meta")),
        "未知元素：Root": lambda r: add(r.find("Root")),
        "未知元素：历史版本": lambda r: add(entry(r).find("History/Entry")),
        "未知元素：分组": lambda r: add(r.find("Root/Group")),
        "未知属性": attribute,
        "未知元素带受保护值（1 字节）": lambda r: unknown_protected(r, 1),
        "未知元素带受保护值（8 字节）": lambda r: unknown_protected(r, 8),
        "历史在字段之前": history_first,
        "Root 在 Meta 之前": root_first,
    }
    for name, mutate in cases.items():
        root = minimal.plain_case("history", "4.1")
        for node in root.iter():
            if node.get("ProtectInMemory") == "True":
                node.text = "a"
        mutate(root)
        yield name, *minimal.encode_v4(root)
    root = minimal.plain_case("control", "4.1")
    yield "没人引用的附件", *minimal.encode_v4(root, inner_items=minimal.v4_payload.item(3, b"\x01synthetic-unreferenced"))
    for feature in ("dual-icons", "empty-protected", "custom-data", "custom-icon", "default-icons"):
        yield f"微型：{feature}", *minimal.make_case(feature)


def expected_after_edit(before, target):
    expected = replace(before, root=copy.deepcopy(before.root))
    node = checks.current_entries(expected)[target]
    snapshot = copy.deepcopy(node)
    for nested in snapshot.findall("History"):
        snapshot.remove(nested)
    history = node.find("History")
    if history is None:
        history = ET.SubElement(node, "History")
    history.append(snapshot)
    return expected


def choose_target(decoded):
    if minimal.TARGET_UUID.replace("-", "") in checks.current_entries(decoded):
        return minimal.TARGET_UUID.replace("-", "")
    return next(i for i, e in checks.current_entries(decoded).items() if "UserName" in checks.fields(e))


def measure(helper, name, data, password, work):
    source, output = work / "input.kdbx", work / "output.kdbx"
    source.write_bytes(data)
    output.unlink(missing_ok=True)
    try:
        before = read_kdbx(data, password)
        target = choose_target(before)
    except Exception as error:
        return {"结果": "输入 oracle 读不了", "详情": str(error)[:80]}
    run = subprocess.run([str(helper), str(source), str(output), target, USERNAME], input=password + "\n",
                         capture_output=True, text=True, timeout=300)
    if run.returncode or not output.exists():
        return {"结果": "拒绝", "详情": run.stderr.strip().split("\n")[-1][:110]}
    try:
        after = read_kdbx(output.read_bytes(), password)
    except Exception as error:
        return {"结果": "输出 oracle 读不了", "详情": str(error)[:110]}
    path = checks.paths(before)[target]
    field = path + "/String=UserName"
    allowed = {field, field + "/Value", path + "/Times/LastModificationTime"}
    other = [c.label for c in checks.diff(canonicalize(expected_after_edit(before, target)), canonicalize(after), ignore=())
             if c.path not in allowed]
    export = subprocess.run([KEEPASSXC, "export", "-q", "-f", "xml", str(output)], input=password + "\n",
                            capture_output=True, text=True, timeout=120)
    # 受保护字段的值变了就是最严重的一类：能打开、能保存，密码却错了。
    corrupted = [label for label in other if "/String=" in label and label.endswith("/Value") and "changed" in label]
    return {
        "结果": "密码被改" if corrupted else ("无差异" if not other else f"{len(other)} 处差异"),
        "版本": f"{before.version}→{after.version}",
        "KeePassXC": "能开" if export.returncode == 0 else "打不开",
        "详情": [label.replace("KeePassFile/", "")[-90:] for label in other[:4]],
    }


def main():
    names = sys.argv[1:] or list(CANDIDATES)
    helpers = {name: CANDIDATES[name]() for name in names}
    table = {}
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        for case, data, password in [*registered(), *adversarial()]:
            table[case] = {name: measure(helper, case, data, password, work) for name, helper in helpers.items()}
    for case, row in table.items():
        print(case)
        for name, cell in row.items():
            print(f"  {name:14} {cell['结果']:10} {cell.get('版本', ''):9} {cell.get('KeePassXC', ''):6} {json.dumps(cell.get('详情', ''), ensure_ascii=False)[:150]}")
    output = ROOT / "tests/web_storage/results/candidates.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(table, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
