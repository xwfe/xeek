"""核对 NSH 合成副本；不放宽现有 oracle 的规范化规则。"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tests/kdbx_oracle/.deps-argon2"),
               str(ROOT / "tests/kdbx_oracle"), str(ROOT / "tests/fixtures/kdbx")]
from kdbx_oracle import read_kdbx
from kdbx_oracle.semantic import canonicalize, diff
from matrix_checks import current_entries, fields, paths

OUT = Path(__file__).resolve().parent / "rust/target/outputs"
FIXTURES = ROOT / "tests/fixtures/kdbx"
VALUE = "synthetic-nsh-edit"


def verify(before, after, identifier):
    identifier = identifier.replace("-", "")
    if identifier not in current_entries(before):
        raise ValueError("missing target")
    if (before.version, before.cipher, before.kdf, before.compressed) != (
            after.version, after.cipher, after.kdf, after.compressed):
        raise ValueError("changed crypto configuration")
    expected = replace(before, root=copy.deepcopy(before.root))
    entry = current_entries(expected)[identifier]
    snapshot = copy.deepcopy(entry)
    for nested in snapshot.findall("History"):
        snapshot.remove(nested)
    history = entry.find("History")
    if history is None:
        history = ET.SubElement(entry, "History")
    history.append(snapshot)
    field = next(s.find("Value") for s in entry.findall("String") if s.findtext("Key") == "UserName")
    field.text = VALUE
    if fields(current_entries(after)[identifier])["UserName"].value != VALUE:
        raise ValueError("edit missing")
    path = paths(before)[identifier] + "/Times/LastModificationTime"
    changes = [change for change in diff(canonicalize(expected), canonicalize(after), ignore=())
               if change.path != path]
    if changes:
        raise ValueError("unexpected semantic changes: " + str(len(changes)))


def inputs(name="baseline"):
    identifier = {"baseline": "V41-VAULT", "scale-1000": "M41-SCALE-1000-SMALL",
                  "scale-10000": "M41-SCALE-10000-SMALL"}[name]
    manifest = json.loads((FIXTURES / ("vault_manifest.json" if name == "baseline" else "matrix_manifest.json")).read_text())
    sample = next(s for s in manifest["samples"] if s["id"] == identifier)
    stage = next(s for s in sample["stages"] if s["name"] == ("edit2" if name == "baseline" else "import"))
    data = (FIXTURES / stage["file"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != stage["sha256"]:
        raise ValueError("fixture digest mismatch")
    receipt = json.loads((OUT / f"receipt-{name}.json").read_text())
    if receipt["sample"] != name:
        raise ValueError("receipt sample mismatch")
    output = (OUT / receipt["copy"]).resolve()
    if output.parent != OUT.resolve() or output.suffix != ".kdbx":
        raise ValueError("invalid copy path")
    password = sample["credentials"]["password"]
    before = read_kdbx(data, password)
    after = read_kdbx(output.read_bytes(), password)
    return before, after, receipt["entry"]


class OracleSliceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before, cls.after, cls.identifier = inputs()

    def test_saved_copy_and_unchanged_semantics(self):
        verify(self.before, self.after, self.identifier)

    def test_scale_copies(self):
        for name in ("scale-1000", "scale-10000"):
            with self.subTest(sample=name):
                verify(*inputs(name))

    def test_no_edit_is_not_a_pass(self):
        with self.assertRaises(ValueError):
            verify(self.before, self.before, self.identifier)

    def test_unrelated_change_is_not_a_pass(self):
        changed = replace(self.after, root=copy.deepcopy(self.after.root))
        changed.root.find("Meta/DatabaseName").text = "synthetic-unrelated-change"
        with self.assertRaises(ValueError):
            verify(self.before, changed, self.identifier)

    def test_missing_target_is_not_a_pass(self):
        with self.assertRaises(ValueError):
            verify(self.before, self.after, "missing-target")


if __name__ == "__main__":
    unittest.main(verbosity=2)
