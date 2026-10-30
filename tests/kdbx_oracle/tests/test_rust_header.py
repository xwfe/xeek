"""K003：保存时文件头的设置不能被悄悄换掉，随机值每次都要换新。没有发现缺陷，这里防回归。"""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reference = load_module("header_reference", "tests/reference_writer/generate.py")
build = load_module("header_build", "tests/rust_preservation/build.py")
checks = reference.checks
import candidate_minimal as minimal
from kdbx_oracle import read_kdbx, reader

payload = minimal.v4_payload
H_COMMENT, H_SEED, H_IV, H_KDF, H_PUBLIC = 1, reader.H_MASTER_SEED, reader.H_IV, reader.H_KDF, reader.H_PUBLIC_CUSTOM
PUBLIC_ITEMS = {
    b"synthetic.text": (0x18, "合成".encode()),
    b"synthetic.u32": (0x04, struct.pack("<I", 7)),
    b"synthetic.u64": (0x05, struct.pack("<Q", 9)),
    b"synthetic.bool": (0x08, b"\x01"),
    b"synthetic.i32": (0x0c, struct.pack("<i", -3)),
    b"synthetic.i64": (0x0d, struct.pack("<q", -9)),
    b"synthetic.bytes": (0x42, b"\x01\x02\x03"),
}


def variant_dictionary(items):
    data = b"\x00\x01"
    for key, (kind, value) in items.items():
        data += bytes([kind]) + struct.pack("<i", len(key)) + key + struct.pack("<i", len(value)) + value
    return data + b"\x00"


def parse_variant_dictionary(data):
    position, items = 2, {}
    while data[position] != 0:
        kind = data[position]
        size = struct.unpack("<i", data[position + 1:position + 5])[0]
        key = data[position + 5:position + 5 + size]
        position += 5 + size
        size = struct.unpack("<i", data[position:position + 4])[0]
        items[key] = (kind, data[position + 4:position + 4 + size])
        position += 4 + size
    return items


def outer_fields(data):
    position, fields = 12, {}
    while True:
        identifier = data[position]
        size = struct.unpack("<i", data[position + 1:position + 5])[0]
        fields[identifier] = data[position + 5:position + 5 + size]
        position += 5 + size
        if identifier == 0:
            return fields


def synthetic(cipher="aes", compressed=True, extra=None, stream=None):
    envelope = minimal._v4_source("4.1")
    if extra:
        envelope = dataclasses.replace(envelope, fields={**envelope.fields, **extra})
    stream_id, key, _, _ = reader._parse_inner_header(envelope.inner)
    if stream:
        stream_id, key = stream
    xml = minimal._wire_xml(minimal.plain_case("history", "4.1"), "4.1", stream_id, key)
    inner = payload.item(1, struct.pack("<I", stream_id)) + payload.item(2, key) + payload.item(0, b"")
    return envelope.encode(cipher, compressed, inner=inner, xml=xml), envelope.password


class HeaderSettingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cli = shutil.which("keepassxc-cli")
        if not cls.cli:
            raise RuntimeError("header checks require keepassxc-cli")
        build.build_helper()
        cls.binary = build.TARGET / "release" / build.HISTORY_EDIT
        temporary = tempfile.TemporaryDirectory(prefix="header-", dir=build.HERE / "target")
        cls.addClassCleanup(temporary.cleanup)
        cls.work = Path(temporary.name)
        cls.sequence = 0

    def run_edit(self, data, password, target=minimal.TARGET_UUID):
        self.__class__.sequence += 1
        source = self.work / f"input-{self.sequence}.kdbx"
        output = self.work / f"output-{self.sequence}.kdbx"
        source.write_bytes(data)
        run = subprocess.run([str(self.binary), str(source), str(output), target, "edited"],
                             input=password + "\n", capture_output=True, text=True, timeout=90)
        return run, output

    def save(self, data, password, target=minimal.TARGET_UUID):
        run, output = self.run_edit(data, password, target)
        self.assertEqual(run.returncode, 0, run.stderr)
        reference.reference_export({"password": password}, output, self.cli)
        return output.read_bytes()

    def assert_same_settings(self, before, after, password):
        old, new = read_kdbx(before, password), read_kdbx(after, password)
        self.assertEqual((new.version, new.cipher, new.compressed, new.inner_stream, new.kdf),
                         (old.version, old.cipher, old.compressed, old.inner_stream, old.kdf))

    def test_cipher_and_compression_are_kept(self):
        for cipher in ("aes", "chacha20"):
            for compressed in (True, False):
                with self.subTest(cipher=cipher, compressed=compressed):
                    data, password = synthetic(cipher, compressed)
                    self.assert_same_settings(data, self.save(data, password), password)

    def test_kdf_parameters_of_registered_samples_are_kept(self):
        manifest = json.loads((build.FIXTURES / "rust_writer_manifest.json").read_text())
        for sample in manifest["samples"]:
            with self.subTest(sample=sample["file"]):
                data = (build.FIXTURES / sample["file"]).read_bytes()
                target = next(iter(checks.current_entries(read_kdbx(data, sample["password"]))))
                self.assert_same_settings(data, self.save(data, sample["password"], target), sample["password"])

    def test_salsa20_inner_stream_stays_salsa20(self):
        data, password = synthetic(stream=(2, bytes(range(32))))
        output = self.save(data, password)
        self.assert_same_settings(data, output, password)
        entry = checks.current_entries(read_kdbx(output, password))[minimal.TARGET_UUID]
        self.assertEqual(checks.fields(entry)["Password"].value, "synthetic-password")

    def test_random_values_change_on_every_save(self):
        # 重用种子或 IV 会破坏加密；两次保存和原文件三者都要不同。
        data, password = synthetic()
        files = [outer_fields(data), outer_fields(self.save(data, password)), outer_fields(self.save(data, password))]
        for field in (H_SEED, H_IV, H_KDF):
            self.assertEqual(len({f[field] for f in files}), 3, field)

    def test_public_custom_data_keeps_every_item(self):
        # 库用字典存它，顺序会变；规范里它本来就是字典，KeePassXC 也这么读，所以比内容不比字节。
        data, password = synthetic(extra={H_PUBLIC: variant_dictionary(PUBLIC_ITEMS)})
        after = outer_fields(self.save(data, password))
        self.assertEqual(parse_variant_dictionary(after[H_PUBLIC]), PUBLIC_ITEMS)

    def test_comment_header_field_is_dropped_like_keepassxc_does(self):
        # 没有哪个客户端展示或写这个字段；KeePassXC 读到也忽略，保存后同样没有。这里钉住现状，不算保留。
        data, password = synthetic(extra={H_COMMENT: b"synthetic-comment"})
        self.assertNotIn(H_COMMENT, outer_fields(self.save(data, password)))
        source = self.work / "comment.kdbx"
        source.write_bytes(data)
        run = subprocess.run([self.cli, "edit", "-q", "-u", "edited", str(source), "/synthetic-minimal"],
                             input=password + "\n", capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn(H_COMMENT, outer_fields(source.read_bytes()))

    def test_unknown_header_field_refuses_to_open(self):
        # 看不懂的头部字段不能在保存时悄悄丢掉；KeePassXC 会丢，这里更保守。
        data, password = synthetic(extra={200: b"synthetic-future"})
        run, output = self.run_edit(data, password)
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
