"""固定 keepass-rs 0.15.3 的有限合成参考保存；保留原始差异，不作生产无损裁决。"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "kdbx"
sys.path[:0] = [str(ROOT / "tests/kdbx_oracle/.deps-argon2"),
               str(ROOT / "tests/kdbx_oracle"), str(FIXTURES)]
import matrix_checks as checks
import matrix_source
import vault_source
from kdbx_oracle import read_kdbx, read_plain_xml
from kdbx_oracle.semantic import canonicalize

MANIFEST = FIXTURES / "rust_writer_manifest.json"
BINARY = HERE / "target/release/keex-reference-writer"
PROVENANCE = (
    "tests/reference_writer/Cargo.toml", "tests/reference_writer/Cargo.lock",
    "tests/reference_writer/src/main.rs", "tests/reference_writer/generate.py",
    "tests/kdbx_oracle/kdbx_oracle/reader.py", "tests/kdbx_oracle/kdbx_oracle/semantic.py",
    "tests/kdbx_oracle/kdbx_oracle/__init__.py",
    "tests/kdbx_oracle/requirements-argon2-macos-arm64.lock",
    "tests/fixtures/kdbx/source.py", "tests/fixtures/kdbx/generate.py",
    "tests/fixtures/kdbx/vault_source.py", "tests/fixtures/kdbx/vault_generate.py",
    "tests/fixtures/kdbx/matrix_source.py", "tests/fixtures/kdbx/matrix_checks.py",
    "tests/fixtures/kdbx/vault_manifest.json", "tests/fixtures/kdbx/matrix_manifest.json",
    "tests/vault_domain/contract.py", "tests/vault_domain/contract.json",
)
STANDARD = {"Title", "UserName", "Password", "URL", "Notes"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def cases():
    for kind, source_file, password, target in (
        ("passkey", "m41-passkey-edit1.kdbx", "keex-synthetic-M41-PASSKEY", matrix_source.hex_uid("passkey")),
        ("vault", "v41-vault-edit1.kdbx", "keex-synthetic-V41-VAULT", vault_source.ref(vault_source.EDIT_NAME)),
    ):
        for kdf in ("aes-kdf", "argon2d", "argon2id"):
            for cipher in ("aes", "chacha20"):
                name = f"rs41-{kind}-{kdf}-{cipher}"
                yield {"id": name.upper(), "file": name + ".kdbx", "kind": kind,
                       "source_file": source_file, "password": password,
                       "entry_uuid": target, "new_username": "synthetic-" + name,
                       "kdf": kdf, "cipher": cipher}


def attachment_values(decoded, entry):
    return [
        (item.findtext("Key"), *decoded.binaries[item.find("Value").get("Ref")])
        for item in entry.findall("Binary")
    ]


def compare_fields(expected, actual):
    checks.require(all(actual.get(key) == value for key, value in expected.items()),
                   "reference writer changed a field or protection marker")
    checks.require(all(key in STANDARD and value == checks.Field("", key == "Password")
                       for key, value in actual.items() if key not in expected),
                   "reference writer added an unexpected field")


def compare_attachments(old, new, original, current, identifier, scope, order_changes):
    before, after = attachment_values(old, original), attachment_values(new, current)
    checks.require(Counter(before) == Counter(after),
                   "reference attachment names/bytes/protection/multiplicity changed")
    if before != after:
        # 既有语义比较器按附件名称比较、不区分 Binary 排序；额外保留原始顺序观察。
        order_changes.append({"entry_uuid": identifier, "scope": scope,
                              "before": [item[0] for item in before],
                              "after": [item[0] for item in after]})


def describe(case, path):
    old_bytes = (FIXTURES / case["source_file"]).read_bytes()
    new_bytes = path.read_bytes()
    old, new = read_kdbx(old_bytes, case["password"]), read_kdbx(new_bytes, case["password"])
    checks.require(new.version == "4.1", "reference output version changed")
    cipher = "aes256-cbc" if case["cipher"] == "aes" else "chacha20"
    kdf = ({"name": "aes-kdf", "rounds": 1_000_000} if case["kdf"] == "aes-kdf" else
           {"name": case["kdf"], "memory": 8 * 1024 * 1024, "iterations": 2, "parallelism": 1})
    checks.require(new.cipher == cipher and new.kdf == kdf, "reference algorithms differ")
    before, after = checks.current_entries(old), checks.current_entries(new)
    checks.require(before.keys() == after.keys(), "reference current UUID set changed")
    checks.require(Counter((digest(data), protected) for data, protected in old.binaries.values())
                   == Counter((digest(data), protected) for data, protected in new.binaries.values()),
                   "reference attachment pool bytes/protection/sharing changed")
    history_changes = []
    attachment_order_changes = []
    for identifier, original in before.items():
        current = after[identifier]
        expected = checks.fields(original)
        if identifier == case["entry_uuid"]:
            expected["UserName"] = checks.Field(case["new_username"], expected["UserName"].protected)
        compare_fields(expected, checks.fields(current))
        compare_attachments(old, new, original, current, identifier, "current", attachment_order_changes)
        original_history = original.findall("History/Entry")
        expected_history = ([original] if identifier == case["entry_uuid"] else []) + original_history
        actual_history = current.findall("History/Entry")
        checks.require(len(expected_history) == len(actual_history), "reference history count changed")
        for index, (a, b) in enumerate(zip(expected_history, actual_history)):
            compare_fields(checks.fields(a), checks.fields(b))
            compare_attachments(old, new, a, b, identifier, "history/" + str(index), attachment_order_changes)
            changes = checks.labels(checks.snapshot(old, a), checks.snapshot(new, b), ignore=())
            if changes:
                history_changes.append({"entry_uuid": identifier, "output_history_index": index, "changes": changes})
    old_summary, new_summary = checks.summary(old), checks.summary(new)
    checks.require(new_summary["history_entries"] == old_summary["history_entries"] + 1, "history delta differs")
    for key in ("groups", "entries", "relations", "rules", "events", "diagnostics", "type_counts"):
        checks.require(old_summary[key] == new_summary[key], "reference domain summary changed: " + key)
    raw_changes = checks.labels(canonicalize(old), canonicalize(new), ignore=())
    target_path = checks.paths(old)[case["entry_uuid"]]
    mutation = {target_path + "/String=UserName/Value", target_path + "/Times/LastModificationTime"}
    other_changes = [change.label for change in checks.diff(canonicalize(old), canonicalize(new), ignore=())
                     if change.path not in mutation and not change.path.startswith(target_path + "/History")]
    return {**case, "source_sha256": digest(old_bytes), "sha256": digest(new_bytes), "bytes": len(new_bytes),
            "source_summary": old_summary, "summary": new_summary, "raw_changes": raw_changes,
            "other_changes": sorted(other_changes), "history_placement": "prepend",
            "history_snapshot_changes": history_changes,
            "attachment_order_changes": attachment_order_changes,
            "lossless_roundtrip": False,
            "verdict": "readable; original field values/protection and attachment bytes retained; semantic differences remain"}


def reference_export(case, path, binary):
    run = subprocess.run([binary, "export", "-q", "-f", "xml", str(path)],
                         input=case["password"] + "\n", text=True, capture_output=True, timeout=30)
    checks.require(run.returncode == 0, "KeePassXC reference export failed")
    source = checks.current_entries(read_kdbx(path.read_bytes(), case["password"]))
    exported = checks.current_entries(read_plain_xml(run.stdout.encode()))
    checks.require(source.keys() == exported.keys(), "reference export UUID set differs")
    for identifier, original in source.items():
        compare_fields(checks.fields(original), checks.fields(exported[identifier]))
        a, b = original.findall("History/Entry"), exported[identifier].findall("History/Entry")
        checks.require(len(a) == len(b), "reference export history count differs")
        for old, new in zip(a, b):
            compare_fields(checks.fields(old), checks.fields(new))
    return {"current_entries": len(source), "history_entries": sum(len(e.findall("History/Entry")) for e in source.values()),
            "attachment_pool_cross_checked": False}


def provenance():
    return {name: digest((ROOT / name).read_bytes()) for name in PROVENANCE}


def build_helper():
    run = subprocess.run(["cargo", "build", "--locked", "--offline", "--release",
                          "--manifest-path", str(HERE / "Cargo.toml"),
                          "--target-dir", str(HERE / "target")], cwd=ROOT,
                         capture_output=True, text=True, timeout=120)
    checks.require(run.returncode == 0 and BINARY.is_file(), "locked offline reference build failed")


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text())
        checks.require(manifest["provenance"] == provenance(), "reference verification provenance differs")
        checks.require([item["id"] for item in manifest["samples"]] == [case["id"] for case in cases()],
                       "reference case scope differs")
        for item, case in zip(manifest["samples"], cases()):
            checks.require(all(item.get(key) == value for key, value in case.items()),
                           "reference case parameters differ")
        for item in manifest["samples"]:
            checks.require(digest((FIXTURES / item["file"]).read_bytes()) == item["sha256"], "reference hash mismatch")
            checks.require(digest((FIXTURES / item["source_file"]).read_bytes()) == item["source_sha256"],
                           "reference input hash mismatch")
        print("verified existing 12 reference outputs; no files rewritten")
        return 0
    items = list(cases())
    if any((FIXTURES / case["file"]).exists() for case in items):
        raise FileExistsError("unregistered reference output exists; refusing overwrite")
    build_helper()
    source_versions = provenance()
    cli = shutil.which("keepassxc-cli")
    if not cli:
        raise RuntimeError("existing KeePassXC CLI is required")
    lock = FIXTURES / ".rust-writer-generate.lock"
    with lock.open("x"):
        pass
    created = []
    try:
        with tempfile.TemporaryDirectory(prefix=".rust-writer-work-", dir=FIXTURES) as temporary:
            work = Path(temporary)
            records = []
            for case in items:
                output = work / case["file"]
                start = time.perf_counter()
                run = subprocess.run([str(BINARY), str(FIXTURES / case["source_file"]), str(output),
                                      case["entry_uuid"], case["new_username"], case["kdf"], case["cipher"]],
                                     input=case["password"] + "\n", text=True, capture_output=True, timeout=30)
                checks.require(run.returncode == 0, "reference helper failed: " + run.stderr.strip())
                record = describe(case, output)
                record["helper_counts"] = json.loads(run.stdout)
                record["reference_export"] = reference_export(case, output, cli)
                record["elapsed_helper_and_checks_seconds"] = round(time.perf_counter() - start, 6)
                records.append(record)
            checks.require(provenance() == source_versions, "reference sources changed during generation")
            manifest = {
                "schema": 1, "note": "public synthetic KDBX 4.1 reference outputs; remaining differences are not waived",
                "writer": {"name": "keepass-rs", "version": "0.15.3", "license": "MIT",
                           "source_commit": "15afd4da3d2f305069c7940795af1de9645fd81c",
                           "feature": "save_kdbx4", "experimental": True},
                "reference_reader": subprocess.check_output([cli, "--version"], text=True).strip(),
                "runtime": {"python": platform.python_version(), "platform": platform.system(), "machine": platform.machine(),
                            "cargo": subprocess.check_output(["cargo", "--version"], text=True).strip(),
                            "cryptography": importlib.metadata.version("cryptography"),
                            "argon2-cffi": importlib.metadata.version("argon2-cffi"),
                            "argon2-cffi-bindings": importlib.metadata.version("argon2-cffi-bindings")},
                "provenance": source_versions, "generation_provenance": source_versions,
                "generation_binary_sha256": digest(BINARY.read_bytes()), "samples": records,
            }
            # 全部生成/解码/交叉读通过后才发布；发布中失败只清理本次新建文件。
            for case in items:
                destination = FIXTURES / case["file"]
                with destination.open("xb") as stream:
                    created.append(destination)
                    stream.write((work / case["file"]).read_bytes())
                    stream.flush()
                    os.fsync(stream.fileno())
            with MANIFEST.open("x", encoding="utf-8") as stream:
                created.append(MANIFEST)
                json.dump(manifest, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            print(json.dumps({"outputs": len(records), "bytes": sum(r["bytes"] for r in records),
                              "semantic_changes": {r["id"]: len(r["raw_changes"]) for r in records},
                              "lossless_roundtrip": False}, ensure_ascii=False))
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    finally:
        lock.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
