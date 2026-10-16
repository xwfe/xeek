# 移动系统凭据、同步与高级 KDBX 调研

核对日期：2026-10-12。范围：用户指定 Monica、Bitwarden iOS/Android，补充 KeePassXC、KeePassium、passkey-rs 与平台规范。**本轮为文档/选定源码阅读，没有构建参考项目、登录云账号或通过真实认证测试。默认分支快照不等于已发行稳定版本。**

## 1. 参考项目应分别解决什么问题

| 参考 | 实际核对/阅读范围 | 值得采用的边界 | 不照搬的部分 |
| --- | --- | --- | --- |
| Bitwarden iOS | CredentialProviderViewController 前240行，密码/Passkey/OTP路径及无交互分派 | 原生扩展按请求建立 context，交由服务/核心处理 | 账号服务器、vault模型、整套UI、原始错误日志策略 |
| Bitwarden Android | CredentialProviderService 全文件 | 服务薄、processor可测试、取消信号传递 | 整体同步协议和后端要求 |
| Monica Android | CredentialProviderService 前155行；KeePassDxPasskeyCodec 全文件；模式/字段搜索 | Android provider 接入、KDBX兼容 codec、模式区分、原生多语言 | Room/多后端作为权威源、非KDBX私有格式、可选键盘/辅助功能权限默认全开 |
| KeePassXC | EntryAttributes 前90行及 PasskeyUtils 相关字段搜索 | KPEX字段、旧客户端别名、每个凭据身份独立保留 | 将任意字段前缀直接等同可签名；把源码快照当稳定互通承诺 |
| KeePassium | 官方Passkey发布说明和AutoFill内存支持文档 | iOS凭据扩展现实限制、KDBX内Passkey路线 | 把某版经验内存值当所有iOS设备硬保证 |
| passkey-rs | 官方项目说明/模块划分 | 可评估的共享软件认证器、CredentialStore接口 | 未验证的算法、存储耐久性和平台桥接不能默认支持 |

没有直接复制上述实现代码。代码移植/链接前须检查目标版本、逐文件许可证、依赖与发行方式；开源或能在商店下载不等于可无条件复制到自己的 Flutter 应用。

## 2. 本轮改变原方案的结论

iOS 与 Android 同期设计、同期最小原生闭环；OneDrive 与 WebDAV 同处 P3。KDBX Advanced 不再只是“自定义字段以后补”：历史、附件引用、保护流和Passkey协议字段属于写入门槛。

两类“识别”分开：读取KDBX的字段解码，与系统候选索引/请求匹配。两类“成功”分开：本地持久化，与网站/远端接受。两类“同步”分开：KDBX多设备同步，与系统凭据交换的一次性迁移。

最主要未知量是 iOS 扩展在完整库/KDF/附件下的写入预算、共享核心的真实字段保留能力、OneDrive精确权限组合和最终提交CAS语义。后续POC为这些问题提供证据；不能用美化页面掩盖。

## 3. 可复核来源

R01 [Bitwarden iOS原生扩展](https://github.com/bitwarden/ios/blob/main/BitwardenAutoFillExtension/CredentialProviderViewController.swift)：本次文件blob SHA `17b156e4e435214dde26eb5309772e628103031a`，读取1–240行。记录的是文件内容哈希，不冒称仓库commit。查看17+Passkey、18+OTP与无交互路径。

R02 [Bitwarden Android薄服务](https://github.com/bitwarden/android/blob/243b9e790deb45b1adb4c1ed25210a454cb1aa8f/app/src/main/kotlin/com/x8bit/bitwarden/data/credentials/BitwardenCredentialProviderService.kt)：commit `243b9e790deb45b1adb4c1ed25210a454cb1aa8f`；blob `bc8a8ee6eb32f31a72d87f2fed9a28903a697f74`。服务将create/get/clear交给processor。

R03 [Android Credential Provider官方指南](https://developer.android.com/identity/sign-in/credential-provider)：区分provider与client；API34、两阶段请求、PendingIntent及调用方/相关origin边界。示例版本号不直接作为本项目依赖版本。

R04 Apple [Credential Provider](https://developer.apple.com/documentation/authenticationservices/ascredentialproviderviewcontroller)、[注册入口](https://developer.apple.com/documentation/authenticationservices/ascredentialproviderviewcontroller/prepareinterface%28forpasskeyregistration%3A%29)、[列表参数](https://developer.apple.com/documentation/authenticationservices/ascredentialproviderviewcontroller/preparecredentiallist%28for%3Arequestparameters%3A%29)。部分页面正文需JavaScript；函数可用性另以R01的实际availability标注和Apple视频交叉核对，实施需用目标SDK编译确认。

R05 [Apple WWDC24：Passkey升级与凭据管理器](https://developer.apple.com/videos/play/wwdc2024/10125/)：iOS18相关增强入口；条件升级不能等同任何情况下静默注册。

R06 [Apple条件注册入口](https://developer.apple.com/documentation/authenticationservices/ascredentialproviderviewcontroller/performwithoutuserinteractionifpossible%28passkeyregistration%3A%29)：无交互条件的设计依据，实际flag/API以SDK验证。

R07 KeePassium [AutoFill内存说明](https://support.keepassium.com/kb/autofill-memory/)、[2.0 Passkey和OTP说明](https://keepassium.com/blog/2024/12/keepassium-2.0/)：参考实现的能力与限制，不构成keex的测试结果。

R08 Monica commit `85e13fab88a51c2c6f01c5230ddf2ff8dc8b28ef`：
- [原生凭据服务](https://github.com/Monica-Pass/Monica/blob/85e13fab88a51c2c6f01c5230ddf2ff8dc8b28ef/Monica%20for%20Android/app/src/main/java/takagi/ru/monica/passkey/MonicaCredentialProviderService.kt)，blob `0ac2447de4c04c7d24abf57faba58c26dadd5d76`，读取1–155行。
- [KeePassDxPasskeyCodec](https://github.com/Monica-Pass/Monica/blob/85e13fab88a51c2c6f01c5230ddf2ff8dc8b28ef/Monica%20for%20Android/app/src/main/java/takagi/ru/monica/keepass/KeePassDxPasskeyCodec.kt)，blob `01949d51f03d720cf141e223c465986a182ddc87`，全文件：保护私钥/ID/handle字段，转换到兼容模式。识别/normalize规则仍需独立审查。

R09 [Microsoft App Folder](https://learn.microsoft.com/en-us/graph/onedrive-sharepoint-appfolder)：应用目录权限模型；不代表任意路径、任意租户和任意上传组合均已实测。

R10 [Graph Upload Session](https://learn.microsoft.com/en-us/graph/api/driveitem-createuploadsession?view=graph-rest-1.0)：会话创建条件、分片、完成、预授权URL和账号差异。最终CAS需用并发反例验证，不能只引用创建header。

R11 [Graph内容上传](https://learn.microsoft.com/en-us/graph/api/driveitem-put-content?view=graph-rest-1.0)：简单PUT的文档接口。未列出的If-Match语义不被当成已确认保证。

R12 [Microsoft官方身份样例](https://learn.microsoft.com/en-us/entra/identity-platform/sample-v2-code)：原生移动公共客户端的授权码/PKCE路径。应用注册、scope与重定向配置须正式准备，不在二进制里藏client secret。

R13 [RFC4918](https://datatracker.ietf.org/doc/html/rfc4918)：WebDAV方法、ETag与条件处理。HTTP条件写与服务实际行为需结合测试，不单凭OPTIONS结果判安全。

R14 [官方KDBX格式](https://keepass.info/help/kb/kdbx.html)：当前4.1、加密内容/头部边界、内层保护与二进制结构。高级用户数据的具体样本另外由参考客户端生成验证。

R15 KeePassXC commit `9e0f57a4a4c6c629fa6d0a593acb7d089b1d95cd`：[EntryAttributes.cpp](https://github.com/keepassxreboot/keepassxc/blob/9e0f57a4a4c6c629fa6d0a593acb7d089b1d95cd/src/core/EntryAttributes.cpp)，blob `e4a913b018e7f7204cb944706ae1d0f748f6c3e5`；[PasskeyUtils.cpp](https://github.com/keepassxreboot/keepassxc/blob/9e0f57a4a4c6c629fa6d0a593acb7d089b1d95cd/src/browser/PasskeyUtils.cpp)。字段和别名是生态兼容证据，不是官方KDBX规范的一部分。

R16 [1Password/passkey-rs](https://github.com/1Password/passkey-rs)：认证器/客户端/存储接口的复用候选。仅完成资料筛选，没有批准生产依赖；后续固定版本并验证平台哈希、算法和存储事务。

R17 [Apple WWDC25：凭据安全迁移](https://developer.apple.com/videos/play/wwdc2025/279/)：系统支持的迁移机制，不能推导出后台读取所有其他管理器内容的权限。

R18 [Android Credential Transfer](https://developer.android.com/identity/sign-in/credential-transfer)：独立于API34 provider的迁移功能。alpha依赖与对端互通需验证，先置于增强门槛。

R19 [Apple后台传输入口](https://developer.apple.com/documentation/foundation/downloading-files-in-the-background)：后台能力由OS调度；本方案不保证固定周期。页面正文解析有限，实施者需以SDK和真机行为补齐证据。

## 4. 研究的局限与交接

源码搜索和片段阅读只支持相应结构/字段存在，未证明整个项目安全。没有将Monica的声明直接作为实际互通验收，没有审计全部Bitwarden/Rust SDK授权，也没有测试任意用户的Microsoft租户。

下一位实施者先用本文件快照复现来源，再锁定实际要支持的**发行版本**，用合成KDBX与测试RP建立互通矩阵。修复和升级都重跑无损/签名/并发提交门槛；不以“参考项目已经有了”跳过验证。
