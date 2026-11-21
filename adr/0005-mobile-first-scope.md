# ADR-0005：移动优先的历史范围决策（已部分取代）

日期：2026-10-16。状态：**历史决策，当前客户端范围以 ADR-0008 为准**。本文件部分取代 [ADR-0001](0001-flutter-kdbx-architecture.md) 中涉及桌面端的内容。

**同日后续决策**：[ADR-0006](0006-personal-data-vault.md) 扩展个人数据保险柜，[ADR-0007](0007-web-vault-client.md) 将 Web 提升为当前独立验收路线，部分取代本文的“只有移动端”和 Web 后续安排；原生桌面仍留给未来 Rust 应用，其余边界不变。

**2026-11-21 替代决定**：[ADR-0008](0008-nsh-unified-clients.md) 将 macOS/Windows 资料客户端纳入当前路线，四个原生端以 NSH + TSX / Rust 为目标，Web 保留独立验收。下文“只做移动端”“桌面留未来”“Flutter”及对应发布/标注规则是历史记录，不再指挥当前实施；Linux、SSH 代理、浏览器扩展、全局自动输入和 CLI 仍为后续。现行任务和阶段见 [TASKS](TASKS.md) 与 [IMPLEMENTATION_PLAN](IMPLEMENTATION_PLAN.md)。

## 原决定

- **当前原生交付范围为 iOS 和 Android**（含平板）。Flutter 做主界面，系统扩展用 Swift/Kotlin，共享核心仍按 K009 选型。新增 Web 按 ADR-0007 单独验收。
- **macOS、Windows、Linux 不在当前交付范围**。未来另做桌面应用，用 Rust 开发。现有桌面资料原地保留并加标注，不删除、不再扩写。
- KeePass、KeePassXC 等桌面客户端仍是兼容性测试的**参考客户端**——它们是测试工具，不是 keex 的交付平台。K002 用 `keepassxc-cli` 生成样本不受影响。

## 对现有计划的影响

| 内容 | 现在怎么处理 |
| --- | --- |
| Flutter 五端 | 只做 Android、iOS；K004、K010、K056 的“五端”改为两端 |
| SSH | 移动端不做代理（ADR-0001 本来就定了“不作通用系统代理”）。**KeeAgent 数据仍须无损**：用户的库可能在桌面 KeePass + KeeAgent 里用，keex 手机端编辑后不能把它弄坏，所以 K042（字段/附件无损）、K043（密钥解析，验收是公钥和指纹与 `ssh-keygen` 一致）留在当前范围。代理和签名（K005、K006、K044–K047、K063）归桌面，签名的 OpenSSH 验签在 K044 |
| 桌面专属功能 | 浏览器扩展填充（K050）、桌面浏览器 Passkey（K054）、全局自动输入（K065）、CLI（K067）归桌面 |
| 任务依赖 | K009 不再等 K005/K006；K055 不再等 K047/K054。任务编号不变，桌面任务在 [TASKS.md](TASKS.md) 的优先级栏标“桌面” |
| 共享核心选型 | K009 仍按 G0 证据裁决 Rust 还是 Dart。新增一个考量：Rust 核心未来可被桌面应用直接复用，Dart 实现不行。这是加分项，不是免除无损门槛的理由 |
| 发布层级 | 个人试用版 = Android + iOS；正式版 = 移动版。见 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) |
| 平台矩阵、威胁模型、验收 | 桌面列、桌面条目原处保留并标注。标注写法：TASKS 优先级栏写“桌面”；THREAT_MODEL、ACCEPTANCE 用【桌面】；其余文档写“未来桌面”。三种写法意思一样。威胁模型补充手机上恶意 App 的部分 |
| Web/小程序（K066） | 后续由 ADR-0007 拆分：Web 进入 K070–K089 的对应实验/实现任务；K066 只保留小程序后续受限研究。二者都不是原生桌面 |
| 平板宽屏 | 不受影响。五项导航在宽屏仍用同序侧栏，验收宽度从 1440 改为 1024（平板横屏） |

## 桌面资料在哪

给未来的 Rust 桌面应用用。这些是 2026-10 的方案和判断，没有一项实测过：

- [ADR-0001](0001-flutter-kdbx-architecture.md) §2 分层图里的“桌面”和 agent-core 两行、§6 SSH Agent/KeeAgent、§7 桌面浏览器填充段、§9 的桌面三列。
- [THREAT_MODEL.md](THREAT_MODEL.md) T4 的桌面各行与桌面承诺、T14 SSH 代理转发、§5 锁库表的 SSH 行。
- [CAPABILITIES.md](CAPABILITIES.md) §3 未来桌面矩阵。
- [ACCEPTANCE.md](ACCEPTANCE.md) AC-SSH，以及 AC-CREDENTIAL 里浏览器扩展与桌面桥接一句。
- [TASKS.md](TASKS.md) 中标“桌面”的任务。
- [RESEARCH.md](RESEARCH.md) S05（KeeAgent）、S09（OpenSSH 代理限制）。
- 中文交互原型 `adr/design/zh-CN/` 的 1440 宽布局。

## 将来启动桌面端时

先写新的 ADR，至少定下：桌面 UI 用什么做；和移动端共享哪些核心库；桌面威胁模型按当时的系统版本复测。上面的资料只能当起点，不能当已验证的结论——尤其 T4 里各桌面系统的进程隔离判断，系统升级后很可能变。
