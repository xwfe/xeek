# 能力状态与平台矩阵

日期：2026-10-16，范围更新：2026-11-21。任务：K001。状态：**REVIEW**。

**当前所有能力在所有平台上都是“未实现”**——仓库里还没有应用代码。下面的矩阵写的是“平台允许什么、前提是什么”，不是 keex 已经做到什么。

## 0. 怎么用

- 界面、设置页、文档提到任何能力时，只能用 §1 的六种状态之一。不要自造“已启用”“支持”“已连接”这类说不清的词。
- 当前路线为 Android/iOS/macOS/Windows 与独立 Web（[ADR-0008](0008-nsh-unified-clients.md)）。§2 是移动，§3 区分当前桌面资料能力与后续增强，Linux 仍为资料；§4 是 Web。框架最低版本不等于 keex 的 API/发行支持下限，K090–K094 分别验证。
- 一项能力做完、测完，在本文件对应格子写上证据文件链接。没有证据链接的格子，一律视为“未实现”。

## 1. 六种状态

判定顺序从上往下，命中就停：

| 状态 | 意思 | 怎么判定 | 界面显示 | 开关 |
| --- | --- | --- | --- | --- |
| 不支持 | 平台没有这种系统能力，或 keex 明确决定不在该平台做，或这台设备达不到 §2 的前提 | 按 §2 的前提做确定性检测：平台、系统版本、硬件（如有没有安全硬件）。这类检测结果是确定的，不存在“不确定” | 写原因和替代办法，例如“需要 iOS 17 或更高” | 不显示 |
| 未实现 | keex 计划做，当前版本还没有 | 当前构建不含这项实现 | “当前版本暂未提供” | 不显示 |
| 未检测 | 已实现，但还没在这台设备或这个服务上确认条件 | 运行时检测没跑完，或结果不确定 | “正在检查”或“无法确认：原因” | 不可打开 |
| 未配置 | 已实现、条件满足，用户还没开启或授权 | 检测通过，用户未启用 | 引导开启的入口 | 关 |
| 暂不可用 | 用户已开启，但现在条件不满足 | 已锁库、系统权限被撤、只读库、同步令牌过期、离线等 | 具体原因 + 怎么恢复 | 保持用户的设置，功能不生效 |
| 可用 | 以上全部满足 | 已实现 + 运行时检测通过 + 已开启 + 当前条件满足 | 正常 | 开 |

硬规则：

1. **“可用”只能来自运行时检测**。不能因为“编译目标是 iOS”或“服务商是 OneDrive”就标可用。
2. **结果不确定一律算“未检测”**。例如 WebDAV 服务器声称支持 ETag 但条件写入没实测通过，就是“未检测”，不是“可用”。
3. **“不支持”和“未实现”必须分开**。前者是平台限制或产品决定，后者是我们还没做。混在一起，用户会以为某个平台永远不能用，或者以为马上就能用。
4. **用户设置和实际状态分开存**。用户开了生物识别快速解锁，但系统里重新录入了指纹、快速解锁材料已失效，应显示“暂不可用：输入主密码后重新启用”，不能把开关拨回“关”——否则用户看不出为什么失效，也不知道怎么恢复。
5. **能力状态是“这台设备上这项功能”**。单条记录的“记录可识别 → 核心可使用 → 已启用系统提供者 → 远端已确认同步”是另一组状态，见 [ADR-0002 §1](0002-mobile-credentials.md)，两者不要混用。

拟定类型（契约，不代表代码已存在）：

```dart
enum CapabilityState { unsupported, notImplemented, unchecked, notConfigured, unavailable, available }

class CapabilityStatus {
  final CapabilityId id;
  final CapabilityState state;
  final CapabilityReason? reason; // 界面按它查中文文案，例如 osTooOld、noSecureHardware（不支持），vaultLocked、permissionRevoked（暂不可用）
  final DateTime? checkedAt;      // 最近一次运行时检测的时间；null 就是没检测过
}
```

## 2. 平台矩阵

格子里写平台前提（系统版本、权限、实现路径）。写“不支持”的格子就是“不支持”状态，其余格子当前都是“未实现”。版本号是 API 可用下限，不是 keex 的发布承诺；带「待核」的内容还没找到一手资料，实施任务必须先确认。

两端条件相同、不单列的能力：KDBX 读写（写入要等 G0 门槛）、生成器、TOTP/HOTP、导入导出、WebDAV/OneDrive 同步。同步在后台运行受系统限制，见 [ADR-0003 §5](0003-cloud-sync.md)。

SSH 代理、浏览器扩展填充、全局自动输入在 Android/iOS 上都是**不支持**：移动系统没有对应入口，填充走下表的系统接口。KeeAgent 条目只保证数据无损。

| 能力 | Android | iOS | 验证任务 |
| --- | --- | --- | --- |
| 打开外部库文件 | SAF + 持久化 URI 授权 | 文件选择器 + security-scoped URL；扩展能否访问需实测（[ADR-0002 §3](0002-mobile-credentials.md)） | K013 |
| 快速解锁 | Keystore 密钥要求 `AUTH_BIOMETRIC_STRONG`、经 `CryptoObject` 使用；`KeyInfo.getSecurityLevel()`（API 31+，旧版回退已弃用的 `isInsideSecureHardware()`）显示不在 TEE/StrongBox 里的设备**不支持**（[THREAT_MODEL.md](THREAT_MODEL.md) T2） | data protection keychain + `ThisDeviceOnly` + Face ID/Touch ID，`.biometryCurrentSet` | K018 |
| 系统事件触发锁库（锁屏、切后台） | 有 | 有 | K019 |
| 剪贴板敏感标记 | Android 13+ `ClipDescription.EXTRA_IS_SENSITIVE`，隐藏剪贴板预览 | `UIPasteboard` 的 `.localOnly`（不进通用剪贴板）和 `.expirationDate` | K019 |
| 截图/录屏防护 | `FLAG_SECURE` 阻止截图和不安全显示；Android 14 可检测截图，15 可检测录屏 | **不能阻止截图**；可检测录屏并遮挡内容 | K019 |
| 任务预览遮挡 | `FLAG_SECURE` 或 `setRecentsScreenshotEnabled(false)`（Android 13+） | 进入后台前盖上遮罩视图 | K019 |
| 对普通无障碍服务隐藏秘密 | Android 14+ `setAccessibilityDataSensitive`：没声明为无障碍工具的服务既读不到也点不了被标记的控件（TalkBack 这类工具不受影响）。“是不是工具”由服务自己声明，靠 Play 审核和 Play Protect 约束，没有 Google 服务的机型基本没有这层约束。API 34 起，设了 `filterTouchesWhenObscured` 的控件在默认的 AUTO 模式下自动算敏感（AOSP android14 `View.java` 原话 “Views that set filterTouchesWhenObscured default to accessibilityDataSensitive”）；Google 2025-12 博客把它当 Android 16 的防护介绍，是博客不严谨，不是版本差异。NSH/宿主是否逐控件正确映射须 K092/K019 真机实测，不能沿用 Flutter 结果 | 不适用：第三方 App 不能像 Android 那样读取别的 App 的界面 | K019 |
| 防悬浮窗诱导点击 | `filterTouchesWhenObscured`；Android 12+ `setHideOverlayWindows(true)` 隐藏其他应用的悬浮窗（需 `HIDE_OVERLAY_WINDOWS` 权限）。无障碍服务自己的覆盖层不在隐藏范围（AOSP 源码只隐藏系统悬浮窗类型和 Toast，见 THREAT_MODEL），K019 真机确认 | 不适用：系统不允许第三方悬浮窗 | K019 |
| 主密码输入不经第三方输入法 | **不支持**：不能强制使用系统输入法；`IME_FLAG_NO_PERSONALIZED_LEARNING` 只防输入法“学习”，不防恶意输入法 | 安全文本框上系统强制使用系统键盘。另可在整个 App 里禁用第三方键盘（`application(_:shouldAllowExtensionPointIdentifier:)` 拒绝 `.keyboard`），代价是用户的输入法在 keex 里都不能用，只做可选项 | K019 |
| 系统密码自动填充 | AutofillService API 26+；键盘内候选 API 30+；API 34+ 另有 Credential Provider | 凭据提供者扩展，iOS 12+；产品基线 iOS 17+（ADR-0002） | K007、K008、K048、K049 |
| 系统通行密钥提供者 | API 34+ `CredentialProviderService` | iOS 17+ | K007、K008、K052、K053 |
| 系统动态口令填充 | 没有和 iOS 对等的入口；Autofill 遇到标了验证码提示的字段时尽力填充，不宣称对等（ADR-0002） | iOS 18+，增强项 | M22 |
| 管理器间凭据交换 | Jetpack Credentials Transfer：Android 8+、仅同设备、CXF，2026-10 为 1.0.0-beta01 | iOS 26+ | M23 |

## 3. 桌面资料客户端与后续增强

macOS/Windows 的前五行基础能力进入 K092/K095/K096；全部仍是未实现目标或明确不支持。SSH、系统凭据/浏览器提供者、自动输入与凭据交换仍属后续增强；Linux 整列仍为后续资料。下表 API 依据核对于 2026-10，NSH/宿主需按目标系统版本重验，不能将框架“原生控件”当安全保证。

| 能力 | macOS | Windows | Linux | 参考任务 |
| --- | --- | --- | --- | --- |
| 打开外部库文件 | 沙盒内用 security-scoped bookmark | 普通文件路径 | 普通文件路径；Flatpak 内走文件选择门户 | K092/K095/K096 |
| 快速解锁 | data protection keychain + `ThisDeviceOnly` + Touch ID，`.biometryCurrentSet` | Windows Hello，必须有 TPM 支撑；没有 TPM 或只能用 DPAPI 时**不支持**。能否禁止 PIN 回退待实测 | **不支持**：Secret Service 只是软件封装，强度等于登录密码。要改成“带警示提供”，先改 ACCEPTANCE AC-SECRET 并复核 | K092/K095/K096 |
| 系统事件触发锁库（锁屏、休眠） | 有系统通知 | 有系统通知 | 取决于桌面环境和 logind，没有统一信号 | K092/K095/K096 |
| 剪贴板敏感标记 | `prepareForNewContents(with: .currentHostOnly)`（macOS 10.12+）让内容不进通用剪贴板；“敏感内容”没有系统级标记，只有 `org.nspasteboard.ConcealedType`/`TransientType` 约定，剪贴板工具自愿遵守 | 写入 `ExcludeClipboardContentFromMonitorProcessing`、`CanIncludeInClipboardHistory`=0、`CanUploadToCloudClipboard`=0 格式，或用 WinRT `ClipboardContentOptions` | KDE Klipper 识别 `x-kde-passwordManagerHint=secret`；其他桌面没有统一约定 | K092/K095/K096 |
| 截图/录屏防护 | **不支持**：`NSWindow.sharingType = .none` 对 ScreenCaptureKit 不可靠（开发者论坛报告，Apple 无正式说明），可以设置但不宣称 | `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`，Windows 10 2004+ | **不支持**：X11 无法阻止，Wayland 由合成器决定 | K092/K095/K096 |
| SSH 代理 | Unix socket + `SSH_AUTH_SOCK` | OpenSSH 命名管道 `\\.\pipe\openssh-ssh-agent`；和系统 ssh-agent 服务怎么共存待实验 | Unix socket + `SSH_AUTH_SOCK` | K005、K006 |
| 系统密码自动填充 | 凭据提供者扩展，macOS 11+ | **不支持**系统级；走浏览器扩展 | **不支持**系统级；走浏览器扩展 | — |
| 系统通行密钥提供者 | macOS 14+ | Windows 11 第三方 passkey 插件模型，有微软官方文档和示例；用户在“设置 > 账户 > 通行密钥 > 高级选项”启用。哪个 Windows 版本起对普通用户正式推送「待核」（二手报道称 2025-11） | **不支持**系统级；走浏览器扩展 | K054 |
| 系统动态口令填充 | macOS 15+ | **不支持** | **不支持** | — |
| 浏览器扩展填充 | Chromium/Firefox + native messaging | 同左 | 同左 | K050、K054 |
| 桌面全局自动输入 | 需“辅助功能”授权 | 无法向管理员权限的窗口输入 | X11 可以；Wayland 受合成器限制 | K065 |
| 管理器间凭据交换 | macOS 26+ | **不支持**：未见系统级接口 | **不支持** | — |

## 4. Web与个人资料增量（目标，全部未实现或明确不支持）

Web是当前计划中的独立客户端，不是 macOS/Windows 原生客户端的替代名称。以下“目标”不是可用声明；上线时逐浏览器版本、部署来源与文件/同步路径填写运行时能力和证据，未测不推定支持。原生手机构建与HTML原型检查不能算Web证据。

| 能力 | 四原生端增量 | Web首版 | 验证任务 |
| --- | --- | --- | --- |
| 金融/通信/文档类型、关系与维护规则 | 未实现，复用会话/KDBX | 未实现，相同schema和业务语义 | K068/K073–K080/K085 |
| KDBX解锁、编辑、导出 | 原有G0–G5门槛 | 未实现；浏览器writer/文件/恢复需GW0–GW2，不降低KDF | K070/K081/K082 |
| 本机保存 | 原生文件provider逐项验收 | 文件回读、可选密文缓存、显式下载分别判断，不能合并为一个“已保存” | K071/K082 |
| 双云同步 | 原计划WebDAV/OneDrive同阶段 | 未实现；浏览器CORS/SPA授权/CAS/CSP允许源独立核验 | K072/K084 |
| 资料搜索与关联索引 | 解锁后内存索引 | 未实现；不落明文索引/搜索词，不写URL | K073/K080/K085 |
| 附件预览/导出 | 受控预览和显式外部分享 | 未实现；不执行同源活动内容，类型/容量/权限不足则拒绝或显式导出 | K024/K076/K085/K088 |
| 应用内待办 | 未实现 | 未实现，仅打开并解锁时计算 | K077/K078/K085 |
| 已关闭应用的通知 | 移动/桌面各验 OS 通用通知，权限/退出/调度限制明示 | 首版不支持关页后提醒；不提供假开关 | K078/K095 |
| 系统级快速解锁 | 按§2/§3安全硬件前提与 K092/K095 实测 | 首版不支持；不以网页登录/短PIN替代库密钥 | K018/K081 |
| 系统填充、跨网站Passkey提供者 | 移动按§2；桌面 provider 仍后续 | 不支持；管理/保留库中记录不等于提供者 | K048/K049/K052/K053 |
| SSH Agent与原生eSIM安装 | 手机不作通用SSH代理、桌面SSH后续；eSIM安装不在本轮范围 | 不支持 | ADR-0006/0007/0008 |
| 重新加载后的离线使用 | 本地文件优先 | 后续能力；需静态包缓存/安装路径另验，首个发布不依赖PWA | K071/K081/K088 |

Web未知条件先为“未检测”，确定当前浏览器/部署不支持时说明具体路径及替代方式，不把单一浏览器限制写成永久全平台限制。资料状态、机构状态（手工记录）、保存状态、同步状态与能力状态分开，不使用一个“正常”徽章替代五个维度。

新增依据见 [研究PV01–PV16](research/personal-vault-2026-10-16.md)；范围与残余风险见 THREAT_MODEL T15/T16。

## 5. 原有平台依据

核对日期 2026-10-16。带「待核」的内容没有一手资料支撑。

- Apple：[Passkey 列表入口](https://developer.apple.com/documentation/authenticationservices/ascredentialproviderviewcontroller/preparecredentiallist(for:requestparameters:))（iOS 17 / macOS 14）；[动态口令列表入口](https://developer.apple.com/documentation/authenticationservices/ascredentialproviderviewcontroller/prepareonetimecodecredentiallist(for:))（iOS 18 / macOS 15）；[currentHostOnly](https://developer.apple.com/documentation/appkit/nspasteboard/contentsoptions/currenthostonly)（macOS 10.12+，内容只留本机）；[sharingType 与 ScreenCaptureKit 的论坛报告](https://developer.apple.com/forums/thread/808016)。
- Android：[安全处理剪贴板](https://developer.android.com/privacy-and-security/risks/secure-clipboard-handling)；[截图检测](https://developer.android.com/about/versions/14/features/screenshot-detection)；[API 34 的 View 变更（含 `setAccessibilityDataSensitive`）](https://developer.android.com/sdk/api_diff/34/changes/android.view.View)；[保护敏感 Activity（含 `HIDE_OVERLAY_WINDOWS`）](https://developer.android.com/security/fraud-prevention/activities)；[Android 开发者博客 2025-12：用 accessibilityDataSensitive 阻止恶意软件窥探](https://android-developers.googleblog.com/2025/12/enhancing-android-security-stop-malware.html)（读和操作都拦、`isAccessibilityTool` 的 Play 约束）。
- Windows：[剪贴板格式](https://learn.microsoft.com/windows/win32/dataxchg/clipboard-formats)；[ClipboardContentOptions](https://learn.microsoft.com/uwp/api/windows.applicationmodel.datatransfer.clipboardcontentoptions)；[Plugin passkey manager support](https://learn.microsoft.com/windows/apps/develop/security/third-party) 与 [PasskeyManager 示例](https://github.com/microsoft/Windows-classic-samples/tree/main/Samples/PasskeyManager)；正式推送时间只有二手报道。
