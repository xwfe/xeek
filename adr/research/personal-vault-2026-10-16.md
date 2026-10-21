# 个人数据保险柜与 Web 增量研究

核对日期：2026-10-16。用于 [ADR-0006](../0006-personal-data-vault.md)、[ADR-0007](../0007-web-vault-client.md) 与 [领域规格](../PERSONAL_VAULT_SPEC.md)。以下是公开资料检查，不是源码安全审计、库性能结论或依赖引入批准。所有拟引入库仍须在实施时固定版本/commit、许可证及替换边界。

## 一手资料与采纳边界

PV01 — **KeePass 官方 KDBX 规范**

- 来源：https://keepass.info/help/kb/kdbx.html
- 当前规范定义 KDBX 4.1，并提供扩展信息、附件及加密 XML 的承载位置；公开头部只应放解锁前必须读取的信息。
- 采纳：个人业务扩展仍进加密 KDBX；Protected 不是字段级独立权限。不要因格式支持扩展而假设任意实现都能无损写回。

PV02 — **keepass-rs 上游**

- 来源：https://github.com/sseemayer/keepass-rs
- README 仍把 KDBX 4.1 写入标为 experimental。页面所示 MIT 只能作为初筛，实施仍核对锁定快照和传递依赖。
- 采纳：候选而非既定生产 writer；本轮未编译、未下载依赖、未做 WASM 测试。

PV03 — **kdbx.dart 上游**

- 来源：https://github.com/authpass/kdbx.dart
- 这是 Dart 的 KDBX 实现，适合作为现有 K003 对照候选；“纯 Dart”不能代替浏览器、保护字段、附件、历史的实际验证。
- 不在本次确定版本、许可证兼容性或跨端写入结论。

PV04 — **Flutter 官方 Web 说明与 FAQ**

- 来源：https://docs.flutter.dev/platform-integration/web
- 来源：https://docs.flutter.dev/platform-integration/web/faq
- Flutter 提供 Web 目标，可共享应用代码；浏览器的插件、文件、原生调用仍有不同边界。
- 采纳：Flutter Web 优先进行复用实验，不先另开 React/Vue 客户端；不假设共享 UI 等于共享所有原生能力。

PV05 — **NexaID 官方 Web 工作台**

- 来源：https://nexaid.lengziyu.cn/
- 本次直接打开失败，但搜索抓取返回了页面正文：分类/表格视图、地区/用途搜索、主力标记、Excel/CSV 预览，以及基础资料同步与本机字段的区分。
- 采纳：类型化资料、批量整理与搜索的交互组织。它不是本项目安全底座的证据。
- 限制：本轮隐私页 https://nadmin.lengziyu.cn/privacy 也未成功读取；**不沿用前次回答中的安全/同步描述作为本轮已核实结论**，未做登录或移动端测试，未确认公开源码及 Android 发布状态。

PV06 — **Wallos 上游**

- 来源：https://github.com/ellite/Wallos
- 官方仓库定位为自托管订阅追踪，适合参考周期、费用与提醒的组织。
- 采纳业务交互，不复制账户后端/数据库，不把订阅追踪系统当秘密保险库；本轮未逐文件审计或确定代码复用许可。

PV07 — **VoucherVault 上游**

- 来源：https://github.com/l4rm4nd/VoucherVault
- 官方仓库覆盖卡券、礼品卡、会员卡、到期通知、附件和交易历史等场景。
- 采纳条码/附件/到期资料模型；不引入其服务端架构，不宣称它与 KDBX 或本项目安全要求兼容。

PV08 — **KeeWeb 官方仓库 Wiki：WebDAV**

- 来源：https://github.com/keeweb/keeweb/wiki/WebDAV-Setup
- 体现浏览器访问 WebDAV 需处理 CORS 和 ETag 暴露等部署细节。
- 仅参考问题清单；其中存在通配 origin 与凭据等示例组合，不能机械照抄到 keex，按 PV15 和实际认证方式重建配置。未验证 KeeWeb 的具体并发保存实现。

PV09 — **OWASP HTML5 Security Cheat Sheet**

- 来源：https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html
- 浏览器存储中的敏感数据、同源脚本/XSS、Worker 消息和跨源通信均需要安全边界。
- 采纳：不落明文/主密钥，严格外联与输入处理；不宣传 Worker、WASM 或客户端加密能抵挡被攻破的执行代码。

PV10 — **MDN：存储配额与驱逐**

- 来源：https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria
- 来源：https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API/Using_IndexedDB
- 浏览器存储有事务、配额和驱逐/清理边界，不等价外部备份。
- 采纳：可选密文缓存、配额/隐私模式/升级阻塞/关闭浏览器测试；不把缓存提交冒称永久保存。

PV11 — **MDN：Web Locks**

- 来源：https://developer.mozilla.org/en-US/docs/Web/API/Web_Locks_API
- 可协调同源上下文中的资源访问，不提供远端版本互斥。
- 采纳：本地多标签协调候选，同时保留版本条件；不把广播通知当锁或密钥传递通道。

PV12 — **MDN：showSaveFilePicker**

- 来源：https://developer.mozilla.org/en-US/docs/Web/API/Window/showSaveFilePicker
- 文件选择/写入入口有安全上下文、用户交互和浏览器支持条件。
- 采纳：运行时能力检测和显式导出回退；不把文件下载等同覆盖源文件，更不据 API 名称推断原子保存保证。

PV13 — **Microsoft：MSAL Browser 与缓存**

- 来源：https://learn.microsoft.com/en-us/entra/msal/javascript/browser/caching
- 来源：https://learn.microsoft.com/en-us/javascript/api/%40azure/msal-browser/?view=msal-js-latest
- 官方支持授权码 + PKCE，并提供 memoryStorage；缓存位置影响重定向和会话恢复。内存模式不支持与持久缓存相同的整页 redirect 流程。
- 采纳：Web 专用授权实验、内存 token 优先、用户触发弹窗与明确失败说明；不自动采用 SDK 默认持久策略，不认为 SDK 缓存加密能阻挡 XSS。

PV14 — **MDN：Web Authentication**

- 来源：https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API
- WebAuthn 涉及 RP、浏览器和认证器，网页客户端 API 与第三方凭据提供者是不同角色。
- 采纳：Web 管理库中记录不等于能为任意 RP 提供 Passkey；原生提供者继续按 ADR-0002/0004 验收。

PV15 — **MDN：CORS**

- 来源：https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- 非简单请求需要预检；响应头可见性、凭据模式与允许源需要匹配。
- 采纳：实际 WebDAV 读写/ETag/CAS 都在真实浏览器验证；不让用户禁用浏览器安全，不采用未知公共代理。

PV16 — **Android 官方 eUICC API**

- 来源：https://source.android.com/docs/core/connect/esim-euicc-api
- 来源：https://source.android.com/docs/core/connect/esim-overview
- 配置下载、切换和删除涉及 eUICC/LPA、运营商权限等平台条件。
- 采纳：首版仅管理资料与用户确认状态；直接安装/切换 eSIM 不是普通表单功能，也不在本次实现范围。

## 仓库事实与研究结论的界限

本轮读取的基线是 `main@2bd1f52047cd0e62a632896028e420b84b44a8a1`，初始工作树干净。K001/K002 为 REVIEW；`tests/kdbx_oracle/` 是测试对照工具，不是应用核心。K002 记录的缺失样本、参考客户端变异、工具链授权和独立复核要求继续有效，详见 [K002 证据](../evidence/K002.md)。

本次新增方案不代表已具备 Flutter/Web/移动应用、真实云同步、Passkey 或通知能力。没有读取个人真实数据，没有审计用户财务状况，也不提供银行或 eSIM 产品选择建议。
