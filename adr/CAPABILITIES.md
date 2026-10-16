# 能力状态与平台矩阵

日期：2026-10-16。任务：K001。状态：**REVIEW**。

**当前所有能力在所有平台上都是“未实现”**——仓库里还没有应用代码。下面的矩阵写的是“平台允许什么、前提是什么”，不是 keex 已经做到什么。

## 0. 怎么用

- 界面、设置页、文档提到任何能力时，只能用 §1 的六种状态之一。不要自造“已启用”“支持”“已连接”这类说不清的词。
- 某平台能不能做、前提是什么，查 §2。keex 打算在哪个阶段做，查 [ADR-0001 §9](0001-flutter-kdbx-architecture.md) 和 [TASKS.md](TASKS.md)。
- 一项能力做完、测完，在本文件对应格子写上证据文件链接。没有证据链接的格子，一律视为“未实现”。

## 1. 六种状态

判定顺序从上往下，命中就停：

| 状态 | 意思 | 怎么判定 | 界面显示 | 开关 |
| --- | --- | --- | --- | --- |
| 不支持 | 平台没有这种系统能力，或 keex 明确决定不在该平台做 | 查本文件 §2，不靠运行时猜 | 写原因和替代办法 | 不显示 |
| 未实现 | keex 计划做，当前版本还没有 | 当前构建不含这项实现 | “当前版本暂未提供” | 不显示 |
| 未检测 | 已实现，但还没在这台设备或这个服务上确认条件 | 运行时检测没跑完，或结果不确定 | “正在检查”或“无法确认：原因” | 不可打开 |
| 未配置 | 已实现、条件满足，用户还没开启或授权 | 检测通过，用户未启用 | 引导开启的入口 | 关 |
| 暂不可用 | 用户已开启，但现在条件不满足 | 已锁库、系统权限被撤、只读库、同步令牌过期、离线等 | 具体原因 + 怎么恢复 | 保持用户的设置，功能不生效 |
| 可用 | 以上全部满足 | 已实现 + 运行时检测通过 + 已开启 + 当前条件满足 | 正常 | 开 |

硬规则：

1. **“可用”只能来自运行时检测**。不能因为“编译目标是 iOS”或“服务商是 OneDrive”就标可用。
2. **结果不确定一律算“未检测”**。例如 WebDAV 服务器声称支持 ETag 但条件写入没实测通过，就是“未检测”，不是“可用”。
3. **“不支持”和“未实现”必须分开**。前者是平台限制或产品决定，后者是我们还没做。混在一起，用户会以为某个平台永远不能用，或者以为马上就能用。
4. **用户设置和实际状态分开存**。用户开了 SSH 代理、但库锁了，应显示“暂不可用：密码库已锁定”，不能把开关拨回“关”——否则解锁后用户还得重新打开，而且看不出为什么失效。
5. **能力状态是“这台设备上这项功能”**。单条记录的“记录可识别 → 核心可使用 → 已启用系统提供者 → 远端已确认同步”是另一组状态，见 [ADR-0002 §1](0002-mobile-credentials.md)，两者不要混用。

拟定类型（契约，不代表代码已存在）：

```dart
enum CapabilityState { unsupported, notImplemented, unchecked, notConfigured, unavailable, available }

class CapabilityStatus {
  final CapabilityId id;
  final CapabilityState state;
  final CapabilityReason? reason; // 界面按它查中文文案，例如 vaultLocked、osTooOld、permissionRevoked
  final DateTime? checkedAt;      // 最近一次运行时检测的时间；null 就是没检测过
}
```

## 2. 平台矩阵

格子里写平台前提（系统版本、权限、实现路径）。写“不支持”的格子就是“不支持”状态，其余格子当前都是“未实现”。版本号是 API 可用下限，不是 keex 的发布承诺；带「待核」的内容还没找到一手资料，实施任务必须先确认。

五端条件相同、不单列的能力：KDBX 读写（写入要等 G0 门槛）、生成器、TOTP/HOTP、导入导出、WebDAV/OneDrive 同步。同步在移动端后台运行受系统限制，见 [ADR-0003 §5](0003-cloud-sync.md)。

| 能力 | macOS | Windows | Linux | Android | iOS | 验证任务 |
| --- | --- | --- | --- | --- | --- | --- |
| 打开外部库文件 | 沙盒内用 security-scoped bookmark | 普通文件路径 | 普通文件路径；Flatpak 内走文件选择门户 | SAF + 持久化 URI 授权 | 文件选择器 + security-scoped URL；扩展能否访问需实测（[ADR-0002 §3](0002-mobile-credentials.md)） | K013 |
| 快速解锁 | data protection keychain + `ThisDeviceOnly` + Touch ID，`.biometryCurrentSet` | Windows Hello，必须有 TPM 支撑；没有 TPM 或只能用 DPAPI 时**不支持**。能否禁止 PIN 回退待 K018 | **不支持**：Secret Service 只是软件封装，强度等于登录密码（[THREAT_MODEL.md](THREAT_MODEL.md) T2）。要改成“带警示提供”，先改 ACCEPTANCE AC-SECRET 并复核，不由 K018 自行决定 | Keystore 密钥要求 `AUTH_BIOMETRIC_STRONG`、经 `CryptoObject` 使用；`KeyInfo` 显示不在安全硬件里的设备**不支持** | data protection keychain + `ThisDeviceOnly` + Face ID/Touch ID，`.biometryCurrentSet` | K018 |
| 系统事件触发锁库（锁屏、休眠、切后台） | 有系统通知 | 有系统通知 | 取决于桌面环境和 logind，没有统一信号 | 有 | 有 | K019 |
| 剪贴板敏感标记 | 无系统级标记；只有 `org.nspasteboard.ConcealedType`/`TransientType` 约定，剪贴板工具自愿遵守；能否排除通用剪贴板「待核」 | 写入 `ExcludeClipboardContentFromMonitorProcessing`、`CanIncludeInClipboardHistory`=0、`CanUploadToCloudClipboard`=0 格式，或用 WinRT `ClipboardContentOptions` | KDE Klipper 识别 `x-kde-passwordManagerHint=secret`；其他桌面没有统一约定 | Android 13+ `ClipDescription.EXTRA_IS_SENSITIVE`，隐藏剪贴板预览 | `UIPasteboard` 的 `.localOnly`（不进通用剪贴板）和 `.expirationDate` | K019 |
| 截图/录屏防护 | **不支持**：`NSWindow.sharingType = .none` 对 ScreenCaptureKit 不可靠（开发者论坛报告，Apple 无正式说明），可以设置但不宣称 | `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`，Windows 10 2004+ | **不支持**：X11 无法阻止，Wayland 由合成器决定 | `FLAG_SECURE` 阻止截图和不安全显示；Android 14 可检测截图，15 可检测录屏 | **不能阻止截图**；可检测录屏并遮挡内容 | K019 |
| 任务预览遮挡 | 不适用 | 不适用 | 不适用 | `FLAG_SECURE` 或 `setRecentsScreenshotEnabled(false)`（Android 13+） | 进入后台前盖上遮罩视图 | K019 |
| SSH 代理 | Unix socket + `SSH_AUTH_SOCK` | OpenSSH 命名管道 `\\.\pipe\openssh-ssh-agent`；和系统 ssh-agent 服务怎么共存待 K006 | Unix socket + `SSH_AUTH_SOCK` | **不支持**：不作通用系统代理 | **不支持**：同左 | K005、K006 |
| 系统密码自动填充 | 凭据提供者扩展，macOS 11+ | **不支持**系统级；走浏览器扩展 | **不支持**系统级；走浏览器扩展 | AutofillService API 26+；键盘内候选 API 30+；API 34+ 另有 Credential Provider | 凭据提供者扩展，iOS 12+；产品基线 iOS 17+（ADR-0002） | K007、K008、K048、K049 |
| 系统通行密钥提供者 | macOS 14+；keex 首版先走浏览器路径（ADR-0001 §9） | Windows 11 第三方 passkey 插件「待核」：二手报道称 2025-11 起正式提供，未找到微软的开发文档 | **不支持**系统级；走浏览器扩展 | API 34+ `CredentialProviderService` | iOS 17+ | K007、K008、K052–K054 |
| 系统动态口令填充 | macOS 15+ | **不支持** | **不支持** | 没有对等的系统入口（ADR-0002） | iOS 18+，增强项 | M22 |
| 浏览器扩展填充 | Chromium/Firefox + native messaging | 同左 | 同左 | **不支持**：走系统填充 | **不支持**：走系统填充 | K050、K054 |
| 桌面全局自动输入 | 需“辅助功能”授权 | 无法向管理员权限的窗口输入 | X11 可以；Wayland 受合成器限制 | **不支持** | **不支持** | K065 |
| 管理器间凭据交换 | macOS 26+ | 待评估 | **不支持** | Credential Transfer「待核」 | iOS 26+ | M23 |

## 3. 依据

核对日期 2026-10-16。带「待核」的格子没有一手资料支撑。

- Apple：[Passkey 列表入口](https://developer.apple.com/documentation/authenticationservices/ascredentialproviderviewcontroller/preparecredentiallist(for:requestparameters:))（iOS 17 / macOS 14）；[动态口令列表入口](https://developer.apple.com/documentation/authenticationservices/ascredentialproviderviewcontroller/prepareonetimecodecredentiallist(for:))（iOS 18 / macOS 15）；[sharingType 与 ScreenCaptureKit 的论坛报告](https://developer.apple.com/forums/thread/808016)。
- Android：[安全处理剪贴板](https://developer.android.com/privacy-and-security/risks/secure-clipboard-handling)；[截图检测](https://developer.android.com/about/versions/14/features/screenshot-detection)。
- Windows：[剪贴板格式](https://learn.microsoft.com/windows/win32/dataxchg/clipboard-formats)；[ClipboardContentOptions](https://learn.microsoft.com/uwp/api/windows.applicationmodel.datatransfer.clipboardcontentoptions)；第三方 passkey 插件只有[微软 2024-10 的公告](https://blogs.windows.com/windowsdeveloper/2024/10/08/passkeys-on-windows-authenticate-seamlessly-with-passkey-providers/)和二手报道。
