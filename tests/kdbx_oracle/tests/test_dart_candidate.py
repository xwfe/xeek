"""K003 对照候选 kdbx.dart 2.5.0 的实际产物、不支持项、剩余差异与失败保护回归。"""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = ROOT / "tests/dart_candidate"
spec = importlib.util.spec_from_file_location("dart_candidate_generate", CANDIDATE / "generate.py")
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)
checks = candidate.checks
from kdbx_oracle import KdbxIntegrityError, KdbxKeyError, read_kdbx

KEEPASSXC = shutil.which("keepassxc-cli")
ROOT_GROUP = "KeePassFile/Root/Group=6f542f7e7f8288660938b7000a25e046"
# KDBX 4.1 新增的元数据：kdbx.dart 按自身模型重写 Meta 时丢掉。
META_41_LOSSES = [
    "removed KeePassFile/Meta/CustomData/Item=KPXC_RANDOM_SLUG/LastModificationTime",
    "removed KeePassFile/Meta/CustomData/Item=keex.fixture/LastModificationTime",
    "removed KeePassFile/Meta/CustomIcons/Icon=e64d2ddb6063d2ca56280dce11b188c4/LastModificationTime",
    "removed KeePassFile/Meta/CustomIcons/Icon=e64d2ddb6063d2ca56280dce11b188c4/Name",
]


class DartCandidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(candidate.MANIFEST.read_text())
        cls.cases = list(candidate.cases())
        cls.samples = cls.manifest["samples"]

    def test_locked_dependency_provenance_and_registered_input_hashes(self):
        self.assertIn("  kdbx: 2.5.0\n", (CANDIDATE / "pubspec.yaml").read_text())
        lock = (CANDIDATE / "pubspec.lock").read_text()
        locked = re.search(r'\n  kdbx:\n    dependency: "direct main"\n(?:.*\n)*?      sha256: "([0-9a-f]{64})"'
                           r'(?:.*\n)*?    version: "([^"]+)"', lock)
        self.assertEqual(locked.groups(), (self.manifest["writer"]["archive_sha256"], "2.5.0"))
        self.assertEqual(self.manifest["writer"]["license"], "GPL-3.0")
        self.assertEqual(self.manifest["provenance"], candidate.provenance())
        self.assertEqual(self.manifest["generation_provenance"], self.manifest["provenance"])
        self.assertEqual(len(self.samples), 8)
        for sample, case in zip(self.samples, self.cases):
            self.assertEqual({k: sample[k] for k in case}, case)
            data = (candidate.FIXTURES / sample["file"]).read_bytes()
            self.assertEqual((len(data), candidate.digest(data)), (sample["bytes"], sample["sha256"]))
            source = (candidate.FIXTURES / case["source_file"]).read_bytes()
            self.assertEqual(candidate.digest(source), sample["source_sha256"])

    def test_all_outputs_reproduce_the_recorded_preservation_report(self):
        for case, sample in zip(self.cases, self.samples):
            with self.subTest(case=case["id"]):
                actual = candidate.describe(case, candidate.FIXTURES / case["file"])
                self.assertEqual(actual, {key: sample[key] for key in actual})

    def test_version_algorithms_are_kept_and_kdf_salt_rotates(self):
        for case, sample in zip(self.cases, self.samples):
            old = candidate.open_case(case, candidate.FIXTURES / case["source_file"])
            new = candidate.open_case(case, candidate.FIXTURES / case["file"])
            self.assertEqual((new.version, new.cipher, new.kdf), (old.version, old.cipher, old.kdf))
            self.assertNotEqual(candidate.kdf_salt(new), candidate.kdf_salt(old))
            self.assertEqual(sample["helper_counts"]["version"], old.version)
        self.assertEqual({s["version"] for s in self.samples}, {"3.1", "4.0", "4.1"})
        self.assertEqual({s["kdf"]["name"] for s in self.samples}, {"aes-kdf", "argon2d"})

    def test_previous_snapshot_is_appended_without_changing_old_history(self):
        for case, sample in zip(self.cases, self.samples):
            before = candidate.open_case(case, candidate.FIXTURES / case["source_file"])
            after = candidate.open_case(case, candidate.FIXTURES / case["file"])
            old = checks.current_entries(before)[case["entry_uuid"]]
            history = checks.current_entries(after)[case["entry_uuid"]].findall("History/Entry")
            expected = old.findall("History/Entry") + [old]
            self.assertEqual(len(history), len(expected))
            for a, b in zip(expected, history):
                self.assertEqual(checks.labels(checks.snapshot(before, a), checks.snapshot(after, b), ignore=()), [])
            self.assertEqual(sample["history_placement"], "append")
            self.assertEqual(sample["history_snapshot_changes"], [])

    def test_remaining_differences_are_recorded_and_never_reported_lossless(self):
        expected = {
            "DK31-VAULT": ["order " + ROOT_GROUP], "DK31-PASSKEY": ["order " + ROOT_GROUP],
            "DK40-VAULT": ["order " + ROOT_GROUP], "DK40-PASSKEY": ["order " + ROOT_GROUP],
            "DK41-VAULT": sorted(META_41_LOSSES + ["order " + ROOT_GROUP]),
            "DK41-PASSKEY": sorted(META_41_LOSSES + ["order " + ROOT_GROUP]),
        }
        # 以 keepass-rs 输出为输入时根分组已是候选的排序，只剩 4.1 元数据丢失。
        expected["DK41-RS-VAULT-ARGON2D-CHACHA20"] = META_41_LOSSES
        for sample in self.samples:
            if sample["id"] in expected:
                self.assertEqual(sample["other_changes"], expected[sample["id"]], sample["id"])
            self.assertTrue(sample["other_changes"], sample["id"])
            self.assertFalse(sample["lossless_roundtrip"])

    def test_only_empty_standard_fields_lose_protection_and_every_case_is_listed(self):
        for sample in self.samples:
            changes = sample["empty_standard_protection_changes"]
            self.assertTrue(all(c["protected"] == [True, False] for c in changes), sample["id"])
            self.assertTrue(all(c["field"] in candidate.rust_reference.STANDARD for c in changes))
            output = candidate.open_case(sample, candidate.FIXTURES / sample["file"])
            for change in changes:
                entry = checks.current_entries(output)[change["entry_uuid"]]
                if change["scope"] != "current":
                    entry = entry.findall("History/Entry")[int(change["scope"].split("/")[1])]
                self.assertEqual(checks.fields(entry)[change["field"]], checks.Field("", False))
        self.assertEqual({s["id"]: len(s["empty_standard_protection_changes"]) for s in self.samples}, {
            "DK31-VAULT": 31, "DK31-PASSKEY": 35, "DK40-VAULT": 31, "DK40-PASSKEY": 35,
            "DK41-VAULT": 31, "DK41-PASSKEY": 35, "DK40-UPSTREAM-ARGON2D-CHACHA20": 0,
            "DK41-RS-VAULT-ARGON2D-CHACHA20": 31})

    def test_unsupported_inputs_are_registered_with_cause(self):
        recorded = self.manifest["unsupported"]
        self.assertEqual([item["id"] for item in recorded], [case["id"] for case in candidate.unsupported_cases()])
        for item in recorded:
            self.assertEqual(item["observed_error"], item["expected_error"])
            data = (candidate.FIXTURES / item["source_file"]).read_bytes()
            self.assertEqual(candidate.digest(data), item["source_sha256"])
            # 独立 oracle 能读这些输入，说明失败来自候选能力缺口而不是样本本身损坏。
            decoded = read_kdbx(data, item["password"], keyfile=candidate.keyfile_bytes(item))
            self.assertIn(decoded.kdf["name"] if "ARGON2ID" in item["id"] else decoded.cipher,
                          ("argon2id", "chacha20"))

    def test_outputs_reject_wrong_password_and_ciphertext_damage(self):
        for case, sample in zip(self.cases, self.samples):
            data = (candidate.FIXTURES / sample["file"]).read_bytes()
            keyfile = candidate.keyfile_bytes(case)
            with self.subTest(case=sample["id"]), self.assertRaises(KdbxKeyError):
                read_kdbx(data, "wrong-public-synthetic-password", keyfile=keyfile)
            damaged = bytearray(data)
            damaged[-80] ^= 1
            with self.subTest(case=sample["id"]), self.assertRaises((KdbxIntegrityError, KdbxKeyError)):
                read_kdbx(bytes(damaged), case["password"], keyfile=keyfile)

    def test_preservation_checks_reject_field_protection_attachment_and_history_corruption(self):
        case = next(c for c in self.cases if c["id"] == "DK41-PASSKEY")
        old = candidate.open_case(case, candidate.FIXTURES / case["source_file"])
        valid = candidate.open_case(case, candidate.FIXTURES / case["file"])
        for kind in ("field", "protection", "attachment", "history", "version", "salt"):
            damaged = copy.deepcopy(valid)
            entry = checks.current_entries(damaged)[case["entry_uuid"]]
            if kind in ("field", "protection"):
                value = next(s.find("Value") for s in entry.findall("String")
                             if s.findtext("Key") == "KPEX_PASSKEY_PRIVATE_KEY_PEM")
                if kind == "field":
                    value.text = "corrupt-public-test-payload"
                else:
                    value.attrib.clear()
            elif kind == "attachment":
                ref = next(iter(damaged.binaries))
                data, protected = damaged.binaries[ref]
                damaged.binaries[ref] = (data + b"corrupt", protected)
            elif kind == "history":
                history = entry.find("History")
                history.remove(history.findall("Entry")[0])
            elif kind == "version":
                damaged.minor = 0
            else:
                # 2.5.0 之前的缺陷形态：保存后 KDF 盐不变。
                damaged.header_fields = dict(old.header_fields)
            with self.subTest(kind=kind), patch.object(candidate, "read_kdbx", side_effect=[old, damaged]):
                with self.assertRaises(AssertionError):
                    candidate.describe(case, candidate.FIXTURES / case["file"])

    @unittest.skipUnless(KEEPASSXC, "keepassxc-cli unavailable; third-party reopen/re-edit not run")
    def test_keepassxc_reopens_and_reedits_every_output(self):
        with tempfile.TemporaryDirectory(prefix=".dart-candidate-test-", dir=CANDIDATE) as work:
            for case, sample in zip(self.cases, self.samples):
                path = candidate.FIXTURES / sample["file"]
                before = path.read_bytes()
                with self.subTest(case=sample["id"]):
                    self.assertEqual(candidate.keepassxc_export(case, path, KEEPASSXC), sample["keepassxc_export"])
                    self.assertEqual(candidate.keepassxc_reedit(case, path, KEEPASSXC, work),
                                     sample["keepassxc_reedit"])
                self.assertEqual(path.read_bytes(), before)


@unittest.skipUnless(KEEPASSXC, "keepassxc-cli unavailable; third-party re-edit of keepass-rs outputs not run")
class KeepassRsReeditParityTest(unittest.TestCase):
    """K003 要求两个候选过同一道“第三方重开并再编辑”；keepass-rs 的 12 份参考输出在此补上再编辑。"""

    def test_keepassxc_reedits_every_keepass_rs_output_without_removing_data(self):
        manifest = json.loads((candidate.FIXTURES / "rust_writer_manifest.json").read_text())
        with tempfile.TemporaryDirectory(prefix=".dart-candidate-test-", dir=CANDIDATE) as work:
            for sample in manifest["samples"]:
                case = {"file": sample["file"], "password": sample["password"], "keyfile": None,
                        "entry_uuid": sample["entry_uuid"], "new_username": sample["new_username"],
                        "entry_path": candidate.PASSKEY_PATH if sample["kind"] == "passkey"
                        else candidate.vault_source.EDIT_PATH}
                with self.subTest(case=sample["id"]):
                    result = candidate.keepassxc_reedit(case, candidate.FIXTURES / sample["file"], KEEPASSXC, work)
                    self.assertEqual(result["version"], "4.1")
                    self.assertEqual(result["history_entries"], sample["summary"]["history_entries"] + 1)
                    self.assertFalse([c for c in result["reference_client_changes"] if c.startswith("removed")])


@unittest.skipUnless(candidate.BINARY.is_file(), "build the locked Dart helper to run live save/guard tests")
class LiveDartCandidateTest(unittest.TestCase):
    """用 Argon2d 小原件做实时调用，避免纯 Dart 跑 100 万轮 AES-KDF 拖慢回归。"""

    def setUp(self):
        self.case = next(c for c in candidate.cases() if c["id"] == "DK40-UPSTREAM-ARGON2D-CHACHA20")

    def invoke(self, output, **override):
        case = {**self.case, **override}
        return candidate.run_helper(case, output)

    def test_actual_single_edit_creates_readable_output_and_keeps_source_bytes(self):
        source = candidate.FIXTURES / self.case["source_file"]
        before = source.read_bytes()
        with tempfile.TemporaryDirectory(prefix=".dart-candidate-test-", dir=CANDIDATE) as directory:
            output = Path(directory) / "new.kdbx"
            run, error, _ = self.invoke(output)
            self.assertEqual(run.returncode, 0, error)
            record = candidate.describe(self.case, output)
            self.assertEqual(record["version"], "4.0")
            self.assertEqual(json.loads(run.stdout)["history_after"], record["summary"]["history_entries"])
        self.assertEqual(source.read_bytes(), before)

    def test_unsupported_inputs_fail_without_output(self):
        with tempfile.TemporaryDirectory(prefix=".dart-candidate-test-", dir=CANDIDATE) as directory:
            for case in candidate.unsupported_cases():
                output = Path(directory) / "must-not-exist.kdbx"
                with self.subTest(case=case["id"]):
                    run, error, _ = candidate.run_helper(case, output)
                    self.assertNotEqual(run.returncode, 0)
                    self.assertEqual(error, {"ok": False, "error": case["expected_error"]})
                    self.assertEqual(run.stdout, "")
                    self.assertFalse(output.exists())

    def test_existing_output_and_same_input_are_never_overwritten(self):
        source = candidate.FIXTURES / self.case["source_file"]
        before = source.read_bytes()
        with tempfile.TemporaryDirectory(prefix=".dart-candidate-test-", dir=CANDIDATE) as directory:
            existing = Path(directory) / "existing.kdbx"
            existing.write_bytes(b"existing-public-test-content")
            for output, code in ((existing, "output_create_failed"), (source, "output_equals_input")):
                run, error, _ = self.invoke(output)
                self.assertNotEqual(run.returncode, 0)
                self.assertEqual(error["error"], code)
                self.assertEqual(run.stdout, "")
            self.assertEqual(existing.read_bytes(), b"existing-public-test-content")
        self.assertEqual(source.read_bytes(), before)

    def test_invalid_credentials_arguments_and_target_do_not_create_output(self):
        original = candidate.open_case(self.case, candidate.FIXTURES / self.case["source_file"])
        username = checks.fields(checks.current_entries(original)[self.case["entry_uuid"]])["UserName"].value
        attempts = [
            ({"password": "wrong-public-test-password"}, "invalid_credentials"),
            ({"password": ""}, "invalid_password_input"),
            ({"password": "public\nsecond-line"}, "invalid_password_input"),
            ({"password": "x" * 4097}, "password_too_long"),
            ({"entry_uuid": "invalid-uuid"}, "invalid_uuid"),
            ({"entry_uuid": "ffffffffffffffffffffffffffffffff"}, "entry_not_found"),
            ({"new_username": username}, "username_is_unchanged"),
            ({"keyfile": None}, "invalid_credentials"),
        ]
        with tempfile.TemporaryDirectory(prefix=".dart-candidate-test-", dir=CANDIDATE) as directory:
            output = Path(directory) / "must-not-exist.kdbx"
            for override, code in attempts:
                with self.subTest(error=code, override=sorted(override)):
                    run, error, _ = self.invoke(output, **override)
                    self.assertNotEqual(run.returncode, 0)
                    self.assertEqual(error, {"ok": False, "error": code})
                    self.assertEqual(run.stdout, "")
                    self.assertFalse(output.exists())


class DartCandidateGeneratorGuardTest(unittest.TestCase):
    def test_existing_manifest_noop_is_read_only_and_does_not_build(self):
        before = candidate.MANIFEST.read_bytes()
        paths = [candidate.FIXTURES / case["file"] for case in candidate.cases()]
        stats = {p: (p.stat().st_mtime_ns, candidate.digest(p.read_bytes())) for p in paths}
        with patch.object(sys, "argv", [str(CANDIDATE / "generate.py")]), \
             patch.object(candidate, "build_helper", side_effect=AssertionError("no-op must not build")), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(candidate.main(), 0)
        self.assertEqual(candidate.MANIFEST.read_bytes(), before)
        self.assertEqual({p: (p.stat().st_mtime_ns, candidate.digest(p.read_bytes())) for p in paths}, stats)

    def test_unregistered_output_is_refused_before_build(self):
        case = next(candidate.cases())
        with tempfile.TemporaryDirectory(prefix=".dart-candidate-test-", dir=CANDIDATE) as directory:
            fixtures = Path(directory)
            existing = fixtures / case["file"]
            existing.write_bytes(b"unregistered-public-test-content")
            with patch.object(candidate, "FIXTURES", fixtures), \
                 patch.object(candidate, "MANIFEST", fixtures / "manifest.json"), \
                 patch.object(candidate, "build_helper", side_effect=AssertionError("must refuse before build")), \
                 patch.object(sys, "argv", [str(CANDIDATE / "generate.py")]):
                with self.assertRaises(FileExistsError):
                    candidate.main()
            self.assertEqual(existing.read_bytes(), b"unregistered-public-test-content")
            self.assertEqual({p.name for p in fixtures.iterdir()}, {case["file"]})

    def test_tampered_case_parameters_are_rejected(self):
        data = json.loads(candidate.MANIFEST.read_text())
        data["samples"][0]["entry_uuid"] = "ffffffffffffffffffffffffffffffff"
        with tempfile.TemporaryDirectory(prefix=".dart-candidate-test-", dir=CANDIDATE) as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps(data))
            with patch.object(candidate, "MANIFEST", manifest), \
                 patch.object(sys, "argv", [str(CANDIDATE / "generate.py")]):
                with self.assertRaisesRegex(AssertionError, "case parameters"):
                    candidate.main()


if __name__ == "__main__":
    unittest.main()
