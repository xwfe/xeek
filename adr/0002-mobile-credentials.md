# ADR-0002：iOS 与 Android 系统凭据能力

日期：2026-10-12。状态：**设计基线；原生实验和真机验收未执行**。与 [ADR-0001](0001-flutter-kdbx-architecture.md) 配合阅读；本文件优先于旧方案中“先 Android，iOS 后续”的交付顺序。

资料编号 Rxx 见 [本轮调研](research/mobile-sync-2026-10-12.md)。具体实现任务见 [移动与同步子任务](MOBILE_SYNC_TASKS.md)。

## 1. 产品能力不是一个“自动填充开关”

| 能力 | iOS 设计基线 | Android 设计基线 | keex 的责任 |
| --- | --- | --- | --- |
| 系统密码填充 | 原生 Credential Provider Extension | AutofillService；API 34+ 另接 Credential Provider | 来源匹配、选择账户、授权后返回密码 |
| 通行密钥提供者 | iOS 17+ AuthenticationServices | Android 14/API 34+ CredentialProviderService | 创建、存储、识别、签名与取消 |
| 动态口令系统填充 | iOS 18+ 可做增强 | 依赖实际请求/字段能力，不宣称全系统对等入口 | 受保护 seed、时间边界与复制/填充策略 |
| 自动升级为通行密钥 | iOS 18+ 条件注册增强 | 按平台支持另评估 | 不替代基础注册；不能未经条件验证静默创建 |
| 管理器间凭据迁移 | iOS 26+ 系统交换增强候选 | Jetpack Credentials Transfer（providerevents）：Android 8+、仅同设备、CXF 格式，2026-10 仍为 beta | 一次迁移，不等于云同步或任意读取别家密码 |

版本是对应 API 的可用范围，不是已发布支持承诺。建议首批完整 iOS 产品以 17+ 为设计基线；是否同时提供较旧系统的密码-only 版本，由 K008 实验和维护成本决定。Android Autofill 与新 Credential Provider 的平台下限分别登记，不能把调用其他管理器的 Passkey 客户端兼容范围当成本应用 provider 的范围。[R03–R06,R17,R18]

系统只会按授权协议调用 keex。它不会自动理解任意 KDBX 字段，也不允许 keex 无提示读取整个 Apple 密码/iCloud 钥匙串或 Google 密码库。四层能力必须独立显示：**记录可识别 → 核心可使用 → 已启用系统提供者 → 远端已确认同步**。

## 2. 共用核心，分别接入系统

```text
Flutter 主应用：五分类、编辑、设置、同步/冲突处理
       │                         │
Swift 原生凭据扩展            Kotlin 原生服务 + Activity
AuthenticationServices         Autofill / Credential Provider
       └──────── 类型化凭据请求 ────────┘
                    ↓
 CredentialCoordinator / VaultAccess / Signing / StorageCommit
                    ↓
   经授权的本机 .kdbx + 受限元数据索引 + OS 设备解封材料
```

原生入口只负责协议分发、系统认证及最小交互；策略、匹配、错误分类、加密和写入放进可测试模块。Bitwarden Android 的薄服务转交 processor、iOS 的 controller/context/service 分层可借鉴；不引入 Bitwarden 账户服务器或其数据库模型。[R01,R02]

Rust 核心应可产出 Swift/Kotlin 可调用的库，原生扩展不能依赖 Dart isolate、主 Flutter 引擎、主程序已打开或后台常驻。Flutter↔Rust 桥接和原生↔Rust 桥接是两个验收项。构建产物不带不必要的网络/GUI依赖，未验证的 panic 不得跨 ABI 边界。

## 3. iOS 原生扩展设计

主应用、Credential Provider Extension 分开 target。逐项配置 App Group、Keychain access group、AutoFill entitlement 和提供者 capability；不能只在 Runner 打勾就认为扩展有权限。扩展界面使用原生 SwiftUI/UIKit 的必要页面，不在扩展里加载整套 Flutter 应用。[R01,R04]

处理路径包括：密码候选列表、无交互请求、需要交互的解锁/选择、Passkey 注册与断言、用户取消、缺失条目、只读库和资源不足。无交互请求无法满足授权时返回 `userInteractionRequired`，不是自行弹一个不受系统管理的认证框。最终只调用相应的系统 complete/cancel 入口一次。

`ASCredentialIdentityStore` 是系统候选索引，不是存储私钥的地方。拟定索引标识为本机 `VaultBindingId + EntryUUID + CredentialID摘要`；它不是网站认证所用的 credentialId。密码、OTP seed、PEM、主密码及云令牌绝不进入该索引。注意 Passkey 候选 `ASPasskeyCredentialIdentity`（iOS 17+）的构造参数**必须**带 `credentialID` 和 `userHandle`（`init(relyingPartyIdentifier:userName:credentialID:userHandle:recordIdentifier:)`），有的网站拿邮箱或账号 ID 当 userHandle。所以进系统索引的是账户名、RP ID、credentialID、userHandle 和 keex 自己的 recordIdentifier；它们虽不是私钥，仍有隐私价值：开启候选提示需说明，停用/移除库要清理，锁定时展示程度按用户隐私策略控制。

索引更新在本地事务提交后进行；编辑、导入、同步合并、恢复、删除、主库解绑都标记 index dirty。更新失败保留可恢复状态，下次重建。每次系统请求仍从已授权的当前库校验记录和版本，不把过期索引直接当作凭据授权。系统传入的 service identifiers 是建议排序线索，不能替代真正的 Passkey 请求参数与系统信任边界。[R04]

### 本机存储与跨进程协调

直接云同步模式在 App Group 内保存受保护的本机 KDBX 工作文件，主程序与扩展共享访问；远端仅是这份库的同步副本。元数据文件只保存绑定、generation、索引状态和传输状态，不另外保存一套可独立修改的凭据数据库。

已有外部文件通过系统文件选择器接入时，必须声明它是“外部文件绑定”还是“导入并由 keex 管理的本地库”。访问授权、文件协调和扩展可访问性需验证，不能默默复制后声称仍编辑原文件。无法保证扩展写入的绑定只能提供经过验证的只读能力，注册入口必须解释原因。

主程序与扩展是**多进程、同一时刻一个提交者**，不是主程序永远充当写入服务器。读取 generation → 锁外生成待保存密文 → 获取共享协调锁 → 再验 generation/撤权 epoch → 提交并验证 → 更新元数据。被其他进程修改则重新读取/拒绝，不覆盖。锁等待有期限；进程退出不会永久占有锁。

请求内授权不能无限缓存。主程序锁库、系统保护状态变化、退出授权范围后，跨进程撤权 epoch 同步失效。签名/复制响应前再校验；约定最终授权检查为线性化点，不能承诺撤回已经返回给调用者的密码或签名。

### 内存与大库

扩展预算要实测：KDF 工作内存 + 解密结构 + 附件/历史 + 签名 + 原生 UI 都算在内。KeePassium 的内存问题说明了这是真实工程风险；其文档数字不是所有 iOS 版本通用的固定系统契约。[R07]

POC 用同样条目数、不同附件/历史/KDF 的库分别测冷启动和注册写入。不能为了适应扩展偷偷降低已有库 KDF；不能只在内存生成私钥就向网站返回注册成功。超预算时保留原库、返回可理解的失败；可建议用户显式整理附件或另建较小库，但不得自动分拆和复制秘密。未经单独威胁分析，不引入永久解锁的“快捷密码副库”绕开问题。

## 4. Android 两套接口并存

AutofillService 负责传统表单填充/保存及已验证的 inline 候选；解析表单时限制树深、节点和字段长度。默认不申请 AccessibilityService、悬浮窗、全屏文本采集或自定义键盘权限来替代系统自动填充。特殊兼容手段必须单独评审，不把 Monica 的可选能力全搬进来。

Android 14+ 服务采用 begin/query 与最终选择两个阶段。第一阶段只返回最小候选/解锁 action；第二阶段由系统触发原生 Activity，使用正式 handler 提取最终请求并重新验证，不信任第一阶段自带 extras 即全部事实。保存成功后才返回创建完成，取消信号向核心传递。[R03,R08]

实现容易出错的边界：服务必须以系统 bind 权限限制调用；provider 流程的 PendingIntent 按官方协议使用 **MUTABLE** 以接收系统附加数据，绑定显式目标并给每条目独立 request code，不用 ONE_SHOT。不能套用“所有 PendingIntent 一律不可变”的通用模板。[R03]

原生调用者核对 package、签名与 Digital Asset Links；特权浏览器 origin 必须经可信包及签名验证后接受。系统/可信浏览器已经执行的 WebAuthn client 校验与本地 authenticator 职责分开；不要增加“origin 主机必须等于 RP ID”的错误规则，避免拒绝合法 Related Origin Requests。任何附加验证必须符合 ROR 规范，不能借此跳过调用者认证或拿其他 RP 的私钥签名。[R03]

最终请求中的 `clientDataHash` 如来自合法平台路径，应使用其原始值；不能重新拼装 JSON 得到不同 hash。`onClearCredentialStateRequest` 清理对应登录/选择状态，不等于删除密码库里的凭据。

## 5. 用户流程与限制

启用向导仅引导系统授权并复查结果；不要求关闭其他密码管理器，不使用私有 Settings URL，不把旧版设置路径写死为所有系统共用。OTP、条件升级、凭据交换单独通过运行时能力检查显示，不以一个开关全部标绿。

扩展只有“选择凭据、创建凭据、授权、完成/取消”的紧凑流程，不出现五项主应用导航、云账号登录或安全审计。没有可用本地副本/同步令牌过期不应迫使用户在网站登录弹窗里做 Microsoft 登录；提示回主应用恢复，已有本地可用凭据按离线策略处理。

密码保存与更新按操作系统实际回调范围实现；iOS 扩展内新增条目是可设计的流程，但不承诺系统会把每个网站的全部注册/改密表单自动交给 keex。自动升级 Passkey 必须保持网站密码可用，不以升级为由删除密码。

## 6. 验收增量

必须测：主程序终止时请求；多库同 UUID 隔离；索引过期；锁库与响应竞态；生物认证取消；来源/签名不符；匹配为空；离线；扩展超预算；系统杀进程；创建时主程序并发编辑。原生测试证据与 HTML 交互证据分开。

“注册成功”分为本机保存、provider 返回、网站确认三个不同观测点；后者不一定回传给 provider。云同步尚未确认时允许已保存凭据在本机使用，但必须显示待同步，不能冒称已在其他设备可用。
