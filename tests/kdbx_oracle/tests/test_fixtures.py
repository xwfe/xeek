"""K002 黄金样本回归：文件没被改、能打开、摘要和 manifest 一致、关键明文值正确。

manifest 是生成器写的，只比对 manifest 的话，生成器和解码器一起错就发现不了；
所以另外按源数据里写死的明文抽查。
"""

import hashlib
import json
import sys
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization

import kdbx_oracle
from kdbx_oracle import KdbxKeyError, read_kdbx, read_plain_xml
from kdbx_oracle.semantic import canonicalize, diff, summarize, uuid_hex

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "kdbx"
sys.path.insert(0, str(FIXTURES))
import generate  # noqa: E402
import mutate  # noqa: E402
import source  # noqa: E402

MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
GOLDEN = [s for s in MANIFEST["samples"] if s["expect"] == "open"]
MUTANTS = [s for s in MANIFEST["samples"] if s["expect"] != "open"]
# 压缩炸弹解压后 512 MiB；测试里把上限压到 16 MiB，不然每次要先解出 256 MiB 才拒绝。
TEST_XML_LIMIT = 16 << 20


def open_sample(sample, password="__manifest__", keyfile="__manifest__"):
    creds = sample["credentials"]
    if password == "__manifest__":
        password = creds["password"]
    if keyfile == "__manifest__":
        keyfile = (FIXTURES / creds["keyfile"]).read_bytes() if creds["keyfile"] else None
    return read_kdbx((FIXTURES / sample["file"]).read_bytes(), password=password, keyfile=keyfile)


def entry_by(decoded, name):
    target = uuid_hex(source.uid(name))
    for entry in decoded.root.iter("Entry"):
        if uuid_hex(entry.findtext("UUID")) == target:
            return entry  # 先遇到的是当前版本，历史在它的 History 里面
    raise KeyError(name)


def value(entry, key):
    for string in entry.findall("String"):
        if string.findtext("Key") == key:
            return string.findtext("Value") or ""
    raise KeyError(key)


def attachment(decoded, entry, key):
    for binary in entry.findall("Binary"):
        if binary.findtext("Key") == key:
            return decoded.binaries[binary.find("Value").get("Ref")][0]
    raise KeyError(key)


class GoldenSamplesTest(unittest.TestCase):
    def test_manifest_is_not_empty(self):
        self.assertGreaterEqual(len(GOLDEN), 10)

    def test_files_unchanged(self):
        for sample in GOLDEN:
            with self.subTest(sample["id"]):
                data = (FIXTURES / sample["file"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), sample["sha256"])
                keyfile = sample["credentials"]["keyfile"]
                if keyfile:
                    digest = hashlib.sha256((FIXTURES / keyfile).read_bytes()).hexdigest()
                    self.assertEqual(digest, sample["credentials"]["keyfile_sha256"])

    def test_summary_matches_manifest(self):
        for sample in GOLDEN:
            with self.subTest(sample["id"]):
                self.assertEqual(summarize(open_sample(sample)), sample["summary"])

    def test_writer_changes_match_manifest(self):
        # 源 XML 是确定的，可以随时重建；KeePassXC 导入时做的改动必须和记录的完全一致。
        for sample in GOLDEN:
            if sample["method"] != "xml-import":
                continue
            with self.subTest(sample["id"]):
                kind, level = sample["source"]
                src = read_plain_xml(source.build(kind, level, sample["id"]))
                changes = diff(canonicalize(src), canonicalize(open_sample(sample)), ignore=generate.VOLATILE)
                self.assertEqual(sorted(c.label for c in changes), sample["writer_changes"])

    def test_wrong_password_rejected(self):
        for sample in GOLDEN:
            with self.subTest(sample["id"]):
                with self.assertRaises(KdbxKeyError):
                    open_sample(sample, password="wrong-synthetic-password")

    def test_missing_keyfile_rejected(self):
        for sample in GOLDEN:
            if not sample["credentials"]["keyfile"] or sample["credentials"]["password"] is None:
                continue
            with self.subTest(sample["id"]):
                with self.assertRaises(KdbxKeyError):
                    open_sample(sample, keyfile=None)


class MutantSamplesTest(unittest.TestCase):
    def test_manifest_lists_every_mutation(self):
        self.assertEqual([s["id"] for s in MUTANTS], [m[0] for m in mutate.MUTATIONS])

    def test_mutations_are_reproducible(self):
        golden = {s["id"]: s for s in GOLDEN}
        for sample_id, base_id, func, *_ in mutate.MUTATIONS:
            with self.subTest(sample_id):
                base = golden[base_id]
                creds = base["credentials"]
                keyfile = (FIXTURES / creds["keyfile"]).read_bytes() if creds["keyfile"] else None
                data = func((FIXTURES / base["file"]).read_bytes(), (creds["password"], keyfile))
                record = next(s for s in MUTANTS if s["id"] == sample_id)
                self.assertEqual(hashlib.sha256(data).hexdigest(), record["sha256"])
                self.assertEqual((FIXTURES / record["file"]).read_bytes(), data)

    def test_rejected_with_expected_error(self):
        for sample in MUTANTS:
            if sample["expect"] != "reject":
                continue
            with self.subTest(sample["id"]):
                error = getattr(kdbx_oracle, sample["oracle_error"])
                with self.assertRaises(error):
                    creds = sample["credentials"]
                    keyfile = (FIXTURES / creds["keyfile"]).read_bytes() if creds["keyfile"] else None
                    read_kdbx((FIXTURES / sample["file"]).read_bytes(), password=creds["password"],
                              keyfile=keyfile, max_xml_bytes=TEST_XML_LIMIT)

    def test_headerhash_missing_opens_read_only_with_same_content(self):
        sample = next(s for s in MUTANTS if s["id"] == "R31-HEADERHASH-MISSING")
        self.assertEqual(sample["expect"], "read-only")
        decoded = open_sample(sample)
        self.assertEqual(decoded.header_hash, "missing")
        base = open_sample(next(s for s in GOLDEN if s["id"] == sample["base"]))
        self.assertEqual(base.header_hash, "match")
        # 重新加密没有打乱保护流：除了 HeaderHash（比较器本来就忽略），内容完全一致。
        self.assertEqual(diff(canonicalize(base), canonicalize(decoded), reveal=True), [])


class RichContentTest(unittest.TestCase):
    """按源数据里写死的明文抽查，覆盖三种格式。"""

    def setUp(self):
        self.samples = [s for s in GOLDEN if s["id"].endswith("-RICH")]
        self.assertEqual(len(self.samples), 3)

    def test_protected_values_in_entry_and_history(self):
        for sample in self.samples:
            with self.subTest(sample["id"]):
                decoded = open_sample(sample)
                login = entry_by(decoded, "login")
                self.assertEqual(value(login, "Password"), "合成-当前口令-Ünï🔑")
                self.assertEqual(value(login, "X-Secret"), "未知受保护字段-当前")
                history = login.findall("History/Entry")
                self.assertEqual([value(h, "Password") for h in history], ["合成-旧口令-1", "合成-旧口令-2"])
                self.assertEqual(value(history[0], "X-Secret"), "未知受保护字段-旧版本-1")
                self.assertEqual(value(history[1], "X-Old-Protected"), "只在历史里的受保护字段")
                edge = entry_by(decoded, "edge")
                self.assertEqual(value(edge, "X-Long-Protected"), "受" * 4096)
                otp = entry_by(decoded, "otp-keepassxc")
                self.assertIn(f"secret={source.TOTP_SECRET}", value(otp, "otp"))

    def test_keeagent_and_passkey_material(self):
        for sample in self.samples:
            with self.subTest(sample["id"]):
                decoded = open_sample(sample)
                agent = entry_by(decoded, "keeagent")
                settings = attachment(decoded, agent, "KeeAgent.settings")
                self.assertEqual(settings, source.keeagent_settings("id_ed25519"))
                key = serialization.load_ssh_private_key(attachment(decoded, agent, "id_ed25519"), password=None)
                self.assertEqual(type(key).__name__, "Ed25519PrivateKey")
                passkey = entry_by(decoded, "passkey")
                pem = value(passkey, "KPEX_PASSKEY_PRIVATE_KEY_PEM")
                self.assertEqual(pem, source.passkey_pem("current"))
                serialization.load_pem_private_key(pem.encode(), password=None)


class CliSampleTest(unittest.TestCase):
    def test_keepassxc_native_history_recycle_and_purge(self):
        sample = next(s for s in GOLDEN if s["id"] == "G41-CLI")
        decoded = open_sample(sample)
        login = next(e for e in decoded.root.iter("Entry") if value(e, "Title") == "登录")
        self.assertEqual(value(login, "Password"), "合成-CLI-口令-2")
        self.assertEqual(value(login, "UserName"), "synthetic-user-2")
        # edit -p、edit -u、两次 attachment-import，每次修改前都存一份历史。
        self.assertEqual([value(h, "Password") for h in login.findall("History/Entry")][:2],
                         ["合成-CLI-口令-1", "合成-CLI-口令-2"])
        self.assertEqual(attachment(decoded, login, "blob.bin"), bytes(range(256)))
        self.assertEqual(sample["summary"]["recycle_bin"], {"enabled": True, "group_present": True, "entries": 1})
        self.assertEqual(sample["summary"]["deleted_objects"], 1)


if __name__ == "__main__":
    unittest.main()
