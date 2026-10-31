# K070 Flutter 联合实验

一个 Dart 接口（`VaultCore`），原生走 FFI，Web 走 Worker + WASM，下面是同一份 Rust。只处理公开合成库，不是产品代码。结论见 [K070 证据](../../adr/evidence/K070.md)。

## 怎么跑

先按 [tests/wasm_core](../wasm_core/README.md) 编好核心，然后：

~~~sh
python3 -B tests/wasm_core/compare_candidates.py keex-patched dart-ffi-rust   # 原生：Dart → FFI → Rust
cd tests/web_storage && node drive-flutter.mjs                                # Web：Flutter → Worker → WASM
~~~

`drive-flutter.mjs` 用 `flutter build web --csp --no-web-resources-cdn` 构建，JS 和 Wasm 两种都跑，同时记录第三方请求和被 CSP 拦下的内容。Safari 用 `node drive-flutter.mjs --serve 47114`，把打印的地址贴进去。

## 文件

| 文件 | 作用 |
| --- | --- |
| [keex_core/lib/src/vault_core.dart](keex_core/lib/src/vault_core.dart) | 界面只认的接口 |
| [keex_core/lib/src/native.dart](keex_core/lib/src/native.dart) | 原生实现，KDF 放后台 isolate |
| [keex_core/lib/src/web.dart](keex_core/lib/src/web.dart) | Web 实现，KDF 放 Worker |
| [keex_core/bin/helper.dart](keex_core/bin/helper.dart) | 命令行入口，让这条路径接受同一套核对 |
| [app/lib/main.dart](app/lib/main.dart) | 最小 Flutter 页面 |

## 常见报错

- `Failed to load dynamic library`：没设 `KEEX_CORE_LIB`，或没编原生库。对比脚本会自己设。
- 页面一直没有上报：看 `results/wasm-out/<标签>.progress.txt`，它记录了走到哪一步。
- Safari 里停顿约 150 秒：见证据的“还没解决”。
