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


def build_native(env):
    """本机动态库：给桌面 Dart 和 Swift 用。原生目标要接住 panic，所以不用 abort。"""
    run(["cargo", "build", "--release", "--locked", "--manifest-path", str(HERE / "Cargo.toml"),
         "--target-dir", str(TARGET)], env={**env, "CARGO_PROFILE_RELEASE_PANIC": "unwind"})


def build_wasm(env):
    run(["cargo", "build", "--release", "--locked", "--target", "wasm32-unknown-unknown",
         "--manifest-path", str(HERE / "Cargo.toml"), "--target-dir", str(TARGET)], env=env)
    binary = TARGET / "wasm32-unknown-unknown" / "release" / f"{CRATE}.wasm"
    shutil.rmtree(SITE_OUT, ignore_errors=True)
    run([str(WASM_BINDGEN), "--target", "web", "--no-typescript", "--out-dir", str(SITE_OUT), str(binary)], env=env)
    out = SITE_OUT / f"{CRATE}_bg.wasm"
    print(f"built {out.relative_to(ROOT)}: {out.stat().st_size} bytes")


def build_android(env):
    """arm64 的 .so，放进 Flutter 工程的 jniLibs。Android 15 起的设备可能用 16 KB 内存页，要按它对齐。"""
    ndk = ROOT / "tests/mobile/.android-sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/darwin-x86_64/bin"
    run(["cargo", "build", "--release", "--locked", "--target", "aarch64-linux-android",
         "--manifest-path", str(HERE / "Cargo.toml"), "--target-dir", str(TARGET)], env={
        **env,
        "CARGO_PROFILE_RELEASE_PANIC": "unwind",
        "CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER": str(ndk / "aarch64-linux-android24-clang"),
        "CARGO_TARGET_AARCH64_LINUX_ANDROID_RUSTFLAGS": "-C link-arg=-Wl,-z,max-page-size=16384",
    })
    library = TARGET / "aarch64-linux-android" / "release" / f"lib{CRATE}.so"
    target = ROOT / "tests/flutter_bridge/app/android/app/src/main/jniLibs/arm64-v8a"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy(library, target)
    print(f"built {library.name}: {library.stat().st_size} bytes")


def build_ios(env):
    """iOS 静态库和 xcframework：主程序和未来的凭据扩展各自链接同一份。"""
    outputs = []
    for triple in ("aarch64-apple-ios", "aarch64-apple-ios-sim"):
        run(["cargo", "build", "--release", "--locked", "--target", triple, "--manifest-path", str(HERE / "Cargo.toml"),
             "--target-dir", str(TARGET)], env={**env, "CARGO_PROFILE_RELEASE_PANIC": "unwind", "IPHONEOS_DEPLOYMENT_TARGET": "17.0"})
        outputs.append(TARGET / triple / "release" / f"lib{CRATE}.a")
    framework = ROOT / "tests/mobile/build/KeexCore.xcframework"
    shutil.rmtree(framework, ignore_errors=True)
    framework.parent.mkdir(parents=True, exist_ok=True)
    arguments = ["xcodebuild", "-create-xcframework"]
    for library in outputs:
        arguments += ["-library", str(library), "-headers", str(ROOT / "tests/mobile/ios/include")]
    run([*arguments, "-output", str(framework)], env=env)
    print(f"built {framework.relative_to(ROOT)}: {[f'{o.stat().st_size} bytes' for o in outputs]}")


def main():
    targets = sys.argv[1:] or ["native", "wasm"]
    patched_source()
    env = build_env()
    builders = {"native": build_native, "wasm": build_wasm, "android": build_android, "ios": build_ios}
    for target in targets:
        builders[target](env)


if __name__ == "__main__":
    sys.exit(main())
