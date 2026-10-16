#!/usr/bin/env python3
"""从黄金样本确定性地变异出损坏/攻击样本，写进 manifest.json（expect = reject 或 read-only）。

用法（在仓库根目录）：

    python3 -I tests/fixtures/kdbx/mutate.py

同一组黄金样本上每次生成的字节完全相同，可以放心重跑。

大部分变异只改字节，不需要密钥。需要改 3.1 密文里的 XML 时（HeaderHash 缺失、压缩炸弹、
XML 攻击），用已知的合成密码解开、改完，再用原来的密钥和 IV 重新加密。这是做测试数据的
变异工具，只用 cryptography 的 AES-CBC，不是 keex 的写入实现。
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
import zlib
from pathlib import Path
from uuid import UUID

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "kdbx_oracle"))

from cryptography.hazmat.primitives import padding  # noqa: E402
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes  # noqa: E402

from kdbx_oracle import reader  # noqa: E402

MANIFEST = HERE / "manifest.json"
BLOCK = 1 << 20


# ---------- 头部工具 ----------

def header_layout(data: bytes) -> tuple[int, list[tuple[int, int, int]], int]:
    """返回 (主版本, [(字段号, 值偏移, 值长度)], 头部结束偏移)，含结束字段。"""
    major = struct.unpack_from("<I", data, 8)[0] >> 16
    size_format = "<H" if major == 3 else "<I"
    size_length = struct.calcsize(size_format)
    pos = 12
    fields = []
    while True:
        field_id = data[pos]
        (size,) = struct.unpack_from(size_format, data, pos + 1)
        fields.append((field_id, pos + 1 + size_length, size))
        pos += 1 + size_length + size
        if field_id == 0:
            return major, fields, pos


def field_offset(data: bytes, field_id: int) -> tuple[int, int]:
    _, fields, _ = header_layout(data)
    for fid, offset, size in fields:
        if fid == field_id:
            return offset, size
    raise KeyError(field_id)


def rebuild_v4_header(data: bytes, replace: dict[int, bytes]) -> bytes:
    """替换 4.x 头部字段并重算头部 SHA-256（不需要密钥）；头部 HMAC 保持原样，所以一定对不上。"""
    _, fields, end = header_layout(data)
    out = bytearray(data[:12])
    for fid, offset, size in fields:
        value = replace.get(fid, data[offset : offset + size])
        out += bytes([fid]) + struct.pack("<I", len(value)) + value
    out = bytes(out)
    return out + hashlib.sha256(out).digest() + data[end + 32 :]


def variant_dictionary(items: list[tuple[int, str, bytes]]) -> bytes:
    out = bytearray(struct.pack("<H", 0x0100))
    for value_type, key, value in items:
        name = key.encode("utf-8")
        out += bytes([value_type]) + struct.pack("<i", len(name)) + name + struct.pack("<i", len(value)) + value
    return bytes(out + b"\x00")


def flip(data: bytes, offset: int) -> bytes:
    return data[:offset] + bytes([data[offset] ^ 0x01]) + data[offset + 1 :]


# ---------- 3.1 重新加密 ----------

def v3_keys(data: bytes, password: str | None, keyfile: bytes | None):
    _, _, fields, header_end = reader._parse_outer_header(data)
    composite = reader.composite_key(password, keyfile)
    transformed, _ = reader._derive_transformed_key(3, fields, composite)
    key = hashlib.sha256(fields[reader.H_MASTER_SEED] + transformed).digest()
    return fields, header_end, key


def v3_inner_xml(data: bytes, password: str | None, keyfile: bytes | None) -> bytes:
    """解出 3.1 的 XML 原文（受保护值仍是加密后的 base64，顺序不动就能原样放回去）。"""
    fields, header_end, key = v3_keys(data, password, keyfile)
    plain = reader._decrypt_payload(reader.CIPHER_AES256, key, fields[reader.H_IV], data[header_end:])
    xml = reader._read_hashed_blocks(plain[32:])
    return reader._gunzip(xml) if struct.unpack("<I", fields[reader.H_COMPRESSION])[0] else xml


def hashed_blocks(payload: bytes) -> bytes:
    out = bytearray()
    index = 0
    for start in range(0, len(payload), BLOCK):
        chunk = payload[start : start + BLOCK]
        out += struct.pack("<I", index) + hashlib.sha256(chunk).digest() + struct.pack("<i", len(chunk)) + chunk
        index += 1
    return bytes(out + struct.pack("<I", index) + bytes(32) + struct.pack("<i", 0))


def gzip_deterministic(chunks) -> bytes:
    compressor = zlib.compressobj(9, zlib.DEFLATED, 31)  # 31 = gzip 封装，头部时间写 0
    out = bytearray()
    for chunk in chunks:
        out += compressor.compress(chunk)
    return bytes(out + compressor.flush())


def v3_reencrypt(data: bytes, password: str | None, keyfile: bytes | None, compressed_xml: bytes) -> bytes:
    fields, header_end, key = v3_keys(data, password, keyfile)
    payload = fields[reader.H_STREAM_START] + hashed_blocks(compressed_xml)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(payload) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(fields[reader.H_IV])).encryptor()
    return data[:header_end] + encryptor.update(padded) + encryptor.finalize()


# ---------- 变异清单 ----------

def m_truncate_half(data, creds):
    return data[: len(data) // 2 + 3]


def m_truncate_header(data, creds):
    _, fields, _ = header_layout(data)
    return data[: fields[2][1] + 3]  # 断在第三个头部字段中间


def m_trailing(data, creds):
    return data + b"keex-trailing-garbage!"


def m_ciphertext_flip(data, creds):
    _, _, end = header_layout(data)
    return flip(data, end + (len(data) - end) // 2)


def m_v3_comment_field(data, creds):
    # 在头部插一个 Comment(1) 字段。密文和密钥都没动，能解开，但 HeaderHash 对不上。
    comment = b"keex-header-tamper"
    return data[:12] + b"\x01" + struct.pack("<H", len(comment)) + comment + data[12:]


def m_v3_headerhash_missing(data, creds):
    xml = v3_inner_xml(data, *creds)
    stripped, count = re.subn(rb"\s*<HeaderHash>[^<]*</HeaderHash>", b"", xml)
    assert count == 1, "黄金样本里应该恰好有一个 HeaderHash"
    return v3_reencrypt(data, *creds, gzip_deterministic([stripped]))


def m_v3_rounds_huge(data, creds):
    offset, size = field_offset(data, reader.H_TRANSFORM_ROUNDS)
    return data[:offset] + struct.pack("<Q", 1 << 62) + data[offset + size :]


def m_v3_cipher_twofish(data, creds):
    offset, size = field_offset(data, reader.H_CIPHER)
    return data[:offset] + reader.CIPHER_TWOFISH.bytes + data[offset + size :]


def m_v3_gzip_bomb(data, creds):
    # 解压后 512 MiB 的空格，压缩后约 0.5 MB。
    head = b'<?xml version="1.0" encoding="UTF-8"?>\n<KeePassFile><Meta><Generator>'
    tail = b"</Generator></Meta><Root/></KeePassFile>\n"
    filler = b" " * (1 << 20)
    return v3_reencrypt(data, *creds, gzip_deterministic([head, *([filler] * 512), tail]))


def m_v3_entity_expansion(data, creds):
    entities = ['<!ENTITY e0 "keex">'] + [
        f'<!ENTITY e{i} "{"&e%d;" % (i - 1) * 10}">' for i in range(1, 10)
    ]
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE KeePassFile [' + "".join(entities) + "]>\n"
        "<KeePassFile><Meta><Generator>&e9;</Generator></Meta><Root/></KeePassFile>\n"
    ).encode()
    return v3_reencrypt(data, *creds, gzip_deterministic([xml]))


def m_v3_external_entity(data, creds):
    xml = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<!DOCTYPE KeePassFile [<!ENTITY ext SYSTEM "file:///etc/hosts">]>\n'
        b"<KeePassFile><Meta><Generator>&ext;</Generator></Meta><Root/></KeePassFile>\n"
    )
    return v3_reencrypt(data, *creds, gzip_deterministic([xml]))


def m_v3_deep_nesting(data, creds):
    depth = 100_000
    xml = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n<KeePassFile><Meta/><Root>'
        + b"<Group>" * depth + b"</Group>" * depth + b"</Root></KeePassFile>\n"
    )
    return v3_reencrypt(data, *creds, gzip_deterministic([xml]))


def m_v4_header_flip(data, creds):
    offset, _ = field_offset(data, reader.H_MASTER_SEED)
    return flip(data, offset)


def m_v4_header_hmac(data, creds):
    offset, size = field_offset(data, reader.H_MASTER_SEED)
    seed = flip(data[offset : offset + size], 0)
    return rebuild_v4_header(data, {reader.H_MASTER_SEED: seed})


def m_v4_block_flip(data, creds):
    _, _, end = header_layout(data)
    return flip(data, end + 64 + 36 + 10)  # 第 0 块数据的第 10 字节


def m_v4_argon2_huge(data, creds):
    params = variant_dictionary([
        (0x42, "$UUID", reader.KDF_ARGON2ID.bytes),
        (0x05, "I", struct.pack("<Q", 2)),
        (0x05, "M", struct.pack("<Q", 1 << 40)),  # 1 TiB
        (0x04, "P", struct.pack("<I", 2)),
        (0x42, "S", bytes(32)),
        (0x04, "V", struct.pack("<I", 0x13)),
    ])
    return rebuild_v4_header(data, {reader.H_KDF: params})


def m_v4_aes_rounds_huge(data, creds):
    offset, size = field_offset(data, reader.H_KDF)
    params = reader.parse_variant_dictionary(data[offset : offset + size])
    rebuilt = variant_dictionary([
        (0x42, "$UUID", params["$UUID"][1]),
        (0x05, "R", struct.pack("<Q", 1 << 62)),
        (0x42, "S", params["S"][1]),
    ])
    return rebuild_v4_header(data, {reader.H_KDF: rebuilt})


def m_v4_version_42(data, creds):
    return data[:8] + struct.pack("<I", (4 << 16) | 2) + data[12:]


def m_kdb1_signature(data, creds):
    return data[:4] + struct.pack("<I", reader.SIGNATURE_2_KDB1) + data[8:]


def m_not_kdbx(data, creds):
    return hashlib.shake_256(b"keex-fixture/not-kdbx").digest(256)


# (ID, 基于哪个黄金样本, 变异, 预期, kdbx_oracle 应抛的异常, 说明)
# 预期里的 reject = keex 必须拒绝打开且不写回；read-only = 可以打开但必须只读。
MUTATIONS = [
    ("R31-TRUNC-HALF", "G31-RICH", m_truncate_half, "reject", "KdbxFormatError", "截掉后一半"),
    ("R31-TRUNC-HEADER", "G31-RICH", m_truncate_header, "reject", "KdbxFormatError", "断在头部字段中间"),
    ("R31-TRAILING", "G31-RICH", m_trailing, "reject", "KdbxFormatError", "密文后追加 22 字节"),
    ("R31-CIPHER-FLIP", "G31-RICH", m_ciphertext_flip, "reject", "KdbxIntegrityError", "密文中间翻转 1 位"),
    ("R31-HEADERHASH-MISMATCH", "G31-RICH", m_v3_comment_field, "reject", "KdbxIntegrityError",
     "头部插入 Comment 字段，密文未动，HeaderHash 不符"),
    ("R31-HEADERHASH-MISSING", "G31-RICH", m_v3_headerhash_missing, "read-only", None,
     "重新加密时去掉 Meta/HeaderHash；内容完整，但头部是否被改无法确认"),
    ("R31-AESKDF-HUGE", "G31-RICH", m_v3_rounds_huge, "reject", "KdbxUnsupported", "AES-KDF 轮数改成 2^62"),
    ("R31-CIPHER-TWOFISH", "G31-RICH", m_v3_cipher_twofish, "reject", "KdbxUnsupported", "加密算法改成 Twofish"),
    ("R31-GZIP-BOMB", "G31-RICH", m_v3_gzip_bomb, "reject", "KdbxUnsupported", "解压后 512 MiB"),
    ("R31-XML-ENTITY", "G31-RICH", m_v3_entity_expansion, "reject", "KdbxFormatError", "实体展开炸弹（10^9 倍）"),
    ("R31-XML-EXTERNAL", "G31-RICH", m_v3_external_entity, "reject", "KdbxFormatError", "外部实体指向 file:///etc/hosts"),
    ("R31-XML-DEEP", "G31-RICH", m_v3_deep_nesting, "reject", "KdbxFormatError", "10 万层嵌套 Group"),
    ("R41-TRUNC-HALF", "G41-RICH", m_truncate_half, "reject", "KdbxFormatError", "截掉后一半"),
    ("R41-TRAILING", "G41-RICH", m_trailing, "reject", "KdbxIntegrityError", "结束块后追加 22 字节"),
    ("R41-HEADER-FLIP", "G41-RICH", m_v4_header_flip, "reject", "KdbxIntegrityError", "主种子翻转 1 位，头部 SHA-256 不符"),
    ("R41-HEADER-HMAC", "G41-RICH", m_v4_header_hmac, "reject", "KdbxKeyError",
     "主种子翻转 1 位并重算 SHA-256，只有头部 HMAC 能发现"),
    ("R41-BLOCK-FLIP", "G41-RICH", m_v4_block_flip, "reject", "KdbxIntegrityError", "第 0 块密文翻转 1 位"),
    ("R41-ARGON2-HUGE", "G41-RICH", m_v4_argon2_huge, "reject", "KdbxUnsupported",
     "KDF 改成 Argon2id、内存 1 TiB，并重算 SHA-256"),
    ("R41-AESKDF-HUGE", "G41-RICH", m_v4_aes_rounds_huge, "reject", "KdbxUnsupported",
     "AES-KDF 轮数改成 2^62，并重算 SHA-256"),
    ("R42-VERSION", "G41-RICH", m_v4_version_42, "reject", "KdbxUnsupported", "版本号改成 4.2"),
    ("R-KDB1", "G31-RICH", m_kdb1_signature, "reject", "KdbxUnsupported", "签名改成 KeePass 1.x 的 KDB"),
    ("R-NOT-KDBX", "G31-RICH", m_not_kdbx, "reject", "KdbxFormatError", "256 字节伪随机数"),
]


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    golden = {s["id"]: s for s in manifest["samples"] if s["expect"] == "open"}
    records = []
    for sample_id, base_id, mutate, expect, error, note in MUTATIONS:
        base = golden[base_id]
        creds = base["credentials"]
        keyfile = (HERE / creds["keyfile"]).read_bytes() if creds["keyfile"] else None
        data = mutate((HERE / base["file"]).read_bytes(), (creds["password"], keyfile))
        target = HERE / (sample_id.lower() + ".kdbx")
        target.write_bytes(data)
        records.append({
            "id": sample_id,
            "file": target.name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "expect": expect,
            "oracle_error": error,
            "method": "mutation",
            "base": base_id,
            "purpose": note,
            "credentials": creds,
        })
        print(f"{sample_id}: {len(data)} 字节")
    manifest["samples"] = list(golden.values()) + records
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
