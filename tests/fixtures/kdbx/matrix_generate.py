#!/usr/bin/env python3
"""用已安装 KeePassXC 生成独立增量矩阵；拒绝覆盖/重定义已有样本。

每案先在 0700 临时目录导入、编辑、校验，再逐文件排他发布；manifest 原子替换。
生成/发布阶段异常会清理本案刚发布的文件；清单写入失败或强杀可能留下未登记文件。
这些文件下次会触发拒绝覆盖，须先核对来源与哈希，不自动删除或接纳。
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent.parent / "kdbx_oracle")]
import cryptography
import generate
import matrix_checks as checks
import matrix_source as source
from kdbx_oracle import read_kdbx, read_plain_xml
from kdbx_oracle.semantic import canonicalize

MANIFEST = HERE / "matrix_manifest.json"
PROVENANCE = ("source.py", "vault_source.py", "matrix_source.py", "matrix_checks.py",
              "matrix_generate.py", "matrix_probe.py", "vault_generate.py")


def probe(request):
    run = subprocess.run([sys.executable, "-B", str(HERE / "matrix_probe.py")],
                         input=json.dumps(request), capture_output=True, text=True, timeout=150)
    if run.returncode:
        raise RuntimeError("matrix probe failed: " + run.stderr[-2000:])
    return json.loads(run.stdout)


def run_cli(binary, args, stdin):
    return probe({"mode": "cli", "argv": [binary, *args], "stdin": stdin})


def describe(case, password, xml, paths):
    original = read_plain_xml(xml)
    original_node = canonicalize(original)
    previous, previous_node, stages = original, original_node, []
    for index, (stage, path) in enumerate(zip(case["stages"], paths)):
        data = path.read_bytes()
        decoded = read_kdbx(data, password=password)
        checks.require(decoded.version == case["format"], "format changed")
        checks.require(decoded.cipher == "aes256-cbc" and decoded.kdf == {"name": "aes-kdf", "rounds": 1000000},
                       "unexpected matrix crypto parameters")
        checks.verify_original_fields(original, decoded, case, index)
        node = canonicalize(decoded)
        source_changes = checks.labels(original_node, node)
        if index == 0:
            checks.require(set(source_changes) == checks.expected_import(case, original),
                           "unreviewed import changes: " + "; ".join(
                               sorted(set(source_changes) ^ checks.expected_import(case, original))[:20]))
        else:
            checks.verify_transition(previous, decoded, case, previous_node, node)
        stages.append({"name": stage, "file": source.filename(case, stage),
                       "bytes": len(data), "sha256": checks.digest(data), "summary": checks.summary(decoded),
                       "raw_source_changes": checks.labels(original_node, node, ()),
                       "source_changes": source_changes,
                       "raw_previous_changes": checks.labels(previous_node, node, ()),
                       "previous_changes": checks.labels(previous_node, node)})
        previous, previous_node = decoded, node
    return stages


def generate_one(case, binary):
    final_paths = [HERE / source.filename(case, stage) for stage in case["stages"]]
    if any(path.exists() for path in final_paths):
        raise FileExistsError("unregistered output exists; refusing overwrite")
    password = "keex-synthetic-" + case["id"]
    identifier, entry_path = source.edit_target(case)
    created = []
    try:
        with tempfile.TemporaryDirectory(prefix=".matrix-work-", dir=HERE) as directory:
            work = Path(directory)
            started = time.perf_counter()
            xml = source.build(case)
            source_seconds = time.perf_counter() - started
            xml_path = work / "source.xml"
            xml_path.write_bytes(xml)
            paths = [work / path.name for path in final_paths]
            commands = [run_cli(binary, ["import", "-q", "-p", str(xml_path), str(paths[0])],
                                password + "\n" + password + "\n")]
            for index, path in enumerate(paths[1:], 1):
                shutil.copyfile(paths[index - 1], path)
                commands.append(run_cli(binary, ["edit", "-q", "-u", source.EDIT_VALUES[index - 1],
                                                  str(path), entry_path], password + "\n"))
            started = time.perf_counter()
            stages = describe(case, password, xml, paths)
            check_seconds = time.perf_counter() - started
            reads = [probe({"mode": "open", "file": str(paths[-1]), "password": password})
                     for _ in range(3)] if case["kind"] == "scale" else []
            sample = {**case, "source_sha256": checks.digest(xml), "source_bytes": len(xml),
                      "credentials": {"password": password, "keyfile": None},
                      "edit": {"entry_uuid": identifier, "path": entry_path, "field": "UserName",
                               "values": list(source.EDIT_VALUES[:len(paths) - 1])},
                      "stages": stages,
                      "measurements": {"source_build_seconds": source_seconds, "verification_seconds": check_seconds,
                                       "cli": dict(zip(case["stages"], commands)), "oracle_final": reads}}
            for temporary, final in zip(paths, final_paths):
                with final.open("xb") as stream:
                    created.append(final)
                    stream.write(temporary.read_bytes())
            return sample
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise


def save_manifest(manifest):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=HERE, prefix=".matrix-manifest-", delete=False,
                                         encoding="utf-8") as stream:
            temporary = Path(stream.name)
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(MANIFEST)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=[c["id"] for c in source.cases()], action="append")
    parser.add_argument("--keepassxc-cli", default="keepassxc-cli")
    args = parser.parse_args()
    lock = HERE / ".matrix-generate.lock"
    lock.mkdir()  # 同目录排他锁；不自动解除其它进程或强杀留下的锁。
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {"samples": []}
        existing = {sample["id"]: sample for sample in manifest["samples"]}
        provenance = {name: checks.digest((HERE / name).read_bytes()) for name in PROVENANCE}
        if existing:
            checks.require(manifest["provenance"] == provenance, "generator/source changed; review before extending manifest")
            for sample in existing.values():
                for stage in sample["stages"]:
                    checks.require(checks.digest((HERE / stage["file"]).read_bytes()) == stage["sha256"], "existing file changed")
        selected = [case for case in source.cases() if not args.only or case["id"] in args.only]
        pending = [case for case in selected if case["id"] not in existing]
        for case in selected:
            if case["id"] in existing:
                print("verified existing " + case["id"], flush=True)
        for case in pending:
            if any((HERE / source.filename(case, stage)).exists() for stage in case["stages"]):
                raise FileExistsError("unregistered output exists; inspect before retry")
        if not pending:
            return 0
        binary = shutil.which(args.keepassxc_cli)
        if not binary:
            raise RuntimeError("keepassxc-cli unavailable; no automatic installation")
        version = generate.keepassxc_version(binary)
        checks.require(version == "2.7.12", "reference writer version requires new review")
        for case in pending:
            sample = generate_one(case, binary)
            existing[case["id"]] = sample
            manifest = {"schema": 1, "note": "public synthetic matrix only; not production writer acceptance",
                        "client": {"name": "KeePassXC", "version": version},
                        "runtime": {"python": platform.python_version(), "cryptography": cryptography.__version__,
                                    "system": platform.system(), "machine": platform.machine()},
                        "measurement_method": "CLI: one command per fresh worker; oracle: three fresh processes, warm filesystem cache possible; ru_maxrss normalized to bytes; no device performance gate.",
                        "provenance": provenance, "ignored_metadata_paths": list(checks.VOLATILE),
                        "samples": [existing[c["id"]] for c in source.cases() if c["id"] in existing]}
            save_manifest(manifest)
            print("generated and verified " + case["id"], flush=True)
    finally:
        lock.rmdir()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

