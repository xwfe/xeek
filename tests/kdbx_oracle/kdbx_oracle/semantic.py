"""把解密后的 KDBX XML 变成可比较的语义树，并给出差异和结构摘要。

“语义相同”的定义（反过来就是会报差异的东西）：
- 字节不同但意思一样的，不报：加密随机数、二进制池的编号、时间的 3.1/4.x
  两种写法、String/Binary/CustomData 的先后顺序、布尔值大小写。
- 其余一律报：包括不认识的元素和属性、保护标记、分组和条目的顺序、历史。
  哪些差异是“改了应该变”的，由调用方用 ignore 模式显式列出，比较器不替人猜。

路径写法：`Root/Group=<uuid hex>/Entry=<uuid hex>/String=Password/Value`。同名兄弟第二个
起加 `#1`、`#2`；键里的 `%` 和 `/` 写成 `%25`、`%2F`。ignore 用 fnmatch 匹配，
`*` 会跨过 `/`。
"""

from __future__ import annotations

import base64
import binascii
import fnmatch
import hashlib
import re
import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .reader import DecodedKdbx

TIME_TAGS = {
    "CreationTime", "LastModificationTime", "LastAccessTime", "ExpiryTime",
    "LocationChanged", "DeletionTime",
}
# Meta 里以 Changed 结尾的都是时间。
TIME_SUFFIX = "Changed"

# 出现在这些元素里的文字是用户数据，不做任何规范化（比如不把 "true" 改成 "True"）。
USER_TEXT_PARENTS = {"String", "Item"}

# 按键区分的子元素：父元素 → {子元素: (键所在的子元素, 键是不是 UUID)}。
KEYED_CHILDREN = {
    "Root": {"Group": ("UUID", True)},
    "Group": {"Group": ("UUID", True), "Entry": ("UUID", True)},
    "Entry": {"String": ("Key", False), "Binary": ("Key", False)},
    "CustomData": {"Item": ("Key", False)},
    "CustomIcons": {"Icon": ("UUID", True)},
    "DeletedObjects": {"DeletedObject": ("UUID", True)},
}
# 顺序有意义（用户看得见的排列）的按键子元素；其余按键子元素不论顺序。
ORDERED_KEYED = {"Group", "Entry"}

# KDBX 4.1 及以前公开的元素。不在表里的就记为未知元素，写进摘要。
KNOWN_CHILDREN = {
    "KeePassFile": {"Meta", "Root"},
    "Meta": {
        "Generator", "HeaderHash", "SettingsChanged", "DatabaseName", "DatabaseNameChanged",
        "DatabaseDescription", "DatabaseDescriptionChanged", "DefaultUserName",
        "DefaultUserNameChanged", "MaintenanceHistoryDays", "Color", "MasterKeyChanged",
        "MasterKeyChangeRec", "MasterKeyChangeForce", "MasterKeyChangeForceOnce",
        "MemoryProtection", "CustomIcons", "RecycleBinEnabled", "RecycleBinUUID",
        "RecycleBinChanged", "EntryTemplatesGroup", "EntryTemplatesGroupChanged",
        "HistoryMaxItems", "HistoryMaxSize", "LastSelectedGroup", "LastTopVisibleGroup",
        "Binaries", "CustomData",
    },
    "MemoryProtection": {"ProtectTitle", "ProtectUserName", "ProtectPassword", "ProtectURL", "ProtectNotes"},
    "CustomIcons": {"Icon"},
    "Icon": {"UUID", "Data", "Name", "LastModificationTime"},
    "Binaries": {"Binary"},
    "CustomData": {"Item"},
    "Item": {"Key", "Value", "LastModificationTime"},
    "Root": {"Group", "DeletedObjects"},
    "DeletedObjects": {"DeletedObject"},
    "DeletedObject": {"UUID", "DeletionTime"},
    "Group": {
        "UUID", "Name", "Notes", "IconID", "CustomIconUUID", "Times", "IsExpanded",
        "DefaultAutoTypeSequence", "EnableAutoType", "EnableSearching", "LastTopVisibleEntry",
        "CustomData", "PreviousParentGroup", "Tags", "Group", "Entry",
    },
    "Times": {
        "CreationTime", "LastModificationTime", "LastAccessTime", "ExpiryTime", "Expires",
        "UsageCount", "LocationChanged",
    },
    "Entry": {
        "UUID", "IconID", "CustomIconUUID", "ForegroundColor", "BackgroundColor", "OverrideURL",
        "QualityCheck", "Tags", "PreviousParentGroup", "Times", "String", "Binary", "AutoType",
        "History", "CustomData",
    },
    "String": {"Key", "Value"},
    "Binary": {"Key", "Value"},
    "AutoType": {"Enabled", "DataTransferObfuscation", "DefaultSequence", "Association"},
    "Association": {"Window", "KeystrokeSequence"},
    "History": {"Entry"},
}

PASSKEY_PREFIX = "KPEX_PASSKEY_"
OTP_KEYS = {"otp", "TOTP Seed", "TOTP Settings", "TimeOtp-Secret", "TimeOtp-Secret-Base32", "HmacOtp-Secret"}
KEEAGENT_SETTINGS = "KeeAgent.settings"
STANDARD_FIELDS = {"Title", "UserName", "Password", "URL", "Notes"}
NULL_UUID = "00000000000000000000000000000000"

_ISO_TIME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?Z$")
_EPOCH = datetime(1, 1, 1, tzinfo=timezone.utc)


@dataclass
class Node:
    tag: str
    text: str = ""
    attrs: dict[str, str] = field(default_factory=dict)
    protected: bool = False
    children: list[tuple[str, "Node"]] = field(default_factory=list)


@dataclass
class Difference:
    kind: str  # added / removed / changed / order
    path: str
    detail: str

    def __str__(self) -> str:
        return f"{self.kind:8} {self.path}  {self.detail}"


# ---------- 规范化 ----------

def uuid_hex(text: str | None) -> str:
    try:
        raw = base64.b64decode((text or "").strip(), validate=True)
    except binascii.Error:
        return "invalid:" + (text or "")
    return raw.hex() if len(raw) == 16 else "invalid:" + (text or "")


def normalize_time(text: str) -> str:
    """3.1 的 ISO 写法和 4.x 的 base64(从 0001-01-01 起的秒数) 统一成 ISO。"""
    text = text.strip()
    match = _ISO_TIME.match(text)
    if match:
        return "{}-{}-{}T{}:{}:{}Z".format(*match.groups())
    try:
        raw = base64.b64decode(text, validate=True)
    except binascii.Error:
        return text
    if len(raw) != 8:
        return text
    (seconds,) = struct.unpack("<q", raw)
    try:
        moment = _EPOCH + timedelta(seconds=seconds)
    except OverflowError:
        return text
    return (
        f"{moment.year:04d}-{moment.month:02d}-{moment.day:02d}T"
        f"{moment.hour:02d}:{moment.minute:02d}:{moment.second:02d}Z"
    )


def _escape(key: str) -> str:
    return key.replace("%", "%25").replace("/", "%2F")


def _is_time(tag: str, parent_tag: str) -> bool:
    return tag in TIME_TAGS or (parent_tag == "Meta" and tag.endswith(TIME_SUFFIX))


def _binary_digest(content: bytes, protected: bool) -> str:
    digest = hashlib.sha256(content).hexdigest()
    return f"sha256:{digest} size:{len(content)}" + (" protected" if protected else "")


def canonicalize(decoded: DecodedKdbx) -> Node:
    return _canon(decoded.root, None, decoded)


def _canon(element: ET.Element, parent: ET.Element | None, decoded: DecodedKdbx) -> Node:
    parent_tag = parent.tag if parent is not None else ""
    attrs = dict(element.attrib)
    protected = False
    for name in ("Protected", "ProtectInMemory"):
        if name in attrs:
            protected = attrs.pop(name).lower() == "true" or protected
    text = (element.text or "").strip() if len(element) else (element.text or "")

    if element.tag == "Value" and parent_tag == "Binary" and "Ref" in attrs:
        ref = attrs.pop("Ref")
        if ref not in decoded.binaries:
            text = f"missing-binary-ref:{ref}"
        else:
            content, pool_protected = decoded.binaries[ref]
            text = _binary_digest(content, pool_protected)
    elif element.tag == "Value" and parent_tag == "Binary":
        # 没有 Ref 的附件是内联 base64；也按内容摘要比较。
        try:
            text = _binary_digest(base64.b64decode(text, validate=True), protected)
        except binascii.Error:
            pass
    elif _is_time(element.tag, parent_tag):
        text = normalize_time(text)
    elif element.tag in ("UUID", "RecycleBinUUID", "EntryTemplatesGroup", "LastSelectedGroup",
                         "LastTopVisibleGroup", "LastTopVisibleEntry", "CustomIconUUID",
                         "PreviousParentGroup"):
        text = uuid_hex(text)
    elif parent_tag not in USER_TEXT_PARENTS and text.lower() in ("true", "false"):
        text = text.capitalize()

    node = Node(tag=element.tag, text=text, attrs=attrs, protected=protected)
    keyed = KEYED_CHILDREN.get(element.tag, {})
    seen: dict[str, int] = {}
    for child in element:
        if element.tag == "Meta" and child.tag in ("Binaries", "HeaderHash"):
            # 二进制池已经折进引用处的摘要；HeaderHash 只属于 3.1 容器，状态另记在 summary。
            continue
        if child.tag in keyed and not (element.tag == "History"):
            key_tag, is_uuid = keyed[child.tag]
            raw_key = child.findtext(key_tag)
            key = uuid_hex(raw_key) if is_uuid else (raw_key or "")
            label = f"{child.tag}={_escape(key)}"
        else:
            label = child.tag
        count = seen.get(label, 0)
        seen[label] = count + 1
        if count:
            label = f"{label}#{count}"
        node.children.append((label, _canon(child, element, decoded)))
    return node


# ---------- 比较 ----------

def _show(node: Node, reveal: bool) -> str:
    if node.protected and not reveal:
        return f"<受保护，{len(node.text)} 字符>"
    text = node.text if len(node.text) <= 120 else node.text[:117] + "..."
    return repr(text)


def diff(a: Node, b: Node, ignore: list[str] | tuple[str, ...] = (), reveal: bool = False) -> list[Difference]:
    """返回 a → b 的差异。受保护值默认只报长度，不写内容。"""
    out: list[Difference] = []
    _diff(a, b, a.tag, list(ignore), reveal, out)
    return out


def _ignored(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _diff(a: Node, b: Node, path: str, ignore: list[str], reveal: bool, out: list[Difference]) -> None:
    if _ignored(path, ignore):
        return
    if a.text != b.text:
        out.append(Difference("changed", path, f"{_show(a, reveal)} → {_show(b, reveal)}"))
    if a.protected != b.protected:
        out.append(Difference("changed", path, f"保护标记 {a.protected} → {b.protected}"))
    if a.attrs != b.attrs:
        out.append(Difference("changed", path, f"属性 {a.attrs} → {b.attrs}"))

    a_children = dict(a.children)
    b_children = dict(b.children)
    for label, child in a.children:
        child_path = f"{path}/{label}"
        if label not in b_children:
            if not _ignored(child_path, ignore):
                out.append(Difference("removed", child_path, ""))
        else:
            _diff(child, b_children[label], child_path, ignore, reveal, out)
    for label, _child in b.children:
        child_path = f"{path}/{label}"
        if label not in a_children and not _ignored(child_path, ignore):
            out.append(Difference("added", child_path, ""))

    a_order = [label for label, child in a.children if child.tag in ORDERED_KEYED and label in b_children]
    b_order = [label for label, child in b.children if child.tag in ORDERED_KEYED and label in a_children]
    if a_order != b_order and not _ignored(path + "#order", ignore):
        out.append(Difference("order", path, "分组或条目的排列顺序变了"))


# ---------- 摘要 ----------

def _entry_fields(entry: ET.Element) -> dict[str, ET.Element]:
    fields = {}
    for string in entry.findall("String"):
        value = string.find("Value")
        fields[string.findtext("Key") or ""] = value if value is not None else ET.Element("Value")
    return fields


def _unknown_elements(element: ET.Element, path: str, out: set[str]) -> None:
    known = KNOWN_CHILDREN.get(element.tag)
    for child in element:
        child_path = f"{path}/{child.tag}"
        if known is None or child.tag not in known:
            out.add(child_path)
            continue
        _unknown_elements(child, child_path, out)


def summarize(decoded: DecodedKdbx) -> dict:
    """只含计数、字段名和摘要，不含任何字段值——可以写进 manifest 和证据。"""
    root = decoded.root
    groups = list(root.iter("Group"))
    current_entries = [e for g in groups for e in g.findall("Entry")]
    history_entries = [h for e in current_entries for h in e.findall("History/Entry")]
    all_entries = current_entries + history_entries

    recycle_uuid = uuid_hex(root.findtext("Meta/RecycleBinUUID"))
    recycle_group = next((g for g in groups if uuid_hex(g.findtext("UUID")) == recycle_uuid), None)

    custom_fields: set[str] = set()
    protected_custom: set[str] = set()
    otp: set[str] = set()
    passkey: set[str] = set()
    tags = 0
    for entry in all_entries:
        if (entry.findtext("Tags") or "").strip():
            tags += 1
        for key, value in _entry_fields(entry).items():
            if key in STANDARD_FIELDS:
                continue
            custom_fields.add(key)
            if (value.get("Protected") or value.get("ProtectInMemory") or "").lower() == "true":
                protected_custom.add(key)
            if key in OTP_KEYS:
                otp.add(key)
            if key.startswith(PASSKEY_PREFIX):
                passkey.add(key)

    attachment_refs = [b for e in all_entries for b in e.findall("Binary")]
    attachment_names = sorted({b.findtext("Key") or "" for b in attachment_refs})
    unknown: set[str] = set()
    _unknown_elements(root, root.tag, unknown)
    meta_custom = sorted(i.findtext("Key") or "" for i in root.findall("Meta/CustomData/Item"))

    return {
        "format": decoded.version,
        "cipher": decoded.cipher,
        "kdf": decoded.kdf,
        "compressed": decoded.compressed,
        "inner_stream": decoded.inner_stream,
        "header_hash": decoded.header_hash,
        "generator": root.findtext("Meta/Generator"),
        "groups": len(groups),
        "entries": len(current_entries),
        "history_entries": len(history_entries),
        "entries_with_history": sum(1 for e in current_entries if e.findall("History/Entry")),
        "recycle_bin": {
            "enabled": (root.findtext("Meta/RecycleBinEnabled") or "").lower() == "true",
            "group_present": recycle_group is not None,
            "entries": len(recycle_group.findall(".//Entry")) - len(recycle_group.findall(".//History/Entry"))
            if recycle_group is not None else 0,
        },
        "deleted_objects": len(root.findall("Root/DeletedObjects/DeletedObject")),
        "custom_icons": len(root.findall("Meta/CustomIcons/Icon")),
        "entries_with_tags": tags,
        "attachments": {
            "references": len(attachment_refs),
            "names": attachment_names,
            "pool_items": len(decoded.binaries),
            "pool_bytes": sum(len(content) for content, _ in decoded.binaries.values()),
            "pool_protected": sum(1 for _, flag in decoded.binaries.values() if flag),
        },
        "custom_fields": sorted(custom_fields),
        "protected_custom_fields": sorted(protected_custom),
        "otp_fields": sorted(otp),
        "passkey_fields": sorted(passkey),
        "keeagent_settings": sum(1 for b in attachment_refs if b.findtext("Key") == KEEAGENT_SETTINGS),
        "meta_custom_data_keys": meta_custom,
        "unknown_elements": sorted(unknown),
    }
