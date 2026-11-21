"""隔离 _merge 保存重开诊断；通过表示缺陷复现，不批准生产合并。"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import tarfile
import tempfile
import tomllib
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from collections import Counter

import build
from kdbx_oracle import KdbxError, read_kdbx
from kdbx_oracle.semantic import canonicalize, diff
from matrix_checks import current_entries, fields, paths


def check_result(dest, source, actual, *, attachment):
    entries = current_entries(dest)
    if len(entries) != 1 or set(entries) != set(current_entries(source)) or set(entries) != set(current_entries(actual)):
        raise ValueError("expected one unchanged entry identity")
    identifier, = entries
    before, incoming = entries[identifier], current_entries(source)[identifier]
    if fields(before)["UserName"].value != "synthetic-official-base" or fields(incoming)["UserName"].value != "synthetic-source":
        raise ValueError("merge input controls missing")
    if before.findall("History/Entry") or incoming.findall("History/Entry"):
        raise ValueError("expected empty input histories")
    expected = replace(dest, root=copy.deepcopy(dest.root))
    entry = current_entries(expected)[identifier]
    next(s.find("Value") for s in entry.findall("String") if s.findtext("Key") == "UserName").text = "synthetic-source"
    entry.find("Times/LastModificationTime").text = incoming.findtext("Times/LastModificationTime")
    changes = diff(canonicalize(expected), canonicalize(actual), ignore=())
    if changes:
        raise ValueError("unexpected merge semantics: " + repr([c.label for c in changes]))
    if (dest.version, dest.cipher, dest.kdf, dest.compressed, dest.inner_stream) != (actual.version, actual.cipher, actual.kdf, actual.compressed, actual.inner_stream):
        raise ValueError("crypto configuration changed")
    if Counter(dest.binaries.values()) != Counter(actual.binaries.values()):
        raise ValueError("unexpected attachment pool semantics")
    history = entry.find("History")
    if history is None:
        history = ET.SubElement(entry, "History")
    snapshot = copy.deepcopy(before)
    for nested in snapshot.findall("History"):
        snapshot.remove(nested)
    history.append(snapshot)
    wanted = {"removed " + paths(dest)[identifier] + "/History"}
    if attachment:
        binary = next((b for b in incoming.findall("Binary") if b.findtext("Key") == "source-only.txt"), None)
        if binary is None or source.binaries[binary.find("Value").get("Ref")][0] != b"synthetic-source-attachment":
            raise ValueError("source attachment control missing")
        binary = copy.deepcopy(binary)
        original_ref = binary.find("Value").get("Ref")
        binary.find("Value").set("Ref", "merge-probe-source-only")
        expected = replace(expected, binaries={**dest.binaries, "merge-probe-source-only": source.binaries[original_ref]})
        entry.append(binary)
        wanted.add("removed " + paths(dest)[identifier] + "/Binary=source-only.txt")
    gaps = diff(canonicalize(expected), canonicalize(actual), ignore=())
    if {c.label for c in gaps} != wanted:
        raise ValueError("expected persistent defects not reproduced")
    return sorted(wanted)


def oracle_checks(work, password):
    cases = {}
    for kind in ("history", "attachment"):
        cases[kind] = [read_kdbx((work / f"{kind}-{stage}.kdbx").read_bytes(), password)
                       for stage in ("dest", "source", "merged", "reopened")]

    class PersistenceTests(unittest.TestCase):
        def test_saved_and_reopened_defects_with_full_semantics(self):
            for kind, (dest, source, merged, reopened) in cases.items():
                for actual in (merged, reopened):
                    gaps = check_result(dest, source, actual, attachment=kind == "attachment")
                    print(f"oracle {kind}: " + "; ".join(gaps))

        def test_empty_result_rejected(self):
            dest, source, merged, _ = cases["history"]
            empty = replace(merged, root=copy.deepcopy(merged.root))
            group = empty.root.find("Root/Group")
            group.remove(group.find("Entry"))
            with self.assertRaises(ValueError):
                check_result(dest, source, empty, attachment=False)

        def test_unrelated_change_rejected(self):
            dest, source, merged, _ = cases["history"]
            changed = replace(merged, root=copy.deepcopy(merged.root))
            changed.root.find("Meta/DatabaseName").text = "synthetic-unexpected"
            with self.assertRaisesRegex(ValueError, "unexpected merge semantics"):
                check_result(dest, source, changed, attachment=False)

        def test_absent_source_attachment_rejected(self):
            dest, source, merged, _ = cases["attachment"]
            missing = replace(source, root=copy.deepcopy(source.root))
            entry = next(iter(current_entries(missing).values()))
            entry.remove(next(b for b in entry.findall("Binary") if b.findtext("Key") == "source-only.txt"))
            with self.assertRaisesRegex(ValueError, "source attachment control missing"):
                check_result(dest, missing, merged, attachment=True)

        def test_not_merged_is_not_a_pass(self):
            dest, source, _, _ = cases["history"]
            with self.assertRaises(ValueError):
                check_result(dest, source, dest, attachment=False)

        def test_wrong_password_rejected(self):
            with self.assertRaises(KdbxError):
                read_kdbx((work / "history-merged.kdbx").read_bytes(), "synthetic-wrong-password")

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PersistenceTests))
    if not result.wasSuccessful():
        raise ValueError("persistent merge oracle checks failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preservation", action="store_true", help="同时应用八补丁并运行原保留 API 测试")
    args = parser.parse_args()
    text = (build.REFERENCE / "Cargo.lock").read_text()
    archive = build.source_archive(tomllib.loads(text))
    parent = build.HERE / "target"
    parent.mkdir(exist_ok=True)
    manifest = json.loads((build.FIXTURES / "official_keepass_manifest.json").read_text())
    sample = manifest["samples"][0]
    data = (build.FIXTURES / sample["file"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != sample["sha256"]:
        raise ValueError("registered official fixture digest mismatch")
    with tempfile.TemporaryDirectory(prefix="merge-", dir=parent) as name:
        work = build.Path(name)
        with tarfile.open(archive) as source:
            source.extractall(work, filter="data")
        if args.preservation:
            upstream = work / ("keepass-" + build.VERSION)
            for patch in build.PATCHES:
                build.run(["git", "apply", "--directory=" + str(upstream.relative_to(build.ROOT)), str(patch)])
            data_dual, password_dual = build.make_case("dual-icons")
            (work / "dual-icons.kdbx").write_bytes(data_dual)
            (work / "dual-icons.password").write_text(password_dual)
            data_vault, password_vault = build.vault_fixture()
            (work / "vault.kdbx").write_bytes(data_vault)
            (work / "vault.password").write_text(password_vault)
            build.unknown_content_inputs(work)
            (work / "fixtures.tsv").write_text(build.registered_fixtures())
        package = (build.REFERENCE / "Cargo.toml").read_text().replace(
            'name = "keex-reference-writer"', f'name = "{build.NAME}"', 1
        ).replace('keepass = { ', f'keepass = {{ path = "keepass-{build.VERSION}", ', 1
        ).replace('["save_kdbx4"]', '["save_kdbx4", "_merge"]', 1)
        package += '\n[[test]]\nname = "merge_probe"\npath = ' + json.dumps(
            str(build.HERE / "tests/merge_probe.rs")) + "\n"
        package += '\n[features]\npreservation_probe = []\n'
        if args.preservation:
            package += '\n[[test]]\nname = "preservation"\npath = ' + json.dumps(str(build.HERE / "tests/preservation.rs")) + "\n"
        (work / "Cargo.toml").write_text(package)
        (work / "Cargo.lock").write_text(build.isolated_lock(text))
        (work / "official.kdbx").write_bytes(data)
        (work / "password").write_text(manifest["password"])
        (work / "entry-id").write_text(manifest["entry"])
        arguments = ["cargo", "test", "--locked", "--offline", "--release",
                     "--manifest-path", str(work / "Cargo.toml"), "--target-dir",
                     str(parent / "merge-build"), "--test", "merge_probe"]
        if args.preservation:
            arguments += ["--test", "preservation", "--features", "preservation_probe"]
        print(build.run(arguments + ["--", "--nocapture"], timeout=300))
        if (work / "Cargo.lock").read_text() != build.isolated_lock(text):
            raise ValueError("isolated lock changed")
        oracle_checks(work, manifest["password"])
    print("preservation + _merge diagnostics" if args.preservation else "upstream _merge diagnostics")
    print("known defects reproduced; production merge/writer gate remains CLOSED")


if __name__ == "__main__":
    main()
