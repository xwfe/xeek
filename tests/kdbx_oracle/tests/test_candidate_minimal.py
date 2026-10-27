"""固定候选的真实最小反例；测试通过表示缺陷已复现，不表示 writer 无损。

每次离线按锁文件构建两个 helper；缺工具或依赖直接失败，不用 skip 伪装完整验证。
输入、输出只存在受限临时目录；旧样本、清单、helper 与比较器不改。
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "minimal_dart_candidate", ROOT / "tests/dart_candidate/generate.py")
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)
checks = candidate.checks
import candidate_minimal as minimal
from kdbx_oracle import read_kdbx, read_plain_xml


class CandidateMinimalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cli = shutil.which("keepassxc-cli")
        if not cls.cli:
            raise RuntimeError("minimal cases require keepassxc-cli input validation")
        candidate.rust_reference.build_helper()
        # 锁文件和项目缓存来自 pub.dev，不能继承另一 mirror 的离线解析目录。
        dart_env = {**candidate.dart_env(), "PUB_HOSTED_URL": "https://pub.dev"}
        for argv in (["dart", "pub", "get", "--offline", "--enforce-lockfile"],
                     ["dart", "compile", "exe", "bin/keex_dart_candidate.dart",
                      "-o", str(candidate.BINARY)]):
            run = subprocess.run(argv, cwd=candidate.HERE, env=dart_env,
                                 capture_output=True, text=True, timeout=300)
            if run.returncode:
                raise RuntimeError("locked offline Dart build failed: " + argv[1])
        cls.temporary = tempfile.TemporaryDirectory(
            prefix=".candidate-minimal-", dir=candidate.FIXTURES)
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.work = Path(cls.temporary.name)
        cls.inputs, cls.outputs = {}, {}

    def input_case(self, feature, level="4.1"):
        key = (feature, level)
        if key not in self.inputs:
            data, password = minimal.make_case(feature, level)
            path = self.work / (feature + "-" + level + ".kdbx")
            path.write_bytes(data)
            before = read_kdbx(data, password)
            # 用另一实现确认输入可打开；它的导出不参与元数据丢失判断。
            opened = subprocess.run(
                [self.cli, "export", "-q", "-f", "xml", str(path)],
                input=password + "\n", capture_output=True, text=True, timeout=60)
            self.assertEqual(opened.returncode, 0, "reference client rejected minimal input")
            exported = read_plain_xml(opened.stdout.encode())
            self.assertEqual(checks.current_entries(exported).keys(),
                             checks.current_entries(before).keys())
            self.assertEqual(checks.fields(checks.current_entries(exported)[minimal.TARGET_UUID]),
                             checks.fields(checks.current_entries(before)[minimal.TARGET_UUID]))
            self.assertEqual(before.version, level)
            self.assertFalse(before.binaries)
            self.inputs[key] = path, data, password, before
        return self.inputs[key]

    def roundtrip(self, writer, feature, level="4.1"):
        key = (writer, feature, level)
        if key not in self.outputs:
            path, data, password, before = self.input_case(feature, level)
            output = self.work / (writer + "-" + feature + "-" + level + ".kdbx")
            binary = candidate.BINARY if writer == "dart" else candidate.rust_reference.BINARY
            argv = [str(binary), str(path), str(output), minimal.TARGET_UUID, minimal.NEW_USERNAME]
            if writer == "rust":
                argv += ["aes-kdf", "aes"]
            run = subprocess.run(argv, input=password + "\n",
                                 capture_output=True, text=True, timeout=90)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stderr, "")
            counts = json.loads(run.stdout)
            self.assertEqual(counts["history_after"], counts["history_before"] + 1)
            after = read_kdbx(output.read_bytes(), password)
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(after.version, level)
            self.assertFalse(after.binaries)
            old_entries, new_entries = checks.current_entries(before), checks.current_entries(after)
            self.assertEqual(old_entries.keys(), new_entries.keys())
            old_groups = [n.findtext("UUID") for n in before.root.iter("Group")]
            new_groups = [n.findtext("UUID") for n in after.root.iter("Group")]
            self.assertCountEqual(old_groups, new_groups)
            old_history = sum(len(e.findall("History/Entry")) for e in old_entries.values())
            new_history = sum(len(e.findall("History/Entry")) for e in new_entries.values())
            self.assertEqual((counts["history_before"], counts["history_after"]),
                             (old_history, new_history))
            self.assertEqual(new_history, old_history + 1)
            for identifier, original in old_entries.items():
                current = new_entries[identifier]
                self.assertEqual(len(current.findall("History/Entry")),
                                 len(original.findall("History/Entry")) + (identifier == minimal.TARGET_UUID))
                if identifier != minimal.TARGET_UUID:
                    self.assertEqual(checks.fields(current), checks.fields(original))
            self.assertEqual(checks.fields(checks.current_entries(after)[minimal.TARGET_UUID])["UserName"],
                             checks.Field(minimal.NEW_USERNAME))
            self.outputs[key] = before, after
        return self.outputs[key]

    @staticmethod
    def target(decoded):
        return checks.current_entries(decoded)[minimal.TARGET_UUID]

    def test_small_inputs_are_deterministic_and_contain_the_trigger(self):
        for level in ("3.1", "4.0", "4.1"):
            path, data, password, before = self.input_case("empty-protected", level)
            self.assertEqual(minimal.make_case("empty-protected", level), (data, password))
            self.assertLess(len(data), 4096)
            current = self.target(before)
            for entry in (current, *current.findall("History/Entry")):
                fields = checks.fields(entry)
                self.assertEqual(fields["Password"], checks.Field("", True))
                self.assertEqual(fields["X-Protected-Empty"], checks.Field("", True))
                self.assertEqual(fields["X-Plain-Empty"], checks.Field("", False))
                self.assertEqual(fields["X-Protected-Tail"], checks.Field("synthetic-tail-中文", True))
            self.assertEqual(before.inner_stream, "salsa20" if level == "3.1" else "chacha20")
            if level == "3.1":
                self.assertEqual(before.header_hash, "match")

    def test_control_preserves_nonempty_protection_plain_empty_and_nondefault_icons(self):
        for writer, level in (("rust", "4.1"), ("dart", "3.1"), ("dart", "4.0"), ("dart", "4.1")):
            with self.subTest(writer=writer, level=level):
                before, after = self.roundtrip(writer, "control", level)
                expected = checks.fields(self.target(before))
                expected["UserName"] = checks.Field(minimal.NEW_USERNAME)
                self.assertEqual(checks.fields(self.target(after)), expected)
                self.assertEqual(after.root.findtext("Root/Group/IconID"), "1")
                self.assertEqual(self.target(after).findtext("IconID"), "1")

    def test_dart_loses_empty_protection_in_current_and_old_and_new_history(self):
        for level in ("3.1", "4.0", "4.1"):
            with self.subTest(level=level):
                before, after = self.roundtrip("dart", "empty-protected", level)
                original = self.target(before)
                current = self.target(after)
                previous = original.findall("History/Entry")
                snapshots = current.findall("History/Entry")
                self.assertEqual(len(snapshots), 2)
                for old, new in zip([original, *previous, original], [current, *snapshots], strict=True):
                    expected = checks.fields(old)
                    if new is current:
                        expected["UserName"] = checks.Field(minimal.NEW_USERNAME)
                    expected["Password"] = checks.Field("", False)
                    expected["X-Protected-Empty"] = checks.Field("", False)
                    self.assertEqual(checks.fields(new), expected)

    def test_rust_keeps_empty_protection_in_current_and_history(self):
        before, after = self.roundtrip("rust", "empty-protected")
        original, current = self.target(before), self.target(after)
        for old, new in zip([original, original, *original.findall("History/Entry")],
                            [current, *current.findall("History/Entry")], strict=True):
            expected = checks.fields(old)
            if new is current:
                expected["UserName"] = checks.Field(minimal.NEW_USERNAME)
            self.assertEqual(checks.fields(new), expected)

    def test_both_writers_reorder_mixed_group_children_but_keep_each_kind_order(self):
        for writer in ("rust", "dart"):
            with self.subTest(writer=writer):
                before, after = self.roundtrip(writer, "mixed-order")
                def children(decoded):
                    return [(n.tag, n.findtext("UUID")) for n in decoded.root.find("Root/Group")
                            if n.tag in ("Group", "Entry")]
                old, new = children(before), children(after)
                self.assertEqual([tag for tag, _ in old], ["Entry", "Group", "Entry", "Group"])
                self.assertEqual(new, [old[1], old[3], old[0], old[2]])

    def test_default_icons_without_custom_icon_are_kept_by_both_writers(self):
        for writer in ("rust", "dart"):
            before, after = self.roundtrip(writer, "default-icons")
            self.assertEqual(before.root.findtext("Root/Group/IconID"), "48")
            self.assertEqual(self.target(before).findtext("IconID"), "0")
            self.assertEqual((after.root.findtext("Root/Group/IconID"),
                              self.target(after).findtext("IconID")), ("48", "0"))

    def test_rust_loses_standard_icon_only_when_custom_icon_also_exists(self):
        for writer in ("rust", "dart"):
            before, after = self.roundtrip(writer, "dual-icons")
            for old, new, standard in (
                (before.root.find("Root/Group"), after.root.find("Root/Group"), "48"),
                (self.target(before), self.target(after), "0"),
            ):
                self.assertEqual(old.findtext("IconID"), standard)
                self.assertIsNotNone(old.find("CustomIconUUID"))
                self.assertEqual(new.findtext("CustomIconUUID"), old.findtext("CustomIconUUID"))
                self.assertEqual(new.findtext("IconID"), None if writer == "rust" else standard)

    def test_history_placement_preserves_old_snapshots_but_differs_between_writers(self):
        for writer in ("rust", "dart"):
            before, after = self.roundtrip(writer, "history")
            original, current = self.target(before), self.target(after)
            old = original.findall("History/Entry")
            new = current.findall("History/Entry")
            self.assertEqual(len(old), 2)
            self.assertEqual(len(new), 3)
            expected = [original, *old] if writer == "rust" else [*old, original]
            for wanted, actual in zip(expected, new, strict=True):
                self.assertEqual(checks.labels(checks.snapshot(before, wanted),
                                               checks.snapshot(after, actual), ignore=()), [])

    def test_customdata_timestamps_loss_is_not_limited_to_meta(self):
        for writer in ("rust", "dart"):
            before, after = self.roundtrip(writer, "custom-data")
            old_entry, new_entry = self.target(before), self.target(after)
            pairs = [
                ("meta", before.root.find("Meta"), after.root.find("Meta")),
                ("group", before.root.find("Root/Group"), after.root.find("Root/Group")),
                ("entry", old_entry, new_entry),
                ("history", old_entry.find("History/Entry"),
                 new_entry.findall("History/Entry")[1 if writer == "rust" else 0]),
                ("new-history", old_entry,
                 new_entry.findall("History/Entry")[0 if writer == "rust" else 1]),
            ]
            for scope, old, new in pairs:
                with self.subTest(writer=writer, scope=scope):
                    old_item, new_item = old.find("CustomData/Item"), new.find("CustomData/Item")
                    self.assertIsNotNone(old_item.find("LastModificationTime"))
                    self.assertIsNotNone(new_item)
                    self.assertEqual(new_item.findtext("Key"), old_item.findtext("Key"))
                    self.assertEqual(new_item.findtext("Value"), old_item.findtext("Value"))
                    expected = None if writer == "dart" and scope != "group" else old_item.findtext("LastModificationTime")
                    self.assertEqual(new_item.findtext("LastModificationTime"), expected)

    def test_dart_loses_custom_icon_name_and_time_but_keeps_identity_and_pixels(self):
        for writer in ("rust", "dart"):
            before, after = self.roundtrip(writer, "custom-icon")
            old, new = before.root.find("Meta/CustomIcons/Icon"), after.root.find("Meta/CustomIcons/Icon")
            for tag in ("UUID", "Data", "Name", "LastModificationTime"):
                self.assertIsNotNone(old.find(tag))
                expected = None if writer == "dart" and tag in ("Name", "LastModificationTime") else old.findtext(tag)
                self.assertEqual(new.findtext(tag), expected, (writer, tag))
            self.assertEqual(self.target(after).findtext("CustomIconUUID"), old.findtext("UUID"))
            # 非默认标准图标同样丢失，证明触发因素是双字段模型而非默认值规范化。
            self.assertEqual(self.target(before).findtext("IconID"), "1")
            self.assertEqual(self.target(after).findtext("IconID"), None if writer == "rust" else "1")

    def test_dart_known_algorithm_gaps_fail_without_any_output(self):
        for case in candidate.unsupported_cases():
            with self.subTest(case=case["id"]):
                source = candidate.FIXTURES / case["source_file"]
                data = source.read_bytes()
                decoded = read_kdbx(data, case["password"], keyfile=candidate.keyfile_bytes(case))
                self.assertIn(decoded.kdf["name"] if "ARGON2ID" in case["id"] else decoded.cipher,
                              ("argon2id", "chacha20"))
                output = self.work / (case["id"] + ".kdbx")
                run, error, _ = candidate.run_helper(case, output)
                self.assertNotEqual(run.returncode, 0)
                self.assertEqual(error, {"ok": False, "error": "database_open_failed"})
                self.assertEqual(run.stdout, "")
                self.assertFalse(output.exists())
                self.assertEqual(source.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
