"""Export locked upstream Cargo metadata, without copying upstream source."""

import collections
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

COMMIT = "2f51d8611677c8a6bbad937b39756e8d0cc45350"
source = Path(sys.argv[1]).resolve()
out = Path(__file__).resolve().parent


def run(*args):
    return subprocess.check_output(args, cwd=source, text=True)


assert run("git", "rev-parse", "HEAD").strip() == COMMIT
assert not run("git", "status", "--porcelain")


def metadata(*args):
    return json.loads(run("cargo", "metadata", "--locked", "--format-version", "1", *args))


def closure(meta, root):
    nodes = {n["id"]: n for n in meta["resolve"]["nodes"]}
    pending = [p["id"] for p in meta["packages"] if p["name"] == root]
    assert len(pending) == 1, root
    seen = set()
    while pending:
        key = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        pending.extend(d["pkg"] for d in nodes[key]["deps"]
                       if any(k["kind"] != "dev" for k in d["dep_kinds"]))
    return {(p["name"], p["version"]) for p in meta["packages"] if p["id"] in seen}


platforms = {}
for name, target, root in [
    ("android", "aarch64-linux-android", "nsh-platform-android"),
    ("ios", "aarch64-apple-ios", "nsh-ios-app"),
    ("web", "wasm32-unknown-unknown", "nsh-platform-web"),
]:
    platforms[name] = closure(metadata("--filter-platform", target), root)

summary = {"commit": COMMIT, "cargo": run("cargo", "--version").strip(),
           "rustc": run("rustc", "--version").strip(),
           "toolchain": (source / "rust-toolchain.toml").read_text(),
           "sha256": {p: hashlib.sha256((source / p).read_bytes()).hexdigest()
                      for p in ["Cargo.lock", "crates/gpui/Cargo.lock", "rust-toolchain.toml"]}}
for name, args in [("root", []), ("gpui", ["--manifest-path", "crates/gpui/Cargo.toml"])]:
    meta = metadata(*args)
    summary[name] = {"packages": len(meta["packages"]), "licenses": dict(sorted(
        collections.Counter(p["license"] or "UNKNOWN" for p in meta["packages"]).items()))}
    with (out / f"{name}-dependencies.tsv").open("w") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["crate", "version", "license", "source", "android", "ios", "web"])
        for p in sorted(meta["packages"], key=lambda p: (p["name"], p["version"])):
            membership = ["possible" if (p["name"], p["version"]) in platforms[t] else "no"
                          for t in platforms] if name == "root" else ["not-selected"] * 3
            writer.writerow([p["name"], p["version"], p["license"] or "UNKNOWN",
                             p["source"] or "workspace", *membership])
(out / "inventory.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
print("root:", summary["root"]["packages"], "gpui:", summary["gpui"]["packages"])
