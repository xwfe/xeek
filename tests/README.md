# 测试与实验

本目录的代码仅用于 keex 的 P0 风险实验与回归测试。测试使用公开合成数据，运行前阅读[真实数据使用规则](../adr/REAL_DATA_RULES.md)。当前任务进度见 [TASKS](../adr/TASKS.md)，已有证据与阻塞见 [STATUS](../adr/STATUS.md)。

## 干净 Linux 克隆

从仓库根运行 `python3 -B scripts/check.py`。需要 Python 3.12 或更高版本及系统时区数据（tzdata），无需下载依赖。该入口运行三项文档校验和 K068 领域契约单元测试。

| 入口 | 覆盖与前提 |
| --- | --- |
| [领域测试](vault_domain/README.md) | 字段、关系、日期规则，以及合成库往返和规模矩阵。仅契约单测可直接使用标准库。完整领域回归需安装 Python 依赖，独立对照另需 KeePassXC CLI。 |
| [KDBX oracle](kdbx_oracle/README.md) | 只读解码与语义比较。读入、比较、Salsa20 和 KDF 边界子集可在安装固定版本的 Python 依赖后单独复跑。全量回归还需要参考客户端和部分已构建 helper。4.x 负载复现校验包含 Python、zlib 与 cryptography 版本。现有 Argon2 wheel 哈希锁只覆盖 macOS arm64。 |

## Rust、浏览器与原生专项

| 入口 | 用途 |
| --- | --- |
| [NSH 固定候选](nsh_candidate/README.md) | K090 固定版本/许可与构建基线；K091 Linux-headless 复用 Rust 核心的类型化合成流程、oracle 与 1k/10k 测量。四原生端与浏览器/视觉缺口另列。 |
| [Rust 参考写入](reference_writer/README.md) | 用固定 keepass 0.15.3 对照合成 KDBX 4.1 的读改写。 |
| [Rust 保留补丁](rust_preservation/README.md) | 应用隔离补丁，验证图标、历史、附件、未知内容及参考客户端往返。需要按锁准备 Cargo 依赖，部分比较需要 KeePassXC CLI。 |
| [WASM 核心](wasm_core/README.md) | 构建既有 Rust 补丁核心与浏览器探针。当前脚本含 macOS arm64 工具链及 Darwin NDK 路径。 |
| [浏览器存储与 WebDAV](web_storage/README.md) | Playwright 存储、文件与同步实验。完整实验含 macOS 磁盘写满和 Apache 路径，Safari 和用户授权文件写回走手动入口。 |
| [原生桥接](mobile/README.md) | Android Kotlin 与 iOS Swift 调用 Rust 的既有实验。设备、SDK 和签名条件见该入口及 [K004 证据](../adr/evidence/K004.md)。 |

Linux 基线只覆盖其列出的静态与契约检查。候选写入、全量 oracle、系统凭据、浏览器与原生专项按实际平台和运行结果记录。NSH 验证从 [K090](../adr/0008-nsh-unified-clients.md) 开始，沿用 TASKS 的状态与验收要求。

## 历史 Flutter、Dart 对照

- [Flutter 桥接](flutter_bridge/README.md)保留 Dart FFI 与 Flutter Web Worker 的对照。
- [ForUI 候选](forui_candidate/README.md)保留组件、读屏、中文输入与 Web CSP 的合成界面实验。
- [kdbx.dart 候选](dart_candidate/README.md)和 [kpasslib 浏览器对照](../adr/evidence/K070.md)保留旧方案的验证证据。当前客户端方向见 [ADR-0008](../adr/0008-nsh-unified-clients.md)。

## 秘密扫描与合成夹具

- [秘密扫描](secret_scan/README.md)说明暂存区检查和 pre-commit 接入。固定 wheel 哈希锁已覆盖 CPython 3.12 / macOS arm64 与 Linux x86_64。
- [KDBX 合成夹具](fixtures/kdbx/README.md)说明样本来源、清单与回归方法。复跑直接使用仓库登记样本，保留原路径与 SHA-256。

## Linux 全量 Python 已知限制（2026-11-21，K003 归因）

不是全量通过记录，不修改样本、清单、比较器或跳过条件；生产 merge/writer 闸门仍关闭。

### main 与 K003 的同环境对照

`git worktree add ~/xeek-main origin/main` 创建干净 main（`a927da3`）。第一次入口因新 worktree 缺 ignored 的 Argon2 依赖拒绝运行；核对 `requirements.txt` 和 `requirements-argon2-macos-arm64.lock` 与 K003 完全相同后，将现有 `.deps-argon2` 环境复制到 main 的 ignored 目录，未改任何 tracked 文件。两边均使用 Python 3.12.16 / zlib 1.4，安装 CLI 前完成对照：

```sh
~/.local/bin/python3.12 -B ~/xeek-main/tests/run_python_tests.py
# Ran 242 tests in 143.523s
# FAILED (failures=9, errors=6, skipped=16)
~/.local/bin/python3.12 -B tests/run_python_tests.py
# K003 6fa6527 的上一轮原始结果：
# Ran 250 tests in 130.612s
# FAILED (failures=9, errors=6, skipped=16)
```

8 项数量差来自本分支新增的官方 KeePass 测试；15 项 failure/error 的名称、子用例和完整报错正文在规范化 worktree 路径后逐项相同，不是只对比汇总数字。下表“同错”均指 main 与 K003 原环境一致：

| 原失败项（模块／类／方法或 subTest） | main | K003 | 修复下述环境后 |
| --- | --- | --- | --- |
| `test_candidate_minimal.CandidateMinimalTest.setUpClass` | 缺 CLI | 同错 | CLI 门槛解除，暴露缺 `dart` |
| `test_rust_header.HeaderSettingsTest.setUpClass` | 缺 CLI | 同错 | 已恢复，无该类失败 |
| `test_rust_history_trim.HistoryTrimTest.setUpClass` | 缺 CLI | 同错 | 已恢复，无该类失败 |
| `test_rust_preservation.RustPreservationTest.setUpClass` | 缺 CLI | 同错 | 已恢复，无该类失败 |
| `test_rust_third_party.ThirdPartyRoundTripTest.setUpClass` | 缺 CLI | 同错 | 已恢复，无该类失败 |
| `test_v4_payload.AuthenticatedPayloadTest.test_generator_noop_preserves_bytes_and_modification_times` | manifest 不符 | 同错 | 仍错误，见 B |
| `test_fixtures.MutantSamplesTest.test_mutations_are_reproducible [R31-HEADERHASH-MISSING]` | SHA 不符 | 同错 | 仍失败，见 A |
| 同方法 `[R31-CIPHER-UNKNOWN]` | SHA 不符 | 同错 | 仍失败，见 A |
| 同方法 `[R31-GZIP-BOMB]` | SHA 不符 | 同错 | 仍失败，见 A |
| 同方法 `[R31-XML-ENTITY]` | SHA 不符 | 同错 | 仍失败，见 A |
| 同方法 `[R31-XML-EXTERNAL]` | SHA 不符 | 同错 | 仍失败，见 A |
| 同方法 `[R31-XML-DEEP]` | SHA 不符 | 同错 | 仍失败，见 A |
| `test_v4_payload.AuthenticatedPayloadTest.test_manifest_and_four_saved_controls_are_reproducible` | manifest 不符 | 同错 | 仍失败，见 B |
| `test_corpus.VaultCorpusTest.test_matrix_hashes_and_source_provenance` | 源 XML SHA 不符 | 同错 | 仍失败，见 C |
| `test_matrix.MatrixCorpusTest.test_matrix_scope_file_hashes_and_current_source_provenance` | 源 XML SHA 不符 | 同错 | 仍失败，见 C |

### 用户级工具修复及重跑

夹具和 oracle README 登记 KeePassXC **2.7.12**，不是当前官网最新版本。下载固定[官方 release](https://github.com/keepassxreboot/keepassxc/releases/tag/2.7.12) 中 `KeePassXC-2.7.12-x86_64.AppImage`、同名 `.DIGEST` 和 `.sig`，SHA-256 核对输出 `KeePassXC-2.7.12-x86_64.AppImage: OK`。另从 `https://keepassxc.org/keepassxc_master_signing_key.asc` 取得公钥，在独立用户 keyring 验签，输出 `Good signature` / `VALIDSIG`；主指纹 `BF5A 669F 2272 CF43 24C1 FDA8 CFB4 C216 6397 D0D2` 与[官网验证说明](https://keepassxc.org/verifying-signatures/)一致。keyring 未赋 owner trust，GPG 的未认证警告不等于坏签名；未修改全局信任库。

核验后在 `~/.local/keepassxc-2.7.12` 运行 `--appimage-extract`，将 `squashfs-root/usr/bin/keepassxc-cli` 链接到 `~/.local/bin/keepassxc-cli`；无需 FUSE、sudo 或系统安装，`keepassxc-cli --version` 实际为 `2.7.12`。仅测试子进程调用，许可证按 oracle README 的外部程序边界，不链接进入产品。

```sh
uv python install 3.12.12
PY312="$(uv python find 3.12.12)"
"$PY312" -c 'import sys,zlib; print(sys.version); print(zlib.ZLIB_VERSION,zlib.ZLIB_RUNTIME_VERSION)'
# Python 3.12.12；zlib build/runtime 均 1.3.1，不是登记的 1.2.12
"$PY312" -B tests/run_python_tests.py
# Ran 281 tests in 245.339s
# FAILED (failures=9, errors=2, skipped=8)
```

上述全量重跑**未注入下述诊断替换**。未发现本次 K003 引入的失败，故不修改源码。剩余 11 项的完整可达原因如下：

- **A：六个 R31 字节复现失败。** `fixtures/kdbx/mutate.py:143–148` 用 `zlib.compressobj(..., 31)` 生成 gzip；六项分别经该文件第 219、232、247、258、267、276 行压缩，再由 `v3_reencrypt` 重算哈希块和 AES 密文，最终在 `kdbx_oracle/tests/test_fixtures.py:125` 比较整个文件 SHA。逐项解开登记文件与现场重建结果，gzip 第 9 偏移的 OS 字节是登记 **19（Darwin）**、本机 **3（Unix）**；六项压缩体和 trailer 均逐字节相同。只在独立诊断进程将压缩结果第 9 字节改为 19，六项**完整 KDBX SHA 全部恢复登记值**。因此不是笼统推断“zlib 版本改变了 deflate”，也不是本分支 merge 路径执行造成的。
- **B：两个 v4 payload 错误／失败。** `fixtures/kdbx/v4_payload.py:49–51` 同样使用平台相关 gzip OS 字节；`build_manifest` 在第 301–303 行还记录运行时版本。直接重建时 **178 条记录 SHA 不同**，但四份留存的不压缩控制文件全部逐字节相同。独立反事实只改 gzip OS 字节后，全部记录与登记相同；再仅对比时替换 runtime 元数据，**整个 manifest 相同**，排除了其它 provenance/source 变更。实际原样重跑仍因 zlib **1.3.1 ≠ 1.2.12** 及 OS 字节差异，在 `kdbx_oracle/tests/test_v4_payload.py:309` 比较失败，且生成器第 315 行拒绝覆盖（由测试第 319 行调用）。原环境另有 Python 3.12.16 与登记 3.12.12 的差异；安装指定 Python 只消除了这一项。
- **C：两个领域源 XML SHA 失败。** `fixtures/kdbx/source.py:181` 将 `gzip.compress(..., mtime=0)` 的附件写为 XML base64，`vault_source.py:195–199` 重建附件池，`matrix_source.py:114,178–185` 复用／构造同类源。失败实际落在 `vault_domain/test_corpus.py:125` 与 `test_matrix.py:61`，不是前面的源码文件 provenance 校验。独立诊断仅把压缩结果 OS 字节改为 19，**3 份 vault 源和全部 7 份 matrix 源的 SHA 都恢复登记值**，含 1k/10k 和大小附件；并未改 XML 业务字段或刷新清单。
- **D：此前被缺 CLI 遮蔽的 Dart 环境门槛。** `kdbx_oracle/tests/test_candidate_minimal.py:35–39` 在 CLI 检查及 Rust 构建后执行 `dart pub get --offline --enforce-lockfile`，实际错误是 `FileNotFoundError: [Errno 2] No such file or directory: 'dart'`。检查 PATH 和常用用户级 SDK 位置未发现可执行文件，不是已有 SDK 未加载；未擅自安装任务外工具链。该测试文件与 main 的 SHA 完全一致，现有生成器也未改；这是恢复 CLI 后首次到达的既有环境门槛，不是新增 K003 回归。完整恢复还需固定 Dart SDK 及其锁定的离线 pub 缓存。

反事实只用于定位具体字节，**不是兼容修复或通过测试的方式**；没有将其用于真实全量测试，未跳过失败，也未写入仓库文件。后续需独立决定跨平台 gzip 头规范及 runtime provenance 的登记策略，不能自动刷新旧样本，单换 Python／zlib 版本也不能保证 OS 字节相同。

本机完整证据保存在 `~/k090-logs/k003-main-before.log`、`k003-merge-python-all.log`、`k003-python-fixed-env.log`、`k003-keepassxc-verify.log`、`k003-attribution.log`；只读诊断脚本为同目录 `k003-attribute.py`（不在仓库）。main worktree 保留、tracked 状态干净。本轮仓库仅补本节说明，不改变任务验收、writer 或生产权限。
