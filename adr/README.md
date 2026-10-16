# 架构与实施资料

更新：2026-10-16。

| 文件 | 用途 |
| --- | --- |
| [0001-flutter-kdbx-architecture.md](0001-flutter-kdbx-architecture.md) | 已确定的架构边界与需要实验裁决的选型 |
| [0002-mobile-credentials.md](0002-mobile-credentials.md) | iOS/Android提供者、原生扩展、索引与共享授权 |
| [0003-cloud-sync.md](0003-cloud-sync.md) | WebDAV/OneDrive权限、最终条件提交、冲突与后台 |
| [0004-kdbx-advanced-passkeys.md](0004-kdbx-advanced-passkeys.md) | 高级字段、附件池、历史、KPEX映射与Passkey签名 |
| [0005-mobile-first-scope.md](0005-mobile-first-scope.md) | 当前只做 iOS/Android；桌面端留给未来 Rust 应用，桌面资料索引 |
| [MOBILE_SYNC_TASKS.md](MOBILE_SYNC_TASKS.md) | 对应主任务的24项专项实施子任务 |
| [research/mobile-sync-2026-10-12.md](research/mobile-sync-2026-10-12.md) | Monica/Bitwarden等源码证据、官方资料与研究限制 |
| [design/IOS_DESIGN.md](design/IOS_DESIGN.md) | iOS专项页面、状态与Flutter/原生交接 |
| [design/BITWARDEN_MOBILE_REFERENCE.md](design/BITWARDEN_MOBILE_REFERENCE.md) | 移动UI/功能取舍与U01–U08验收细化 |
| [THREAT_MODEL.md](THREAT_MODEL.md) | K001：要防谁、防到什么程度、锁库语义；功能和文案只能承诺这里写的 |
| [CAPABILITIES.md](CAPABILITIES.md) | K001：能力六种状态的判定规则与五端平台前置条件 |
| [REAL_DATA_RULES.md](REAL_DATA_RULES.md) | K001：什么算真实数据、合成数据怎么造、真实库分级接入、泄露处理 |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | 阶段、发布门槛、关键依赖与首批行动 |
| [TASKS.md](TASKS.md) | 可独立领取的任务、交付物和验收标准 |
| [ACCEPTANCE.md](ACCEPTANCE.md) | 兼容性、安全、原生功能、同步与性能测试 |
| [RESEARCH.md](RESEARCH.md) | 官方资料、社区复用点与限制 |
| [STATUS.md](STATUS.md) | 实际完成内容、执行证据与未完成事项 |
| [design/README.md](design/README.md) | 中文设计基准与原稿修改对照 |

`stitch_` 是输入材料，不是架构事实来源。界面出现的安全徽章、网络节点、算法参数或“已连接”不等于相应能力已实现。
