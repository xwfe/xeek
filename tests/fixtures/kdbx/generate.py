#!/usr/bin/env python3
"""用 keepassxc-cli 生成 K002 的合成 KDBX 黄金样本，并写 manifest.json。

用法（在仓库根目录）：

    python3 -I tests/fixtures/kdbx/generate.py            # 只生成还不存在的样本
    python3 -I tests/fixtures/kdbx/generate.py --force    # 全部重新生成（会覆盖）

重新生成的文件字节一定和旧的不同（KeePassXC 每次随机生成种子和 IV），所以默认不覆盖；
已提交的样本就是黄金文件，不要随手 --force。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "kdbx_oracle"))
sys.path.insert(0, str(HERE))

from kdbx_oracle import read_kdbx, read_plain_xml  # noqa: E402
from kdbx_oracle.semantic import canonicalize, diff, summarize  # noqa: E402

import source  # noqa: E402

MANIFEST = HERE / "manifest.json"

# KeePassXC 每次保存都会改的自有元数据，和生成器写的 Generator。其余差异都记进 writer_changes。
VOLATILE = [
    "*/Meta/Generator",
    "*/Meta/CustomData/Item=KPXC_RANDOM_SLUG*",
    "*/CustomData/Item=_LAST_MODIFIED*",
]

SAMPLES = [
    {
        "id": "G31-RICH", "method": "xml-import", "source": ["rich", "3.1"], "format": "3.1",
        "password": "合成口令-G31-RICH-Ünï🔑",
        "purpose": "3.1 全特性：历史（含受保护字段增删）、回收站、DeletedObjects、共享附件、未知受保护字段、"
                   "KeeAgent、三种 OTP、Passkey（含旧字段名）、字段引用、自定义图标、Unicode/空字段/长字符串",
    },
    {
        "id": "G40-RICH", "method": "xml-import", "source": ["rich", "4.0"], "format": "4.0",
        "password": "合成口令-G40-RICH-Ünï🔑",
        "purpose": "同 G31-RICH，加分组/条目/元数据 CustomData（KeePassXC 遇到条目 CustomData 才写 4.0）",
    },
    {
        "id": "G41-RICH", "method": "xml-import", "source": ["rich", "4.1"], "format": "4.1",
        "password": "合成口令-G41-RICH-Ünï🔑",
        "purpose": "同 G40-RICH，加 4.1 特性：QualityCheck、PreviousParentGroup、分组标签、图标名称、CustomData 时间",
    },
    {
        "id": "G31-BIG", "method": "xml-import", "source": ["big", "3.1"], "format": "3.1",
        "password": "keex-synthetic-G31-BIG",
        "purpose": "1.2 MB 不可压缩附件，内容跨过 1 MiB 块边界（3.1 哈希块）",
    },
    {
        "id": "G41-BIG", "method": "xml-import", "source": ["big", "4.1"], "format": "4.1",
        "password": "keex-synthetic-G41-BIG",
        "purpose": "1.2 MB 不可压缩附件，密文跨过 1 MiB 块边界（4.x HMAC 块）",
    },
    {
        "id": "G41-CLI", "method": "cli-ops", "format": "4.1",
        "password": "keex-synthetic-G41-CLI",
        "purpose": "KeePassXC 自己产生的历史、附件、回收站和永久删除（不经过手写 XML）。"
                   "移进回收站时 KeePassXC 写入 PreviousParentGroup，整库随之升到 4.1",
    },
    {
        "id": "G31-KEYXML", "method": "cli-keyfile", "format": "3.1", "keyfile": "generated",
        "password": "keex-synthetic-G31-KEYXML",
        "purpose": "密码 + KeePassXC 生成的 XML 2.0 密钥文件",
    },
    {
        "id": "G31-KEYONLY", "method": "cli-keyfile", "format": "3.1", "keyfile": "generated",
        "password": None,
        "purpose": "只用密钥文件，没有密码",
    },
    {
        "id": "G31-KEYXML1", "method": "cli-keyfile", "format": "3.1", "keyfile": "xml-1.0",
        "password": "keex-synthetic-G31-KEYXML1",
        "purpose": "密码 + KeePass 2.x 旧式 XML 1.0 密钥文件（base64）",
    },
    {
        "id": "G31-KEYRAW32", "method": "cli-keyfile", "format": "3.1", "keyfile": "raw-32",
        "password": "keex-synthetic-G31-KEYRAW32",
        "purpose": "密码 + 恰好 32 字节的二进制密钥文件（直接当密钥）",
    },
    {
        "id": "G31-KEYBIN", "method": "cli-keyfile", "format": "3.1", "keyfile": "binary-64",
        "password": "keex-synthetic-G31-KEYBIN",
        "purpose": "密码 + 64 字节任意二进制密钥文件（按 SHA-256 取密钥）",
    },
    {
        "id": "G31-KEYHEX", "method": "cli-keyfile", "format": "3.1", "keyfile": "hex-64",
        "password": "keex-synthetic-G31-KEYHEX",
        "purpose": "密码 + 64 个十六进制字符的密钥文件（直接当 32 字节密钥）",
    },
]


class Cli:
    def __init__(self, binary: str, password: str | None, keyfile: Path | None) -> None:
        self.binary = binary
        self.password = password
        self.keyfile = keyfile

    def run(self, command: str, *args: str, extra_input: list[str] = (), unlock: bool = True) -> None:
        argv = [self.binary, command, "-q"]
        lines: list[str] = []
        if unlock:
            if self.keyfile:
                argv += ["-k", str(self.keyfile)]
            if self.password is None:
                argv.append("--no-password")
            else:
                lines.append(self.password)
        argv += list(args)
        lines += list(extra_input)
        result = subprocess.run(
            argv, input="".join(line + "\n" for line in lines), capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"{' '.join(argv)} 失败：{result.stderr.strip()} {result.stdout.strip()}")

    def create(self, database: Path) -> None:
        argv = ["-t", "100"]
        prompts: list[str] = []
        if self.password is not None:
            argv.append("-p")
            prompts = [self.password, self.password]
        if self.keyfile:
            argv += ["--set-key-file", str(self.keyfile)]
        self.run("db-create", *argv, str(database), extra_input=prompts, unlock=False)


def keepassxc_version(binary: str) -> str:
    return subprocess.run([binary, "--version"], capture_output=True, text=True, check=True).stdout.strip()


def make_keyfile(kind: str, sample_id: str, path: Path) -> None:
    if kind == "generated":
        return  # 交给 KeePassXC 在 db-create 时生成
    if kind == "raw-32":
        path.write_bytes(source.seed("keyfile/" + sample_id, 32))
    elif kind == "xml-1.0":
        encoded = base64.b64encode(source.seed("keyfile/" + sample_id, 32)).decode()
        path.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n<KeyFile>\n\t<Meta>\n\t\t<Version>1.00</Version>\n\t</Meta>\n'
            f"\t<Key>\n\t\t<Data>{encoded}</Data>\n\t</Key>\n</KeyFile>\n",
            encoding="utf-8",
        )
    elif kind == "binary-64":
        path.write_bytes(source.seed("keyfile/" + sample_id, 64))
    elif kind == "hex-64":
        path.write_text(source.seed("keyfile/" + sample_id, 32).hex(), encoding="ascii")
    else:
        raise ValueError(kind)


def generate_xml_import(cli: Cli, sample: dict, work: Path, target: Path) -> bytes:
    xml = source.build(sample["source"][0], sample["source"][1], sample["id"])
    xml_path = work / "source.xml"
    xml_path.write_bytes(xml)
    cli.run("import", "-p", str(xml_path), str(target), extra_input=[cli.password, cli.password], unlock=False)
    return xml


def generate_cli_ops(cli: Cli, sample: dict, work: Path, target: Path) -> None:
    notes_file = work / "notes.txt"
    notes_file.write_bytes("合成附件：CLI 导入\n".encode("utf-8"))
    blob_file = work / "blob.bin"
    blob_file.write_bytes(bytes(range(256)))
    cli.create(target)
    db = str(target)
    cli.run("mkdir", db, "网站")
    cli.run("mkdir", db, "网站/子组")
    cli.run("add", "-u", "synthetic-user", "--url", "https://login.example.com", "--notes", "多行\n备注 🧪",
            "-p", db, "网站/登录", extra_input=["合成-CLI-口令-1"])
    cli.run("edit", "-p", db, "网站/登录", extra_input=["合成-CLI-口令-2"])
    cli.run("edit", "-u", "synthetic-user-2", db, "网站/登录")
    cli.run("attachment-import", db, "网站/登录", "notes.txt", str(notes_file))
    cli.run("attachment-import", db, "网站/登录", "blob.bin", str(blob_file))
    cli.run("add", "-p", db, "网站/子组/待删除", extra_input=["合成-待删除"])
    cli.run("rm", db, "网站/子组/待删除")  # 移进回收站
    cli.run("add", db, "临时")
    cli.run("rm", db, "临时")
    cli.run("rm", db, "Recycle Bin/临时")  # 在回收站里再删 = 永久删除，应写进 DeletedObjects


def generate_cli_keyfile(cli: Cli, sample: dict, work: Path, target: Path) -> None:
    cli.create(target)
    cli.run("add", "-u", "synthetic-user", "-p", str(target), "条目", extra_input=["合成-密钥文件样本"])


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sample_paths(sample: dict, out: Path) -> tuple[Path, Path | None]:
    target = out / (sample["id"].lower() + ".kdbx")
    keyfile = None
    if sample.get("keyfile"):
        suffix = ".keyx" if sample["keyfile"] == "generated" else ".key"
        keyfile = out / (sample["id"].lower() + suffix)
    return target, keyfile


def generate(sample: dict, binary: str, out: Path, force: bool) -> dict | None:
    target, keyfile = sample_paths(sample, out)
    if target.exists() and not force:
        return None
    for path in (target, keyfile):
        if path is not None and path.exists():
            path.unlink()
    if keyfile is not None:
        make_keyfile(sample["keyfile"], sample["id"], keyfile)
    cli = Cli(binary, sample["password"], keyfile)
    source_xml = None
    with tempfile.TemporaryDirectory(prefix="keex-k002-") as tmp:
        work = Path(tmp)
        if sample["method"] == "xml-import":
            source_xml = generate_xml_import(cli, sample, work, target)
        elif sample["method"] == "cli-ops":
            generate_cli_ops(cli, sample, work, target)
        else:
            generate_cli_keyfile(cli, sample, work, target)
    return describe(sample, target, keyfile, source_xml)


def describe(sample: dict, target: Path, keyfile: Path | None, source_xml: bytes | None) -> dict:
    decoded = read_kdbx(
        target.read_bytes(), password=sample["password"], keyfile=keyfile.read_bytes() if keyfile else None
    )
    if decoded.version != sample["format"]:
        raise RuntimeError(f"{sample['id']} 期望 KDBX {sample['format']}，KeePassXC 写成了 {decoded.version}")
    record = {
        "id": sample["id"],
        "file": target.name,
        "sha256": sha256_file(target),
        "expect": "open",
        "method": sample["method"],
        "purpose": sample["purpose"],
        "credentials": {
            "password": sample["password"],
            "keyfile": keyfile.name if keyfile else None,
            "keyfile_sha256": sha256_file(keyfile) if keyfile else None,
        },
        "summary": summarize(decoded),
    }
    if source_xml is not None:
        record["source"] = sample["source"]
        changes = diff(canonicalize(read_plain_xml(source_xml)), canonicalize(decoded), ignore=VOLATILE)
        # 只记类型和路径：值里可能有 KeePassXC 写入的当前时间，每次生成都不同。
        record["writer_changes"] = sorted(c.label for c in changes)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="覆盖已有样本")
    parser.add_argument("--keepassxc-cli", default="keepassxc-cli")
    parser.add_argument("--only", action="append", help="只生成指定 ID，可重复")
    parser.add_argument("--refresh", action="store_true",
                        help="不重新生成库文件，只按现有文件重算 manifest 里的摘要和写入差异（改了比较器以后用）")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {"samples": []}
    existing = {record["id"]: record for record in manifest["samples"]}
    if args.refresh:
        for sample in SAMPLES:
            target, keyfile = sample_paths(sample, HERE)
            if sample["id"] not in existing or not target.exists():
                continue
            source_xml = source.build(*sample["source"], sample["id"]) if sample["method"] == "xml-import" else None
            record = describe(sample, target, keyfile, source_xml)
            record["client"] = existing[sample["id"]]["client"]
            existing[sample["id"]] = record
            print(f"重算 {sample['id']}")
        write_manifest(existing)
        return 0

    version = keepassxc_version(args.keepassxc_cli)
    for sample in SAMPLES:
        if args.only and sample["id"] not in args.only:
            continue
        record = generate(sample, args.keepassxc_cli, HERE, args.force or sample["id"] not in existing)
        if record is None:
            print(f"跳过 {sample['id']}：已存在（要重做加 --force）")
            continue
        record["client"] = {"name": "KeePassXC", "tool": "keepassxc-cli", "version": version}
        existing[sample["id"]] = record
        print(f"生成 {sample['id']}：KDBX {record['summary']['format']}，{len(record.get('writer_changes', []))} 处写入差异")
    write_manifest(existing)
    return 0


def write_manifest(existing: dict) -> None:
    order = [s["id"] for s in SAMPLES]
    manifest = {
        "note": "K002 合成样本。密码和密钥都是公开的合成值，只用于测试。生成方式见 README.md。",
        "samples": [existing[i] for i in order if i in existing]
        + [r for i, r in existing.items() if i not in order],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
