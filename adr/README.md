# 架构与实施资料

更新：2026-11-21。

| 文件 | 用途 |
| --- | --- |
| [0001-flutter-kdbx-architecture.md](0001-flutter-kdbx-architecture.md) | KDBX 安全架构与历史 Flutter 选型；客户端方向以 ADR-0008 为准 |
| [0002-mobile-credentials.md](0002-mobile-credentials.md) | iOS/Android提供者、原生扩展、索引与共享授权 |
| [0003-cloud-sync.md](0003-cloud-sync.md) | WebDAV/OneDrive权限、最终条件提交、冲突与后台 |
| [0004-kdbx-advanced-passkeys.md](0004-kdbx-advanced-passkeys.md) | 高级字段、附件池、历史、KPEX映射与Passkey签名 |
| [0005-mobile-first-scope.md](0005-mobile-first-scope.md) | 历史移动优先范围；Web 和 macOS/Windows 已由 ADR-0007/0008 纳入 |
| [0006-personal-data-vault.md](0006-personal-data-vault.md) | 个人数据保险柜定位、范围、五导航与并入现有架构的决策 |
| [0007-web-vault-client.md](0007-web-vault-client.md) | 独立 Web 客户端、浏览器保存/授权/同步和 GW0–GW2 门槛 |
| [0008-nsh-unified-clients.md](0008-nsh-unified-clients.md) | NSH/TSX + Rust 四原生端、独立 Web、迁移门槛 GN 与复用/退出边界 |
| [PERSONAL_VAULT_SPEC.md](PERSONAL_VAULT_SPEC.md) | 金融、通信、卡片、资料关系、维护规则及安全数据契约 |
| [K068_FIELD_CONTRACT.md](K068_FIELD_CONTRACT.md) | v1 字段编码、保护、业务原子组、关系和日期的可执行合成契约 |
| [PERSONAL_VAULT_PLAN.md](PERSONAL_VAULT_PLAN.md) | 增量阶段、K068–K089 任务细化、18 个验收场景及交接入口 |
| [research/personal-vault-2026-10-16.md](research/personal-vault-2026-10-16.md) | 16 组一手来源、复用边界与未核实事项 |
| [MOBILE_SYNC_TASKS.md](MOBILE_SYNC_TASKS.md) | 对应主任务的24项专项实施子任务 |
| [research/mobile-sync-2026-10-12.md](research/mobile-sync-2026-10-12.md) | Monica/Bitwarden等源码证据、官方资料与研究限制 |
| [design/IOS_DESIGN.md](design/IOS_DESIGN.md) | iOS专项页面、状态与主 UI/原生交接 |
| [design/BITWARDEN_MOBILE_REFERENCE.md](design/BITWARDEN_MOBILE_REFERENCE.md) | 移动UI/功能取舍与U01–U08验收细化 |
| [design/IOS_VALIDATION.md](design/IOS_VALIDATION.md) | iOS 交互原型的浏览器验证范围、命令与限制 |
| [THREAT_MODEL.md](THREAT_MODEL.md) | K001：要防谁、防到什么程度、锁库语义；功能和文案只能承诺这里写的 |
| [CAPABILITIES.md](CAPABILITIES.md) | K001：能力六种状态的判定规则，四原生端与 Web 前置条件，Linux/桌面增强另列后续 |
| [REAL_DATA_RULES.md](REAL_DATA_RULES.md) | K001：什么算真实数据、合成数据怎么造、真实库分级接入、泄露处理 |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | 阶段、发布门槛、关键依赖与首批行动 |
| [TASKS.md](TASKS.md) | 任务状态表，以及可独立领取的任务、交付物和验收标准 |
| [ACCEPTANCE.md](ACCEPTANCE.md) | 兼容性、安全、原生功能、同步与性能测试 |
| [RESEARCH.md](RESEARCH.md) | 官方资料、社区复用点与限制 |
| [STATUS.md](STATUS.md) | 现在在哪、卡在哪，以及各批工作的历史记录；任务状态以 TASKS 顶部为准 |
| [design/README.md](design/README.md) | 中文设计基准与原稿修改对照 |

## 证据（evidence/）

每项任务的执行记录：做了什么、怎么跑、结果、失败和没覆盖的范围。证据不等于任务已 DONE，状态以 [TASKS.md](TASKS.md) 为准。

| 文件 | 内容 |
| --- | --- |
| [evidence/D07.md](evidence/D07.md) | 2026-11-21 NSH 路线并入主计划、依赖/文档检查；不代表框架与安全验证通过 |
| [evidence/D06.md](evidence/D06.md) | 2026-10-16 方案落盘与文档静态验证，不是功能实现证据 |
| [evidence/K001.md](evidence/K001.md) | 威胁模型、能力矩阵、真实数据规则的交付与复核 |
| [evidence/K002.md](evidence/K002.md) | 合成黄金样本、只读 oracle 与语义比较器的交付、复核与修正 |
| [evidence/K002_ALGORITHMS.md](evidence/K002_ALGORITHMS.md) | 固定 kdbxweb 公开原件：Argon2 与外层 ChaCha20 读取 |
| [evidence/K002_LIBRARIES.md](evidence/K002_LIBRARIES.md) | Argon2d 后端与固定 keepass-rs 0.15.3 的参考保存实验 |
| [evidence/K002_RESOURCES.md](evidence/K002_RESOURCES.md) | 4.x 认证负载 278 案、资源边界与读取器修复 |
| [evidence/K002_SECRETS.md](evidence/K002_SECRETS.md) | 本地秘密与合成样本扫描 |
| [evidence/K002_HOOKS.md](evidence/K002_HOOKS.md) | 提交前扫描接入与真实提交验收 |
| [evidence/K003.md](evidence/K003.md) | keepass-rs 与 kdbx.dart 同样本读改写预实验，两者都未达无损 |
| [evidence/K003_MINIMAL.md](evidence/K003_MINIMAL.md) | 真实最小反例、直接上游版本探针、缺陷范围修正与修补成本 |
| [evidence/K003_RUST_PATCH.md](evidence/K003_RUST_PATCH.md) | 隔离 Rust 图标/历史补丁、重开引用修复与剩余生命周期缺口 |
| [evidence/K011_FORUI.md](evidence/K011_FORUI.md) | forui 0.27.7 界面预实验：读屏、200% 大字、中文输入、Web 严格 CSP 与中文字体自托管 |
| [evidence/K068.md](evidence/K068.md) | 字段契约 v1 的检查器与反例 |
| [evidence/K069.md](evidence/K069.md) | 个人资料合成库与参考客户端逐阶段对照 |
| [evidence/K069_MATRIX.md](evidence/K069_MATRIX.md) | 同 RP 多 Passkey、1k/10k 规模矩阵与本机资源记录 |

`stitch_` 是输入材料，不是架构事实来源。界面出现的安全徽章、网络节点、算法参数或“已连接”不等于相应能力已实现。
