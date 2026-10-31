# K070 浏览器 KDBX 核心

把 K003 同一套补丁的 keepass 0.15.3 编译成 WASM，在浏览器 Worker 里跑。只处理公开合成库，不是生产绑定。结论见 [K070 证据](../../adr/evidence/K070.md)。

## 怎么跑

工具链只装在这个目录（`.toolchain/`，约 560 MB），不动全局环境。从仓库根目录执行：

~~~sh
RUSTUP_HOME="$PWD/tests/wasm_core/.toolchain/rustup" rustup toolchain install 1.98.0 --profile minimal --target wasm32-unknown-unknown --no-self-update
RUSTUP_HOME="$PWD/tests/wasm_core/.toolchain/rustup" tests/wasm_core/.toolchain/rustup/toolchains/1.98.0-aarch64-apple-darwin/bin/cargo install wasm-bindgen-cli --version 0.2.129 --locked --root "$PWD/tests/wasm_core/.toolchain/tools"
python3 -B tests/rust_preservation/build.py   # 原生对照 helper
python3 -B tests/wasm_core/build.py           # 产物放进 tests/web_storage/site/wasm/
cd tests/web_storage && node drive-core.mjs   # 全部可驱动的浏览器
~~~

Safari 和真机：`node drive-core.mjs --serve 47113`，把打印的地址贴进浏览器，跑完自动核对。

## 文件

| 文件 | 作用 |
| --- | --- |
| [src/core.rs](src/core.rs) | 浏览器和原生共用的一份逻辑 |
| [src/web.rs](src/web.rs)、[src/native.rs](src/native.rs) | 两个薄壳：wasm-bindgen 导出和 C ABI |
| [build.py](build.py) | 核对缓存哈希、打补丁、编译 |
| [check_outputs.py](check_outputs.py) | 浏览器写出的库交给独立 oracle、原生补丁库和 KeePassXC 核对 |
| [compare_candidates.py](compare_candidates.py) | 社区候选和补丁版用同一批输入比较 |

`compare_candidates.py manykee-fork` 会克隆 ManyKee（固定提交，见脚本）到 `target/candidates/`，编译并运行它的代码，只喂合成库。默认不想跑外部代码时，点名别的候选即可。

## 常见报错

- `Library not loaded: @rpath/libLLVM.dylib`：直接用了工具链的 cargo。build.py 会补上 `DYLD_FALLBACK_LIBRARY_PATH`，手动编译要自己加。
- 浏览器报 `CompileError`：响应头的 CSP 没有 `'wasm-unsafe-eval'`。这是 WASM 唯一需要的放开，不需要 `'unsafe-eval'`。
- `RuntimeError: unreachable`：通常是 Argon2 内存到了 2 GiB。wasm32 单次分配不能超过这个数，这个 Worker 要丢弃。
