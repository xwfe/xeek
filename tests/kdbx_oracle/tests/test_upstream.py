"""固定提交的上游公开测试原件；不安装 kdbxweb，不执行 URL 或自动类型操作。"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from kdbx_oracle import read_kdbx, read_plain_xml, KdbxKeyError, KdbxIntegrityError, KdbxUnsupported
from kdbx_oracle.reader import H_KDF, parse_variant_dictionary
from kdbx_oracle.semantic import summarize, uuid_hex

HERE = Path(__file__).resolve().parents[2] / "fixtures" / "kdbx" / "upstream_kdbxweb"
KEEPASSXC = shutil.which("keepassxc-cli")
SUPPORTED = ("Argon2id.kdbx", "AesChaCha.kdbx", "Argon2ChaCha.kdbx")


def entry_map(db):
    entries = [entry for group in db.root.iter("Group") for entry in group.findall("Entry")]
    result = {uuid_hex(entry.findtext("UUID")): entry for entry in entries}
    if len(result) != len(entries):
        raise AssertionError("duplicate current UUID")
    return result


def field_map(entry):
    result = {}
    for string in entry.findall("String"):
        key, value = string.findtext("Key"), string.find("Value")
        if key in result or value is None:
            raise AssertionError("duplicate/malformed field")
        result[key] = (value.text or "", any(value.get(a, "").lower() == "true"
                       for a in ("Protected", "ProtectInMemory")))
    return result


class UpstreamAlgorithmTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((HERE / "manifest.json").read_text())
        cls.keyfile = (HERE / "demo.key").read_bytes()

    def open(self, name):
        return read_kdbx((HERE / name).read_bytes(), "demo", self.keyfile)

    def assert_export_fields(self, original, exported):
        expected, actual = field_map(original), field_map(exported)
        for key, value in expected.items():
            self.assertEqual(actual.get(key), value)
        # CLI 给缺省标准字段补空值；原字段及其保护位仍逐项精确比较。
        for key in actual.keys() - expected.keys():
            self.assertIn(key, {"Title", "UserName", "Password", "URL", "Notes"})
            self.assertEqual(actual[key], ("", key == "Password"))

    def test_pinned_source_blobs_sha256_keyfile_and_license(self):
        self.assertEqual(self.manifest["commit"], "7601e45d2a437f35a7fa3d767164eab60bc05d42")
        self.assertEqual(self.manifest["license"], "MIT")
        self.assertIsNone(self.manifest["original_writer_version"])
        for item in self.manifest["files"]:
            data = (HERE / item["file"]).read_bytes()
            self.assertEqual(len(data), item["bytes"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])
            self.assertEqual(hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(), item["git_blob_sha1"])
        self.assertIn(b"\r\n", self.keyfile)

    def test_argon2id_aes_file_unlocks_and_preserves_actual_parameters(self):
        opened = self.open("Argon2id.kdbx")
        self.assertEqual((opened.version, opened.cipher, opened.inner_stream), ("4.0", "aes256-cbc", "chacha20"))
        self.assertEqual(opened.kdf, {"name": "argon2id", "memory": 8192, "iterations": 3, "parallelism": 1})
        self.assertEqual(parse_variant_dictionary(opened.header_fields[H_KDF])["V"][1], 19)

    def test_outer_chacha20_file_unlocks_with_aes_kdf(self):
        opened = self.open("AesChaCha.kdbx")
        self.assertEqual((opened.version, opened.cipher, opened.inner_stream), ("3.1", "chacha20", "salsa20"))
        self.assertEqual(opened.kdf, {"name": "aes-kdf", "rounds": 6000})
        self.assertEqual(opened.header_hash, "match")

    def test_argon2d_and_outer_chacha20_unlock_with_original_parameters(self):
        opened = self.open("Argon2ChaCha.kdbx")
        self.assertEqual((opened.version, opened.cipher, opened.inner_stream), ("4.0", "chacha20", "chacha20"))
        self.assertEqual(opened.kdf, {"name": "argon2d", "memory": 24576, "iterations": 2, "parallelism": 3})
        self.assertEqual(parse_variant_dictionary(opened.header_fields[H_KDF])["V"][1], 19)

    def test_contents_match_the_upstream_checkdb_contract(self):
        for name in SUPPORTED:
            opened = self.open(name)
            self.assertEqual(opened.root.findtext("Meta/DatabaseName"), "demo")
            self.assertEqual(opened.root.findtext("Meta/DatabaseDescription"), "demo db")
            summary = summarize(opened)
            self.assertEqual((summary["groups"], summary["entries"], summary["history_entries"], summary["deleted_objects"]),
                             (8, 4, 2, 1))
            entry = next(e for e in entry_map(opened).values() if field_map(e).get("Title") == ("my entry", False))
            fields = field_map(entry)
            self.assertEqual(fields["Password"], ("mypass", True))
            self.assertEqual(fields["my field protected"], ("protected val", True))
            history = entry.findall("History/Entry")
            self.assertEqual(len(history), 1)
            self.assertEqual(field_map(history[0])["Password"], ("pass", True))
            self.assertEqual(field_map(history[0])["Title"], ("my-entry", False))

    def test_attachment_bytes_match_the_upstream_published_digest(self):
        for name in SUPPORTED:
            opened = self.open(name)
            self.assertEqual(len(opened.binaries), 1)
            data, protected = next(iter(opened.binaries.values()))
            self.assertEqual(len(data), 15)
            self.assertFalse(protected)
            self.assertEqual(hashlib.sha256(data).hexdigest(), "6de2ccb163da5f925ea9cdc1298b7c1bd6f7afbbbed41f3d52352f9efbd9db8a")

    def test_wrong_password_or_keyfile_is_rejected(self):
        for name in SUPPORTED:
            data = (HERE / name).read_bytes()
            for password, keyfile in (("wrong-synthetic-password", self.keyfile), ("demo", b"wrong-synthetic-keyfile")):
                with self.assertRaises(KdbxKeyError):
                    read_kdbx(data, password, keyfile)

    def test_ciphertext_damage_is_rejected(self):
        for name in SUPPORTED:
            data = bytearray((HERE / name).read_bytes())
            data[-80] ^= 1
            with self.assertRaises(KdbxIntegrityError):
                read_kdbx(bytes(data), "demo", self.keyfile)

    @unittest.skipUnless(KEEPASSXC, "keepassxc-cli unavailable; independent export not run")
    def test_reference_cli_opens_all_three_and_cross_checks_current_and_history_fields(self):
        for name in SUPPORTED:
            path = HERE / name
            before = path.read_bytes()
            run = subprocess.run([KEEPASSXC, "export", "-q", "-f", "xml", "-k", str(HERE / "demo.key"), str(path)],
                                 input="demo\n", capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, "public upstream export failed")
            exported = entry_map(read_plain_xml(run.stdout.encode()))
            original = entry_map(self.open(name))
            self.assertEqual(exported.keys(), original.keys())
            for identifier, entry in original.items():
                self.assert_export_fields(entry, exported[identifier])
                old, new = entry.findall("History/Entry"), exported[identifier].findall("History/Entry")
                self.assertEqual(len(old), len(new))
                for a, b in zip(old, new):
                    self.assert_export_fields(a, b)
            self.assertEqual(path.read_bytes(), before)
        # KDBX 4 的 CLI XML 缺附件池；附件在独立的上游摘要断言中核对。


if __name__ == "__main__":
    unittest.main()

