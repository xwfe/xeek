"""新增公开合成矩阵：持久化产物、身份/引用/附件不变量及故障反例。"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "kdbx"
sys.path[:0] = [str(FIXTURES), str(FIXTURES.parent.parent / "kdbx_oracle")]
import matrix_checks as checks
import matrix_generate
import matrix_source as source
import vault_source
from kdbx_oracle import read_kdbx, read_plain_xml
from kdbx_oracle.semantic import canonicalize, diff, uuid_hex

KEEPASSXC = shutil.which("keepassxc-cli")
TYPE_MULTIPLIERS = {"login": 4, "finance_account": 1, "payment_card": 3, "subscription": 2,
                    "telecom_line": 1, "sim_profile": 3, "telecom_plan": 1, "identity_document": 1,
                    "document": 1, "membership_card": 1, "gift_card": 1, "maintenance": 1, "secure_note": 5}


def load_stage(sample, index):
    return read_kdbx((FIXTURES / sample["stages"][index]["file"]).read_bytes(),
                     password=sample["credentials"]["password"])


def attachment_map(decoded, entry):
    pairs = [(b.findtext("Key"), b.find("Value").get("Ref")) for b in entry.findall("Binary")]
    if len(dict(pairs)) != len(pairs):
        raise AssertionError("duplicate attachment name")
    return {name: decoded.binaries[ref] for name, ref in pairs}


class MatrixCorpusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((FIXTURES / "matrix_manifest.json").read_text(encoding="utf-8"))
        cls.samples = cls.manifest["samples"]
        cls.passkeys = [s for s in cls.samples if s["kind"] == "passkey"]
        cls.scales = [s for s in cls.samples if s["kind"] == "scale"]

    def test_matrix_scope_file_hashes_and_current_source_provenance(self):
        self.assertEqual([s["id"] for s in self.samples], [c["id"] for c in source.cases()])
        self.assertEqual(sum(len(s["stages"]) for s in self.samples), 17)
        self.assertEqual(self.manifest["ignored_metadata_paths"], list(checks.VOLATILE))
        self.assertFalse(any("*" in path or "?" in path for path in checks.VOLATILE))
        for name, digest in self.manifest["provenance"].items():
            self.assertEqual(checks.digest((FIXTURES / name).read_bytes()), digest, name)
        for sample in self.samples:
            case = source.case_by_id(sample["id"])
            xml = source.build(case)
            self.assertEqual(checks.digest(xml), sample["source_sha256"])
            self.assertEqual(len(xml), sample["source_bytes"])
            for stage in sample["stages"]:
                data = (FIXTURES / stage["file"]).read_bytes()
                self.assertEqual((len(data), checks.digest(data)), (stage["bytes"], stage["sha256"]))

    def test_every_saved_stage_reproduces_the_full_reviewed_differences(self):
        for sample in self.samples:
            with self.subTest(sample=sample["id"]):
                case = source.case_by_id(sample["id"])
                actual = matrix_generate.describe(case, sample["credentials"]["password"], source.build(case),
                                                   [FIXTURES / stage["file"] for stage in sample["stages"]])
                self.assertEqual(actual, sample["stages"])

    def test_three_same_rp_credentials_keep_identity_pairing_and_valid_p256_keys(self):
        for sample in self.passkeys:
            original = read_plain_xml(source.build(source.case_by_id(sample["id"])))
            originals = checks.current_entries(original)
            for index in range(3):
                opened = load_stage(sample, index)
                entries = checks.current_entries(opened)
                modern = [e for e in entries.values() if checks.fields(e).get("KPEX_PASSKEY_RELYING_PARTY") ==
                          checks.Field("passkey.example.com")]
                self.assertEqual(len(modern), 3)
                maps = [checks.fields(entries[source.hex_uid(name)]) for name in source.PASSKEY_NAMES]
                self.assertEqual(maps[0]["KPEX_PASSKEY_USER_HANDLE"], maps[2]["KPEX_PASSKEY_USER_HANDLE"])
                self.assertNotEqual(maps[0]["KPEX_PASSKEY_USER_HANDLE"], maps[1]["KPEX_PASSKEY_USER_HANDLE"])
                self.assertEqual(len({m["KPEX_PASSKEY_CREDENTIAL_ID"].value for m in maps}), 3)
                public_keys = set()
                for name, actual in zip(source.PASSKEY_NAMES, maps):
                    expected = checks.fields(originals[source.hex_uid(name)])
                    for key in expected:
                        if key.startswith("KPEX_") or key == "keex.parentEntryUuid":
                            self.assertEqual(actual[key], expected[key])
                    self.assertTrue(actual["KPEX_PASSKEY_PRIVATE_KEY_PEM"].protected)
                    self.assertTrue(actual["KPEX_PASSKEY_USER_HANDLE"].protected)
                    self.assertTrue(actual["keex.parentEntryUuid"].protected)
                    key = serialization.load_pem_private_key(actual["KPEX_PASSKEY_PRIVATE_KEY_PEM"].value.encode(), None)
                    self.assertIsInstance(key.curve, ec.SECP256R1)
                    public_keys.add(key.public_key().public_bytes(serialization.Encoding.DER,
                                                                  serialization.PublicFormat.SubjectPublicKeyInfo))
                self.assertEqual(len(public_keys), 3)
                self.assertIn(source.hex_uid("passkey-legacy"), entries)
                target = entries[source.hex_uid("passkey")]
                self.assertEqual(len(target.findall("History/Entry")), index)
                for previous in target.findall("History/Entry"):
                    self.assertEqual(checks.fields(previous)["KPEX_PASSKEY_PRIVATE_KEY_PEM"],
                                     maps[0]["KPEX_PASSKEY_PRIVATE_KEY_PEM"])

    def test_scale_has_exact_counts_types_relations_events_and_diagnostics(self):
        for sample in self.scales:
            blocks = sample["count"] // 25
            for index in range(2):
                opened = load_stage(sample, index)
                summary = checks.summary(opened)
                self.assertEqual((summary["entries"], summary["groups"], summary["history_entries"],
                                  summary["recycle_bin"]["entries"]), (sample["count"], blocks + 2, blocks + index, blocks))
                self.assertEqual(summary["type_counts"], {k: v * blocks for k, v in TYPE_MULTIPLIERS.items()})
                self.assertEqual((summary["relations"], summary["rules"], summary["events"]),
                                 (23 * blocks, blocks, 2 * blocks))
                self.assertEqual(summary["diagnostics"], {
                    "valid:": 21 * blocks, "valid:missing_target": blocks,
                    "read_only:legacy_parent_conflict": blocks,
                    "read_only:unknown_keex_field": blocks, "read_only:unknown_schema": blocks,
                })
                self.assertEqual(summary["attachments"]["current_references"], 4 * blocks + 1)
                self.assertEqual(summary["attachments"]["history_references"], 1)

    def test_scale_references_are_local_and_high_fan_in_is_explicit(self):
        for sample in self.scales:
            opened = load_stage(sample, 1)
            groups = {g.findtext("Name"): g for g in opened.root.iter("Group")}
            all_entries = checks.current_entries(opened)
            # 回收站条目的关系也纳入全库身份唯一性，不只检查普通批次组。
            dynamic_ids = [key.rsplit(".", 1)[1] for entry in all_entries.values()
                           for key in checks.fields(entry) if key.startswith(source.DYNAMIC_PREFIXES)]
            first = {checks.fields(e)["Title"].value: e for e in groups["合成批次0000"].findall("Entry")}
            first_service = uuid_hex(first["合成服务账户"].findtext("UUID"))
            for block in range(sample["count"] // 25):
                group = groups[f"合成批次{block:04d}"]
                by_title = {checks.fields(e)["Title"].value: e for e in group.findall("Entry")}
                service = uuid_hex(by_title["合成服务账户"].findtext("UUID"))
                document = uuid_hex(by_title["合成地址证明"].findtext("UUID"))
                missing = uuid_hex(by_title["合成缺失引用"].findtext("UUID"))
                local_ids = {uuid_hex(e.findtext("UUID")) for e in group.findall("Entry")}
                for entry in group.findall("Entry"):
                    values = checks.fields(entry)
                    for key, value in values.items():
                        if not key.startswith("keex.relation."):
                            continue
                        target = json.loads(value.value)["target"]
                        if values["Title"].value == "合成集中关联账户":
                            self.assertEqual(target, first_service)
                        elif values["Title"].value == "合成缺失引用":
                            self.assertNotIn(target, all_entries)
                        else:
                            self.assertIn(target, local_ids)
                for subscription, card in (("合成订阅1", "合成旧卡"), ("合成订阅2", "合成新卡")):
                    payment = next(json.loads(v.value)["target"] for k, v in checks.fields(by_title[subscription]).items()
                                   if k.startswith("keex.relation.") and json.loads(v.value)["type"] == "paidBy")
                    self.assertEqual(payment, uuid_hex(by_title[card].findtext("UUID")))
                hub = checks.fields(by_title["合成集中关联账户"])
                self.assertEqual(next(json.loads(v.value)["target"] for k, v in hub.items()
                                      if k.startswith("keex.relation.")), first_service)
                legacy = checks.fields(by_title["合成旧关联冲突"])
                self.assertEqual(legacy["keex.parentEntryUuid"].value, service)
                self.assertEqual(next(json.loads(v.value)["target"] for k, v in legacy.items()
                                      if k.startswith("keex.relation.")), missing)
                maintenance = checks.fields(by_title["合成维护事项"])
                rules = {k.removeprefix("keex.lifecycle.rule.") for k in maintenance if k.startswith("keex.lifecycle.rule.")}
                events = {k.removeprefix("keex.lifecycle.event."): json.loads(v.value)
                          for k, v in maintenance.items() if k.startswith("keex.lifecycle.event.")}
                self.assertEqual(len(rules), 1)
                for event in events.values():
                    self.assertIn(event["ruleId"], rules)
                    if event["kind"] == "completed":
                        self.assertEqual(event["evidence"], {"entry": document, "attachment": "合成凭据.txt"})
                    else:
                        self.assertIn(event["targetEventId"], events)
                        self.assertEqual(events[event["targetEventId"]]["kind"], "completed")
            self.assertEqual(len(dynamic_ids), len(set(dynamic_ids)))

    def test_all_original_current_and_history_attachment_bytes_flags_and_sharing(self):
        for sample in self.samples:
            original = read_plain_xml(source.build(source.case_by_id(sample["id"])))
            originals = checks.current_entries(original)
            expected_pool = Counter(checks.digest(data) for data, _ in original.binaries.values())
            for index in range(len(sample["stages"])):
                opened = load_stage(sample, index)
                entries = checks.current_entries(opened)
                self.assertEqual(Counter(checks.digest(data) for data, _ in opened.binaries.values()), expected_pool)
                self.assertTrue(all(flag == (sample["format"] != "3.1") for _, flag in opened.binaries.values()))
                for identifier, entry in originals.items():
                    pairs = [(entry, entries[identifier])]
                    pairs += list(zip(entry.findall("History/Entry"), entries[identifier].findall("History/Entry")))
                    self.assertGreaterEqual(len(entries[identifier].findall("History/Entry")), len(entry.findall("History/Entry")))
                    for before, after in pairs:
                        expected, actual = attachment_map(original, before), attachment_map(opened, after)
                        self.assertEqual(actual.keys(), expected.keys())
                        for name, (data, _) in expected.items():
                            self.assertEqual(actual[name][0], data)
                if sample["kind"] == "scale":
                    self.assertEqual(len(opened.binaries), 3)
                    self.assertEqual(sum(len(data) for data, _ in opened.binaries.values()),
                                     4096 + source.ATTACHMENT_BYTES[sample["attachment"]] + len(vault_source.DOCUMENT_BYTES))
                    references = {}
                    for entry in entries.values():
                        for binary in entry.findall("Binary"):
                            references.setdefault(binary.findtext("Key"), set()).add(binary.find("Value").get("Ref"))
                    self.assertTrue(all(len(refs) == 1 for refs in references.values()))

    @unittest.skipUnless(KEEPASSXC, "keepassxc-cli unavailable; reference export not run")
    def test_reference_cli_export_matches_every_current_and_history_field(self):
        for sample in self.samples:
            for index, stage in enumerate(sample["stages"]):
                opened = load_stage(sample, index)
                run = subprocess.run([KEEPASSXC, "export", "-q", "-f", "xml", str(FIXTURES / stage["file"])],
                                     input=sample["credentials"]["password"] + "\n",
                                     capture_output=True, text=True, timeout=60)
                self.assertEqual(run.returncode, 0, "synthetic reference export failed")
                exported = read_plain_xml(run.stdout.encode())
                left, right = checks.current_entries(opened), checks.current_entries(exported)
                self.assertEqual(left.keys(), right.keys())
                for identifier, entry in left.items():
                    self.assertEqual(checks.fields(entry), checks.fields(right[identifier]))
                    a, b = entry.findall("History/Entry"), right[identifier].findall("History/Entry")
                    self.assertEqual(len(a), len(b))
                    for old, new in zip(a, b):
                        self.assertEqual(checks.fields(old), checks.fields(new))

    def test_recorded_resource_measurements_have_units_and_no_fake_threshold(self):
        self.assertIn("ru_maxrss normalized to bytes", self.manifest["measurement_method"])
        for sample in self.scales:
            runs = sample["measurements"]["oracle_final"]
            self.assertEqual(len(runs), 3)
            for run in runs:
                self.assertEqual(run["entries"], sample["count"])
                self.assertEqual(run["statuses"], {"valid": sample["count"] * 22 // 25, "read_only": sample["count"] * 3 // 25})
                self.assertGreater(run["open_seconds"], 0)
                self.assertGreater(run["contract_seconds"], 0)
                self.assertGreater(run["open_peak_rss_bytes"], 0)
                self.assertGreaterEqual(run["combined_peak_rss_bytes"], run["open_peak_rss_bytes"])


class MatrixMutationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = json.loads((FIXTURES / "matrix_manifest.json").read_text(encoding="utf-8"))
        cls.sample = next(s for s in manifest["samples"] if s["id"] == "M41-PASSKEY")
        cls.case = source.case_by_id(cls.sample["id"])
        cls.before = load_stage(cls.sample, 0)
        cls.saved = load_stage(cls.sample, 1)

    def assert_rejected(self, mutate):
        changed = copy.deepcopy(self.saved)
        mutate(changed)
        with self.assertRaises(AssertionError):
            checks.verify_transition(self.before, changed, self.case)

    def test_passkey_credential_to_key_swap_is_rejected(self):
        def mutate(db):
            entries = checks.current_entries(db)
            a, b = [entries[source.hex_uid(name)] for name in source.PASSKEY_NAMES[:2]]
            av, bv = [next(s.find("Value") for s in e.findall("String")
                           if s.findtext("Key") == "KPEX_PASSKEY_PRIVATE_KEY_PEM") for e in (a, b)]
            av.text, bv.text = bv.text, av.text
        self.assert_rejected(mutate)

    def test_protection_downgrade_is_rejected(self):
        def mutate(db):
            entry = checks.current_entries(db)[source.hex_uid("matrix/passkey-b")]
            value = next(s.find("Value") for s in entry.findall("String")
                         if s.findtext("Key") == "KPEX_PASSKEY_USER_HANDLE")
            value.set("Protected", "False")
        self.assert_rejected(mutate)

    def test_valid_billing_change_is_rejected_and_redacted(self):
        def mutate(db):
            entry = checks.current_entries(db)[vault_source.ref("subscription-1")]
            value = next(s.find("Value") for s in entry.findall("String")
                         if s.findtext("Key") == "keex.subscription.billing")
            value.text = value.text.replace('"9.90"', '"9.91"')
            changes = diff(canonicalize(self.saved), canonicalize(db))
            self.assertEqual(len(changes), 1)
            self.assertNotIn("9.91", str(changes))
        self.assert_rejected(mutate)

    def test_new_history_with_wrong_private_key_is_rejected(self):
        def mutate(db):
            history = checks.current_entries(db)[source.hex_uid("passkey")].find("History/Entry")
            value = next(s.find("Value") for s in history.findall("String")
                         if s.findtext("Key") == "KPEX_PASSKEY_PRIVATE_KEY_PEM")
            value.text = "SYNTHETIC-DAMAGED-PEM"
        self.assert_rejected(mutate)

    def test_old_history_removal_is_rejected(self):
        def mutate(db):
            entry = checks.current_entries(db)[vault_source.ref("card-old")]
            entry.remove(entry.find("History"))
        self.assert_rejected(mutate)

    def test_attachment_content_mutation_is_rejected(self):
        def mutate(db):
            key = next(iter(db.binaries))
            data, protected = db.binaries[key]
            db.binaries[key] = (data + b"synthetic-damage", protected)
        self.assert_rejected(mutate)

    def test_unknown_similar_metadata_is_not_filtered(self):
        def mutate(db):
            item = db.root.find("Meta/CustomData/Item")
            extra = copy.deepcopy(item)
            extra.find("Key").text = "_LAST_MODIFIED_PRIVATE_NOTE"
            db.root.find("Meta/CustomData").append(extra)
        self.assert_rejected(mutate)


if __name__ == "__main__":
    unittest.main()

