"""K003：历史裁剪与 KeePassXC 对照。同一份合成库各编辑一次，用独立 oracle 比两边结果。"""
from __future__ import annotations

import copy
import importlib.util
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


reference = load_module("trim_reference", "tests/reference_writer/generate.py")
build = load_module("trim_build", "tests/rust_preservation/build.py")
checks = reference.checks
import candidate_minimal as minimal
from kdbx_oracle import read_kdbx
from kdbx_oracle.semantic import canonicalize

source, payload = minimal.source, minimal.v4_payload
TITLE = "synthetic-trim"
OTHER = "synthetic-other"
EDITED = "v-edited"
NO_LIMIT = -1


def version(pool, number, *, name=TITLE, attachments=None, tags=None, custom=None, autotype=None):
    # 字段、标签、自定义数据、关联窗口、附件都计入大小；带中文，字节数和字符数不同。
    fields = [("Title", name, False), ("UserName", f"v{number}", False),
              ("Password", f"密码-{number}", True), ("URL", "", False), ("Notes", "", False)]
    return source.entry("4.1", pool, name, fields, modified=source.day(number + 1), tags=tags,
                        attachments=attachments, custom=custom, autotype=autotype)


def size_of(entry, binaries):
    """按 KeePassXC 的 Entry::size 独立计算；Rust 实现算错时边界用例会和它对不上。"""
    def utf8(text):
        return len((text or "").encode())

    total = sum(utf8(s.findtext("Key")) + utf8(s.findtext("Value")) for s in entry.findall("String"))
    for binary in entry.findall("Binary"):
        content, _ = binaries[binary.find("Value").get("Ref")]
        total += utf8(binary.findtext("Key")) + len(content)
    total += sum(utf8(a.findtext("Window")) + utf8(a.findtext("KeystrokeSequence"))
                 for a in entry.findall("AutoType/Association"))
    total += sum(utf8(i.findtext("Key")) + utf8(i.findtext("Value"))
                 for i in entry.findall("CustomData/Item"))
    return total + sum(utf8(tag) for tag in (entry.findtext("Tags") or "").split(";"))


def library(*, items, size, build_history=None, reverse=False):
    """五份历史 v0..v4 + 当前 v5。build_history 可给每个版本加内容，并返回其它条目。"""
    pool = source.Pool()
    extras = build_history(pool) if build_history else {}
    options = extras.get("versions", {})
    history = [version(pool, n, **options.get(n, {})) for n in range(5)]
    if reverse:
        history.reverse()
    current = version(pool, 5, **options.get(5, {}))
    current.append(source.E("History", children=history))
    children = [current, *extras.get("others", [])]
    group = source.group("4.1", "trim-root", "synthetic-root", children, icon="1")
    meta = source.meta("4.1", "K003-TRIM", source.Pool(), recycle_bin=None, icons=extras.get("icon", False))
    for tag, value in (("HistoryMaxItems", items), ("HistoryMaxSize", size)):
        node = meta.find(tag)
        if value is None:
            meta.remove(node)
        else:
            node.text = str(value)
    root = ET.fromstring(source.document(meta, group))
    # 4.x 的附件放在内层头；首字节是保护标记。
    inner = b"".join(payload.item(3, b"\x00" + data) for data in pool.items)
    return root, inner


class HistoryTrimTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cli = shutil.which("keepassxc-cli")
        if not cls.cli:
            raise RuntimeError("history trim comparison requires keepassxc-cli")
        build.build_helper()
        cls.binary = build.TARGET / "release" / build.HISTORY_EDIT
        temporary = tempfile.TemporaryDirectory(prefix="trim-", dir=build.HERE / "target")
        cls.addClassCleanup(temporary.cleanup)
        cls.work = Path(temporary.name)
        cls.sequence = 0

    def edit_both(self, root, inner, *, title=TITLE):
        self.__class__.sequence += 1
        name = self.work / f"case-{self.sequence}"
        data, password = minimal.encode_v4(root, inner_items=inner)
        before = read_kdbx(data, password)
        source_path, ours, theirs = (name.with_suffix(s) for s in (".kdbx", ".ours.kdbx", ".theirs.kdbx"))
        source_path.write_bytes(data)
        target = next(uuid for uuid, e in checks.current_entries(before).items()
                      if checks.fields(e)["Title"].value == title)
        run = subprocess.run([str(self.binary), str(source_path), str(ours), target, EDITED],
                             input=password + "\n", capture_output=True, text=True, timeout=90)
        self.assertEqual(run.returncode, 0, run.stderr)
        shutil.copy(source_path, theirs)
        run = subprocess.run([self.cli, "edit", "-q", "-u", EDITED, str(theirs), "/" + title],
                             input=password + "\n", capture_output=True, text=True, timeout=90)
        self.assertEqual(run.returncode, 0, run.stderr)
        return before, read_kdbx(ours.read_bytes(), password), read_kdbx(theirs.read_bytes(), password)

    @staticmethod
    def kept(decoded, title=TITLE):
        for entry in checks.current_entries(decoded).values():
            if checks.fields(entry)["Title"].value == title:
                return [checks.fields(v)["UserName"].value for v in entry.findall("History/Entry")]
        raise AssertionError(title)

    def assert_only_trimmed(self, before, after, wanted):
        """全文比较：除目标条目的 UserName、修改时间和裁剪后的历史，什么都不能变。"""
        expected = replace(before, root=copy.deepcopy(before.root))
        path = None
        for identifier, entry in checks.current_entries(expected).items():
            if checks.fields(entry)["Title"].value == TITLE:
                path = checks.paths(before)[identifier]
                snapshot = copy.deepcopy(entry)
                for nested in snapshot.findall("History"):
                    snapshot.remove(nested)
                history = entry.find("History")
                if history is None:
                    history = ET.SubElement(entry, "History")
                history.append(snapshot)
                for old in list(history):
                    if checks.fields(old)["UserName"].value not in wanted:
                        history.remove(old)
                if not len(history):
                    entry.remove(history)
        changes = checks.diff(canonicalize(expected), canonicalize(after), ignore=())
        allowed = {path + "/String=UserName/Value", path + "/Times/LastModificationTime"}
        self.assertEqual([c.label for c in changes if not (c.kind == "changed" and c.path in allowed)], [])

    def test_item_limit_matches_keepassxc(self):
        for items, wanted in {
            NO_LIMIT: ["v0", "v1", "v2", "v3", "v4", "v5"],
            0: [],
            1: ["v5"],
            3: ["v3", "v4", "v5"],
            5: ["v1", "v2", "v3", "v4", "v5"],
            6: ["v0", "v1", "v2", "v3", "v4", "v5"],
        }.items():
            with self.subTest(items=items):
                root, inner = library(items=items, size=NO_LIMIT)
                before, ours, theirs = self.edit_both(root, inner)
                self.assertEqual(self.kept(ours), wanted)
                self.assertEqual(self.kept(theirs), wanted)
                self.assert_only_trimmed(before, ours, wanted)

    def test_invalid_or_missing_limits_keep_everything(self):
        # 文件没写上限时，KeePassXC/KeePass 用默认值（10 份、6 MiB），这里不替用户决定删数据。
        everything = ["v0", "v1", "v2", "v3", "v4", "v5"]
        for items, size in ((None, None), (-5, -5), (None, NO_LIMIT), (NO_LIMIT, None)):
            with self.subTest(items=items, size=size):
                root, inner = library(items=items, size=size)
                before, ours, _ = self.edit_both(root, inner)
                self.assertEqual(self.kept(ours), everything)
                self.assert_only_trimmed(before, ours, everything)

    def test_unparsable_limit_refuses_to_open(self):
        # KeePassXC 同样报错；不能把看不懂的上限当成“没有上限”存回去。
        root, inner = library(items="many", size=NO_LIMIT)
        data, password = minimal.encode_v4(root, inner_items=inner)
        source_path = self.work / "unparsable.kdbx"
        output = self.work / "unparsable-output.kdbx"
        source_path.write_bytes(data)
        run = subprocess.run([str(self.binary), str(source_path), str(output),
                              source.uid("uuid/" + TITLE), EDITED],
                             input=password + "\n", capture_output=True, text=True, timeout=90)
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse(output.exists())
        run = subprocess.run([self.cli, "export", "-q", "-f", "xml", str(source_path)],
                             input=password + "\n", capture_output=True, text=True, timeout=60)
        self.assertNotEqual(run.returncode, 0)

    @staticmethod
    def rich_versions(pool):
        automatic = source.E("AutoType", children=[
            source.E("Enabled", "True"), source.E("DataTransferObfuscation", "0"),
            source.E("DefaultSequence", "{PASSWORD}"),
            source.E("Association", children=[source.E("Window", "合成窗口"),
                                              source.E("KeystrokeSequence", "{TAB}")]),
        ])
        return {"versions": {
            1: {"tags": "标签一;tag2"},
            2: {"tags": "t"},
            3: {"attachments": {"文件.bin": b"synthetic-attachment-" * 5}},
            4: {"autotype": automatic},
            5: {"attachments": {"文件.bin": b"synthetic-attachment-" * 5}, "tags": "x"},
        }}

    @classmethod
    def custom_data_versions(cls, pool):
        extras = cls.rich_versions(pool)
        extras["versions"][2] = {"custom": {"合成.键": "合成值"}}
        return extras

    def size_boundaries(self, versions):
        """每个“刚好放得下”和“差一个字节”的上限，以及对应应保留的版本。"""
        root, inner = library(items=NO_LIMIT, size=NO_LIMIT, build_history=versions)
        decoded = read_kdbx(*minimal.encode_v4(root, inner_items=inner))
        current = next(iter(checks.current_entries(decoded).values()))
        by_name = {checks.fields(v)["UserName"].value: v for v in current.findall("History/Entry")}
        by_name["v5"] = current
        newest_first = ["v5", "v4", "v3", "v2", "v1", "v0"]
        sizes = [size_of(by_name[n], decoded.binaries) for n in newest_first]
        self.assertEqual(len(set(sizes)), len(sizes), "sizes must differ so a wrong measure shows")
        limits = {0: 0}
        for count in range(1, len(sizes) + 1):
            total = sum(sizes[:count])
            limits[total] = count
            limits[total - 1] = count - 1
        return {limit: list(reversed(newest_first[:count])) for limit, count in limits.items()}

    def test_size_limit_boundaries_match_keepassxc(self):
        for limit, wanted in sorted(self.size_boundaries(self.rich_versions).items()):
            with self.subTest(limit=limit, wanted=wanted):
                root, inner = library(items=NO_LIMIT, size=limit, build_history=self.rich_versions)
                before, ours, theirs = self.edit_both(root, inner)
                self.assertEqual(self.kept(ours), wanted)
                self.assertEqual(self.kept(theirs), wanted)
                self.assert_only_trimmed(before, ours, wanted)

    def test_custom_data_counts_what_the_file_says(self):
        # KeePassXC 读入自定义数据时会在内存里多出 _LAST_MODIFIED 项并计入大小（它的源码注释也说这让长度不可预测），
        # 所以这里只和独立计算比，不和它比到字节。
        for limit, wanted in sorted(self.size_boundaries(self.custom_data_versions).items()):
            with self.subTest(limit=limit, wanted=wanted):
                root, inner = library(items=NO_LIMIT, size=limit, build_history=self.custom_data_versions)
                before, ours, _ = self.edit_both(root, inner)
                self.assertEqual(self.kept(ours), wanted)
                self.assert_only_trimmed(before, ours, wanted)

    def test_both_limits_apply_together(self):
        for items, size_versions, wanted in ((4, 2, ["v4", "v5"]), (2, 4, ["v4", "v5"])):
            with self.subTest(items=items):
                each = len("TitleUserNamePasswordURLNotes") + len(TITLE) + 2 + len("密码-0".encode())
                root, inner = library(items=items, size=each * size_versions)
                _, ours, theirs = self.edit_both(root, inner)
                self.assertEqual(self.kept(ours), wanted)
                self.assertEqual(self.kept(theirs), wanted)

    def test_content_only_dropped_versions_used_leaves_the_file(self):
        def versions(pool):
            return {
                "versions": {
                    0: {"attachments": {"dropped.bin": b"synthetic-dropped",
                                        "kept-later.bin": b"synthetic-kept-later",
                                        "other.bin": b"synthetic-other-entry"}},
                    4: {"attachments": {"kept-later.bin": b"synthetic-kept-later"}},
                    5: {"attachments": {"current.bin": b"synthetic-current"}},
                },
                "others": [version(pool, 0, name=OTHER, attachments={"other.bin": b"synthetic-other-entry"})],
            }

        root, inner = library(items=2, size=NO_LIMIT, build_history=versions)
        before, ours, theirs = self.edit_both(root, inner)
        wanted = ["v4", "v5"]
        self.assertEqual(self.kept(ours), wanted)
        self.assertEqual(self.kept(theirs), wanted)
        remaining = {b"synthetic-kept-later", b"synthetic-other-entry", b"synthetic-current"}
        self.assertEqual(Counter(c for c, _ in before.binaries.values()),
                         Counter(remaining | {b"synthetic-dropped"}))
        self.assertEqual(Counter(c for c, _ in ours.binaries.values()), Counter(remaining))
        self.assertEqual(Counter(c for c, _ in theirs.binaries.values()), Counter(remaining))
        self.assert_only_trimmed(before, ours, wanted)

    def test_unreferenced_pool_item_is_not_this_trims_to_delete(self):
        # 文件里本来就没人引用的附件不是这次裁剪造成的；KeePassXC 保存时会丢掉，这里按“不丢数据”保留。
        root, inner = library(items=1, size=NO_LIMIT, build_history=lambda pool: {"versions": {
            0: {"attachments": {"dropped.bin": b"synthetic-dropped"}}}})
        inner += payload.item(3, b"\x00synthetic-unreferenced")
        before, ours, _ = self.edit_both(root, inner)
        self.assertEqual(len(before.binaries), 2)
        self.assertEqual([c for c, _ in ours.binaries.values()], [b"synthetic-unreferenced"])

    def test_custom_icon_only_dropped_versions_used_stays_available(self):
        icon = source.uid("icon")
        root, inner = library(items=1, size=NO_LIMIT, build_history=lambda pool: {"icon": True})
        ET.SubElement(root.find("Root/Group/Entry/History/Entry"), "CustomIconUUID").text = icon
        _, ours, theirs = self.edit_both(root, inner)
        self.assertEqual(self.kept(ours), ["v5"])
        self.assertEqual(self.kept(theirs), ["v5"])
        for result in (ours, theirs):
            self.assertEqual([n.findtext("UUID") for n in result.root.findall("Meta/CustomIcons/Icon")], [icon])

    def test_only_the_edited_entry_is_trimmed(self):
        # 其它条目超限也不动：只有用户编辑它（或显式要求）时才删它的历史。
        def versions(pool):
            return {"others": [version(pool, 0, name=OTHER)]}

        root, inner = library(items=2, size=NO_LIMIT, build_history=versions)
        _, ours, theirs = self.edit_both(root, inner, title=OTHER)
        for result in (ours, theirs):
            self.assertEqual(self.kept(result), ["v0", "v1", "v2", "v3", "v4"])
            self.assertEqual(self.kept(result, OTHER), ["v0"])

    def test_oldest_means_oldest_time_not_first_in_list(self):
        # 未打补丁的 keepass-rs 写出的文件是最新在前。按列表位置裁剪会删掉最新的历史；这里按时间。
        root, inner = library(items=3, size=NO_LIMIT, reverse=True)
        _, ours, _ = self.edit_both(root, inner)
        self.assertEqual(self.kept(ours), ["v4", "v3", "v5"])


if __name__ == "__main__":
    unittest.main()
