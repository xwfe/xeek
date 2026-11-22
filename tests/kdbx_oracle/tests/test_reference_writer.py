"""固定 Rust 参考写入器的实际产物、兼容性差异与有限失败保护回归。"""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "tests/reference_writer"
spec = importlib.util.spec_from_file_location("rust_fixture_generate", REFERENCE / "generate.py")
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)
checks = reference.checks
from kdbx_oracle import KdbxIntegrityError, KdbxKeyError, read_kdbx

KEEPASSXC = shutil.which("keepassxc-cli")


def source_hashes(value):
    if isinstance(value, dict):
        if "file" in value and "sha256" in value:
            yield value["file"], value["sha256"]
        for child in value.values():
            yield from source_hashes(child)
    elif isinstance(value, list):
        for child in value:
            yield from source_hashes(child)


def invoke(case, output, *, source=None, password=None, uuid=None, username=None, kdf=None, cipher=None):
    return subprocess.run(
        [str(reference.BINARY), str(source or reference.FIXTURES / case["source_file"]), str(output),
         uuid or case["entry_uuid"], username or case["new_username"],
         kdf or case["kdf"], cipher or case["cipher"]],
        input=(case["password"] + "\n") if password is None else password,
        capture_output=True, text=True, timeout=30,
    )


class ReferenceWriterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(reference.MANIFEST.read_text())
        cls.cases = list(reference.cases())
        cls.samples = cls.manifest["samples"]
        cls.opened = {
            s["id"]: read_kdbx((reference.FIXTURES / s["file"]).read_bytes(), s["password"])
            for s in cls.samples
        }
        cls.originals = {
            c["kind"]: read_kdbx((reference.FIXTURES / c["source_file"]).read_bytes(), c["password"])
            for c in cls.cases
        }

    def test_locked_dependency_provenance_and_registered_input_hashes(self):
        cargo = tomllib.loads((REFERENCE / "Cargo.toml").read_text())
        self.assertEqual(cargo["dependencies"]["keepass"],
                         {"version": "=0.15.3", "default-features": False, "features": ["save_kdbx4"]})
        locked = tomllib.loads((REFERENCE / "Cargo.lock").read_text())["package"]
        package = next(p for p in locked if p["name"] == "keepass")
        self.assertEqual(package["version"], "0.15.3")
        self.assertEqual(len(package["checksum"]), 64)
        self.assertEqual(self.manifest["writer"]["source_commit"], "15afd4da3d2f305069c7940795af1de9645fd81c")
        self.assertEqual(self.manifest["writer"]["license"], "MIT")
        self.assertTrue(self.manifest["writer"]["experimental"])
        self.assertEqual(self.manifest["provenance"], reference.provenance())
        changed = {name for name, value in self.manifest["generation_provenance"].items()
                   if value != self.manifest["provenance"][name]}
        reader_path = "tests/kdbx_oracle/kdbx_oracle/reader.py"
        gzip_paths = ["tests/fixtures/kdbx/source.py", "tests/fixtures/kdbx/vault_manifest.json",
                      "tests/fixtures/kdbx/matrix_manifest.json"]
        self.assertEqual(changed, {"tests/reference_writer/generate.py", reader_path, *gzip_paths})
        self.assertEqual(self.manifest["generation_provenance"][reader_path],
                         "ed72d093e1f402ec1257832ce9dd68b8380670b14ce01786436b9fe474c1f764")
        revisions = self.manifest["verification_revisions"]
        self.assertEqual([item["file"] for item in revisions], [reader_path, *gzip_paths])
        self.assertEqual(revisions[0]["file"], reader_path)
        self.assertEqual(revisions[0]["previous_sha256"], self.manifest["generation_provenance"][reader_path])
        self.assertEqual(revisions[0]["sha256"], self.manifest["provenance"][reader_path])
        self.assertEqual(revisions[0]["evidence"], "adr/evidence/K002_RESOURCES.md")
        # source.py 只固定 gzip 头部 OS 字节，两份清单随之更新来源登记；登记输入的摘要在下面逐项复核，不随修订放宽。
        for revision in revisions[1:]:
            self.assertEqual(revision["previous_sha256"], self.manifest["generation_provenance"][revision["file"]])
            self.assertEqual(revision["sha256"], self.manifest["provenance"][revision["file"]])
            self.assertEqual(revision["evidence"], "adr/evidence/K002_GZIP.md")
        expected_inputs = {}
        for name in ("vault_manifest.json", "matrix_manifest.json"):
            expected_inputs.update(source_hashes(json.loads((reference.FIXTURES / name).read_text())))
        self.assertEqual(len(self.samples), 12)
        self.assertEqual({(s["kind"], s["kdf"], s["cipher"]) for s in self.samples},
                         {(c["kind"], c["kdf"], c["cipher"]) for c in self.cases})
        for sample, case in zip(self.samples, self.cases):
            self.assertEqual({k: sample[k] for k in case}, case)
            self.assertEqual(sample["source_sha256"], expected_inputs[case["source_file"]])
            data = (reference.FIXTURES / sample["file"]).read_bytes()
            self.assertEqual((len(data), reference.digest(data)), (sample["bytes"], sample["sha256"]))

    def test_all_twelve_outputs_reproduce_the_recorded_preservation_report(self):
        for case, sample in zip(self.cases, self.samples):
            with self.subTest(case=case["id"]):
                actual = reference.describe(case, reference.FIXTURES / case["file"])
                self.assertEqual(actual, {key: sample[key] for key in actual})

    def test_same_rp_credentials_keep_distinct_keys_and_original_parent_pairs(self):
        names = reference.matrix_source.PASSKEY_NAMES
        for sample in self.samples:
            if sample["kind"] != "passkey":
                continue
            entries = checks.current_entries(self.opened[sample["id"]])
            original = checks.current_entries(self.originals["passkey"])
            maps = [checks.fields(entries[reference.matrix_source.hex_uid(name)]) for name in names]
            self.assertEqual(sum(checks.fields(e).get("KPEX_PASSKEY_RELYING_PARTY")
                                 == checks.Field("passkey.example.com") for e in entries.values()), 3)
            self.assertEqual(maps[0]["KPEX_PASSKEY_USER_HANDLE"], maps[2]["KPEX_PASSKEY_USER_HANDLE"])
            self.assertNotEqual(maps[0]["KPEX_PASSKEY_USER_HANDLE"], maps[1]["KPEX_PASSKEY_USER_HANDLE"])
            self.assertEqual(len({m["KPEX_PASSKEY_CREDENTIAL_ID"].value for m in maps}), 3)
            public_keys = set()
            for name, actual in zip(names, maps):
                expected = checks.fields(original[reference.matrix_source.hex_uid(name)])
                for key in expected:
                    if key.startswith("KPEX_") or key == "keex.parentEntryUuid":
                        self.assertEqual(actual[key], expected[key])
                key = serialization.load_pem_private_key(actual["KPEX_PASSKEY_PRIVATE_KEY_PEM"].value.encode(), None)
                self.assertIsInstance(key.curve, ec.SECP256R1)
                public_keys.add(key.public_key().public_bytes(serialization.Encoding.DER,
                                                              serialization.PublicFormat.SubjectPublicKeyInfo))
            self.assertEqual(len(public_keys), 3)

    def test_previous_current_snapshot_is_prepended_without_losing_old_history(self):
        for sample in self.samples:
            before, after = self.originals[sample["kind"]], self.opened[sample["id"]]
            old = checks.current_entries(before)[sample["entry_uuid"]]
            new = checks.current_entries(after)[sample["entry_uuid"]]
            self.assertEqual(len(old.findall("History/Entry")), 1)
            history = new.findall("History/Entry")
            self.assertEqual(len(history), 2)
            for expected, actual in zip([old, *old.findall("History/Entry")], history):
                self.assertEqual(checks.labels(checks.snapshot(before, expected),
                                               checks.snapshot(after, actual), ignore=()), [])
            self.assertEqual((sample["helper_counts"]["history_before"], sample["helper_counts"]["history_after"]), (4, 5))

    def test_unresolved_order_and_icon_differences_are_never_reported_lossless(self):
        root = "KeePassFile/Root/Group=6f542f7e7f8288660938b7000a25e046"
        web = root + "/Group=619866709f661f4847cc86d411ca5bf1"
        remaining = sorted(["order " + root, "removed " + web + "/IconID",
                            "removed " + web + "/Entry=8965805d6caa1155bdc9ed01dcb11d04/IconID"])
        for sample in self.samples:
            self.assertFalse(sample["lossless_roundtrip"])
            self.assertEqual(sample["history_placement"], "prepend")
            self.assertEqual(sample["other_changes"], remaining)
            self.assertEqual(sample["history_snapshot_changes"], [])
            self.assertEqual(len(sample["raw_changes"]), 9)
            self.assertEqual(sample["summary"]["attachments"]["pool_items"], 6)
            self.assertEqual(sample["summary"]["attachments"]["pool_bytes"], 3300)
        self.assertEqual(sum(bool(s["attachment_order_changes"]) for s in self.samples), 9)

    def test_all_algorithm_pairs_reject_wrong_password_and_ciphertext_damage(self):
        for sample in self.samples:
            data = (reference.FIXTURES / sample["file"]).read_bytes()
            with self.subTest(case=sample["id"]), self.assertRaises(KdbxKeyError):
                read_kdbx(data, "wrong-public-synthetic-password")
            damaged = bytearray(data)
            damaged[-80] ^= 1
            with self.subTest(case=sample["id"]), self.assertRaises(KdbxIntegrityError):
                read_kdbx(bytes(damaged), sample["password"])

    @unittest.skipUnless(KEEPASSXC, "keepassxc-cli unavailable; independent reference read not run")
    def test_reference_cli_cross_checks_all_current_and_historical_fields(self):
        for sample in self.samples:
            path = reference.FIXTURES / sample["file"]
            before = path.read_bytes()
            self.assertEqual(reference.reference_export(sample, path, KEEPASSXC), sample["reference_export"])
            self.assertEqual(path.read_bytes(), before)

    def test_preservation_checks_reject_field_protection_attachment_and_history_corruption(self):
        sample = self.samples[0]
        old, valid = self.originals["passkey"], self.opened[sample["id"]]
        for kind in ("field", "protection", "attachment", "history"):
            damaged = copy.deepcopy(valid)
            entry = checks.current_entries(damaged)[sample["entry_uuid"]]
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
            else:
                history = entry.find("History")
                history.remove(history.findall("Entry")[-1])
            with self.subTest(kind=kind), patch.object(reference, "read_kdbx", side_effect=[old, damaged]):
                with self.assertRaises(AssertionError):
                    reference.describe(self.cases[0], reference.FIXTURES / sample["file"])
        for field in ("Password", "Notes"):
            with self.assertRaises(AssertionError):
                reference.compare_fields({}, {field: checks.Field("", field != "Password")})


@unittest.skipUnless(reference.BINARY.is_file(), "build the locked reference helper to run live save/guard tests")
class LiveReferenceWriterTest(unittest.TestCase):
    def setUp(self):
        self.case = next(c for c in reference.cases() if c["kdf"] == "argon2d" and c["cipher"] == "chacha20")

    def test_actual_single_edit_creates_readable_output_and_keeps_source_bytes(self):
        source = reference.FIXTURES / self.case["source_file"]
        before = source.read_bytes()
        with tempfile.TemporaryDirectory(prefix=".reference-test-", dir=REFERENCE) as directory:
            output = Path(directory) / "new.kdbx"
            run = invoke(self.case, output)
            self.assertEqual(run.returncode, 0, run.stderr)
            record = reference.describe(self.case, output)
            self.assertEqual(record["summary"]["history_entries"], 5)
            self.assertFalse(record["lossless_roundtrip"])
            self.assertEqual(json.loads(run.stdout)["history_after"], 5)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(source.read_bytes(), before)

    def test_existing_output_and_same_input_are_never_overwritten(self):
        source = reference.FIXTURES / self.case["source_file"]
        before = source.read_bytes()
        with tempfile.TemporaryDirectory(prefix=".reference-test-", dir=REFERENCE) as directory:
            existing = Path(directory) / "existing.kdbx"
            existing.write_bytes(b"existing-public-test-content")
            for output in (existing, source):
                run = invoke(self.case, output)
                self.assertNotEqual(run.returncode, 0)
                self.assertEqual(json.loads(run.stderr)["error"], "output_create_failed")
                self.assertEqual(run.stdout, "")
            self.assertEqual(existing.read_bytes(), b"existing-public-test-content")
        self.assertEqual(source.read_bytes(), before)

    def test_invalid_credentials_arguments_target_and_format_do_not_create_output(self):
        attempts = [
            ({"password": "wrong-public-test-password\n"}, "database_open_failed"),
            ({"password": "\n"}, "invalid_password_input"),
            ({"password": "public\nsecond-line\n"}, "invalid_password_input"),
            ({"password": "x" * 4097}, "password_too_long"),
            ({"uuid": "invalid-uuid"}, "invalid_uuid"),
            ({"uuid": "ffffffffffffffffffffffffffffffff"}, "entry_not_found"),
            ({"kdf": "unsupported"}, "unsupported_kdf"),
            ({"cipher": "unsupported"}, "unsupported_cipher"),
        ]
        original = read_kdbx((reference.FIXTURES / self.case["source_file"]).read_bytes(), self.case["password"])
        username = checks.fields(checks.current_entries(original)[self.case["entry_uuid"]])["UserName"].value
        attempts.append(({"username": username}, "username_is_unchanged"))
        for version in ("31", "40"):
            attempts.append(({"source": reference.FIXTURES / ("m" + version + "-passkey-edit1.kdbx"),
                              "password": "keex-synthetic-M" + version + "-PASSKEY\n"}, "input_is_not_kdbx_4_1"))
        with tempfile.TemporaryDirectory(prefix=".reference-test-", dir=REFERENCE) as directory:
            output = Path(directory) / "must-not-exist.kdbx"
            for arguments, error in attempts:
                with self.subTest(error=error):
                    run = invoke(self.case, output, **arguments)
                    self.assertNotEqual(run.returncode, 0)
                    self.assertEqual(json.loads(run.stderr), {"ok": False, "error": error})
                    self.assertEqual(run.stdout, "")
                    self.assertFalse(output.exists())

    @unittest.skipUnless(KEEPASSXC, "keepassxc-cli required for a real save before injected publication failure")
    def test_manifest_publication_failure_cleans_only_new_outputs(self):
        with tempfile.TemporaryDirectory(prefix=".reference-test-", dir=REFERENCE) as directory:
            fixtures = Path(directory)
            source = fixtures / self.case["source_file"]
            source.write_bytes((reference.FIXTURES / self.case["source_file"]).read_bytes())
            before = source.read_bytes()
            manifest = fixtures / "rust_writer_manifest.json"
            original_open = Path.open

            def fail_manifest(path, *args, **kwargs):
                if path == manifest and args and args[0] == "x":
                    raise OSError("injected manifest write failure")
                return original_open(path, *args, **kwargs)

            with patch.object(reference, "FIXTURES", fixtures), patch.object(reference, "MANIFEST", manifest), \
                 patch.object(reference, "cases", side_effect=lambda: iter([self.case])), \
                 patch.object(reference, "build_helper"), patch.object(Path, "open", fail_manifest), \
                 patch.object(sys, "argv", [str(REFERENCE / "generate.py")]):
                with self.assertRaisesRegex(OSError, "injected"):
                    reference.main()
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual({p.name for p in fixtures.iterdir()}, {source.name})


class ReferenceGeneratorGuardTest(unittest.TestCase):
    def test_existing_manifest_noop_is_read_only_and_does_not_build(self):
        before = reference.MANIFEST.read_bytes()
        paths = [reference.FIXTURES / case["file"] for case in reference.cases()]
        stats = {p: (p.stat().st_mtime_ns, reference.digest(p.read_bytes())) for p in paths}
        with patch.object(sys, "argv", [str(REFERENCE / "generate.py")]), \
             patch.object(reference, "build_helper", side_effect=AssertionError("no-op must not build")), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(reference.main(), 0)
        self.assertEqual(reference.MANIFEST.read_bytes(), before)
        self.assertEqual({p: (p.stat().st_mtime_ns, reference.digest(p.read_bytes())) for p in paths}, stats)

    def test_unregistered_output_is_refused_before_build(self):
        case = next(reference.cases())
        with tempfile.TemporaryDirectory(prefix=".reference-test-", dir=REFERENCE) as directory:
            fixtures = Path(directory)
            existing = fixtures / case["file"]
            existing.write_bytes(b"unregistered-public-test-content")
            with patch.object(reference, "FIXTURES", fixtures), \
                 patch.object(reference, "MANIFEST", fixtures / "manifest.json"), \
                 patch.object(reference, "build_helper", side_effect=AssertionError("must refuse before build")), \
                 patch.object(sys, "argv", [str(REFERENCE / "generate.py")]):
                with self.assertRaises(FileExistsError):
                    reference.main()
            self.assertEqual(existing.read_bytes(), b"unregistered-public-test-content")
            self.assertEqual({p.name for p in fixtures.iterdir()}, {case["file"]})

    def test_tampered_case_parameters_are_rejected_before_reading_outputs(self):
        data = json.loads(reference.MANIFEST.read_text())
        data["samples"][0]["cipher"] = "unsupported"
        with tempfile.TemporaryDirectory(prefix=".reference-test-", dir=REFERENCE) as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps(data))
            with patch.object(reference, "MANIFEST", manifest), \
                 patch.object(sys, "argv", [str(REFERENCE / "generate.py")]):
                with self.assertRaisesRegex(AssertionError, "case parameters"):
                    reference.main()


if __name__ == "__main__":
    unittest.main()

