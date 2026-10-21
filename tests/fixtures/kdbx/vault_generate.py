#!/usr/bin/env python3
"""K069：用已有 KeePassXC 生成新增领域库，记录导入和两次保存的全部语义差异。

仅使用确定性合成源。默认不覆盖已有 KDBX；不运行旧 generate.py 的 main，
不修改旧 manifest.json/黄金文件。明文源只在本目录的受限临时目录内生成并清理。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent.parent / "kdbx_oracle")]
import cryptography
import generate
import vault_source
from kdbx_oracle import read_kdbx, read_plain_xml
from kdbx_oracle.semantic import canonicalize, diff, summarize

MANIFEST = HERE / "vault_manifest.json"
STAGES = ("import", "edit1", "edit2")
# 只排除这批样本实际观察到的五个元数据节点；未知相似前缀不在名单内。
VOLATILE = [
    "KeePassFile/Meta/Generator",
    "KeePassFile/Meta/CustomData/Item=KPXC_RANDOM_SLUG",
    "KeePassFile/Meta/CustomData/Item=_LAST_MODIFIED",
    "KeePassFile/Root/Group=6f542f7e7f8288660938b7000a25e046/Group=619866709f661f4847cc86d411ca5bf1/CustomData/Item=_LAST_MODIFIED",
    "KeePassFile/Root/Group=6f542f7e7f8288660938b7000a25e046/Group=619866709f661f4847cc86d411ca5bf1/Entry=8965805d6caa1155bdc9ed01dcb11d04/CustomData/Item=_LAST_MODIFIED",
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sample_id(format):
    return "V" + format.replace(".", "") + "-VAULT"


def stage_filename(identifier, stage):
    return identifier.lower() + ("" if stage == "import" else "-" + stage) + ".kdbx"


def labels(before, after, ignore=()):
    return sorted(change.label for change in diff(before, after, ignore=ignore))


def describe(format, identifier, password, source_xml, paths, version):
    source_node = canonicalize(read_plain_xml(source_xml))
    previous, stages = source_node, []
    for name, path in zip(STAGES, paths):
        decoded = read_kdbx(path.read_bytes(), password=password)
        if decoded.version != format:
            raise RuntimeError("unexpected output format: " + decoded.version)
        node = canonicalize(decoded)
        stages.append({
            "name": name, "file": stage_filename(identifier, name),
            "sha256": digest(path.read_bytes()), "summary": summarize(decoded),
            "raw_source_changes": labels(source_node, node),
            "source_changes": labels(source_node, node, VOLATILE),
            "raw_previous_changes": labels(previous, node),
            "previous_changes": labels(previous, node, VOLATILE),
        })
        previous = node
    return {
        "id": identifier, "format": format, "source_sha256": digest(source_xml),
        "client": {"name": "KeePassXC", "tool": "keepassxc-cli", "version": version},
        "credentials": {"password": password, "keyfile": None},
        "edit": {"entry_uuid": vault_source.ref(vault_source.EDIT_NAME), "field": "UserName",
                 "values": list(vault_source.EDIT_VALUES)},
        "stages": stages,
    }


def generate_one(format, binary, version):
    identifier = sample_id(format)
    final_paths = [HERE / stage_filename(identifier, stage) for stage in STAGES]
    if any(path.exists() for path in final_paths):
        raise FileExistsError(identifier + " output already exists; refusing overwrite")
    password = "keex-synthetic-" + identifier
    cli = generate.Cli(binary, password, None)
    source_xml = vault_source.build(format, identifier)
    created = []
    try:
        with tempfile.TemporaryDirectory(prefix=".vault-work-", dir=HERE) as temporary:
            work = Path(temporary)
            xml_path = work / "source.xml"
            xml_path.write_bytes(source_xml)
            paths = [work / path.name for path in final_paths]
            cli.run("import", "-p", str(xml_path), str(paths[0]),
                    extra_input=[password, password], unlock=False)
            # 每次 CLI 命令均重新解锁，从上一步的真实 KDBX 副本编辑。
            for index, username in enumerate(vault_source.EDIT_VALUES, 1):
                shutil.copyfile(paths[index - 1], paths[index])
                cli.run("edit", "-u", username, str(paths[index]), vault_source.EDIT_PATH)
            record = describe(format, identifier, password, source_xml, paths, version)
            for source_path, target in zip(paths, final_paths):
                with target.open("xb") as stream:
                    created.append(target)
                    stream.write(source_path.read_bytes())
        return record
    except BaseException:
        for target in created:
            target.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keepassxc-cli", default="keepassxc-cli")
    parser.add_argument("--only", choices=vault_source.FORMATS, action="append")
    args = parser.parse_args()
    formats = args.only or list(vault_source.FORMATS)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {"samples": []}
    existing = {sample["id"]: sample for sample in manifest["samples"]}
    pending = [format for format in formats if sample_id(format) not in existing]
    for format in formats:
        if sample_id(format) in existing:
            print("skip existing manifest sample " + sample_id(format))
    if not pending:
        return 0
    # 先确认所有待写名字为空，避免做了一半才发现另一个旧库。
    for format in pending:
        if any((HERE / stage_filename(sample_id(format), stage)).exists() for stage in STAGES):
            raise FileExistsError("unregistered output exists; inspect it instead of overwriting")
    binary = shutil.which(args.keepassxc_cli)
    if binary is None:
        raise RuntimeError("keepassxc-cli is required; no automatic installation")
    version = generate.keepassxc_version(binary)
    for format in pending:
        sample = generate_one(format, binary, version)
        existing[sample["id"]] = sample
        manifest = {
            "schema": 1,
            "note": "K069 public synthetic credentials and data only; no production writer or real account.",
            "method": "deterministic-xml -> KeePassXC import -> username edit1 -> username edit2",
            "ignored_metadata_patterns": VOLATILE,
            "runtime": {"python": platform.python_version(), "cryptography": cryptography.__version__,
                        "system": platform.system(), "machine": platform.machine()},
            "provenance": {name: digest((HERE / name).read_bytes())
                           for name in ("source.py", "vault_source.py", "vault_generate.py")},
            "samples": [existing[sample_id(f)] for f in vault_source.FORMATS if sample_id(f) in existing],
        }
        # 临时文件在同一目录，完整写出后替换本任务的独立 manifest。
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=HERE,
                                         prefix=".vault-manifest-", delete=False) as stream:
            temporary_manifest = Path(stream.name)
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        try:
            temporary_manifest.replace(MANIFEST)
        finally:
            temporary_manifest.unlink(missing_ok=True)
        print(json.dumps({
            "id": sample["id"], "format": sample["format"],
            "entries": sample["stages"][0]["summary"]["entries"],
            "stages": [{"name": stage["name"], "source_diffs": len(stage["source_changes"]),
                        "previous_diffs": len(stage["previous_changes"])} for stage in sample["stages"]],
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
