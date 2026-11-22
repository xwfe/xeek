"""合成样本的源 XML：完全确定，同一个样本每次生成的字节都一样。

UUID、时间、附件、SSH/Passkey 密钥都从固定种子派生。好处是测试可以随时重建源 XML，
拿它和提交的样本比，不用把含明文私钥的 XML 放进仓库。

这些密钥的种子就写在这里，等于公开。它们只用来测保留和解析，**绝不能**加进任何
`authorized_keys` 或注册到任何网站。
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import struct
import xml.etree.ElementTree as ET

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

LEVELS = ("3.1", "4.0", "4.1")

# 1x1 透明 PNG，当自定义图标。
ICON_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
TOTP_SECRET = "JBSWY3DPEHPK3PXP"  # RFC 4226/6238 文档和各客户端常用的公开示例种子
P256_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551


def seed(name: str, length: int = 32) -> bytes:
    return hashlib.shake_256(b"keex-fixture/" + name.encode("utf-8")).digest(length)


def uid(name: str) -> str:
    return base64.b64encode(seed("uuid/" + name, 16)).decode()


def uid_ref(name: str) -> str:
    """字段引用 {REF:..@I:..} 里用的大写十六进制 UUID。"""
    return seed("uuid/" + name, 16).hex().upper()


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def at_least(level: str, target: str) -> bool:
    return LEVELS.index(level) >= LEVELS.index(target)


def day(n: int, month: int = 1) -> str:
    return f"2026-{month:02d}-{n:02d}T08:00:00Z"


# ---------- 合成密钥 ----------

def _ssh_string(data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + data


def openssh_ed25519(name: str, comment: str) -> bytes:
    """不加密的 OpenSSH ed25519 私钥文件。

    自己拼而不用 cryptography 导出：后者的 checkint 是随机数，每次字节不同，源 XML
    就不确定了。格式见 OpenSSH 的 PROTOCOL.key；生成器会用 cryptography 把它读回来核对。
    """
    private = ed25519.Ed25519PrivateKey.from_private_bytes(seed("ssh/" + name))
    raw_private = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    raw_public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    public_blob = _ssh_string(b"ssh-ed25519") + _ssh_string(raw_public)
    check = seed("ssh-check/" + name, 4)
    section = (
        check + check + _ssh_string(b"ssh-ed25519") + _ssh_string(raw_public)
        + _ssh_string(raw_private + raw_public) + _ssh_string(comment.encode("utf-8"))
    )
    section += bytes(range(1, 9 - len(section) % 8)) if len(section) % 8 else b""
    body = (
        b"openssh-key-v1\x00" + _ssh_string(b"none") + _ssh_string(b"none") + _ssh_string(b"")
        + struct.pack(">I", 1) + _ssh_string(public_blob) + _ssh_string(section)
    )
    encoded = base64.b64encode(body).decode()
    lines = [encoded[i : i + 70] for i in range(0, len(encoded), 70)]
    return ("-----BEGIN OPENSSH PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END OPENSSH PRIVATE KEY-----\n").encode()


def passkey_pem(name: str) -> str:
    scalar = int.from_bytes(seed("passkey/" + name), "big") % (P256_ORDER - 1) + 1
    key = ec.derive_private_key(scalar, ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()


def keeagent_settings(attachment: str) -> bytes:
    """按 KeeAgent 的 EntrySettings 格式手写，UTF-16LE 带 BOM（KeeAgent 只读 UTF-16）。

    比 KeePassXC 2.7.12 自己写的多了 UseDestinationConstraintWhenAdding/DestinationConstraints，
    用来确认附件是按字节保留的。没有用 KeeAgent 本体验证过。
    """
    text = (
        '<?xml version="1.0" encoding="utf-16"?>\r\n'
        '<EntrySettings xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\r\n'
        "  <AllowUseOfSshKey>true</AllowUseOfSshKey>\r\n"
        "  <AddAtDatabaseOpen>true</AddAtDatabaseOpen>\r\n"
        "  <RemoveAtDatabaseClose>true</RemoveAtDatabaseClose>\r\n"
        "  <UseConfirmConstraintWhenAdding>true</UseConfirmConstraintWhenAdding>\r\n"
        "  <UseLifetimeConstraintWhenAdding>false</UseLifetimeConstraintWhenAdding>\r\n"
        "  <LifetimeConstraintDuration>600</LifetimeConstraintDuration>\r\n"
        "  <UseDestinationConstraintWhenAdding>false</UseDestinationConstraintWhenAdding>\r\n"
        "  <DestinationConstraints />\r\n"
        "  <Location>\r\n"
        "    <SelectedType>attachment</SelectedType>\r\n"
        f"    <AttachmentName>{attachment}</AttachmentName>\r\n"
        "    <SaveAttachmentToTempFile>false</SaveAttachmentToTempFile>\r\n"
        "    <FileName />\r\n"
        "  </Location>\r\n"
        "</EntrySettings>"
    )
    return b"\xff\xfe" + text.encode("utf-16-le")


# ---------- XML 构件 ----------

def E(tag: str, text: str | None = None, children=(), **attrs: str) -> ET.Element:
    element = ET.Element(tag, attrs)
    if text is not None:
        element.text = text
    for child in children:
        if child is not None:
            element.append(child)
    return element


def times(created: str, modified: str | None = None, expires: str | None = None) -> ET.Element:
    modified = modified or created
    return E("Times", children=[
        E("LastModificationTime", modified),
        E("CreationTime", created),
        E("LastAccessTime", modified),
        E("ExpiryTime", expires or created),
        E("Expires", "True" if expires else "False"),
        E("UsageCount", "0"),
        E("LocationChanged", created),
    ])


def field(key: str, value: str, protected: bool = False) -> ET.Element:
    value_element = E("Value", value, ProtectInMemory="True") if protected else E("Value", value)
    return E("String", children=[E("Key", key), value_element])


def custom_data(level: str, items: dict[str, str], modified: str) -> ET.Element | None:
    if not items:
        return None
    return E("CustomData", children=[
        E("Item", children=[
            E("Key", key), E("Value", value),
            E("LastModificationTime", modified) if at_least(level, "4.1") else None,
        ])
        for key, value in items.items()
    ])


def gzip_fixed(data: bytes) -> bytes:
    """gzip 头部 OS 字节由 zlib 的构建平台决定；登记样本生成于 macOS（19），固定后各平台字节一致。"""
    packed = bytearray(gzip.compress(data, mtime=0))
    packed[9] = 19
    return bytes(packed)


class Pool:
    """Meta/Binaries 附件池；内容相同的附件共用一个编号（KeePass 也这样去重）。"""

    def __init__(self) -> None:
        self.items: list[bytes] = []

    def ref(self, data: bytes) -> str:
        if data not in self.items:
            self.items.append(data)
        return str(self.items.index(data))

    def element(self) -> ET.Element:
        return E("Binaries", children=[
            E("Binary", base64.b64encode(gzip_fixed(data)).decode(), ID=str(i), Compressed="True")
            for i, data in enumerate(self.items)
        ])


def entry(
    level: str,
    pool: Pool,
    name: str,
    fields: list[tuple[str, str, bool]],
    *,
    created: str = day(1),
    modified: str | None = None,
    expires: str | None = None,
    tags: str | None = None,
    attachments: dict[str, bytes] | None = None,
    history: list[ET.Element] = (),
    custom: dict[str, str] | None = None,
    autotype: ET.Element | None = None,
    icon: str = "0",
    custom_icon: str | None = None,
    colors: tuple[str, str] | None = None,
    override_url: str | None = None,
    previous_parent: str | None = None,
) -> ET.Element:
    modified = modified or created
    return E("Entry", children=[
        E("UUID", uid(name)),
        E("IconID", icon),
        E("CustomIconUUID", custom_icon) if custom_icon else None,
        E("ForegroundColor", colors[0]) if colors else None,
        E("BackgroundColor", colors[1]) if colors else None,
        E("OverrideURL", override_url) if override_url else None,
        E("QualityCheck", "False") if at_least(level, "4.1") else None,
        E("Tags", tags) if tags else None,
        E("PreviousParentGroup", previous_parent) if previous_parent and at_least(level, "4.1") else None,
        times(created, modified, expires),
        *[field(key, value, protected) for key, value, protected in fields],
        *[
            E("Binary", children=[E("Key", key), E("Value", Ref=pool.ref(data))])
            for key, data in (attachments or {}).items()
        ],
        autotype if autotype is not None else E("AutoType", children=[
            E("Enabled", "True"), E("DataTransferObfuscation", "0"), E("DefaultSequence", ""),
        ]),
        custom_data(level, custom or {}, modified) if at_least(level, "4.0") else None,
        E("History", children=history) if history else None,
    ])


def group(
    level: str,
    name: str,
    title: str,
    children: list[ET.Element],
    *,
    notes: str = "",
    icon: str = "48",
    tags: str | None = None,
    custom: dict[str, str] | None = None,
    custom_icon: str | None = None,
    previous_parent: str | None = None,
    created: str = day(1),
) -> ET.Element:
    return E("Group", children=[
        E("UUID", uid(name)),
        E("Name", title),
        E("Notes", notes),
        E("IconID", icon),
        E("CustomIconUUID", custom_icon) if custom_icon else None,
        times(created),
        E("IsExpanded", "True"),
        E("DefaultAutoTypeSequence", ""),
        E("EnableAutoType", "null"),
        E("EnableSearching", "null"),
        E("LastTopVisibleEntry", "AAAAAAAAAAAAAAAAAAAAAA=="),
        E("PreviousParentGroup", previous_parent) if previous_parent and at_least(level, "4.1") else None,
        E("Tags", tags) if tags and at_least(level, "4.1") else None,
        custom_data(level, custom or {}, created) if at_least(level, "4.0") else None,
        *children,
    ])


def meta(level: str, sample_id: str, pool: Pool, *, recycle_bin: str | None, icons: bool) -> ET.Element:
    return E("Meta", children=[
        E("Generator", "keex-fixture-source"),
        E("DatabaseName", f"合成测试库 {sample_id}"),
        E("DatabaseNameChanged", day(1)),
        E("DatabaseDescription", "keex K002 合成样本，不含任何真实数据"),
        E("DatabaseDescriptionChanged", day(1)),
        E("DefaultUserName", "synthetic-user"),
        E("DefaultUserNameChanged", day(1)),
        E("MaintenanceHistoryDays", "365"),
        E("Color", "#336699"),
        E("MasterKeyChanged", day(1)),
        E("MasterKeyChangeRec", "-1"),
        E("MasterKeyChangeForce", "-1"),
        E("MemoryProtection", children=[
            E("ProtectTitle", "False"), E("ProtectUserName", "False"), E("ProtectPassword", "True"),
            E("ProtectURL", "False"), E("ProtectNotes", "False"),
        ]),
        E("CustomIcons", children=[
            E("Icon", children=[
                E("UUID", uid("icon")),
                E("Data", base64.b64encode(ICON_PNG).decode()),
                E("Name", "合成图标") if at_least(level, "4.1") else None,
                E("LastModificationTime", day(1)) if at_least(level, "4.1") else None,
            ]),
        ] if icons else []),
        E("RecycleBinEnabled", "True"),
        E("RecycleBinUUID", uid(recycle_bin) if recycle_bin else "AAAAAAAAAAAAAAAAAAAAAA=="),
        E("RecycleBinChanged", day(1)),
        E("EntryTemplatesGroup", "AAAAAAAAAAAAAAAAAAAAAA=="),
        E("EntryTemplatesGroupChanged", day(1)),
        E("HistoryMaxItems", "10"),
        E("HistoryMaxSize", "6291456"),
        E("LastSelectedGroup", "AAAAAAAAAAAAAAAAAAAAAA=="),
        E("LastTopVisibleGroup", "AAAAAAAAAAAAAAAAAAAAAA=="),
        pool.element(),
        custom_data(level, {"keex.fixture": sample_id}, day(1)) if at_least(level, "4.0") else E("CustomData"),
    ])


def document(meta_element: ET.Element, root_group: ET.Element, deleted: list[tuple[str, str]] = ()) -> bytes:
    root = E("KeePassFile", children=[
        meta_element,
        E("Root", children=[
            root_group,
            E("DeletedObjects", children=[
                E("DeletedObject", children=[E("UUID", uid(name)), E("DeletionTime", when)])
                for name, when in deleted
            ]),
        ]),
    ])
    ET.indent(root, space="\t")
    body = ET.tostring(root, encoding="unicode")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + body + "\n").encode("utf-8")


# ---------- 样本内容 ----------

def long_text(lines: int) -> str:
    return "".join(f"合成长文本第 {i:05d} 行，Long synthetic line {i:05d}.\n" for i in range(lines))


def rich(level: str, sample_id: str) -> bytes:
    """功能最全的样本；只放目标格式版本支持的特性，所以 KeePassXC 会正好写成该版本。"""
    pool = Pool()
    notes_txt = "合成附件：第一行\nsecond line\n".encode("utf-8")
    shared_txt = b"shared attachment referenced by two entries and one history item\n"
    blob = bytes(range(256)) * 4
    icon = uid("icon")
    old_parent = uid("group/web")

    login_history = [
        entry(level, pool, "login", [
            ("Title", "登录 Login", False), ("UserName", "synthetic-user", False),
            ("Password", "合成-旧口令-1", True), ("URL", "https://login.example.com/", False),
            ("Notes", "", False), ("X-Secret", "未知受保护字段-旧版本-1", True),
        ], created=day(1), modified=day(2), attachments={"blob.bin": blob, "shared.txt": shared_txt}),
        entry(level, pool, "login", [
            ("Title", "登录 Login", False), ("UserName", "synthetic-user", False),
            ("Password", "合成-旧口令-2", True), ("URL", "https://login.example.com/", False),
            ("Notes", "", False), ("X-Old-Protected", "只在历史里的受保护字段", True),
        ], created=day(1), modified=day(3)),
    ]
    login = entry(level, pool, "login", [
        ("Title", "登录 Login", False),
        ("UserName", "synthetic-user", False),
        ("Password", "合成-当前口令-Ünï🔑", True),
        ("URL", "https://login.example.com/path?q=1&r=二", False),
        ("Notes", "第一行\n第二行 with emoji 🧪\n\t制表符缩进", False),
        ("X-Secret", "未知受保护字段-当前", True),
        ("X-Plain", "普通自定义字段", False),
        ("X-Empty", "", False),
        ("KP2A_URL_1", "https://alt.example.com/", False),
    ], created=day(1), modified=day(4), tags="合成;web", colors=("#FF0000", "#00FF00"),
        override_url="cmd://synthetic-browser {URL}", custom_icon=icon,
        attachments={"notes.txt": notes_txt, "shared.txt": shared_txt},
        custom={"keex.fixture.entry": "login"}, history=login_history,
        autotype=E("AutoType", children=[
            E("Enabled", "True"), E("DataTransferObfuscation", "1"),
            E("DefaultSequence", "{USERNAME}{TAB}{PASSWORD}{ENTER}"),
            E("Association", children=[E("Window", "合成窗口 * example"), E("KeystrokeSequence", "{PASSWORD}{ENTER}")]),
        ]))

    login_ref = uid_ref("login")
    web = group(level, "group/web", "网站 Web", [
        login,
        entry(level, pool, "reference", [
            ("Title", "字段引用 Reference", False),
            ("UserName", f"{{REF:U@I:{login_ref}}}", False),
            ("Password", f"{{REF:P@I:{login_ref}}}", True),
            ("Notes", f"标题引用 {{REF:T@I:{login_ref}}}", False),
        ], attachments={"shared.txt": shared_txt}),
        entry(level, pool, "otp-keepassxc", [
            ("Title", "OTP KeePassXC 格式", False),
            ("otp", f"otpauth://totp/keex:synthetic%40example.com?secret={TOTP_SECRET}&period=30&digits=6&issuer=keex", True),
        ]),
        entry(level, pool, "otp-keepass", [
            ("Title", "OTP KeePass 2.x 原生格式", False),
            ("TimeOtp-Secret-Base32", TOTP_SECRET, True),
            ("TimeOtp-Length", "8", False),
            ("TimeOtp-Period", "60", False),
            ("TimeOtp-Algorithm", "HMAC-SHA-256", False),
        ]),
        entry(level, pool, "otp-legacy", [
            ("Title", "OTP 旧插件格式", False),
            ("TOTP Seed", TOTP_SECRET, True),
            ("TOTP Settings", "30;6", False),
        ]),
        entry(level, pool, "expired", [("Title", "已过期 Expired", False), ("Password", "expired-pw", True)],
              expires=day(1, month=6)),
    ], tags="合成组标签", custom={"keex.fixture.group": "web"}, notes="组备注", custom_icon=icon)

    passkeys = group(level, "group/passkey", "Passkey", [
        entry(level, pool, "passkey", [
            ("Title", "Passkey KeePassXC 字段", False),
            ("UserName", "synthetic-user", False),
            ("URL", "https://passkey.example.com", False),
            ("KPEX_PASSKEY_USERNAME", "synthetic-user", False),
            ("KPEX_PASSKEY_CREDENTIAL_ID", b64url(seed("passkey-credential", 16)), False),
            ("KPEX_PASSKEY_PRIVATE_KEY_PEM", passkey_pem("current"), True),
            ("KPEX_PASSKEY_RELYING_PARTY", "passkey.example.com", False),
            ("KPEX_PASSKEY_USER_HANDLE", b64url(seed("passkey-user", 16)), True),
            ("KPEX_PASSKEY_FLAG_BE", "1", False),
            ("KPEX_PASSKEY_FLAG_BS", "1", False),
        ], tags="Passkey"),
        entry(level, pool, "passkey-legacy", [
            ("Title", "Passkey 旧字段名", False),
            ("URL", "https://legacy.passkey.example.com", False),
            ("KPXC_PASSKEY_USERNAME", "synthetic-legacy-user", False),
            ("KPEX_PASSKEY_CREDENTIAL_ID", b64url(seed("passkey-legacy-credential", 16)), False),
            ("KPEX_PASSKEY_PRIVATE_KEY_PEM", passkey_pem("legacy"), True),
            ("KPEX_PASSKEY_RELYING_PARTY", "legacy.passkey.example.com", False),
            ("KPEX_PASSKEY_GENERATED_USER_ID", b64url(seed("passkey-legacy-user", 16)), True),
        ], tags="Passkey"),
    ])

    ssh = group(level, "group/ssh", "SSH", [
        entry(level, pool, "keeagent", [
            ("Title", "KeeAgent ed25519", False),
            ("UserName", "synthetic", False),
            ("Password", "", True),
            ("Notes", "公开的合成密钥，绝不能加进任何 authorized_keys", False),
        ], attachments={
            "KeeAgent.settings": keeagent_settings("id_ed25519"),
            "id_ed25519": openssh_ed25519("keeagent", "keex-synthetic"),
        }),
    ])

    nested = group(level, "group/level1", "层级1", [
        group(level, "group/level2", "层级2", [
            group(level, "group/level3", "层级3", [
                entry(level, pool, "deep", [("Title", "深层条目 Deep", False), ("Password", "deep-pw", True)]),
            ]),
        ]),
    ])

    recycle = group(level, "group/recycle", "回收站 Recycle Bin", [
        entry(level, pool, "deleted", [("Title", "已删除条目 Deleted", False), ("Password", "deleted-pw", True)],
              previous_parent=old_parent, modified=day(5)),
    ], icon="43")

    edge = entry(level, pool, "edge", [
        ("Title", "", False),
        ("UserName", "", False),
        ("Password", "", True),
        ("URL", "https://例子.测试/登录", False),
        ("Notes", long_text(1500), False),
        ("X-Long-Protected", "受" * 4096, True),
        ("自定义中文字段名", "值", False),
    ])

    root_group = group(level, "group/root", "合成根 Root", [edge, web, passkeys, ssh, nested, recycle])
    deleted = [("purged-1", day(6)), ("purged-2", day(7))]
    return document(meta(level, sample_id, pool, recycle_bin="group/recycle", icons=True), root_group, deleted)


def big(level: str, sample_id: str, size: int = 1_200_000) -> bytes:
    """一个不可压缩的大附件，让密文超过 1 MiB、分成至少两个 HMAC/哈希块。"""
    pool = Pool()
    payload = hashlib.shake_256(b"keex-fixture/big").digest(size)
    root_group = group(level, "group/root", "合成根 Root", [
        entry(level, pool, "big", [("Title", "大附件 Big", False), ("Password", "big-pw", True)],
              attachments={"random.bin": payload}),
    ])
    return document(meta(level, sample_id, pool, recycle_bin=None, icons=False), root_group)


BUILDERS = {"rich": rich, "big": big}


def build(kind: str, level: str, sample_id: str) -> bytes:
    return BUILDERS[kind](level, sample_id)
