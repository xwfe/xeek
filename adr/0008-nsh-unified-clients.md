# ADR-0008：NSH 主界面与共享 Rust 核心的多端路线

日期：2026-11-21。状态：**目标路线已确定；NSH 迁移与各端交付尚待实验和独立验收**。

本决策部分取代 [ADR-0001](0001-flutter-kdbx-architecture.md)、[ADR-0005](0005-mobile-first-scope.md)、[ADR-0007](0007-web-vault-client.md) 的 UI 技术和桌面交付安排。其 KDBX、安全、原生凭据及 Web 独立验收约定继续有效。任务状态唯一入口是 [TASKS.md](TASKS.md)，进展与历史记录见 [STATUS.md](STATUS.md)。

## 1. 决定与原因

采用 **NSH + TSX 主界面 + 共享 Rust 核心**作为 Android、iOS、macOS、Windows 的目标路线；Web 继续作为正式客户端目标，独立验证 NSH HTML/WASM 与现有 Worker 核心的组合。

NSH 官方已有四种原生后端、混合 Rust/TSX 入口和 Web 后端，值得用现有合成样本验证。[N1][N2] 这能让界面开发使用 TypeScript，并保留 Rust 在数据、会话和兼容性上的积累；不能据此推断四端功能齐备、性能达标或秘密隔离可靠。

NSH 的 TSX 使用自身组件、signals 和编译器，原生端有 QuickJS，浏览器使用浏览器 JS 引擎；它不是 React/DOM 运行时。复用 TypeScript 类型和业务契约，不承诺直接搬 React 组件库；Flutter/ForUI 组件需重新实现。[N2][N3]

**保持不变：**

- keex 是个人数据保险柜；五项导航仍为“密码、验证、证件、银行、设置”，窄屏底栏、宽屏同序侧栏。
- KDBX 仍是唯一权威库；密码、银行/虚拟卡、金融账户、证件、SIM/eSIM、关系和维护规则沿用既有 schema。
- writer 由 K009 和既有证据裁决；现有 Rust 补丁不是因 UI 换型而获准生产。
- K007/K008 原生提供者实验、G0–G5、GV、GW 与 [真实数据规则](REAL_DATA_RULES.md) 继续生效。
- 保留 Flutter、ForUI、Dart 候选和全部历史证据；停止扩大正式 Flutter UI，不删除成果或重置旧任务进度。

## 2. 平台与功能范围

| 客户端 | 本轮路线 | 单独验证的边界 |
| --- | --- | --- |
| Android | NSH 主 UI + Kotlin 平台与凭据服务 + Rust | 输入、后台/进程、Keystore、文件 provider、剪贴板、签名包 |
| iOS | NSH 主 UI + Swift 平台与凭据扩展 + Rust | 输入、扩展预算、Keychain/App Group、文件授权、签名与真机 |
| macOS | NSH 主 UI + Rust 核心与必要原生适配 | 多窗口、系统锁屏、Keychain/本地认证、文件授权、签名/公证 |
| Windows | NSH 主 UI + Rust 核心与必要原生适配 | 多窗口、会话锁定、设备保护/快速解锁、文件事务、签名安装 |
| Web | NSH HTML/WASM 候选 + 现有 Rust WASM Worker | CSP、Worker 生命周期、密文缓存、文件保存、双云授权、GW |
| Linux / 小程序 | 继续后续范围 | 不因 NSH 提供后端便宣称支持 |

macOS/Windows 本轮加入的是个人资料客户端：管理同一库、搜索、编辑、附件、关系、维护事项、备份与同步。SSH Agent、浏览器扩展、桌面 Passkey 提供者、全局自动输入和 CLI 继续原后续任务；保留 KeeAgent 数据的义务不变。

官方当前运行下限为 iOS 15、Android 8/API 26、macOS 14、Windows 10 1809。[N1] 这是 NSH 下限；keex 的最低版本须同时满足所用系统 API、构建和设备验证。特别是 Android 14+ CredentialProviderService 与 Apple 凭据扩展 API availability，不由 UI 下限替代。[N7]

四端目标不等于同日可发。缺设备、SDK、证书或账号时明确记录“未验证/阻塞”；模拟器、交叉编译和临时签名均不能冒充发行验收。

## 3. 共享与隔离边界

| 层 | 承担职责 | 不承担职责 |
| --- | --- | --- |
| 共享 Rust 核心 | KDBX、schema、关系/规则、会话、OTP/签名策略、保存/合并语义 | 依赖 NSH、QuickJS、组件树或平台窗口 |
| NSH Rust 适配层 | 将核心能力映射为类型化 UI 调用，调度、取消与结果转换 | 另写一套 writer、密码策略或保存真相 |
| TSX 主界面 | 导航、表单、受限摘要、搜索结果、授权提示与准确状态 | 持有整库明文、长期主密钥，直接操作数据库内部对象 |
| Swift / Kotlin | 凭据提供者、系统认证、文件授权、平台生命周期 | 依赖主 UI 或 QuickJS 存活才能处理系统请求 |
| Web 适配 | Worker 消息、浏览器 IO/缓存、授权和部署策略 | 把原生文件/安全存储保证直接投射到浏览器 |

原生主 UI 可通过 NSH 的 Rust 模块或受限宿主桥调用核心；K091 选择最小可用绑定，避免再绕经 Dart。现有 C ABI/JNI 是复用基础，但它们目前只是合成实验接口，生产句柄、所有权与错误边界仍须完善。

Swift Credential Provider Extension 和 Kotlin Autofill/Credential Provider 必须能在主 UI 未启动、已退出时独立调用同一 Rust 核心。普通 Input 自动完成提示、AuthSession OAuth 会话不等于系统凭据提供者；NSH 壳不能替代扩展 target、权限、调用方验证与冷启动实验。[N7]

共享 UI 也不统一平台权限承诺：安全存储只保护经审查的设备授权材料，后台锁定、文件 provider 和多窗口按端实现；不以“能创建窗口”推断多窗口同时编辑安全。

## 4. 秘密、错误与生命周期

- 核心接口按用途返回摘要或单个字段；列表分页，只返回该视图所需数据。编辑提交字段补丁，不传整库 JSON。
- 会话引用带 VaultBindingId、epoch/generation 与请求身份；这些是校验输入，不是 UI 自报即可获得的权限。
- 解锁、读秘密、复制、签名、保存等敏感操作在开始和结果交付前检查会话；切库、锁库、撤权后丢弃旧异步回调。
- 锁库撤销核心权限并释放 UI 状态；所有窗口、扩展/进程及在途请求一起失效。遮罩、关页面或清空 signal 不能替代撤权。
- Rust 返回稳定错误码与脱敏信息；取消、错误密码、权限失效、预算超限、存储冲突可区分。不得把原始字段或完整核心错误对象写入日志。
- C ABI/JNI 不让 panic 越界；沿用现有 KDF 预算检查与失败策略。OOM/abort 不承诺可捕获；NSH 线程/VM 崩溃恢复另测。
- KDF、解析和保存不阻塞 UI；测取消、卡死与进程终止后的状态。不得只用“调用是 async”证明后台执行或安全取消。

**主密码输入是明确风险点。** 若值经过 NSH Input → TS/QuickJS → Rust，就可能产生多个不可保证擦除的副本；缩短留存、禁用调试/日志，不宣传 JS 字符串可安全清零。

K092 对比两条路径：受控 TSX 输入；原生安全输入视图直接交给受限核心接口。后者只是减少 JS 接触的候选，仍要验证 IME、自动更正、可访问性、系统截图/任务预览、回调、复制和内存生命周期，不能先声称已解决泄露。

复制优先核心到原生剪贴板适配，测试敏感标记、过期清理、锁库清理及系统间同步行为；只清除仍属于本应用的内容。NSH 普通剪贴板 API 不直接提供全部 keex 保证。[N5]

QuickJS 沙箱和 Rust 类型安全都不构成明文密码库对本进程恶意代码的隔离。Web Worker 也不能防同源恶意脚本；延续 ADR-0007 的浏览器信任边界。

## 5. 存储、能力与可信交付

NSH 的普通 Storage 仅用于经审查的非敏感显示偏好；**不得存主密码、解锁材料、明文条目、搜索索引或同步认证秘密**。其通用键值持久化不是密码库事务，也不是 Keychain/Keystore。[N5]

KDBX、加密快照、保存事务和恢复沿用现有核心与平台协议；不为适配 NSH 增建明文 SQLite/JSON 库。原生快解锁保留完整主密码回退，Windows/macOS 等差异以 K092 证据决定能力状态。

原生发布的 TSX/JS、Rust 核心、字体和图标随签名应用包交付；keex 不采用远端 TSX、脚本 OTA 或第三方插件执行。关闭发行调试入口，开发热更新只用于合成数据。

显式声明最小 capabilities，并在嵌入宿主设置同等或更窄的 grants；逐项验证 network、文件、剪贴板、openUrl、窗口和 host 方法。不要把“未配置”理解为默认拒绝。[N4]

宿主接口仅注册确需的方法，参数由 Rust/原生再次验证；不开放任意路径、任意执行、任意网络或 dump-vault。自定义原生组件仍是宿主可信代码，不能只靠 NSH capabilities 保护。[N4]

默认无外部字体、图标、遥测或 UI 资源请求；同步和授权网络通过经审查的 provider 与允许来源配置启用。附件与社区链接不能变成可执行 UI 或受信任资源源。

Web 继续固定版本自托管静态包、严格 CSP、同源资源和独立更新控制；K093 验证是否只需已有 WASM 放行，不能为 NSH 泛化开放 unsafe-eval。不新增长期保存主密码或同步令牌的浏览器方案。

安装包生成不等于发布成功：iOS 签名/权限、Android 签名、macOS Developer ID/公证与 Windows 代码签名分别留证；临时签名、未签名产物只标实验。[N6]

## 6. 复用代码与最小目录调整

| 现有位置 | 迁移处理 |
| --- | --- |
| `tests/wasm_core/src/core.rs` | 复用同一合成 Rust 逻辑，不复制成 NSH 专用 writer |
| `tests/wasm_core/src/native.rs`、`android.rs`、`web.rs` | 分别复用 C ABI、JNI、WASM 边界与反例，按新桥补测 |
| `tests/mobile/` | 复用 Swift/Kotlin 探针，补真正服务/扩展证据；探针不算 provider |
| `tests/flutter_bridge/`、`tests/forui_candidate/`、`tests/dart_candidate/` | 保留可复现对照与失败记录，不扩大正式 UI |
| `tests/fixtures/kdbx/`、`tests/kdbx_oracle/`、`tests/vault_domain/` | 沿用独立样本、语义 oracle 与领域契约 |
| `tests/web_storage/` | 复用浏览器驱动与存储/同步反例；NSH 页面接入后重测 |

拟新增实验仅放 `tests/nsh_candidate/`，包含最小 TSX 页面、Rust/宿主适配与复现说明；先接现有实验核心，不批量搬动通过的样本与证据。

生产落点沿用既有规划中的 `apps/keex/`、`crates/vault_core/`、`native/apple/`、`native/android/`，当前均不能据此写成已建成。GN 和对应核心裁决后才抽取正式模块；暂不为每个平台或每类资料创建一个 crate/服务。

领域、凭据、同步可先是核心内模块；只有实际依赖或进程边界需要时再拆。NSH 绑定留在 app/适配层，Rust 核心可继续被无 UI 测试、原生扩展与 WASM 使用。

## 7. 执行顺序与 GN 裁决

执行任务与依赖以 [TASKS.md](TASKS.md) 为准；这里限定各步的决策意义，不维护第二份任务状态。

1. **K090** 固定候选 NSH v0.6.1，锁完整 commit、CLI/运行时/绑定/依赖；核查许可证、最小能力和四端构建前提。
2. **K091** 运行四原生端 TSX + 现有 Rust 的合成纵向实验：打开/解锁、分页搜索、字段编辑、保存新副本、锁库；输出交给原有 oracle。
3. **K092** 验证四端敏感输入、后台/锁屏/多窗口/销毁回调、文件与快速解锁边界、安全剪贴板和签名包。
4. **K093** 独立验证 NSH Web + 现有 WASM Worker；覆盖中文输入、可访问性、解锁/锁库/重启、CSP/外联及原有浏览器反例。
5. **K094（GN）** 独立审查 K091/K092/K093 与 K007/K008 的证据，作 UI 迁移裁决；**不依赖生产 K010**。
6. GN 通过后按原生产前置进入相应客户端任务；桌面资料集成走 **K095**，桌面发布验收走 **K096**。

K091–K093 只授权合成实验。K091 可复用实验 writer 做往返以证明桥接正确，但 GN 不批准生产写入，也不替代 K009/G0 或 GV/GW。

### GN 必须回答的问题

| 问题 | 所需结论 |
| --- | --- |
| 可构建与可信交付 | 四原生端构建、实际运行、签名路径及资源边界有可复现记录；缺项明确阻塞 |
| 业务 UI 可用 | 五导航、列表/详情/表单、中文 IME、键盘与触控、读屏可访问性通过约定场景 |
| 核心没有分叉 | 同一核心/样本/oracle；既有字段、未知数据保留与拒写反例不退化 |
| 敏感生命周期 | 旧 epoch 回调无权显示/复制/保存；锁定和销毁覆盖窗口、进程与 Worker |
| 原生提供者独立 | K007/K008 证明不依赖主 UI/QuickJS，不拿普通输入控件替代系统能力 |
| Web 要求仍可完成 | K093 有浏览器可行路径与缺口；旧 GW 和双云验收保持独立 |
| 成本与依赖可接受 | 固定版本许可、补丁范围、平台维护成本与未解决故障可审查 |

GN 有未解决的硬性失败或缺失证据时不判通过；可以继续已具备条件的平台合成实验，不宣布四端迁移完成。修复不应静默扩大宿主权限或降级锁库、输入与保存约束。

本轮不设缺乏测量依据的性能数字。K091/K092 先用同一合成负载与旧实验对照记录启动、长列表、KDF、保存、峰值内存和响应性，再由 GN 审查是否满足用途。

如果候选失败，保留样本、核心、桥接结果和原因，修订选型决策后再恢复或更换 UI 路线；不维护两套长期生产 UI，也不把失败历史改为“未开始”。

## 8. 已有事实与尚欠证据

[K004](evidence/K004.md) 已证明 Android Flutter 主进程与独立 Kotlin 探针可调用同一 Rust 核心；Swift C ABI 在 Mac 有结果，iOS 只有编译链接。这些能降低重做成本，不能算 NSH 四端验证。

[K004](evidence/K004.md) 当前记录 iOS 按负责人要求暂停且资源缺失；本 ADR 不自动恢复真机/SDK条件，不变更该历史状态。K008/K092 缺 iOS 证据时 GN 仍不能通过。

[K070](evidence/K070.md) 已有浏览器 Rust/WASM 合成结果；Flutter/Safari Worker 重启停顿是对照中的未解决项。NSH 需独立复测，不预先声称换框架即可消失。

[ForUI 证据](evidence/K011_FORUI.md) 的导航、中文资源、输入与可访问性发现用于 NSH 场景设计；它不是新框架的现成组件或验收结果。

候选 v0.6.1 发布于 2026-11-20；v0.6.0 有能力、输入与平台 API 的 breaking changes，v0.6.1 仍在修复移动生命周期/键盘问题。[N8] 因此 K090 固定版本与依赖，升级另做影响检查；当前没有 keex 的 NSH 真机、签名发行或完整安全审计结论。

## 9. 官方依据

以下为 2026-11-21 核对的上游说明；实现时以 K090 锁定版本源码复核，不把滚动文档当成 keex 实测。

- [N1 平台与最低运行版本](https://nsh.dev/docs/platforms/)。
- [N2 Rust、TSX 与混合模式](https://nsh.dev/docs/rust/)。
- [N3 JSX 与组件模型](https://nsh.dev/docs/jsx-and-components/)。
- [N4 capabilities、宿主 grants 与原生组件边界](https://nsh.dev/docs/sandbox-and-capabilities/)。
- [N5 Storage、Clipboard 与宿主 API](https://nsh.dev/modules/nsh/)。
- [N6 平台打包与签名](https://nsh.dev/docs/packaging/)。
- N7 [Apple Credential Provider Extension](https://developer.apple.com/documentation/authenticationservices/ascredentialproviderviewcontroller)；[Android 凭据提供者](https://developer.android.com/identity/sign-in/credential-provider)。
- [N8 NSH v0.6.1 与 v0.6.0 发布说明](https://github.com/longbridge/nsh/releases)。
