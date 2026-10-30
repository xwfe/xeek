"""K003：隔离 Rust 补丁的真实往返；原候选诊断与持久样本保持不变。"""
from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reference = load_module("preservation_reference", "tests/reference_writer/generate.py")
build = load_module("preservation_build", "tests/rust_preservation/build.py")
checks = reference.checks
import candidate_minimal as minimal
from kdbx_oracle import read_kdbx, reader
from kdbx_oracle.semantic import canonicalize


class RustPreservationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cli = shutil.which("keepassxc-cli")
        if not cls.cli:
            raise RuntimeError("preservation experiment requires keepassxc-cli")
        cls.binary, _ = build.build_helper()
        temporary = tempfile.TemporaryDirectory(prefix="cases-", dir=build.HERE / "target")
        cls.addClassCleanup(temporary.cleanup)
        cls.work = Path(temporary.name)
        cls.sequence = 0

    def write_input(self, name, data):
        path = self.work / (name + ".kdbx")
        path.write_bytes(data)
        return path

    @staticmethod
    def mixed_order_label(decoded):
        identifier = checks.uuid_hex(decoded.root.findtext("Root/Group/UUID"))
        return "order KeePassFile/Root/Group=" + identifier

    @staticmethod
    def root_children(decoded):
        return [(child.tag, child.findtext("UUID")) for child in decoded.root.find("Root/Group")
                if child.tag in ("Entry", "Group")]

    def roundtrip(self, source, password, target, username, *, kdf="aes-kdf",
                  cipher="aes", remaining=(), compare_export=True):
        original_bytes = source.read_bytes()
        before = read_kdbx(original_bytes, password)
        output = self.work / f"output-{self.sequence}.kdbx"
        self.__class__.sequence += 1
        run = subprocess.run(
            [str(self.binary), str(source), str(output), target, username, kdf, cipher],
            input=password + "\n", capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stderr, "")
        result_bytes = output.read_bytes()
        after = read_kdbx(result_bytes, password)
        counts = json.loads(run.stdout)
        self.assertTrue(counts["ok"])
        self.assertEqual(counts["bytes"], len(result_bytes))
        self.assertEqual(source.read_bytes(), original_bytes)
        self.assertEqual(after.version, "4.1")
        self.assertEqual(after.cipher, "aes256-cbc" if cipher == "aes" else "chacha20")
        expected_kdf = ({"name": "aes-kdf", "rounds": 1_000_000} if kdf == "aes-kdf" else
                        {"name": kdf, "memory": 8 * 1024 * 1024, "iterations": 2, "parallelism": 1})
        self.assertEqual(after.kdf, expected_kdf)
        old_entries, new_entries = checks.current_entries(before), checks.current_entries(after)
        self.assertEqual(old_entries.keys(), new_entries.keys())
        self.assertEqual(counts["entries"], len(new_entries))
        old_groups = [n.findtext("UUID") for n in before.root.iter("Group")]
        new_groups = [n.findtext("UUID") for n in after.root.iter("Group")]
        self.assertCountEqual(old_groups, new_groups)
        self.assertEqual(counts["groups"], len(new_groups))
        self.assertEqual(Counter(before.binaries.values()), Counter(after.binaries.values()))
        self.assertEqual(counts["attachments"], len(after.binaries))

        old_history_count = new_history_count = 0
        for identifier, original in old_entries.items():
            current = new_entries[identifier]
            fields = checks.fields(original)
            if identifier == target:
                fields["UserName"] = checks.Field(username, fields["UserName"].protected)
            self.assertEqual(checks.fields(current), fields)
            self.assertEqual(Counter(reference.attachment_values(before, original)),
                             Counter(reference.attachment_values(after, current)))
            old_history = original.findall("History/Entry")
            new_history = current.findall("History/Entry")
            expected = old_history + ([original] if identifier == target else [])
            self.assertEqual(len(expected), len(new_history))
            old_history_count += len(old_history)
            new_history_count += len(new_history)
            for wanted, actual in zip(expected, new_history, strict=True):
                self.assertEqual(checks.fields(wanted), checks.fields(actual))
                self.assertEqual(Counter(reference.attachment_values(before, wanted)),
                                 Counter(reference.attachment_values(after, actual)))
        self.assertEqual((counts["history_before"], counts["history_after"]),
                         (old_history_count, new_history_count))
        self.assertEqual(new_history_count, old_history_count + 1)

        target_path = checks.paths(before)[target]
        expected = replace(before, root=copy.deepcopy(before.root))
        expected_entry = checks.current_entries(expected)[target]
        snapshot = copy.deepcopy(expected_entry)
        for nested in snapshot.findall("History"):
            snapshot.remove(nested)
        history = expected_entry.find("History")
        if history is None:
            history = ET.SubElement(expected_entry, "History")
        history.append(snapshot)
        username_path = target_path + "/String=UserName/Value"
        mutation_paths = {username_path, target_path + "/Times/LastModificationTime"}
        # 历史容器和快照完整参与比较，不能把新增 History 整棵忽略。
        changes = checks.diff(canonicalize(expected), canonicalize(after), ignore=())
        self.assertEqual(sum(c.path == username_path and c.kind == "changed" for c in changes), 1)
        other = [c.label for c in changes if not (
            c.kind == "changed" and c.aspect == "value" and c.path in mutation_paths
        )]
        self.assertEqual(sorted(other), sorted(remaining))
        if compare_export:
            reference.reference_export({"password": password}, output, self.cli)
        else:
            run = subprocess.run([self.cli, "export", "-q", "-f", "xml", str(output)],
                                 input=password + "\n", capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, "KeePassXC cannot open the output")
        return output, before, after

    def test_existing_microcases_preserve_everything_and_write_entries_before_groups(self):
        for feature in minimal.FEATURES:
            with self.subTest(feature=feature):
                data, password = minimal.make_case(feature)
                source = self.write_input(feature, data)
                reference.reference_export({"password": password}, source, self.cli)
                before = read_kdbx(data, password)
                # 构造的交错顺序在 KeePass/KeePassXC 的模型里也无法表示：两者都按“先条目、后子组”写出，
                # 各自内部顺序不变。这里精确断言该顺序，而不是笼统放行“顺序变了”。
                remaining = [self.mixed_order_label(before)] if feature == "mixed-order" else []
                _, _, after = self.roundtrip(source, password, minimal.TARGET_UUID,
                                             minimal.NEW_USERNAME, remaining=remaining)
                children = self.root_children(before)
                self.assertEqual(self.root_children(after),
                                 [c for c in children if c[0] == "Entry"] +
                                 [c for c in children if c[0] == "Group"])

    def test_icon_presence_in_group_current_old_and_new_history(self):
        for presence in ("neither", "standard", "custom", "both"):
            with self.subTest(presence=presence):
                root = minimal.plain_case("dual-icons", "4.1")
                entry = root.find("Root/Group/Entry")
                historical = copy.deepcopy(entry)
                for nested in historical.findall("History"):
                    historical.remove(nested)
                history = entry.find("History")
                if history is None:
                    history = ET.SubElement(entry, "History")
                history.append(historical)
                for node in [root.find("Root/Group"), *root.iter("Entry")]:
                    for tag, keep in (("IconID", presence in ("standard", "both")),
                                      ("CustomIconUUID", presence in ("custom", "both"))):
                        if not keep:
                            node.remove(node.find(tag))
                    if presence in ("standard", "both"):
                        node.find("IconID").text = "7"
                envelope = minimal._v4_source("4.1")
                stream_id, key, _, _ = reader._parse_inner_header(envelope.inner)
                xml = minimal._wire_xml(root, "4.1", stream_id, key)
                inner = envelope.config + minimal.v4_payload.item(0, b"")
                data = envelope.encode("aes", True, inner=inner, xml=xml)
                source = self.write_input("icons-" + presence, data)
                reference.reference_export({"password": envelope.password}, source, self.cli)
                _, before, after = self.roundtrip(
                    source, envelope.password, minimal.TARGET_UUID, minimal.NEW_USERNAME)
                original = checks.current_entries(before)[minimal.TARGET_UUID]
                current = checks.current_entries(after)[minimal.TARGET_UUID]
                for old, new in [
                    (before.root.find("Root/Group"), after.root.find("Root/Group")),
                    (original, current),
                    (original.find("History/Entry"), current.findall("History/Entry")[0]),
                    (original, current.findall("History/Entry")[1]),
                ]:
                    for tag in ("IconID", "CustomIconUUID"):
                        self.assertEqual(new.findtext(tag), old.findtext(tag), (presence, tag))

    def test_consecutive_edits_append_complete_snapshots(self):
        data, password = minimal.make_case("history")
        source = self.write_input("continuous-history", data)
        first, _, _ = self.roundtrip(source, password, minimal.TARGET_UUID, "synthetic-first")
        _, _, after = self.roundtrip(first, password, minimal.TARGET_UUID, "synthetic-second")
        snapshots = checks.current_entries(after)[minimal.TARGET_UUID].findall("History/Entry")
        self.assertEqual([checks.fields(e)["UserName"].value for e in snapshots],
                         ["synthetic-older", "synthetic-later", "synthetic-current", "synthetic-first"])

    def test_original_twelve_case_matrix_round_trips_without_differences(self):
        registered = {s["id"]: s for s in json.loads(reference.MANIFEST.read_text())["samples"]}
        for case in reference.cases():
            with self.subTest(case=case["id"]):
                source = reference.FIXTURES / case["source_file"]
                self.assertEqual(reference.digest(source.read_bytes()),
                                 registered[case["id"]]["source_sha256"])
                # 输入由 KeePassXC 写出，已是“先条目、后子组”；写出顺序一致后不应再有任何差异。
                self.roundtrip(source, case["password"], case["entry_uuid"], case["new_username"],
                               kdf=case["kdf"], cipher=case["cipher"])


    def run_helper(self, data, password, name):
        source = self.write_input(name, data)
        output = self.work / (name + "-output.kdbx")
        run = subprocess.run(
            [str(self.binary), str(source), str(output), minimal.TARGET_UUID, minimal.NEW_USERNAME,
             "aes-kdf", "aes"], input=password + "\n", capture_output=True, text=True, timeout=90)
        self.assertEqual(source.read_bytes(), data)
        return run, output

    def assert_helper_error(self, data, password, name, code):
        run, output = self.run_helper(data, password, name)
        self.assertNotEqual(run.returncode, 0, name)
        self.assertEqual(json.loads(run.stderr), {"ok": False, "error": code}, name)
        self.assertEqual(run.stdout, "")
        self.assertFalse(output.exists(), name)

    def test_unknown_elements_and_attributes_block_saving(self):
        def add(parent):
            ET.SubElement(parent, "KeexFuture").text = "synthetic-unknown"

        def entry(root):
            return root.find("Root/Group/Entry")

        def attributes(root):
            entry(root).set("KeexAttr", "synthetic")
            entry(root).find("String").set("KeexAttr", "synthetic")
            root.find("Root/Group").set("KeexAttr", "synthetic")

        cases = {
            "entry": lambda r: add(entry(r)),
            "meta": lambda r: add(r.find("Meta")),
            "root": lambda r: add(r.find("Root")),
            "file": add,
            "history": lambda r: add(entry(r).find("History/Entry")),
            "times": lambda r: add(entry(r).find("Times")),
            "attributes": attributes,
            "stray-text": lambda r: setattr(entry(r), "text", "synthetic-stray"),
            # KeePass 2.x 真实会写、但上游模型没有字段的元素。
            "keepass-force-once": lambda r: ET.SubElement(
                r.find("Meta"), "MasterKeyChangeForceOnce").__setattr__("text", "True"),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                root = minimal.plain_case("history", "4.1")
                mutate(root)
                data, password = minimal.encode_v4(root)
                self.assert_helper_error(data, password, "unknown-" + name, "database_save_failed")

    def test_content_that_can_desynchronize_the_inner_stream_refuses_to_open(self):
        def unknown_protected(root, length, nested=False):
            entry = root.find("Root/Group/Entry")
            holder = ET.Element("KeexSecret")
            value = ET.SubElement(ET.SubElement(holder, "Deep") if nested else holder, "Value",
                                  {"ProtectInMemory": "True"})
            value.text = "x" * length
            entry.insert(0, holder)

        def history_first(root):
            entry = root.find("Root/Group/Entry")
            history = entry.find("History")
            entry.remove(history)
            entry.insert(0, history)

        def root_first(root):
            meta = root.find("Meta")
            root.remove(meta)
            root.append(meta)

        def protected_tags(root):
            root.find("Root/Group/Entry/Tags").set("ProtectInMemory", "True")

        # 上游对这几种输入会静默解出错误明文，或把内层流用错位置。
        cases = {f"unknown-protected-{n}": (lambda r, n=n: unknown_protected(r, n)) for n in (1, 2, 8, 40)}
        cases["unknown-protected-nested"] = lambda r: unknown_protected(r, 8, nested=True)
        cases["history-before-string"] = history_first
        cases["root-before-meta"] = root_first
        cases["protected-attribute-on-known-element"] = protected_tags
        for name, mutate in cases.items():
            with self.subTest(case=name):
                root = minimal.plain_case("history", "4.1")
                for node in root.iter():
                    if node.get("ProtectInMemory") == "True":
                        node.text = "a"
                entry = root.find("Root/Group/Entry")
                if entry.find("Tags") is None:
                    ET.SubElement(entry, "Tags").text = "synthetic"
                mutate(root)
                data, password = minimal.encode_v4(root)
                self.assert_helper_error(data, password, "stream-" + name, "database_open_failed")

    def test_structures_the_model_cannot_parse_stay_refused(self):
        def between_strings(root):
            entry = root.find("Root/Group/Entry")
            index = next(i for i, c in enumerate(entry) if c.tag == "String")
            ET.SubElement(entry, "KeexFuture")
            entry.insert(index + 1, entry[-1])

        cases = {"group-child": lambda r: ET.SubElement(r.find("Root/Group"), "KeexFuture"),
                 "between-strings": between_strings}
        for name, mutate in cases.items():
            with self.subTest(case=name):
                root = minimal.plain_case("history", "4.1")
                mutate(root)
                data, password = minimal.encode_v4(root)
                self.assert_helper_error(data, password, "shape-" + name, "database_open_failed")

    def test_unreferenced_attachment_pool_item_is_kept(self):
        root = minimal.plain_case("control", "4.1")
        data, password = minimal.encode_v4(
            root, inner_items=minimal.v4_payload.item(3, b"\x01synthetic-unreferenced"))
        source = self.write_input("unreferenced-attachment", data)
        _, before, after = self.roundtrip(source, password, minimal.TARGET_UUID, minimal.NEW_USERNAME)
        self.assertEqual(list(before.binaries.values()), [(b"synthetic-unreferenced", True)])
        self.assertEqual(list(after.binaries.values()), [(b"synthetic-unreferenced", True)])

    def test_every_element_the_scanner_accepts_round_trips(self):
        # 扫描表声称“能带过保存”的每个元素都放一个非默认值，防止表比模型的实际能力更宽。
        # KeePassXC 导出时会按 MemoryProtection 重新标记标准字段，所以翻转这组开关的变体只核对
        # 独立 oracle 的全文比较和“能打开”，不比较 KeePassXC 导出的保护位。
        for flipped in (False, True):
            with self.subTest(flipped_memory_protection=flipped):
                self.full_schema_roundtrip(flipped)

    def full_schema_roundtrip(self, flipped):
        def ensure(parent, tag, text=None):
            node = parent.find(tag)
            if node is None:
                node = ET.SubElement(parent, tag)
            if text is not None:
                node.text = text
            return node

        when = "2026-01-02T03:04:05Z"
        uuid_a, uuid_b = minimal.source.uid("schema-a"), minimal.source.uid("schema-b")
        root = minimal.plain_case("custom-data", "4.1")
        meta = root.find("Meta")
        for tag, text in {
            "Generator": "synthetic-generator", "DatabaseName": "synthetic-name",
            "DatabaseNameChanged": when, "DatabaseDescription": "synthetic-description",
            "DatabaseDescriptionChanged": when, "DefaultUserName": "synthetic-default",
            "DefaultUserNameChanged": when, "MaintenanceHistoryDays": "33", "Color": "#112233",
            "MasterKeyChanged": when, "MasterKeyChangeRec": "11", "MasterKeyChangeForce": "22",
            "RecycleBinEnabled": "True", "RecycleBinUUID": uuid_a, "RecycleBinChanged": when,
            "EntryTemplatesGroup": uuid_a, "EntryTemplatesGroupChanged": when,
            "LastSelectedGroup": uuid_b, "LastTopVisibleGroup": uuid_b, "HistoryMaxItems": "7",
            "HistoryMaxSize": "12345", "SettingsChanged": when,
        }.items():
            ensure(meta, tag, text)
        protection = ensure(meta, "MemoryProtection")
        for tag, default in {"ProtectTitle": False, "ProtectUserName": False, "ProtectPassword": True,
                             "ProtectURL": False, "ProtectNotes": False}.items():
            ensure(protection, tag, str(default != flipped))
        group = root.find("Root/Group")
        for tag, text in {"Notes": "synthetic-group-notes", "Tags": "synthetic-group-tag",
                          "IsExpanded": "True", "DefaultAutoTypeSequence": "{USERNAME}",
                          "EnableAutoType": "False", "EnableSearching": "True",
                          "LastTopVisibleEntry": uuid_b, "PreviousParentGroup": uuid_a}.items():
            ensure(group, tag, text)
        entry = group.find("Entry")
        for tag, text in {"ForegroundColor": "#112233", "BackgroundColor": "#445566",
                          "OverrideURL": "cmd://synthetic", "Tags": "synthetic-entry-tag",
                          "QualityCheck": "False", "PreviousParentGroup": uuid_a}.items():
            ensure(entry, tag, text)
        auto_type = ensure(entry, "AutoType")
        ensure(auto_type, "Enabled", "True")
        ensure(auto_type, "DataTransferObfuscation", "1")
        ensure(auto_type, "DefaultSequence", "{PASSWORD}")
        association = ensure(auto_type, "Association")
        ensure(association, "Window", "synthetic-window")
        ensure(association, "KeystrokeSequence", "{TAB}")
        deleted = ET.SubElement(ensure(root.find("Root"), "DeletedObjects"), "DeletedObject")
        ET.SubElement(deleted, "UUID").text = uuid_b
        ET.SubElement(deleted, "DeletionTime").text = when
        data, password = minimal.encode_v4(root)
        source = self.write_input(f"full-schema-{flipped}", data)
        self.roundtrip(source, password, minimal.TARGET_UUID, minimal.NEW_USERNAME,
                       compare_export=not flipped)


if __name__ == "__main__":
    unittest.main()
