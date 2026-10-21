#!/usr/bin/env python3
"""公开合成 KDBX 4.x 的认证负载变异；固定输入，不提供通用保存接口。

只复用已有 cryptography 原语；测试故意重复公开密钥/IV，不能用于用户数据。
负例现场重建，四份不压缩正例和完整配方/哈希单独登记；不改原始语料。
"""
from __future__ import annotations

import hashlib
import hmac
import importlib.metadata
import json
import os
import platform
import re
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tests/kdbx_oracle/.deps-argon2"), str(ROOT / "tests/kdbx_oracle")]

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from kdbx_oracle import read_kdbx, reader

MANIFEST = HERE / "v4_payload_manifest.json"
TEST_LIMIT = 256 << 10
EXPANDED_BYTES = 4 << 20
SOURCES = {
    "G40-RICH": ("g40-rich.kdbx", "419f2406522d7b3e16f22fcd8e40a1a97a54ee2e4e1f70a0ad8298fe239efc14",
                 "合成口令-G40-RICH-Ünï🔑"),
    "G41-RICH": ("g41-rich.kdbx", "68c71f1c7896b2678799fa656ce0a5bfa5921c7703f15fe2aec6ecb88cda0f6d",
                 "合成口令-G41-RICH-Ünï🔑"),
}
CIPHERS = {"aes": reader.CIPHER_AES256, "chacha20": reader.CIPHER_CHACHA20}
MIN_XML = b"<KeePassFile><Meta/><Root/></KeePassFile>"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def gzip_bytes(chunks):
    compressor = zlib.compressobj(9, zlib.DEFLATED, 31)
    return b"".join(compressor.compress(c) for c in chunks) + compressor.flush()


def item(identifier, value):
    return bytes([identifier]) + struct.pack("<i", len(value)) + value


def block_mac(base, index, data):
    number = struct.pack("<Q", index)
    key = hashlib.sha512(number + base).digest()
    return hmac.new(key, number + struct.pack("<i", len(data)) + data, hashlib.sha256).digest()


def frames(payload, base, block_size=4096):
    if type(block_size) is not int or not 1 <= block_size <= (1 << 20):
        raise ValueError("fixture block_size out of range")
    chunks = [payload[i:i + block_size] for i in range(0, len(payload), block_size)]
    return [block_mac(base, i, c) + struct.pack("<i", len(c)) + c
            for i, c in enumerate(chunks + [b""])]


@dataclass
class Envelope:
    source_id: str
    data: bytes
    fields: dict
    password: str
    key: bytes
    hmac_base: bytes
    inner: bytes
    xml: bytes

    def header(self, cipher, compressed):
        if cipher not in CIPHERS or type(compressed) is not bool:
            raise ValueError("fixture cipher/compression unsupported")
        iv_size = 16 if cipher == "aes" else 12
        iv = hashlib.sha256(("keex-public-v4:" + self.source_id + ":" + cipher).encode()).digest()[:iv_size]
        replace = {reader.H_CIPHER: CIPHERS[cipher].bytes,
                   reader.H_COMPRESSION: struct.pack("<I", int(compressed)), reader.H_IV: iv}
        # 保留已认证源头部的字段顺序和值；只改变明确的三个字段。
        header = self.data[:12]
        for identifier, value in self.fields.items():
            value = replace.get(identifier, value)
            header += bytes([identifier]) + struct.pack("<i", len(value)) + value
        header += item(0, b"\r\n\r\n")
        return header, iv

    def prefix(self, cipher, compressed):
        header, _ = self.header(cipher, compressed)
        key = hashlib.sha512(struct.pack("<Q", (1 << 64) - 1) + self.hmac_base).digest()
        return header + hashlib.sha256(header).digest() + hmac.new(key, header, hashlib.sha256).digest()

    def encode(self, cipher, compressed, *, inner=None, xml=None, encoded=None, block_size=4096):
        if encoded is None:
            body = (self.inner if inner is None else inner) + (self.xml if xml is None else xml)
            encoded = gzip_bytes([body]) if compressed else body
        _, iv = self.header(cipher, compressed)
        if cipher == "aes":
            padder = padding.PKCS7(128).padder()
            encoded = padder.update(encoded) + padder.finalize()
            encryptor = Cipher(algorithms.AES(self.key), modes.CBC(iv)).encryptor()
        else:
            encryptor = Cipher(algorithms.ChaCha20(self.key, bytes(4) + iv), None).encryptor()
        ciphertext = encryptor.update(encoded) + encryptor.finalize()
        return self.prefix(cipher, compressed) + b"".join(frames(ciphertext, self.hmac_base, block_size))

    @property
    def config(self):
        stream_id, stream_key, _, _ = reader._parse_inner_header(self.inner)
        return item(1, struct.pack("<I", stream_id)) + item(2, stream_key)


def load_source(source_id):
    filename, expected, password = SOURCES[source_id]
    data = (HERE / filename).read_bytes()
    if digest(data) != expected:
        raise ValueError("registered synthetic source hash changed: " + source_id)
    decoded = read_kdbx(data, password)
    major, _, fields, end = reader._parse_outer_header(data)
    if data[end - 9:end] != item(0, b"\r\n\r\n"):
        raise ValueError("registered source terminator changed")
    if major != 4 or decoded.kdf != {"name": "aes-kdf", "rounds": 1000000}:
        raise ValueError("registered source parameters changed")
    transformed, _ = reader._derive_transformed_key(4, fields, reader.composite_key(password, None))
    master_seed = fields[reader.H_MASTER_SEED]
    key = hashlib.sha256(master_seed + transformed).digest()
    base = hashlib.sha512(master_seed + transformed + b"\x01").digest()
    ciphertext = reader._read_hmac_blocks(data, end + 64, base)
    plain = reader._unpad(UUID(bytes=fields[reader.H_CIPHER]),
                          reader._decrypt_raw(UUID(bytes=fields[reader.H_CIPHER]), key,
                                              fields[reader.H_IV], ciphertext))
    if decoded.compressed:
        plain = reader._gunzip(plain)
    _, _, _, inner_end = reader._parse_inner_header(plain)
    return Envelope(source_id, data, fields, password, key, base, plain[:inner_end], plain[inner_end:])


@dataclass(frozen=True)
class Case:
    name: str
    compressed: bool
    stage: str
    error: str | None = None
    reason: str | None = None

    def record(self, source_id, cipher, data):
        identifier = source_id.lower().replace("g", "v", 1) + "-" + cipher + "-" + self.name
        return {"id": identifier, "source_id": source_id, "cipher": cipher,
                "compressed": self.compressed, "case": self.name, "stage": self.stage,
                "expect": "reject" if self.error else "open", "oracle_error": self.error,
                "oracle_reason": self.reason, "sha256": digest(data), "bytes": len(data),
                "file": identifier + ".kdbx" if self.name == "uncompressed" else None}


def cases(envelope, cipher):
    for compressed in (False, True):
        label = "gzip" if compressed else "raw"
        yield Case("compressed" if compressed else "uncompressed", compressed, "open"), envelope.encode(cipher, compressed)
        xml_cases = {
            "entity": (b'<!DOCTYPE KeePassFile [<!ENTITY x "synthetic">]>'
                       b"<KeePassFile><Meta><Generator>&x;</Generator></Meta><Root/></KeePassFile>", "DOCTYPE"),
            "external": (b'<!DOCTYPE KeePassFile [<!ENTITY x SYSTEM "https://synthetic.invalid/entity">]>'
                         b"<KeePassFile><Meta><Generator>&x;</Generator></Meta><Root/></KeePassFile>", "DOCTYPE"),
            "delayed-doctype": (b"<!--" + b" " * (64 << 10) + b"-->"
                                b'<!DOCTYPE KeePassFile [<!ENTITY x "synthetic">]>' + MIN_XML, "DOCTYPE"),
            "utf16": ('<?xml version="1.0" encoding="UTF-16"?><KeePassFile/>'.encode("utf-16"), "UTF-8"),
            "deep": (b"<KeePassFile>" + b"<Group>" * 256 + b"</Group>" * 256 + b"</KeePassFile>", "嵌套超过"),
            "malformed": (b"<KeePassFile><Root></KeePassFile>", "XML 解析失败"),
            "wrong-root": (b"<Synthetic/>", "XML 根元素"),
        }
        for name, (xml, reason) in xml_cases.items():
            yield Case(label + "-xml-" + name, compressed, "xml", "KdbxFormatError", reason), envelope.encode(
                cipher, compressed, xml=xml)
        for name, text in (("bad-base64", b"!"), ("nonascii-base64", "合成".encode())):
            xml, count = re.subn(rb'(<Value Protected="True">)[^<]*', rb"\g<1>" + text, envelope.xml, count=1)
            if count != 1:
                raise ValueError("registered protected value missing")
            yield Case(label + "-xml-" + name, compressed, "unprotect", "KdbxFormatError", "base64"), envelope.encode(
                cipher, compressed, xml=xml)
        config = envelope.config
        stream_id, stream_key, _, _ = reader._parse_inner_header(envelope.inner)
        ending = item(0, b"")
        inner_cases = {
            "negative-size": (b"\x01" + struct.pack("<i", -1), "字段被截断"),
            "oversized-field": (b"\x02" + struct.pack("<i", (1 << 31) - 1), "字段被截断"),
            "stream-id-width": (item(1, b"123") + item(2, stream_key) + ending, "编号应为 4 字节"),
            "missing-id": (item(2, stream_key) + ending, "缺少保护流"),
            "missing-key": (item(1, struct.pack("<I", stream_id)) + ending, "缺少保护流"),
            "binary-no-flags": (config + item(3, b"") + ending, "缺少标志位"),
            "unknown-field": (config + item(127, b"synthetic") + ending, "未知内层头部"),
            "duplicate-id": (item(1, struct.pack("<I", stream_id)) + envelope.inner, "重复"),
            "conflicting-id": (item(1, struct.pack("<I", 0)) + envelope.inner, "重复"),
            "duplicate-key": (item(2, stream_key) + envelope.inner, "重复"),
            "conflicting-key": (item(2, b"public-wrong-key") + envelope.inner, "重复"),
            "nonempty-end": (envelope.inner[:-5] + item(0, b"synthetic"), "结束字段必须为空"),
        }
        for name, (inner, reason) in inner_cases.items():
            yield Case(label + "-inner-" + name, compressed, "inner", "KdbxFormatError", reason), envelope.encode(
                cipher, compressed, inner=inner)
        unsupported = item(1, struct.pack("<I", 127)) + item(2, stream_key) + item(0, b"")
        yield Case(label + "-unknown-stream", compressed, "stream", "KdbxUnsupported", "内层保护流"), envelope.encode(
            cipher, compressed, inner=unsupported, xml=MIN_XML)
        # size=0 的字段头缺一字节，后面没有 XML 可意外补齐它。
        yield Case(label + "-inner-truncated", compressed, "inner", "KdbxFormatError", "内层头部被截断"), envelope.encode(
            cipher, compressed, inner=b"\x00\x00\x00\x00", xml=b"")
    packed = gzip_bytes([envelope.inner, envelope.xml])
    corrupted_crc = packed[:-8] + bytes([packed[-8] ^ 1]) + packed[-7:]
    corrupted_size = packed[:-4] + bytes([packed[-4] ^ 1]) + packed[-3:]
    invalid_deflate = packed[:10] + b"\x07" + packed[11:]
    gzip_cases = {
        "truncated": (packed[:-4], "KdbxIntegrityError", "gzip 数据被截断"),
        "crc": (corrupted_crc, "KdbxIntegrityError", "gzip 数据损坏"),
        "isize": (corrupted_size, "KdbxIntegrityError", "gzip 数据损坏"),
        "deflate": (invalid_deflate, "KdbxIntegrityError", "gzip 数据损坏"),
        "trailing": (packed + b"synthetic", "KdbxIntegrityError", "多余内容"),
        "concatenated": (packed + gzip_bytes([b""]), "KdbxIntegrityError", "多余内容"),
    }
    filler = b" " * 4096
    xml_bomb = gzip_bytes([envelope.inner, b"<KeePassFile><Meta><Generator>",
                          *([filler] * (EXPANDED_BYTES // len(filler))),
                          b"</Generator></Meta><Root/></KeePassFile>"])
    inner_bomb = gzip_bytes([envelope.config, b"\x03" + struct.pack("<i", EXPANDED_BYTES + 1) + b"\x01",
                            *([filler] * (EXPANDED_BYTES // len(filler))), item(0, b""), MIN_XML])
    gzip_cases.update({"xml-budget": (xml_bomb, "KdbxUnsupported", "压缩炸弹"),
                       "inner-budget": (inner_bomb, "KdbxUnsupported", "压缩炸弹")})
    for name, (encoded, error, reason) in gzip_cases.items():
        yield Case("gzip-" + name, True, "gzip", error, reason), envelope.encode(cipher, True, encoded=encoded)

    # 只有本组在完整容器上破坏认证；上面的 gzip/XML/inner 负例均重算了 HMAC。
    valid = envelope.encode(cipher, True)
    prefix_size = len(envelope.prefix(cipher, True))
    chunks, pos = [], prefix_size
    while pos < len(valid):
        size = struct.unpack_from("<i", valid, pos + 32)[0]
        chunks.append(valid[pos:pos + 36 + size])
        pos += 36 + size
    def flipped(value, offset=0):
        return value[:offset] + bytes([value[offset] ^ 1]) + value[offset + 1:]
    broken = {
        "later-tag": ([chunks[0], flipped(chunks[1]), *chunks[2:]], "KdbxIntegrityError", "第 1 块 HMAC"),
        "end-tag": ([*chunks[:-1], flipped(chunks[-1])], "KdbxIntegrityError", "块 HMAC"),
        "swap": ([chunks[1], chunks[0], *chunks[2:]], "KdbxIntegrityError", "第 0 块 HMAC"),
        "repeat": ([chunks[0], *chunks], "KdbxIntegrityError", "第 1 块 HMAC"),
        "drop": (chunks[1:], "KdbxIntegrityError", "第 0 块 HMAC"),
        "missing-end": (chunks[:-1], "KdbxFormatError", "HMAC 块流被截断"),
        "truncated-end": ([*chunks[:-1], chunks[-1][:-1]], "KdbxFormatError", "HMAC 块流被截断"),
        "negative-size": ([chunks[0][:32] + struct.pack("<i", -1) + chunks[0][36:], *chunks[1:]],
                          "KdbxFormatError", "HMAC 块被截断"),
        "oversized-block": ([chunks[0][:32] + struct.pack("<i", (1 << 31) - 1) + chunks[0][36:], *chunks[1:]],
                            "KdbxFormatError", "HMAC 块被截断"),
        "trailing": ([*chunks, b"x"], "KdbxIntegrityError", "结束块之后"),
        "double-end": ([*chunks, chunks[-1]], "KdbxIntegrityError", "结束块之后"),
        "ciphertext": ([chunks[0], flipped(chunks[1], 36), *chunks[2:]], "KdbxIntegrityError", "第 1 块 HMAC"),
    }
    for name, (blocks, error, reason) in broken.items():
        yield Case("hmac-" + name, True, "hmac", error, reason), valid[:prefix_size] + b"".join(blocks)
    if cipher == "aes":
        ciphertext = b"".join(chunk[36:] for chunk in chunks[:-1])
        pad_size = 16 - len(packed) % 16
        bad_padding = bytearray(ciphertext)
        bad_padding[-17] ^= pad_size  # 最后一个明文字节变成 0；HMAC 重新计算。
        for name, body, stage, error, reason in (
            ("padding", bytes(bad_padding), "padding", "KdbxIntegrityError", "填充不对"),
            ("cipher-length", ciphertext[:-1], "decrypt", "KdbxFormatError", "密文长度"),
            ("empty-cipher", b"", "decrypt", "KdbxFormatError", "密文长度"),
        ):
            yield Case("aes-" + name, True, stage, error, reason), (
                valid[:prefix_size] + b"".join(frames(body, envelope.hmac_base)))


def provenance():
    names = ["tests/fixtures/kdbx/v4_payload.py", "tests/fixtures/kdbx/manifest.json",
             "tests/kdbx_oracle/kdbx_oracle/reader.py", "tests/kdbx_oracle/kdbx_oracle/semantic.py",
             "tests/kdbx_oracle/kdbx_oracle/salsa20.py", "tests/kdbx_oracle/kdbx_oracle/__init__.py",
             "tests/kdbx_oracle/requirements.txt", "tests/kdbx_oracle/requirements-argon2-macos-arm64.lock"]
    return {name: digest((ROOT / name).read_bytes()) for name in names}


def build_manifest():
    records, outputs = [], {}
    for source_id in SOURCES:
        envelope = load_source(source_id)
        for cipher in CIPHERS:
            for case, data in cases(envelope, cipher):
                record = case.record(source_id, cipher, data)
                records.append(record)
                if record["file"]:
                    outputs[record["file"]] = data
    return {"schema_version": 1, "note": "仅公开合成变异；四份正例留存，负例现场重建。不是参考客户端 writer。",
            "format_spec": "https://keepass.info/help/kb/kdbx.html",
            "runtime": {"python": platform.python_version(), "zlib_build": zlib.ZLIB_VERSION,
                        "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
                        "cryptography": importlib.metadata.version("cryptography")},
            "test_xml_limit": TEST_LIMIT, "bomb_filler_bytes": EXPANDED_BYTES,
            "sources": [{"id": name, "file": item[0], "sha256": item[1], "password": item[2]}
                        for name, item in SOURCES.items()],
            "provenance": provenance(), "samples": records}, outputs


def main():
    manifest, outputs = build_manifest()
    serialized = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if MANIFEST.exists():
        if MANIFEST.read_text(encoding="utf-8") != serialized:
            raise ValueError("registered payload manifest differs; review before updating")
        for name, data in outputs.items():
            if (HERE / name).read_bytes() != data:
                raise ValueError("registered payload output differs: " + name)
        print(f"verified {len(manifest['samples'])} cases / {len(outputs)} files; no writes")
        return 0
    targets = [HERE / name for name in outputs] + [MANIFEST]
    if any(path.exists() for path in targets):
        raise ValueError("unregistered payload output exists; refusing overwrite")
    # 所有字节已构造完毕；排他创建，只清理本次创建成功的文件。
    created = []
    try:
        for path, data in [(HERE / name, data) for name, data in outputs.items()] + [(MANIFEST, serialized.encode())]:
            with path.open("xb") as handle:
                created.append(path)
                os.chmod(path, 0o600)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    print(f"registered {len(manifest['samples'])} cases / {len(outputs)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
