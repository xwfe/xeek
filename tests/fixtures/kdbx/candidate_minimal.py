"""K003 微型合成输入；仅复用公开夹具封装，不提供生产保存接口。

直接构造 XML，避免参考客户端先删除目标元数据；密钥/IV 沿用公开合成源，
只在测试临时目录使用。没有真实凭据、附件或联网操作。
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import struct
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import mutate
import source
import v4_payload
from kdbx_oracle import reader
from kdbx_oracle.semantic import _is_time

HERE = Path(__file__).resolve().parent
TARGET_NAME = "candidate-minimal-entry"
TARGET_UUID = source.seed("uuid/" + TARGET_NAME, 16).hex()
NEW_USERNAME = "synthetic-edited"
FEATURES = ("control", "mixed-order", "default-icons", "dual-icons", "history",
            "empty-protected", "custom-data", "custom-icon")


def _entry(level, *, username="synthetic-current", day=3, history=(), empty=False,
           custom=None, name=TARGET_NAME, icon="1", custom_icon=None):
    fields = [
        ("Title", "synthetic-minimal", False),
        ("UserName", username, False),
        ("Password", "" if empty else "synthetic-password", True),
        ("URL", "https://synthetic.example", False),
        ("Notes", "synthetic-note", False),
        ("X-Plain-Empty", "", False),
    ]
    if empty:
        fields.append(("X-Protected-Empty", "", True))
    # 位于空值后，验证空值不消耗流、后续值仍正确。
    fields.append(("X-Protected-Tail", "synthetic-tail-中文", True))
    return source.entry(level, source.Pool(), name, fields, created=source.day(1),
                        modified=source.day(day), history=history, custom=custom,
                        icon=icon, custom_icon=custom_icon)


def plain_case(feature, level):
    if feature not in FEATURES or level not in source.LEVELS:
        raise ValueError("unknown minimal synthetic case")
    if feature in ("custom-data", "custom-icon") and level != "4.1":
        raise ValueError("4.1 metadata case requires 4.1")
    empty = feature == "empty-protected"
    custom = feature == "custom-data"
    icon = feature in ("custom-icon", "dual-icons")
    default_icon = feature in ("default-icons", "dual-icons")
    history = []
    if feature in ("history", "empty-protected", "custom-data"):
        history.append(_entry(level, username="synthetic-older", day=1, empty=empty,
                              custom={"synthetic.history": "history-value"} if custom else None))
    if feature == "history":
        history.append(_entry(level, username="synthetic-later", day=2))
    entry = _entry(level, history=history, empty=empty,
                   custom={"synthetic.entry": "entry-value"} if custom else None,
                   icon="0" if default_icon else "1",
                   custom_icon=source.uid("icon") if icon else None)
    children = [entry]
    if feature == "mixed-order":
        children += [source.group(level, "candidate-child", "synthetic-child", [], icon="1"),
                     _entry(level, name="candidate-second", username="synthetic-second"),
                     source.group(level, "candidate-child-2", "synthetic-child-2", [], icon="1")]
    group = source.group(
        level, "candidate-root", "synthetic-root", children,
        icon="48" if default_icon else "1",
        custom_icon=source.uid("icon") if feature == "dual-icons" else None,
        custom={"synthetic.group": "group-value"} if custom else None,
    )
    meta = source.meta(level, "K003-MINIMAL", source.Pool(), recycle_bin=None, icons=icon)
    old_custom = meta.find("CustomData")
    if old_custom is not None:
        meta.remove(old_custom)
    if custom:
        meta.append(source.custom_data(level, {"synthetic.meta": "meta-value"}, source.day(2)))
    if level == "3.1":
        meta.append(source.E("HeaderHash", "placeholder"))
    return ET.fromstring(source.document(meta, group))


def _wire_xml(root, level, stream_id, stream_key):
    root = copy.deepcopy(root)
    epoch = datetime(1, 1, 1, tzinfo=timezone.utc)
    if level != "3.1":
        for parent in root.iter():
            for child in parent:
                if _is_time(child.tag, parent.tag) and child.text:
                    when = datetime.fromisoformat(child.text.replace("Z", "+00:00"))
                    seconds = int((when - epoch).total_seconds())
                    child.text = base64.b64encode(struct.pack("<Q", seconds)).decode()
    stream, _ = reader._inner_stream(stream_id, stream_key)
    for node in root.iter():
        if node.attrib.pop("ProtectInMemory", None) == "True":
            node.set("Protected", "True")
            raw = (node.text or "").encode("utf-8")
            encrypted = bytes(a ^ b for a, b in zip(raw, stream.keystream(len(raw))))
            node.text = base64.b64encode(encrypted).decode()
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


@lru_cache(maxsize=1)
def _v3_source():
    manifest = json.loads((HERE / "manifest.json").read_text())
    record = next(item for item in manifest["samples"] if item["id"] == "G31-RICH")
    data = (HERE / record["file"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise ValueError("registered G31-RICH changed")
    return data, record["credentials"]["password"]


@lru_cache(maxsize=2)
def _v4_source(level):
    return v4_payload.load_source("G" + level.replace(".", "") + "-RICH")


def encode_v4(root, level="4.1", inner_items=b""):
    """把调用方改过的 XML 树封装成合成 4.x 密文；inner_items 插在内层头结束标记之前。"""
    envelope = _v4_source(level)
    stream_id, key, _, _ = reader._parse_inner_header(envelope.inner)
    xml = _wire_xml(root, level, stream_id, key)
    inner = envelope.config + inner_items + v4_payload.item(0, b"")
    return envelope.encode("aes", True, inner=inner, xml=xml), envelope.password


def make_case(feature, level="4.1"):
    """返回确定性的 (合成密文, 公开合成口令)；不写文件。"""
    root = plain_case(feature, level)
    if level == "3.1":
        data, password = _v3_source()
        fields, end, _ = mutate.v3_keys(data, password, None)
        stream_id = struct.unpack("<I", fields[reader.H_INNER_STREAM_ID])[0]
        xml = _wire_xml(root, level, stream_id, fields[reader.H_PROTECTED_KEY])
        xml = mutate.with_header_hash(xml, data[:end])
        return mutate.v3_reencrypt(data, password, None, mutate.gzip_deterministic([xml])), password
    envelope = _v4_source(level)
    stream_id, key, _, _ = reader._parse_inner_header(envelope.inner)
    xml = _wire_xml(root, level, stream_id, key)
    inner = envelope.config + v4_payload.item(0, b"")
    return envelope.encode("aes", True, inner=inner, xml=xml), envelope.password
