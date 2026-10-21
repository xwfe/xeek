# K003 对照候选：kdbx.dart 合成读改写 helper

此目录用 kdbx（kdbx.dart）2.5.0 做“读取已有公开合成库 → 改一个 UserName → 保存为新文件”，与 [keepass-rs 参考 helper](../reference_writer/README.md) 用同一批输入、同一套比较口径。它是 K003 的候选对照实验，不是生产 writer，也不是 K009 选型结论。实测结果、差异和不支持项见 [K003 证据](../../adr/evidence/K003.md)。

## 先知道的三件事

- **许可证是 GPL-3.0。** 这里只作为独立测试进程运行，不链接进 keex。若产品链接它，整个应用要按 GPL-3.0 发布，这必须在 K009 定发行许可证时先裁决。
- **不支持 Argon2id，也不支持 KDBX 3.1 外层 ChaCha20。** 2.5.0 源码只登记 Argon2d 与 AES-KDF 两个 KDF；3.x 固定按 AES-CBC 解密。这类库直接打不开，helper 报 `database_open_failed`，不会产出文件。
- **Argon2 走纯 Dart。** `KdbxFormat()` 不传实现时用 pointycastle 的 Argon2，不加载包里附带的预编译 `libargon2_ffi` 原生库。纯 Dart 的 AES-KDF 很慢：100 万轮的库读一次、存一次，本机要 7–13 秒。

## 依赖和构建

需要本机已有 Dart SDK ≥ 3.9（本机实测 3.13.5）。依赖装在本目录的 `.pub-cache/`，不写全局 pub 缓存；`pubspec.lock` 固定全部传递依赖和 sha256。第一次需要联网下载：

~~~sh
cd tests/dart_candidate
PUB_CACHE="$PWD/.pub-cache" dart pub get --enforce-lockfile
PUB_CACHE="$PWD/.pub-cache" dart compile exe bin/keex_dart_candidate.dart -o build/keex-dart-candidate
~~~

缓存齐了以后，生成器会用 `--offline --enforce-lockfile` 重新构建，防止拿旧二进制当新源码结果。锁文件里除 kdbx 外还有 dio、argon2_ffi_base 等传递依赖（来自 kdbx 的 `logging_appenders` 和 FFI 接口）；helper 不调用网络，也不加载 FFI 库，但它们仍会被下载，供应链审查时要算进去。

## 生成与验证

仓库根目录执行：

~~~sh
python3 -B tests/dart_candidate/generate.py
python3 -B tests/run_python_tests.py --suite oracle --pattern test_dart_candidate.py -v
~~~

`dart_writer_manifest.json` 已存在时，生成器只核对源码哈希、案例参数、输入和产物哈希，然后无操作退出，不构建、不写文件。

helper 参数顺序为 `INPUT OUTPUT UUID NEW_USERNAME [KEYFILE]`；密码从单行标准输入读取，不进 argv。它在内存完成加密后才排他创建新目标，拒绝覆盖源文件或已有文件；只打印计数或固定错误码，库内部异常原文不输出（可能带字段内容）。Dart 没有在创建时指定 0600 的接口，所以生成器让它写进权限 0700 的临时目录，再统一发布。

## 失败处理

首次生成先在临时目录完成全部保存、独立解码、KeePassXC 重开和再编辑，再排他发布；普通异常只清理本次新建文件。强杀或磁盘故障可能留下锁文件 `.dart-writer-generate.lock` 或未登记输出，下次会拒绝覆盖，需要人工核对来源和哈希后再处理。这里没有生产事务保存、并发控制或崩溃恢复承诺。
