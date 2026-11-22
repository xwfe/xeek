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

import base64
import hashlib
import hmac
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

from kdbx_oracle import read_kdbx, reader  # noqa: E402
from kdbx_oracle.semantic import summarize  # noqa: E402

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


def build_header(data: bytes, replace: dict[int, bytes] = None, insert: dict[int, bytes] = None) -> bytes:
    """按原头部重拼：替换 replace 里的字段，在结束字段前插入 insert 里的字段。版本号不动。"""
    major, fields, _ = header_layout(data)
    size_format = "<H" if major == 3 else "<I"
    replace = replace or {}
    out = bytearray(data[:12])
    for fid, offset, size in fields:
        if fid == 0:
            for new_id, value in (insert or {}).items():
                out += bytes([new_id]) + struct.pack(size_format, len(value)) + value
        value = replace.get(fid, data[offset : offset + size])
        out += bytes([fid]) + struct.pack(size_format, len(value)) + value
    return bytes(out)


def v4_hmac_base(data: bytes, password: str | None, keyfile: bytes | None) -> bytes:
    _, _, fields, _ = reader._parse_outer_header(data)
    composite = reader.composite_key(password, keyfile)
    transformed, _ = reader._derive_transformed_key(4, fields, composite)
    return hashlib.sha512(fields[reader.H_MASTER_SEED] + transformed + b"\x01").digest()


def v4_assemble(data: bytes, header: bytes, hmac_base: bytes | None = None) -> bytes:
    """新头部 + 重算的 SHA-256 + 头部 HMAC + 原来的 HMAC 块。

    不给 hmac_base 就保留原来的头部 HMAC（一定对不上新头部）；给了就用合成密码重算，
    这样只剩样本要测的那一项检查能拦住它。
    """
    _, _, end = header_layout(data)
    stored = data[end + 32 : end + 64]
    if hmac_base is not None:
        stored = hmac.new(reader._block_key(hmac_base, reader.HEADER_HMAC_INDEX), header, hashlib.sha256).digest()
    return header + hashlib.sha256(header).digest() + stored + data[end + 64 :]


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
    raw = reader._decrypt_raw(reader.CIPHER_AES256, key, fields[reader.H_IV], data[header_end:])
    plain = reader._unpad(reader.CIPHER_AES256, raw)
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
    out += compressor.flush()
    out[9] = 19  # zlib 按构建平台写头部 OS 字节；登记样本生成于 macOS（19），固定后各平台字节一致
    return bytes(out)


def v3_reencrypt(
    data: bytes, password: str | None, keyfile: bytes | None, xml_payload: bytes, header: bytes | None = None
) -> bytes:
    """用原密钥和 IV 重新加密。xml_payload 是已压缩或不压缩的 XML，和头部的压缩标志一致。"""
    fields, header_end, key = v3_keys(data, password, keyfile)
    payload = fields[reader.H_STREAM_START] + hashed_blocks(xml_payload)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(payload) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(fields[reader.H_IV])).encryptor()
    return (header if header is not None else data[:header_end]) + encryptor.update(padded) + encryptor.finalize()


def with_header_hash(xml: bytes, header: bytes) -> bytes:
    """把 XML 里的 Meta/HeaderHash 换成新头部的哈希，让改过的 3.1 头部重新“合法”。"""
    digest = base64.b64encode(hashlib.sha256(header).digest())
    updated, count = re.subn(rb"<HeaderHash>[^<]*</HeaderHash>", b"<HeaderHash>" + digest + b"</HeaderHash>", xml)
    assert count == 1, "黄金样本里应该恰好有一个 HeaderHash"
    return updated


# ---------- 变异清单 ----------

def m_truncate_half(data, creds):
    return data[: len(data) // 2 + 3]


def m_truncate_header(data, creds):
    _, fields, _ = header_layout(data)
    return data[: fields[2][1] + 3]  # 断在第三个头部字段中间


def m_truncate_aligned(data, creds):
    # 断在 16 字节边界上：密文长度检查拦不住，只能靠“密钥对了但填充不对”。
    _, _, end = header_layout(data)
    return data[: end + (len(data) - end) // 32 * 16]


def m_trailing(data, creds):
    return data + b"keex-trailing-garbage!"


def m_trailing_aligned(data, creds):
    return data + seed_bytes("trailing-aligned", 32)


def m_ciphertext_flip(data, creds):
    _, _, end = header_layout(data)
    return flip(data, end + (len(data) - end) // 2)


def m_v3_field_swap(data, creds):
    # 交换 MasterSeed(4) 和 TransformSeed(5) 两个字段的位置。字段值一个没变，密钥、密文都能解开，
    # 只有头部字节变了，所以只有 HeaderHash 能发现。不用“插入 Comment 字段”：KeePassXC 会因为不认识
    # 字段 1 而拒绝，测不到 HeaderHash。
    _, fields, end = header_layout(data)
    order = [f for f in fields]
    i, j = next(k for k, f in enumerate(order) if f[0] == 4), next(k for k, f in enumerate(order) if f[0] == 5)
    order[i], order[j] = order[j], order[i]
    out = bytearray(data[:12])
    for fid, offset, size in order:
        out += bytes([fid]) + struct.pack("<H", size) + data[offset : offset + size]
    return bytes(out) + data[end:]


def m_v3_headerhash_missing(data, creds):
    xml = v3_inner_xml(data, *creds)
    stripped, count = re.subn(rb"\s*<HeaderHash>[^<]*</HeaderHash>", b"", xml)
    assert count == 1, "黄金样本里应该恰好有一个 HeaderHash"
    return v3_reencrypt(data, *creds, gzip_deterministic([stripped]))


def m_v3_rounds_huge(data, creds):
    offset, size = field_offset(data, reader.H_TRANSFORM_ROUNDS)
    return data[:offset] + struct.pack("<Q", 1 << 62) + data[offset + size :]


def m_v3_cipher_unknown(data, creds):
    # 算法换成一个不存在的 UUID，但内容仍用 AES 加密，并把 HeaderHash 更新到新头部。
    # 这样一个无视算法 UUID、直接按 AES 解的实现会成功打开它——样本只测“认不认算法”。
    header = build_header(data, replace={reader.H_CIPHER: seed_bytes("unknown-cipher", 16)})
    xml = with_header_hash(v3_inner_xml(data, *creds), header)
    return v3_reencrypt(data, *creds, gzip_deterministic([xml]), header=header)


def m_v3_uncompressed(data, creds):
    # 不压缩的合法 3.1 库。keepassxc-cli 不能关压缩，只好由这里重新加密。
    header = build_header(data, replace={reader.H_COMPRESSION: struct.pack("<I", 0)})
    xml = with_header_hash(v3_inner_xml(data, *creds), header)
    return v3_reencrypt(data, *creds, xml, header=header)


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
    # 插入一个 PublicCustomData(12) 字段并重算 SHA-256。这个字段不参与密钥派生，块 HMAC 照样
    # 对得上，只有头部 HMAC 能发现。改主种子就不行：块 HMAC 的密钥也从主种子来。
    public = variant_dictionary([(0x18, "keex.tamper", b"synthetic")])
    return v4_assemble(data, build_header(data, insert={reader.H_PUBLIC_CUSTOM: public}))


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
    return v4_assemble(data, build_header(data, replace={reader.H_KDF: params}))


def m_v4_aes_rounds_huge(data, creds):
    offset, size = field_offset(data, reader.H_KDF)
    params = reader.parse_variant_dictionary(data[offset : offset + size])
    rebuilt = variant_dictionary([
        (0x42, "$UUID", params["$UUID"][1]),
        (0x05, "R", struct.pack("<Q", 1 << 62)),
        (0x42, "S", params["S"][1]),
    ])
    return v4_assemble(data, build_header(data, replace={reader.H_KDF: rebuilt}))


def m_v4_version_42(data, creds):
    # 版本号改成 4.2，并用合成密码重算 SHA-256 和头部 HMAC：只有版本检查能拦住它。
    header = build_header(data)
    header = header[:8] + struct.pack("<I", (4 << 16) | 2) + header[12:]
    return v4_assemble(data, header, v4_hmac_base(data, *creds))


def m_kdb1_signature(data, creds):
    return data[:4] + struct.pack("<I", reader.SIGNATURE_2_KDB1) + data[8:]


def m_not_kdbx(data, creds):
    return seed_bytes("not-kdbx", 256)


def seed_bytes(name: str, length: int) -> bytes:
    return hashlib.shake_256(b"keex-fixture/" + name.encode()).digest(length)


# (ID, 基于哪个黄金样本, 变异, 预期, kdbx_oracle 应抛的异常, 异常信息里必须有的片段, 说明)
# 预期：reject = keex 必须拒绝打开且不写回；read-only = 可以打开但必须只读；
# open = 变异后仍是合法库，内容必须和基础样本完全一致。
# 异常信息片段确保样本是被它声称的那一项检查拦住的，而不是碰巧被别的检查拦住。
MUTATIONS = [
    ("R31-TRUNC-HALF", "G31-RICH", m_truncate_half, "reject", "KdbxFormatError", "16 的倍数", "截掉后一半（不对齐）"),
    ("R31-TRUNC-ALIGNED", "G31-RICH", m_truncate_aligned, "reject", "KdbxIntegrityError", "填充不对",
     "在 16 字节边界截断，长度检查拦不住"),
    ("R31-TRUNC-HEADER", "G31-RICH", m_truncate_header, "reject", "KdbxFormatError", "头部字段被截断", "断在头部字段中间"),
    ("R31-TRAILING", "G31-RICH", m_trailing, "reject", "KdbxFormatError", "16 的倍数", "密文后追加 22 字节"),
    ("R31-TRAILING-ALIGNED", "G31-RICH", m_trailing_aligned, "reject", "KdbxIntegrityError", "填充不对",
     "密文后追加 32 字节（对齐）"),
    ("R31-CIPHER-FLIP", "G31-RICH", m_ciphertext_flip, "reject", "KdbxIntegrityError", "哈希不符", "密文中间翻转 1 位"),
    ("R31-HEADERHASH-MISMATCH", "G31-RICH", m_v3_field_swap, "reject", "KdbxIntegrityError", "HeaderHash 不符",
     "交换两个头部字段的位置，值和密文都不变，只有 HeaderHash 能发现"),
    ("R31-HEADERHASH-MISSING", "G31-RICH", m_v3_headerhash_missing, "read-only", None, None,
     "重新加密时去掉 Meta/HeaderHash；内容完整，但头部是否被改无法确认"),
    ("R31-AESKDF-HUGE", "G31-RICH", m_v3_rounds_huge, "reject", "KdbxUnsupported", "AES-KDF 轮数", "AES-KDF 轮数改成 2^62"),
    ("R31-CIPHER-UNKNOWN", "G31-RICH", m_v3_cipher_unknown, "reject", "KdbxUnsupported", "未知加密算法",
     "算法改成未知 UUID，内容仍是 AES，HeaderHash 已更新"),
    ("R31-GZIP-BOMB", "G31-RICH", m_v3_gzip_bomb, "reject", "KdbxUnsupported", "压缩炸弹", "解压后 512 MiB"),
    ("R31-XML-ENTITY", "G31-RICH", m_v3_entity_expansion, "reject", "KdbxFormatError", "DOCTYPE", "实体展开炸弹（10^9 倍）"),
    ("R31-XML-EXTERNAL", "G31-RICH", m_v3_external_entity, "reject", "KdbxFormatError", "DOCTYPE",
     "外部实体指向 file:///etc/hosts"),
    ("R31-XML-DEEP", "G31-RICH", m_v3_deep_nesting, "reject", "KdbxFormatError", "嵌套超过", "10 万层嵌套 Group"),
    ("V31-UNCOMPRESSED", "G31-RICH", m_v3_uncompressed, "open", None, None,
     "压缩标志改成 0、XML 不压缩重新加密、HeaderHash 已更新；不是参考客户端写的"),
    ("R41-TRUNC-HALF", "G41-RICH", m_truncate_half, "reject", "KdbxFormatError", "HMAC 块被截断", "截掉后一半"),
    ("R41-TRAILING", "G41-RICH", m_trailing, "reject", "KdbxIntegrityError", "结束块之后", "结束块后追加 22 字节"),
    ("R41-HEADER-FLIP", "G41-RICH", m_v4_header_flip, "reject", "KdbxIntegrityError", "头部 SHA-256",
     "主种子翻转 1 位，不重算 SHA-256"),
    ("R41-HEADER-HMAC", "G41-RICH", m_v4_header_hmac, "reject", "KdbxKeyError", "头部 HMAC",
     "插入 PublicCustomData 并重算 SHA-256，只有头部 HMAC 能发现"),
    ("R41-BLOCK-FLIP", "G41-RICH", m_v4_block_flip, "reject", "KdbxIntegrityError", "块 HMAC 不符", "第 0 块密文翻转 1 位"),
    ("R41-ARGON2-HUGE", "G41-RICH", m_v4_argon2_huge, "reject", "KdbxUnsupported", "Argon2 参数",
     "KDF 改成 Argon2id、内存 1 TiB，并重算 SHA-256"),
    ("R41-AESKDF-HUGE", "G41-RICH", m_v4_aes_rounds_huge, "reject", "KdbxUnsupported", "AES-KDF 轮数",
     "AES-KDF 轮数改成 2^62，并重算 SHA-256"),
    ("R42-VERSION", "G41-RICH", m_v4_version_42, "reject", "KdbxUnsupported", "4.2",
     "版本号改成 4.2，并重算 SHA-256 和头部 HMAC"),
    ("R-KDB1", "G31-RICH", m_kdb1_signature, "reject", "KdbxUnsupported", "KDB", "签名改成 KeePass 1.x 的 KDB"),
    ("R-NOT-KDBX", "G31-RICH", m_not_kdbx, "reject", "KdbxFormatError", "签名", "256 字节伪随机数"),
]


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    golden = {s["id"]: s for s in manifest["samples"] if s["method"] != "mutation"}
    old = {s["file"] for s in manifest["samples"] if s["method"] == "mutation"}
    records = []
    for sample_id, base_id, mutate, expect, error, reason, note in MUTATIONS:
        base = golden[base_id]
        creds = base["credentials"]
        keyfile = (HERE / creds["keyfile"]).read_bytes() if creds["keyfile"] else None
        data = mutate((HERE / base["file"]).read_bytes(), (creds["password"], keyfile))
        target = HERE / (sample_id.lower() + ".kdbx")
        target.write_bytes(data)
        record = {
            "id": sample_id,
            "file": target.name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "expect": expect,
            "oracle_error": error,
            "oracle_reason": reason,
            "method": "mutation",
            "base": base_id,
            "purpose": note,
            "credentials": creds,
        }
        if expect == "open":
            record["summary"] = summarize(read_kdbx(data, password=creds["password"], keyfile=keyfile))
        records.append(record)
        print(f"{sample_id}: {len(data)} 字节")
    # 清单里已经不存在的旧变异样本（比如改名前的文件）一并删掉，否则会留在目录里没人管。
    for stale in old - {r["file"] for r in records}:
        (HERE / stale).unlink(missing_ok=True)
        print(f"删除已不在清单里的 {stale}")
    manifest["samples"] = list(golden.values()) + records
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
