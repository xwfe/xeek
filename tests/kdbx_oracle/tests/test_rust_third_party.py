"""K003：补丁库 → KeePassXC 再编辑 → 补丁库读回再改 → KeePassXC 再开。

KeePassXC 自己的变动单列断言，不算候选的问题；补丁库这一步除目标条目外不许有任何差异。
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reference = load_module("third_party_reference", "tests/reference_writer/generate.py")
build = load_module("third_party_build", "tests/rust_preservation/build.py")
checks = reference.checks
import candidate_minimal as minimal
from kdbx_oracle import read_kdbx
from kdbx_oracle.semantic import canonicalize

FIXTURES = build.FIXTURES
# KeePassXC 编辑一个条目时，自己还会动这些地方（2.8.0 实测）。其它任何变动都要先查清再放行。
KEEPASSXC_OWN = re.compile(
    r"(/CustomData/Item=_LAST_MODIFIED/Value"
    r"|/Meta/CustomData/Item=KPXC_RANDOM_SLUG/(Value|LastModificationTime)"
    r"|/Meta/CustomData(/Item=(_LAST_MODIFIED|KPXC_RANDOM_SLUG))?"
    r"|/Meta/SettingsChanged)$"
)
# 只在这些合成输入上出现，真实客户端写的文件不会有：
# 带自定义图标的节点，KeePassXC 把 IconID 归零；条目自定义数据，它去掉单项时间并补 _LAST_MODIFIED。
KEEPASSXC_OWN_BY_SAMPLE = {
    "dual-icons": re.compile(r"/IconID$"),
    "custom-icon": re.compile(r"/IconID$"),
    "custom-data": re.compile(r"/CustomData/Item=\S+/LastModificationTime$|/CustomData/Item=_LAST_MODIFIED$"),
}


def samples():
    def stage(manifest, sample_id, stage_name):
        sample = next(s for s in json.loads((FIXTURES / manifest).read_text())["samples"]
                      if s["id"] == sample_id)
        record = next(s for s in sample["stages"] if s["name"] == stage_name)
        return (FIXTURES / record["file"]).read_bytes(), sample["credentials"]["password"]

    yield "vault", *stage("vault_manifest.json", "V41-VAULT", "edit2")
    yield "passkey", *stage("matrix_manifest.json", "M41-PASSKEY", "edit2")
    golden = next(s for s in json.loads((FIXTURES / "manifest.json").read_text())["samples"]
                  if s["id"] == "G41-RICH")
    yield "golden", (FIXTURES / golden["file"]).read_bytes(), golden["credentials"]["password"]
    for feature in minimal.FEATURES:
        yield feature, *minimal.make_case(feature)


def paths_by_id(decoded):
    """每个当前条目的 KeePassXC 路径（根组不写进路径）。"""
    found = {}

    def walk(group, prefix):
        for entry in group.findall("Entry"):
            found[checks.uuid_hex(entry.findtext("UUID"))] = prefix + "/" + checks.fields(entry)["Title"].value
        for child in group.findall("Group"):
            walk(child, prefix + "/" + child.findtext("Name"))

    walk(decoded.root.find("Root/Group"), "")
    return found


class ThirdPartyRoundTripTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cli = shutil.which("keepassxc-cli")
        if not cls.cli:
            raise RuntimeError("third-party round trip requires keepassxc-cli")
        build.build_helper()
        cls.binary = build.TARGET / "release" / build.HISTORY_EDIT
        temporary = tempfile.TemporaryDirectory(prefix="third-party-", dir=build.HERE / "target")
        cls.addClassCleanup(temporary.cleanup)
        cls.work = Path(temporary.name)
        cls.sequence = 0

    def scratch(self):
        self.__class__.sequence += 1
        return self.work / f"step-{self.sequence}.kdbx"

    def ours(self, source, target, username, password, normalized=()):
        """补丁库改一次用户名；除这个条目的这次编辑和 normalized 登记的差异外，不许有任何差异。"""
        output = self.scratch()
        before = read_kdbx(source.read_bytes(), password)
        run = subprocess.run([str(self.binary), str(source), str(output), target, username],
                             input=password + "\n", capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        after = read_kdbx(output.read_bytes(), password)

        path = checks.paths(before)[target]
        expected = replace(before, root=copy.deepcopy(before.root))
        entry = checks.current_entries(expected)[target]
        snapshot = copy.deepcopy(entry)
        for nested in snapshot.findall("History"):
            snapshot.remove(nested)
        history = entry.find("History")
        if history is None:
            history = ET.SubElement(entry, "History")
        history.append(snapshot)
        field = path + "/String=UserName"
        allowed = {field, field + "/Value", path + "/Times/LastModificationTime"}
        changes = checks.diff(canonicalize(expected), canonicalize(after), ignore=())
        self.assertEqual([c.label for c in changes if c.path not in allowed], list(normalized))
        self.assertEqual(checks.fields(checks.current_entries(after)[target])["UserName"].value, username)
        return output

    def keepassxc_edit(self, source, password, entry_path, username):
        output = self.scratch()
        shutil.copy(source, output)
        self.apply(output, password, ("edit", "-u", username, entry_path))
        return output

    def apply(self, path, password, arguments):
        # keepassxc-cli 的参数顺序：命令 [选项] 数据库 位置参数...
        command, *rest = arguments
        options = []
        while rest and rest[0].startswith("-"):
            options += rest[:2]
            rest = rest[2:]
        run = subprocess.run([self.cli, command, "-q", *options, str(path), *rest],
                             input=password + "\n", capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, f"{arguments}: {run.stderr}")

    def assert_keepassxc_only_touched_its_own(self, before, after, target, sample):
        extra = KEEPASSXC_OWN_BY_SAMPLE.get(sample)
        path = checks.paths(before)[target]
        target_own = {path + "/String=UserName", path + "/String=UserName/Value",
                      path + "/Times/LastModificationTime", path + "/Times/LastAccessTime"}
        history = re.compile(re.escape(path) + r"/History(/Entry#\d+)?$")
        other = [c.label for c in checks.diff(canonicalize(before), canonicalize(after), ignore=())
                 if not (c.path in target_own or history.search(c.path) or KEEPASSXC_OWN.search(c.path)
                         or (extra and extra.search(c.path)))]
        self.assertEqual(other, [])

    def test_edits_survive_a_full_circle_through_keepassxc(self):
        for name, data, password in samples():
            with self.subTest(sample=name):
                source = self.scratch()
                source.write_bytes(data)
                decoded = read_kdbx(data, password)
                entries = paths_by_id(decoded)
                target = (minimal.TARGET_UUID if name in minimal.FEATURES else
                          next(i for i, p in entries.items() if not p.endswith("/")))
                entry_path = entries[target]

                # 组和条目交错的输入，第一次保存按参考客户端的写法规范成先条目后子组（§6）。
                normalized = (["order KeePassFile/Root/Group=" + checks.uuid_hex(
                    decoded.root.findtext("Root/Group/UUID"))] if name == "mixed-order" else [])
                first = self.ours(source, target, "round-1", password, normalized)
                second = self.keepassxc_edit(first, password, entry_path, "round-2")
                self.assert_keepassxc_only_touched_its_own(
                    read_kdbx(first.read_bytes(), password), read_kdbx(second.read_bytes(), password),
                    target, name)
                third = self.ours(second, target, "round-3", password)
                reference.reference_export({"password": password}, third, self.cli)
                fourth = self.keepassxc_edit(third, password, entry_path, "round-4")
                fifth = self.ours(fourth, target, "round-5", password)

                final = checks.current_entries(read_kdbx(fifth.read_bytes(), password))[target]
                chain = [checks.fields(v)["UserName"].value for v in final.findall("History/Entry")]
                self.assertEqual(chain[-4:], ["round-1", "round-2", "round-3", "round-4"])
                self.assertEqual(checks.fields(final)["UserName"].value, "round-5")

    def test_edits_within_one_second_survive_a_keepassxc_merge(self):
        # 同步时 KeePassXC 按修改时间合并历史；时间戳相同的两份会被当成一份，中间版本就丢了。
        data, password = minimal.make_case("control")
        source = self.scratch()
        source.write_bytes(data)
        edited = self.scratch()
        run = subprocess.run([str(self.binary), str(source), str(edited), minimal.TARGET_UUID, "edit-1", "edit-2", "edit-3"],
                             input=password + "\n", capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        merged = self.scratch()
        shutil.copy(source, merged)
        run = subprocess.run([self.cli, "merge", "-q", "-s", str(merged), str(edited)], input=password + "\n",
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        entry = checks.current_entries(read_kdbx(merged.read_bytes(), password))[minimal.TARGET_UUID.replace("-", "")]
        names = [checks.fields(v)["UserName"].value for v in entry.findall("History/Entry")]
        self.assertEqual(names[-3:], ["synthetic-current", "edit-1", "edit-2"])
        self.assertEqual(checks.fields(entry)["UserName"].value, "edit-3")

    def test_structural_changes_by_keepassxc_survive_our_save(self):
        # KeePassXC 动结构后，补丁库读回再存：`ours` 的全文比较保证这些改动一处不丢。
        data, password = next((d, p) for name, d, p in samples() if name == "vault")
        source = self.scratch()
        source.write_bytes(data)
        decoded = read_kdbx(data, password)
        entries = paths_by_id(decoded)
        titled = {p.rsplit("/", 1)[1]: (i, p) for i, p in entries.items() if not p.endswith("/")}
        target, target_path = titled["登录 Login"]
        moved_id, moved_path = titled["字段引用 Reference"]
        removed_id, removed_path = next(v for k, v in titled.items()
                                        if v[0] not in (target, moved_id))
        attachment = self.work / "synthetic-import.bin"
        attachment.write_bytes(b"synthetic-imported-attachment")

        first = self.ours(source, target, "round-1", password)
        changed = self.scratch()
        shutil.copy(first, changed)
        moved_title = moved_path.rsplit("/", 1)[1]
        for arguments in (
            ("mkdir", "/合成新组"),
            ("add", "-u", "synthetic-new", "/合成新组/合成新条目"),
            ("mv", moved_path, "/合成新组"),
            ("rm", removed_path),
            ("edit", "--url", "https://synthetic.example/changed", "--notes", "synthetic-notes", target_path),
            ("attachment-rm", target_path, "notes.txt"),
            ("attachment-import", target_path, "imported.bin", str(attachment)),
        ):
            with self.subTest(step=arguments[0]):
                self.apply(changed, password, arguments)
        # 第一次 rm 进回收站，再删一次才真正删除；回收站路径从文件里读，组名随语言变。
        recycled = paths_by_id(read_kdbx(changed.read_bytes(), password))[removed_id]
        self.apply(changed, password, ("rm", recycled))

        result = self.ours(changed, target, "round-3", password)
        after = read_kdbx(result.read_bytes(), password)
        reference.reference_export({"password": password}, result, self.cli)

        current = checks.current_entries(after)
        new_paths = paths_by_id(after)
        self.assertEqual(new_paths[moved_id], "/合成新组/" + moved_title)
        self.assertNotIn(removed_id, current)
        self.assertIn(removed_id, {checks.uuid_hex(n.findtext("UUID"))
                                   for n in after.root.findall("Root/DeletedObjects/DeletedObject")})
        self.assertIn("/合成新组/合成新条目", new_paths.values())
        entry = current[target]
        self.assertEqual(checks.fields(entry)["Notes"].value, "synthetic-notes")
        names = {b.findtext("Key") for b in entry.findall("Binary")}
        self.assertIn("imported.bin", names)
        self.assertNotIn("notes.txt", names)
        self.assertIn(b"synthetic-imported-attachment", {c for c, _ in after.binaries.values()})
        # 再让 KeePassXC 改一次，确认补丁库写出的结构它还能接着用。
        self.keepassxc_edit(result, password, target_path, "round-4")

    def test_elements_the_file_left_out_stay_equivalent(self):
        """只留必需元素的文件：保存不能改语义，只允许多出下面这份已知等价的清单。"""
        source_module = minimal.source
        versions = [("Title", "bare", False), ("UserName", "old", False), ("Password", "synthetic-old", True)]
        fields = [("Title", "bare", False), ("UserName", "current", False), ("Password", "synthetic-new", True)]
        entry = source_module.entry("4.1", source_module.Pool(), "bare", fields, history=[
            source_module.entry("4.1", source_module.Pool(), "bare", versions)])
        child = source_module.group("4.1", "bare-child", "synthetic-child", [], icon="1")
        group = source_module.group("4.1", "bare-root", "synthetic-root", [entry, child], icon="1")
        root = ET.fromstring(source_module.document(ET.Element("Meta"), group))
        for node in root.iter("Group"):
            for element in list(node):
                if element.tag not in ("UUID", "Name", "Entry", "Group"):
                    node.remove(element)
        for node in root.iter("Entry"):
            for element in list(node):
                if element.tag not in ("UUID", "String", "History"):
                    node.remove(element)
        data, password = minimal.encode_v4(root)
        source = self.scratch()
        source.write_bytes(data)
        before = read_kdbx(data, password)
        target = next(iter(checks.current_entries(before)))
        output = self.scratch()
        run = subprocess.run([str(self.binary), str(source), str(output), target, "edited"],
                             input=password + "\n", capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        after = read_kdbx(output.read_bytes(), password)

        for node in after.root.iter("Entry"):
            self.assertIsNone(node.find("QualityCheck"), "QualityCheck was not in the file")
        for node in after.root.iter("Group"):
            # KeePass 和 KeePassXC 没写时都按展开处理；写成 False 等于把分组折叠。
            self.assertEqual(node.findtext("IsExpanded"), "True")
        path = checks.paths(before)[target]
        equivalent = re.compile(
            r"(/Meta/CustomIcons|/Meta/CustomData|/Root/DeletedObjects|/Times"
            r"|/Group=\w+/(IsExpanded|EnableAutoType|EnableSearching)"
            r"|/Root/Group/(IsExpanded|EnableAutoType|EnableSearching))$")
        target_paths = {path + "/String=UserName/Value", path + "/Times/LastModificationTime"}
        history = re.compile(re.escape(path) + r"/History/Entry#\d+$")
        other = [c.label for c in checks.diff(canonicalize(before), canonicalize(after), ignore=())
                 if not (c.path in target_paths or history.search(c.path) or equivalent.search(c.path))]
        self.assertEqual(other, [])
        # KeePassXC 眼里两份文件除这次编辑外一样：它按自己的默认值读没写的元素，再导出比较。
        def exported(path):
            run = subprocess.run([self.cli, "export", "-q", "-f", "xml", str(path)],
                                 input=password + "\n", capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stderr)
            return reference.read_plain_xml(run.stdout.encode())

        other = [c.label for c in checks.diff(canonicalize(exported(source)), canonicalize(exported(output)), ignore=())
                 if not (c.path in target_paths or history.search(c.path) or KEEPASSXC_OWN.search(c.path))]
        self.assertEqual(other, [])


if __name__ == "__main__":
    unittest.main()
