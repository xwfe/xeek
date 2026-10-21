"""K002/K069 增量确定性 XML：同 RP 多凭据与精确 1k/10k 当前条目。

仅公开合成数据，不读取用户文件，不实现 KDBX writer。旧 source/vault_source 保持不变。
规模由 25 条领域块组成；Entry、关系、规则、事件与证据引用一起重映射。
"""
from __future__ import annotations

import base64
import copy
import gzip
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import source
import vault_source as vault

FORMATS = ("3.1", "4.0", "4.1")
COUNTS = (1000, 10000)
ATTACHMENT_BYTES = {"small": 4096, "large": 4 * 1024 * 1024}
EDIT_VALUES = ("synthetic-matrix-edit-1", "synthetic-matrix-edit-2")
UUID_PROPERTIES = {"target", "ruleId", "targetEventId", "basisEventId", "entry"}
DYNAMIC_PREFIXES = ("keex.relation.", "keex.lifecycle.rule.", "keex.lifecycle.event.")
PASSKEY_NAMES = ("passkey", "matrix/passkey-b", "matrix/passkey-a2")


def cases():
    return [
        *[{"id": "M" + fmt.replace(".", "") + "-PASSKEY", "kind": "passkey", "format": fmt,
           "stages": ["import", "edit1", "edit2"]} for fmt in FORMATS],
        *[{"id": f"M41-SCALE-{count}-{size.upper()}", "kind": "scale", "format": "4.1",
           "count": count, "attachment": size, "stages": ["import", "edit1"]}
          for count in COUNTS for size in ATTACHMENT_BYTES],
    ]


def case_by_id(identifier):
    return next(case for case in cases() if case["id"] == identifier)


def filename(case, stage):
    return case["id"].lower() + ("" if stage == "import" else "-" + stage) + ".kdbx"


def hex_uid(name):
    return base64.b64decode(source.uid(name)).hex()


def mapped_uuid(block, original):
    return source.seed(f"matrix-scale/{block}/uuid/{original}", 16).hex()


def scale_uuid(block, name):
    return mapped_uuid(block, vault.ref(name))


def xml_uuid(identifier):
    return base64.b64encode(bytes.fromhex(identifier)).decode()


def remap_json(value, block):
    if isinstance(value, list):
        return [remap_json(item, block) for item in value]
    if isinstance(value, dict):
        return {key: mapped_uuid(block, item) if key in UUID_PROPERTIES else remap_json(item, block)
                for key, item in value.items()}
    return value


def scale_records(block):
    items = copy.deepcopy(vault.records())
    # 第 25 条产生跨块高扇入；其它关系仍限定在各自块内。
    items.append({"name": "hub-login", "type": "login", "fields": [
        vault.field("Title", "合成集中关联账户"),
        vault.field("keex.record.schema", "1"), vault.field("keex.record.type", "login"),
        vault.field("UserName", f"synthetic-hub-{block:04d}"),
        vault.field("Password", f"SYNTHETIC-HUB-{block:04d}", True),
        vault.relation("hub-recovery", "recoveredBy", "service-login"),
    ]})
    for item in items:
        remapped = []
        for key, value, protected in item["fields"]:
            prefix = next((p for p in DYNAMIC_PREFIXES if key.startswith(p)), None)
            if prefix:
                key = prefix + mapped_uuid(block, key[len(prefix):])
                value = remap_json(json.loads(value), block)
                if item["name"] == "hub-login":
                    value["target"] = scale_uuid(0, "service-login")
                value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            elif key == "keex.parentEntryUuid":
                value = mapped_uuid(block, value)
            remapped.append((key, value, protected))
        item["fields"] = remapped
        item["uuid"] = scale_uuid(block, item["name"])
    return items


def edit_target(case):
    if case["kind"] == "passkey":
        return hex_uid("passkey"), "Passkey/Passkey KeePassXC 字段"
    return scale_uuid(0, "service-login"), "合成批次0000/合成服务账户"


def write_xml(root):
    ET.indent(root, space="\t")
    return (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            + ET.tostring(root, encoding="utf-8") + b"\n")


def build_passkeys(case):
    root = ET.fromstring(vault.build(case["format"], case["id"]))
    level = case["format"]
    group = next(g for g in root.iter("Group") if g.findtext("UUID") == source.uid("group/passkey"))
    pool = source.Pool()  # 新增条目不带附件；原 XML 附件池保持原样。
    parent_b = "matrix/passkey-parent-b"
    parent = source.entry(level, pool, parent_b, [
        vault.field("Title", "合成第二个通行密钥账户"), vault.field("UserName", "synthetic-user-b"),
        vault.field("keex.record.schema", "1"), vault.field("keex.record.type", "login"),
        vault.field("Password", "SYNTHETIC-PASSKEY-PARENT-B", True),
        vault.field("URL", "https://passkey.example.com"),
    ])
    next(g for g in root.iter("Group") if g.findtext("UUID") == source.uid("vault/group")).append(parent)
    for label, user, handle, parent_name in (
        ("b", "synthetic-user-b", "matrix-passkey-user-b", parent_b),
        ("a2", "synthetic-user", "passkey-user", "vault/service-login"),
    ):
        group.append(source.entry(level, pool, "matrix/passkey-" + label, [
            vault.field("Title", "合成同站通行密钥-" + label),
            vault.field("UserName", user), vault.field("URL", "https://passkey.example.com"),
            vault.field("KPEX_PASSKEY_USERNAME", user),
            vault.field("KPEX_PASSKEY_CREDENTIAL_ID", source.b64url(source.seed("matrix-credential-" + label, 16))),
            vault.field("KPEX_PASSKEY_PRIVATE_KEY_PEM", source.passkey_pem("matrix-" + label), True),
            vault.field("KPEX_PASSKEY_RELYING_PARTY", "passkey.example.com"),
            vault.field("KPEX_PASSKEY_USER_HANDLE", source.b64url(source.seed(handle, 16)), True),
            vault.field("KPEX_PASSKEY_FLAG_BE", "1"), vault.field("KPEX_PASSKEY_FLAG_BS", "1"),
            vault.field("keex.parentEntryUuid", source.uid(parent_name), True),
        ], tags="合成;Passkey"))
    root.find("Meta/DatabaseDescription").text = "keex 合成同 RP 多凭据；未注册到任何网站"
    return write_xml(root)


def build_scale(case):
    count = case["count"]
    if count not in COUNTS or case["attachment"] not in ATTACHMENT_BYTES:
        raise ValueError("unsupported bounded scale case")
    pool, groups, recycled = source.Pool(), [], []
    shared = source.seed("matrix-shared-small-attachment", 4096)
    payload = source.seed("matrix-payload-attachment", ATTACHMENT_BYTES[case["attachment"]])
    for block in range(count // 25):
        entries = []
        for item in scale_records(block):
            attachments = {}
            if item.get("attachment"):
                attachments["合成凭据.txt"] = vault.DOCUMENT_BYTES
                attachments["synthetic-shared.bin"] = shared
            # 一份独立大块跨当前/历史共用；并非每个引用都新增 4 MiB。
            if item["name"] == "card-old" and block == 0:
                attachments["synthetic-payload.bin"] = payload
            history = []
            if item.get("history"):
                old = [field for field in item["fields"] if field[0] != "X-Vault-Protected"]
                old.append(vault.field("X-Vault-History-Only", "合成仅历史保护值", True))
                previous = source.entry("4.1", pool, "unused", old, modified=source.day(2),
                                        attachments=attachments)
                previous.find("UUID").text = xml_uuid(item["uuid"])
                history = [previous]
            entry = source.entry("4.1", pool, "unused", item["fields"], modified=source.day(4),
                                 attachments=attachments, history=history)
            entry.find("UUID").text = xml_uuid(item["uuid"])
            (recycled if item.get("recycle") else entries).append(entry)
        groups.append(source.group("4.1", f"matrix/scale-group/{block}", f"合成批次{block:04d}", entries))
    recycle_name = "matrix/scale-recycle"
    groups.append(source.group("4.1", recycle_name, "合成回收站", recycled, icon="43"))
    root_group = source.group("4.1", "matrix/scale-root", "合成规模库", groups)
    meta = source.meta("4.1", case["id"], pool, recycle_bin=recycle_name, icons=False)
    meta.find("DatabaseDescription").text = "keex 合成规模样本；当前条目数含回收站，历史另计"
    # HistoryMaxSize 默认 6 MiB，大附件只有一份 4 MiB 历史，保持同一参数。
    return source.document(meta, root_group)


def build(case):
    return build_passkeys(case) if case["kind"] == "passkey" else build_scale(case)

