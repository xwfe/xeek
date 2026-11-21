"""官方 KeePass L0 留存样本与 oracle 判定边界。"""
import copy
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "rust_preservation"))
import official_roundtrip as official


class OfficialFixtureTests(official.OfficialTests):
    def test_generator_refuses_existing_registration_without_invoking_tools(self):
        with self.assertRaisesRegex(ValueError, "refusing to refresh"):
            official.generate(Path("/unused-tools"), Path("/unused-mono"))

    def test_unknown_attribute_on_known_null_path_rejected(self):
        changed = replace(self.decoded[1], root=copy.deepcopy(self.decoded[1].root))
        changed.root.find("Root/Group/EnableAutoType").set("FutureSetting", "synthetic")
        with self.assertRaises(ValueError):
            official.check_edit(self.decoded[0], changed, "synthetic-rust-edit", inspect_null_spelling=True)

    def test_empty_result_rejected(self):
        empty = replace(self.decoded[1], root=copy.deepcopy(self.decoded[1].root))
        group = empty.root.find("Root/Group")
        for entry in group.findall("Entry"):
            group.remove(entry)
        with self.assertRaises(ValueError):
            official.check_edit(self.decoded[0], empty, "synthetic-rust-edit")
