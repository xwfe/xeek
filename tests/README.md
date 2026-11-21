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
| [NSH 固定候选](nsh_candidate/README.md) | K090 固定版本/许可清单、最小五导航与空 capabilities/grants 输入；Linux CLI/headless/拒绝反例/wasm32/Web 打包已验证，原生与浏览器/视觉缺口另列。 |
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
