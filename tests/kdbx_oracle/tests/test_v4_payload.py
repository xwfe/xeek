"""KDBX 4.x 认证负载、资源界限和分块顺序的端到端回归。"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import io
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/fixtures/kdbx"))
import v4_payload as payload

import kdbx_oracle
from kdbx_oracle import KdbxFormatError, KdbxKeyError, KdbxUnsupported, read_kdbx, read_plain_xml, reader
from kdbx_oracle.semantic import canonicalize, diff

KEEPASSXC = shutil.which("keepassxc-cli")


def exported_fields(root):
    # History 的 UUID 与当前条目相同，用出现序号区分；字段顺序不影响字段含义。
    result, occurrences = {}, {}
    for entry in root.iter("Entry"):
        identifier = entry.findtext("UUID")
        ordinal = occurrences.get(identifier, 0)
        occurrences[identifier] = ordinal + 1
        values = {}
        for string in entry.findall("String"):
            key, value = string.findtext("Key"), string.find("Value")
            if key in values or value is None:
                raise AssertionError("duplicate or missing exported field")
            values[key] = (value.text or "", any(value.get(a, "").lower() == "true"
                          for a in ("Protected", "ProtectInMemory")))
        result[(identifier, ordinal)] = values
    return result


class AuthenticatedPayloadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.envelopes = {name: payload.load_source(name) for name in payload.SOURCES}
        cls.originals = {name: read_kdbx(e.data, e.password) for name, e in cls.envelopes.items()}
        cls.variants = [(envelope, cipher, case, data)
                        for envelope in cls.envelopes.values() for cipher in payload.CIPHERS
                        for case, data in payload.cases(envelope, cipher)]

    def selected(self, *stages):
        return [v for v in self.variants if v[2].stage in stages]

    def assert_rejected(self, envelope, case, data, **kwargs):
        with self.assertRaisesRegex(getattr(kdbx_oracle, case.error), case.reason) as caught:
            read_kdbx(data, envelope.password, max_xml_bytes=payload.TEST_LIMIT, **kwargs)
        return caught.exception

    def assert_authenticated(self, envelope, data):
        # 不调用 fixture 的 block_mac/frames 或 reader 的认证入口，独立逐块检查最终字节。
        _, _, _, end = reader._parse_outer_header(data)
        self.assertEqual(hashlib.sha256(data[:end]).digest(), data[end:end + 32])
        key = hashlib.sha512(struct.pack("<Q", (1 << 64) - 1) + envelope.hmac_base).digest()
        self.assertEqual(hmac.new(key, data[:end], hashlib.sha256).digest(), data[end + 32:end + 64])
        position, index = end + 64, 0
        while True:
            self.assertLessEqual(position + 36, len(data))
            size = struct.unpack_from("<i", data, position + 32)[0]
            self.assertGreaterEqual(size, 0)
            block = data[position + 36:position + 36 + size]
            self.assertEqual(len(block), size)
            number = struct.pack("<Q", index)
            block_key = hashlib.sha512(number + envelope.hmac_base).digest()
            expected = hmac.new(block_key, number + struct.pack("<i", size) + block, hashlib.sha256).digest()
            self.assertEqual(expected, data[position:position + 32])
            position += 36 + size
            if not size:
                break
            index += 1
        self.assertEqual(position, len(data))

    def test_matrix_scope_and_original_manifest_sources(self):
        self.assertEqual(len(self.variants), 278)
        self.assertEqual(len(self.selected("open")), 8)
        identifiers = [c.record(e.source_id, cipher, data)["id"] for e, cipher, c, data in self.variants]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        original = json.loads((payload.HERE / "manifest.json").read_text())
        for name, (filename, digest, password) in payload.SOURCES.items():
            record = next(s for s in original["samples"] if s["id"] == name)
            self.assertEqual((record["file"], record["sha256"], record["credentials"]["password"]),
                             (filename, digest, password))
            self.assertEqual(record["method"], "xml-import")

    def test_every_payload_negative_has_valid_header_and_all_block_macs(self):
        for envelope, cipher, case, data in self.variants:
            if case.stage == "hmac":
                continue
            with self.subTest(source=envelope.source_id, cipher=cipher, case=case.name):
                self.assert_authenticated(envelope, data)

    def test_eight_controls_preserve_xml_protection_history_and_attachment_pool(self):
        for envelope, cipher, case, data in self.selected("open"):
            with self.subTest(source=envelope.source_id, cipher=cipher, case=case.name):
                result = read_kdbx(data, envelope.password, max_xml_bytes=payload.TEST_LIMIT)
                original = self.originals[envelope.source_id]
                self.assertEqual(result.version, original.version)
                self.assertEqual(result.cipher, "aes256-cbc" if cipher == "aes" else "chacha20")
                self.assertEqual(result.compressed, case.compressed)
                self.assertEqual(result.kdf, original.kdf)
                self.assertEqual(diff(canonicalize(original), canonicalize(result), ignore=()), [])
                self.assertEqual(ET.tostring(result.root), ET.tostring(original.root))
                self.assertEqual(result.binaries, original.binaries)
                self.assertEqual(len(result.root.findall(".//History/Entry")), 2)
                values = [v.text for v in result.root.findall(".//String/Value")]
                self.assertIn("合成-当前口令-Ünï🔑", values)
                self.assertIn("只在历史里的受保护字段", values)

    def test_gzip_failures_reach_decompressor_before_any_inner_or_xml_parse(self):
        for envelope, cipher, case, data in self.selected("gzip"):
            with self.subTest(source=envelope.source_id, cipher=cipher, case=case.name):
                with patch.object(reader, "_gunzip", wraps=reader._gunzip) as gzip, \
                     patch.object(reader, "_parse_inner_header") as inner, patch.object(reader, "_parse_xml") as xml:
                    self.assert_rejected(envelope, case, data)
                    gzip.assert_called_once()
                    inner.assert_not_called()
                    xml.assert_not_called()

    def test_inner_header_failures_reach_inner_parser_before_xml(self):
        for envelope, cipher, case, data in self.selected("inner"):
            with self.subTest(source=envelope.source_id, cipher=cipher, case=case.name):
                with patch.object(reader, "_parse_inner_header", wraps=reader._parse_inner_header) as inner, \
                     patch.object(reader, "_parse_xml") as xml:
                    self.assert_rejected(envelope, case, data)
                    inner.assert_called_once()
                    xml.assert_not_called()

    def test_xml_failures_reach_xml_parser_before_unprotect(self):
        for envelope, cipher, case, data in self.selected("xml"):
            with self.subTest(source=envelope.source_id, cipher=cipher, case=case.name):
                with patch.object(reader, "_parse_inner_header", wraps=reader._parse_inner_header) as inner, \
                     patch.object(reader, "_parse_xml", wraps=reader._parse_xml) as xml, \
                     patch.object(reader, "_unprotect") as unprotect:
                    self.assert_rejected(envelope, case, data)
                    inner.assert_called_once()
                    xml.assert_called_once()
                    unprotect.assert_not_called()

    def test_doctype_and_utf16_never_reach_elementtree(self):
        for envelope, cipher, case, data in self.selected("xml"):
            if case.reason not in ("DOCTYPE", "UTF-8"):
                continue
            with self.subTest(source=envelope.source_id, cipher=cipher, case=case.name):
                with patch.object(reader.ET, "fromstring") as parser:
                    self.assert_rejected(envelope, case, data)
                    parser.assert_not_called()

    def test_protected_value_base64_has_controlled_value_free_error(self):
        for envelope, cipher, case, data in self.selected("unprotect"):
            with self.subTest(source=envelope.source_id, cipher=cipher, case=case.name):
                with patch.object(reader, "_unprotect", wraps=reader._unprotect) as unprotect:
                    error = self.assert_rejected(envelope, case, data)
                    unprotect.assert_called_once()
                    self.assertNotIn("合成", str(error))

    def test_unknown_inner_stream_is_explicitly_unsupported(self):
        for envelope, cipher, case, data in self.selected("stream"):
            with self.subTest(source=envelope.source_id, cipher=cipher, case=case.name):
                with patch.object(reader, "_inner_stream", wraps=reader._inner_stream) as stream, \
                     patch.object(reader, "_unprotect") as unprotect:
                    self.assert_rejected(envelope, case, data)
                    stream.assert_called_once()
                    unprotect.assert_not_called()

    def test_plain_and_legacy_meta_binary_base64_errors_are_controlled(self):
        envelope = self.envelopes["G41-RICH"]
        for invalid in (b"!", "合成".encode()):
            xml = b'<KeePassFile><Meta><Binaries><Binary ID="0">' + invalid + (
                b"</Binary></Binaries></Meta><Root/></KeePassFile>")
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(KdbxFormatError, "base64"):
                    read_plain_xml(xml)
                for cipher in payload.CIPHERS:
                    data = envelope.encode(cipher, False, xml=xml)
                    self.assert_authenticated(envelope, data)
                    with self.assertRaisesRegex(KdbxFormatError, "base64"):
                        read_kdbx(data, envelope.password)

    def test_legacy_headerhash_base64_error_is_controlled(self):
        import mutate
        manifest = json.loads((payload.HERE / "manifest.json").read_text())
        source = next(s for s in manifest["samples"] if s["id"] == "G31-RICH")
        original = (payload.HERE / source["file"]).read_bytes()
        self.assertEqual(payload.digest(original), source["sha256"])
        credentials = (source["credentials"]["password"], None)
        xml = mutate.v3_inner_xml(original, *credentials)
        for invalid in (b"!", "合成".encode()):
            changed, count = re.subn(rb"<HeaderHash>[^<]*</HeaderHash>",
                                     b"<HeaderHash>" + invalid + b"</HeaderHash>", xml)
            self.assertEqual(count, 1)
            data = mutate.v3_reencrypt(original, *credentials, payload.gzip_bytes([changed]))
            with self.assertRaisesRegex(KdbxFormatError, "base64"):
                read_kdbx(data, credentials[0])

    def test_all_hmac_failures_precede_decryption_and_decompression(self):
        for envelope, cipher, case, data in self.selected("hmac"):
            with self.subTest(source=envelope.source_id, cipher=cipher, case=case.name):
                with patch.object(reader, "_decrypt_raw") as decrypt, patch.object(reader, "_gunzip") as gzip, \
                     patch.object(reader, "_parse_inner_header") as inner, patch.object(reader, "_parse_xml") as xml:
                    self.assert_rejected(envelope, case, data)
                    for operation in (decrypt, gzip, inner, xml):
                        operation.assert_not_called()

    def test_authenticated_aes_length_and_padding_fail_before_gzip(self):
        for envelope, cipher, case, data in self.selected("padding", "decrypt"):
            with self.subTest(source=envelope.source_id, case=case.name):
                with patch.object(reader, "_decrypt_raw", wraps=reader._decrypt_raw) as decrypt, \
                     patch.object(reader, "_unpad", wraps=reader._unpad) as unpad, \
                     patch.object(reader, "_gunzip") as gzip:
                    self.assert_rejected(envelope, case, data)
                    decrypt.assert_called_once()
                    self.assertEqual(unpad.call_count, int(case.stage == "padding"))
                    gzip.assert_not_called()

    def test_uncompressed_xml_budget_accepts_exact_size_and_rejects_one_less(self):
        for envelope in self.envelopes.values():
            for cipher in payload.CIPHERS:
                with self.subTest(source=envelope.source_id, cipher=cipher):
                    data = envelope.encode(cipher, False)
                    read_kdbx(data, envelope.password, max_xml_bytes=len(envelope.xml))
                    with patch.object(reader, "_parse_xml") as xml:
                        with self.assertRaisesRegex(KdbxUnsupported, "XML 超过测试上限"):
                            read_kdbx(data, envelope.password, max_xml_bytes=len(envelope.xml) - 1)
                        xml.assert_not_called()

    def test_compressed_budget_includes_inner_header_and_accepts_exact_total(self):
        for envelope in self.envelopes.values():
            for cipher in payload.CIPHERS:
                with self.subTest(source=envelope.source_id, cipher=cipher):
                    data = envelope.encode(cipher, True)
                    total = len(envelope.inner) + len(envelope.xml)
                    read_kdbx(data, envelope.password, max_xml_bytes=total)
                    with patch.object(reader, "_parse_inner_header") as inner:
                        with self.assertRaisesRegex(KdbxUnsupported, "压缩炸弹"):
                            read_kdbx(data, envelope.password, max_xml_bytes=total - 1)
                        inner.assert_not_called()

    def test_xml_depth_boundary_256_accepted_and_257_rejected(self):
        for envelope in self.envelopes.values():
            for cipher in payload.CIPHERS:
                for compressed in (False, True):
                    with self.subTest(source=envelope.source_id, cipher=cipher, compressed=compressed):
                        for depth in (256, 257):
                            xml = b"<KeePassFile>" + b"<Group>" * (depth - 1) + b"</Group>" * (depth - 1) + b"</KeePassFile>"
                            data = envelope.encode(cipher, compressed, xml=xml)
                            if depth == 256:
                                read_kdbx(data, envelope.password)
                            else:
                                with self.assertRaisesRegex(KdbxFormatError, "嵌套超过 256"):
                                    read_kdbx(data, envelope.password)

    def test_odd_hmac_blocks_can_split_aes_cipher_blocks(self):
        for envelope in self.envelopes.values():
            for cipher in payload.CIPHERS:
                for size in (17, 4093, 1 << 20):
                    with self.subTest(source=envelope.source_id, cipher=cipher, block_size=size):
                        data = envelope.encode(cipher, False, block_size=size)
                        self.assert_authenticated(envelope, data)
                        actual = read_kdbx(data, envelope.password)
                        self.assertEqual(ET.tostring(actual.root), ET.tostring(self.originals[envelope.source_id].root))
                        self.assertEqual(actual.binaries, self.originals[envelope.source_id].binaries)

    def test_one_byte_hmac_blocks_on_small_valid_body(self):
        for envelope in self.envelopes.values():
            for cipher in payload.CIPHERS:
                with self.subTest(source=envelope.source_id, cipher=cipher):
                    data = envelope.encode(cipher, False, inner=envelope.config + payload.item(0, b""),
                                           xml=payload.MIN_XML, block_size=1)
                    self.assert_authenticated(envelope, data)
                    self.assertEqual(read_kdbx(data, envelope.password).root.tag, "KeePassFile")

    def test_wrong_password_fails_before_payload_processing(self):
        for envelope, cipher, case, data in self.selected("open"):
            with self.subTest(source=envelope.source_id, cipher=cipher, case=case.name):
                with patch.object(reader, "_decrypt_raw") as decrypt, patch.object(reader, "_gunzip") as gzip:
                    with self.assertRaisesRegex(KdbxKeyError, "头部 HMAC"):
                        read_kdbx(data, "wrong-synthetic-password")
                    decrypt.assert_not_called()
                    gzip.assert_not_called()

    def test_only_registered_unchanged_synthetic_sources_are_loaded(self):
        with patch.object(Path, "read_bytes") as read:
            with self.assertRaises(KeyError):
                payload.load_source("../unregistered")
            read.assert_not_called()
        with patch.object(Path, "read_bytes", return_value=b"changed"), patch.object(payload, "read_kdbx") as decrypt:
            with self.assertRaisesRegex(ValueError, "source hash changed"):
                payload.load_source("G40-RICH")
            decrypt.assert_not_called()

    def test_manifest_and_four_saved_controls_are_reproducible(self):
        actual, outputs = payload.build_manifest()
        self.assertEqual(actual, json.loads(payload.MANIFEST.read_text()))
        self.assertEqual(len(outputs), 4)
        for name, data in outputs.items():
            self.assertEqual((payload.HERE / name).read_bytes(), data)

    def test_generator_noop_preserves_bytes_and_modification_times(self):
        records = json.loads(payload.MANIFEST.read_text())["samples"]
        files = [payload.MANIFEST] + [payload.HERE / s["file"] for s in records if s["file"]]
        before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in files}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(payload.main(), 0)
        self.assertEqual(before, {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in files})

    def test_generator_new_run_is_exclusive_then_noop(self):
        manifest, outputs = payload.build_manifest()
        with tempfile.TemporaryDirectory(dir=payload.HERE) as temp:
            directory = Path(temp)
            with patch.object(payload, "HERE", directory), patch.object(payload, "MANIFEST", directory / "manifest.json"), \
                 patch.object(payload, "build_manifest", return_value=(manifest, outputs)), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(payload.main(), 0)
                before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir()}
                self.assertEqual(payload.main(), 0)
                self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir()})
                self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in directory.iterdir()))

    def test_generator_refuses_unregistered_file_or_stale_manifest(self):
        manifest, outputs = payload.build_manifest()
        with tempfile.TemporaryDirectory(dir=payload.HERE) as temp:
            directory = Path(temp)
            target = directory / next(iter(outputs))
            target.write_bytes(b"preexisting-synthetic")
            with patch.object(payload, "HERE", directory), patch.object(payload, "MANIFEST", directory / "manifest.json"), \
                 patch.object(payload, "build_manifest", return_value=(manifest, outputs)):
                with self.assertRaisesRegex(ValueError, "unregistered"):
                    payload.main()
                self.assertEqual(target.read_bytes(), b"preexisting-synthetic")
                (directory / "manifest.json").write_text("{}")
                with self.assertRaisesRegex(ValueError, "manifest differs"):
                    payload.main()
                self.assertEqual(target.read_bytes(), b"preexisting-synthetic")

    def test_publication_failure_cleans_only_files_created_by_this_attempt(self):
        manifest, outputs = payload.build_manifest()
        original_open = Path.open
        with tempfile.TemporaryDirectory(dir=payload.HERE) as temp:
            directory = Path(temp)
            sentinel = directory / "unrelated.txt"
            sentinel.write_bytes(b"synthetic-sentinel")
            destination = directory / "manifest.json"
            def fail_manifest(path, *args, **kwargs):
                if path == destination and args and args[0] == "xb":
                    raise OSError("synthetic manifest failure")
                return original_open(path, *args, **kwargs)
            with patch.object(payload, "HERE", directory), patch.object(payload, "MANIFEST", destination), \
                 patch.object(payload, "build_manifest", return_value=(manifest, outputs)), patch.object(Path, "open", fail_manifest):
                with self.assertRaisesRegex(OSError, "synthetic manifest failure"):
                    payload.main()
            self.assertEqual(list(directory.iterdir()), [sentinel])
            self.assertEqual(sentinel.read_bytes(), b"synthetic-sentinel")

    @unittest.skipUnless(KEEPASSXC, "缺少 keepassxc-cli：未完成八个安全正例的交叉读取")
    def test_keepassxc_exports_all_eight_controls_with_fields_and_history(self):
        # 只给外部读者安全正例；XML/解压攻击样本不交给未设同样预算的 CLI。
        with tempfile.TemporaryDirectory(dir=payload.HERE) as temp:
            for envelope, cipher, case, data in self.selected("open"):
                with self.subTest(source=envelope.source_id, cipher=cipher, case=case.name):
                    target = Path(temp) / "synthetic-control.kdbx"
                    target.write_bytes(data)
                    run = subprocess.run([KEEPASSXC, "export", "-q", str(target)],
                                         input=(envelope.password + "\n").encode(), capture_output=True,
                                         timeout=30, check=True)
                    exported = read_plain_xml(run.stdout)
                    self.assertEqual(exported_fields(exported.root),
                                     exported_fields(self.originals[envelope.source_id].root))
                    self.assertEqual(target.read_bytes(), data)
                    # CLI 的 4.x 导出没有完整附件池，附件内容由上面的 oracle 逐字比较验证。


if __name__ == "__main__":
    unittest.main()
