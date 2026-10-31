"""K070 构建：把和 K003 同一套补丁的 keepass 编译成 WASM，产物放进探针站点。

工具链装在 .toolchain/ 里（版本见 TOOLCHAIN），不动全局环境；步骤见 README。
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOOLCHAIN = "1.98.0"
RUSTUP_HOME = HERE / ".toolchain" / "rustup"
BIN = RUSTUP_HOME / "toolchains" / f"{TOOLCHAIN}-aarch64-apple-darwin" / "bin"
WASM_BINDGEN = HERE / ".toolchain" / "tools" / "bin" / "wasm-bindgen"
TARGET = HERE / "target"
SITE_OUT = ROOT / "tests" / "web_storage" / "site" / "wasm"
CRATE = "keex_wasm_core"

spec = importlib.util.spec_from_file_location("preservation_build", ROOT / "tests/rust_preservation/build.py")
preservation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preservation)


def run(argv, *, env=None, cwd=ROOT):
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=1500, env=env)
    if result.returncode:
        raise RuntimeError(f"{argv[0]} failed ({result.returncode}):\n{result.stdout}{result.stderr}")
    return result.stdout


def patched_source():
    """每次从核对过哈希的缓存归档重新解包并打补丁，保证和 K003 是同一份代码。"""
    lock = tomllib.loads((preservation.REFERENCE / "Cargo.lock").read_text())
    archive = preservation.source_archive(lock)
    source = TARGET / "source"
    shutil.rmtree(source, ignore_errors=True)
    source.mkdir(parents=True)
    with tarfile.open(archive) as crate:
        crate.extractall(source, filter="data")
    upstream = source / f"keepass-{preservation.VERSION}"
    for patch in preservation.PATCHES:
        run(["git", "apply", "--directory=" + str(upstream.relative_to(ROOT)), str(patch)])
    return upstream


def build_env():
    # rust-lld 的 rpath 指向 rustlib/<host>/lib，而 libLLVM 在工具链的 lib/ 下，不补会报 Library not loaded。
    return {**os.environ, "PATH": f"{BIN}:{os.environ['PATH']}", "RUSTUP_HOME": str(RUSTUP_HOME),
            "DYLD_FALLBACK_LIBRARY_PATH": str(BIN.parent / "lib")}


def main():
    patched_source()
    env = build_env()
    run(["cargo", "build", "--release", "--locked", "--target", "wasm32-unknown-unknown",
         "--manifest-path", str(HERE / "Cargo.toml"), "--target-dir", str(TARGET)], env=env)
    binary = TARGET / "wasm32-unknown-unknown" / "release" / f"{CRATE}.wasm"
    shutil.rmtree(SITE_OUT, ignore_errors=True)
    run([str(WASM_BINDGEN), "--target", "web", "--no-typescript", "--out-dir", str(SITE_OUT), str(binary)], env=env)
    out = SITE_OUT / f"{CRATE}_bg.wasm"
    print(f"built {out.relative_to(ROOT)}: {out.stat().st_size} bytes")


if __name__ == "__main__":
    sys.exit(main())
