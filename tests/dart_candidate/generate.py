"""K003 对照候选 kdbx.dart 2.5.0 的合成读改写矩阵；如实记录差异、不支持项与资源，不作生产无损裁决。"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
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
import generate as fixture_generate
import matrix_checks as checks
import matrix_source
import vault_source
from kdbx_oracle import read_kdbx, read_plain_xml
from kdbx_oracle.reader import parse_variant_dictionary
from kdbx_oracle.semantic import canonicalize

# 字段与附件的保留比较和 keepass-rs 参考实验共用同一实现，保证两个候选同口径。
_spec = importlib.util.spec_from_file_location("rust_reference_generate", ROOT / "tests/reference_writer/generate.py")
rust_reference = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rust_reference)

MANIFEST = FIXTURES / "dart_writer_manifest.json"
BINARY = HERE / "build/keex-dart-candidate"
PUB_CACHE = HERE / ".pub-cache"
PROVENANCE = (
    "tests/dart_candidate/pubspec.yaml", "tests/dart_candidate/pubspec.lock",
    "tests/dart_candidate/bin/keex_dart_candidate.dart", "tests/dart_candidate/generate.py",
    "tests/reference_writer/generate.py",
    "tests/kdbx_oracle/kdbx_oracle/reader.py", "tests/kdbx_oracle/kdbx_oracle/semantic.py",
    "tests/kdbx_oracle/kdbx_oracle/__init__.py",
    "tests/fixtures/kdbx/generate.py", "tests/fixtures/kdbx/matrix_checks.py",
    "tests/fixtures/kdbx/vault_manifest.json", "tests/fixtures/kdbx/matrix_manifest.json",
    "tests/fixtures/kdbx/rust_writer_manifest.json", "tests/fixtures/kdbx/upstream_kdbxweb/manifest.json",
)
H_TRANSFORM_SEED, H_KDF_PARAMETERS = 5, 11
UPSTREAM_TARGET = "1f3605b271829042b2acfb4e6ba6cd30"
VAULT_TARGET = vault_source.ref(vault_source.EDIT_NAME)
PASSKEY_TARGET = matrix_source.hex_uid("passkey")
PASSKEY_PATH = "Passkey/Passkey KeePassXC 字段"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _case(name, source_file, password, target, entry_path, source_writer, keyfile=None):
    return {"id": name.upper(), "file": name + ".kdbx", "source_file": source_file,
            "source_writer": source_writer, "password": password, "keyfile": keyfile,
            "entry_uuid": target, "entry_path": entry_path, "new_username": "synthetic-" + name}


def cases():
    for version in ("31", "40", "41"):
        yield _case(f"dk{version}-vault", f"v{version}-vault-edit1.kdbx", f"keex-synthetic-V{version}-VAULT",
                    VAULT_TARGET, vault_source.EDIT_PATH, "KeePassXC 2.7.12")
        yield _case(f"dk{version}-passkey", f"m{version}-passkey-edit1.kdbx", f"keex-synthetic-M{version}-PASSKEY",
                    PASSKEY_TARGET, PASSKEY_PATH, "KeePassXC 2.7.12")
    yield _case("dk40-upstream-argon2d-chacha20", "upstream_kdbxweb/Argon2ChaCha.kdbx", "demo",
                UPSTREAM_TARGET, "Sample Entry", "kdbxweb public fixture (writer unknown)",
                keyfile="upstream_kdbxweb/demo.key")
    yield _case("dk41-rs-vault-argon2d-chacha20", "rs41-vault-argon2d-chacha20.kdbx", "keex-synthetic-V41-VAULT",
                VAULT_TARGET, vault_source.EDIT_PATH, "keepass-rs 0.15.3 reference output")


def unsupported_cases():
    """已从 kdbx 2.5.0 源码确认不支持、生成时实际复现失败的输入；不产出文件。"""
    yield {"id": "DK-UNSUPPORTED-ARGON2ID-4.0", "source_file": "upstream_kdbxweb/Argon2id.kdbx", "password": "demo",
           "keyfile": "upstream_kdbxweb/demo.key", "entry_uuid": UPSTREAM_TARGET,
           "expected_error": "database_open_failed",
           "cause": "key_encrypter_kdf.dart 只登记 Argon2d 与 AES-KDF 的 KDF UUID；Argon2id 抛 Invalid KDF UUID"}
    yield {"id": "DK-UNSUPPORTED-ARGON2ID-4.1", "source_file": "rs41-vault-argon2id-aes.kdbx",
           "password": "keex-synthetic-V41-VAULT", "keyfile": None, "entry_uuid": VAULT_TARGET,
           "expected_error": "database_open_failed",
           "cause": "同上；KDBX 4.1 + Argon2id 同样无法打开"}
    yield {"id": "DK-UNSUPPORTED-KDBX31-CHACHA20", "source_file": "upstream_kdbxweb/AesChaCha.kdbx", "password": "demo",
           "keyfile": "upstream_kdbxweb/demo.key", "entry_uuid": UPSTREAM_TARGET,
           "expected_error": "database_open_failed",
           "cause": "_loadV3 固定用 AES-CBC 解密；3.1 外层 ChaCha20 的 12 字节 IV 被 pointycastle 拒绝"}


def keyfile_bytes(case):
    return (FIXTURES / case["keyfile"]).read_bytes() if case.get("keyfile") else None


def open_case(case, path):
    return read_kdbx(Path(path).read_bytes(), case["password"], keyfile=keyfile_bytes(case))


def kdf_salt(decoded):
    if decoded.major == 3:
        return decoded.header_fields[H_TRANSFORM_SEED]
    return parse_variant_dictionary(decoded.header_fields[H_KDF_PARAMETERS])["S"][1]


def compare_fields(expected, actual, identifier, scope, flips):
    """与 keepass-rs 同口径比较；唯一放行的是两边都为空的标准字段保护标记变化，且逐处登记方向。"""
    expected = dict(expected)
    for key, value in expected.items():
        other = actual.get(key)
        if (key in rust_reference.STANDARD and other is not None and value.value == other.value == ""
                and value.protected != other.protected):
            flips.append({"entry_uuid": identifier, "scope": scope, "field": key,
                          "protected": [value.protected, other.protected]})
            expected[key] = other
    rust_reference.compare_fields(expected, actual)


def describe(case, path):
    old_bytes, new_bytes = (FIXTURES / case["source_file"]).read_bytes(), Path(path).read_bytes()
    old, new = open_case(case, FIXTURES / case["source_file"]), open_case(case, path)
    # 版本、算法和 KDF 资源参数必须原样保留；盐必须轮换（2.5.0 修复的缺陷）。
    checks.require(new.version == old.version, "candidate changed the KDBX version")
    checks.require((new.cipher, new.kdf, new.inner_stream, new.compressed)
                   == (old.cipher, old.kdf, old.inner_stream, old.compressed), "candidate changed algorithms")
    checks.require(kdf_salt(new) != kdf_salt(old), "candidate reused the KDF salt")
    checks.require(old.major != 3 or new.header_hash == "match", "candidate 3.x HeaderHash missing or wrong")
    before, after = checks.current_entries(old), checks.current_entries(new)
    checks.require(before.keys() == after.keys(), "candidate current UUID set changed")
    checks.require(Counter((digest(data), protected) for data, protected in old.binaries.values())
                   == Counter((digest(data), protected) for data, protected in new.binaries.values()),
                   "candidate attachment pool bytes/protection/sharing changed")
    history_changes, attachment_order_changes, dropped = [], [], []
    for identifier, original in before.items():
        current = after[identifier]
        expected = checks.fields(original)
        if identifier == case["entry_uuid"]:
            expected["UserName"] = checks.Field(case["new_username"], expected["UserName"].protected)
        compare_fields(expected, checks.fields(current), identifier, "current", dropped)
        rust_reference.compare_attachments(old, new, original, current, identifier, "current",
                                           attachment_order_changes)
        # KeePass 语义：编辑前快照追加到历史末尾，旧历史顺序不动。
        expected_history = original.findall("History/Entry") + ([original] if identifier == case["entry_uuid"] else [])
        actual_history = current.findall("History/Entry")
        checks.require(len(expected_history) == len(actual_history), "candidate history count changed")
        for index, (a, b) in enumerate(zip(expected_history, actual_history)):
            compare_fields(checks.fields(a), checks.fields(b), identifier, "history/" + str(index), dropped)
            rust_reference.compare_attachments(old, new, a, b, identifier, "history/" + str(index),
                                               attachment_order_changes)
            changes = checks.labels(checks.snapshot(old, a), checks.snapshot(new, b), ignore=())
            if changes:
                history_changes.append({"entry_uuid": identifier, "output_history_index": index, "changes": changes})
    old_summary, new_summary = checks.summary(old), checks.summary(new)
    checks.require(new_summary["history_entries"] == old_summary["history_entries"] + 1, "history delta differs")
    for key in ("groups", "entries", "relations", "rules", "events", "diagnostics", "type_counts"):
        checks.require(old_summary[key] == new_summary[key], "candidate domain summary changed: " + key)
    raw_changes = checks.labels(canonicalize(old), canonicalize(new), ignore=())
    target_path = checks.paths(old)[case["entry_uuid"]]
    mutation = {target_path + "/String=UserName/Value", target_path + "/Times/LastModificationTime",
                target_path + "/Times/LastAccessTime"}
    other_changes = sorted(change.label for change in checks.diff(canonicalize(old), canonicalize(new), ignore=())
                           if change.path not in mutation and not change.path.startswith(target_path + "/History"))
    return {**case, "source_sha256": digest(old_bytes), "sha256": digest(new_bytes), "bytes": len(new_bytes),
            "version": new.version, "cipher": new.cipher, "kdf": new.kdf, "inner_stream": new.inner_stream,
            "kdf_salt_rotated": True, "source_summary": old_summary, "summary": new_summary,
            "raw_changes": raw_changes, "other_changes": other_changes, "history_placement": "append",
            "history_snapshot_changes": history_changes, "attachment_order_changes": attachment_order_changes,
            "empty_standard_protection_changes": dropped,
            "lossless_roundtrip": not (other_changes or history_changes or attachment_order_changes or dropped)}


def keepassxc(case, binary):
    keyfile = FIXTURES / case["keyfile"] if case.get("keyfile") else None
    return fixture_generate.Cli(binary, case["password"], keyfile)


def keepassxc_export(case, path, binary):
    argv = [binary, "export", "-q", "-f", "xml"]
    if case.get("keyfile"):
        argv += ["-k", str(FIXTURES / case["keyfile"])]
    run = subprocess.run(argv + [str(path)], input=case["password"] + "\n", text=True,
                         capture_output=True, timeout=60)
    checks.require(run.returncode == 0, "KeePassXC export failed")
    source = checks.current_entries(open_case(case, path))
    exported = checks.current_entries(read_plain_xml(run.stdout.encode()))
    checks.require(source.keys() == exported.keys(), "KeePassXC export UUID set differs")
    flips = []
    for identifier, original in source.items():
        compare_fields(checks.fields(original), checks.fields(exported[identifier]), identifier, "current", flips)
        a, b = original.findall("History/Entry"), exported[identifier].findall("History/Entry")
        checks.require(len(a) == len(b), "KeePassXC export history count differs")
        for index, (old, new) in enumerate(zip(a, b)):
            compare_fields(checks.fields(old), checks.fields(new), identifier, "history/" + str(index), flips)
    return {"current_entries": len(source), "history_entries": sum(len(e.findall("History/Entry")) for e in source.values()),
            "empty_standard_protection_changes": len(flips), "attachment_pool_cross_checked": False}


def keepassxc_reedit(case, path, binary, work):
    """第三方再编辑：KeePassXC 在候选输出的副本上改同一字段，参考客户端自身变异单列。"""
    copy = Path(work) / ("reedit-" + case["file"])
    shutil.copyfile(path, copy)
    username = case["new_username"] + "-keepassxc"
    keepassxc(case, binary).run("edit", "-u", username, str(copy), case["entry_path"])
    old, new = open_case(case, path), open_case(case, copy)
    entry = checks.current_entries(new)[case["entry_uuid"]]
    checks.require(checks.fields(entry)["UserName"].value == username, "KeePassXC re-edit not applied")
    target_path = checks.paths(old)[case["entry_uuid"]]
    mutation = {target_path + "/String=UserName/Value", target_path + "/Times/LastModificationTime",
                target_path + "/Times/LastAccessTime"}
    changes = sorted(change.label for change in checks.diff(canonicalize(old), canonicalize(new), ignore=())
                     if change.path not in mutation and not change.path.startswith(target_path + "/History"))
    return {"version": new.version, "history_entries": checks.summary(new)["history_entries"],
            "reference_client_changes": changes}


def run_helper(case, output):
    argv = [str(BINARY), str(FIXTURES / case["source_file"]), str(output), case["entry_uuid"],
            case.get("new_username", "synthetic-unsupported")]
    if case.get("keyfile"):
        argv.append(str(FIXTURES / case["keyfile"]))
    # macOS 的 /usr/bin/time -l 给出子进程峰值 RSS；包含读取和保存两次 KDF。
    measured = platform.system() == "Darwin" and Path("/usr/bin/time").is_file()
    start = time.perf_counter()
    run = subprocess.run((["/usr/bin/time", "-l"] if measured else []) + argv, input=case["password"] + "\n",
                         text=True, capture_output=True, timeout=600)
    elapsed = round(time.perf_counter() - start, 3)
    rss = re.search(r"(\d+)\s+maximum resident set size", run.stderr) if measured else None
    error = next((json.loads(line) for line in run.stderr.splitlines() if line.startswith("{")), None)
    return run, error, {"wall_seconds": elapsed, "max_rss_bytes": int(rss.group(1)) if rss else None}


def provenance():
    return {name: digest((ROOT / name).read_bytes()) for name in PROVENANCE}


def dart_env():
    return {**os.environ, "PUB_CACHE": str(PUB_CACHE)}


def build_helper():
    for argv in (["dart", "pub", "get", "--offline", "--enforce-lockfile"],
                 ["dart", "compile", "exe", "bin/keex_dart_candidate.dart", "-o", str(BINARY)]):
        run = subprocess.run(argv, cwd=HERE, env=dart_env(), capture_output=True, text=True, timeout=300)
        checks.require(run.returncode == 0, "locked offline Dart build failed: " + argv[1])
    checks.require(BINARY.is_file(), "Dart helper binary missing after build")


def verify_existing():
    manifest = json.loads(MANIFEST.read_text())
    checks.require(manifest["provenance"] == provenance(), "candidate verification provenance differs")
    checks.require([item["id"] for item in manifest["samples"]] == [case["id"] for case in cases()],
                   "candidate case scope differs")
    for item, case in zip(manifest["samples"], cases()):
        checks.require(all(item.get(key) == value for key, value in case.items()), "candidate case parameters differ")
    checks.require([{k: item[k] for k in case} for item, case in zip(manifest["unsupported"], unsupported_cases())]
                   == list(unsupported_cases()), "candidate unsupported scope differs")
    for item in manifest["samples"]:
        checks.require(digest((FIXTURES / item["file"]).read_bytes()) == item["sha256"], "candidate hash mismatch")
    for item in manifest["samples"] + manifest["unsupported"]:
        checks.require(digest((FIXTURES / item["source_file"]).read_bytes()) == item["source_sha256"],
                       "candidate input hash mismatch")
    print(f"verified existing {len(manifest['samples'])} candidate outputs; no files rewritten")
    return 0


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    if MANIFEST.exists():
        return verify_existing()
    items = list(cases())
    if any((FIXTURES / case["file"]).exists() for case in items):
        raise FileExistsError("unregistered candidate output exists; refusing overwrite")
    cli = shutil.which("keepassxc-cli")
    if not cli:
        raise RuntimeError("existing KeePassXC CLI is required")
    build_helper()
    source_versions = provenance()
    lock = FIXTURES / ".dart-writer-generate.lock"
    with lock.open("x"):
        pass
    created = []
    try:
        with tempfile.TemporaryDirectory(prefix=".dart-writer-work-", dir=FIXTURES) as temporary:
            work = Path(temporary)
            records, unsupported = [], []
            for case in items:
                output = work / case["file"]
                run, error, resources = run_helper(case, output)
                checks.require(run.returncode == 0, f"candidate helper failed: {error}")
                record = describe(case, output)
                record["helper_counts"] = json.loads(run.stdout)
                record["helper_resources"] = resources
                record["keepassxc_export"] = keepassxc_export(case, output, cli)
                record["keepassxc_reedit"] = keepassxc_reedit(case, output, cli, work)
                records.append(record)
            for case in unsupported_cases():
                output = work / (case["id"].lower() + ".kdbx")
                run, error, _ = run_helper(case, output)
                checks.require(run.returncode != 0 and error == {"ok": False, "error": case["expected_error"]}
                               and not output.exists(), "unsupported input did not fail as recorded: " + case["id"])
                unsupported.append({**case, "source_sha256": digest((FIXTURES / case["source_file"]).read_bytes()),
                                    "observed_error": error["error"]})
            checks.require(provenance() == source_versions, "candidate sources changed during generation")
            dart_version = subprocess.check_output(["dart", "--version"], text=True, stderr=subprocess.STDOUT).strip()
            manifest = {
                "schema": 1,
                "note": "public synthetic K003 candidate outputs; differences and unsupported inputs are not waived",
                "writer": {"name": "kdbx (kdbx.dart)", "version": "2.5.0", "license": "GPL-3.0",
                           "archive_sha256": "8cded0bd122c17b1c1b9398ea6589ed79b34830baba9873d688646cb009bea88",
                           "argon2_backend": "pointycastle pure Dart (KdbxFormat default)"},
                "reference_reader": subprocess.check_output([cli, "--version"], text=True).strip(),
                "runtime": {"python": platform.python_version(), "platform": platform.system(),
                            "machine": platform.machine(), "dart": dart_version,
                            "cryptography": importlib.metadata.version("cryptography"),
                            "argon2-cffi": importlib.metadata.version("argon2-cffi")},
                "provenance": source_versions, "generation_provenance": source_versions,
                "generation_binary_sha256": digest(BINARY.read_bytes()),
                "samples": records, "unsupported": unsupported,
            }
            # 全部生成、解码、交叉读和再编辑通过后才发布；发布中失败只清理本次新建文件。
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
            print(json.dumps({"outputs": len(records), "unsupported": len(unsupported),
                              "other_changes": {r["id"]: len(r["other_changes"]) for r in records},
                              "lossless": {r["id"]: r["lossless_roundtrip"] for r in records}}, ensure_ascii=False))
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    finally:
        lock.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
