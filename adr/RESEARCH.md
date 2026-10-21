# 调研依据与复用边界

本轮增补：[移动系统凭据、双云同步与高级KDBX调研](research/mobile-sync-2026-10-12.md)，包含用户指定项目的源码路径/快照、R01–R19资料和可复用边界。Sxx为原始总体来源；新的细化ADR使用Rxx。

核对日期：2026-10-12。以下是方案依据，不是依赖锁定或已验证兼容性清单。实施时重新确认版本、维护状态与许可证；保留具体 commit/版本和测试证据。只把官方规范/原项目作为关键技术依据。

| 编号 | 官方/原项目资料 | 支持的决策与限制 |
| --- | --- | --- |
| S01 | https://keepass.info/help/kb/kdbx.html | 最新 KDBX 4.1；内外层结构、KDF、AES-CBC/ChaCha20、HMAC、扩展字段、保护流。不能用 AES-GCM 替代仍称兼容 KDBX |
| S02 | https://docs.flutter.dev/reference/supported-platforms | Flutter 五端界面可行；不说明每项系统 API 全端同等可用 |
| S03 | https://docs.rs/keepass/latest/keepass/ | Rust 候选 keepass-rs，MIT；4.1 写入仍标 experimental。2026-10-22 更正：原记“0.13.17”已过时，K002/K003 实测固定 0.15.3；其保存只接受 KDBX 4.1（3.x/4.0 返回 UnsupportedVersion）。必须先做无损写入门槛 |
| S04 | https://pub.dev/packages/kdbx 和 https://github.com/authpass/kdbx.dart | Dart 对照实现；页面宣称 3.x/4.x，不等于所有 4.1/第三方字段无损。2026-10-22 补充：2.5.0（约 2026-08 发布）为 **GPL-3.0**；KDF 只认 Argon2d 与 AES-KDF，**不支持 Argon2id**，3.x 只认外层 AES；默认用 pointycastle 纯 Dart Argon2（README 所说“需 argon2 ffi”已不准确）；2.5.0 前保存不轮换 KDF 盐。实测见 [K003](evidence/K003.md) |
| S05 | https://github.com/dlech/KeeAgent 和 https://keeagent.readthedocs.io/en/latest/ | KeePass 插件与自有/外部代理模式；参考配置和 SSH 行为，不直接加载 .NET 插件 |
| S06 | https://developer.android.com/identity/sign-in/credential-provider | Android 14+ 密码管理器 provider API；与“使用其他管理器的 passkey 登录”的客户端 API 区分 |
| S07 | https://developer.apple.com/documentation/authenticationservices/ascredentialproviderviewcontroller/ | Apple 凭据扩展、密码/Passkey/OTP API 与 entitlement；按 API availability 和真机预算验收 |
| S08 | https://keepassxc.org/docs/KeePassXC_UserGuide | 密码管理器基础功能、浏览器 Passkey 集成及导入导出；导出 .passkey 可能为明文，不能自动云同步 |
| S09 | https://www.openssh.com/agent-restrict.html | 会话绑定与目的地约束；普通代理请求不能让 UI 可信推断目标主机 |
| S10 | https://flutter.dev/blog/progress-of-the-flutter-package-ecosystem 和 https://github.com/fzyzcjy/flutter_rust_bridge | Rust/Flutter 桥接复用入口；仍需验证原生扩展能不依赖 Flutter 引擎调用共享核心 |
| S11 | https://keepass.info/help/v2/sync.html | KeePass 条目合并、历史与删除记录；keex 的三方合并是拟定增强，不是既有 KeePass 实现的等同描述 |
| S12 | https://www.rfc-editor.org/rfc/rfc6238 和 https://www.rfc-editor.org/rfc/rfc4226 | TOTP/HOTP 的算法、参数与测试向量 |
| S13 | https://www.w3.org/TR/webauthn-3/ | WebAuthn 校验和数据语义；实施先确认规范状态及平台实现差异，不以“支持 WebAuthn”省略安全测试 |

## 复用策略

首先复用密码原语、KDBX 实现、系统凭据 API、成熟 SSH 编码/签名库；应用自己负责明确的会话状态、授权策略、中文体验、无损兼容和可验证的同步。不要重造密码学地基，也不要把多个未经核对的密码管理器源码拼接后宣称兼容。

AuthPass 用于 Flutter/KDBX 交互与库的对照；KeePass/KeePassXC/KeePassDX/KeeAgent 用于合成兼容样本与行为验证。引用代码前需核对每个仓库和文件的许可；当前方案未复制其应用实现。
