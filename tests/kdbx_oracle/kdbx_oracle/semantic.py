"""把解密后的 KDBX XML 变成可比较的语义树，并给出差异和结构摘要。

“语义相同”的定义（反过来就是会报差异的东西）：
- 字节不同但意思一样的，不报：加密随机数、二进制池的编号、时间的 3.1/4.x
  两种写法、String/Binary/CustomData 的先后顺序、布尔值大小写、标签的顺序和分隔符
  （`a;b` 和 `b,a` 一样）、**已知**的空元素和不写该元素（`<Tags/>` 和没有 Tags 一样）、
  值为空的五个标准字段和不写该字段。自定义字段哪怕值为空，有和没有也算不同；不认识的
  元素哪怕是空的，丢了也报（它可能是新版本或插件的标记，空不等于没有）。
- 附件的“内容”和“保护标记”分开报：内容是节点文字（SHA-256 + 长度），保护标记是属性
  `pool_protected`。
- 其余一律报：包括不认识的元素和属性、保护标记、分组和条目的顺序、历史。
  哪些差异是“改了应该变”的，由调用方用 ignore 模式显式列出，比较器不替人猜。

路径写法：`Root/Group=<uuid hex>/Entry=<uuid hex>/String=Password/Value`。同名兄弟第二个
起加 `#1`、`#2`；键里的 `%`、`/` 和 `#` 写成 `%25`、`%2F`、`%23`。ignore 用 fnmatch 匹配，
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
# 只有已知结构里的明确布尔项才忽略大小写；Name/Notes/Generator 等文字不转换。
BOOLEAN_CHILDREN = {
    "Meta": {"RecycleBinEnabled", "MasterKeyChangeForceOnce"},
    "MemoryProtection": {"ProtectTitle", "ProtectUserName", "ProtectPassword", "ProtectURL", "ProtectNotes"},
    "Group": {"IsExpanded", "EnableAutoType", "EnableSearching"},
    "Times": {"Expires"},
    "Entry": {"QualityCheck"},
    "AutoType": {"Enabled"},
}

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

# KPEX_ 是 KeePassXC/Strongbox 共用的字段前缀；KPXC_PASSKEY_USERNAME 是 KeePassXC 早期的旧名。
PASSKEY_PREFIXES = ("KPEX_PASSKEY_", "KPXC_PASSKEY_")
# otp 是 KeePassXC 的 otpauth:// URI；TOTP Seed/Settings 是旧 KeeOtp/KeeTrayTOTP 插件；
# TimeOtp-*/HmacOtp-* 是 KeePass 2.47+ 原生格式。
OTP_KEYS = {"otp", "TOTP Seed", "TOTP Settings"}
OTP_PREFIXES = ("TimeOtp-", "HmacOtp-")
KEEAGENT_SETTINGS = "KeeAgent.settings"
STANDARD_FIELDS = {"Title", "UserName", "Password", "URL", "Notes"}
NULL_UUID = "00000000000000000000000000000000"

_ISO_TIME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d+)?Z$")
_EPOCH = datetime(1, 1, 1, tzinfo=timezone.utc)


@dataclass
class Node:
    tag: str
    text: str = ""
    attrs: dict[str, str] = field(default_factory=dict)
    protected: bool = False
    tail: str = ""
    preserve_order: bool = False
    children: list[tuple[str, "Node"]] = field(default_factory=list)


@dataclass
class Difference:
    kind: str  # added / removed / changed / order
    path: str
    detail: str
    aspect: str = ""  # changed 时是哪一项变了：value / protected / attrs

    @property
    def label(self) -> str:
        """只含类型和路径、不含值的简写，用来写进 manifest。"""
        kind = f"{self.kind}/{self.aspect}" if self.aspect else self.kind
        return f"{kind} {self.path}"

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
        parts = match.groups()
        try:
            datetime(*map(int, parts[:6]))
        except ValueError:
            return text
        fraction = (parts[6] or "").rstrip("0").rstrip(".")
        return "{}-{}-{}T{}:{}:{}".format(*parts[:6]) + fraction + "Z"
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
    return key.replace("%", "%25").replace("/", "%2F").replace("#", "%23")


def _is_time(tag: str, parent_tag: str) -> bool:
    return (
        (parent_tag == "Times" and tag in TIME_TAGS)
        or (parent_tag in ("Icon", "Item") and tag == "LastModificationTime")
        or (parent_tag == "DeletedObject" and tag == "DeletionTime")
        or (parent_tag == "Meta" and tag in KNOWN_CHILDREN["Meta"] and tag.endswith("Changed"))
    )


def _binary_digest(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()} size:{len(content)}"


def canonicalize(decoded: DecodedKdbx) -> Node:
    return _canon(decoded.root, None, decoded, decoded.root.tag == "KeePassFile")


def _canon(element: ET.Element, parent: ET.Element | None, decoded: DecodedKdbx,
           known_context: bool) -> Node:
    parent_tag = parent.tag if parent is not None else ""
    attrs = dict(element.attrib)
    protected = any(attrs.get(name, "").lower() == "true" for name in ("Protected", "ProtectInMemory"))
    # 未知节点/属性原样比较，仍尊重保护标记以免差异输出泄露文本。
    if known_context and parent_tag in ("String", "Binary") and element.tag == "Value":
        for name in ("Protected", "ProtectInMemory"):
            if attrs.get(name, "").lower() in ("true", "false"):
                attrs.pop(name)
    known = KNOWN_CHILDREN.get(element.tag, set()) if known_context else set()
    preserve_order = not known_context or any(child.tag not in known for child in element)
    text = element.text or ""
    if len(element) and not preserve_order and not text.strip():
        text = ""  # 仅丢弃已知结构容器的纯排版空白，不 strip 混合文字。

    if known_context and not len(element):
        if element.tag == "Value" and parent_tag == "Binary":
            # 附件按内容摘要比，不按池编号；保护标记单独比较。
            if "Ref" in attrs:
                ref = attrs.pop("Ref")
                if ref not in decoded.binaries:
                    text = f"missing-binary-ref:{ref}"
                else:
                    content, protected = decoded.binaries[ref]
                    text = _binary_digest(content)
            else:
                try:
                    text = _binary_digest(base64.b64decode(text, validate=True))
                except binascii.Error:
                    pass
            if protected:
                attrs["pool_protected"] = "True"
            protected = False
        elif _is_time(element.tag, parent_tag):
            text = normalize_time(text)
        elif element.tag in ("UUID", "RecycleBinUUID", "EntryTemplatesGroup", "LastSelectedGroup",
                             "LastTopVisibleGroup", "LastTopVisibleEntry", "CustomIconUUID",
                             "PreviousParentGroup"):
            text = uuid_hex(text)
        elif element.tag == "Tags" and parent_tag in ("Entry", "Group"):
            text = ",".join(sorted({tag.strip() for tag in re.split(r"[;,]", text) if tag.strip()}))
        elif element.tag in BOOLEAN_CHILDREN.get(parent_tag, set()) and text.lower() in ("true", "false"):
            text = text.capitalize()

    node = Node(tag=element.tag, text=text, attrs=attrs, protected=protected, preserve_order=preserve_order)
    keyed = KEYED_CHILDREN.get(element.tag, {}) if known_context else {}
    seen: dict[str, int] = {}
    for child in element:
        if known_context and element.tag == "Meta" and child.tag in ("Binaries", "HeaderHash"):
            # 二进制池已经折进引用摘要；HeaderHash 是容器字段，另由解码器校验。
            continue
        child_node = _canon(child, element, decoded, known_context and child.tag in known)
        tail = child.tail or ""
        child_node.tail = tail if preserve_order or tail.strip() else ""
        if not preserve_order and child.tag in known and not (element.tag == "String" and child.tag in ("Key", "Value")) and not child_node.tail and (
                _is_empty(child_node) or _is_empty_standard_field(child_node)):
            continue
        if child.tag in keyed:
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
        node.children.append((label, child_node))
    return node


def _is_empty(node: Node) -> bool:
    return not node.text and not node.tail and not node.attrs and not node.protected and not node.children


def _is_empty_standard_field(node: Node) -> bool:
    # 仅折叠明确的普通空字段；未知属性/子节点、重复 Key/Value、混合内容必须保留。
    if node.tag != "String" or node.text or node.attrs or node.protected or node.tail:
        return False
    if any(label not in ("Key", "Value") for label, _ in node.children):
        return False
    children = dict(node.children)
    key, value = children.get("Key"), children.get("Value")
    if key is None or key.text not in STANDARD_FIELDS or key.attrs or key.protected or key.children or key.tail:
        return False
    # 空 Value 的标准保护标记与空值缺失的兼容行为保持不变。
    return value is None or not (value.text or value.attrs or value.children or value.tail)


# ---------- 比较 ----------

def _show(node: Node, reveal: bool, protected_context: bool = False) -> str:
    if (node.protected or protected_context) and not reveal:
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


def _diff(a: Node, b: Node, path: str, ignore: list[str], reveal: bool, out: list[Difference],
          protected_context: bool = False) -> None:
    if _ignored(path, ignore):
        return
    protected_context = protected_context or a.protected or b.protected
    if a.text != b.text:
        out.append(Difference("changed", path, f"{_show(a, reveal, protected_context)} → {_show(b, reveal, protected_context)}", "value"))
    if a.tail != b.tail:
        out.append(Difference("changed", path, "尾随文字变了", "tail"))
    if a.protected != b.protected:
        out.append(Difference("changed", path, f"保护标记 {a.protected} → {b.protected}", "protected"))
    if a.attrs != b.attrs:
        detail = f"属性 {a.attrs} → {b.attrs}" if reveal or not protected_context else "受保护节点的属性变了"
        out.append(Difference("changed", path, detail, "attrs"))

    a_children = dict(a.children)
    b_children = dict(b.children)
    for label, child in a.children:
        child_path = f"{path}/{label}"
        if label not in b_children:
            if not _ignored(child_path, ignore):
                out.append(Difference("removed", child_path, ""))
        else:
            _diff(child, b_children[label], child_path, ignore, reveal, out, protected_context)
    for label, _child in b.children:
        child_path = f"{path}/{label}"
        if label not in a_children and not _ignored(child_path, ignore):
            out.append(Difference("added", child_path, ""))

    preserve_order = a.preserve_order or b.preserve_order
    a_order = [label for label, child in a.children if (preserve_order or child.tag in ORDERED_KEYED) and label in b_children]
    b_order = [label for label, child in b.children if (preserve_order or child.tag in ORDERED_KEYED) and label in a_children]
    if a_order != b_order and not _ignored(path + "#order", ignore):
        out.append(Difference("order", path, "子节点排列顺序变了" if preserve_order else "分组或条目的排列顺序变了"))


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
            if key in OTP_KEYS or key.startswith(OTP_PREFIXES):
                otp.add(key)
            if key.startswith(PASSKEY_PREFIXES):
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
