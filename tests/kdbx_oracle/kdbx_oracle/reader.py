"""只读 KDBX 解码器：给无损测试当“独立对照”。

为什么不直接用 KeePassXC 读：K003 要判断候选库有没有丢数据。如果用
KeePassXC 读两边的文件，KeePassXC 读的时候自己丢掉的东西（例如它不认识的 XML
元素）两边都看不见，结论就会是假的“无损”。这里把解密后的 XML 原样保留，
只把受保护字段还原成明文。

边界：
- 只读，不写。密码学原语来自 cryptography 库；Salsa20 见 salsa20.py。
- 不支持 Argon2d（cryptography 只有 Argon2id）、Twofish、ArcFour 内层流，
  遇到直接报 KdbxUnsupported，不猜。
- 上限只为防止测试被大文件卡死，不是生产的资源策略（那是 K015）。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
import struct
import zlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from uuid import UUID

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from .salsa20 import Salsa20

SIGNATURE_1 = 0x9AA2D903
SIGNATURE_2 = 0xB54BFB67
SIGNATURE_2_KDB1 = 0xB54BFB65

CIPHER_AES256 = UUID("31c1f2e6-bf71-4350-be58-05216afc5aff")
CIPHER_CHACHA20 = UUID("d6038a2b-8b6f-4cb5-a524-339a31dbb59a")
CIPHER_TWOFISH = UUID("ad68f29f-576f-4bb9-a36a-d47af965346c")

# KeePass 和 KeePassXC 给 AES-KDF 用过两个 UUID，算法相同。
KDF_AES = {
    UUID("c9d9f39a-628a-4460-bf74-0d08c18a4fea"),
    UUID("7c02bb82-79a7-4ac0-927d-114a00648238"),
}
KDF_ARGON2D = UUID("ef636ddf-8c29-444b-91f7-a9a403e30a0c")
KDF_ARGON2ID = UUID("9e298b19-56db-4773-b23d-fc3ec6f0a1e6")

SALSA20_IV = bytes.fromhex("e830094b97205d2a")
HEADER_HMAC_INDEX = 0xFFFFFFFFFFFFFFFF

MAX_FILE_BYTES = 64 << 20
MAX_XML_BYTES = 256 << 20
# KeePass 的 Root/Group…/Entry/History/Entry/String/Value 正常不超过几十层。再深就是攻击：
# 递归处理 XML 的代码（包括 semantic.py）会栈溢出。
MAX_XML_DEPTH = 256
MAX_AES_ROUNDS = 1 << 32
MAX_ARGON2_MEMORY = 1 << 30
MAX_ARGON2_ITERATIONS = 1 << 16
_AES_CHUNK_BLOCKS = 1 << 16

# 外层头部字段编号（KDBX 规范）
H_END, H_COMMENT, H_CIPHER, H_COMPRESSION, H_MASTER_SEED = 0, 1, 2, 3, 4
H_TRANSFORM_SEED, H_TRANSFORM_ROUNDS, H_IV, H_PROTECTED_KEY = 5, 6, 7, 8
H_STREAM_START, H_INNER_STREAM_ID, H_KDF, H_PUBLIC_CUSTOM = 9, 10, 11, 12


class KdbxError(Exception):
    """所有读取失败的基类。"""


class KdbxFormatError(KdbxError):
    """不是 KDBX、字段缺失或长度不对、文件被截断。"""


class KdbxIntegrityError(KdbxError):
    """密钥正确，但内容被改过或有多余数据。必须拒绝，不能写回。"""


class KdbxKeyError(KdbxError):
    """密钥错误，或者头部/密文被改——这一步在文件格式上分不出是哪一种。"""


class KdbxUnsupported(KdbxError):
    """合法但本工具不支持的算法或版本。"""


@dataclass
class DecodedKdbx:
    major: int
    minor: int
    cipher: str
    kdf: dict
    compressed: bool
    inner_stream: str
    # KDBX 3.x 的 HeaderHash：match / missing（缺失时调用方应只读）；4.x 为 not-applicable。
    header_hash: str
    root: ET.Element
    # 二进制池：引用编号（字符串）→ (内容, 是否受保护)
    binaries: dict[str, tuple[bytes, bool]] = field(default_factory=dict)
    header_fields: dict[int, bytes] = field(default_factory=dict)

    @property
    def version(self) -> str:
        return f"{self.major}.{self.minor}"


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


# ---------- 密钥 ----------

def keyfile_key(data: bytes) -> bytes:
    """按 KeePassXC 2.7.12 `FileKey::load` 的顺序把密钥文件变成 32 字节：
    XML → 恰好 32 字节 → 恰好 64 个十六进制字符 → 整个文件取 SHA-256。

    跟 KeePassXC 不一致的只有一处：含 DOCTYPE 或不是 UTF-8 的文件不当 XML 解析（避免
    实体展开），直接走后面的规则。所以这两类“合法 KeyFile”在这里会被当成普通文件取哈希。
    """
    if b"<!DOCTYPE" not in data and _non_utf8_reason(data) is None:
        key = _xml_keyfile_key(data)
        if key is not None:
            return key
    if len(data) == 32:
        return data
    if len(data) == 64 and re.fullmatch(rb"[0-9a-fA-F]{64}", data):
        return bytes.fromhex(data.decode("ascii"))
    return _sha256(data)


def _xml_keyfile_key(data: bytes) -> bytes | None:
    """不是 XML 或根元素不是 KeyFile 就返回 None（调用方接着试别的格式）；
    是 KeyFile 但内容不对就报错——KeePassXC 也是这样，不会退回去取哈希。"""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    if root.tag != "KeyFile":
        return None
    version = (root.findtext("Meta/Version") or "").strip()
    node = root.find("Key/Data")
    text = "".join((node.text or "").split()) if node is not None else ""
    try:
        if version.startswith("1.0"):
            return base64.b64decode(text, validate=True)
        if version == "2.0":
            key = bytes.fromhex(text)
            expected = (node.get("Hash") or "").strip().upper() if node is not None else ""
            if _sha256(key)[:4].hex().upper() != expected:
                raise KdbxFormatError("XML 2.0 密钥文件的 Hash 缺失或不符")
            return key
    except (binascii.Error, ValueError) as exc:
        if isinstance(exc, KdbxError):
            raise
        raise KdbxFormatError("XML 密钥文件的 Key/Data 不是合法的 base64/十六进制") from exc
    raise KdbxUnsupported(f"不认识的密钥文件版本：{version!r}")


def composite_key(password: str | None, keyfile: bytes | None) -> bytes:
    parts = []
    if password is not None:
        parts.append(_sha256(password.encode("utf-8")))
    if keyfile is not None:
        parts.append(keyfile_key(keyfile))
    if not parts:
        raise ValueError("至少需要密码或密钥文件之一")
    return _sha256(b"".join(parts))


def _aes_kdf(composite: bytes, seed: bytes, rounds: int) -> bytes:
    if len(seed) != 32:
        raise KdbxFormatError("AES-KDF 种子必须是 32 字节")
    if rounds > MAX_AES_ROUNDS:
        raise KdbxUnsupported(f"AES-KDF 轮数 {rounds} 超过测试上限")
    if rounds == 0:
        return _sha256(composite)
    # 对同一个块反复做 AES-ECB，等价于用全零 IV 的 CBC 加密“该块 + 若干全零块”后
    # 取最后一块：C0 = E(x)，Ci = E(0 xor C(i-1))。这样循环在 C 里跑，百万轮也只要一瞬。
    zero_chunk = bytes(16 * min(rounds, _AES_CHUNK_BLOCKS))
    result = b""
    for half in (composite[:16], composite[16:]):
        encryptor = Cipher(algorithms.AES(seed), modes.CBC(bytes(16))).encryptor()
        last = encryptor.update(half)
        remaining = rounds - 1
        while remaining > 0:
            blocks = min(remaining, _AES_CHUNK_BLOCKS)
            last = encryptor.update(zero_chunk[: 16 * blocks])[-16:]
            remaining -= blocks
        result += last
    return _sha256(result)


def _argon2id(composite: bytes, params: dict) -> bytes:
    salt = _vd_bytes(params, "S")
    lanes = _vd_int(params, "P")
    memory = _vd_int(params, "M")
    iterations = _vd_int(params, "I")
    version = _vd_int(params, "V")
    if version != 0x13:
        raise KdbxUnsupported(f"Argon2 版本 0x{version:x} 不支持，只支持 0x13")
    if memory > MAX_ARGON2_MEMORY or iterations > MAX_ARGON2_ITERATIONS:
        raise KdbxUnsupported("Argon2 参数超过测试上限")
    secret = params.get("K", (None, None))[1]
    associated = params.get("A", (None, None))[1]
    kdf = Argon2id(
        salt=salt,
        length=32,
        iterations=iterations,
        lanes=lanes,
        memory_cost=memory // 1024,
        ad=associated or None,
        secret=secret or None,
    )
    return kdf.derive(composite)


# ---------- 头部 ----------

def _parse_outer_header(data: bytes) -> tuple[int, int, dict[int, bytes], int]:
    if len(data) < 12:
        raise KdbxFormatError("文件太短，不是 KDBX")
    sig1, sig2, version = struct.unpack_from("<III", data, 0)
    if sig1 != SIGNATURE_1:
        raise KdbxFormatError("文件签名不对，不是 KDBX")
    if sig2 == SIGNATURE_2_KDB1:
        raise KdbxUnsupported("KeePass 1.x 的 KDB 格式不支持")
    if sig2 != SIGNATURE_2:
        raise KdbxFormatError("文件签名不对，不是 KDBX")
    major, minor = version >> 16, version & 0xFFFF
    if major == 3:
        size_format = "<H"
    elif major == 4:
        if minor > 1:
            raise KdbxUnsupported(f"KDBX 4.{minor} 高于已知的 4.1，拒绝解析")
        size_format = "<I"
    else:
        raise KdbxUnsupported(f"KDBX 主版本 {major} 不支持")
    size_length = struct.calcsize(size_format)
    fields: dict[int, bytes] = {}
    pos = 12
    while True:
        if pos + 1 + size_length > len(data):
            raise KdbxFormatError("头部被截断")
        field_id = data[pos]
        (size,) = struct.unpack_from(size_format, data, pos + 1)
        pos += 1 + size_length
        if pos + size > len(data):
            raise KdbxFormatError("头部字段被截断")
        value = data[pos : pos + size]
        pos += size
        if field_id == H_END:
            break
        if field_id in fields:
            raise KdbxFormatError(f"头部字段 {field_id} 重复")
        fields[field_id] = value
    return major, minor, fields, pos


def _require(fields: dict[int, bytes], field_id: int, length: int | None = None) -> bytes:
    if field_id not in fields:
        raise KdbxFormatError(f"缺少头部字段 {field_id}")
    value = fields[field_id]
    if length is not None and len(value) != length:
        raise KdbxFormatError(f"头部字段 {field_id} 长度应为 {length}，实为 {len(value)}")
    return value


_VD_TYPES = {0x04: "<I", 0x05: "<Q", 0x08: "<?", 0x0C: "<i", 0x0D: "<q"}


def parse_variant_dictionary(data: bytes) -> dict[str, tuple[int, object]]:
    if len(data) < 2:
        raise KdbxFormatError("VariantDictionary 太短")
    (version,) = struct.unpack_from("<H", data, 0)
    if (version & 0xFF00) > 0x0100:
        raise KdbxUnsupported(f"VariantDictionary 版本 0x{version:04x} 不支持")
    pos = 2
    items: dict[str, tuple[int, object]] = {}
    while True:
        if pos >= len(data):
            raise KdbxFormatError("VariantDictionary 缺少结束标记")
        value_type = data[pos]
        pos += 1
        if value_type == 0:
            break
        if pos + 4 > len(data):
            raise KdbxFormatError("VariantDictionary 被截断")
        (key_length,) = struct.unpack_from("<i", data, pos)
        pos += 4
        key = data[pos : pos + key_length].decode("utf-8")
        pos += key_length
        (value_length,) = struct.unpack_from("<i", data, pos)
        pos += 4
        raw = data[pos : pos + value_length]
        if key_length < 0 or value_length < 0 or len(raw) != value_length:
            raise KdbxFormatError("VariantDictionary 被截断")
        pos += value_length
        if value_type in _VD_TYPES:
            fmt = _VD_TYPES[value_type]
            if struct.calcsize(fmt) != value_length:
                raise KdbxFormatError(f"VariantDictionary 项 {key} 长度不对")
            (value,) = struct.unpack(fmt, raw)
        elif value_type == 0x18:
            value = raw.decode("utf-8")
        elif value_type == 0x42:
            value = raw
        else:
            raise KdbxUnsupported(f"VariantDictionary 类型 0x{value_type:02x} 不支持")
        items[key] = (value_type, value)
    return items


def _vd_bytes(params: dict, key: str) -> bytes:
    if key not in params or not isinstance(params[key][1], bytes):
        raise KdbxFormatError(f"KDF 参数缺少 {key}")
    return params[key][1]


def _vd_int(params: dict, key: str) -> int:
    if key not in params or not isinstance(params[key][1], int):
        raise KdbxFormatError(f"KDF 参数缺少 {key}")
    return params[key][1]


def _derive_transformed_key(major: int, fields: dict[int, bytes], composite: bytes) -> tuple[bytes, dict]:
    if major == 3:
        seed = _require(fields, H_TRANSFORM_SEED, 32)
        (rounds,) = struct.unpack("<Q", _require(fields, H_TRANSFORM_ROUNDS, 8))
        return _aes_kdf(composite, seed, rounds), {"name": "aes-kdf", "rounds": rounds}
    params = parse_variant_dictionary(_require(fields, H_KDF))
    kdf_uuid = UUID(bytes=_vd_bytes(params, "$UUID"))
    if kdf_uuid in KDF_AES:
        rounds = _vd_int(params, "R")
        return _aes_kdf(composite, _vd_bytes(params, "S"), rounds), {"name": "aes-kdf", "rounds": rounds}
    if kdf_uuid == KDF_ARGON2ID:
        info = {
            "name": "argon2id",
            "memory": _vd_int(params, "M"),
            "iterations": _vd_int(params, "I"),
            "parallelism": _vd_int(params, "P"),
        }
        return _argon2id(composite, params), info
    if kdf_uuid == KDF_ARGON2D:
        raise KdbxUnsupported("Argon2d 暂不支持：cryptography 只提供 Argon2id")
    raise KdbxUnsupported(f"未知 KDF {kdf_uuid}")


# ---------- 解密与块流 ----------

def _chacha20(key: bytes, nonce12: bytes, data: bytes) -> bytes:
    # cryptography 的 16 字节 nonce = 4 字节小端计数器 + 12 字节 nonce；KDBX 计数器从 0 开始。
    cipher = Cipher(algorithms.ChaCha20(key, bytes(4) + nonce12), mode=None)
    return cipher.decryptor().update(data)


def _check_cipher(cipher_uuid: UUID, iv: bytes) -> None:
    """在跑 KDF 之前就排除不支持的算法和长度不对的 IV。"""
    if cipher_uuid == CIPHER_AES256:
        if len(iv) != 16:
            raise KdbxFormatError("AES 的 IV 必须是 16 字节")
    elif cipher_uuid == CIPHER_CHACHA20:
        if len(iv) != 12:
            raise KdbxFormatError("ChaCha20 的 IV 必须是 12 字节")
    elif cipher_uuid == CIPHER_TWOFISH:
        raise KdbxUnsupported("Twofish 不支持（KeePass 2.x 里是插件，KeePassXC 原生支持）")
    else:
        raise KdbxUnsupported(f"未知加密算法 {cipher_uuid}")


def _decrypt_raw(cipher_uuid: UUID, key: bytes, iv: bytes, payload: bytes) -> bytes:
    """只解密，不去填充。去填充失败是“密钥错”还是“文件坏”，要由调用方先用
    StreamStartBytes（3.1）或 HMAC（4.x）确认密钥之后才分得清。"""
    if cipher_uuid == CIPHER_CHACHA20:
        return _chacha20(key, iv, payload)
    if not payload or len(payload) % 16:
        raise KdbxFormatError("密文长度不是 16 的倍数：文件被截断或被改")
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    return decryptor.update(payload) + decryptor.finalize()


def _unpad(cipher_uuid: UUID, data: bytes) -> bytes:
    if cipher_uuid == CIPHER_CHACHA20:
        return data
    unpadder = padding.PKCS7(128).unpadder()
    try:
        return unpadder.update(data) + unpadder.finalize()
    except ValueError as exc:
        raise KdbxIntegrityError("密钥正确但填充不对：文件末尾被截断或被追加了数据") from exc


def _gunzip(data: bytes, limit: int = MAX_XML_BYTES) -> bytes:
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = decompressor.decompress(data, limit + 1)
    if len(out) > limit or decompressor.unconsumed_tail:
        raise KdbxUnsupported("解压后超过测试上限，疑似压缩炸弹")
    if not decompressor.eof:
        raise KdbxIntegrityError("gzip 数据被截断")
    if decompressor.unused_data:
        raise KdbxIntegrityError("gzip 数据之后还有多余内容")
    return out


def _block_key(hmac_base: bytes, index: int) -> bytes:
    return _sha512(struct.pack("<Q", index) + hmac_base)


def _read_hmac_blocks(data: bytes, pos: int, hmac_base: bytes) -> bytes:
    payload = bytearray()
    index = 0
    while True:
        if pos + 36 > len(data):
            raise KdbxFormatError("HMAC 块流被截断")
        stored = data[pos : pos + 32]
        (size,) = struct.unpack_from("<i", data, pos + 32)
        pos += 36
        if size < 0 or pos + size > len(data):
            raise KdbxFormatError("HMAC 块被截断")
        block = data[pos : pos + size]
        pos += size
        message = struct.pack("<Q", index) + struct.pack("<i", size) + block
        expected = hmac.new(_block_key(hmac_base, index), message, hashlib.sha256).digest()
        if not hmac.compare_digest(stored, expected):
            raise KdbxIntegrityError(f"第 {index} 块 HMAC 不符：密文被改")
        if size == 0:
            break
        payload += block
        index += 1
    if pos != len(data):
        raise KdbxIntegrityError("结束块之后还有数据：HMAC 管不到这部分，必须拒绝")
    return bytes(payload)


def _read_hashed_blocks(data: bytes) -> bytes:
    payload = bytearray()
    pos = 0
    expected_index = 0
    while True:
        if pos + 40 > len(data):
            raise KdbxIntegrityError("哈希块流被截断")
        index, stored, size = struct.unpack_from("<I32si", data, pos)
        pos += 40
        if index != expected_index:
            raise KdbxIntegrityError(f"哈希块序号应为 {expected_index}，实为 {index}")
        if size == 0:
            if stored != bytes(32):
                raise KdbxIntegrityError("结束块的哈希应为全零")
            break
        if size < 0 or pos + size > len(data):
            raise KdbxIntegrityError("哈希块被截断")
        block = data[pos : pos + size]
        pos += size
        if _sha256(block) != stored:
            raise KdbxIntegrityError(f"第 {index} 块哈希不符")
        payload += block
        expected_index += 1
    if pos != len(data):
        raise KdbxIntegrityError("哈希块流结束后还有数据")
    return bytes(payload)


# ---------- 内层保护流 ----------

class _ChaCha20Stream:
    def __init__(self, key: bytes) -> None:
        digest = _sha512(key)
        self._encryptor = Cipher(algorithms.ChaCha20(digest[:32], bytes(4) + digest[32:44]), mode=None).encryptor()

    def keystream(self, length: int) -> bytes:
        return self._encryptor.update(bytes(length))


def _inner_stream(stream_id: int, key: bytes):
    if stream_id == 0:
        return None, "none"
    if stream_id == 2:
        return Salsa20(_sha256(key), SALSA20_IV), "salsa20"
    if stream_id == 3:
        return _ChaCha20Stream(key), "chacha20"
    raise KdbxUnsupported(f"内层保护流 {stream_id} 不支持（1 是已废弃的 ArcFour）")


def _parse_inner_header(data: bytes) -> tuple[int, bytes, list[tuple[bytes, bool]], int]:
    pos = 0
    stream_id = None
    stream_key = None
    binaries: list[tuple[bytes, bool]] = []
    while True:
        if pos + 5 > len(data):
            raise KdbxFormatError("内层头部被截断")
        field_id = data[pos]
        (size,) = struct.unpack_from("<i", data, pos + 1)
        pos += 5
        if size < 0 or pos + size > len(data):
            raise KdbxFormatError("内层头部字段被截断")
        value = data[pos : pos + size]
        pos += size
        if field_id == 0:
            break
        if field_id == 1:
            if size != 4:
                raise KdbxFormatError("内层流编号应为 4 字节")
            (stream_id,) = struct.unpack("<I", value)
        elif field_id == 2:
            stream_key = value
        elif field_id == 3:
            if size < 1:
                raise KdbxFormatError("内层二进制字段缺少标志位")
            binaries.append((value[1:], bool(value[0] & 0x01)))
        else:
            raise KdbxFormatError(f"未知内层头部字段 {field_id}")
    if stream_id is None or stream_key is None:
        raise KdbxFormatError("内层头部缺少保护流编号或密钥")
    return stream_id, stream_key, binaries, pos


_XML_ENCODING = re.compile(rb"\s*<\?xml[^>]*?encoding\s*=\s*[\"']([^\"']*)[\"']")


def _non_utf8_reason(xml_bytes: bytes) -> str | None:
    """不是 UTF-8 就返回原因。下面的 DOCTYPE 检查按 UTF-8 字节搜，UTF-16 写的 DOCTYPE 搜不到；
    而 expat 会自动识别 UTF-16 并展开里面的实体。KeePass 只写 UTF-8，其他编码一律拒绝。"""
    if xml_bytes.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in xml_bytes:
        return "有 UTF-16/32 的 BOM 或 NUL 字节"
    match = _XML_ENCODING.match(xml_bytes.removeprefix(b"\xef\xbb\xbf"))
    if match and match.group(1).strip().lower() not in (b"utf-8", b"utf8"):
        return f"声明的编码是 {match.group(1).decode('ascii', 'replace')}"
    return None


def _parse_xml(xml_bytes: bytes) -> ET.Element:
    reason = _non_utf8_reason(xml_bytes)
    if reason:
        raise KdbxFormatError(f"XML 不是 UTF-8（{reason}），拒绝解析")
    # KeePass 写出的 XML 从不带 DOCTYPE；带了就可能是实体炸弹或外部实体，直接拒绝。
    # 搜整个文档而不只是开头：前面塞一大段注释就能把 DOCTYPE 推到后面。用户数据里的
    # "<!DOCTYPE" 会被转义成 "&lt;!DOCTYPE"，不会误伤。
    if b"<!DOCTYPE" in xml_bytes or b"<!ENTITY" in xml_bytes:
        raise KdbxFormatError("XML 含 DOCTYPE/ENTITY，拒绝解析")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise KdbxFormatError(f"XML 解析失败：{exc}") from exc
    stack = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        if depth > MAX_XML_DEPTH:
            raise KdbxFormatError(f"XML 嵌套超过 {MAX_XML_DEPTH} 层")
        stack.extend((child, depth + 1) for child in element)
    return root


def _unprotect(root: ET.Element, stream, binaries: dict[str, tuple[bytes, bool]]) -> None:
    """按文档顺序把 Protected="True" 的值还原成明文。

    顺序不能变：保护流是一条连续密钥流，跳过或重排任何一个值，后面的全会解错。
    这正是 ADR-0004 说“不能把旧内层密文剪贴到新流里”的原因。
    """
    meta_binaries = root.find("Meta/Binaries")
    meta_binary_nodes = set(meta_binaries.findall("Binary")) if meta_binaries is not None else set()
    for element in root.iter():
        protected = (element.get("Protected") or "").lower() == "true"
        if element in meta_binary_nodes:
            raw = base64.b64decode(element.text or "", validate=True)
            if protected:
                if stream is None:
                    raise KdbxFormatError("存在受保护值但未声明保护流")
                raw = bytes(a ^ b for a, b in zip(raw, stream.keystream(len(raw))))
            if (element.get("Compressed") or "").lower() == "true":
                raw = _gunzip(raw)
            binaries[element.get("ID", "")] = (raw, protected)
            continue
        if not protected:
            continue
        if stream is None:
            raise KdbxFormatError("存在受保护值但未声明保护流")
        raw = base64.b64decode(element.text or "", validate=True)
        plain = bytes(a ^ b for a, b in zip(raw, stream.keystream(len(raw))))
        try:
            element.text = plain.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise KdbxIntegrityError("受保护值解出来不是 UTF-8：保护流顺序或密钥不对") from exc


# ---------- 入口 ----------

def read_plain_xml(xml_bytes: bytes) -> DecodedKdbx:
    """读 KeePass 的明文 XML（导出格式），转成和 read_kdbx 一样的结构，用来和成品库比较。

    明文 XML 里没有保护流：受保护值用 ProtectInMemory="True" 标记，附件池在 Meta/Binaries。
    """
    root = _parse_xml(xml_bytes)
    if root.tag != "KeePassFile":
        raise KdbxFormatError("XML 根元素不是 KeePassFile")
    binaries: dict[str, tuple[bytes, bool]] = {}
    for element in root.findall("Meta/Binaries/Binary"):
        raw = base64.b64decode(element.text or "", validate=True)
        if (element.get("Compressed") or "").lower() == "true":
            raw = _gunzip(raw)
        binaries[element.get("ID", "")] = (raw, (element.get("Protected") or "").lower() == "true")
    return DecodedKdbx(
        major=0,
        minor=0,
        cipher="none",
        kdf={},
        compressed=False,
        inner_stream="none",
        header_hash="not-applicable",
        root=root,
        binaries=binaries,
    )


def read_kdbx(
    data: bytes,
    password: str | None = None,
    keyfile: bytes | None = None,
    max_xml_bytes: int = MAX_XML_BYTES,
) -> DecodedKdbx:
    """解密并校验一个 KDBX；任何校验失败都抛异常，不返回部分结果。

    max_xml_bytes 只是为了让压缩炸弹测试不必真的解出 256 MiB，不是 keex 的上限（那是 K015）。
    """
    if len(data) > MAX_FILE_BYTES:
        raise KdbxUnsupported("文件超过测试上限")
    major, minor, fields, header_end = _parse_outer_header(data)
    header_bytes = data[:header_end]

    cipher_uuid = UUID(bytes=_require(fields, H_CIPHER, 16))
    (compression,) = struct.unpack("<I", _require(fields, H_COMPRESSION, 4))
    if compression not in (0, 1):
        raise KdbxUnsupported(f"压缩方式 {compression} 不支持")
    master_seed = _require(fields, H_MASTER_SEED, 32)
    iv = _require(fields, H_IV)

    if major == 4:
        # 先做不需要密钥的头部 SHA-256，再跑 KDF。反过来的话，改坏的头部也会先烧一遍
        # 可能很贵的 KDF；超大 KDF 参数样本也靠这个顺序才能测到上限检查。
        if header_end + 64 > len(data):
            raise KdbxFormatError("头部校验值被截断")
        if _sha256(header_bytes) != data[header_end : header_end + 32]:
            raise KdbxIntegrityError("头部 SHA-256 不符：头部损坏或被改")
    _check_cipher(cipher_uuid, iv)

    composite = composite_key(password, keyfile)
    transformed, kdf_info = _derive_transformed_key(major, fields, composite)
    encryption_key = _sha256(master_seed + transformed)
    cipher_name = {CIPHER_AES256: "aes256-cbc", CIPHER_CHACHA20: "chacha20"}.get(cipher_uuid, str(cipher_uuid))

    binaries: dict[str, tuple[bytes, bool]] = {}
    if major == 4:
        pos = header_end
        stored_hmac = data[pos + 32 : pos + 64]
        hmac_base = _sha512(master_seed + transformed + b"\x01")
        expected_hmac = hmac.new(_block_key(hmac_base, HEADER_HMAC_INDEX), header_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(stored_hmac, expected_hmac):
            raise KdbxKeyError("头部 HMAC 不符：密钥错误，或头部被改")
        payload = _read_hmac_blocks(data, pos + 64, hmac_base)
        plain = _unpad(cipher_uuid, _decrypt_raw(cipher_uuid, encryption_key, iv, payload))
        if compression:
            plain = _gunzip(plain, max_xml_bytes)
        stream_id, stream_key, pool, inner_end = _parse_inner_header(plain)
        for index, item in enumerate(pool):
            binaries[str(index)] = item
        xml_bytes = plain[inner_end:]
        header_hash_status = "not-applicable"
    else:
        stream_start = _require(fields, H_STREAM_START, 32)
        stream_key = _require(fields, H_PROTECTED_KEY)
        (stream_id,) = struct.unpack("<I", _require(fields, H_INNER_STREAM_ID, 4))
        raw = _decrypt_raw(cipher_uuid, encryption_key, iv, data[header_end:])
        # 先比 StreamStartBytes 再去填充：开头对得上说明密钥正确，之后的填充错误就是文件坏了。
        # 顺序反了，在 16 字节对齐处截断的文件会被报成“密码错”，用户会反复试密码。
        if raw[:32] != stream_start:
            raise KdbxKeyError("StreamStartBytes 不符：密钥错误，或密文开头被改")
        plain = _unpad(cipher_uuid, raw)
        xml_bytes = _read_hashed_blocks(plain[32:])
        if compression:
            xml_bytes = _gunzip(xml_bytes, max_xml_bytes)
        header_hash_status = "pending"

    if len(xml_bytes) > max_xml_bytes:
        raise KdbxUnsupported("XML 超过测试上限")
    root = _parse_xml(xml_bytes)
    if root.tag != "KeePassFile":
        raise KdbxFormatError("XML 根元素不是 KeePassFile")
    stream, stream_name = _inner_stream(stream_id, stream_key)
    _unprotect(root, stream, binaries)

    if major == 3:
        stored = root.findtext("Meta/HeaderHash")
        if stored is None or not stored.strip():
            header_hash_status = "missing"
        elif base64.b64decode(stored.strip(), validate=True) != _sha256(header_bytes):
            raise KdbxIntegrityError("HeaderHash 不符：头部被改，拒绝打开")
        else:
            header_hash_status = "match"

    return DecodedKdbx(
        major=major,
        minor=minor,
        cipher=cipher_name,
        kdf=kdf_info,
        compressed=bool(compression),
        inner_stream=stream_name,
        header_hash=header_hash_status,
        root=root,
        binaries=binaries,
        header_fields=fields,
    )
