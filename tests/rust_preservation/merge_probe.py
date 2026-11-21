"""只在校验过的原版 keepass 0.15.3 上启用 _merge，固定最小反例。"""
from __future__ import annotations

import hashlib
import json
import tarfile
import tempfile
import tomllib

import build


def main():
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
        package = (build.REFERENCE / "Cargo.toml").read_text().replace(
            'name = "keex-reference-writer"', f'name = "{build.NAME}"', 1
        ).replace('keepass = { ', f'keepass = {{ path = "keepass-{build.VERSION}", ', 1
        ).replace('["save_kdbx4"]', '["save_kdbx4", "_merge"]', 1)
        package += '\n[[test]]\nname = "merge_probe"\npath = ' + json.dumps(
            str(build.HERE / "tests/merge_probe.rs")) + "\n"
        (work / "Cargo.toml").write_text(package)
        (work / "Cargo.lock").write_text(build.isolated_lock(text))
        (work / "official.kdbx").write_bytes(data)
        (work / "password").write_text(manifest["password"])
        (work / "entry-id").write_text(manifest["entry"])
        print(build.run(["cargo", "test", "--locked", "--offline", "--release",
                         "--manifest-path", str(work / "Cargo.toml"), "--target-dir",
                         str(parent / "merge-build"), "--test", "merge_probe", "--", "--nocapture"], timeout=300))
    print("upstream _merge diagnostics only; preservation patches and production features unchanged")


if __name__ == "__main__":
    main()
