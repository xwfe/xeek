"""K069：源内容与九份参考 writer 产物的独立不变量及差异清单回归。"""
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent / "fixtures" / "kdbx"
sys.path[:0] = [str(HERE), str(FIXTURES), str(HERE.parent / "kdbx_oracle")]
import source
import vault_source
from contract import CONTRACT, Field, inspect_vault, record_from_pairs
from kdbx_oracle import read_kdbx, read_plain_xml
from kdbx_oracle.semantic import canonicalize, diff, summarize, uuid_hex

STANDARD = {"Title", "UserName", "Password", "URL", "Notes"}
VOLATILE = [
    "KeePassFile/Meta/Generator",
    "KeePassFile/Meta/CustomData/Item=KPXC_RANDOM_SLUG",
    "KeePassFile/Meta/CustomData/Item=_LAST_MODIFIED",
    "KeePassFile/Root/Group=6f542f7e7f8288660938b7000a25e046/Group=619866709f661f4847cc86d411ca5bf1/CustomData/Item=_LAST_MODIFIED",
    "KeePassFile/Root/Group=6f542f7e7f8288660938b7000a25e046/Group=619866709f661f4847cc86d411ca5bf1/Entry=8965805d6caa1155bdc9ed01dcb11d04/CustomData/Item=_LAST_MODIFIED",
]
KEEPASSXC = shutil.which("keepassxc-cli")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def current_entries(decoded):
    entries = [entry for group in decoded.root.iter("Group") for entry in group.findall("Entry")]
    result = {uuid_hex(entry.findtext("UUID")): entry for entry in entries}
    if len(result) != len(entries):
        raise AssertionError("duplicate current entry UUID")
    return result


def fields(entry):
    result = {}
    for string in entry.findall("String"):
        key, value = string.findtext("Key"), string.find("Value")
        if key in result:
            raise AssertionError("duplicate String key")
        protected = value is not None and any(value.get(name, "").lower() == "true"
                                               for name in ("Protected", "ProtectInMemory"))
        result[key] = Field("" if value is None else value.text or "", protected)
    return result


def snapshot(decoded, entry):
    """包装成真实已知结构以比较单 Entry；只去掉其 History，现有历史另逐项比较。"""
    entry = copy.deepcopy(entry)
    for history in entry.findall("History"):
        entry.remove(history)
    root = ET.Element("KeePassFile")
    group = ET.SubElement(ET.SubElement(root, "Root"), "Group")
    ET.SubElement(group, "UUID").text = source.uid("group/root")
    group.append(entry)
    return canonicalize(replace(decoded, root=root))


def changes(a, b, ignore=VOLATILE):
    return sorted(item.label for item in diff(canonicalize(a), canonicalize(b), ignore=ignore))


def entry_path(group, name):
    return ("KeePassFile/Root/Group=" + uuid_hex(source.uid("group/root"))
            + "/Group=" + uuid_hex(source.uid(group)) + "/Entry=" + uuid_hex(source.uid(name)))


def expected_import(format):
    web = "KeePassFile/Root/Group=" + uuid_hex(source.uid("group/root")) + "/Group=" + uuid_hex(source.uid("group/web"))
    expected = {"changed/value " + web + "/IconID"}
    if format == "3.1":
        return expected | {"added KeePassFile/Meta/CustomData"}
    expected.add("added KeePassFile/Meta/SettingsChanged")
    attachments = [
        ("group/web", "reference", "shared.txt", ""),
        ("group/web", "login", "notes.txt", ""),
        ("group/web", "login", "shared.txt", ""),
        ("group/web", "login", "blob.bin", "/History/Entry"),
        ("group/web", "login", "shared.txt", "/History/Entry"),
        ("group/ssh", "keeagent", "KeeAgent.settings", ""),
        ("group/ssh", "keeagent", "id_ed25519", ""),
        ("vault/group", "vault/identity", "合成凭据.txt", ""),
        ("vault/group", "vault/document", "合成凭据.txt", ""),
    ]
    expected.update("changed/attrs " + entry_path(group, name) + history + "/Binary=" + key + "/Value"
                    for group, name, key, history in attachments)
    if format == "4.1":
        expected |= {
            "removed " + web + "/CustomData/Item=keex.fixture.group/LastModificationTime",
            "removed " + entry_path("group/web", "login") + "/CustomData/Item=keex.fixture.entry/LastModificationTime",
        }
    return expected


class VaultCorpusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((FIXTURES / "vault_manifest.json").read_text(encoding="utf-8"))
        cls.data = []
        for sample in cls.manifest["samples"]:
            xml = vault_source.build(sample["format"], sample["id"])
            decoded = [read_kdbx((FIXTURES / stage["file"]).read_bytes(),
                                 password=sample["credentials"]["password"]) for stage in sample["stages"]]
            cls.data.append((sample, xml, read_plain_xml(xml), decoded))

    def test_matrix_hashes_and_source_provenance(self):
        self.assertEqual([s["format"] for s, *_ in self.data], ["3.1", "4.0", "4.1"])
        self.assertEqual(self.manifest["ignored_metadata_patterns"], VOLATILE)
        for name, expected in self.manifest["provenance"].items():
            if name == "vault_generate.py":
                # 原生成版本保留；如仅修订比较策略，另记当前策略代码版本。
                expected = self.manifest.get("analysis", {}).get("comparison_policy_generator_sha256", expected)
            self.assertEqual(digest((FIXTURES / name).read_bytes()), expected)
        for sample, xml, _, decoded in self.data:
            self.assertEqual(digest(xml), sample["source_sha256"])
            self.assertEqual(xml, vault_source.build(sample["format"], sample["id"]))
            self.assertEqual(sample["client"]["version"], "2.7.12")
            self.assertEqual([stage["name"] for stage in sample["stages"]], ["import", "edit1", "edit2"])
            for stage, opened in zip(sample["stages"], decoded):
                self.assertEqual(digest((FIXTURES / stage["file"]).read_bytes()), stage["sha256"])
                self.assertEqual(opened.version, sample["format"])
                self.assertEqual(summarize(opened), stage["summary"])

    def test_domain_matrix_and_expected_diagnostics_survive_every_stage(self):
        self.assertEqual(len(vault_source.records()), 24)
        self.assertEqual({item["type"] for item in vault_source.records()}, set(CONTRACT["types"]))
        expected = {"missing-link": ("valid", {"missing_target"}),
                    "future-schema": ("read_only", {"unknown_schema"}),
                    "future-field": ("read_only", {"unknown_keex_field"}),
                    "legacy-conflict": ("read_only", {"legacy_parent_conflict"})}
        for sample, _, original, decoded in self.data:
            for opened in [original, *decoded]:
                entries = current_entries(opened)
                records = [record_from_pairs(vault_source.ref(item["name"]),
                            list(fields(entries[vault_source.ref(item["name"])]).items()))
                           for item in vault_source.records()]
                for item, result in zip(vault_source.records(), inspect_vault(records)):
                    with self.subTest(sample=sample["id"], item=item["name"]):
                        self.assertEqual((result.status, {issue.code for issue in result.issues}),
                                         expected.get(item["name"], ("valid", set())))

    def test_all_original_fields_and_protection_survive_except_requested_username(self):
        for sample, _, original, decoded in self.data:
            originals = current_entries(original)
            for index, opened in enumerate(decoded):
                actual = current_entries(opened)
                self.assertEqual(set(actual), set(originals))
                for identifier, original_entry in originals.items():
                    expected = fields(original_entry)
                    if index and identifier == vault_source.ref(vault_source.EDIT_NAME):
                        expected["UserName"] = Field(vault_source.EDIT_VALUES[index - 1])
                    observed = fields(actual[identifier])
                    for key, value in expected.items():
                        with self.subTest(sample=sample["id"], stage=index, entry=identifier, key=key):
                            self.assertEqual(observed.get(key), value)
                    self.assertLessEqual(set(observed) - set(expected), STANDARD)

    def test_exact_import_variations_are_explicit(self):
        for sample, _, original, decoded in self.data:
            expected = expected_import(sample["format"])
            self.assertEqual(set(changes(original, decoded[0])), expected)
            # 源基线不会在导入后重置；原始 writer 差异一直留到第二次保存。
            for opened in decoded[1:]:
                self.assertLessEqual(expected, set(changes(original, opened)))

    def test_manifest_records_raw_and_filtered_source_and_previous_differences(self):
        for sample, _, original, decoded in self.data:
            previous = original
            for stage, opened in zip(sample["stages"], decoded):
                self.assertEqual(changes(original, opened, []), stage["raw_source_changes"])
                self.assertEqual(changes(original, opened), stage["source_changes"])
                self.assertEqual(changes(previous, opened, []), stage["raw_previous_changes"])
                self.assertEqual(changes(previous, opened), stage["previous_changes"])
                previous = opened

    def test_two_saves_only_change_probe_and_append_one_history(self):
        target = entry_path("vault/group", "vault/" + vault_source.EDIT_NAME)
        allowed_values = {target + "/String=UserName/Value", target + "/Times/LastAccessTime",
                          target + "/Times/LastModificationTime"}
        for sample, _, _, decoded in self.data:
            for index in (1, 2):
                actual = diff(canonicalize(decoded[index - 1]), canonicalize(decoded[index]), ignore=VOLATILE)
                expected_history = target + ("/History" if index == 1 else "/History/Entry#1")
                self.assertEqual(sum(change.path == target + "/String=UserName/Value" for change in actual), 1)
                self.assertEqual(sum(change.path == expected_history and change.kind == "added" for change in actual), 1)
                for change in actual:
                    self.assertTrue(
                        (change.kind == "changed" and change.aspect == "value" and change.path in allowed_values)
                        or (change.kind == "added" and change.path == expected_history), change.label)

    def test_new_history_is_previous_snapshot_and_existing_history_is_unchanged(self):
        for sample, _, original, decoded in self.data:
            for index in (1, 2):
                before, after = current_entries(decoded[index - 1]), current_entries(decoded[index])
                target = vault_source.ref(vault_source.EDIT_NAME)
                previous_history = before[target].findall("History/Entry")
                new_history = after[target].findall("History/Entry")
                self.assertEqual(len(new_history), len(previous_history) + 1)
                self.assertEqual(diff(snapshot(decoded[index - 1], before[target]),
                                      snapshot(decoded[index], new_history[-1])), [])
                for identifier, old_entry in before.items():
                    old_history = old_entry.findall("History/Entry")
                    kept_history = after[identifier].findall("History/Entry")
                    self.assertGreaterEqual(len(kept_history), len(old_history))
                    for a, b in zip(old_history, kept_history):
                        self.assertEqual(diff(snapshot(decoded[index - 1], a), snapshot(decoded[index], b)), [])
            original_card = current_entries(original)[vault_source.ref("card-old")].find("History/Entry")
            for opened in decoded:
                card_history = current_entries(opened)[vault_source.ref("card-old")].find("History/Entry")
                original_fields, kept_fields = fields(original_card), fields(card_history)
                for key, value in original_fields.items():
                    self.assertEqual(kept_fields.get(key), value)
                # KeePassXC 给原本缺省的标准字段补空值；不得容许自定义项或非空新增值。
                for key in set(kept_fields) - set(original_fields):
                    self.assertIn(key, STANDARD)
                    self.assertEqual(kept_fields[key].value, "")
                self.assertEqual(diff(snapshot(original, original_card), snapshot(opened, card_history)), [])
                self.assertIn("X-Vault-History-Only", kept_fields)

    def test_attachments_bytes_references_protection_and_recycle_are_preserved(self):
        for sample, _, original, decoded in self.data:
            for opened in decoded:
                self.assertEqual(len(opened.binaries), 6)
                self.assertEqual(sum(len(data) for data, _ in opened.binaries.values()), 3300)
                for identifier, source_entry in current_entries(original).items():
                    destination = current_entries(opened)[identifier]
                    pairs = [(source_entry, destination), *zip(source_entry.findall("History/Entry"),
                                                             destination.findall("History/Entry"))]
                    for old, new in pairs:
                        binaries = {binary.findtext("Key"): binary for binary in new.findall("Binary")}
                        self.assertEqual(len(binaries), len(old.findall("Binary")))
                        for attachment in old.findall("Binary"):
                            key = attachment.findtext("Key")
                            original_data, _ = original.binaries[attachment.find("Value").get("Ref")]
                            data, protected = opened.binaries[binaries[key].find("Value").get("Ref")]
                            self.assertEqual(data, original_data)
                            self.assertEqual(protected, sample["format"] != "3.1")
                recycle = next(g for g in opened.root.iter("Group")
                               if uuid_hex(g.findtext("UUID")) == uuid_hex(source.uid("group/recycle")))
                self.assertIn(vault_source.ref("trash-card"),
                              {uuid_hex(e.findtext("UUID")) for e in recycle.findall("Entry")})
                identity = current_entries(opened)[vault_source.ref("identity")].find("Binary/Value").get("Ref")
                document = current_entries(opened)[vault_source.ref("document")].find("Binary/Value").get("Ref")
                self.assertEqual(identity, document)
                self.assertEqual(opened.binaries[identity][0], vault_source.DOCUMENT_BYTES)

    def test_incomplete_esim_money_dates_and_old_passkey_are_literal(self):
        for _, _, _, decoded in self.data:
            for opened in decoded:
                entries = current_entries(opened)
                profile = fields(entries[vault_source.ref("profile-uninstalled")])
                self.assertFalse({"keex.telecom.number", "keex.telecom.iccid", "keex.telecom.eid"} & profile.keys())
                self.assertEqual(json.loads(profile["keex.telecom.installState"].value)["value"], "not_installed")
                billing = json.loads(fields(entries[vault_source.ref("subscription-1")])["keex.subscription.billing"].value)
                self.assertEqual((billing["amount"], billing["currency"], billing["period"]["anchor"]["value"]),
                                 ("9.90", "USD", "2026-01-31"))
                self.assertEqual(billing["recordedAt"], "2026-10-18T00:00:00Z")
                plan = fields(entries[vault_source.ref("plan")])
                local = json.loads(plan["keex.telecom.validFrom"].value)
                self.assertEqual((local["precision"], local["timeZone"], local["fold"]),
                                 ("local", "America/New_York", 1))
                passkey = fields(entries[uuid_hex(source.uid("passkey"))])
                self.assertEqual(passkey["keex.parentEntryUuid"], Field(source.uid("vault/service-login"), True))
                self.assertEqual(passkey["KPEX_PASSKEY_PRIVATE_KEY_PEM"], Field(source.passkey_pem("current"), True))

    def test_similar_unknown_metadata_is_never_filtered(self):
        original = self.data[0][3][0]
        for key in ("_LAST_MODIFIED_PRIVATE_NOTE", "KPXC_RANDOM_SLUG_BACKUP"):
            modified = copy.deepcopy(original)
            custom = modified.root.find("Meta/CustomData")
            if custom is None:
                custom = ET.SubElement(modified.root.find("Meta"), "CustomData")
            item = ET.SubElement(custom, "Item")
            ET.SubElement(item, "Key").text = key
            ET.SubElement(item, "Value").text = "synthetic unknown metadata"
            actual = changes(original, modified)
            self.assertEqual(len(actual), 1)
            self.assertTrue(actual[0].endswith("/Item=" + key))

    def test_valid_but_changed_compound_is_not_mistaken_for_unchanged_data(self):
        original = self.data[0][3][0]
        modified = copy.deepcopy(original)
        entry = current_entries(modified)[vault_source.ref("subscription-1")]
        value = next(item.find("Value") for item in entry.findall("String")
                     if item.findtext("Key") == "keex.subscription.billing")
        value.text = value.text.replace('"amount":"9.90"', '"amount":"9.91"')
        records = [record_from_pairs(vault_source.ref("subscription-1"), list(fields(entry).items()))]
        self.assertEqual(inspect_vault(records)[0].status, "valid")
        actual = diff(canonicalize(original), canonicalize(modified))
        self.assertEqual(len(actual), 1)
        self.assertTrue(actual[0].path.endswith("/String=keex.subscription.billing/Value"))
        self.assertNotIn("9.91", str(actual))

    @unittest.skipUnless(KEEPASSXC, "keepassxc-cli unavailable; independent export check not run")
    def test_keepassxc_export_agrees_on_every_current_and_history_field(self):
        # 4.x CLI XML 导出不携带附件池；本项只交叉验证字段，附件由上面单独逐字核对。
        for sample, _, _, decoded in self.data:
            for stage, opened in zip(sample["stages"], decoded):
                result = subprocess.run([KEEPASSXC, "export", "-q", "-f", "xml", str(FIXTURES / stage["file"])],
                                        input=sample["credentials"]["password"] + "\n",
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, "synthetic export failed")
                exported = read_plain_xml(result.stdout.encode("utf-8"))
                left, right = current_entries(opened), current_entries(exported)
                self.assertEqual(set(left), set(right))
                for identifier, original_entry in left.items():
                    self.assertEqual(fields(original_entry), fields(right[identifier]))
                    a, b = original_entry.findall("History/Entry"), right[identifier].findall("History/Entry")
                    self.assertEqual(len(a), len(b))
                    for old, new in zip(a, b):
                        self.assertEqual(fields(old), fields(new))


if __name__ == "__main__":
    unittest.main()
