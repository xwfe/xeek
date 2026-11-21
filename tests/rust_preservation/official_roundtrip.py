"""官方 KeePass/KPScript 2.62 合成往返；不提供生产写入入口。"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIXTURES = ROOT / "tests/fixtures/kdbx"
MANIFEST = FIXTURES / "official_keepass_manifest.json"
sys.path[:0] = [str(ROOT / "tests/kdbx_oracle/.deps-argon2"),
               str(ROOT / "tests/kdbx_oracle"), str(FIXTURES)]
from kdbx_oracle import KdbxError, read_kdbx
from kdbx_oracle.semantic import canonicalize, diff, summarize
from matrix_checks import current_entries, fields, paths

PASSWORD = "keex-synthetic-OFFICIAL-262"
ARCHIVES = {
    "KeePass-2.62.zip": ("https://downloads.sourceforge.net/project/keepass/KeePass%202.x/2.62/KeePass-2.62.zip",
                         "49b008e4ca9e9db9cb22e1173ec0f7676235b5309d7b47213cf81010cd1bbeed"),
    "KPScript-2.62.zip": ("https://keepass.info/extensions/v2/kpscript/KPScript-2.62.zip",
                          "d87336c432ca02ef44f8c3acf2119abe675989999f564036676d452cb6dfc899"),
}
STAGES = ("official-base", "rust-edit", "official-reedit")
EXPECT = {"version": "4.1", "current_entries": 1, "history_entries": [0, 1, 2],
          "null_spelling_counts": [2, 2], "strict_zero_diff": False}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check_edit(before, after, value, *, official=False, inspect_null_spelling=False):
    if (before.version, before.cipher, before.kdf, before.compressed) != (
            after.version, after.cipher, after.kdf, after.compressed):
        raise ValueError("crypto configuration changed")
    entries = current_entries(before)
    if len(entries) != 1 or set(entries) != set(current_entries(after)):
        raise ValueError("expected one unchanged synthetic entry identity")
    identifier, = entries
    expected = replace(before, root=copy.deepcopy(before.root))
    entry = current_entries(expected)[identifier]
    snapshot = copy.deepcopy(entry)
    for nested in snapshot.findall("History"):
        snapshot.remove(nested)
    history = entry.find("History")
    if history is None:
        history = ET.SubElement(entry, "History")
    history.append(snapshot)
    next(s.find("Value") for s in entry.findall("String") if s.findtext("Key") == "UserName").text = value
    if fields(current_entries(after)[identifier])["UserName"].value != value:
        raise ValueError("expected edit missing")
    base = paths(before)[identifier] + "/Times/"
    allowed = {base + "LastModificationTime"}
    if official:
        allowed |= {base + "LastAccessTime", base + "UsageCount"}
    changes = diff(canonicalize(expected), canonicalize(after), ignore=())
    representations = []
    if inspect_null_spelling:
        root_path = paths(before)[identifier].rsplit("/Entry=", 1)[0]
        for tag in ("EnableAutoType", "EnableSearching"):
            left = before.root.findtext("Root/Group/" + tag)
            right = after.root.findtext("Root/Group/" + tag)
            if left != right and left in ("Null", "null") and right in ("Null", "null"):
                path = root_path + "/" + tag
                representations.append({"path": path, "before": left, "after": right})
    known = {c["path"] for c in representations}
    unexpected = [c.label for c in changes if not (
        c.kind == "changed" and c.aspect == "value" and c.path in allowed | known)]
    if unexpected:
        raise ValueError("unexpected semantics: " + repr(unexpected))
    return {"time_changes": sorted(c.path for c in changes if c.path in allowed),
            "null_spelling_differences": representations}


def run(command, **kwargs):
    result = subprocess.run(command, capture_output=True, text=True, timeout=180, **kwargs)
    if result.returncode:
        raise RuntimeError(f"subprocess rc={result.returncode}: {result.stdout}{result.stderr}")
    return result.stdout.strip()


def generate(tools, mono_root):
    destinations = [FIXTURES / ("of262-" + stage + ".kdbx") for stage in STAGES]
    if MANIFEST.exists() or any(p.exists() for p in destinations):
        raise ValueError("refusing to refresh existing registration or samples")
    app = tools / "keepass-2.62"
    for name, (_, checksum) in ARCHIVES.items():
        archive = tools / name
        if digest(archive.read_bytes()) != checksum:
            raise ValueError("official archive checksum mismatch")
        with zipfile.ZipFile(archive) as z:
            exe = "KPScript.exe" if name.startswith("KPScript") else "KeePass.exe"
            if z.read(exe) != (app / exe).read_bytes():
                raise ValueError("installed executable differs from verified archive")
    helper = ROOT / "tests/reference_writer/target/release/keex-history-edit"
    if not helper.is_file():
        raise ValueError("build the existing patched helper first")
    env = dict(os.environ)
    env.update(PATH=str(mono_root / "usr/bin") + os.pathsep + env["PATH"],
               MONO_PATH=str(mono_root / "usr/lib/mono/4.5"),
               MONO_CFG_DIR=str(mono_root / "etc"), MONO_GAC_PREFIX=str(mono_root / "usr"),
               LD_LIBRARY_PATH=os.pathsep.join(str(mono_root / p) for p in
                                               ("usr/lib", "usr/lib/x86_64-linux-gnu")))
    parent = HERE / "target"
    parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="official-", dir=parent) as name:
        work = Path(name)
        env["KEEX_OFFICIAL_OUT"] = str(work)

        def official(mode):
            env["KEEX_OFFICIAL_MODE"] = mode
            output = run(["xvfb-run", "-a", str(mono_root / "usr/bin/mono-sgen"),
                          str(app / "KPScript.exe"), str(HERE / "official.kps")], env=env)
            expected = "official_create_ok" if mode == "create" else "official_reopen_reedit_ok"
            if expected not in output:
                raise ValueError("official script did not report success")
            print(output)

        official("create")
        before = read_kdbx((work / "official-base.kdbx").read_bytes(), PASSWORD)
        if before.version != "4.1":
            raise ValueError("official sample is not KDBX 4.1")
        identifier, = current_entries(before)
        run([str(helper), str(work / "official-base.kdbx"), str(work / "rust-edit.kdbx"),
             identifier, "synthetic-rust-edit"], input=PASSWORD + "\n")
        edited = read_kdbx((work / "rust-edit.kdbx").read_bytes(), PASSWORD)
        rust_changes = check_edit(before, edited, "synthetic-rust-edit", inspect_null_spelling=True)
        official("control")
        control = read_kdbx((work / "official-control.kdbx").read_bytes(), PASSWORD)
        control_changes = check_edit(before, control, "synthetic-official-reedit", official=True)
        official("edit")
        final = read_kdbx((work / "official-reedit.kdbx").read_bytes(), PASSWORD)
        official_changes = check_edit(edited, final, "synthetic-official-reedit", official=True, inspect_null_spelling=True)
        manifest = {
            "level": "L0", "client": "KeePass 2.62 + KPScript 2.62 (Dominik Reichl)",
            "license": "GPL-2.0-or-later", "platform": "Linux x86_64 / Mono 6.8.0.105 / Xvfb",
            "integrity_sources": ["https://keepass.info/integrity.html", "https://keepass.info/integrity_etc.html"],
            "archives": {name: {"url": url, "sha256": checksum} for name, (url, checksum) in ARCHIVES.items()},
            "password": PASSWORD, "entry": identifier, "expect": EXPECT,
            "provenance": {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in
                           [Path(__file__), HERE / "official.kps", HERE / "build.py",
                            ROOT / "tests/reference_writer/src/main.rs", HERE / "src/history_edit.rs",
                            ROOT / "tests/reference_writer/Cargo.lock", *sorted((HERE / "patches").glob("*.patch"))]},
            "helper_sha256": digest(helper.read_bytes()),
            "oracle": {"rust": rust_changes, "official_control": control_changes,
                       "official_reedit": official_changes, "strict_zero_diff": False,
                       "note": "Raw oracle reports Null/null spelling differences; no global normalization changed."},
            "samples": [{"file": path.name, "stage": stage,
                         "sha256": digest((work / (stage + ".kdbx")).read_bytes()), "summary": summarize(decoded)}
                        for stage, path, decoded in zip(STAGES, destinations, (before, edited, final))],
        }
        created = []
        try:
            for stage, path in zip(STAGES, destinations):
                with path.open("xb") as stream:
                    created.append(path)
                    stream.write((work / (stage + ".kdbx")).read_bytes())
            with MANIFEST.open("x") as stream:
                created.append(MANIFEST)
                json.dump(manifest, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        except BaseException:
            for path in reversed(created):
                path.unlink()
            raise
    print("registered 3 new L0 samples; 2 Null/null representation differences per roundtrip leg, no other unexpected differences")


class OfficialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text())
        cls.decoded = []
        for sample in cls.manifest["samples"]:
            data = (FIXTURES / sample["file"]).read_bytes()
            if digest(data) != sample["sha256"]:
                raise ValueError("fixture digest mismatch")
            decoded = read_kdbx(data, PASSWORD)
            if summarize(decoded) != sample["summary"]:
                raise ValueError("fixture summary mismatch")
            cls.decoded.append(decoded)

    def test_registered_roundtrip(self):
        base, rust, official = self.decoded
        expected = self.manifest["expect"]
        for decoded, count in zip(self.decoded, expected["history_entries"]):
            self.assertEqual(decoded.version, expected["version"])
            self.assertEqual(len(current_entries(decoded)), expected["current_entries"])
            self.assertEqual(summarize(decoded)["history_entries"], count)
        left = check_edit(base, rust, "synthetic-rust-edit", inspect_null_spelling=True)
        right = check_edit(rust, official, "synthetic-official-reedit", official=True, inspect_null_spelling=True)
        self.assertEqual([len(left["null_spelling_differences"]), len(right["null_spelling_differences"])],
                         expected["null_spelling_counts"])
        self.assertFalse(expected["strict_zero_diff"])

    def test_strict_raw_oracle_difference_is_not_hidden(self):
        with self.assertRaises(ValueError):
            check_edit(self.decoded[0], self.decoded[1], "synthetic-rust-edit")

    def test_no_edit_rejected(self):
        with self.assertRaises(ValueError):
            check_edit(self.decoded[0], self.decoded[0], "synthetic-rust-edit")

    def test_unrelated_change_rejected(self):
        changed = replace(self.decoded[1], root=copy.deepcopy(self.decoded[1].root))
        changed.root.find("Meta/DatabaseName").text = "synthetic-unrelated"
        with self.assertRaises(ValueError):
            check_edit(self.decoded[0], changed, "synthetic-rust-edit", inspect_null_spelling=True)

    def test_wrong_password_rejected(self):
        sample = self.manifest["samples"][0]
        with self.assertRaises(KdbxError):
            read_kdbx((FIXTURES / sample["file"]).read_bytes(), "wrong-synthetic")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("generate", "verify"))
    parser.add_argument("--tools", type=Path)
    parser.add_argument("--mono-root", type=Path)
    args = parser.parse_args()
    if args.mode == "generate":
        if args.tools is None or args.mono_root is None:
            parser.error("generate requires --tools and --mono-root")
        generate(args.tools.resolve(), args.mono_root.resolve())
    else:
        unittest.main(argv=[sys.argv[0]], verbosity=2)
